from datetime import datetime
from pydantic import BaseModel

class OrderSchema(BaseModel):
    razorpay_order_id: str
    amount_minor: int | None
    currency: str | None
    status: str
    
    class Config:
        from_attributes = True
