"""
Orders API endpoints for creating and viewing customer orders.
Requires user authentication.
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from sample_project.database import get_db
from sample_project.models import Order, User
from sample_project.auth import get_current_user

router = APIRouter(prefix="/orders", tags=["Orders"])


class OrderCreateRequest(BaseModel):
    item_name: str = Field(..., min_length=1, max_length=100)
    quantity: int = Field(1, gt=0)
    total_price: float = Field(..., gt=0.0)


class OrderResponse(BaseModel):
    id: int
    user_id: int
    item_name: str
    quantity: int
    total_price: float
    status: str

    class Config:
        from_attributes = True


@router.post("/", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
def create_order(
    req: OrderCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new order belonging to the currently logged in user."""
    order = Order(
        user_id=current_user.id,
        item_name=req.item_name,
        quantity=req.quantity,
        total_price=req.total_price,
        status="CONFIRMED"
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


@router.get("/", response_model=List[OrderResponse])
def list_orders(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retrieve all orders placed by the currently logged in user."""
    return db.query(Order).filter(Order.user_id == current_user.id).all()
