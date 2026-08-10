#!/usr/bin/env python3
"""Fetch plain text from a Lark Wiki document via Open Platform API."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

LARK_API_BASE = "https://open.larksuite.com/open-apis"


def get_tenant_access_token(app_id: str, app_secret: str) -> str:
    resp = requests.post(
        f"{LARK_API_BASE}/auth/v3/tenant_access_token/internal",
        json={"app_id": app_id, "app_secret": app_secret},
        timeout=30,
    )
    data = _parse_lark_response(resp, "get tenant_access_token")
    return data["tenant_access_token"]


def _parse_lark_response(resp: requests.Response, action: str) -> dict:
    try:
        data = resp.json()
    except ValueError as exc:
        raise RuntimeError(f"{action}: invalid JSON response (HTTP {resp.status_code})") from exc
    if data.get("code") != 0:
        raise RuntimeError(f"{action} failed (HTTP {resp.status_code}): {data}")
    return data


def get_wiki_node(token: str, wiki_token: str) -> dict:
    resp = requests.get(
        f"{LARK_API_BASE}/wiki/v2/spaces/get_node",
        headers={"Authorization": f"Bearer {token}"},
        params={"token": wiki_token},
        timeout=30,
    )
    data = _parse_lark_response(resp, "get wiki node")
    return data["data"]["node"]


def get_doc_raw_content(token: str, document_id: str) -> str:
    resp = requests.get(
        f"{LARK_API_BASE}/docx/v1/documents/{document_id}/raw_content",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    data = _parse_lark_response(resp, "get document content")
    return data["data"]["content"]


def fetch_wiki_text(app_id: str, app_secret: str, wiki_token: str) -> str:
    access_token = get_tenant_access_token(app_id, app_secret)
    node = get_wiki_node(access_token, wiki_token)

    obj_type = node.get("obj_type")
    obj_token = node.get("obj_token")
    if obj_type != "docx":
        raise RuntimeError(
            f"Unsupported document type '{obj_type}'. "
            "This script currently supports docx wiki pages only."
        )

    return get_doc_raw_content(access_token, obj_token)


def main() -> int:
    load_dotenv()

    app_id = os.getenv("LARK_APP_ID", "").strip()
    app_secret = os.getenv("LARK_APP_SECRET", "").strip()
    wiki_token = os.getenv("LARK_WIKI_TOKEN", "").strip()

    if not app_id or not app_secret:
        print("Missing LARK_APP_ID or LARK_APP_SECRET in .env", file=sys.stderr)
        return 1
    if not wiki_token:
        print("Missing LARK_WIKI_TOKEN in .env", file=sys.stderr)
        return 1

    try:
        content = fetch_wiki_text(app_id, app_secret, wiki_token)
    except requests.RequestException as exc:
        print(f"Network error: {exc}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / f"{wiki_token}.txt"
    output_file.write_text(content, encoding="utf-8")

    print(f"Saved to {output_file}")
    print("-" * 40)
    print(content[:2000] + ("..." if len(content) > 2000 else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
