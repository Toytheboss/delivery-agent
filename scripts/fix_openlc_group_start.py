#!/usr/bin/env python3
"""Fix OpenLC project events: start at 拉群, chronological top-to-bottom."""

from __future__ import annotations

import json
from pathlib import Path

RID = "rec28fJTuC71lg"
CHAT = -5124634472
GROUP = "OpenLC X BOT Chain"
GROUP_START = "2026-09-25T19:02:45+08:00"

PULL_EVENT = {
    "ts": GROUP_START,
    "day": "2026-09-25",
    "kind": "tg_group_pulled",
    "source": "拉群",
    "project_name": GROUP,
    "text": "已拉群：OpenLC X BOT Chain（交付号进群）",
    "status": "success",
    "chat_id": CHAT,
    "record_id": RID,
    "event_id": "openlc-group-pulled",
}

OLD_SLICE = """                    "project_events": (
                        [
                            ev
                            for ev in unique_events
                            if str(ev.get("kind") or "")
                            not in {"telegram_outbound", "qa_silent", "qa_replied"}
                        ]
                        if str(record_id) == "rec28fJTuC71lg"
                        else unique_events[:30]
                    ),
"""

NEW_SLICE = """                    "project_events": _openlc_delivery_events(unique_events)
                    if str(record_id) == "rec28fJTuC71lg"
                    else unique_events[:30],
"""

HELPER = '''
def _openlc_delivery_events(unique_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """OpenLC preview: start at 拉群, oldest first, no pre-group Lark noise."""
    chatter = {"telegram_outbound", "qa_silent", "qa_replied"}
    group_start = "2026-09-25T19:02:45+08:00"
    kind_rank = {
        "tg_group_pulled": 0,
        "folder_chat_added": 1,
        "welcome_sequence_sent": 2,
    }
    events = [
        ev
        for ev in unique_events
        if str(ev.get("kind") or "") not in chatter
        and str(ev.get("ts") or "") >= group_start
    ]
    events.sort(
        key=lambda ev: (
            str(ev.get("ts") or ""),
            kind_rank.get(str(ev.get("kind") or ""), 9),
            str(ev.get("event_id") or ""),
        )
    )
    return events

'''


def patch_builder() -> None:
    path = Path("/opt/josh-dashboard/bot/dashboard_snapshot.py")
    text = path.read_text(encoding="utf-8")
    if "def _openlc_delivery_events(" not in text:
        needle = "def snapshot_path(config: Any | None = None) -> Path:"
        if needle not in text:
            raise SystemExit("snapshot_path missing")
        text = text.replace(needle, HELPER + needle, 1)
        print("inserted helper")
    else:
        print("helper already present")
    if OLD_SLICE in text:
        text = text.replace(OLD_SLICE, NEW_SLICE, 1)
        print("replaced OpenLC slice")
    elif "_openlc_delivery_events(unique_events)" in text:
        print("OpenLC slice already using helper")
    else:
        raise SystemExit("OpenLC slice not found")
    path.write_text(text, encoding="utf-8")


def append_jsonl() -> None:
    jsonl = Path("/opt/botchain-qa-tg-bot/data/workflow_events.jsonl")
    existing = jsonl.read_text(encoding="utf-8")
    marker = str(PULL_EVENT["event_id"])
    if marker in existing:
        print("skip jsonl", marker)
        return
    with jsonl.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(PULL_EVENT, ensure_ascii=False) + "\n")
    print("jsonl+", PULL_EVENT["kind"], PULL_EVENT["ts"])


if __name__ == "__main__":
    patch_builder()
    append_jsonl()
    print("ok")
