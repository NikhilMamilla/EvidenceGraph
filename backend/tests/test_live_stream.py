"""
Phase 20 — Live event stream (SSE).

Regression cover for the buffer-growth bug: the in-memory buffer is bounded,
each DB row is streamed exactly once (its own high-water cursor), and the
heartbeat is throttled rather than emitted every poll.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):  # noqa: ANN001
    return "JSON"


from app.db.session import Base
from app.models.webhook_event import WebhookEvent
from app.api.v1 import live_stream as ls


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------
def test_recent_buffer_is_bounded():
    ls._recent_events.clear()
    for i in range(500):
        ls._recent_events.append({"n": i})
    assert len(ls._recent_events) == ls._MAX_RECENT == 50


def test_get_recent_events_is_newest_first_and_capped():
    ls._recent_events.clear()
    for i in range(120):
        ls._recent_events.append({"n": i})
    out = ls._get_recent_events()
    assert len(out) == 50
    assert out[0]["n"] == 119 and out[-1]["n"] == 70


def test_heartbeat_is_throttled():
    assert ls._HEARTBEAT_EVERY >= 2  # not once per poll


# ---------------------------------------------------------------------------
# Generator behaviour against a real (SQLite) session
# ---------------------------------------------------------------------------
class _Stop(Exception):
    pass


@pytest.fixture()
def sqlite_factory():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _mk_event(session_factory, eid: str, etype: str = "payment.captured") -> None:
    s = session_factory()
    try:
        s.add(
            WebhookEvent(
                razorpay_event_id=eid,
                event_type=etype,
                payment_id="pay_LS1",
                processing_status="PROCESSED",
                payload_hash=f"hash-{eid}",
                raw_payload={"id": eid},
                received_at=datetime.now(timezone.utc),
            )
        )
        s.commit()
    finally:
        s.close()


async def _drain(max_cycles: int) -> list[str]:
    """Run the generator for a bounded number of poll cycles."""
    calls = {"n": 0}

    async def fake_sleep(_seconds):
        calls["n"] += 1
        if calls["n"] >= max_cycles:
            raise _Stop

    orig = ls.asyncio.sleep
    ls.asyncio.sleep = fake_sleep
    chunks: list[str] = []
    try:
        async for chunk in ls._event_generator():
            chunks.append(chunk)
    except _Stop:
        pass
    finally:
        ls.asyncio.sleep = orig
    return chunks


def test_existing_rows_are_not_replayed(sqlite_factory, monkeypatch):
    """A row that already existed when the stream opened is not streamed."""
    monkeypatch.setattr(ls, "get_session_factory", lambda: sqlite_factory)
    ls._recent_events.clear()
    _mk_event(sqlite_factory, "evt_old")

    chunks = asyncio.run(_drain(max_cycles=4))
    body = "".join(chunks)
    assert "evt_old" not in body
    assert "webhook_event" not in body
    assert body.count("event: heartbeat") == 1  # cycle 0 only, of 4


def test_new_row_is_streamed_exactly_once(sqlite_factory, monkeypatch):
    monkeypatch.setattr(ls, "get_session_factory", lambda: sqlite_factory)
    ls._recent_events.clear()

    calls = {"n": 0}

    async def fake_sleep(_s):
        calls["n"] += 1
        if calls["n"] == 1:
            _mk_event(sqlite_factory, "evt_new")  # appears after the stream opened
        if calls["n"] >= 6:
            raise _Stop

    monkeypatch.setattr(ls.asyncio, "sleep", fake_sleep)

    chunks: list[str] = []
    try:
        asyncio.run(_collect(ls._event_generator(), chunks))
    except _Stop:
        pass

    body = "".join(chunks)
    assert body.count("event: webhook_event") == 1
    assert body.count("evt_new") == 1
    # and it landed in the bounded buffer once
    assert sum(1 for e in ls._recent_events if e.get("event_id")) == 1


async def _collect(agen, sink: list[str]) -> None:
    async for chunk in agen:
        sink.append(chunk)
