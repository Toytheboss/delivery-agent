"""First-check KPI audit plus the English result post.

The batch does not run on a timer. ``scripts/run_kpi_result_push.py --send``
audits September mainnet-live projects and posts to Project verification push.
A run without ``--send`` only lists who is still pending.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from bot.workflow_form_dispatch import _field_text
from bot.workflow_kpi_diag import latest_copy
from bot.workflow_kpi_pass_chain import KPI7_PASS_COPY
from bot.workflow_kpi_write import (
    diag_not_eligible_reason,
    field_result,
    now_shanghai,
    parse_live_start,
)
from bot.workflow_pr_capture import _display_pr_url

if TYPE_CHECKING:
    from bot.config_loader import AppConfig

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent

_KPI2_LINK = "KPI 2 - PR 新闻链接验证"
_SENT_FILE = ROOT / "data" / "kpi_result_push_sent.json"
# Already posted by hand. A missing state file must not send these again.
_ALREADY_POSTED = frozenset({"rec28ah3MsNpTG", "rec28abJciwa4a"})

_KPI4_LINE = (
    "mainnet MVP is live; wallet can connect, interact with the contract and "
    "consume gas; product availability verification passed"
)
_KPI5_LINE = (
    "mainnet go-live and product interaction have been manually verified; "
    "independence verification passed"
)
_BOT = "https://botchain.ai"
_SCAN = "https://scan.botchain.ai"
_TWITTER_SUBMIT = (
    "submit the official Twitter and reach `≥5` original posts in `30` days"
)
_TWITTER_COUNT = "reach `≥5` original posts in `30` days"
_PR_FIX = "share the Twitter PR link in the Telegram group"
_ONCHAIN_MISSING = (
    "submit the mainnet contract if missing, and reach `≥3` unique wallets "
    "and `≥5` successful core txs"
)
_ONCHAIN_SHORT = "reach `≥3` unique wallets and `≥5` successful core txs"
_VALID = "Valid KPI"
_HELD = "Held for rectification"
_PASS = "通过"
_HELD_COORD = "暂扣整改"
_COORD_FIELD = "KPI 统筹"
_JUDGE_FIELD = "KPI 判定时间"
_KPI1_RESULT = "推特验证结果"
_KPI1_COPY = "KPI 1 - Twitter运营验证"
_KPI2_RESULT = "新闻验证结果"
_KPI3_RESULT = "官网验证结果"
_KPI3_COPY = "KPI 3 - 官网展示验证"
_KPI4_RESULT = "产品可用验证结果"
_KPI5_RESULT = "独立性验证结果"
_KPI6_RESULT = "交互验证结果"
_KPI6_COPY = "KPI 6 - 链上交互验证"
_POSTED_RE = re.compile(r"posted (\d+) original", re.I)
_WALLETS_RE = re.compile(r"(\d+) unique wallets, (\d+) successful", re.I)


def posted_ids(path: Path | None = None) -> set[str]:
    ids = set(_ALREADY_POSTED)
    file = path or _SENT_FILE
    if not file.exists():
        return ids
    try:
        raw = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ids
    extra = raw.get("record_ids") if isinstance(raw, dict) else None
    if isinstance(extra, list):
        ids.update(str(item).strip() for item in extra if str(item).strip())
    return ids


def remember_posted(record_id: str, path: Path | None = None) -> None:
    file = path or _SENT_FILE
    ids = posted_ids(file)
    rid = (record_id or "").strip()
    if rid:
        ids.add(rid)
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(
        json.dumps({"record_ids": sorted(ids)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def is_september_2026_live(
    fields: dict[str, Any], status_field: str = "项目状态"
) -> bool:
    if diag_not_eligible_reason(fields, status_field):
        return False
    live = parse_live_start(fields)
    return bool(live and live.year == 2026 and live.month == 9)


def pending_september_rows(
    records: list[dict[str, Any]],
    *,
    status_field: str = "项目状态",
    name_field: str = "项目名称 Project Name",
    skip_ids: set[str] | None = None,
    project_name: str = "",
) -> list[dict[str, Any]]:
    """September mainnet-live rows that do not already have a result post."""
    skip = skip_ids if skip_ids is not None else posted_ids()
    want = (project_name or "").strip().casefold()
    out: list[dict[str, Any]] = []
    for row in records:
        rid = str(row.get("record_id") or "").strip()
        fields = row.get("fields") or {}
        if not rid or not isinstance(fields, dict) or rid in skip:
            continue
        if not is_september_2026_live(fields, status_field):
            continue
        name = _field_text(fields, name_field)
        if want and name.casefold() != want:
            continue
        out.append(row)
    out.sort(key=lambda row: _field_text(row.get("fields") or {}, name_field).casefold())
    return out


def twitter_post_line(
    *, handle: str, count: int | None, unread: bool
) -> tuple[bool, str]:
    if not (handle or "").strip():
        return False, "Not submitted"
    if unread or count is None:
        return False, "Official account could not be read."
    shown = int(count)
    if shown >= 5:
        return True, f"`{shown}` original posts. Meets the Twitter requirement."
    return False, f"`{shown}` original posts. Does not meet the Twitter requirement."


def twitter_fix(*, handle: str, count: int | None, unread: bool) -> str:
    if not (handle or "").strip() or unread or count is None:
        return _TWITTER_SUBMIT
    return _TWITTER_COUNT


def pr_post_line(url: str) -> tuple[bool, str]:
    shown = _display_pr_url(url)
    if not shown:
        return False, "Not submitted"
    return True, shown


def website_fix(reason: str, copy: str) -> str:
    text = copy or ""
    both = f"no clickable {_BOT} or {_SCAN}" in text
    if reason == "no_url" or "no official website URL" in text:
        return "submit the official website URL"
    if reason == "unreachable" or "could not be opened" in text:
        return "make the official website open"
    if reason == "no_botchain_name" or "BOT Chain name not found" in text:
        return "show the BOT Chain name on the website"
    if both:
        return f"add a clickable {_BOT} and {_SCAN} on the website"
    if f"but no clickable {_BOT}" in text:
        return f"add a clickable {_BOT} on the website"
    if f"but no clickable {_SCAN}" in text:
        return f"add a clickable {_SCAN} on the website"
    return "fix the official website links"


def onchain_post_line(
    *, contract: str, wallets: int, txs: int
) -> tuple[bool, str]:
    if not (contract or "").strip():
        return False, "Not submitted"
    ok = int(wallets) >= 3 and int(txs) >= 5
    numbers = f"`{int(wallets)}` wallets, `{int(txs)}` txs. "
    if ok:
        return True, numbers + "Meets the wallet and on-chain requirement."
    return False, numbers + "Does not meet the wallet and on-chain requirement."


def onchain_fix(*, contract: str) -> str:
    if not (contract or "").strip():
        return _ONCHAIN_MISSING
    return _ONCHAIN_SHORT


def format_result_post(
    *,
    project: str,
    bd_name: str,
    bd_open_id: str,
    live_date: str,
    check_date: str,
    twitter_ok: bool,
    twitter_line: str,
    pr_ok: bool,
    pr_line: str,
    website_ok: bool,
    website_line: str,
    onchain_ok: bool,
    onchain_line: str,
    fixes: list[str],
) -> str:
    """English first-check post. Held posts omit KPI 7. Never says KPI failed."""
    name = (bd_name or "").strip() or "BD"
    at = (
        f'<at user_id="{bd_open_id}">{name}</at>'
        if (bd_open_id or "").strip()
        else f"@{name}"
    )
    valid = twitter_ok and pr_ok and website_ok and onchain_ok
    result = _VALID if valid else _HELD
    items: list[tuple[int, str, bool, str]] = [
        (1, "KPI 1 Twitter", twitter_ok, twitter_line),
        (2, "KPI 2 PR", pr_ok, pr_line),
        (3, "KPI 3 Website", website_ok, website_line),
        (4, "KPI 4 Product availability", True, _KPI4_LINE),
        (5, "KPI 5 Project independence", True, _KPI5_LINE),
        (6, "KPI 6 On-chain", onchain_ok, onchain_line),
    ]
    if valid:
        items.append((7, "KPI 7 Ongoing operations", True, KPI7_PASS_COPY))
    failed = [item for item in items if not item[2]]
    passed = [item for item in items if item[2]]
    lines = [
        at,
        "",
        f"**Project:** `{project}`",
        f"**BD:** {name}",
        f"**Live date:** `{live_date}` Day `1`",
        f"**First check:** `{check_date}` · {result}",
        "",
        f"**Result:** {result}",
        "",
    ]
    if failed:
        lines.append("**Failed**")
        lines.extend(f"- **{label}:** {text}" for _n, label, _ok, text in failed)
        lines.append("")
    if passed:
        lines.append("**Passed**")
        lines.extend(f"- **{label}:** {text}" for _n, label, _ok, text in passed)
        lines.append("")
    if valid:
        lines.append("**Summary:** This is a valid KPI. There is no rectification item.")
    else:
        del fixes
        lines.append(
            "**Summary:** This is held for rectification under the new standard. "
            "Quote this message and submit the missing items within `2` weeks. "
            "The second review is final."
        )
    return "\n".join(lines).rstrip() + "\n"


def _passed(fields: dict[str, Any], result_field: str) -> bool:
    return field_result(fields, result_field) == _PASS


def twitter_line_from_copy(copy: str) -> str:
    match = _POSTED_RE.search(latest_copy(copy))
    if not match:
        return "Meets the Twitter requirement."
    return twitter_post_line(handle="kept", count=int(match.group(1)), unread=False)[1]


def onchain_line_from_copy(copy: str) -> str:
    match = _WALLETS_RE.search(latest_copy(copy))
    if not match:
        return "Meets the wallet and on-chain requirement."
    return onchain_post_line(
        contract="kept",
        wallets=int(match.group(1)),
        txs=int(match.group(2)),
    )[1]


def write_held_coord(token: str, config: AppConfig, record_id: str) -> None:
    """First-check hold. The coordination cell is 暂扣整改, never 不通过."""
    from bot.lark_bitable import update_record
    from bot.workflow_kpi_pass_chain import judge_time_ms

    update_record(
        token,
        config.workflow_base_app_token,
        config.workflow_progress_table_id,
        record_id,
        {_COORD_FIELD: _HELD_COORD, _JUDGE_FIELD: judge_time_ms()},
    )


def _pr_url(fields: dict[str, Any], written: str) -> str:
    from bot.project_logo import link_str

    raw = (written or "").strip()
    if not raw:
        raw = link_str(fields.get(_KPI2_LINK)) or _field_text(fields, _KPI2_LINK)
    return _display_pr_url(raw)


def audit_first_check(
    token: str,
    config: AppConfig,
    record_id: str,
    fields: dict[str, Any],
    *,
    project_name: str,
) -> dict[str, Any]:
    """Re-check items that are not already passed, then write coordination.

    Passed cells are left untouched. A hold writes 暂扣整改 and does not mark
    KPI 7 passed. A full pass writes KPI 7 and 通过.
    """
    from bot.lark_bitable import update_record
    from bot.workflow_kpi1_twitter import audit_kpi1_for_fields, fill_kpi2_pr_from_twitter
    from bot.workflow_kpi3_website import audit_kpi3_for_fields
    from bot.workflow_kpi45_live import fill_kpi45_for_fields, kpi45_pass_fields
    from bot.workflow_kpi6_onchain import audit_kpi6_for_fields
    from bot.workflow_kpi_pass_chain import (
        apply_pass_chain,
        planned_kpi2_result,
        write_kpi2_result,
    )
    from bot.workflow_live_onboard import parse_bd_person

    rid = (record_id or "").strip()
    name = (project_name or "").strip()
    current = dict(fields)
    twitter_passed = _passed(current, _KPI1_RESULT)
    pr_passed = _passed(current, _KPI2_RESULT)
    website_passed = _passed(current, _KPI3_RESULT)
    onchain_passed = _passed(current, _KPI6_RESULT)
    kpi1_copy_field = str(
        getattr(config, "workflow_kpi1_copy_field", "") or _KPI1_COPY
    )
    kpi3_copy_field = str(
        getattr(config, "workflow_kpi3_copy_field", "") or _KPI3_COPY
    )
    kpi6_copy_field = str(
        getattr(config, "workflow_kpi6_copy_field", "") or _KPI6_COPY
    )

    fresh_pr = ""
    if not twitter_passed:
        twitter = audit_kpi1_for_fields(
            token, config, rid, current, project_name=name
        )
        fresh_pr = str(twitter.get("pr_url") or "")
        handle = str(twitter.get("handle") or "")
        count = twitter.get("count")
        unread = str(twitter.get("reason") or "") == "unread"
        if not isinstance(count, int):
            count = None
        twitter_ok, twitter_line = twitter_post_line(
            handle=handle, count=count, unread=unread
        )
    else:
        twitter_ok = True
        twitter_line = twitter_line_from_copy(_field_text(current, kpi1_copy_field))
        handle = "kept"
        count = 5
        unread = False

    pr = _pr_url(current, fresh_pr)
    if pr and not pr_passed:
        current[_KPI2_LINK] = pr
    if not pr_passed:
        if twitter_passed:
            fresh_pr = fill_kpi2_pr_from_twitter(
                token, config, rid, current, project_name=name
            )
            pr = _pr_url(current, fresh_pr)
            if pr:
                current[_KPI2_LINK] = pr
        kpi2_write = planned_kpi2_result(current)
        if kpi2_write:
            write_kpi2_result(token, config, rid, kpi2_write)
            current[_KPI2_RESULT] = kpi2_write
        pr_ok, pr_line = pr_post_line(pr)
    else:
        pr_ok = True
        pr_line = pr_post_line(pr)[1] if pr else "Meets the PR requirement."

    if not website_passed:
        website = audit_kpi3_for_fields(
            token,
            config,
            rid,
            current,
            project_name=name,
            skip_if_audited=False,
        )
        if not isinstance(website, dict) or website.get("result") == "write_failed":
            raise RuntimeError(f"website write failed for {name}")
        site_copy = latest_copy(str(website.get("copy") or ""))
        site_reason = str(website.get("reason") or "")
        website_ok = site_reason == "passed"
    else:
        website_ok = True
        site_copy = latest_copy(_field_text(current, kpi3_copy_field))
        site_reason = "passed"

    kpi4_passed = _passed(current, _KPI4_RESULT)
    kpi5_passed = _passed(current, _KPI5_RESULT)
    if not kpi4_passed or not kpi5_passed:
        filled = fill_kpi45_for_fields(
            token, config, rid, current, project_name=name
        )
        if filled == "write_failed":
            raise RuntimeError(f"product and independence write failed for {name}")
        if filled == "already_filled":
            update_record(
                token,
                config.workflow_base_app_token,
                config.workflow_progress_table_id,
                rid,
                kpi45_pass_fields(
                    include_kpi4=not kpi4_passed,
                    include_kpi5=not kpi5_passed,
                ),
            )

    if not onchain_passed:
        onchain = audit_kpi6_for_fields(
            token, config, rid, current, project_name=name
        )
        chain_contract = str(onchain.get("contract") or "")
        wallets = int(onchain.get("wallets") or 0)
        txs = int(onchain.get("txs") or 0)
        onchain_ok, onchain_line = onchain_post_line(
            contract=chain_contract, wallets=wallets, txs=txs
        )
    else:
        onchain_ok = True
        onchain_line = onchain_line_from_copy(_field_text(current, kpi6_copy_field))
        chain_contract = "kept"

    fixes: list[str] = []
    if not twitter_ok:
        fixes.append(twitter_fix(handle=handle, count=count, unread=unread))
    if not pr_ok:
        fixes.append(_PR_FIX)
    if not website_ok:
        fixes.append(website_fix(site_reason, site_copy))
    if not onchain_ok:
        fixes.append(onchain_fix(contract=chain_contract))
    all_ok = twitter_ok and pr_ok and website_ok and onchain_ok
    if all_ok:
        apply_pass_chain(
            token,
            config,
            rid,
            {
                **current,
                _KPI1_RESULT: _PASS,
                _KPI2_RESULT: _PASS,
                _KPI3_RESULT: _PASS,
                _KPI4_RESULT: _PASS,
                _KPI5_RESULT: _PASS,
                _KPI6_RESULT: _PASS,
            },
        )
    else:
        write_held_coord(token, config, rid)
    live = parse_live_start(fields)
    live_date = live.strftime("%Y-%m-%d") if live else ""
    bd_field = str(getattr(config, "workflow_live_onboard_bd_field", "") or "BD")
    bd_open_id, bd_name = parse_bd_person(fields, bd_field)
    check_date = now_shanghai().strftime("%Y-%m-%d")
    markdown = format_result_post(
        project=name,
        bd_name=bd_name,
        bd_open_id=bd_open_id,
        live_date=live_date,
        check_date=check_date,
        twitter_ok=twitter_ok,
        twitter_line=twitter_line,
        pr_ok=pr_ok,
        pr_line=pr_line,
        website_ok=website_ok,
        website_line=site_copy,
        onchain_ok=onchain_ok,
        onchain_line=onchain_line,
        fixes=fixes,
    )
    return {
        "project": name,
        "record_id": rid,
        "valid": twitter_ok and pr_ok and website_ok and onchain_ok,
        "markdown": markdown,
    }


def send_result_post(token: str, config: AppConfig, markdown: str) -> None:
    from bot.lark_im import send_markdown_post_to_chat

    chat_id = str(getattr(config, "workflow_live_onboard_lark_chat_id", "") or "").strip()
    if not chat_id:
        raise RuntimeError("Project verification push chat id is empty")
    send_markdown_post_to_chat(token, chat_id, markdown)


def push_pending(
    token: str,
    config: AppConfig,
    records: list[dict[str, Any]],
    *,
    send: bool,
    project_name: str = "",
    sent_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Audit and, when send is true, post each pending September project."""
    status_field = str(getattr(config, "workflow_status_field", "") or "项目状态")
    name_field = str(
        getattr(config, "workflow_project_name_field", "") or "项目名称 Project Name"
    )
    rows = pending_september_rows(
        records,
        status_field=status_field,
        name_field=name_field,
        skip_ids=posted_ids(sent_path),
        project_name=project_name,
    )
    if not send:
        return [
            {
                "project": _field_text(row.get("fields") or {}, name_field),
                "record_id": str(row.get("record_id") or ""),
                "sent": False,
            }
            for row in rows
        ]
    done: list[dict[str, Any]] = []
    for row in rows:
        rid = str(row.get("record_id") or "")
        fields = row.get("fields") or {}
        name = _field_text(fields, name_field)
        try:
            built = audit_first_check(
                token, config, rid, fields, project_name=name
            )
            send_result_post(token, config, built["markdown"])
            remember_posted(rid, sent_path)
        except Exception as exc:  # noqa: BLE001
            logger.exception("kpi result push failed project=%r", name)
            done.append(
                {
                    "project": name,
                    "record_id": rid,
                    "sent": False,
                    "error": str(exc),
                }
            )
            continue
        try:
            from bot.workflow_events import log_delivery

            log_delivery(
                "kpi_result_pushed",
                "kpi result push",
                project_name=name,
                record_id=rid,
                text="已向 Project verification push 发送首轮考核结果",
            )
        except Exception:
            logger.exception("kpi result push log failed project=%r", name)
        done.append(
            {
                "project": name,
                "record_id": rid,
                "sent": True,
                "valid": built["valid"],
                "markdown": built["markdown"],
            }
        )
    return done
