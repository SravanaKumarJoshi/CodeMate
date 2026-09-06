"""
ShopFlow E-Commerce API Main Application.
Initializes SQLite tables, configures routers, and handles root endpoints.
"""

from fastapi import FastAPI
from sample_project.config import settings
from sample_project.database import engine, Base
from sample_project.api.users import router as users_router
from sample_project.api.orders import router as orders_router

# Initialize database schema tables on startup
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Sample e-commerce backend demonstration service using FastAPI and SQLite."
)

app.include_router(users_router, prefix=settings.API_PREFIX)
app.include_router(orders_router, prefix=settings.API_PREFIX)


@app.get("/")
def root():
    return {
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "docs": "/docs",
        "status": "online"
    }
