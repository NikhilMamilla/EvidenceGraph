"""
Internal CLI script to replay a Razorpay webhook event.

Usage:
    poetry run python scripts/replay_event.py <razorpay_event_id>
"""

import argparse
import sys
import os

# Add the backend root directory to the python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import select

from app.db.session import get_session_factory
from app.models.webhook_event import WebhookEvent
from app.schemas.webhook import ProcessingStatus
from app.services.redis_client import get_redis_client
from app.services.webhook_service import REDIS_WEBHOOK_QUEUE

def replay_event(razorpay_event_id: str):
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        # Find the event
        event = db.execute(
            select(WebhookEvent).where(WebhookEvent.razorpay_event_id == razorpay_event_id)
        ).scalar_one_or_none()
        
        if not event:
            print(f"Error: WebhookEvent with razorpay_event_id '{razorpay_event_id}' not found.")
            sys.exit(1)
            
        print(f"Found event (Internal ID: {event.id}, Status: {event.processing_status})")
        
        # Reset the status
        event.processing_status = ProcessingStatus.RECEIVED
        db.commit()
        
        # Push back into Redis queue
        redis = get_redis_client()
        redis.lpush(REDIS_WEBHOOK_QUEUE, str(event.id))
        
        print(f"Successfully queued event {event.id} for replay.")
        
    finally:
        db.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Replay a Razorpay Webhook Event")
    parser.add_argument("event_id", type=str, help="The razorpay_event_id (e.g. ev_...)")
    
    args = parser.parse_args()
    replay_event(args.event_id)
