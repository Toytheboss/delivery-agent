"""Workflow step 5→6: Lark status live → send Google Form to matched TG group.

Matching order:
1. Optional Lark field TG群ID (if present and valid)
2. Fuzzy match project name ↔ Delivery folder group titles
Manual fallback: group command sends the form in the current chat.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from bot.lark_bitable import get_tenant_access_token, list_records, update_record

if TYPE_CHECKING:
    from telethon import TelegramClient

    from bot.config_loader import AppConfig
    from bot.folder_scope import FolderScope

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent


def _load_state(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    sent = raw.get("sent_record_ids") or []
    return {str(x) for x in sent}


def _save_state(path: Path, sent: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"sent_record_ids": sorted(sent)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _field_text(fields: dict[str, Any], name: str) -> str:
    value = fields.get(name)
    if value is None:
        return ""
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("name") or item))
            else:
                parts.append(str(item))
        return " ".join(parts).strip()
    return str(value).strip()


def _parse_chat_id(raw: str) -> int | None:
    text = raw.strip().replace(" ", "")
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _normalize_name(text: str) -> str:
    text = str(text or "").lower().strip()
    # Project names often differ only by spaces, hyphens, slashes, or bracket
    # decoration (for example ``Aura AI`` vs ``Aura - AI``). Keep letters,
    # digits, and Unicode word characters; discard all punctuation so fuzzy
    # matching treats those display variants as the same project.
    return re.sub(r"[^\w]+", "", text, flags=re.UNICODE)


_MATCH_NOISE = {
    "botchain",
    "bot",
    "chain",
    "deployment",
    "group",
    "live",
    "testnet",
    "mainnet",
    "partnership",
    "communication",
    "wallet",
    "on",
    "the",
    "x",
    "grant",
    "program",
    "and",
    "of",
    "vs",
    "with",
    "for",
    "app",
    "web",
    "web3",
    "official",
    "community",
    "telegram",
    "dao",
    "fi",
    "labs",
    "lab",
    "pwa",
    "dapp",
    "oracle",
}
_CAMEL_SPLIT = re.compile(
    r"[A-Z]+(?=[A-Z][a-z])|[A-Z][a-z]+|[a-z]+|[A-Z]+|[0-9]+"
)
_MATCH_GENERIC_PROJECTS = {
    "test",
    "safe",
    "oracle",
    "wallet",
    "pass",
    "protocol",
    "chain",
    "bot",
    "ai",
    "di",
}


def _match_tokens(text: str) -> list[str]:
    """Split on separators and CamelCase (CloudChain → cloud, chain).

    Do not split when a fragment is shorter than 3 letters, so ``TaskOn``
    stays ``taskon`` instead of ``task`` + ``on``.
    """
    out: list[str] = []
    for chunk in re.findall(r"[a-zA-Z0-9]+", str(text or "")):
        parts = [part.lower() for part in _CAMEL_SPLIT.findall(chunk) if part]
        if not parts:
            out.append(chunk.lower())
        elif len(parts) >= 2 and any(len(part) < 3 or part in _MATCH_NOISE for part in parts):
            out.append(chunk.lower())
        else:
            out.extend(parts)
    return out


def _stem_token(token: str) -> str:
    if len(token) > 4 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def _tokens_equivalent(left: str, right: str) -> bool:
    if left == right:
        return True
    return _stem_token(left) == _stem_token(right)


def _token_covered_by_title(token: str, title_tokens: list[str], title_core: str) -> bool:
    return any(_tokens_equivalent(token, title_token) for title_token in title_tokens)


def _project_tokens_covered(project_tokens: list[str], title_tokens: list[str]) -> bool:
    if not project_tokens:
        return False
    if all(_token_covered_by_title(token, title_tokens, "") for token in project_tokens):
        return True
    if len(project_tokens) < 2:
        return False
    if not all(_token_covered_by_title(token, title_tokens, "") for token in project_tokens[:-1]):
        return False
    last = project_tokens[-1]
    return any(
        len(title_token) >= 3
        and len(last) - len(title_token) >= 2
        and last.startswith(title_token)
        for title_token in title_tokens
    )


def _contains_as_name(needle: str, haystack: str, title_tokens: list[str]) -> bool:
    """True if needle appears in haystack without being inside a longer word.

    ``botsea`` must not match ``botseal``; ``sent`` must not match ``consent``.
    ``botsea`` may still match ``botseapixeloptimus`` when ``pixel`` is a
    real title token after the needle.
    """
    if not needle or not haystack:
        return False
    start = 0
    while True:
        idx = haystack.find(needle, start)
        if idx < 0:
            return False
        prev = haystack[idx - 1] if idx > 0 else ""
        prefix_ok = idx == 0 or not prev.isalnum()
        rest = haystack[idx + len(needle) :]
        suffix_ok = (not rest or not rest[0].isalnum()) or any(
            rest.startswith(token) for token in title_tokens if len(token) >= 4
        )
        if prefix_ok and suffix_ok:
            if not rest or not rest[0].isalnum():
                return True
            if any(rest.startswith(token) for token in title_tokens if len(token) >= 4):
                return True
        start = idx + 1


def _meaningful_match_tokens(text: str) -> list[str]:
    return [token for token in _match_tokens(text) if token not in _MATCH_NOISE]


def _project_name_for_match(project: str) -> str:
    """Use the site slug when Lark stored a URL as the project name."""
    text = str(project or "").strip()
    if not re.match(r"^https?://", text, flags=re.I):
        return text
    host = re.sub(r"^https?://", "", text, flags=re.I).split("/", 1)[0].lower()
    if host.startswith("www."):
        host = host[4:]
    skip = {
        "vercel",
        "netlify",
        "github",
        "app",
        "io",
        "com",
        "xyz",
        "site",
        "online",
        "pages",
        "dev",
    }
    for label in host.split("."):
        if label and label not in skip:
            return label.replace("-", " ")
    return text


def _title_has_project_phrase(project: str, title: str) -> bool:
    """True when the project words appear as a contiguous phrase in the title."""
    proj = re.sub(r"[^a-z0-9]+", " ", str(project or "").lower()).strip()
    titl = re.sub(r"[^a-z0-9]+", " ", str(title or "").lower()).strip()
    if not proj or not titl:
        return False
    return f" {proj} " in f" {titl} "


def _prefer_chat_item(
    items: list[tuple[int, int, str, str]],
) -> tuple[int, int, str, str]:
    live = [item for item in items if str(item[1]).startswith("-100")]
    pool = live or items
    return min(pool, key=lambda item: item[1])


def _title_collapse_key(title: str) -> str:
    """Group duplicate chats without gluing different words together.

    ``BanshanBook&botchain`` and ``banshanbook&botchain`` collapse; ``Link Chain``
    and ``Linkchain`` stay distinct so Sudeep/Nicoley groups are not merged.
    """
    text = re.sub(r"\([^)]*\)", " ", str(title or ""))
    text = re.sub(r"[^a-z0-9]+", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def _collapse_migrated_chat_duplicates(
    candidates: list[tuple[int, int, str, str]],
) -> list[tuple[int, int, str, str]]:
    """Keep one chat per display title; prefer a migrated -100 group."""
    by_title: dict[str, list[tuple[int, int, str, str]]] = {}
    for item in candidates:
        by_title.setdefault(_title_collapse_key(item[2]), []).append(item)
    return [_prefer_chat_item(group) for group in by_title.values()]


def find_project_chat_matches(
    project_name: str,
    title_by_chat: dict[int, str],
) -> list[tuple[int, str, int, str]]:
    """Return best fuzzy TG title matches as (chat_id, title, score, reason)."""
    project = _project_name_for_match(str(project_name or "").strip())
    raw_project_tokens = _match_tokens(project)
    project_tokens = _meaningful_match_tokens(project) or raw_project_tokens
    project_token_set = set(project_tokens)
    project_norm = _normalize_name(project)
    project_core = "".join(raw_project_tokens) or "".join(project_tokens)
    if not project_core or len(project) < 2:
        return []
    if len(raw_project_tokens) == 1 and project_core in _MATCH_GENERIC_PROJECTS:
        return []

    candidates: list[tuple[int, int, str, str]] = []
    for chat_id, title in title_by_chat.items():
        title_text = str(title or "").strip()
        if not title_text:
            continue
        title_text = re.sub(r"\([^)]*\)", " ", title_text)
        title_norm = _normalize_name(title_text)
        title_tokens = _meaningful_match_tokens(title_text)
        title_core = "".join(title_tokens)
        if not title_tokens and not title_core:
            continue
        score = -1
        reason = ""

        if project_norm == title_norm:
            score, reason = 100, "exact title match"
        elif _title_has_project_phrase(project, title_text):
            score, reason = 98, "phrase match"
        elif project_norm and _contains_as_name(project_norm, title_norm, title_tokens):
            score, reason = 96, "title contains project"
        elif title_norm and _contains_as_name(title_norm, project_norm, project_tokens):
            score, reason = 94, "project contains title"

        if project_core and project_core == title_core:
            score, reason = max(score, 95), "core title match"
        elif project_core and len(project_core) >= 4 and _contains_as_name(project_core, title_core, title_tokens):
            score, reason = max(score, 90), "core title contains project"

        if project_tokens and _project_tokens_covered(project_tokens, title_tokens):
            score, reason = max(score, 92), "meaningful token match"

        if (
            len(project_tokens) == 1
            and len(project_tokens[0]) >= 3
            and project_tokens[0] not in _MATCH_GENERIC_PROJECTS
            and project_tokens[0] in title_tokens
        ):
            score, reason = max(score, 88), "single token match"

        if len(project_core) >= 5:
            for token in title_tokens:
                if (
                    len(token) >= 5
                    and token != project_core
                    and (
                        project_core.startswith(token)
                        or token.startswith(project_core)
                    )
                ):
                    extra_len = abs(len(token) - len(project_core))
                    if extra_len < 3:
                        continue
                    leftover = (
                        project_core[len(token) :]
                        if project_core.startswith(token)
                        else token[len(project_core) :]
                    )
                    if leftover and leftover not in title_core:
                        continue
                    extra_other = [
                        t
                        for t in title_tokens
                        if t != token and t not in project_token_set
                    ]
                    if extra_other:
                        continue
                    score, reason = max(score, 64), "compact alias match"
                    break

        extra_title = [
            t
            for t in title_tokens
            if t not in project_token_set
            and t not in _MATCH_NOISE
            and t not in _MATCH_GENERIC_PROJECTS
            and not any(_tokens_equivalent(t, p) for p in project_token_set)
            and t not in project_core
            and _stem_token(t) not in project_core
        ]
        weak_extra_title_reasons = {
            "title contains project",
            "core title contains project",
            "meaningful token match",
            "single token match",
            "leading project token match",
        }
        if (
            extra_title
            and reason in weak_extra_title_reasons
            and project_core != title_core
            and project_norm != title_norm
            and (
                reason == "leading project token match"
                or (
                    len(project_tokens) == 1
                    and len(project_tokens[0]) < 6
                )
            )
        ):
            # Short Lark names must not bind a longer distinct product group.
            # "Space" → "BOT Chain | Space Runners" used to score 96.
            # Leading-token-only hits with leftover product words are also skipped.
            score, reason = -1, ""

        if score >= 0:
            candidates.append((score, int(chat_id), title_text, reason))

    if not candidates:
        return []
    candidates = _collapse_migrated_chat_duplicates(candidates)
    best = max(item[0] for item in candidates)
    top = [item for item in candidates if item[0] == best]
    if len(top) > 1:
        phrase_hits = [
            item
            for item in top
            if item[3] == "phrase match" or _title_has_project_phrase(project, item[2])
        ]
        if len(phrase_hits) == 1:
            top = phrase_hits
        else:
            core_hits = [
                item
                for item in top
                if "".join(
                    _meaningful_match_tokens(re.sub(r"\([^)]*\)", " ", item[2]))
                )
                == project_core
            ]
            if len(core_hits) == 1:
                top = core_hits
            elif len(core_hits) == len(top) and len(top) > 1:
                top = [_prefer_chat_item(top)]
    top.sort(key=lambda item: (item[2].lower(), item[1]))
    return [(chat_id, title, score, reason) for score, chat_id, title, reason in top]


_DEFAULT_FORM_TEMPLATE = (
    "🎉 Congratulations! {project_name} is now live on BOT Chain Mainnet.\n\n"
    "Please submit your project info in this form. We will use it for "
    "website showcase / future gas rebates / potential grant support:\n"
    "{form_url}\n\n"
    "---\n"
    "Could you also coordinate a PR announcement on Twitter, mention that "
    "your project is live on BOT Chain. We will help to amplify.\n\n"
    "---\n"
    "You can also have your project displayed on DeFiLlama under the "
    "BOT Chain section if you want. Here's how:\n"
    "https://docs.google.com/document/d/1BXDfXq5KwpCi-A4eEO7ngE-a40uz3OM1/"
    "edit?usp=sharing&ouid=116519297133280129218&rtpof=true&sd=true\n\n"
    "Thanks for your support ❤️"
)


def build_form_message(config: AppConfig, project_name: str) -> str:
    template = config.workflow_message_template.strip() or _DEFAULT_FORM_TEMPLATE
    return template.format(
        form_url=config.workflow_google_form_url,
        project_name=project_name or "your project",
    )


def build_form_messages(config: AppConfig, project_name: str) -> list[str]:
    """Split the live form template on --- into Telegram bubbles."""
    from bot.rag import split_reply_bubbles

    text = build_form_message(config, project_name)
    bubbles = split_reply_bubbles(text)
    return bubbles or [text]


async def send_form_messages(
    client: TelegramClient,
    config: AppConfig,
    chat_id: int,
    project_name: str,
) -> int:
    """Send live-form bubbles with a pause between them (default 10s)."""
    bubbles = build_form_messages(config, project_name)
    gap = max(
        0, int(getattr(config, "workflow_form_message_gap_seconds", 10) or 0)
    )
    sent = 0
    for i, bubble in enumerate(bubbles):
        if i > 0 and gap > 0:
            await asyncio.sleep(gap)
        await client.send_message(chat_id, bubble)
        sent += 1
    logger.info(
        "form bubbles sent chat_id=%s project=%r count=%d gap=%ss",
        chat_id,
        project_name,
        sent,
        gap,
    )
    return sent


def _chat_ids_already_sent_form(config: Any) -> set[int]:
    """Chat IDs that already received a live/form message (from chase tracking)."""
    rel = str(
        getattr(config, "workflow_form_chase_state_file", "data/form_chase_state.json")
        or "data/form_chase_state.json"
    )
    path = ROOT / rel
    if not path.exists():
        return set()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    out: set[int] = set()
    for meta in (raw.get("projects") or {}).values():
        if not isinstance(meta, dict):
            continue
        try:
            out.add(int(meta.get("chat_id")))
        except (TypeError, ValueError):
            continue
    return out


def match_project_to_chat(
    project_name: str,
    title_by_chat: dict[int, str],
) -> tuple[int | None, str]:
    """Return (chat_id, reason). chat_id is None when unmatched or ambiguous."""
    candidates = find_project_chat_matches(project_name, title_by_chat)
    if not candidates:
        return None, "no fuzzy title match"
    if len(candidates) > 1:
        ids = [chat_id for chat_id, _, _, _ in candidates]
        return None, f"ambiguous title matches: {ids}"
    chat_id, _, _, reason = candidates[0]
    return chat_id, reason


async def build_folder_title_map(
    client: TelegramClient,
    chat_ids: set[int],
    *,
    force_refresh: bool = False,
) -> dict[int, str]:
    """Map chat_id → title with disk+memory cache.

    Avoids resolving ~N groups on every form/wallet poll (main flood source).
    Missing IDs are paced via get_entity; known titles are reused.
    """
    import json
    import time
    from pathlib import Path

    from bot.tg_rate_limit import paced_get_entity, tg_heavy_section

    root = Path(__file__).resolve().parent.parent
    cache_path = root / "data" / "folder_title_cache.json"
    ttl_s = 6 * 3600  # 6h — titles rarely change
    now = time.time()

    cache: dict[str, dict] = {}
    if cache_path.exists() and not force_refresh:
        try:
            raw = json.loads(cache_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                cache = raw.get("titles") if isinstance(raw.get("titles"), dict) else raw
        except (OSError, json.JSONDecodeError):
            cache = {}

    title_by_chat: dict[int, str] = {}
    missing: list[int] = []
    for chat_id in chat_ids:
        key = str(chat_id)
        entry = cache.get(key)
        if isinstance(entry, dict):
            title = str(entry.get("title") or "").strip()
            ts = float(entry.get("ts") or 0)
            if title and (force_refresh is False) and (now - ts) < ttl_s:
                title_by_chat[chat_id] = title
                continue
        elif isinstance(entry, str) and entry.strip():
            title_by_chat[chat_id] = entry.strip()
            continue
        missing.append(chat_id)

    if missing:
        logger.info(
            "Title cache: resolve %d/%d chat(s) via get_entity",
            len(missing),
            len(chat_ids),
        )
        async with tg_heavy_section():
            for chat_id in missing:
                try:
                    entity = await paced_get_entity(client, chat_id)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Could not resolve chat_id=%s: %s", chat_id, exc)
                    continue
                title = getattr(entity, "title", None)
                if title:
                    title_by_chat[chat_id] = str(title)
                    cache[str(chat_id)] = {"title": str(title), "ts": now}

        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            # Drop entries not in current folder set to keep file small
            keep = {str(cid) for cid in chat_ids}
            pruned = {k: v for k, v in cache.items() if k in keep}
            # merge freshly resolved
            for cid, title in title_by_chat.items():
                pruned[str(cid)] = {"title": title, "ts": now}
            cache_path.write_text(
                json.dumps({"titles": pruned}, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError:
            logger.exception("Failed to persist folder title cache")

    return title_by_chat


def remember_chat_title(chat_id: int, title: str) -> None:
    """Update title cache when we already know the title (join / auto-add)."""
    import json
    import time
    from pathlib import Path

    title = (title or "").strip()
    if not title:
        return
    root = Path(__file__).resolve().parent.parent
    cache_path = root / "data" / "folder_title_cache.json"
    cache: dict[str, dict] = {}
    if cache_path.exists():
        try:
            raw = json.loads(cache_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                cache = raw.get("titles") if isinstance(raw.get("titles"), dict) else {}
                if not isinstance(cache, dict):
                    cache = {}
        except (OSError, json.JSONDecodeError):
            cache = {}
    cache[str(chat_id)] = {"title": title, "ts": time.time()}
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps({"titles": cache}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError:
        logger.exception("Failed to update folder title cache")


def is_manual_form_command(text: str, commands: list[str]) -> bool:
    cleaned = (text or "").strip().lower()
    if not cleaned:
        return False
    for cmd in commands:
        c = cmd.strip().lower()
        if c and cleaned == c:
            return True
    return False


async def _mark_sent_in_lark(
    loop: asyncio.AbstractEventLoop,
    token: str,
    config: AppConfig,
    record_id: str,
) -> None:
    if not config.workflow_form_sent_field:
        return
    try:
        await loop.run_in_executor(
            None,
            update_record,
            token,
            config.workflow_base_app_token,
            config.workflow_progress_table_id,
            record_id,
            {config.workflow_form_sent_field: "已发送"},
        )
    except Exception:
        logger.exception(
            "Form sent but failed to mark Lark field %s on %s",
            config.workflow_form_sent_field,
            record_id,
        )


async def run_form_dispatch_once(
    client: TelegramClient,
    config: AppConfig,
    scope: FolderScope,
) -> int:
    """Scan progress table and send Google Form to matched TG groups. Returns sent count."""
    if not config.workflow_enabled:
        return 0
    if not config.workflow_google_form_url:
        logger.warning("workflow.enabled but google_form_url is empty; skip")
        return 0

    app_id = os.getenv("LARK_APP_ID", "").strip()
    app_secret = os.getenv("LARK_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        logger.warning("workflow skipped: missing LARK_APP_ID / LARK_APP_SECRET")
        return 0

    if not scope.chat_ids:
        await scope.refresh()

    title_by_chat = await build_folder_title_map(client, scope.chat_ids)
    if not title_by_chat:
        logger.warning("workflow: no resolvable group titles in folder %r", config.folder_name)

    loop = asyncio.get_running_loop()
    token = await loop.run_in_executor(None, get_tenant_access_token, app_id, app_secret)
    records = await loop.run_in_executor(
        None,
        list_records,
        token,
        config.workflow_base_app_token,
        config.workflow_progress_table_id,
    )

    state_path = ROOT / config.workflow_state_file
    sent = _load_state(state_path)
    sent_now = 0
    state_dirty = False
    already_sent_chats = _chat_ids_already_sent_form(config)

    # First run: mark all currently-live rows as already handled (no spam)
    if config.workflow_baseline_existing_live and not state_path.exists():
        for record in records:
            record_id = str(record.get("record_id") or "")
            fields = record.get("fields") or {}
            status = _field_text(fields, config.workflow_status_field)
            if record_id and status == config.workflow_trigger_status:
                sent.add(record_id)
        _save_state(state_path, sent)
        logger.info(
            "Workflow baseline: marked %d existing live project(s) as already handled",
            len(sent),
        )
        return 0

    for record in records:
        record_id = str(record.get("record_id") or "")
        if not record_id or record_id in sent:
            continue

        fields = record.get("fields") or {}
        status = _field_text(fields, config.workflow_status_field)
        if status != config.workflow_trigger_status:
            continue

        if config.workflow_form_sent_field:
            already = _field_text(fields, config.workflow_form_sent_field).lower()
            if already in {"true", "yes", "1", "是", "已发送"}:
                sent.add(record_id)
                state_dirty = True
                try:
                    from bot.metrics import record_form_outcome

                    record_form_outcome("already_sent")
                except Exception:  # noqa: BLE001
                    pass
                continue

        project_name = _field_text(fields, config.workflow_project_name_field)
        chat_id: int | None = None
        match_reason = ""

        if config.workflow_tg_chat_id_field:
            chat_raw = _field_text(fields, config.workflow_tg_chat_id_field)
            chat_id = _parse_chat_id(chat_raw)
            if chat_id is not None:
                match_reason = "lark TG群ID field"

        if chat_id is None:
            chat_id, match_reason = match_project_to_chat(project_name, title_by_chat)

        if chat_id is None:
            logger.warning(
                "Skip live project %r (%s): %s — use manual command in TG group",
                project_name,
                record_id,
                match_reason,
            )
            try:
                from bot.metrics import record_form_outcome

                record_form_outcome(f"no_group:{match_reason}")
            except Exception:  # noqa: BLE001
                pass
            continue

        if chat_id in already_sent_chats:
            sent.add(record_id)
            state_dirty = True
            logger.info(
                "Skip live project %r (%s): form already sent to chat_id=%s",
                project_name,
                record_id,
                chat_id,
            )
            continue

        try:
            await send_form_messages(client, config, chat_id, project_name)
        except Exception as exc:
            logger.exception(
                "Failed to send Google Form to chat_id=%s project=%r",
                chat_id,
                project_name,
            )
            try:
                from bot.metrics import record_form_outcome

                record_form_outcome(f"send_failed:{exc}")
            except Exception:  # noqa: BLE001
                pass
            continue

        sent.add(record_id)
        sent_now += 1
        state_dirty = True
        already_sent_chats.add(chat_id)
        try:
            from bot.metrics import record_form_outcome

            record_form_outcome("sent")
        except Exception:  # noqa: BLE001
            pass
        try:
            from bot.workflow_form_chase import note_form_sent

            note_form_sent(
                config,
                record_id=record_id,
                project_name=project_name,
                chat_id=chat_id,
                source="form_dispatch",
            )
        except Exception:  # noqa: BLE001
            logger.exception("form-chase note failed for %r", project_name)
        logger.info(
            "Sent Google Form to chat_id=%s project=%r record=%s via %s",
            chat_id,
            project_name,
            record_id,
            match_reason,
        )
        await _mark_sent_in_lark(loop, token, config, record_id)

    if state_dirty or not state_path.exists():
        _save_state(state_path, sent)

    return sent_now


async def send_form_manual(
    client: TelegramClient,
    config: AppConfig,
    chat_id: int,
    chat_title: str,
) -> str:
    """Manual fallback: send form in current group; try to mark matching Lark row."""
    if not config.workflow_google_form_url:
        return "Google form URL is not configured (workflow.google_form_url)."

    project_guess = chat_title or "your project"
    await send_form_messages(client, config, chat_id, project_guess)
    try:
        from bot.metrics import record_form_outcome

        record_form_outcome("sent")
    except Exception:  # noqa: BLE001
        pass

    # Best-effort: mark matching live Lark record as sent
    app_id = os.getenv("LARK_APP_ID", "").strip()
    app_secret = os.getenv("LARK_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        return f"Form sent in this group. (Could not update Lark: missing credentials)"

    loop = asyncio.get_running_loop()
    try:
        token = await loop.run_in_executor(None, get_tenant_access_token, app_id, app_secret)
        records = await loop.run_in_executor(
            None,
            list_records,
            token,
            config.workflow_base_app_token,
            config.workflow_progress_table_id,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Manual form sent but Lark lookup failed")
        return f"Form sent. Lark lookup failed: {exc}"

    state_path = ROOT / config.workflow_state_file
    sent = _load_state(state_path)
    title_map = {chat_id: chat_title}
    matched_id = ""

    for record in records:
        record_id = str(record.get("record_id") or "")
        fields = record.get("fields") or {}
        project_name = _field_text(fields, config.workflow_project_name_field)
        matched, reason = match_project_to_chat(project_name, title_map)
        if matched != chat_id:
            continue
        # Prefer live status, but still mark if unique title match
        status = _field_text(fields, config.workflow_status_field)
        matched_id = record_id
        sent.add(record_id)
        await _mark_sent_in_lark(loop, token, config, record_id)
        try:
            from bot.workflow_form_chase import note_form_sent

            note_form_sent(
                config,
                record_id=record_id,
                project_name=project_name,
                chat_id=chat_id,
                source="manual",
            )
        except Exception:  # noqa: BLE001
            logger.exception("form-chase note failed for manual %r", project_name)
        logger.info(
            "Manual form linked to Lark record=%s project=%r (%s, status=%r)",
            record_id,
            project_name,
            reason,
            status,
        )
        break

    _save_state(state_path, sent)
    if matched_id:
        return f"Form sent. Linked Lark record {matched_id}."
    return "Form sent. No unique Lark project matched this group title."


async def form_dispatch_loop(
    client: TelegramClient,
    config: AppConfig,
    scope: FolderScope,
) -> None:
    interval = max(config.workflow_poll_interval_minutes, 1) * 60
    while True:
        try:
            from bot.metrics import inc

            inc("poll_cycles_run")
            n = await run_form_dispatch_once(client, config, scope)
            if n:
                logger.info("Form dispatch cycle sent %d message(s)", n)
        except Exception:
            logger.exception("Form dispatch cycle failed")
        await asyncio.sleep(interval)
