"""Append-only workflow automation event log shared by the dashboard."""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    from backports.zoneinfo import ZoneInfo  # type: ignore

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent
EVENTS_FILE = ROOT / "data" / "workflow_events.jsonl"
_lock = threading.Lock()

try:
    TZ = ZoneInfo("Asia/Shanghai")
except Exception:  # noqa: BLE001
    TZ = timezone(timedelta(hours=8))


def append_event(
    kind: str,
    source: str,
    *,
    project_name: str = "",
    text: str = "",
    status: str = "success",
    event_ts: str | None = None,
    **extra: Any,
) -> None:
    """Persist one automation action without ever breaking the caller."""
    now = datetime.now(TZ)
    ts = event_ts or now.isoformat(timespec="seconds")
    row: dict[str, Any] = {
        "ts": ts,
        "day": now.strftime("%Y-%m-%d"),
        "kind": str(kind or "automation"),
        "source": str(source or "automation"),
        "project_name": str(project_name or ""),
        "text": str(text or ""),
        "status": str(status or "success"),
    }
    row.update({k: v for k, v in extra.items() if v is not None})
    try:
        EVENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(row, ensure_ascii=False) + "\n"
        with _lock:
            with EVENTS_FILE.open("a", encoding="utf-8") as fh:
                fh.write(line)
    except OSError:
        logger.exception("workflow events: failed appending %s", kind)
