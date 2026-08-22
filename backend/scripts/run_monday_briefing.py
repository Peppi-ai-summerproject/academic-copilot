"""Confirmation-gated manual trigger for the production Monday workflow."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import sys


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.api.routes.telegram import (
    initialize_telegram_application,
    shutdown_telegram_application,
)
from app.workflows.monday import run_manual_monday_workflow


async def _run() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm-send",
        action="store_true",
        help="Acknowledge that the production workflow may send real Telegram messages.",
    )
    args = parser.parse_args()
    if not args.confirm_send:
        parser.error("--confirm-send is required")

    await initialize_telegram_application()
    try:
        result = await asyncio.to_thread(run_manual_monday_workflow)
    finally:
        await shutdown_telegram_application()

    print(
        f"status={result.status} execution_key={result.execution_key} "
        f"briefings={len(result.briefings)}"
    )
    return 0 if result.status in {"completed", "partial"} else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_run()))
