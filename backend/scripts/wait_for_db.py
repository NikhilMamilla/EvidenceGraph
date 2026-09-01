"""
Block until the configured database answers a trivial query, or give up with a
clear diagnosis. Run by entrypoint.sh before migrations so a cold / slow / wrongly
configured database produces an actionable message instead of a raw traceback.
"""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text  # noqa: E402

from app.db.session import get_engine  # noqa: E402

DEADLINE_SECONDS = int(os.getenv("DB_WAIT_SECONDS", "150"))
RETRY_SECONDS = 5


def main() -> int:
    started = time.time()
    attempt = 0
    last_err = "unknown"

    while True:
        attempt += 1
        try:
            with get_engine().connect() as conn:
                conn.execute(text("SELECT 1"))
            print(f"[wait_for_db] connected on attempt {attempt} "
                  f"({time.time() - started:.0f}s)", flush=True)
            return 0
        except Exception as exc:  # noqa: BLE001 — we want the message, not the trace
            last_err = f"{type(exc).__name__}: {str(exc).splitlines()[0][:200]}"
            elapsed = time.time() - started
            if elapsed > DEADLINE_SECONDS:
                break
            print(f"[wait_for_db] not ready (attempt {attempt}, {elapsed:.0f}s): "
                  f"{last_err} — retrying in {RETRY_SECONDS}s", flush=True)
            time.sleep(RETRY_SECONDS)

    print("", flush=True)
    print(f"[wait_for_db] GAVE UP after {attempt} attempts / {DEADLINE_SECONDS}s.", flush=True)
    print(f"[wait_for_db] last error: {last_err}", flush=True)
    print("[wait_for_db] checklist:", flush=True)
    print("  1. .env DATABASE_URL is the Supabase *Session Pooler* URI "
          "(host ...pooler.supabase.com, port 5432, ?sslmode=require),", flush=True)
    print("     and @ # % in the password are URL-encoded as %40 %23 %25.", flush=True)
    print("  2. The Supabase project is not paused "
          "(dashboard -> project -> Restore).", flush=True)
    print("  3. 'SSL SYSCALL error: EOF detected' on Docker Desktop / WSL2 is an MTU "
          "problem. The compose network is pinned to MTU 1400; if it persists, lower", flush=True)
    print("     com.docker.network.driver.mtu to 1350 or 1280 in docker-compose.yml, "
          "then 'docker compose down && docker compose up --build'. See docs/RUN.md.", flush=True)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
