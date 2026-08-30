from datetime import datetime
from typing import Any
from pydantic import BaseModel

class PaymentEventSchema(BaseModel):
    event_type: str
    event_timestamp: datetime | None

    class Config:
        from_attributes = True

class PaymentSchema(BaseModel):
    razorpay_payment_id: str
    amount_minor: int | None
    currency: str | None
    status: str
    payment_method_type: str | None
    payment_method_details: dict[str, Any] | None
    captured: bool
    first_observed_at: datetime
    last_observed_at: datetime
    
    class Config:
        from_attributes = True

class PaymentWithEventsSchema(PaymentSchema):
    events: list[PaymentEventSchema] = []
