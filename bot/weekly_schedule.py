"""Shared clocks for weekly Lark pings: prepare early, send at HH:00:00."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

TZ = timezone(timedelta(hours=8))
DEFAULT_SEND_HOUR = 0
DEFAULT_DAILY_HOUR = 0
DEFAULT_PREPARE_MINUTES = 5
DEFAULT_WEEKDAY = 0  # Monday
SEND_GRACE = timedelta(minutes=2)
SENT_RECENT = timedelta(hours=18)


def ping_weekday(config: Any, attr: str) -> int:
    return int(getattr(config, attr, DEFAULT_WEEKDAY) or 0)


def send_hour(config: Any, attr: str) -> int:
    raw = getattr(config, attr, DEFAULT_SEND_HOUR)
    if raw is None:
        return DEFAULT_SEND_HOUR
    return int(raw)


def daily_hour(config: Any, attr: str) -> int:
    raw = getattr(config, attr, DEFAULT_DAILY_HOUR)
    if raw is None:
        return DEFAULT_DAILY_HOUR
    return int(raw)


def prepare_minutes(config: Any, attr: str) -> int:
    raw = getattr(config, attr, DEFAULT_PREPARE_MINUTES)
    if raw is None:
        return DEFAULT_PREPARE_MINUTES
    return max(int(raw), 1)


def next_clock(now: datetime, hour: int, minute: int = 0) -> datetime:
    now = now.astimezone(TZ)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if now >= target:
        target += timedelta(days=1)
    return target


def next_send_at(now: datetime, *, weekday: int, hour: int) -> datetime:
    """Next weekday at hour:00:00. If that instant is now, return now's slot."""
    now = now.astimezone(TZ)
    days = (weekday - now.weekday()) % 7
    target = now.replace(hour=hour, minute=0, second=0, microsecond=0) + timedelta(
        days=days
    )
    if target < now:
        target += timedelta(days=7)
    return target


def this_send_at(now: datetime, *, weekday: int, hour: int) -> datetime:
    now = now.astimezone(TZ)
    days = (now.weekday() - weekday) % 7
    return now.replace(hour=hour, minute=0, second=0, microsecond=0) - timedelta(
        days=days
    )


def ping_sent_recently(
    state: dict[str, Any] | None,
    now: datetime,
    *,
    window: timedelta = SENT_RECENT,
) -> bool:
    """True if we already pinged the group in this window — do not send again."""
    raw = str((state or {}).get("last_sent_at") or "").strip()
    if not raw:
        return False
    try:
        sent = datetime.fromisoformat(raw)
    except ValueError:
        return False
    if sent.tzinfo is None:
        sent = sent.replace(tzinfo=TZ)
    return now.astimezone(TZ) - sent.astimezone(TZ) < window


def upcoming_send_at(
    now: datetime,
    *,
    weekday: int,
    hour: int,
    already_sent: bool,
    grace: timedelta = SEND_GRACE,
) -> datetime:
    """Next Monday 00:00:00. Do not replay last week's slot after a restart.

    Only the same ping instant plus a short grace may still send. Later the
    same night, skip until next week — never send a second copy.
    """
    now = now.astimezone(TZ)
    slot = this_send_at(now, weekday=weekday, hour=hour)
    if already_sent:
        return slot + timedelta(days=7)
    if now < slot:
        return slot
    if now <= slot + grace:
        return slot
    return slot + timedelta(days=7)


def send_due(now: datetime, *, weekday: int, hour: int) -> bool:
    now = now.astimezone(TZ)
    return now.weekday() == weekday and now >= now.replace(
        hour=hour, minute=0, second=0, microsecond=0
    )


async def sleep_until(target: datetime) -> None:
    """Sleep until target. Last slice uses the remaining seconds so send can hit :00:00."""
    target = target.astimezone(TZ)
    while True:
        remaining = (target - datetime.now(TZ)).total_seconds()
        if remaining <= 0:
            return
        if remaining > 30:
            await asyncio.sleep(30)
            continue
        await asyncio.sleep(remaining)
        return
