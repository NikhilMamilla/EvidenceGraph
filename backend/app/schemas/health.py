"""
Pydantic response schemas for health endpoints.
"""

from __future__ import annotations

from pydantic import BaseModel


class LivenessResponse(BaseModel):
    status: str
    service: str


class ReadinessResponse(BaseModel):
    status: str
    database: str
    redis: str
