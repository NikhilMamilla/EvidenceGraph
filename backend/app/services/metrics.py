"""
Simple in-process ingestion metrics.

Incremented atomically using a thread-safe counter dict.
No external metrics platform required for Phase 2.
In production this would be replaced by Prometheus/StatsD.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class IngestionMetrics:
    webhooks_received_total: int = 0
    webhooks_verified_total: int = 0
    webhooks_rejected_total: int = 0
    webhooks_duplicate_total: int = 0
    webhooks_processed_total: int = 0
    webhooks_failed_total: int = 0
    last_verified_event_at: Optional[datetime] = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def inc_received(self) -> None:
        with self._lock:
            self.webhooks_received_total += 1

    def inc_verified(self) -> None:
        with self._lock:
            self.webhooks_verified_total += 1
            self.last_verified_event_at = datetime.now(tz=timezone.utc)

    def inc_rejected(self) -> None:
        with self._lock:
            self.webhooks_rejected_total += 1

    def inc_duplicate(self) -> None:
        with self._lock:
            self.webhooks_duplicate_total += 1

    def inc_processed(self) -> None:
        with self._lock:
            self.webhooks_processed_total += 1

    def inc_failed(self) -> None:
        with self._lock:
            self.webhooks_failed_total += 1


# Module-level singleton
_metrics = IngestionMetrics()


def get_metrics() -> IngestionMetrics:
    return _metrics
