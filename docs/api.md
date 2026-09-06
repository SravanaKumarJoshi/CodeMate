# CodeMate REST API Reference

All API endpoints are prefixed with `/api`.

---

## Health & Diagnostics

### `GET /api/health`
Returns system status, ML model readiness, ChromaDB indexed chunk counts, and LLM operational mode.

**Response:**
```json
{
  "status": "ok",
  "service": "CodeMate",
  "version": "2.0.0",
  "environment": "development",
  "ml_model_loaded": true,
  "vector_db": {
    "status": "connected",
    "indexed_chunks": 42,
    "collection": "codemate_chunks"
  },
  "llm_mode": "offline_demo",
  "active_repository_id": "repo_sample_project",
  "max_upload_size_mb": 2048
}
```

---

## Repositories & Ingestion

### `POST /api/repositories/upload`
Uploads a repository ZIP archive (up to 2 GB) or initializes the bundled sample project. Streams archive directly to disk without buffering into RAM.

**Form Data:**
- `file`: (Optional) ZIP file upload
- `use_sample`: (Optional) Boolean, true to load sample e-commerce project
- `repository_name`: (Optional) Custom display name

**Response (202 Accepted):**
```json
{
  "repository_id": "repo_a81f03cd",
  "repository_name": "MyProject",
  "status": "indexing"
}
```

### `GET /api/repositories/{repository_id}/status`
Polls real-time progress of a background indexing job.

**Response:**
```json
{
  "repository_id": "repo_a81f03cd",
  "repository_name": "MyProject",
  "status": "indexing",
  "files_processed": 140,
  "total_files": 420,
  "chunks_created": 890,
  "progress": 33,
  "error_message": null
}
```

### `GET /api/repositories`
Lists all repositories owned by the current user or sample repositories.

### `POST /api/repositories/{repository_id}/activate`
Switches the active repository used for default queries.

### `DELETE /api/repositories/{repository_id}`
Deletes repository files and cleans up vector embeddings from ChromaDB.

---

## Codebase Chat & Reasoning

### `POST /api/chat`
Executes the full LangGraph agent cognitive cycle: intent classification -> reasoning -> dynamic tool execution -> RAG -> grounded response synthesis.

**Request:**
```json
{
  "message": "Where is authentication implemented?",
  "repository_id": "repo_sample_project"
}
```

**Response:**
```json
{
  "request_id": "req_1038592a",
  "repository_id": "repo_sample_project",
  "answer": "Authentication is implemented in auth.py...",
  "intent": "CODE_SEARCH",
  "confidence": 0.94,
  "sources": [
    {
      "file": "auth.py",
      "start_line": 18,
      "end_line": 63
    },
    {
      "file": "api/users.py",
      "start_line": 35,
      "end_line": 72
    }
  ],
  "tools_used": ["search_code", "read_file"],
  "tool_calls": [
    {
      "tool": "search_code",
      "args": {"query": "Where is authentication implemented?"},
      "summary": "Retrieved 4 code chunks"
    }
  ],
  "workflow_steps": ["user_request", "intent_classifier", "agent_reasoning", "search_code", "read_file", "llm_synthesis", "response_synthesis"],
  "duration_ms": 142
}
```

---

## Interactive Workflow & Diagnostics

### `GET /api/workflow/{request_id}`
Returns the live execution timeline of a specific chat query.

**Response:**
```json
{
  "request_id": "req_1038592a",
  "repository_id": "repo_sample_project",
  "query": "Where is authentication implemented?",
  "intent": "CODE_SEARCH",
  "status": "completed",
  "duration_ms": 142,
  "steps": [
    {
      "name": "user_request",
      "status": "completed",
      "detail": "Received HTTP POST /api/chat",
      "timestamp": "2026-09-06T12:00:00Z"
    },
    {
      "name": "intent_classifier",
      "status": "completed",
      "detail": "Classified as CODE_SEARCH (confidence: 0.94)",
      "timestamp": "2026-09-06T12:00:00.020Z"
    },
    {
      "name": "search_code",
      "status": "completed",
      "detail": "Retrieved 4 code chunks",
      "timestamp": "2026-09-06T12:00:00.050Z"
    }
  ]
}
```

### `GET /api/workflow/architecture`
Returns metadata and technology specifications for all nodes in the architecture.

---

## File Exploration

### `GET /api/files?repository_id={id}`
Returns all source files discovered within the authorized repository.

### `GET /api/files/content?file_path={path}&start_line={s}&end_line={e}`
Safely returns file contents with path traversal protection.
