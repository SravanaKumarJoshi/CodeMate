"""
Vercel Serverless Function Entrypoint for CodeMate.
Exposes the existing FastAPI application instance for Vercel's Python runtime.
"""

import sys
from pathlib import Path

# Add project root to sys.path to ensure 'app' and related packages can be imported
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Import the existing FastAPI application instance
from app.main import app
