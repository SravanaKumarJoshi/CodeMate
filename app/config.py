import os
import secrets
from pathlib import Path
from typing import List, Set, Union
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "CodeMate"
    VERSION: str = "2.0.0"
    DEBUG: bool = False
    APP_ENV: str = "development"

    # Base Directories
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    DATA_DIR: Path = BASE_DIR / "data"
    STORAGE_DIR: Path = BASE_DIR / "storage" / "repositories"
    UPLOAD_DIR: Path = STORAGE_DIR
    CHROMA_DIR: Path = DATA_DIR / "chromadb"
    SAMPLE_PROJECT_DIR: Path = BASE_DIR / "sample_project"
    ML_MODEL_PATH: Path = BASE_DIR / "ml" / "model" / "classifier.joblib"
    ML_METADATA_PATH: Path = BASE_DIR / "ml" / "model" / "metadata.json"

    # Database
    DATABASE_URL: str = f"sqlite:///{Path(__file__).resolve().parent.parent / 'data' / 'codemate.db'}"

    # Authentication & Security
    # Loaded from .env or environment; if unset, dynamically generates a secure 256-bit random key at startup
    JWT_SECRET_KEY: str = Field(default_factory=lambda: secrets.token_hex(32))
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 1440
    ALLOWED_ORIGINS: Union[List[str], str] = ["http://localhost:8000", "http://127.0.0.1:8000", "http://localhost:3000"]

    # LLM & Embedding Settings
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    MODEL_NAME: str = "gpt-4o-mini"
    TEMPERATURE: float = 0.2
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_BATCH_SIZE: int = 64

    # ChromaDB RAG Settings
    CHROMA_COLLECTION_NAME: str = "codemate_chunks"
    TOP_K_RESULTS: int = 5
    CHUNK_SIZE: int = 400
    CHUNK_OVERLAP: int = 60

    # Agent Constraints (Guardrails)
    MAX_AGENT_ITERATIONS: int = 4
    MAX_TOOL_CALLS: int = 6
    MAX_RETRIEVED_CHUNKS: int = 8
    MAX_CONTEXT_TOKENS: int = 4000

    # Archive & Large Ingestion Constraints
    MAX_UPLOAD_SIZE_MB: int = 2048               # 2 GB archive upload ceiling
    UPLOAD_CHUNK_SIZE_KB: int = 64              # 64 KB streaming buffer
    MAX_EXTRACTED_SIZE_MB: int = 5120           # 5 GB total decompressed limit
    MAX_ARCHIVE_FILES: int = 100000             # Max files inside archive
    MAX_FILE_SIZE_MB: int = 50                  # 50 MB per single text file
    MAX_DECOMPRESSION_RATIO: float = 100.0      # Archive bomb defense

    # Allowed Source and Documentation Extensions
    ALLOWED_EXTENSIONS: Set[str] = {
        ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".cpp", ".c", ".h", ".hpp",
        ".go", ".rs", ".php", ".rb", ".sql", ".html", ".css", ".json", ".yaml",
        ".yml", ".toml", ".xml", ".md", ".txt", ".env.example", ".sh", ".bat",
        ".ini", ".cfg", ".proto"
    }

    # Binary and Media Extensions to Exclude
    IGNORED_EXTENSIONS: Set[str] = {
        ".pack", ".idx", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico",
        ".mp3", ".mp4", ".mov", ".avi", ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar",
        ".exe", ".dll", ".so", ".dylib", ".bin", ".o", ".a", ".class", ".jar", ".war",
        ".pyc", ".pyd", ".woff", ".woff2", ".ttf", ".eot", ".pdf", ".db", ".sqlite", ".sqlite3"
    }

    # Directories to Ignore
    IGNORED_DIRECTORIES: Set[str] = {
        ".git", ".svn", ".hg", "__pycache__", ".venv", ".venv_test", "venv", "env", "node_modules",
        "site-packages", ".tox", ".pytest_cache", ".ruff_cache", ".mypy_cache", ".idea", ".vscode",
        "dist", "build", "target", "coverage", ".cache", ".chromadb",
        ".system_generated", "bin", "obj"
    }

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_allowed_origins(cls, v):
        if isinstance(v, str):
            if v.strip().startswith("["):
                import json
                try:
                    return json.loads(v)
                except Exception:
                    pass
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parent.parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def max_upload_bytes(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    @property
    def max_file_bytes(self) -> int:
        return self.MAX_FILE_SIZE_MB * 1024 * 1024

    @property
    def max_extracted_bytes(self) -> int:
        return self.MAX_EXTRACTED_SIZE_MB * 1024 * 1024


settings = Settings()

# Ensure critical directories exist
settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
settings.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
settings.CHROMA_DIR.mkdir(parents=True, exist_ok=True)
