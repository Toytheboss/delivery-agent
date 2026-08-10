#!/usr/bin/env python3
"""Backfill 「项目方钱包地址搜集」 from another Lark source table (查漏补缺).

Source (default): QxM0b4lxBa4fCZsXoShlXYEHgwd / tblmWiaUC237PJFd (view vewHRLN0Jb)
Dest: workflow base Kb6rbLenJa4FzWsi6pzlTkdjg0e / wallet tblj0FdKPrlc7PrM

Dedupe key: normalized Project name (case-insensitive, collapsed whitespace).

Sync (fill-empty only; never overwrite non-empty dest with different values):
  - Mainnet Contract Address → Contract Addresss/主网合约
  - Project logo (Attachment) → Project logo (Text URL) + Project log (Attachment)

Creates missing projects when source has name + (contract and/or logo).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from bot.lark_bitable import (  # noqa: E402
    LARK_API_BASE,
    create_record,
    get_tenant_access_token,
    list_fields,
    list_records,
    update_record,
)
from bot.project_logo import upload_bitable_image  # noqa: E402
import requests  # noqa: E402

SRC_APP_DEFAULT = "QxM0b4lxBa4fCZsXoShlXYEHgwd"
SRC_TBL_DEFAULT = "tblmWiaUC237PJFd"
SRC_VIEW_DEFAULT = "vewHRLN0Jb"
DST_APP_DEFAULT = "Kb6rbLenJa4FzWsi6pzlTkdjg0e"
DST_TBL_DEFAULT = "tblj0FdKPrlc7PrM"

SRC_NAME = "Project Name"
SRC_LOGO = "Project logo"
SRC_CONTRACT = "Mainnet Contract Address"

DST_NAME = "Project name"
DST_LOGO_TEXT = "Project logo"  # Text
DST_LOGO_ATT = "Project log"  # Attachment (field name typo in dest)
DST_CONTRACT = "Contract Addresss/主网合约"

# Source has no separate treasury/fee fields — only contract maps.
ADDRESS_MAP = [
    (SRC_CONTRACT, DST_CONTRACT),
]

TYPE_MAP = {
    1: "Text",
    2: "Number",
    3: "SingleSelect",
    4: "MultiSelect",
    5: "DateTime",
    7: "Checkbox",
    11: "User",
    13: "Phone",
    15: "Url",
    17: "Attachment",
    18: "SingleLink",
    19: "Lookup",
    20: "Formula",
    1005: "AutoNumber",
}


def textify(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, list):
        parts = []
        for x in v:
            if isinstance(x, dict):
                if "text" in x:
                    parts.append(str(x.get("text") or ""))
                elif "name" in x:
                    parts.append(str(x.get("name") or ""))
            else:
                parts.append(str(x))
        return "\n".join(p for p in parts if p).strip()
    if isinstance(v, dict):
        if "text" in v:
            return str(v.get("text") or "").strip()
        if "link" in v:
            return str(v.get("link") or "").strip()
        return json.dumps(v, ensure_ascii=False)
    return str(v).strip()


def norm_name(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip()).lower()


def is_empty(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, list):
        return len(v) == 0
    return not textify(v)


def list_with_view(
    token: str, app: str, tbl: str, view_id: str | None = None
) -> list[dict]:
    headers = {"Authorization": f"Bearer {token}"}
    items: list[dict] = []
    page_token = ""
    while True:
        params: dict = {"page_size": 500}
        if view_id:
            params["view_id"] = view_id
        if page_token:
            params["page_token"] = page_token
        resp = requests.get(
            f"{LARK_API_BASE}/bitable/v1/apps/{app}/tables/{tbl}/records",
            headers=headers,
            params=params,
            timeout=60,
        )
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"list records failed: {data}")
        d = data["data"]
        items.extend(d.get("items") or [])
        if not d.get("has_more"):
            break
        page_token = d.get("page_token") or ""
        if not page_token:
            break
    return items


def print_fields(label: str, fields: list[dict]) -> None:
    print(f"\n=== {label} FIELDS ===")
    for f in fields:
        t = f.get("type")
        print(
            f"  - {f.get('field_name')!r}: type={t} "
            f"({TYPE_MAP.get(t, f'Unknown({t})')}) ui={f.get('ui_type')}"
        )


def first_attachment(fields: dict) -> dict | None:
    logo = fields.get(SRC_LOGO)
    if isinstance(logo, list) and logo and isinstance(logo[0], dict):
        return logo[0]
    return None


def download_attachment(token: str, att: dict) -> tuple[bytes, str]:
    """Download attachment bytes via auth download URL or tmp URL."""
    headers = {"Authorization": f"Bearer {token}"}
    name = str(att.get("name") or "logo.png")
    url = str(att.get("url") or "")
    if url:
        resp = requests.get(url, headers=headers, timeout=90)
        if resp.status_code == 200 and resp.content:
            return resp.content, name

    file_token = str(att.get("file_token") or "")
    if not file_token:
        raise RuntimeError(f"attachment missing file_token: {att}")

    params: dict[str, str] = {"file_tokens": file_token}
    extra = parse_qs(urlparse(url).query).get("extra", [None])[0]
    if not extra:
        tmp_url_meta = str(att.get("tmp_url") or "")
        extra = parse_qs(urlparse(tmp_url_meta).query).get("extra", [None])[0]
    if extra:
        params["extra"] = extra

    meta = requests.get(
        f"{LARK_API_BASE}/drive/v1/medias/batch_get_tmp_download_url",
        headers=headers,
        params=params,
        timeout=30,
    ).json()
    if meta.get("code") != 0:
        raise RuntimeError(f"batch_get_tmp_download_url failed: {meta}")
    urls = (meta.get("data") or {}).get("tmp_download_urls") or []
    if not urls:
        raise RuntimeError(f"no tmp download url for {file_token}")
    dl = urls[0].get("tmp_download_url")
    resp = requests.get(dl, timeout=90)
    if resp.status_code != 200 or not resp.content:
        raise RuntimeError(
            f"tmp download failed status={resp.status_code} len={len(resp.content or b'')}"
        )
    return resp.content, name


def resolve_tmp_download_url(token: str, file_token: str, extra: str | None = None) -> str:
    headers = {"Authorization": f"Bearer {token}"}
    params: dict[str, str] = {"file_tokens": file_token}
    if extra:
        params["extra"] = extra
    meta = requests.get(
        f"{LARK_API_BASE}/drive/v1/medias/batch_get_tmp_download_url",
        headers=headers,
        params=params,
        timeout=30,
    ).json()
    if meta.get("code") != 0:
        raise RuntimeError(f"resolve tmp url failed: {meta}")
    urls = (meta.get("data") or {}).get("tmp_download_urls") or []
    if not urls or not urls[0].get("tmp_download_url"):
        raise RuntimeError(f"empty tmp url for {file_token}")
    return str(urls[0]["tmp_download_url"])


def address_patch(src_fields: dict, dst_fields: dict) -> dict[str, str]:
    patch: dict[str, str] = {}
    for src_key, dst_key in ADDRESS_MAP:
        src_val = textify(src_fields.get(src_key))
        if src_val and is_empty(dst_fields.get(dst_key)):
            patch[dst_key] = src_val
    return patch


def plan(src_records: list[dict], dst_records: list[dict]) -> dict:
    dst_by_name: dict[str, dict] = {}
    for r in dst_records:
        name = textify((r.get("fields") or {}).get(DST_NAME))
        key = norm_name(name)
        if key and key not in dst_by_name:
            dst_by_name[key] = r

    create_list: list[dict] = []
    patch_list: list[dict] = []
    skip_list: list[str] = []
    empty_name = 0
    src_logo_count = 0
    src_contract_count = 0

    for r in src_records:
        fields = r.get("fields") or {}
        name = textify(fields.get(SRC_NAME))
        if not name:
            empty_name += 1
            continue

        att = first_attachment(fields)
        contract = textify(fields.get(SRC_CONTRACT))
        if att:
            src_logo_count += 1
        if contract:
            src_contract_count += 1

        if not contract and not att:
            skip_list.append(f"{name} (no contract/logo)")
            continue

        key = norm_name(name)
        if key in dst_by_name:
            existing = dst_by_name[key]
            ef = existing.get("fields") or {}
            patch_fields = address_patch(fields, ef)
            need_text_logo = bool(att) and is_empty(ef.get(DST_LOGO_TEXT))
            need_att_logo = bool(att) and is_empty(ef.get(DST_LOGO_ATT))
            if patch_fields or need_text_logo or need_att_logo:
                patch_list.append(
                    {
                        "name": name,
                        "record_id": existing["record_id"],
                        "address_patch": patch_fields,
                        "need_text_logo": need_text_logo,
                        "need_att_logo": need_att_logo,
                        "src_att": att,
                        "src_contract": contract,
                    }
                )
            else:
                skip_list.append(name)
        else:
            create_list.append(
                {
                    "name": name,
                    "contract": contract,
                    "src_att": att,
                    "need_logo": bool(att),
                }
            )
            # prevent duplicate creates within same run
            dst_by_name[key] = {
                "record_id": "__pending__",
                "fields": {DST_NAME: name, DST_CONTRACT: contract} if contract else {DST_NAME: name},
            }

    return {
        "create": create_list,
        "patch": patch_list,
        "skip": skip_list,
        "empty_name": empty_name,
        "src_logo_count": src_logo_count,
        "src_contract_count": src_contract_count,
    }


def apply_logo(
    token: str,
    dst_app: str,
    dst_table: str,
    record_id: str,
    name: str,
    att: dict,
    *,
    need_text: bool,
    need_att: bool,
    sleep_s: float,
) -> dict[str, Any]:
    """Download source logo, upload to dest, fill empty logo fields."""
    result: dict[str, Any] = {"ok": False, "text": False, "att": False, "error": None}
    if not need_text and not need_att:
        result["ok"] = True
        return result

    data, fname = download_attachment(token, att)
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", name)[:40] or "project"
    ext = Path(fname).suffix or ".png"
    if not ext.startswith("."):
        ext = "." + ext
    file_token = upload_bitable_image(token, dst_app, data, f"{safe}{ext}")
    time.sleep(sleep_s)

    fields: dict[str, Any] = {}
    if need_att:
        fields[DST_LOGO_ATT] = [{"file_token": file_token}]

    text_url = ""
    if need_text:
        try:
            text_url = resolve_tmp_download_url(token, file_token)
        except Exception:
            # fallback: open-apis download URL (auth required, still a link)
            text_url = (
                f"{LARK_API_BASE}/drive/v1/medias/{file_token}/download"
            )
        fields[DST_LOGO_TEXT] = text_url

    if fields:
        update_record(token, dst_app, dst_table, record_id, fields)
        time.sleep(sleep_s)

    result["ok"] = True
    result["text"] = bool(need_text)
    result["att"] = bool(need_att)
    result["file_token"] = file_token
    result["text_url_prefix"] = (text_url[:80] + "…") if len(text_url) > 80 else text_url
    return result


def field_stats(records: list[dict]) -> dict[str, int]:
    n = len(records)
    text_logo = att_logo = contract = 0
    for r in records:
        f = r.get("fields") or {}
        if not is_empty(f.get(DST_LOGO_TEXT)):
            text_logo += 1
        if not is_empty(f.get(DST_LOGO_ATT)):
            att_logo += 1
        if not is_empty(f.get(DST_CONTRACT)):
            contract += 1
    return {
        "total": n,
        "text_logo": text_logo,
        "att_logo": att_logo,
        "contract": contract,
        "empty_text_logo": n - text_logo,
        "empty_att_logo": n - att_logo,
        "empty_contract": n - contract,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true", help="Actually write to Lark")
    ap.add_argument("--src-app", default=SRC_APP_DEFAULT)
    ap.add_argument("--src-table", default=SRC_TBL_DEFAULT)
    ap.add_argument("--src-view", default=SRC_VIEW_DEFAULT)
    ap.add_argument("--dst-app", default=DST_APP_DEFAULT)
    ap.add_argument("--dst-table", default=DST_TBL_DEFAULT)
    ap.add_argument("--no-view", action="store_true", help="Ignore view_id filter")
    ap.add_argument(
        "--sleep",
        type=float,
        default=0.35,
        help="Seconds between write/upload calls (rate limit)",
    )
    ap.add_argument("--limit", type=int, default=0, help="Max create+patch ops (0=all)")
    args = ap.parse_args()

    app_id = os.getenv("LARK_APP_ID", "").strip()
    app_secret = os.getenv("LARK_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        print("Missing LARK_APP_ID / LARK_APP_SECRET")
        return 1

    token = get_tenant_access_token(app_id, app_secret)

    src_fields = list_fields(token, args.src_app, args.src_table)
    dst_fields = list_fields(token, args.dst_app, args.dst_table)
    print_fields("SOURCE", src_fields)
    print_fields("DEST", dst_fields)

    dst_logo_text_type = next(
        (f.get("type") for f in dst_fields if f.get("field_name") == DST_LOGO_TEXT),
        None,
    )
    dst_logo_att_type = next(
        (f.get("type") for f in dst_fields if f.get("field_name") == DST_LOGO_ATT),
        None,
    )
    print(
        f"\nDest logo fields: {DST_LOGO_TEXT!r} type={dst_logo_text_type} "
        f"({TYPE_MAP.get(dst_logo_text_type)}); "
        f"{DST_LOGO_ATT!r} type={dst_logo_att_type} "
        f"({TYPE_MAP.get(dst_logo_att_type)})"
    )
    print(
        "Address mapping: "
        + ", ".join(f"{s} → {d}" for s, d in ADDRESS_MAP)
        + " (fill-empty only; other dest address cols have no source counterpart)"
    )
    print(
        f"Logo mapping: {SRC_LOGO}(Attachment) → {DST_LOGO_TEXT}(Text URL) "
        f"+ {DST_LOGO_ATT}(Attachment upload)"
    )

    view_id = None if args.no_view else args.src_view
    src = list_with_view(token, args.src_app, args.src_table, view_id)
    dst_before = list_records(token, args.dst_app, args.dst_table)
    before_stats = field_stats(dst_before)
    p = plan(src, dst_before)

    would_addr = sum(1 for x in p["patch"] if x["address_patch"])
    would_logo = sum(
        1 for x in p["patch"] if x["need_text_logo"] or x["need_att_logo"]
    )
    create_with_logo = sum(1 for x in p["create"] if x["need_logo"])
    create_with_contract = sum(1 for x in p["create"] if x["contract"])

    print(f"\nSource records (view={view_id or 'ALL'}): {len(src)}")
    print(f"  with logo: {p['src_logo_count']}, with contract: {p['src_contract_count']}")
    print(f"Dest before: {before_stats}")
    print(f"Would CREATE projects: {len(p['create'])} "
          f"(logo={create_with_logo}, contract={create_with_contract})")
    print(f"Would PATCH matches: {len(p['patch'])} "
          f"(address_fill={would_addr}, logo_fill={would_logo})")
    print(f"Would SKIP: {len(p['skip'])}")
    print(f"Source empty Project Name: {p['empty_name']}")

    print("\nCREATE preview:")
    for x in p["create"][:30]:
        print(
            f"  + {x['name']} | contract={'Y' if x['contract'] else 'N'} "
            f"| logo={'Y' if x['need_logo'] else 'N'}"
        )
    if len(p["create"]) > 30:
        print(f"  ... +{len(p['create']) - 30} more")

    print("\nPATCH preview (first 25):")
    for x in p["patch"][:25]:
        bits = []
        if x["address_patch"]:
            bits.append("addr=" + ",".join(x["address_patch"]))
        if x["need_text_logo"]:
            bits.append("text_logo")
        if x["need_att_logo"]:
            bits.append("att_logo")
        print(f"  ~ {x['name']}: {', '.join(bits)}")
    if len(p["patch"]) > 25:
        print(f"  ... +{len(p['patch']) - 25} more")

    if not args.execute:
        print("\nDRY-RUN only. Pass --execute to write.")
        return 0

    created: list[dict] = []
    patched: list[dict] = []
    logo_ok = 0
    logo_fail = 0
    logo_fail_samples: list[dict] = []
    failed: list[dict] = []
    ops = 0
    limit = args.limit or 10**9

    for item in p["create"]:
        if ops >= limit:
            break
        ops += 1
        fields: dict[str, Any] = {DST_NAME: item["name"]}
        if item["contract"]:
            fields[DST_CONTRACT] = item["contract"]
        try:
            rid = create_record(token, args.dst_app, args.dst_table, fields)
            time.sleep(args.sleep)
            logo_info = None
            if item["need_logo"] and item["src_att"]:
                try:
                    logo_info = apply_logo(
                        token,
                        args.dst_app,
                        args.dst_table,
                        rid,
                        item["name"],
                        item["src_att"],
                        need_text=True,
                        need_att=True,
                        sleep_s=args.sleep,
                    )
                    if logo_info.get("ok"):
                        logo_ok += 1
                    else:
                        logo_fail += 1
                        logo_fail_samples.append(
                            {"name": item["name"], "error": logo_info.get("error")}
                        )
                except Exception as exc:
                    logo_fail += 1
                    logo_fail_samples.append({"name": item["name"], "error": str(exc)})
                    print(f"FAIL logo on create {item['name']}: {exc}")
            created.append(
                {
                    "name": item["name"],
                    "record_id": rid,
                    "logo": logo_info,
                }
            )
            print(f"CREATED {item['name']} -> {rid} logo={logo_info and logo_info.get('ok')}")
        except Exception as exc:
            failed.append({"name": item["name"], "error": str(exc), "op": "create"})
            print(f"FAIL create {item['name']}: {exc}")

    for item in p["patch"]:
        if ops >= limit:
            break
        ops += 1
        try:
            if item["address_patch"]:
                update_record(
                    token,
                    args.dst_app,
                    args.dst_table,
                    item["record_id"],
                    item["address_patch"],
                )
                time.sleep(args.sleep)

            logo_info = None
            if (item["need_text_logo"] or item["need_att_logo"]) and item["src_att"]:
                try:
                    logo_info = apply_logo(
                        token,
                        args.dst_app,
                        args.dst_table,
                        item["record_id"],
                        item["name"],
                        item["src_att"],
                        need_text=item["need_text_logo"],
                        need_att=item["need_att_logo"],
                        sleep_s=args.sleep,
                    )
                    if logo_info.get("ok"):
                        logo_ok += 1
                    else:
                        logo_fail += 1
                        logo_fail_samples.append(
                            {"name": item["name"], "error": logo_info.get("error")}
                        )
                except Exception as exc:
                    logo_fail += 1
                    logo_fail_samples.append({"name": item["name"], "error": str(exc)})
                    print(f"FAIL logo on patch {item['name']}: {exc}")

            patched.append(
                {
                    "name": item["name"],
                    "address": list(item["address_patch"].keys()),
                    "logo": logo_info,
                }
            )
            print(
                f"PATCHED {item['name']} addr={list(item['address_patch'].keys())} "
                f"logo={logo_info and logo_info.get('ok')}"
            )
        except Exception as exc:
            failed.append({"name": item["name"], "error": str(exc), "op": "patch"})
            print(f"FAIL patch {item['name']}: {exc}")

    dst_after = list_records(token, args.dst_app, args.dst_table)
    after_stats = field_stats(dst_after)
    summary = {
        "source_count": len(src),
        "dest_before": before_stats,
        "dest_after": after_stats,
        "created": len(created),
        "patched": len(patched),
        "skipped": len(p["skip"]),
        "empty_name_skipped": p["empty_name"],
        "logo_ok": logo_ok,
        "logo_fail": logo_fail,
        "logo_fail_samples": logo_fail_samples[:20],
        "failed": failed,
        "created_names": [c["name"] for c in created],
        "patched_names": [c["name"] for c in patched],
        "field_mapping": {
            "name": f"{SRC_NAME} → {DST_NAME}",
            "address": [f"{s} → {d}" for s, d in ADDRESS_MAP],
            "logo": f"{SRC_LOGO}(Attachment) → {DST_LOGO_TEXT}(Text) + {DST_LOGO_ATT}(Attachment)",
        },
    }
    out_path = Path("/tmp/lark_wallet_backfill_result.json")
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print("\n=== SUMMARY ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Wrote {out_path}")
    return 1 if failed or logo_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
