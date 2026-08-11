"""Append-only per-message detail log (JSONL, one file per Asia/Shanghai day).

Designed to be cheap and non-blocking for the reply hot path:
- append a single line under a short lock
- truncate text
- never raise to callers
- optional retention purge of old day files
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    from zoneinfo import ZoneInfo
except ImportError:  # Python < 3.9
    from backports.zoneinfo import ZoneInfo  # type: ignore

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent

try:
    TZ = ZoneInfo("Asia/Shanghai")
except Exception:  # noqa: BLE001
    TZ = timezone(timedelta(hours=8))

_lock = threading.Lock()
_enabled = True
_log_dir = ROOT / "data" / "message_logs"
_retain_days = 90
_text_max = 500
_last_purge_day = ""
_title_cache: dict[int, str] = {}
_title_cache_loaded = False


def configure(
    *,
    enabled: bool = True,
    log_dir: str | Path | None = None,
    retain_days: int = 90,
    text_max: int = 500,
) -> None:
    global _enabled, _log_dir, _retain_days, _text_max
    _enabled = bool(enabled)
    if log_dir is not None:
        _log_dir = Path(log_dir)
        if not _log_dir.is_absolute():
            _log_dir = ROOT / _log_dir
    _retain_days = max(int(retain_days or 90), 1)
    _text_max = max(int(text_max or 500), 80)


def _load_title_cache() -> None:
    global _title_cache_loaded, _title_cache
    if _title_cache_loaded:
        return
    path = ROOT / "data" / "folder_title_cache.json"
    cache: dict[int, str] = {}
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            titles = raw.get("titles") if isinstance(raw, dict) else {}
            if isinstance(titles, dict):
                for k, v in titles.items():
                    try:
                        cid = int(k)
                    except (TypeError, ValueError):
                        continue
                    if isinstance(v, dict):
                        t = str(v.get("title") or "").strip()
                    else:
                        t = str(v or "").strip()
                    if t:
                        cache[cid] = t
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            cache = {}
    _title_cache = cache
    _title_cache_loaded = True


def cached_chat_title(chat_id: int | None) -> str:
    if chat_id is None:
        return ""
    try:
        _load_title_cache()
        return _title_cache.get(int(chat_id), "")
    except Exception:  # noqa: BLE001
        return ""


def _today() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d")


def _now_iso() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def _path_for_day(day: str) -> Path:
    return _log_dir / f"messages-{day}.jsonl"


def _maybe_purge_unlocked() -> None:
    """Delete day files older than retain_days. At most once per calendar day."""
    global _last_purge_day
    day = _today()
    if _last_purge_day == day:
        return
    _last_purge_day = day
    if not _log_dir.exists():
        return
    cutoff = datetime.now(TZ).date() - timedelta(days=_retain_days)
    for path in _log_dir.glob("messages-*.jsonl"):
        stem = path.stem  # messages-YYYY-MM-DD
        try:
            ds = stem.split("messages-", 1)[1]
            file_day = datetime.strptime(ds, "%Y-%m-%d").date()
        except (IndexError, ValueError):
            continue
        if file_day < cutoff:
            try:
                path.unlink()
                logger.info("message_log purged %s", path.name)
            except OSError:
                logger.exception("message_log purge failed for %s", path)


def _clip(text: str, limit: int) -> str:
    body = (text or "").replace("\n", " ").strip()
    if len(body) > limit:
        return body[: limit - 1] + "…"
    return body


def log_message_event(
    *,
    kind: str,
    chat_id: int | None,
    chat_title: str = "",
    sender_id: int | None = None,
    sender_username: str = "",
    message_id: int | None = None,
    text: str = "",
    reply_text: str = "",
    qa: bool = False,
    qa_group: bool = False,
    outcome: str = "",
    reason: str = "",
    score: float | None = None,
    bubbles: int | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Append one event. Safe to call from any thread; never raises."""
    if not _enabled:
        return
    try:
        row: dict[str, Any] = {
            "ts": _now_iso(),
            "kind": kind,
            "chat_id": chat_id,
            "chat_title": (chat_title or cached_chat_title(chat_id) or "")[:120],
            "sender_id": sender_id,
            "sender_username": (sender_username or "")[:64],
            "message_id": message_id,
            "text": _clip(text, _text_max),
            "reply_text": _clip(reply_text, max(_text_max * 2, 1000)),
            "qa": bool(qa),
            "qa_group": bool(qa_group),
            "outcome": outcome or "",
            "reason": (reason or "")[:200],
        }
        if score is not None:
            try:
                row["score"] = round(float(score), 3)
            except (TypeError, ValueError):
                pass
        if bubbles is not None:
            row["bubbles"] = int(bubbles)
        if extra:
            row["extra"] = extra
        line = json.dumps(row, ensure_ascii=False) + "\n"
        with _lock:
            _log_dir.mkdir(parents=True, exist_ok=True)
            _maybe_purge_unlocked()
            path = _path_for_day(_today())
            with path.open("a", encoding="utf-8") as f:
                f.write(line)
    except Exception:  # noqa: BLE001
        logger.exception("message_log append failed")
