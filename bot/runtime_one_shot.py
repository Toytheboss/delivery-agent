"""Load an optional server-only `scripts/runtime_one_shot.py` at boot.

The file is not in git. Ops drops it on the host when a one-time background
task must share the live Telegram client (for example a paced group leave).
"""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent
_PATH = ROOT / "scripts" / "runtime_one_shot.py"


def start_if_present(client: Any, config: Any) -> None:
    if not _PATH.is_file():
        return
    spec = importlib.util.spec_from_file_location("runtime_one_shot", _PATH)
    if spec is None or spec.loader is None:
        logger.warning("runtime one-shot skipped: cannot load %s", _PATH)
        return
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    start = getattr(mod, "start", None)
    if start is None:
        logger.warning("runtime one-shot skipped: no start() in %s", _PATH)
        return
    import asyncio

    asyncio.create_task(start(client, config))
    logger.info("runtime one-shot started from %s", _PATH)
