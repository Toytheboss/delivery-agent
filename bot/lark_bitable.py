"""Lark Base (Bitable) API helpers."""

from __future__ import annotations

import logging
from typing import Any

import requests

LARK_API_BASE = "https://open.larksuite.com/open-apis"
logger = logging.getLogger(__name__)


class LarkBitableError(RuntimeError):
    pass


def get_tenant_access_token(app_id: str, app_secret: str) -> str:
    resp = requests.post(
        f"{LARK_API_BASE}/auth/v3/tenant_access_token/internal",
        json={"app_id": app_id, "app_secret": app_secret},
        timeout=30,
    )
    data = _parse(resp, "get tenant_access_token")
    return str(data["tenant_access_token"])


def _parse(resp: requests.Response, action: str) -> dict[str, Any]:
    try:
        data = resp.json()
    except ValueError as exc:
        raise LarkBitableError(f"{action}: invalid JSON (HTTP {resp.status_code})") from exc
    if data.get("code") != 0:
        raise LarkBitableError(f"{action} failed: {data}")
    return data


def list_records(
    token: str,
    app_token: str,
    table_id: str,
    *,
    page_size: int = 500,
) -> list[dict[str, Any]]:
    """Fetch all records (paginated)."""
    headers = {"Authorization": f"Bearer {token}"}
    items: list[dict[str, Any]] = []
    page_token = ""
    while True:
        params: dict[str, Any] = {"page_size": min(page_size, 500)}
        if page_token:
            params["page_token"] = page_token
        resp = requests.get(
            f"{LARK_API_BASE}/bitable/v1/apps/{app_token}/tables/{table_id}/records",
            headers=headers,
            params=params,
            timeout=60,
        )
        data = _parse(resp, "list records")["data"]
        items.extend(data.get("items") or [])
        if not data.get("has_more"):
            break
        page_token = data.get("page_token") or ""
        if not page_token:
            break
    return items


def update_record(
    token: str,
    app_token: str,
    table_id: str,
    record_id: str,
    fields: dict[str, Any],
) -> None:
    resp = requests.put(
        f"{LARK_API_BASE}/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={"fields": fields},
        timeout=30,
    )
    _parse(resp, "update record")


def create_record(
    token: str,
    app_token: str,
    table_id: str,
    fields: dict[str, Any],
) -> str:
    resp = requests.post(
        f"{LARK_API_BASE}/bitable/v1/apps/{app_token}/tables/{table_id}/records",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={"fields": fields},
        timeout=30,
    )
    data = _parse(resp, "create record")
    record = (data.get("data") or {}).get("record") or {}
    record_id = str(record.get("record_id") or "")
    if not record_id:
        raise LarkBitableError(f"create record: missing record_id in {data}")
    return record_id


def list_fields(token: str, app_token: str, table_id: str) -> list[dict[str, Any]]:
    headers = {"Authorization": f"Bearer {token}"}
    items: list[dict[str, Any]] = []
    page_token = ""
    while True:
        params: dict[str, Any] = {"page_size": 100}
        if page_token:
            params["page_token"] = page_token
        resp = requests.get(
            f"{LARK_API_BASE}/bitable/v1/apps/{app_token}/tables/{table_id}/fields",
            headers=headers,
            params=params,
            timeout=30,
        )
        data = _parse(resp, "list fields")["data"]
        items.extend(data.get("items") or [])
        if not data.get("has_more"):
            break
        page_token = data.get("page_token") or ""
        if not page_token:
            break
    return items


def create_field(
    token: str,
    app_token: str,
    table_id: str,
    field_name: str,
    *,
    field_type: int = 1,
) -> dict[str, Any]:
    """Create a field. Default type=1 (Text)."""
    resp = requests.post(
        f"{LARK_API_BASE}/bitable/v1/apps/{app_token}/tables/{table_id}/fields",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={"field_name": field_name, "type": field_type},
        timeout=30,
    )
    return _parse(resp, "create field")


def batch_create_records(
    token: str,
    app_token: str,
    table_id: str,
    records_fields: list[dict[str, Any]],
    *,
    batch_size: int = 500,
) -> int:
    """Create many records. Returns number created."""
    created = 0
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    for i in range(0, len(records_fields), batch_size):
        chunk = records_fields[i : i + batch_size]
        payload = {"records": [{"fields": fields} for fields in chunk]}
        resp = requests.post(
            f"{LARK_API_BASE}/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_create",
            headers=headers,
            json=payload,
            timeout=120,
        )
        _parse(resp, "batch create records")
        created += len(chunk)
    return created


def batch_delete_records(
    token: str,
    app_token: str,
    table_id: str,
    record_ids: list[str],
    *,
    batch_size: int = 500,
) -> int:
    deleted = 0
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    for i in range(0, len(record_ids), batch_size):
        chunk = record_ids[i : i + batch_size]
        resp = requests.post(
            f"{LARK_API_BASE}/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_delete",
            headers=headers,
            json={"records": chunk},
            timeout=120,
        )
        _parse(resp, "batch delete records")
        deleted += len(chunk)
    return deleted
