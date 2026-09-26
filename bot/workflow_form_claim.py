"""One live-form send per Lark row, shared by Roy号 and 交付号.

Mark live reserves the row before the status flip. The speaker is assigned
next. Every sender calls begin_form_send immediately before the bubbles, so
a table scan cannot start a second copy while the first is still in the
10-second gap.
"""

from __future__ import annotations

import fcntl
import json
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parent.parent
SENDING_STALE_SECONDS = 180
HANDOFF_TIMEOUT_SECONDS = 45


def other_account(account: str) -> str:
    return "roy" if str(account or "").strip().lower() == "josh" else "josh"


def live_form_speaker(issuer: str, *, peer_in_group: bool) -> str:
    """Who posts the congrats and form bubbles.

    The issuer is already in the group (they received Mark live). When the
    other bot is there too, that other bot speaks. Otherwise the issuer does.
    """
    issuer = "josh" if str(issuer or "").strip().lower() == "josh" else "roy"
    if peer_in_group:
        return "roy" if issuer == "josh" else "josh"
    return issuer


def claim_path_for(config: Any) -> Path:
    override = str(getattr(config, "workflow_form_claim_state_file", "") or "").strip()
    if override:
        path = Path(override)
        return path if path.is_absolute() else ROOT / path
    shared = Path("/opt/botchain-shared/form_send_claim.json")
    if shared.parent.is_dir():
        return shared
    return ROOT / "data" / "form_send_claim.json"


@contextmanager
def _locked(path: Path) -> Iterator[dict[str, Any]]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        handle.seek(0)
        raw = handle.read()
        try:
            data = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            data = {}
        if not isinstance(data, dict):
            data = {}
        records = data.get("records")
        if not isinstance(records, dict):
            data["records"] = {}
        yield data
        handle.seek(0)
        handle.truncate()
        handle.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        handle.flush()


def _entry(data: dict[str, Any], record_id: str) -> dict[str, Any]:
    records = data.setdefault("records", {})
    entry = records.get(record_id)
    if not isinstance(entry, dict):
        entry = {}
        records[record_id] = entry
    return entry


def _fill(
    entry: dict[str, Any],
    *,
    chat_id: int | None,
    project_name: str,
    chat_title: str,
    requested_by: str,
) -> None:
    if chat_id is not None:
        entry["chat_id"] = int(chat_id)
    if project_name:
        entry["project_name"] = project_name
    if chat_title:
        entry["chat_title"] = chat_title
    if requested_by and not entry.get("requested_by"):
        entry["requested_by"] = requested_by


def _public(record_id: str, entry: dict[str, Any]) -> dict[str, Any]:
    try:
        chat_id = int(entry.get("chat_id") or 0)
    except (TypeError, ValueError):
        chat_id = 0
    try:
        updated = float(entry.get("updated_at") or 0)
    except (TypeError, ValueError):
        updated = 0.0
    return {
        "record_id": record_id,
        "status": str(entry.get("status") or ""),
        "owner": str(entry.get("owner") or ""),
        "requested_by": str(entry.get("requested_by") or ""),
        "chat_id": chat_id,
        "chat_title": str(entry.get("chat_title") or ""),
        "project_name": str(entry.get("project_name") or ""),
        "updated_at": updated,
    }


def reserve_form_send(
    path: Path,
    record_id: str,
    *,
    chat_id: int,
    project_name: str = "",
    chat_title: str = "",
    requested_by: str,
    now: float | None = None,
) -> None:
    """Block every sender until assign_form_sender. Leaves sent/sending/assigned alone."""
    rid = str(record_id or "").strip()
    if not rid:
        return
    now = time.time() if now is None else now
    with _locked(path) as data:
        entry = _entry(data, rid)
        status = str(entry.get("status") or "")
        if status in {"sent", "sending", "assigned"}:
            return
        entry["status"] = "reserved"
        entry["owner"] = ""
        entry["updated_at"] = now
        _fill(
            entry,
            chat_id=chat_id,
            project_name=project_name,
            chat_title=chat_title,
            requested_by=requested_by,
        )


def assign_form_sender(
    path: Path,
    record_id: str,
    sender: str,
    *,
    chat_id: int | None = None,
    project_name: str = "",
    chat_title: str = "",
    requested_by: str = "",
    now: float | None = None,
) -> str:
    """Name the bot that may post the bubbles. Returns the owner, or '' if already sent."""
    rid = str(record_id or "").strip()
    sender = "josh" if sender == "josh" else "roy"
    if not rid:
        return ""
    now = time.time() if now is None else now
    with _locked(path) as data:
        entry = _entry(data, rid)
        status = str(entry.get("status") or "")
        if status == "sent":
            return ""
        if status == "sending":
            return str(entry.get("owner") or "")
        entry["status"] = "assigned"
        entry["owner"] = sender
        entry["updated_at"] = now
        _fill(
            entry,
            chat_id=chat_id,
            project_name=project_name,
            chat_title=chat_title,
            requested_by=requested_by,
        )
        return sender


def begin_form_send(
    path: Path,
    record_id: str,
    owner: str,
    *,
    chat_id: int | None = None,
    project_name: str = "",
    chat_title: str = "",
    now: float | None = None,
) -> str:
    """Return 'send', 'done', or 'wait'.

    'send' means this caller owns the bubbles and must finish or release.
    """
    rid = str(record_id or "").strip()
    owner = "josh" if owner == "josh" else "roy"
    if not rid:
        return "wait"
    now = time.time() if now is None else now
    with _locked(path) as data:
        records = data.setdefault("records", {})
        current = records.get(rid)
        entry = current if isinstance(current, dict) else None
        if entry is None:
            entry = {
                "status": "sending",
                "owner": owner,
                "updated_at": now,
            }
            _fill(
                entry,
                chat_id=chat_id,
                project_name=project_name,
                chat_title=chat_title,
                requested_by=owner,
            )
            records[rid] = entry
            return "send"

        status = str(entry.get("status") or "")
        entry_owner = str(entry.get("owner") or "")
        try:
            updated = float(entry.get("updated_at") or 0)
        except (TypeError, ValueError):
            updated = 0.0
        age = now - updated if updated else 0.0

        if status == "sent":
            return "done"
        if status == "assigned" and entry_owner != owner:
            return "wait"
        if status == "reserved" and age < SENDING_STALE_SECONDS:
            return "wait"
        if status == "sending" and age < SENDING_STALE_SECONDS:
            return "wait"

        entry["status"] = "sending"
        entry["owner"] = owner
        entry["updated_at"] = now
        _fill(
            entry,
            chat_id=chat_id,
            project_name=project_name,
            chat_title=chat_title,
            requested_by="",
        )
        return "send"


def finish_form_send(path: Path, record_id: str, owner: str, *, now: float | None = None) -> None:
    rid = str(record_id or "").strip()
    owner = "josh" if owner == "josh" else "roy"
    if not rid:
        return
    now = time.time() if now is None else now
    with _locked(path) as data:
        entry = _entry(data, rid)
        if str(entry.get("status") or "") == "sent":
            return
        entry["status"] = "sent"
        if not entry.get("owner"):
            entry["owner"] = owner
        entry["updated_at"] = now


def release_form_send(path: Path, record_id: str, owner: str, *, now: float | None = None) -> None:
    """Give the slot back to the same owner so a failed send can be retried."""
    rid = str(record_id or "").strip()
    owner = "josh" if owner == "josh" else "roy"
    if not rid:
        return
    now = time.time() if now is None else now
    with _locked(path) as data:
        records = data.get("records") or {}
        entry = records.get(rid)
        if not isinstance(entry, dict):
            return
        if str(entry.get("status") or "") != "sending":
            return
        if str(entry.get("owner") or "") != owner:
            return
        entry["status"] = "assigned"
        entry["owner"] = owner
        entry["updated_at"] = now


def pending_form_sends(path: Path, owner: str) -> list[dict[str, Any]]:
    owner = "josh" if owner == "josh" else "roy"
    if not path.exists():
        return []
    with _locked(path) as data:
        out: list[dict[str, Any]] = []
        for rid, entry in (data.get("records") or {}).items():
            if not isinstance(entry, dict):
                continue
            if str(entry.get("status") or "") != "assigned":
                continue
            if str(entry.get("owner") or "") != owner:
                continue
            out.append(_public(str(rid), entry))
        return out


def reclaim_expired_form_sends(
    path: Path,
    requester: str,
    *,
    now: float | None = None,
    timeout: float = HANDOFF_TIMEOUT_SECONDS,
) -> list[dict[str, Any]]:
    """If the other bot never posted, hand the bubbles back to whoever Marked live."""
    requester = "josh" if requester == "josh" else "roy"
    if not path.exists():
        return []
    now = time.time() if now is None else now
    with _locked(path) as data:
        out: list[dict[str, Any]] = []
        for rid, entry in (data.get("records") or {}).items():
            if not isinstance(entry, dict):
                continue
            if str(entry.get("requested_by") or "") != requester:
                continue
            status = str(entry.get("status") or "")
            owner = str(entry.get("owner") or "")
            if status != "assigned" or owner == requester or not owner:
                continue
            try:
                updated = float(entry.get("updated_at") or 0)
            except (TypeError, ValueError):
                updated = 0.0
            if not updated or now - updated < timeout:
                continue
            entry["status"] = "assigned"
            entry["owner"] = requester
            entry["updated_at"] = now
            out.append(_public(str(rid), entry))
        return out
