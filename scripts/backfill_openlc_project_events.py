#!/usr/bin/env python3
"""OpenLC-only: persist missing automation events and uncap the project-events card."""

from __future__ import annotations

import json
from pathlib import Path

RID = "rec28fJTuC71lg"
CHAT = -5124634472
NAME = "OpenLC"
GROUP = "OpenLC X BOT Chain"
PR_URL = "https://x.com/OpenLCdev/status/2103260520187064709"
PR_TS = "2026-09-25T19:48:57+08:00"

NEW_EVENTS = [
    {
        "ts": "2026-09-25T19:02:45+08:00",
        "day": "2026-09-25",
        "kind": "welcome_sequence_sent",
        "source": "group_welcome",
        "project_name": GROUP,
        "text": "交付号已向 OpenLC X BOT Chain 完成 1 步自动问候",
        "status": "success",
        "chat_id": CHAT,
        "language": "en",
        "step_count": 1,
        "event_id": "openlc-welcome-josh",
        "bot": "josh",
    },
    {
        "ts": "2026-09-25T19:02:46+08:00",
        "day": "2026-09-25",
        "kind": "folder_chat_added",
        "source": "folder_auto_add",
        "project_name": GROUP,
        "text": "交付号已将 OpenLC X BOT Chain 拉入文件夹 botchain #8",
        "status": "success",
        "chat_id": CHAT,
        "folder_name": "botchain #8",
        "event_id": "openlc-folder-josh",
        "bot": "josh",
    },
    {
        "ts": "2026-09-25T19:08:38+08:00",
        "day": "2026-09-25",
        "kind": "folder_chat_added",
        "source": "folder_auto_add",
        "project_name": GROUP,
        "text": "Roy号已将 OpenLC X BOT Chain 拉入文件夹 Botchain #8",
        "status": "success",
        "chat_id": CHAT,
        "folder_name": "Botchain #8",
        "event_id": "openlc-folder-roy",
        "bot": "roy",
    },
    {
        "ts": PR_TS,
        "day": "2026-09-25",
        "kind": "pr_support_written",
        "source": "pr support",
        "project_name": NAME,
        "text": f"pr support：已将 PR 链接覆盖写入飞书进度表 KPI 2：{PR_URL}",
        "status": "success",
        "record_id": RID,
        "chat_id": CHAT,
        "url": PR_URL,
        "event_id": f"pr-capture-{RID}-{PR_TS}",
    },
    {
        "ts": "2026-09-25T21:18:48+08:00",
        "day": "2026-09-25",
        "kind": "mark_live",
        "source": "mark_live",
        "project_name": NAME,
        "text": "已在 TG 执行 mark live，OpenLC 状态改为主网上线",
        "status": "success",
        "record_id": RID,
        "chat_id": CHAT,
        "event_id": "openlc-mark-live",
    },
]

LOGO_BLOCK = """            indexed_events.append(
                {
                    **item,
                    "kind": "logo_uploaded_lark",
                    "text": logo_text,
                    "ts": event_iso(item.get("ts")),
                    "source": "logo_fill",
                    "status": status,
                }
            )

        deploy_state = load_state(
"""

LOGO_REPL = """            indexed_events.append(
                {
                    **item,
                    "kind": "logo_uploaded_lark",
                    "text": logo_text,
                    "ts": event_iso(item.get("ts")),
                    "source": "logo_fill",
                    "status": status,
                }
            )

        pr_capture_path = Path(
            str(getattr(config, "pr_capture_events_file", "") or "").strip()
            or "/opt/botchain-shared/pr_capture_events.jsonl"
        )
        if pr_capture_path.is_file():
            for item in _read_jsonl(pr_capture_path, max_days=3650):
                url = str(item.get("url") or "").strip()
                if not url:
                    continue
                project = str(item.get("project") or item.get("project_name") or "").strip()
                rid = str(item.get("record_id") or "").strip()
                ts = event_iso(item.get("ts"))
                indexed_events.append(
                    {
                        **item,
                        "kind": "pr_support_written",
                        "event_id": f"pr-capture-{rid}-{ts}",
                        "project_name": project,
                        "text": f"pr support：已将 PR 链接覆盖写入飞书进度表 KPI 2：{url}",
                        "ts": ts,
                        "source": "pr support",
                        "status": "success",
                    }
                )

        deploy_state = load_state(
"""

CAP_BLOCK = """                    "delivery_steps": delivery_steps,
                    "project_events": unique_events[:30],
                    "issues": issues,
"""

CAP_REPL = """                    "delivery_steps": delivery_steps,
                    "project_events": (
                        [
                            ev
                            for ev in unique_events
                            if str(ev.get("kind") or "")
                            not in {"telegram_outbound", "qa_silent", "qa_replied"}
                        ]
                        if str(record_id) == "rec28fJTuC71lg"
                        else unique_events[:30]
                    ),
                    "issues": issues,
"""


def patch_snapshot_builder() -> None:
    path = Path("/opt/josh-dashboard/bot/dashboard_snapshot.py")
    text = path.read_text(encoding="utf-8")
    if "pr_support_written" in text and 'record_id) == "rec28fJTuC71lg"' in text:
        print("dashboard_snapshot.py already patched")
        return
    if LOGO_BLOCK not in text:
        raise SystemExit("logo insert point missing")
    if CAP_BLOCK not in text:
        raise SystemExit("30-cap insert point missing")
    text = text.replace(LOGO_BLOCK, LOGO_REPL, 1)
    text = text.replace(CAP_BLOCK, CAP_REPL, 1)
    path.write_text(text, encoding="utf-8")
    print("patched", path)


def patch_html() -> None:
    path = Path("/opt/josh-dashboard/static/dashboard/delivery-console-prototype.html")
    text = path.read_text(encoding="utf-8")
    updated = text.replace("项目事件（最近 30 条）", "项目事件")
    updated = updated.replace("Project events (latest 30)", "Project events")
    if updated == text:
        print("html already patched or heading missing")
        return
    path.write_text(updated, encoding="utf-8")
    print("patched", path)


def append_jsonl() -> None:
    jsonl = Path("/opt/botchain-qa-tg-bot/data/workflow_events.jsonl")
    existing = jsonl.read_text(encoding="utf-8")
    appended = 0
    with jsonl.open("a", encoding="utf-8") as fh:
        for ev in NEW_EVENTS:
            marker = str(ev["event_id"])
            if marker in existing:
                print("skip jsonl", marker)
                continue
            fh.write(json.dumps(ev, ensure_ascii=False) + "\n")
            appended += 1
            print("jsonl+", ev["kind"], ev["ts"])
    print("appended", appended)


if __name__ == "__main__":
    patch_snapshot_builder()
    patch_html()
    append_jsonl()
    print("ok")
