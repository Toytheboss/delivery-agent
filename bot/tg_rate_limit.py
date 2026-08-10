"""Shared Telegram API throttle — avoid GetChatsRequest flood as folders grow."""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator

# One heavy TG operation at a time (folder refresh, title resolve, dialog scans).
_TG_HEAVY_LOCK = asyncio.Lock()

# Space out get_entity / similar calls.
_MIN_ENTITY_GAP_S = 0.08
_last_entity_at = 0.0


@asynccontextmanager
async def tg_heavy_section() -> AsyncIterator[None]:
    """Serialize folder scans / bulk resolves so they don't pile up."""
    async with _TG_HEAVY_LOCK:
        yield


async def paced_get_entity(client, peer, *, gap: float | None = None):
    """get_entity with a small gap so bulk resolves don't trip flood wait."""
    global _last_entity_at
    gap = _MIN_ENTITY_GAP_S if gap is None else max(0.0, gap)
    now = time.monotonic()
    wait = gap - (now - _last_entity_at)
    if wait > 0:
        await asyncio.sleep(wait)
    try:
        return await client.get_entity(peer)
    finally:
        _last_entity_at = time.monotonic()
