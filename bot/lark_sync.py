"""Sync Lark Wiki content into the knowledge directory."""

from __future__ import annotations

import logging
from pathlib import Path

from fetch_lark_wiki import fetch_wiki_text

logger = logging.getLogger(__name__)


def sync_lark_wiki(
    knowledge_dir: Path,
    app_id: str,
    app_secret: str,
    wiki_token: str,
) -> bool:
    """Fetch wiki content and write to knowledge/lark_{wiki_token}.md. Returns True on success."""
    content = fetch_wiki_text(app_id, app_secret, wiki_token)
    knowledge_dir.mkdir(parents=True, exist_ok=True)
    out_file = knowledge_dir / f"lark_{wiki_token}.md"
    header = f"# Lark Wiki ({wiki_token})\n\n"
    out_file.write_text(header + content, encoding="utf-8")
    logger.info("Lark wiki synced to %s (%d chars)", out_file.name, len(content))
    return True
