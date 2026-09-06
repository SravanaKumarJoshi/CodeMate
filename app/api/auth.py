"""
Authentication API for CodeMate.
Handles user registration, login, JWT issuance, and profile resolution.
"""

import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.services.database import get_db
from app.models.db_models import UserModel
from app.security.auth import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6, max_length=100)


class LoginRequest(BaseModel):
    username: str = Field(...)
    password: str = Field(...)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    username: str


@router.post("/register", response_model=TokenResponse)
def register(request: RegisterRequest, db: Session = Depends(get_db)):
    """Registers a new user."""
    existing = db.query(UserModel).filter(UserModel.username == request.username).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username is already registered."
        )

    user_id = f"usr_{uuid.uuid4().hex[:10]}"
    user = UserModel(
        id=user_id,
        username=request.username,
        hashed_password=hash_password(request.password)
    )
    db.add(user)
    db.commit()

    token = create_access_token(data={"sub": user_id, "username": user.username})
    return TokenResponse(
        access_token=token,
        user_id=user_id,
        username=user.username
    )


@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)):
    """Authenticates user credentials and returns a signed JWT."""
    user = db.query(UserModel).filter(UserModel.username == request.username).first()
    if not user or not verify_password(request.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    token = create_access_token(data={"sub": user.id, "username": user.username})
    return TokenResponse(
        access_token=token,
        user_id=user.id,
        username=user.username
    )


@router.get("/me")
def get_profile(current_user: dict = Depends(get_current_user)):
    """Returns profile information for the authenticated user."""
    return current_user
