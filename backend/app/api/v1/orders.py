from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.order import Order
from app.schemas.order import OrderSchema

router = APIRouter()

@router.get("/{razorpay_order_id}", response_model=OrderSchema)
def get_order(razorpay_order_id: str, db: Session = Depends(get_db)):
    order = db.execute(
        select(Order).where(Order.razorpay_order_id == razorpay_order_id)
    ).scalar_one_or_none()
    
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )
    return order
