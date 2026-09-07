"""Auto-greet newly joined Telegram groups whose title contains Delivery.

Flow:
1. ChatAction (bot added / group created) → mark pending and try send immediately.
2. Before send: sample recent non-bot messages → detect lang; else title; else EN.
3. min_messages_before_welcome=0 means send as soon as eligible (no wait for new msgs).
4. Send the timed welcome sequence in that language and mark greeted.

Periodic scans never backfill-greet existing groups. On first enable or when
pilot scope expands, currently known matching groups are baselined as greeted.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from telethon import events, utils

from bot.config_loader import is_pilot_chat

if TYPE_CHECKING:
    from telethon import TelegramClient

    from bot.config_loader import AppConfig

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent

# In-process claim so concurrent ChatAction (Telegram often fires twice on join)
# cannot start two welcome sequences before disk "greeted" is written.
_welcome_claiming: set[int] = set()


def _state_path(config: AppConfig) -> Path:
    return ROOT / config.welcome_state_file


def _welcome_scope_key(config: AppConfig) -> str:
    """Fingerprint of who is eligible for welcome (changes when pilot toggles)."""
    if not config.pilot_enabled:
        return "all"
    ids = ",".join(str(i) for i in sorted(config.pilot_group_ids))
    return f"pilot:{ids}"


def _empty_state() -> dict[str, Any]:
    return {
        "greeted_chat_ids": [],
        "pending_chat_ids": [],
        "pending_msg_counts": {},
        "baseline_scope": None,
    }


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _empty_state()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return _empty_state()
        if "pending_msg_counts" not in data or not isinstance(
            data.get("pending_msg_counts"), dict
        ):
            data["pending_msg_counts"] = {}
        return data
    except (OSError, json.JSONDecodeError):
        return _empty_state()


def _save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _as_int_set(values: Any) -> set[int]:
    out: set[int] = set()
    for x in values or []:
        try:
            out.add(int(x))
        except (TypeError, ValueError):
            continue
    return out


def _as_count_map(values: Any) -> dict[int, int]:
    out: dict[int, int] = {}
    if not isinstance(values, dict):
        return out
    for k, v in values.items():
        try:
            out[int(k)] = max(int(v), 0)
        except (TypeError, ValueError):
            continue
    return out


def _min_messages(config: AppConfig) -> int:
    """0 = send immediately once eligible (sample history → lang → welcome)."""
    raw = getattr(config, "welcome_min_messages_before_welcome", 0)
    try:
        return max(int(raw), 0)
    except (TypeError, ValueError):
        return 0


def title_matches_project(title: str, keywords: list[str]) -> bool:
    norm = " ".join((title or "").lower().split())
    if not norm:
        return False
    for kw in keywords:
        k = " ".join((kw or "").lower().split())
        if k and k in norm:
            return True
    compact = norm.replace(" ", "")
    for kw in keywords:
        k = "".join((kw or "").lower().split())
        if k and k in compact:
            return True
    return False


def title_language_hint(title: str, keywords: list[str] | None = None) -> str | None:
    """Infer zh/en from group title after stripping configured brand tokens."""
    raw = (title or "").strip()
    if not raw:
        return None
    cleaned = raw
    for kw in keywords or []:
        k = (kw or "").strip()
        if k:
            cleaned = re.sub(re.escape(k), " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[<>|/_\-–,.:]+", " ", cleaned)
    cleaned = " ".join(cleaned.split())
    if not cleaned:
        return None

    letters = sum(1 for c in cleaned if c.isascii() and c.isalpha())
    cjk = sum(1 for c in cleaned if "\u4e00" <= c <= "\u9fff")
    if cjk >= 1:
        return "zh"
    if letters >= 2:
        return "en"
    return None


def classify_message_language(text: str) -> str | None:
    """Classify one message as zh/en, or None if inconclusive.

    Heuristic: CJK ratio vs Latin letters. Pure emoji / digits → None.
    """
    sample = (text or "").strip()
    if len(sample) < 1:
        return None
    letters = sum(1 for c in sample if c.isascii() and c.isalpha())
    cjk = sum(1 for c in sample if "\u4e00" <= c <= "\u9fff")
    if cjk >= 1 and cjk >= letters:
        return "zh"
    if cjk >= 2:
        return "zh"
    if letters >= 2 and letters > cjk:
        return "en"
    return None


def detect_welcome_language(title: str, sample_text: str | list[str]) -> str:
    """Pick welcome language from group messages, then title, then English.

    Rules:
    1. Majority vote over collected non-bot message texts (zh vs en).
    2. If tied / no clear votes → title heuristic.
    3. If still unclear → English (mixed Latin / ambiguous default).
    """
    if isinstance(sample_text, list):
        messages = [str(m).strip() for m in sample_text if str(m).strip()]
    else:
        # Split joined samples from sample_group_text / recount
        raw = (sample_text or "").strip()
        messages = [ln.strip() for ln in raw.split("\n") if ln.strip()] if raw else []

    zh_votes = 0
    en_votes = 0
    for msg in messages:
        lang = classify_message_language(msg)
        if lang == "zh":
            zh_votes += 1
        elif lang == "en":
            en_votes += 1

    if zh_votes > en_votes:
        return "zh"
    if en_votes > zh_votes:
        return "en"

    # Tie or inconclusive: fall back to title, then English
    hint = title_language_hint(title)
    if hint in ("zh", "en"):
        return hint
    return "en"


def welcome_text_for_lang(config: AppConfig, lang: str) -> str:
    if lang == "zh":
        text = (config.welcome_message_zh or "").strip()
        if text:
            return text
    text = (config.welcome_message_en or "").strip()
    if text:
        return text
    return (config.welcome_message or "").strip()


def welcome_sequence_for_lang(config: AppConfig, lang: str) -> list[dict[str, Any]]:
    """Return timed welcome steps: [{delay_seconds, text}, ...]."""
    seq = (
        config.welcome_sequence_zh
        if lang == "zh"
        else config.welcome_sequence_en
    )
    if not seq and lang == "zh":
        seq = config.welcome_sequence_en
    if not seq and lang != "zh":
        seq = config.welcome_sequence_zh
    if seq:
        return seq
    # Fallback: single message
    text = welcome_text_for_lang(config, lang)
    if not text:
        return []
    return [{"delay_seconds": 0, "text": text}]


async def _send_welcome_sequence(
    client: TelegramClient,
    chat_id: int,
    steps: list[dict[str, Any]],
    *,
    lang: str,
    title: str,
) -> bool:
    """Send timed welcome messages. delay_seconds is from sequence start."""
    if not steps:
        return False
    loop = asyncio.get_running_loop()
    start = loop.time()
    sent_any = False
    for i, step in enumerate(steps, 1):
        delay = max(int(step.get("delay_seconds") or 0), 0)
        text = str(step.get("text") or "").strip()
        if not text:
            continue
        wait = delay - (loop.time() - start)
        if wait > 0:
            await asyncio.sleep(wait)
        try:
            await client.send_message(chat_id, text)
            sent_any = True
            try:
                from bot.metrics import inc

                inc("welcome_messages_sent")
            except Exception:  # noqa: BLE001
                pass
            logger.info(
                "Welcome step %d/%d (%s, +%ds) chat_id=%s title=%r",
                i,
                len(steps),
                lang,
                delay,
                chat_id,
                title,
            )
        except Exception:
            logger.exception(
                "Welcome step %d failed chat_id=%s title=%r",
                i,
                chat_id,
                title,
            )
            # Keep going for later steps if one fails
            continue
    return sent_any


async def sample_group_messages(
    client: TelegramClient,
    chat_id: int,
    *,
    sample_limit: int = 50,
    exclude_user_id: int | None = None,
) -> list[str]:
    """Collect recent non-empty non-bot message texts (newest first)."""
    chunks: list[str] = []
    try:
        async for msg in client.iter_messages(chat_id, limit=sample_limit):
            if exclude_user_id is not None and getattr(msg, "sender_id", None) == exclude_user_id:
                continue
            if getattr(msg, "out", False):
                continue
            text = (
                getattr(msg, "message", None) or getattr(msg, "raw_text", None) or ""
            ).strip()
            if text:
                chunks.append(text)
    except Exception:  # noqa: BLE001
        logger.warning("welcome: failed to sample messages chat_id=%s", chat_id)
    return chunks


async def sample_group_text(
    client: TelegramClient,
    chat_id: int,
    *,
    sample_limit: int = 30,
    exclude_user_id: int | None = None,
) -> str:
    """Collect recent non-empty message text (compat helper)."""
    chunks = await sample_group_messages(
        client,
        chat_id,
        sample_limit=sample_limit,
        exclude_user_id=exclude_user_id,
    )
    return "\n".join(chunks).strip()


def _mark_pending(path: Path, chat_id: int) -> None:
    state = _load_state(path)
    greeted = _as_int_set(state.get("greeted_chat_ids"))
    pending = _as_int_set(state.get("pending_chat_ids"))
    counts = _as_count_map(state.get("pending_msg_counts"))
    if chat_id in greeted:
        return
    pending.add(chat_id)
    counts.setdefault(chat_id, 0)
    state["greeted_chat_ids"] = sorted(greeted)
    state["pending_chat_ids"] = sorted(pending)
    state["pending_msg_counts"] = {str(k): v for k, v in sorted(counts.items())}
    _save_state(path, state)


def _set_pending_count(path: Path, chat_id: int, count: int) -> None:
    state = _load_state(path)
    pending = _as_int_set(state.get("pending_chat_ids"))
    counts = _as_count_map(state.get("pending_msg_counts"))
    if chat_id not in pending:
        return
    counts[chat_id] = max(int(count), 0)
    state["pending_msg_counts"] = {str(k): v for k, v in sorted(counts.items())}
    _save_state(path, state)


def _mark_greeted(path: Path, chat_id: int) -> None:
    state = _load_state(path)
    greeted = _as_int_set(state.get("greeted_chat_ids"))
    pending = _as_int_set(state.get("pending_chat_ids"))
    counts = _as_count_map(state.get("pending_msg_counts"))
    greeted.add(chat_id)
    pending.discard(chat_id)
    counts.pop(chat_id, None)
    state["greeted_chat_ids"] = sorted(greeted)
    state["pending_chat_ids"] = sorted(pending)
    state["pending_msg_counts"] = {str(k): v for k, v in sorted(counts.items())}
    _save_state(path, state)


async def try_send_welcome_now(
    client: TelegramClient,
    config: AppConfig,
    chat_id: int,
    title: str,
    *,
    my_id: int | None = None,
    sample_text: str | list[str] | None = None,
    known_count: int | None = None,
) -> bool:
    """Send welcome when eligible; with min_messages=0, send immediately after sampling."""
    if not config.welcome_enabled:
        return False
    if not is_pilot_chat(config, chat_id):
        logger.debug(
            "Welcome skipped (outside pilot list) chat_id=%s title=%r",
            chat_id,
            title,
        )
        return False

    path = _state_path(config)
    state = _load_state(path)
    greeted = _as_int_set(state.get("greeted_chat_ids"))
    pending = _as_int_set(state.get("pending_chat_ids"))
    if chat_id in greeted or chat_id in _welcome_claiming:
        return False
    # Already queued: allow send even if title fetch fails later
    if chat_id not in pending and not title_matches_project(
        title, config.welcome_name_keywords
    ):
        return False

    # Claim before any await — Telegram often emits two ChatAction events on join.
    _welcome_claiming.add(chat_id)
    try:
        min_n = _min_messages(config)
        messages: list[str]
        if isinstance(sample_text, list):
            messages = [str(m).strip() for m in sample_text if str(m).strip()]
        elif isinstance(sample_text, str) and sample_text.strip():
            messages = [ln.strip() for ln in sample_text.split("\n") if ln.strip()]
        else:
            messages = await sample_group_messages(
                client, chat_id, exclude_user_id=my_id
            )

        count = known_count if known_count is not None else len(messages)
        if min_n > 0 and count < min_n:
            _mark_pending(path, chat_id)
            _set_pending_count(path, chat_id, count)
            logger.info(
                "Welcome pending (%d/%d non-bot messages) chat_id=%s title=%r",
                count,
                min_n,
                chat_id,
                title,
            )
            _welcome_claiming.discard(chat_id)
            return False

        lang = detect_welcome_language(title, messages)
        steps = welcome_sequence_for_lang(config, lang)
        if not steps:
            logger.warning("welcome.enabled but no welcome message/sequence configured")
            _welcome_claiming.discard(chat_id)
            return False

        # Persist greeted so restarts/scans don't start a duplicate sequence.
        # Keep greeted even if send fails — do not retry-spam every scan.
        _mark_greeted(path, chat_id)
        try:
            from bot.metrics import inc

            inc("welcome_sequences_started")
        except Exception:  # noqa: BLE001
            pass

        async def _run() -> None:
            try:
                ok = await _send_welcome_sequence(
                    client, chat_id, steps, lang=lang, title=title
                )
                if not ok:
                    logger.warning(
                        "Welcome sequence sent 0 messages (kept greeted to avoid retry) "
                        "chat_id=%s title=%r",
                        chat_id,
                        title,
                    )
                    return
                logger.info(
                    "Welcome sequence done (%s, %d step(s), from %d msg(s)) "
                    "chat_id=%s title=%r",
                    lang,
                    len(steps),
                    count,
                    chat_id,
                    title,
                )
            finally:
                _welcome_claiming.discard(chat_id)

        # Don't block handlers for the 30s / 60s waits
        asyncio.create_task(_run())
        return True
    except Exception:
        _welcome_claiming.discard(chat_id)
        raise


async def send_group_welcome(
    client: TelegramClient,
    config: AppConfig,
    chat_id: int,
    title: str,
    *,
    greeted: set[int] | None = None,
    my_id: int | None = None,
) -> bool:
    """Compatibility wrapper used by scanners."""
    path = _state_path(config)
    state = _load_state(path)
    already = _as_int_set(state.get("greeted_chat_ids"))
    if greeted is not None:
        already |= greeted
    if chat_id in already:
        return False
    return await try_send_welcome_now(
        client, config, chat_id, title, my_id=my_id
    )


async def baseline_existing_project_groups(
    client: TelegramClient, config: AppConfig
) -> int:
    """Mark existing matching groups as already greeted (no spam).

    Always runs on startup:
    - When scope expands (e.g. pilot → all) or first baseline: force-mark every
      currently known matching dialog, and clear pending.
    - Otherwise soft catch-up: mark unknown matching dialogs as greeted without
      sending (so scans never backfill-greet old groups).

    When pilot_enabled, pilot groups stay unmarked so greet_pilot_groups_now
    can still send.
    """
    if not config.welcome_enabled:
        return 0

    path = _state_path(config)
    state = _load_state(path)
    scope_key = _welcome_scope_key(config)
    prev_scope = state.get("baseline_scope")
    force = prev_scope != scope_key

    greeted = _as_int_set(state.get("greeted_chat_ids"))
    pending = _as_int_set(state.get("pending_chat_ids"))
    counts = _as_count_map(state.get("pending_msg_counts"))
    pending_before = len(pending)
    marked = 0
    skipped_pilot = 0

    async for dialog in client.iter_dialogs():
        entity = dialog.entity
        title = getattr(entity, "title", None) or ""
        if not title_matches_project(title, config.welcome_name_keywords):
            continue
        # Prefer live megagroup after migration
        migrated = getattr(entity, "migrated_to", None)
        if migrated is not None:
            try:
                entity = await client.get_entity(migrated)
            except Exception:  # noqa: BLE001
                pass
        try:
            chat_id = utils.get_peer_id(entity)
        except Exception:  # noqa: BLE001
            continue

        if title:
            try:
                from bot.workflow_form_dispatch import remember_chat_title

                remember_chat_title(chat_id, title)
            except Exception:  # noqa: BLE001
                pass

        if config.pilot_enabled and is_pilot_chat(config, chat_id):
            skipped_pilot += 1
            continue

        if force:
            pending.discard(chat_id)
            counts.pop(chat_id, None)
            if chat_id not in greeted:
                greeted.add(chat_id)
                marked += 1
            else:
                greeted.add(chat_id)
        else:
            # Soft catch-up: never send to unknown existing dialogs
            if chat_id not in greeted and chat_id not in pending:
                greeted.add(chat_id)
                marked += 1

    if force:
        # Drop all pending on scope expand / first baseline so we never resume
        # a mistaken backfill storm after restart.
        pending.clear()
        counts.clear()

    state["greeted_chat_ids"] = sorted(greeted)
    state["pending_chat_ids"] = sorted(pending)
    state["pending_msg_counts"] = {str(k): v for k, v in sorted(counts.items())}
    state["baseline_scope"] = scope_key
    _save_state(path, state)

    if force:
        logger.info(
            "Welcome baseline (scope %r → %r): newly marked %d, total greeted=%d, "
            "cleared %d pending; skipped %d pilot group(s) — no messages sent",
            prev_scope,
            scope_key,
            marked,
            len(greeted),
            pending_before,
            skipped_pilot,
        )
    elif marked:
        logger.info(
            "Welcome baseline catch-up: marked %d previously unseen group(s) as greeted "
            "(no send); scope=%r total_greeted=%d",
            marked,
            scope_key,
            len(greeted),
        )
    else:
        logger.info(
            "Welcome baseline OK (scope=%r, greeted=%d, pending=%d) — no messages sent",
            scope_key,
            len(greeted),
            len(pending),
        )
    return marked


async def greet_pilot_groups_now(
    client: TelegramClient,
    config: AppConfig,
    *,
    my_id: int | None = None,
) -> int:
    """Kick off welcome for pilot groups (immediate when min_messages=0)."""
    if not config.welcome_enabled or not config.pilot_enabled:
        return 0
    if not config.pilot_group_ids:
        return 0

    path = _state_path(config)
    min_n = _min_messages(config)
    started = 0
    for chat_id in sorted(config.pilot_group_ids):
        try:
            entity = await client.get_entity(chat_id)
        except Exception:  # noqa: BLE001
            logger.warning("greet_pilot: cannot resolve chat_id=%s", chat_id)
            continue
        title = getattr(entity, "title", None) or ""
        messages = await sample_group_messages(
            client, chat_id, exclude_user_id=my_id
        )
        if min_n > 0 and len(messages) < min_n:
            _mark_pending(path, chat_id)
            _set_pending_count(path, chat_id, len(messages))
            logger.info(
                "Pilot welcome pending (%d/%d msgs) chat_id=%s title=%r",
                len(messages),
                min_n,
                chat_id,
                title,
            )
            continue
        ok = await try_send_welcome_now(
            client,
            config,
            chat_id,
            title,
            my_id=my_id,
            sample_text=messages,
            known_count=len(messages),
        )
        if ok:
            started += 1
            logger.info("Pilot welcome started chat_id=%s title=%r", chat_id, title)
    return started


async def scan_new_project_groups(
    client: TelegramClient,
    config: AppConfig,
    *,
    my_id: int | None = None,
) -> int:
    """Process pending welcomes only; silently baseline any other unmatched dialogs.

    Never backfill-greet existing groups that were not explicitly pending
    (pending comes from ChatAction join / empty new group wait).
    """
    if not config.welcome_enabled:
        return 0

    path = _state_path(config)
    state = _load_state(path)
    greeted = _as_int_set(state.get("greeted_chat_ids"))
    pending = _as_int_set(state.get("pending_chat_ids"))
    sent = 0
    catchup = 0

    # Soft catch-up: mark unknown matching dialogs as greeted (no send)
    async for dialog in client.iter_dialogs():
        entity = dialog.entity
        title = getattr(entity, "title", None) or ""
        if not title_matches_project(title, config.welcome_name_keywords):
            continue
        try:
            chat_id = utils.get_peer_id(entity)
        except Exception:  # noqa: BLE001
            continue
        if chat_id in greeted or chat_id in pending:
            continue
        if config.pilot_enabled and not is_pilot_chat(config, chat_id):
            continue
        greeted.add(chat_id)
        catchup += 1

    if catchup:
        state = _load_state(path)
        merged = _as_int_set(state.get("greeted_chat_ids")) | greeted
        state["greeted_chat_ids"] = sorted(merged)
        state["pending_chat_ids"] = sorted(
            _as_int_set(state.get("pending_chat_ids"))
        )
        _save_state(path, state)
        logger.info(
            "Welcome scan catch-up: marked %d unseen group(s) as greeted (no send)",
            catchup,
        )

    # Only attempt sends for explicitly pending chats (min_messages=0 → immediate)
    state = _load_state(path)
    pending = _as_int_set(state.get("pending_chat_ids"))
    for chat_id in sorted(pending):
        try:
            entity = await client.get_entity(chat_id)
        except Exception:  # noqa: BLE001
            logger.warning("welcome scan: cannot resolve pending chat_id=%s", chat_id)
            # Avoid infinite retry on unresolvable chats
            _mark_greeted(path, chat_id)
            continue
        title = getattr(entity, "title", None) or ""
        ok = await try_send_welcome_now(
            client, config, chat_id, title, my_id=my_id
        )
        if ok:
            sent += 1

    return sent


def register_welcome_handlers(
    client: TelegramClient, config: AppConfig, my_id: int
) -> None:
    """Join detection: mark pending + try immediate welcome; optional N-msg gate."""

    @client.on(events.ChatAction)
    async def _on_chat_action(event: events.ChatAction.Event) -> None:
        if not config.welcome_enabled:
            return
        added_me = False
        if event.user_added or event.created:
            user_ids = list(event.user_ids or [])
            if event.user_id:
                user_ids.append(event.user_id)
            if my_id in user_ids:
                added_me = True
        if getattr(event, "user_joined", False) and event.user_id == my_id:
            added_me = True
        if not added_me:
            return

        try:
            chat = await event.get_chat()
        except Exception:  # noqa: BLE001
            logger.exception("welcome: could not get chat from ChatAction")
            return
        title = getattr(chat, "title", None) or ""
        try:
            chat_id = utils.get_peer_id(chat)
        except Exception:  # noqa: BLE001
            chat_id = event.chat_id
        if chat_id is None:
            return

        chat_id_i = int(chat_id)
        if not is_pilot_chat(config, chat_id_i):
            return
        if not title_matches_project(title, config.welcome_name_keywords):
            logger.debug(
                "Welcome skip join (title mismatch) chat_id=%s title=%r",
                chat_id_i,
                title,
            )
            return

        path = _state_path(config)
        state = _load_state(path)
        if chat_id_i in _as_int_set(state.get("greeted_chat_ids")):
            return

        # Mark pending, then try immediate send (sample history → lang → EN fallback).
        _mark_pending(path, chat_id_i)
        min_n = _min_messages(config)
        logger.info(
            "Welcome join/create: pending + try send now (min_msgs=%d) "
            "chat_id=%s title=%r",
            min_n,
            chat_id_i,
            title,
        )
        await try_send_welcome_now(
            client, config, chat_id_i, title, my_id=my_id
        )

    @client.on(events.NewMessage)
    async def _on_message_for_pending(event: events.NewMessage.Event) -> None:
        if not config.welcome_enabled:
            return
        if event.is_private:
            return
        chat_id = event.chat_id
        if chat_id is None:
            return

        # Ignore our own messages; BD (and anyone else) can trigger language detection
        sender_id = None
        try:
            sender = await event.get_sender()
            sender_id = getattr(sender, "id", None)
        except Exception:  # noqa: BLE001
            pass
        if sender_id == my_id or getattr(event.message, "out", False):
            return

        path = _state_path(config)
        state = _load_state(path)
        pending = _as_int_set(state.get("pending_chat_ids"))
        greeted = _as_int_set(state.get("greeted_chat_ids"))
        if chat_id in greeted or chat_id not in pending:
            return

        text = (event.message.raw_text or event.message.message or "").strip()
        if len(text) < 1:
            return

        try:
            chat = await event.get_chat()
            title = getattr(chat, "title", None) or ""
        except Exception:  # noqa: BLE001
            title = ""

        # Recount from history so restarts / missed events stay accurate
        messages = await sample_group_messages(
            client, int(chat_id), exclude_user_id=my_id
        )
        # Ensure the triggering message is included (history lag / race)
        if text and (not messages or messages[0] != text):
            if text not in messages:
                messages = [text] + messages

        count = len(messages)
        _set_pending_count(path, int(chat_id), count)
        min_n = _min_messages(config)
        if min_n > 0 and count < min_n:
            logger.info(
                "Welcome pending (%d/%d non-bot messages) chat_id=%s title=%r",
                count,
                min_n,
                chat_id,
                title or "Delivery",
            )
            return

        await try_send_welcome_now(
            client,
            config,
            int(chat_id),
            title or "Delivery",
            my_id=my_id,
            sample_text=messages,
            known_count=count,
        )


async def welcome_scan_loop(
    client: TelegramClient,
    config: AppConfig,
    *,
    my_id: int | None = None,
) -> None:
    interval = max(int(config.welcome_scan_interval_minutes or 2), 1) * 60
    while True:
        await asyncio.sleep(interval)
        try:
            n = await scan_new_project_groups(client, config, my_id=my_id)
            if n:
                logger.info("Welcome scan sent %d greeting(s)", n)
        except Exception:
            logger.exception("Welcome scan failed")
