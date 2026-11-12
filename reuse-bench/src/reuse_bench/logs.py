"""Structured JSON-lines logging to stderr."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime


def log(event: str, **fields: object) -> None:
    record = {"ts": datetime.now(UTC).isoformat(timespec="seconds"), "event": event, **fields}
    print(json.dumps(record, default=str, ensure_ascii=False), file=sys.stderr, flush=True)
