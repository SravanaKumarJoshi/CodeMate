# CodeMate Architecture & System Design

## 1. System Overview

CodeMate is a production-quality, large-repository AI codebase assistant designed to ingest real-world software repositories (up to 2 GB archives), understand their syntax, architecture, and documentation, and answer open-ended developer inquiries with strict factual grounding and line-level citations.

```text
┌────────────────────────────────────────────────────────────────────────┐
│                              FRONTEND                                  │
│  [Repository Selector]  [Project Explorer]  [Chat Area]  [Workflow View]│
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ HTTP / REST
┌───────────────────────────────────▼────────────────────────────────────┐
│                           FASTAPI BACKEND                              │
│  /api/repositories (upload, status, list) | /api/chat | /api/workflow │
└─────────┬─────────────────────────┬──────────────────────┬─────────────┘
          │ (Background Task)       │                      │
┌─────────▼──────────┐    ┌─────────▼──────────┐ ┌─────────▼─────────────┐
│ INGESTION PIPELINE │    │   ML CLASSIFIER    │ │   WORKFLOW STORE      │
│ - Streaming Upload │    │ TF-IDF + LogReg    │ │ Logs request lifecycle│
│ - Safe Extraction  │    │ 6 Intent Classes   │ │ Timeline & tool audits│
│ - AST / Code Chunk │    └─────────┬──────────┘ └───────────────────────┘
│ - Batch Embedding  │              │ (Routing signal)
└─────────┬──────────┘    ┌─────────▼────────────────────────────────────┐
          │               │         LANGGRAPH AGENT LOOP                 │
┌─────────▼──────────┐    │ State: query, intent, tool_calls, context    │
│     CHROMADB       │    │ Loop: decide -> execute -> inspect -> loop   │
│ - Vector Search    │◄───┤ Tools: search_code, read_file, search_symbols│
│ - Filter by repo_id│    │        list_project_files, generate_test     │
└────────────────────┘    └─────────┬────────────────────────────────────┘
                                    │
                          ┌─────────▼──────────┐
                          │    LLM / RAG       │
                          │ Grounded Synthesis │
                          │ Source Citations   │
                          └────────────────────┘
```

---

## 2. Ingestion & Large Repository Processing

To process archives up to 2 GB without exceeding memory limits:
1. **Streaming Uploads**: The file stream is piped directly to disk in 64 KB chunks (`UPLOAD_CHUNK_SIZE_KB = 64`). The full file is never buffered into RAM.
2. **Pre-Extraction Security Audits**: Archive is checked for Zip Slip, archive bombs (decompression ratio limit: 100x, decompressed size limit: 5 GB), max file counts (100,000 files), and disallowed symlinks.
3. **Smart Filtering**: Disallowed extensions (binaries, executables, videos) and directories (`.git`, `node_modules`, `venv`, `dist`, `__pycache__`, etc.) are skipped during filesystem traversal.
4. **AST-Aware Parsing**:
   - Python files are parsed using `ast.parse` to extract `ClassDef`, `FunctionDef`, `AsyncFunctionDef`, methods, imports, and docstrings with exact line numbers and symbol names.
   - Other languages (JS, TS, Go, Rust, Java, SQL, C++) are split using structural definitions.
5. **Incremental Batch Vectorization**: Chunks are added to ChromaDB in batches of 64 with `repository_id` metadata. Memory is reclaimed after each batch.
6. **Progress Tracking**: Real-time updates (`processed_files`, `total_files`, `total_chunks`, `progress`) are recorded in the database, viewable via `GET /api/repositories/{id}/status`.

---

## 3. LangGraph Cognitive Agent Workflow

Unlike static pipelines, CodeMate uses a cyclic LangGraph directed state graph:
1. **`classify_intent`**: Traditional ML (scikit-learn TF-IDF + Logistic Regression) generates a routing signal across 6 intents (`CODE_SEARCH`, `CODE_EXPLANATION`, `BUG_ANALYSIS`, `TEST_GENERATION`, `ARCHITECTURE`, `GENERAL_QUERY`).
2. **`reason`**: The agent analyzes the user question, previous observations, and gathered context to decide the next action or tool.
3. **`execute_tools`**: The agent executes narrow, safe tools:
   - `search_code`: Semantic vector search in ChromaDB.
   - `read_file`: Path-safe file reading with line ranges.
   - `search_symbols`: AST class/function definition lookup.
   - `list_project_files`: Repository file tree inspection.
   - `retrieve_context`: Multi-query vector context retrieval.
   - `generate_unit_test`: Test scaffolding generator (never automatically executed).
4. **`should_continue`**: Evaluates whether sufficient evidence has been gathered or if another tool iteration is needed. Guardrails limit execution to 4 iterations and 6 tool calls.
5. **`generate_response`**: Synthesizes the grounded response with source citations.

---

## 4. Multi-Repository Isolation

Every chunk in ChromaDB is indexed with a `repository_id` metadata attribute. All vector searches enforce a strict metadata filter:
```python
where={"repository_id": target_repo_id}
```
This guarantees that queries from one repository cannot retrieve code or secrets from another repository.

---

## 5. Dual LLM Engine (Online & Local Grounded)

- **Online Mode**: When `OPENAI_API_KEY` is configured, CodeMate delegates grounded synthesis to GPT-4o-mini with prompt injection protection.
- **Offline / Zero-Config Demo Mode**: When no API key is provided, CodeMate uses an intelligent local grounded synthesizer that parses retrieved AST chunks, inspects tool observations, and generates technically deep answers with citations.
