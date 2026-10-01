"""Automatically learn high-quality replies from configured trusted Telegram users."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path

from telethon.tl.custom.message import Message

from bot.learn import save_learned_content
from bot.workflow_events import append_event

logger = logging.getLogger(__name__)

_LOW_VALUE_RE = re.compile(
    r"^(?:ok(?:ay)?|yes|no|sure|thanks?|thank\s+you|got\s+it|done|"
    r"好(?:的)?|可以|收到|明白|谢谢|已处理|已完成|没问题)[.!\s。！]*$",
    re.IGNORECASE,
)
_SENSITIVE_RE = re.compile(
    r"(?:-----BEGIN [A-Z ]*PRIVATE KEY-----|"
    r"\b(?:seed phrase|mnemonic|private key|api[_ -]?secret|client[_ -]?secret)\b\s*[:=]|"
    r"\b(?:助记词|私钥|API\s*密钥|客户端密钥)\b\s*[:：])",
    re.IGNORECASE,
)


def is_trusted_sender(sender_id: int | None, username: str | None, config) -> bool:
    normalized = (username or "").strip().lstrip("@").lower()
    return (
        config.trusted_auto_learn_enabled
        and (
            (sender_id is not None and sender_id in config.trusted_auto_learn_user_ids)
            or (normalized and normalized in config.trusted_auto_learn_usernames)
        )
    )


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _quality_reason(answer: str, question: str, min_chars: int) -> str | None:
    clean_answer = _clean(answer)
    clean_question = _clean(question)
    if len(clean_answer) < max(min_chars, 10):
        return "answer_too_short"
    if len(clean_answer) > 3500:
        return "answer_too_long"
    if len(clean_question) < 3:
        return "missing_reply_context"
    if _LOW_VALUE_RE.fullmatch(clean_answer):
        return "low_value_reply"
    if _SENSITIVE_RE.search(clean_answer) or _SENSITIVE_RE.search(clean_question):
        return "sensitive_content"
    return None


def _state_path(config) -> Path:
    path = Path(config.trusted_auto_learn_state_file)
    if not path.is_absolute():
        path = Path(__file__).resolve().parent.parent / path
    return path


def _load_hashes(path: Path) -> set[str]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        values = raw.get("hashes", []) if isinstance(raw, dict) else []
        return {str(value) for value in values if value}
    except (OSError, json.JSONDecodeError, TypeError):
        return set()


def _save_hashes(path: Path, hashes: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # One month is the system retention window; cap the state as an extra guard.
    values = sorted(hashes)[-5000:]
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps({"hashes": values}, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


async def auto_learn_trusted_reply(
    message: Message,
    kb,
    config,
    *,
    chat_id: int,
    chat_title: str,
    sender_id: int | None,
    sender_username: str | None,
) -> bool:
    """Learn one trusted reply. Returns True only when a new entry was saved."""
    if not message.is_reply:
        logger.debug("Trusted auto-learn skipped: message is not a reply")
        return False

    replied = await message.get_reply_message()
    question = (replied.raw_text or "").strip() if replied else ""
    answer = (message.raw_text or "").strip()
    reason = _quality_reason(answer, question, config.trusted_auto_learn_min_chars)
    if reason:
        logger.info(
            "Trusted auto-learn skipped chat=%s sender=%s reason=%s",
            chat_id,
            sender_id,
            reason,
        )
        return False

    normalized = f"{_clean(question).lower()}\n{_clean(answer).lower()}"
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    state_path = _state_path(config)
    hashes = _load_hashes(state_path)
    if digest in hashes:
        logger.info("Trusted auto-learn duplicate skipped chat=%s hash=%s", chat_id, digest[:12])
        return False

    path = save_learned_content(
        answer,
        config.knowledge_dir,
        chat_id=chat_id,
        sender_id=sender_id,
        sender_username=sender_username,
        subdirectory=config.learn_subdirectory,
        related_question=question,
    )
    count = kb.reload()

    record_id = None
    if config.agent_kb_lark_sync_enabled:
        from bot.agent_kb_sync import sync_learned_file_to_lark

        record_id = sync_learned_file_to_lark(
            path.name,
            path.read_text(encoding="utf-8"),
            app_token=config.agent_kb_app_token,
            table_id=config.agent_kb_table_id,
        )

    hashes.add(digest)
    _save_hashes(state_path, hashes)
    append_event(
        "trusted_auto_learn",
        "telegram",
        project_name=chat_title,
        text=f"@{sender_username or sender_id} 的有效回复已加入自动学习并同步资料库",
        chat_id=chat_id,
        sender_id=sender_id,
        sender_username=sender_username or "",
        message_id=message.id,
        knowledge_file=path.name,
        lark_record_id=record_id,
    )
    logger.info(
        "Trusted auto-learn saved %s (chunks=%d, lark_record=%s)",
        path,
        count,
        record_id or "none",
    )
    return True
