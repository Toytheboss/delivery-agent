#!/usr/bin/env python3
"""All projects: newest-first automation events, no 30-cap, no TG chatter."""

from __future__ import annotations

import re
from pathlib import Path

SLICE_RE = re.compile(
    r'"project_events": _openlc_delivery_events\(unique_events\)\n'
    r"                    if str\(record_id\) == \"rec28fJTuC71lg\"\n"
    r"                    else unique_events\[:30\],\n"
)
NEW_SLICE = '"project_events": _delivery_automation_events(unique_events),\n'

HELPER_RE = re.compile(
    r"\ndef _openlc_delivery_events\(unique_events: list\[dict\[str, Any\]\]\) -> list\[dict\[str, Any\]\]:\n"
    r'(?:.*\n)*?    return events\n'
)

NEW_HELPER = '''
def _delivery_automation_events(unique_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Newest first, full automation history, no Telegram chatter, no 30-cap."""
    chatter = {"telegram_outbound", "qa_silent", "qa_replied"}
    events = [
        ev
        for ev in unique_events
        if str(ev.get("kind") or "") not in chatter
    ]
    events.sort(key=lambda ev: str(ev.get("ts") or ""), reverse=True)
    return events
'''


def main() -> None:
    path = Path("/opt/josh-dashboard/bot/dashboard_snapshot.py")
    text = path.read_text(encoding="utf-8")
    new, n = SLICE_RE.subn(NEW_SLICE, text, count=1)
    print("slice replacements", n)
    if n != 1 and "_delivery_automation_events(unique_events)" not in text:
        raise SystemExit("slice not found")
    text = new if n else text
    new, n = HELPER_RE.subn(NEW_HELPER + "\n", text, count=1)
    print("helper replacements", n)
    if n != 1 and "def _delivery_automation_events(" not in text:
        raise SystemExit("helper not found")
    text = new if n else text
    if "def _openlc_delivery_events(" in text:
        raise SystemExit("old helper still present")
    if "unique_events[:30]" in text:
        print("WARN leftover [:30]", text.count("unique_events[:30]"))
    path.write_text(text, encoding="utf-8")
    print("ok")


if __name__ == "__main__":
    main()
