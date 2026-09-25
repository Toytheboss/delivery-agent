#!/usr/bin/env python3
"""Drop dateless synthetic events; ISO-convert unix timestamps on project cards."""

from __future__ import annotations

from pathlib import Path

DASH = Path("/opt/josh-dashboard/bot/dashboard_snapshot.py")

OLD_ADD = '''            def add_unique_event(item: dict[str, Any]) -> None:
                """Add durable workflow evidence when its append-only event is absent."""
                event_key = (
                    str(item.get("kind") or "automation"),
                    str(item.get("event_id") or ""),
                    str(item.get("ts") or ""),
                    str(item.get("text") or ""),
                )
                if event_key in seen_events:
                    return
                seen_events.add(event_key)
                unique_events.append(
                    {
                        "kind": event_key[0],
                        "event_id": event_key[1],
                        "ts": event_key[2],
                        "text": event_key[3] or "自动化任务已执行",
                        "source": str(item.get("source") or "workflow_state"),
                        "status": str(item.get("status") or "success"),
                    }
                )
'''

NEW_ADD = '''            def add_unique_event(item: dict[str, Any]) -> None:
                """Add durable workflow evidence when its append-only event is absent."""
                ts = event_iso(item.get("ts"))
                if not ts:
                    return
                text = (
                    str(item.get("text") or "")
                    .replace("（历史状态无时间）", "")
                    .replace("（历史状态无事件时间）", "")
                    .strip()
                )
                event_key = (
                    str(item.get("kind") or "automation"),
                    str(item.get("event_id") or ""),
                    ts,
                    text,
                )
                if event_key in seen_events:
                    return
                seen_events.add(event_key)
                unique_events.append(
                    {
                        "kind": event_key[0],
                        "event_id": event_key[1],
                        "ts": ts,
                        "text": text or "自动化任务已执行",
                        "source": str(item.get("source") or "workflow_state"),
                        "status": str(item.get("status") or "success"),
                    }
                )
'''

OLD_ASSIGN = '                    "project_events": unique_events,\n'
NEW_ASSIGN = '''                    "project_events": [
                        ev
                        for ev in unique_events
                        if str(ev.get("ts") or "").strip()
                    ],
'''


def main() -> None:
    text = DASH.read_text(encoding="utf-8")
    if OLD_ADD not in text:
        if "if not ts:\n                    return" in text:
            print("add_unique_event already skips empty ts")
        else:
            raise SystemExit("add_unique_event block not found")
    else:
        text = text.replace(OLD_ADD, NEW_ADD, 1)
        print("patched add_unique_event")
    if OLD_ASSIGN not in text:
        if 'if str(ev.get("ts") or "").strip()' in text:
            print("project_events already drops empty ts")
        else:
            raise SystemExit("project_events assign not found")
    else:
        text = text.replace(OLD_ASSIGN, NEW_ASSIGN, 1)
        print("patched project_events filter")
    DASH.write_text(text, encoding="utf-8")
    print("ok")


if __name__ == "__main__":
    main()
