"""Allowlisted runtime settings + knowledge learn helpers for the dashboard UI."""

from __future__ import annotations

import logging
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from bot.learn import save_learned_content

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent
OVERRIDES_PATH = ROOT / "data" / "runtime_overrides.yaml"

# dot-path → (AppConfig attr, yaml section path for persistence, type)
# Only these keys are exposed to the settings panel.
SETTING_SPECS: dict[str, dict[str, Any]] = {
    "scope.group_replies_enabled": {
        "attr": "group_replies_enabled",
        "type": "bool",
        "label": "群内自动回复",
    },
    "scope.pilot_enabled": {
        "attr": "pilot_enabled",
        "type": "bool",
        "label": "仅试点群回复",
    },
    "trigger.require_mention_or_question": {
        "attr": "require_mention_or_question",
        "type": "bool",
        "label": "需 @ 或像提问",
    },
    "trigger.hint_keywords": {
        "attr": "hint_keywords",
        "type": "str_list",
        "label": "提示关键词",
    },
    "reply.rate_limit_seconds": {
        "attr": "rate_limit_seconds",
        "type": "int",
        "label": "回复频控（秒）",
    },
    "reply.reply_delay_seconds": {
        "attr": "reply_delay_seconds",
        "type": "int",
        "label": "回复延迟（秒）",
    },
    "reply.bubble_gap_seconds": {
        "attr": "bubble_gap_seconds",
        "type": "int",
        "label": "气泡间隔（秒）",
    },
    "reply.min_relevance_score": {
        "attr": "min_relevance_score",
        "type": "float",
        "label": "最低相关度",
    },
    "reply.language": {
        "attr": "reply_language",
        "type": "str",
        "label": "回复语言",
    },
    "reply.footer_enabled": {
        "attr": "reply_footer_enabled",
        "type": "bool",
        "label": "FAQ 页脚",
    },
    "learn.enabled": {
        "attr": "learn_enabled",
        "type": "bool",
        "label": "知识学习开关",
    },
    "learn.trigger_word": {
        "attr": "learn_trigger_word",
        "type": "str",
        "label": "学习触发词",
    },
    "learn.min_chars": {
        "attr": "learn_min_chars",
        "type": "int",
        "label": "学习最短字数",
    },
    "learn.scopes.qa_test_groups": {
        "attr": "learn_scope_qa_groups",
        "type": "bool",
        "label": "学习·QA 测试群",
    },
    "learn.scopes.qa_testers": {
        "attr": "learn_scope_qa_testers",
        "type": "bool",
        "label": "学习·QA 账号",
    },
    "learn.scopes.project_folder": {
        "attr": "learn_scope_project_folder",
        "type": "bool",
        "label": "学习·项目 Folder",
    },
    "learn.agent_kb.enabled": {
        "attr": "agent_kb_lark_sync_enabled",
        "type": "bool",
        "label": "学习同步飞书词条",
    },
    "knowledge.chunk_size": {
        "attr": "chunk_size",
        "type": "int",
        "label": "知识分块大小",
    },
    "knowledge.chunk_overlap": {
        "attr": "chunk_overlap",
        "type": "int",
        "label": "分块重叠",
    },
    "knowledge.top_k": {
        "attr": "top_k",
        "type": "int",
        "label": "检索 top_k",
    },
    "welcome.enabled": {
        "attr": "welcome_enabled",
        "type": "bool",
        "label": "欢迎语开关",
    },
    "welcome.name_keywords": {
        "attr": "welcome_name_keywords",
        "type": "str_list",
        "label": "欢迎语标题关键词",
    },
    "welcome.min_messages_before_welcome": {
        "attr": "welcome_min_messages_before_welcome",
        "type": "int",
        "label": "欢迎前最少消息数",
    },
    "workflow.logo_fill_enabled": {
        "attr": "workflow_logo_fill_enabled",
        "type": "bool",
        "label": "Logo 自动抓取",
    },
    "workflow.mark_live_also_send_form": {
        "attr": "workflow_mark_live_also_send_form",
        "type": "bool",
        "label": "上线时同时发表单",
    },
    "workflow.form_chase_enabled": {
        "attr": "workflow_form_chase_enabled",
        "type": "bool",
        "label": "表单催收",
    },
    "workflow.form_chase_after_hours": {
        "attr": "workflow_form_chase_after_hours",
        "type": "float",
        "label": "催收等待小时",
    },
    "workflow.form_chase_min_filled": {
        "attr": "workflow_form_chase_min_filled",
        "type": "int",
        "label": "催收最少已填项",
    },
    "workflow.form_chase_max_reminders": {
        "attr": "workflow_form_chase_max_reminders",
        "type": "int",
        "label": "催收最多次数",
    },
    "workflow.wallet_notify_enabled": {
        "attr": "workflow_wallet_notify_enabled",
        "type": "bool",
        "label": "钱包通知 TG",
    },
    "workflow.lark_digest_enabled": {
        "attr": "workflow_lark_digest_enabled",
        "type": "bool",
        "label": "飞书钱包日报",
    },
    "workflow.lark_digest_hour": {
        "attr": "workflow_lark_digest_hour",
        "type": "int",
        "label": "飞书日报小时（上海）",
    },
    "metrics.message_log_enabled": {
        "attr": "metrics_message_log_enabled",
        "type": "bool",
        "label": "消息明细日志",
    },
    "metrics.message_log_retain_days": {
        "attr": "metrics_message_log_retain_days",
        "type": "int",
        "label": "消息日志保留天数",
    },
    "safety.blocked_topics": {
        "attr": "blocked_topics",
        "type": "str_list",
        "label": "屏蔽话题",
    },
    "rules": {
        "attr": "reply_rules",
        "type": "str_list",
        "label": "回复规则",
    },
}


def _deep_set(root: dict[str, Any], dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    cur: dict[str, Any] = root
    for p in parts[:-1]:
        nxt = cur.get(p)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[p] = nxt
        cur = nxt
    cur[parts[-1]] = value


def _coerce(value: Any, typ: str) -> Any:
    if typ == "bool":
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on"}
    if typ == "int":
        return int(value)
    if typ == "float":
        return float(value)
    if typ == "str":
        return str(value).strip()
    if typ == "str_list":
        if isinstance(value, list):
            return [str(x).strip() for x in value if str(x).strip()]
        text = str(value or "")
        parts = re.split(r"[\n,]+", text)
        return [p.strip() for p in parts if p.strip()]
    return value


def load_overrides() -> dict[str, Any]:
    if not OVERRIDES_PATH.exists():
        return {}
    try:
        raw = yaml.safe_load(OVERRIDES_PATH.read_text(encoding="utf-8")) or {}
        return raw if isinstance(raw, dict) else {}
    except Exception:  # noqa: BLE001
        logger.exception("failed loading runtime overrides")
        return {}


def save_overrides(data: dict[str, Any]) -> None:
    OVERRIDES_PATH.parent.mkdir(parents=True, exist_ok=True)
    if OVERRIDES_PATH.exists():
        shutil.copy2(OVERRIDES_PATH, OVERRIDES_PATH.with_suffix(".yaml.bak"))
    OVERRIDES_PATH.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in (overlay or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def get_settings_view(config: Any) -> dict[str, Any]:
    fields = []
    values: dict[str, Any] = {}
    for key, spec in SETTING_SPECS.items():
        attr = spec["attr"]
        cur = getattr(config, attr, None)
        if spec["type"] == "str_list" and isinstance(cur, (set, tuple)):
            cur = sorted(str(x) for x in cur)
        values[key] = cur
        fields.append(
            {
                "key": key,
                "label": spec["label"],
                "type": spec["type"],
                "value": cur,
            }
        )
    return {
        "fields": fields,
        "values": values,
        "overrides_path": str(OVERRIDES_PATH.relative_to(ROOT)),
    }


def apply_settings_to_config(config: Any, updates: dict[str, Any]) -> list[str]:
    """Mutate live AppConfig + persist overrides. Returns applied keys."""
    applied: list[str] = []
    overrides = load_overrides()
    for key, raw in (updates or {}).items():
        spec = SETTING_SPECS.get(key)
        if not spec:
            continue
        try:
            value = _coerce(raw, spec["type"])
        except (TypeError, ValueError) as exc:
            logger.warning("skip setting %s: %s", key, exc)
            continue
        setattr(config, spec["attr"], value)
        _deep_set(overrides, key, value)
        applied.append(key)
        if key == "metrics.message_log_retain_days":
            try:
                from bot.message_log import configure as configure_message_log

                configure_message_log(
                    enabled=bool(getattr(config, "metrics_message_log_enabled", True)),
                    log_dir=getattr(config, "metrics_message_log_dir", "data/message_logs"),
                    retain_days=int(value),
                    text_max=getattr(config, "metrics_message_log_text_max", 500),
                )
            except Exception:  # noqa: BLE001
                logger.exception("reconfigure message_log failed")
        if key == "metrics.message_log_enabled":
            try:
                from bot.message_log import configure as configure_message_log

                configure_message_log(
                    enabled=bool(value),
                    log_dir=getattr(config, "metrics_message_log_dir", "data/message_logs"),
                    retain_days=getattr(config, "metrics_message_log_retain_days", 60),
                    text_max=getattr(config, "metrics_message_log_text_max", 500),
                )
            except Exception:  # noqa: BLE001
                logger.exception("reconfigure message_log failed")
    if applied:
        save_overrides(overrides)
    return applied


def list_learned(config: Any, *, limit: int = 80) -> list[dict[str, Any]]:
    knowledge_dir = Path(getattr(config, "knowledge_dir", ROOT / "knowledge"))
    sub = str(getattr(config, "learn_subdirectory", "learned") or "learned")
    learned_dir = knowledge_dir / sub
    if not learned_dir.is_dir():
        return []
    files = sorted(learned_dir.glob("learned_*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    out: list[dict[str, Any]] = []
    for path in files[: max(int(limit), 1)]:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        preview = re.sub(r"<!--.*?-->", "", text, flags=re.S).strip()[:240]
        out.append(
            {
                "name": path.name,
                "mtime": datetime.fromtimestamp(path.stat().st_mtime).isoformat(
                    timespec="seconds"
                ),
                "chars": len(text),
                "preview": preview,
            }
        )
    return out


def create_learned_note(
    config: Any,
    *,
    content: str,
    related_question: str = "",
    sync_lark: bool = False,
) -> dict[str, Any]:
    body = (content or "").strip()
    if len(body) < int(getattr(config, "learn_min_chars", 5) or 5):
        raise ValueError("content too short")
    knowledge_dir = Path(getattr(config, "knowledge_dir", ROOT / "knowledge"))
    sub = str(getattr(config, "learn_subdirectory", "learned") or "learned")
    path = save_learned_content(
        body,
        knowledge_dir,
        chat_id=0,
        sender_id=None,
        sender_username="dashboard",
        subdirectory=sub,
        related_question=(related_question or "").strip() or None,
    )
    record_id = None
    if sync_lark and getattr(config, "agent_kb_lark_sync_enabled", False):
        try:
            from bot.agent_kb_sync import sync_learned_file_to_lark

            body_text = path.read_text(encoding="utf-8")
            record_id = sync_learned_file_to_lark(
                path.name,
                body_text,
                app_token=getattr(config, "agent_kb_app_token", ""),
                table_id=getattr(config, "agent_kb_table_id", ""),
            )
        except Exception:  # noqa: BLE001
            logger.exception("dashboard learn: lark sync failed")
    try:
        from bot.metrics import inc

        inc("absorb_learn_success")
        if record_id:
            inc("agent_kb_lark_sync_success")
    except Exception:  # noqa: BLE001
        pass
    return {"name": path.name, "path": str(path.relative_to(ROOT)), "lark_record_id": record_id}


def delete_learned_note(config: Any, name: str) -> bool:
    safe = Path(name).name
    if not safe.startswith("learned_") or not safe.endswith(".md"):
        raise ValueError("invalid learned filename")
    knowledge_dir = Path(getattr(config, "knowledge_dir", ROOT / "knowledge"))
    sub = str(getattr(config, "learn_subdirectory", "learned") or "learned")
    path = knowledge_dir / sub / safe
    if not path.is_file():
        return False
    path.unlink()
    return True
