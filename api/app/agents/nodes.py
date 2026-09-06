"""
LangGraph Workflow Nodes for CodeMate.
Implements the real agentic cognitive loop:
classify_intent -> reason -> execute_tools -> inspect_and_reason_again -> generate_response
"""

import logging
from pathlib import Path
from typing import Dict, Any, List
from app.agents.state import AgentState
from app.config import settings
from app.ml.classifier import classify_intent
from app.tools.code_search import search_code
from app.tools.file_reader import read_file
from app.tools.test_generator import generate_unit_test
from app.tools.file_lister import list_project_files
from app.tools.search_symbols import search_symbols
from app.tools.retrieve_context import retrieve_context
from app.services.llm_service import generate_llm_response
from app.services.workflow_service import add_workflow_step
from app.agents.repo_analyzer import is_broad_repo_query, get_repo_query_subtype

logger = logging.getLogger(__name__)


def classify_intent_node(state: AgentState) -> Dict[str, Any]:
    """
    Node 1: Classifies the user's intent using the trained scikit-learn model.
    Serves as an initial routing signal without restricting the agent's capabilities.
    """
    query = state.get("query", "")
    req_id = state.get("request_id", "req_unknown")

    classification = classify_intent(query)
    intent = classification.get("intent", "GENERAL_QUERY")
    confidence = classification.get("confidence", 0.0)

    add_workflow_step(
        request_id=req_id,
        step_name="intent_classifier",
        status="completed",
        detail=f"Classified as {intent} (confidence: {confidence:.2f})",
        data={"intent": intent, "confidence": confidence}
    )

    logger.info("Classified query '%s' as %s (confidence: %.2f)", query, intent, confidence)
    return {
        "intent": intent,
        "confidence": confidence,
        "iteration": 0,
        "max_iterations": settings.MAX_AGENT_ITERATIONS,
        "is_finished": False,
        "reasoning_notes": []
    }


def reasoning_node(state: AgentState) -> Dict[str, Any]:
    """
    Node 2: Cognitive Reasoning & Tool Decision.
    Evaluates current state, queries, and past observations to select the next action.
    """
    req_id = state.get("request_id", "req_unknown")
    query = state.get("query", "").lower()
    intent = state.get("intent", "GENERAL_QUERY")
    iteration = state.get("iteration", 0)
    max_iter = state.get("max_iterations", settings.MAX_AGENT_ITERATIONS)
    tool_calls = state.get("tool_calls", [])
    retrieved_context = state.get("retrieved_context", [])
    sources = state.get("sources", [])
    repo_id = state.get("repository_id", "default_repo")

    tools_to_run: List[Dict[str, Any]] = []
    is_finished = False
    is_repo_query = is_broad_repo_query(query, intent)

    # Iteration 0: Initial tool selection based on intent and query
    if iteration == 0:
        if is_repo_query:
            # Broad project understanding workflow starts with repository structural enumeration
            tools_to_run.append({"tool": "list_project_files", "args": {"repository_id": repo_id}})
            tools_to_run.append({"tool": "retrieve_context", "args": {"query": "project overview architecture description dataset", "repository_id": repo_id, "top_k": 4}})
        elif intent == "ARCHITECTURE" or any(w in query for w in ["overview", "summary", "files", "structure"]):
            tools_to_run.append({"tool": "list_project_files", "args": {"repository_id": repo_id}})
            tools_to_run.append({"tool": "search_code", "args": {"query": query, "repository_id": repo_id, "top_k": 4}})
        elif intent == "TEST_GENERATION" or "test" in query:
            tools_to_run.append({"tool": "search_code", "args": {"query": query, "repository_id": repo_id, "top_k": 3}})
            tools_to_run.append({"tool": "generate_unit_test", "args": {"code": query, "framework": "pytest"}})
        elif any(w in query for w in ["class", "function", "method", "def ", "symbol"]):
            # Extract likely symbol
            words = [w.strip("?,.:;\"'") for w in query.split()]
            sym = words[-1] if words else query
            tools_to_run.append({"tool": "search_symbols", "args": {"symbol_name": sym, "repository_id": repo_id}})
            tools_to_run.append({"tool": "retrieve_context", "args": {"query": query, "repository_id": repo_id, "top_k": 3}})
        else:
            # Default first pass: semantic code search
            tools_to_run.append({"tool": "search_code", "args": {"query": query, "repository_id": repo_id, "top_k": 4}})

    # Iteration 1+: Inspect results and decide whether to drill deeper (e.g. read_file) or conclude
    else:
        read_tools_already = [t.get("args", {}).get("file_path") for t in tool_calls if t.get("tool") == "read_file"]

        if is_repo_query:
            # Inspect discovered files and read high-value documentation first
            lister_call = next((tc for tc in tool_calls if tc.get("tool") == "list_project_files"), None)
            enum_files = lister_call.get("files", []) if lister_call else []
            file_paths = [f.get("path", "") if isinstance(f, dict) else str(f) for f in enum_files]

            doc_priority = [
                "README.md", "README", "technologies.md", "data_schema.md",
                "DATASETS.md", "AndroidManifest.xml", "build.gradle", "package.json", "requirements.txt"
            ]
            to_read = []
            for target_name in doc_priority:
                for fp in file_paths:
                    if (Path(fp).name.lower() == target_name.lower() or fp.lower().endswith(target_name.lower())) and fp not in read_tools_already:
                        if fp not in to_read:
                            to_read.append(fp)
                            break

            for doc_path in to_read[:2]:
                if len(tool_calls) + len(tools_to_run) < settings.MAX_TOOL_CALLS:
                    tools_to_run.append({
                        "tool": "read_file",
                        "args": {"file_path": doc_path, "start_line": 1, "end_line": 100, "repository_id": repo_id}
                    })

            if not tools_to_run or iteration >= 2:
                is_finished = True

        else:
            # Standard single-file drill-down
            if sources and not read_tools_already and len(tool_calls) < settings.MAX_TOOL_CALLS:
                top_file = sources[0].get("file") if isinstance(sources[0], dict) else str(sources[0])
                if top_file and top_file != "unknown":
                    tools_to_run.append({
                        "tool": "read_file",
                        "args": {"file_path": top_file, "start_line": 1, "end_line": 75, "repository_id": repo_id}
                    })

            # If we have enough context or reached limits, conclude
            if not tools_to_run or iteration >= (max_iter - 1) or len(tool_calls) >= settings.MAX_TOOL_CALLS:
                is_finished = True

    add_workflow_step(
        request_id=req_id,
        step_name="agent_reasoning",
        status="completed",
        detail=f"Iteration {iteration + 1}: decided {[t['tool'] for t in tools_to_run] or 'conclude'}",
        data={"iteration": iteration + 1, "tools_decided": [t["tool"] for t in tools_to_run], "is_finished": is_finished}
    )

    logger.info("Agent Reasoning (Iteration %d): decided %s (finished=%s)", iteration, tools_to_run, is_finished)
    return {
        "tools_to_run": tools_to_run,
        "is_finished": is_finished,
        "iteration": iteration + 1
    }


def execute_tools_node(state: AgentState) -> Dict[str, Any]:
    """
    Node 3: Executes decided tools safely, accumulates context, and updates audit records.
    """
    req_id = state.get("request_id", "req_unknown")
    tools_to_run = state.get("tools_to_run", [])
    repo_id = state.get("repository_id", "default_repo")

    tool_calls: List[Dict[str, Any]] = list(state.get("tool_calls", []))
    retrieved_context: List[Dict[str, Any]] = list(state.get("retrieved_context", []))
    sources: List[Dict[str, Any]] = list(state.get("sources", []))
    tools_used: List[str] = list(state.get("tools_used", []))

    for item in tools_to_run:
        tool_name = item.get("tool")
        args = item.get("args", {})

        if tool_name not in tools_used:
            tools_used.append(tool_name)

        if tool_name == "search_code":
            q = args.get("query", "")
            chunks = search_code(q, repository_id=repo_id, top_k=args.get("top_k", 4))
            retrieved_context.extend(chunks)
            tool_calls.append({
                "tool": "search_code",
                "args": args,
                "summary": f"Retrieved {len(chunks)} code chunks"
            })
            for c in chunks:
                fp = c.get("file_path")
                s_l = c.get("start_line", 1)
                e_l = c.get("end_line", 1)
                if fp and not any(s.get("file") == fp for s in sources):
                    sources.append({"file": fp, "start_line": s_l, "end_line": e_l})

            add_workflow_step(req_id, "search_code", "completed", f"Retrieved {len(chunks)} code chunks")

        elif tool_name == "retrieve_context":
            q = args.get("query", "")
            chunks = retrieve_context(q, repository_id=repo_id, top_k=args.get("top_k", 4))
            retrieved_context.extend(chunks)
            tool_calls.append({
                "tool": "retrieve_context",
                "args": args,
                "summary": f"Retrieved {len(chunks)} semantic chunks"
            })
            for c in chunks:
                fp = c.get("file_path")
                s_l = c.get("start_line", 1)
                e_l = c.get("end_line", 1)
                if fp and not any(s.get("file") == fp for s in sources):
                    sources.append({"file": fp, "start_line": s_l, "end_line": e_l})

            add_workflow_step(req_id, "retrieve_context", "completed", f"Retrieved {len(chunks)} semantic chunks")

        elif tool_name == "search_symbols":
            sym = args.get("symbol_name", "")
            chunks = search_symbols(sym, repository_id=repo_id, limit=args.get("limit", 4))
            retrieved_context.extend(chunks)
            tool_calls.append({
                "tool": "search_symbols",
                "args": args,
                "summary": f"Found {len(chunks)} symbol matches for '{sym}'"
            })
            for c in chunks:
                fp = c.get("file_path")
                s_l = c.get("start_line", 1)
                e_l = c.get("end_line", 1)
                if fp and not any(s.get("file") == fp for s in sources):
                    sources.append({"file": fp, "start_line": s_l, "end_line": e_l})

            add_workflow_step(req_id, "search_symbols", "completed", f"Found {len(chunks)} symbol matches for '{sym}'")

        elif tool_name == "read_file":
            fp = args.get("file_path", "")
            s_l = args.get("start_line", 1)
            e_l = args.get("end_line", 80)
            res = read_file(fp, start_line=s_l, end_line=e_l, repository_id=repo_id)
            tool_calls.append({
                "tool": "read_file",
                "args": args,
                "summary": f"Read {res.get('total_lines', 0)} lines from {fp}"
            })
            if res.get("status") == "success":
                retrieved_context.append({
                    "file_path": fp,
                    "start_line": s_l,
                    "end_line": e_l,
                    "content": res.get("content", ""),
                    "symbol": "file_read"
                })
                if not any(s.get("file") == fp for s in sources):
                    sources.append({"file": fp, "start_line": s_l, "end_line": e_l})

            add_workflow_step(req_id, "read_file", "completed", f"Read {fp}:{s_l}-{e_l}")

        elif tool_name == "list_project_files":
            files = list_project_files(repository_id=repo_id)
            tool_calls.append({
                "tool": "list_project_files",
                "args": args,
                "summary": f"Enumerated {len(files)} files in repository",
                "files": files
            })
            for f in files[:8]:
                if not any(s.get("file") == f["path"] for s in sources):
                    sources.append({"file": f["path"], "start_line": 1, "end_line": f.get("lines", 1)})

            add_workflow_step(req_id, "list_project_files", "completed", f"Enumerated {len(files)} repository files")

        elif tool_name == "generate_unit_test":
            target_code = retrieved_context[0]["content"] if retrieved_context else args.get("code", "")
            test_spec = generate_unit_test(target_code, framework=args.get("framework", "pytest"))
            tool_calls.append({
                "tool": "generate_unit_test",
                "args": args,
                "summary": "Synthesized unit test specification"
            })
            add_workflow_step(req_id, "generate_unit_test", "completed", "Generated pytest scaffolding")

    # Bound retrieved context
    trimmed_context = retrieved_context[:settings.MAX_RETRIEVED_CHUNKS]

    return {
        "tool_calls": tool_calls,
        "retrieved_context": trimmed_context,
        "sources": sources,
        "tools_used": tools_used,
        "tools_to_run": []
    }


def should_continue(state: AgentState) -> str:
    """
    Conditional Edge: Checks if more iterations / tools are required or if we should synthesize the answer.
    """
    is_finished = state.get("is_finished", False)
    iteration = state.get("iteration", 0)
    max_iter = state.get("max_iterations", settings.MAX_AGENT_ITERATIONS)
    tools_to_run = state.get("tools_to_run", [])

    if is_finished or iteration >= max_iter or not tools_to_run:
        return "generate_response"
    return "execute_tools"


def generate_response_node(state: AgentState) -> Dict[str, Any]:
    """
    Node 4: Grounded Answer Synthesis.
    Generates response using LLM or smart grounded local engine, citing sources.
    """
    query = state.get("query", "")
    intent = state.get("intent", "GENERAL_QUERY")
    context_chunks = state.get("retrieved_context", [])
    tool_calls = state.get("tool_calls", [])
    repo_id = state.get("repository_id", "default_repo")
    req_id = state.get("request_id", "req_unknown")

    system_prompt = (
        "You are CodeMate, a senior AI codebase assistant. "
        "Your responses must be strictly grounded in the provided codebase context. "
        "Cite specific file paths and function names where relevant. "
        "Be concise, technical, and accurate."
    )

    response_text = generate_llm_response(
        system_prompt=system_prompt,
        user_prompt=query,
        context_chunks=context_chunks,
        intent=intent,
        tool_results=tool_calls,
        repository_id=repo_id
    )

    add_workflow_step(
        request_id=req_id,
        step_name="llm_synthesis",
        status="completed",
        detail="Synthesized grounded answer with source citations"
    )

    return {"response": response_text}
