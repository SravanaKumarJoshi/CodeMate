"""
CodeMate Application Entrypoint.
Initializes database, mounts API routers, configures CORS,
serves the interactive developer UI, and manages startup indexing.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import settings
from app.services.database import init_db, SessionLocal
from app.services.repo_service import create_repository, get_repository, set_active_repository_id
from app.rag.retriever import get_collection
from app.rag.ingestion import index_codebase_incrementally

# Import Routers
from app.api.health import router as health_router
from app.api.auth import router as auth_router
from app.api.repositories import router as repositories_router
from app.api.indexing import router as indexing_router
from app.api.files import router as files_router
from app.api.chat import router as chat_router
from app.api.workflow import router as workflow_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("codemate")

FRONTEND_DIR = settings.BASE_DIR / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Warm startup: Initializes database tables and auto-indexes sample project."""
    logger.info("Initializing CodeMate v%s...", settings.VERSION)
    try:
        init_db()
        sample_repo_id = "repo_sample_project"

        # Register sample repository in database if not present
        with SessionLocal() as db:
            existing = get_repository(db, sample_repo_id)
            if not existing and settings.SAMPLE_PROJECT_DIR.exists():
                create_repository(
                    db=db,
                    repo_id=sample_repo_id,
                    name="Sample E-Commerce Store",
                    owner_id="usr_demo",
                    root_path=str(settings.SAMPLE_PROJECT_DIR),
                    is_sample=True
                )
                logger.info("Registered sample project repository metadata.")

        coll = get_collection()
        if coll.count() == 0 and settings.SAMPLE_PROJECT_DIR.exists():
            logger.info("ChromaDB is empty; auto-indexing sample project...")
            index_codebase_incrementally(
                source_dir=settings.SAMPLE_PROJECT_DIR,
                repository_id=sample_repo_id,
                repository_name="Sample E-Commerce Store"
            )
            logger.info("Sample project auto-indexing completed.")
        else:
            set_active_repository_id(sample_repo_id)
            logger.info("ChromaDB active with %d indexed chunks.", coll.count())
    except Exception as err:
        logger.warning("Startup initialization non-critical warning: %s", err, exc_info=True)

    yield
    logger.info("CodeMate backend shutting down.")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    description="Large Repository AI Codebase Assistant with RAG, LangGraph Agent, and Interactive Workflow.",
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS if settings.APP_ENV == "production" else ["*"],
    allow_origin_regex=r"^https:\/\/.*\.vercel\.app$" if settings.APP_ENV == "production" else None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API Routers under /api
app.include_router(health_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(repositories_router, prefix="/api")
app.include_router(indexing_router, prefix="/api")
app.include_router(files_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(workflow_router, prefix="/api")

# Mount frontend static directory if exists
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/")
    @app.get("/workflow")
    def serve_frontend():
        index_file = FRONTEND_DIR / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
        return {"service": settings.APP_NAME, "status": "frontend index.html not found"}

    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR)), name="frontend")
else:
    @app.get("/")
    def serve_api_root():
        return {
            "service": settings.APP_NAME,
            "version": settings.VERSION,
            "docs": "/docs",
            "status": "ready"
        }
