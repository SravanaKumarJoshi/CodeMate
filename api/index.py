"""
Vercel Serverless Function Entrypoint for CodeMate.
Exposes the FastAPI application instance for Vercel's Python runtime.
"""

import sys
from pathlib import Path

# Ensure both api/ (where Vercel packages functions) and the project root are on sys.path
API_DIR = Path(__file__).resolve().parent
ROOT_DIR = API_DIR.parent

for p in (str(API_DIR), str(ROOT_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

# Import the existing FastAPI application instance
try:
    from app.main import app
except Exception as e:
    import traceback
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse

    app = FastAPI(title="CodeMate Diagnostic")
    _err = traceback.format_exc()
    _sys_path = list(sys.path)
    _files = [str(p) for p in Path("/var/task").rglob("*")][:100] if Path("/var/task").exists() else []

    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
    async def catch_all(path: str):
        return JSONResponse(
            status_code=500,
            content={
                "error": "Failed to import app.main in production",
                "traceback": _err,
                "sys_path": _sys_path,
                "files_in_var_task": _files
            }
        )
