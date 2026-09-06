"""
Database models for CodeMate.
Tracks users, repositories, indexing jobs, and workflow events.
"""

from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, DateTime, Text, Float, Boolean, ForeignKey
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class UserModel(Base):
    __tablename__ = "users"

    id = Column(String(64), primary_key=True, index=True)
    username = Column(String(64), unique=True, index=True, nullable=False)
    hashed_password = Column(String(256), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    repositories = relationship("RepositoryModel", back_populates="owner", cascade="all, delete-orphan")


class RepositoryModel(Base):
    __tablename__ = "repositories"

    id = Column(String(64), primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    owner_id = Column(String(64), ForeignKey("users.id"), nullable=False, index=True)
    status = Column(String(32), default="indexing", index=True)  # indexing, ready, failed
    total_files = Column(Integer, default=0)
    processed_files = Column(Integer, default=0)
    files_discovered = Column(Integer, default=0)
    files_skipped = Column(Integer, default=0)
    skip_reasons = Column(Text, default="{}")  # JSON dict of category: count
    total_chunks = Column(Integer, default=0)
    indexing_progress = Column(Integer, default=0)  # 0 - 100
    languages_detected = Column(Text, default="[]")  # JSON list
    size_bytes = Column(Integer, default=0)
    root_path = Column(String(512), nullable=False)
    is_sample = Column(Boolean, default=False)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    owner = relationship("UserModel", back_populates="repositories")


class WorkflowEventModel(Base):
    __tablename__ = "workflow_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = Column(String(64), unique=True, index=True, nullable=False)
    repository_id = Column(String(64), nullable=False, index=True)
    user_id = Column(String(64), nullable=False)
    query = Column(Text, nullable=False)
    intent = Column(String(64), default="GENERAL_QUERY")
    confidence = Column(Float, default=1.0)
    duration_ms = Column(Integer, default=0)
    steps_json = Column(Text, default="[]")  # JSON list of execution steps
    tools_used = Column(Text, default="[]")  # JSON list of tools
    sources_json = Column(Text, default="[]")  # JSON list of sources
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
