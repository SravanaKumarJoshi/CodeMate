# CodeMate — Large Repository AI Codebase Assistant

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111+-009688.svg)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2+-orange.svg)](https://github.com/langchain-ai/langgraph)
[![ChromaDB](https://img.shields.io/badge/ChromaDB-0.5+-green.svg)](https://www.trychroma.com/)
[![Tests](https://img.shields.io/badge/Tests-38%20Passed-brightgreen.svg)]()
[![Security](https://img.shields.io/badge/Security-ZipSlip%20%7C%20No%20Exec-red.svg)]()

> A production-grade AI codebase assistant capable of ingesting real-world software repositories (up to **2 GB archives**), parsing syntax trees with **AST-aware chunking**, coordinating multi-step reasoning through a **LangGraph agentic loop**, and answering open-ended developer inquiries with **grounded citations**.

---

## 1. Executive Summary & Architecture

CodeMate is engineered to eliminate the limitations of naive codebase chatbots. It does not load entire repositories into memory, does not dump massive files into LLM context windows, and does not restrict developers to rigid hard-coded questions.

```text
                 USER
                   ↓
               FRONTEND (UI & Project Explorer)
                   ↓  HTTP POST /api/chat
               FASTAPI (Pydantic & Auth Validation)
                   ↓
          ML INTENT CLASSIFIER (TF-IDF + Logistic Regression)
                   ↓ (Routing Signal)
             LANGGRAPH AGENT (Cyclic Cognitive Loop)
                   ↓
          ┌────────┼───────────────────────────┐
          ↓        ↓                           ↓
       SEARCH   READ FILE   SYMBOLS   FILE LISTER   TEST GEN
          ↓        ↓                           ↓
          └────────┼───────────────────────────┘
                   ↓
              RAG ENGINE
                   ↓ (where={"repository_id": repo_id})
               CHROMADB (AST Vectors)
                   ↓
              LLM ENGINE (OpenAI / Grounded Local Synthesizer)
                   ↓
          RESPONSE SYNTHESIS (Clickable Citations)
                   ↓
               FASTAPI
                   ↓
               FRONTEND
                   ↓
                  USER
```

---

## 2. Core Capabilities & Architectural Pillars

### Large Repository Streaming Ingestion
- **2 GB Upload Support**: Files are streamed directly to disk in 64 KB chunks (`UPLOAD_CHUNK_SIZE_KB=64`). Archives are never loaded into RAM.
- **Incremental Processing**: Files are scanned, AST-parsed, and vectorized in batches of 64 chunks, freeing memory after every batch.
- **Asynchronous Background Indexing**: `POST /api/repositories/upload` returns an immediate `202 Accepted` with a repository ID. Clients track progress via `GET /api/repositories/{id}/status`.

### Archive Security & Defense-in-Depth
- **Zip Slip Defense**: Path normalization verifies extracted members stay strictly within the repository storage directory.
- **Archive Bomb Protection**: Pre-decompression inspections reject archives exceeding 100x expansion ratio or 5 GB uncompressed size.
- **Symlink Disallowance**: Symlinks and hardlinks are rejected to prevent host filesystem escape.
- **No Arbitrary Code Execution**: Uploaded code is strictly treated as passive data. CodeMate never invokes shells, compilers, or subprocesses. Generated unit tests are never auto-executed.

### AST-Aware Code Chunking
- **Python AST**: Uses `ast.parse` to extract semantic boundaries: `ClassDef`, `FunctionDef`, `AsyncFunctionDef`, methods, module docstrings, and imports blocks.
- **Structural Code Parser**: Regular expression structural extractors parse classes, functions, and interfaces for JavaScript, TypeScript, Go, Rust, Java, C++, and SQL.
- **Line-Level Metadata**: Every chunk retains:
  ```json
  {
    "repository_id": "repo_ecomm_prod",
    "file_path": "backend/auth.py",
    "language": "python",
    "start_line": 20,
    "end_line": 57,
    "symbol": "verify_token",
    "chunk_type": "function"
  }
  ```

### Repository Isolation
- Every vector chunk in ChromaDB is indexed with a `repository_id`.
- Retrieval queries enforce mandatory metadata filtering:
  ```python
  collection.query(query_texts=[query], where={"repository_id": active_repo_id})
  ```
  This guarantees zero cross-repository data leakage.

### LangGraph Agentic Loop
Unlike linear `Question -> Tool -> Answer` chains, CodeMate runs a state machine:
`START -> classify_intent -> reason -> [should_continue: execute_tools -> reason | generate_response] -> END`
- **Dynamic Chaining**: The agent can search code, inspect the result, decide to read specific lines from a file, and then synthesize the final answer.
- **Safety Guardrails**: Configurable ceilings prevent runaway loops (`MAX_AGENT_ITERATIONS=4`, `MAX_TOOL_CALLS=6`, `MAX_RETRIEVED_CHUNKS=8`).

### Dedicated Interactive Workflow Page
A dedicated page accessible at `/workflow` (or via the Workflow tab):
- **Visual Architecture Pipeline**: Click any component (FastAPI, ML Classifier, LangGraph Agent, Tools, RAG, LLM) to inspect its technical specifications, model types, inputs, outputs, and security controls.
- **Live Request Lifecycle Tracer**: Automatically polls `GET /api/workflow/{request_id}` to show the real-time execution steps, durations, and tool outputs for queries executed in chat.

---

## 3. Supported Interview Demonstration Scenarios

The system natively answers the 10 core interview questions using the indexed sample codebase:

| # | Demo Question | Verified Sources |
|---|---|---|
| 1 | *Where is authentication implemented?* | `auth.py:18-63`, `api/users.py:35-72` |
| 2 | *Explain how login works in this application.* | `api/users.py:35-72`, `auth.py:20-57` |
| 3 | *Generate unit tests for the login function.* | `auth.py:18-63`, `api/users.py:35-72` |
| 4 | *Why could the login endpoint return a 401 error?* | `api/users.py:40-52`, `auth.py:45-65` |
| 5 | *Explain the complete architecture of this project.* | `main.py:1-40`, `database.py:1-35`, `models.py:1-55` |
| 6 | *What database does this application use?* | `database.py:8-25`, `config.py:10-22` |
| 7 | *How does the users API interact with authentication?* | `api/users.py:20-68`, `auth.py:18-63` |
| 8 | *List the important files involved in user registration.* | `api/users.py:20-34`, `auth.py:18-28`, `models.py:12-28` |
| 9 | *Where is the database connection configured?* | `config.py:10-22`, `database.py:8-28` |
| 10 | *Give me a summary of this repository.* | `main.py:1-40`, `api/users.py:1-80`, `api/orders.py:1-60` |

Plus open-ended queries (e.g. data flow tracking, dependency inspection, bug analysis, configuration verification).

---

## 4. Installation & Local Setup

### Prerequisites
- Python 3.11+
- Virtual environment (recommended)

### 1. Clone & Setup Environment
```bash
git clone <repository-url>
cd Projectt

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Environment Configuration
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
To enable online OpenAI mode, set your key in `.env`:
```ini
OPENAI_API_KEY=sk-your-openai-api-key
```
*Note: If no API key is set, CodeMate runs seamlessly in zero-config offline mode with grounded responses.*

### 3. Start the Application
```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
Open your browser at:
**http://127.0.0.1:8000**

---

## 5. Reverse-Proxy Configuration (For 2 GB Uploads)

When deploying behind **Nginx**, adjust `client_max_body_size` and disable request buffering for streaming:

```nginx
server {
    listen 80;
    server_name codemate.example.com;

    # Allow up to 2 GB repository uploads
    client_max_body_size 2048M;
    client_body_buffer_size 128k;

    # Stream requests directly to backend without buffering entire file
    proxy_request_buffering off;
    proxy_buffering off;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 600s;
        proxy_connect_timeout 600s;
    }
}
```

---

## 6. Testing

The project includes 38 automated tests covering security, chunking, retrieval, agent loops, API contracts, and the 10 demo queries.

Run all tests:
```bash
pytest
```

Run test suites individually:
```bash
# Security tests (Zip Slip, Path Traversal, Archive Bomb)
pytest tests/test_security.py

# Large repository streaming & multi-repo isolation tests
pytest tests/test_large_repo.py

# All 10 demo queries & open-ended reasoning tests
pytest tests/test_demo_queries.py
```

---

## 7. Project Structure

```text
├── app/
│   ├── agents/            # LangGraph cognitive state graph, nodes, and router
│   ├── api/               # FastAPI endpoints (chat, repositories, workflow, files, auth)
│   ├── config.py          # Centralized settings, limits, and guardrails
│   ├── main.py            # FastAPI entrypoint, lifespan auto-indexing, and CORS
│   ├── ml/                # Scikit-learn model inference wrapper
│   ├── models/            # SQLAlchemy database models (Repository, User, WorkflowEvent)
│   ├── rag/               # AST chunking, batch embeddings, ChromaDB retriever, ingestion
│   ├── security/          # Zip Slip, path traversal defense, and JWT auth
│   ├── services/          # LLM service, repository service, workflow event tracer
│   └── tools/             # Narrow agent tools (search_code, read_file, symbols, test_gen)
├── data/                  # SQLite DB, ChromaDB vector storage, extracted projects
├── docs/                  # In-depth Architecture, Security, and API documentation
├── frontend/              # Developer UI (HTML5, Vanilla CSS, app.js, Workflow page)
├── ml/                    # Classifier training dataset and training script
├── sample_project/        # Realistic e-commerce reference codebase
├── tests/                 # 38 unit & integration tests
├── requirements.txt       # Python dependencies
└── README.md              # Project documentation
```

---

## 8. Final Interview Value Proposition

> **"This project demonstrates end-to-end expertise in training a machine learning model, integrating AI into an asynchronous Python backend, architecting memory-bounded ingestion for 2 GB repositories, building a cyclic LangGraph tool-calling agent, implementing isolated RAG retrieval, enforcing security defenses against Zip Slip and prompt injection, and connecting the entire system to an interactive developer frontend with real-time lifecycle visualization."**
