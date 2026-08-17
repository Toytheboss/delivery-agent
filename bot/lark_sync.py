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
    """Fetch the wiki and update its local file only when content changed.

    Returns ``True`` when a new version was written and ``False`` when the
    remote content is identical to the current local copy.
    """
    content = fetch_wiki_text(app_id, app_secret, wiki_token)
    knowledge_dir.mkdir(parents=True, exist_ok=True)
    out_file = knowledge_dir / f"lark_{wiki_token}.md"
    header = f"# Lark Wiki ({wiki_token})\n\n"
    payload = header + content
    if out_file.is_file():
        try:
            if out_file.read_text(encoding="utf-8") == payload:
                logger.info("Lark wiki unchanged: %s (%d chars)", out_file.name, len(content))
                return False
        except OSError:
            logger.exception("Failed reading existing Lark wiki file %s", out_file)
    out_file.write_text(payload, encoding="utf-8")
    logger.info("Lark wiki synced to %s (%d chars)", out_file.name, len(content))
    return True
