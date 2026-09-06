"""
Database connection and session factory for CodeMate.
Uses SQLite for robust, self-contained, zero-configuration local persistence.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.config import settings
from app.models.db_models import Base, UserModel
from app.security.auth import hash_password

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Creates database tables and ensures the default demo user exists."""
    Base.metadata.create_all(bind=engine)
    
    # Lightweight schema migration for existing SQLite database
    with engine.connect() as conn:
        for col_name, col_type in [
            ("files_discovered", "INTEGER DEFAULT 0"),
            ("files_skipped", "INTEGER DEFAULT 0"),
            ("skip_reasons", "TEXT DEFAULT '{}'"),
        ]:
            try:
                from sqlalchemy import text
                conn.execute(text(f"ALTER TABLE repositories ADD COLUMN {col_name} {col_type}"))
                conn.commit()
            except Exception:
                pass

    # Ensure default demo user exists
    with SessionLocal() as db:
        demo_user = db.query(UserModel).filter(UserModel.id == "usr_demo").first()
        if not demo_user:
            demo_user = UserModel(
                id="usr_demo",
                username="developer",
                hashed_password=hash_password("developer123")
            )
            db.add(demo_user)
            db.commit()


def get_db():
    """FastAPI dependency for database session."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
