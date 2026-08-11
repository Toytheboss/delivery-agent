"""Telegram message handler."""

from __future__ import annotations

import asyncio
import html
import logging
import time
from typing import TYPE_CHECKING

from telethon import events
from telethon.tl.custom.message import Message

from bot.config_loader import is_pilot_chat
from bot.learn import contains_learn_trigger, handle_learn, in_learn_scope
from bot.metrics import (
    build_daily_report,
    format_daily_report_zh,
    format_report_zh,
    format_stats_zh,
    inc,
    snapshot,
    write_report_file,
)
from bot.message_log import log_message_event
from bot.rag import generate_reply, split_reply_bubbles
from bot.triggers import (
    is_qa_tester,
    is_social_chitchat,
    is_whitelisted,
    is_workflow_operator,
    pick_social_reply,
    should_process,
)
from bot.workflow_form_dispatch import is_manual_form_command, send_form_manual
from bot.workflow_mark_live import is_mark_live_command, mark_live_from_group

_STATS_COMMANDS = frozenset({"/stats", "交付统计"})
_REPORT_COMMANDS = frozenset({"/report", "交付周报", "交付报告"})
_DAILY_REPORT_COMMANDS = frozenset(
    {
        "/daily",
        "/daily_report",
        "交付日报",
        "今日交付日报",
        "今日:交付日报:",
        "今日：交付日报：",
        "今日:交付日报",
        "今日：交付日报",
    }
)


def _is_daily_report_command(text: str) -> bool:
    """Exact match + tolerate extra spaces around the colon form."""
    raw = (text or "").strip()
    if raw in _DAILY_REPORT_COMMANDS:
        return True
    compact = "".join(raw.split())
    return compact in {
        "今日:交付日报:",
        "今日：交付日报：",
        "今日:交付日报",
        "今日：交付日报",
        "交付日报",
        "今日交付日报",
    }

if TYPE_CHECKING:
    from telethon import TelegramClient

    from bot.config_loader import AppConfig
    from bot.folder_scope import FolderScope
    from bot.knowledge import KnowledgeBase

logger = logging.getLogger(__name__)

# HTML: entire footer bold+italic; @usernames stay plain so Telegram links them.
_FOOTER_PARSE_MODE = "html"


def _faq_footer_message(config: "AppConfig", language: str) -> str | None:
    if not config.reply_footer_enabled:
        return None
    raw = (
        config.reply_footer_en
        if (language or "").lower() == "en"
        else config.reply_footer_zh
    )
    text = (raw or "").strip()
    if not text:
        return None
    return f"<b><i>{html.escape(text)}</i></b>"


class MessageHandler:
    def __init__(
        self,
        client: TelegramClient,
        config: AppConfig,
        scope: FolderScope,
        kb: KnowledgeBase,
    ) -> None:
        self.client = client
        self.config = config
        self.scope = scope
        self.kb = kb
        self.my_id: int | None = None
        self.my_username: str | None = None
        self._last_reply: dict[tuple[int, int], float] = {}
        self._processing: set[int] = set()

    async def init_me(self) -> None:
        me = await self.client.get_me()
        self.my_id = me.id
        self.my_username = (me.username or "").lower() or None
        logger.info("Logged in as %s (id=%s)", me.username or me.first_name, me.id)

    def _is_rate_limited(self, chat_id: int, user_id: int) -> bool:
        key = (chat_id, user_id)
        last = self._last_reply.get(key, 0)
        return time.time() - last < self.config.rate_limit_seconds

    def _mark_replied(self, chat_id: int, user_id: int) -> None:
        self._last_reply[(chat_id, user_id)] = time.time()

    async def handle(self, event: events.NewMessage.Event) -> None:
        message: Message = event.message
        if not message:
            return
        if self.my_id is None:
            return

        chat_id = event.chat_id
        if chat_id is None:
            return

        if chat_id in self.config.ignored_group_ids:
            return

        sender = await event.get_sender()
        sender_id = getattr(sender, "id", None)
        sender_username = getattr(sender, "username", None)
        qa_tester = is_qa_tester(
            sender_id,
            sender_username,
            self.config.qa_tester_user_ids,
            self.config.qa_tester_usernames,
        )

        in_folder = (
            self.config.group_replies_enabled
            and self.scope.contains(chat_id)
            and is_pilot_chat(self.config, chat_id)
        )
        in_project_folder = self.scope.contains(chat_id)
        in_qa_private = qa_tester and event.is_private
        in_qa_group = chat_id in self.config.qa_test_group_ids
        qa_mode = qa_tester or in_qa_group
        # QA test groups still work even outside pilot list
        in_reply_scope = in_folder or in_qa_private or in_qa_group

        text = (message.raw_text or "").strip()
        has_learn_trigger = self.config.learn_enabled and contains_learn_trigger(
            text, self.config.learn_trigger_word
        )
        workflow_op = is_workflow_operator(
            sender_id,
            sender_username,
            self.config.workflow_operator_user_ids,
            self.config.workflow_operator_usernames,
        )
        is_mark_live = is_mark_live_command(
            text, self.config.workflow_mark_live_commands
        )
        is_form_cmd = is_manual_form_command(
            text, self.config.workflow_manual_commands
        )
        is_stats_cmd = text in _STATS_COMMANDS
        is_report_cmd = text in _REPORT_COMMANDS
        is_daily_cmd = _is_daily_report_command(text)
        delivery_account = bool(message.out) or (
            self.my_id is not None and sender_id == self.my_id
        )
        can_ops = qa_tester or delivery_account or workflow_op

        # Operator stats / exec report / daily report
        if (is_stats_cmd or is_report_cmd or is_daily_cmd) and can_ops:
            msg_id = message.id
            if msg_id in self._processing:
                return
            self._processing.add(msg_id)
            try:
                loop = asyncio.get_running_loop()
                if is_daily_cmd:
                    # Refresh wallet first_seen so "今日新收集" includes latest rows.
                    try:
                        from bot.workflow_lark_wallet_group import sync_wallet_first_seen

                        await sync_wallet_first_seen(self.config)
                    except Exception:  # noqa: BLE001
                        logger.exception("Daily report: wallet first_seen sync failed")
                    daily = await loop.run_in_executor(
                        None, lambda: build_daily_report(self.config)
                    )
                    await message.reply(format_daily_report_zh(daily))
                else:
                    snap = await loop.run_in_executor(
                        None, lambda: snapshot(self.config, include_lark=True)
                    )
                    if is_report_cmd:
                        report = format_report_zh(snap)
                        await loop.run_in_executor(None, lambda: write_report_file(snap))
                        await message.reply(report)
                    else:
                        await message.reply(format_stats_zh(snap))
            except Exception:
                logger.exception("Stats/report command failed in chat %s", chat_id)
                await message.reply("统计生成失败，请查看日志。")
            finally:
                self._processing.discard(msg_id)
            return

        # BD blacklist: never auto-respond, except workflow operators on mark-live/form
        if (
            not message.out
            and is_whitelisted(
                sender_id,
                sender_username,
                self.config.ignore_user_ids,
                self.config.ignore_usernames,
            )
            and not (workflow_op and (is_mark_live or is_form_cmd))
        ):
            logger.debug(
                "Skip BD/blacklist sender %s (@%s) in chat %s",
                sender_id,
                sender_username,
                chat_id,
            )
            return

        # Workflow: keyword in any group → mark Lark status live (+ optional form)
        # Operators / delivery / QA do not require Delivery folder membership.
        if (
            self.config.workflow_enabled
            and not event.is_private
            and is_mark_live
        ):
            # Delivery account, QA testers, or configured workflow operators
            if not can_ops:
                logger.info(
                    "Mark-live ignored from non-operator chat=%s sender=%s",
                    chat_id,
                    sender_id,
                )
                return

            msg_id = message.id
            if msg_id in self._processing:
                return
            self._processing.add(msg_id)
            try:
                chat = await event.get_chat()
                title = getattr(chat, "title", None) or ""
                inc("mark_live_triggers")
                result = await mark_live_from_group(
                    self.client, self.config, chat_id, title
                )
                await message.reply(result)
            except Exception:
                logger.exception("Mark-live failed in chat %s", chat_id)
                await message.reply("Failed to update Lark status. Check logs.")
            finally:
                self._processing.discard(msg_id)
            return

        # Workflow manual fallback: send Google Form in current group (any group)
        if (
            self.config.workflow_enabled
            and not event.is_private
            and is_form_cmd
        ):
            if not can_ops:
                logger.info(
                    "Form command ignored from non-operator chat=%s sender=%s",
                    chat_id,
                    sender_id,
                )
                return

            msg_id = message.id
            if msg_id in self._processing:
                return
            self._processing.add(msg_id)
            try:
                chat = await event.get_chat()
                title = getattr(chat, "title", None) or ""
                inc("send_form_triggers")
                result = await send_form_manual(self.client, self.config, chat_id, title)
                await message.reply(result)
            except Exception:
                logger.exception("Manual form dispatch failed in chat %s", chat_id)
                await message.reply("Failed to send form. Check logs.")
            finally:
                self._processing.discard(msg_id)
            return

        if has_learn_trigger and in_learn_scope(
            chat_id, qa_tester, in_qa_group, in_project_folder, self.config
        ):
            # Delivery 项目群内仅 QA 测试账号可写入知识库
            if (
                in_project_folder
                and not in_qa_group
                and not event.is_private
                and not qa_tester
                and not message.out
            ):
                logger.info("Learn rejected: non-qa user in delivery group chat=%s", chat_id)
                return

            msg_id = message.id
            if msg_id in self._processing:
                return
            self._processing.add(msg_id)
            try:
                result = await handle_learn(
                    message,
                    self.kb,
                    self.config,
                    chat_id=chat_id,
                    sender_id=sender_id,
                    sender_username=sender_username,
                    owner_id=self.my_id,
                )
                if result.success or result.message != "no trigger":
                    await message.reply(result.message)
            except Exception:
                logger.exception("Learn failed in chat %s", chat_id)
            finally:
                self._processing.discard(msg_id)
            return

        if message.out:
            return

        if not in_reply_scope:
            return

        if is_whitelisted(
            sender_id,
            sender_username,
            self.config.ignore_user_ids,
            self.config.ignore_usernames,
        ) and not qa_mode:
            logger.debug("Skip whitelisted sender %s in chat %s", sender_id, chat_id)
            return

        # Social gm / X-post shares → short emoji reply (not FAQ)
        if is_social_chitchat(text):
            if sender_id is not None and not qa_mode and self._is_rate_limited(
                chat_id, sender_id
            ):
                logger.info(
                    "Rate limited social reply user %s in chat %s", sender_id, chat_id
                )
                return
            msg_id = message.id
            if msg_id in self._processing:
                return
            self._processing.add(msg_id)
            try:
                reply = pick_social_reply(
                    text, seed=(chat_id or 0) ^ (msg_id or 0)
                )
                delay = 0 if qa_mode else min(8, max(0, self.config.reply_delay_seconds))
                if delay > 0:
                    await asyncio.sleep(delay)
                await message.reply(reply)
                if sender_id is not None:
                    self._mark_replied(chat_id, sender_id)
                try:
                    inc("messages_processed")
                    inc("social_chitchat_replies")
                except Exception:  # noqa: BLE001
                    pass
                log_message_event(
                    kind="social",
                    chat_id=chat_id,
                    sender_id=sender_id,
                    sender_username=sender_username or "",
                    message_id=msg_id,
                    text=text,
                    reply_text=reply,
                    qa=qa_mode,
                    qa_group=in_qa_group,
                    outcome="replied",
                    reason="social_chitchat",
                )
                logger.info(
                    "Social chitchat reply in chat %s: %r", chat_id, reply
                )
            except Exception:
                logger.exception("Social chitchat reply failed in chat %s", chat_id)
                log_message_event(
                    kind="social",
                    chat_id=chat_id,
                    sender_id=sender_id,
                    sender_username=sender_username or "",
                    message_id=msg_id,
                    text=text,
                    qa=qa_mode,
                    qa_group=in_qa_group,
                    outcome="error",
                    reason="social_reply_failed",
                )
            finally:
                self._processing.discard(msg_id)
            return

        if not should_process(
            message,
            self.my_id,
            self.my_username,
            self.config.hint_keywords,
            self.config.require_mention_or_question,
            qa_tester=qa_mode,
        ):
            return

        if sender_id is not None and not qa_mode and self._is_rate_limited(chat_id, sender_id):
            logger.info("Rate limited user %s in chat %s", sender_id, chat_id)
            return

        msg_id = message.id
        if msg_id in self._processing:
            return
        self._processing.add(msg_id)

        question = text
        logger.info(
            "Processing chat=%s sender=%s (@%s) qa=%s qa_group=%s: %s",
            chat_id,
            sender_id,
            sender_username,
            qa_tester,
            in_qa_group,
            question[:120],
        )
        try:
            inc("messages_processed")
        except Exception:  # noqa: BLE001
            pass

        started_at = time.time()
        try:
            decision = await generate_reply(question, self.kb, self.config)
            if not decision.should_reply:
                # Fallback: if FAQ silenced a share/greeting that slipped through
                if is_social_chitchat(question):
                    reply = pick_social_reply(
                        question, seed=(chat_id or 0) ^ (msg_id or 0)
                    )
                    delay = 0 if qa_mode else min(
                        8, max(0, self.config.reply_delay_seconds)
                    )
                    if delay > 0:
                        await asyncio.sleep(delay)
                    await message.reply(reply)
                    if sender_id is not None:
                        self._mark_replied(chat_id, sender_id)
                    try:
                        inc("social_chitchat_replies")
                    except Exception:  # noqa: BLE001
                        pass
                    log_message_event(
                        kind="faq",
                        chat_id=chat_id,
                        sender_id=sender_id,
                        sender_username=sender_username or "",
                        message_id=msg_id,
                        text=question,
                        reply_text=reply,
                        qa=qa_tester,
                        qa_group=in_qa_group,
                        outcome="replied",
                        reason=f"social_fallback:{decision.reason}",
                        score=decision.best_score,
                    )
                    logger.info(
                        "Social fallback after FAQ silence (%s) in chat %s: %r",
                        decision.reason,
                        chat_id,
                        reply,
                    )
                    return
                log_message_event(
                    kind="faq",
                    chat_id=chat_id,
                    sender_id=sender_id,
                    sender_username=sender_username or "",
                    message_id=msg_id,
                    text=question,
                    qa=qa_tester,
                    qa_group=in_qa_group,
                    outcome="silent",
                    reason=decision.reason,
                    score=decision.best_score,
                )
                logger.info(
                    "No reply: %s (score=%.2f)", decision.reason, decision.best_score
                )
                return

            # 项目群：故意等待，避免秒回像机器人；QA 测试不延迟
            delay = 0 if qa_mode else max(0, self.config.reply_delay_seconds)
            if delay > 0:
                elapsed = time.time() - started_at
                wait = delay - elapsed
                if wait > 0:
                    logger.info(
                        "Delaying reply %.0fs in chat %s (target=%ss)",
                        wait,
                        chat_id,
                        delay,
                    )
                    await asyncio.sleep(wait)

            bubbles = split_reply_bubbles(decision.text)
            # First bubble as reply; follow-ups as separate short messages (more human)
            gap = 0 if qa_mode else max(0, self.config.bubble_gap_seconds)
            for i, bubble in enumerate(bubbles):
                if i == 0:
                    await message.reply(bubble)
                else:
                    if gap > 0:
                        logger.info(
                            "Delaying bubble %d/%d by %ss in chat %s",
                            i + 1,
                            len(bubbles),
                            gap,
                            chat_id,
                        )
                        await asyncio.sleep(gap)
                    await self.client.send_message(chat_id, bubble)

            # FAQ path only: one bold+italic disclaimer after successful auto-reply
            footer = _faq_footer_message(self.config, decision.language)
            if footer:
                if gap > 0 and bubbles:
                    await asyncio.sleep(gap)
                await self.client.send_message(
                    chat_id, footer, parse_mode=_FOOTER_PARSE_MODE
                )

            if sender_id is not None:
                self._mark_replied(chat_id, sender_id)
            # One FAQ reply session (not per-bubble); bubbles + footer counted too
            if bubbles:
                inc("faq_reply_sessions")
                inc("faq_bubbles_sent", len(bubbles))
            if footer:
                inc("faq_footer_sent")
            reply_joined = "\n---\n".join(bubbles) if bubbles else ""
            if footer:
                reply_joined = (
                    f"{reply_joined}\n---\n{footer}" if reply_joined else footer
                )
            log_message_event(
                kind="faq",
                chat_id=chat_id,
                sender_id=sender_id,
                sender_username=sender_username or "",
                message_id=msg_id,
                text=question,
                reply_text=reply_joined,
                qa=qa_tester,
                qa_group=in_qa_group,
                outcome="replied",
                reason=decision.reason,
                score=decision.best_score,
                bubbles=len(bubbles),
                extra={"footer": bool(footer)},
            )
            logger.info(
                "Replied in chat %s (%s, %d bubble(s)%s)",
                chat_id,
                decision.reason,
                len(bubbles),
                ", +footer" if footer else "",
            )
        except Exception:
            logger.exception("Failed to handle message in chat %s", chat_id)
            log_message_event(
                kind="faq",
                chat_id=chat_id,
                sender_id=sender_id,
                sender_username=sender_username or "",
                message_id=msg_id,
                text=question,
                qa=qa_tester,
                qa_group=in_qa_group,
                outcome="error",
                reason="handler_exception",
            )
        finally:
            self._processing.discard(msg_id)

    def register(self) -> None:
        @self.client.on(events.NewMessage())
        async def _on_message(event: events.NewMessage.Event) -> None:
            asyncio.create_task(self.handle(event))
