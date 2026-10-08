"""First-check KPI audit plus the English result post.

The batch does not run on a timer. ``scripts/run_kpi_result_push.py --send``
audits September mainnet-live projects and posts to Project verification push.
A run without ``--send`` only lists who is still pending.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta
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
_FAILED = "KPI failed"
_PASS = "通过"
_HELD_COORD = "暂扣整改"
_FAIL_COORD = "不通过"
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


_WEBSITE_PASS_LINE = (
    "Website display verification: website opened, BOT Chain name is visible, "
    f"page has clickable {_BOT} and {_SCAN}; website display verification passed"
)


def website_post_line(*, ok: bool, site_copy: str = "", site_reason: str = "") -> str:
    """One-line Website result for the Lark post (never the raw checklist)."""
    if ok or (site_reason or "").strip() == "passed":
        return _WEBSITE_PASS_LINE
    text = latest_copy(site_copy or "")
    low = text.lower()
    if "official website url: not submitted" in low or (site_reason or "") == "no_url":
        return "Official website URL not submitted."
    if "- site opened: no" in low or (site_reason or "") == "unreachable":
        return "Official website could not be opened."
    if "bot chain name: no" in low or (site_reason or "") == "no_botchain_name":
        return "BOT Chain name not found on the website."
    bot_ok = f"- {_BOT}: yes" in text
    scan_ok = f"- {_SCAN}: yes" in text
    name_ok = "BOT Chain name: yes" in text
    opened = "- Site opened: yes" in text
    parts = [
        f"Site opened: {'yes' if opened else 'no'}",
        f"BOT Chain name: {'yes' if name_ok else 'no'}",
        f"{_BOT}: {'yes' if bot_ok else 'no'}",
        f"{_SCAN}: {'yes' if scan_ok else 'no'}",
    ]
    return "Website display verification failed (" + "; ".join(parts) + ")."


def website_fix(reason: str, copy: str) -> str:
    text = copy or ""
    if f"no clickable {_BOT} or {_SCAN}" in text:
        return f"add a clickable {_BOT} and {_SCAN} on the website"
    bot_missing = (
        f"- {_BOT}: no" in text
        or f"no clickable {_BOT}" in text
        or f"but no clickable {_BOT}" in text
    )
    scan_missing = (
        f"- {_SCAN}: no" in text
        or f"no clickable {_SCAN}" in text
        or f"but no clickable {_SCAN}" in text
    )
    if reason == "no_url" or "no official website URL" in text or "Official website URL: not submitted" in text:
        return "submit the official website URL"
    if reason == "unreachable" or "could not be opened" in text or "- Site opened: no" in text:
        return "make the official website open"
    if reason == "no_botchain_name" or "BOT Chain name not found" in text:
        return "show the BOT Chain name on the website"
    if bot_missing and scan_missing:
        return f"add a clickable {_BOT} and {_SCAN} on the website"
    if bot_missing:
        return f"add a clickable {_BOT} on the website"
    if scan_missing:
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


_CHECK_DAY_RE = re.compile(
    r"(?:First check|Recheck)\s+(\d{4}-\d{2}-\d{2})",
    re.IGNORECASE,
)


def first_check_date_from_fields(fields: dict[str, Any] | None) -> str:
    """Earliest First check / Recheck stamp in KPI copy cells (e.g. 2026-09-30 batch)."""
    days: list[str] = []
    for value in (fields or {}).values():
        text = str(value or "")
        if not text:
            continue
        for match in _CHECK_DAY_RE.finditer(text):
            days.append(match.group(1))
    return min(days) if days else ""


def resolve_first_check_date(
    live_date: str,
    first_check_date: str = "",
    fields: dict[str, Any] | None = None,
) -> str:
    """Resolve First check day for final posts.

    Order: earliest stamp in progress KPI cells (covers the 2026-09-30 batch) →
    schedule / caller date → live+7 only as last resort.
    """
    candidates: list[str] = []
    from_fields = first_check_date_from_fields(fields)
    if from_fields:
        candidates.append(from_fields)
    explicit = (first_check_date or "").strip()
    if explicit:
        candidates.append(explicit)
    if candidates:
        return min(candidates)
    live = (live_date or "").strip()
    if not live:
        return ""
    try:
        return (
            datetime.strptime(live, "%Y-%m-%d").date() + timedelta(days=7)
        ).isoformat()
    except ValueError:
        return ""


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
    final: bool = False,
    final_trigger: str = "calendar",
    first_check_date: str = "",
    fields: dict[str, Any] | None = None,
) -> str:
    """English result post. The first check never says KPI failed."""
    name = (bd_name or "").strip() or "BD"
    at = (
        f'<at user_id="{bd_open_id}">{name}</at>'
        if (bd_open_id or "").strip()
        else f"@{name}"
    )
    valid = twitter_ok and pr_ok and website_ok and onchain_ok
    if final:
        result = _VALID if valid else _FAILED
    else:
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
    ]
    if final:
        # Final posts always show First check + Second check. Prefer real audit
        # stamps (incl. 2026-09-30 batch) over live+7.
        first_day = resolve_first_check_date(
            live_date, first_check_date, fields=fields
        )
        if first_day:
            lines.append(f"**First check:** `{first_day}` · {_HELD}")
        trigger = (final_trigger or "calendar").strip().lower()
        if trigger == "submit":
            second_label = "final (triggered by submit)"
        else:
            second_label = "Day `21` recheck"
        lines.append(f"**Second check:** `{check_date}` · {second_label}")
    else:
        lines.append(f"**First check:** `{check_date}` · {result}")
    lines.extend(
        [
            "",
            f"**Result:** {result}",
            "",
        ]
    )
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
    elif final:
        del fixes
        lines.append(
            "**Summary:** Held items still failed on final review, so this is "
            "`KPI failed` under the new standard. There is no further fix window."
        )
    else:
        del fixes
        lines.append(
            "**Summary:** This is held for rectification under the new standard. "
            "Quote this message to submit X profile, mainnet contract, and/or "
            "PR tweet. Any successful submit triggers a **final** recheck now: "
            "pass → `Valid KPI`; fail → `KPI failed` (no further chance). "
            "Website issues must be fixed on the live site — a URL paste here "
            "does not count. No submit → final review on live day `21`."
        )
    return "\n".join(lines).rstrip() + "\n"


def _passed(fields: dict[str, Any], result_field: str) -> bool:
    return field_result(fields, result_field) == _PASS


def twitter_line_from_copy(copy: str) -> str:
    body = latest_copy(copy)
    low = body.lower()
    if "official account: not submitted" in low or "no official account submitted" in low:
        return "Not submitted"
    if "original posts (30d): unread" in low or "could not be read" in low:
        return "Official account could not be read."
    match = _POSTED_RE.search(body) or re.search(
        r"Original posts \(30d\): (\d+)", body
    )
    if not match:
        return "Meets the Twitter requirement."
    return twitter_post_line(handle="kept", count=int(match.group(1)), unread=False)[1]


def onchain_line_from_copy(copy: str) -> str:
    body = latest_copy(copy)
    match = _WALLETS_RE.search(body)
    if match:
        wallets, txs = int(match.group(1)), int(match.group(2))
    else:
        wallets_match = re.search(r"Unique wallets: (\d+)", body)
        txs_match = re.search(r"Core txs: (\d+)", body)
        if not wallets_match or not txs_match:
            if "contract: not submitted" in body.lower() or "no contract detected" in body.lower():
                return "Not submitted"
            return "Meets the wallet and on-chain requirement."
        wallets, txs = int(wallets_match.group(1)), int(txs_match.group(1))
    return onchain_post_line(contract="kept", wallets=wallets, txs=txs)[1]


def write_final_fail_coord(token: str, config: AppConfig, record_id: str) -> None:
    """Second check. Still-failing items become 不通过. There is no further hold."""
    from bot.lark_bitable import update_record
    from bot.workflow_kpi_pass_chain import judge_time_ms

    stamp = judge_time_ms()
    last_error: Exception | None = None
    for coord in (_FAIL_COORD, "KPI未通过"):
        try:
            update_record(
                token,
                config.workflow_base_app_token,
                config.workflow_progress_table_id,
                record_id,
                {_COORD_FIELD: coord, _JUDGE_FIELD: stamp},
            )
            return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
    if last_error:
        raise last_error


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
    final: bool = False,
    final_trigger: str = "calendar",
    first_check_date: str = "",
) -> dict[str, Any]:
    """Re-check items that are not already passed, then write coordination.

    Passed cells are left untouched. The first check writes 暂扣整改 and does
    not mark KPI 7 passed. The second check writes 不通过 instead. A full pass
    writes KPI 7 and 通过.
    """
    from bot.workflow_kpi_write import kpi_checks_on_this_host

    if not kpi_checks_on_this_host():
        raise RuntimeError("KPI checks run on Roy号 only")
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
    elif final:
        write_final_fail_coord(token, config, rid)
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
        website_line=website_post_line(
            ok=website_ok, site_copy=site_copy, site_reason=site_reason
        ),
        onchain_ok=onchain_ok,
        onchain_line=onchain_line,
        fixes=fixes,
        final=final,
        final_trigger=final_trigger,
        first_check_date=first_check_date,
        fields=current,
    )
    return {
        "project": name,
        "record_id": rid,
        "valid": twitter_ok and pr_ok and website_ok and onchain_ok,
        "markdown": markdown,
        "result": (
            _VALID
            if (twitter_ok and pr_ok and website_ok and onchain_ok)
            else (_FAILED if final else _HELD)
        ),
        "final": final,
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


def _coord_value(fields: dict[str, Any]) -> str:
    return field_result(fields, _COORD_FIELD) or _field_text(fields, _COORD_FIELD)


def pick_early_final_progress_row(
    rows: list[dict[str, Any]],
    *,
    project_name: str,
    name_field: str,
    record_id: str = "",
) -> dict[str, Any] | None:
    """Pick the KPI-era progress row for a补交终审.

    Pre-2026-09-01 live duplicates are ignored. Among September-or-later rows
    with the same name, prefer ``暂扣整改``.
    """
    from bot.workflow_form_dispatch import _normalize_name
    from bot.workflow_kpi_write import is_kpi_era_live

    key = _normalize_name(project_name)
    rid = (record_id or "").strip()
    name_hits: list[dict[str, Any]] = []
    for row in rows:
        row_id = str(row.get("record_id") or "").strip()
        fields = row.get("fields") or {}
        if not isinstance(fields, dict):
            continue
        if not is_kpi_era_live(fields):
            continue
        if rid and row_id == rid:
            return row
        if key and _normalize_name(_field_text(fields, name_field)) == key:
            name_hits.append(row)
    if not name_hits:
        return None
    held = [
        row
        for row in name_hits
        if _coord_value(row.get("fields") or {}) == _HELD_COORD
    ]
    return held[0] if held else name_hits[0]


def run_early_final_after_submit(
    config: AppConfig,
    *,
    project_name: str,
    record_id: str = "",
) -> dict[str, Any]:
    """If the project is still held, run a final recheck immediately and post it.

    Triggered after BD successfully pastes X profile / contract / PR under the
    held result post. Pass → Valid KPI. Fail → KPI failed with no further chance.
    Calendar day-21 second check is then skipped via schedule state.
    """
    import os

    from bot.lark_bitable import get_tenant_access_token, list_records
    from bot.workflow_kpi_schedule import first_check_date_for, mark_rounds_done
    from bot.workflow_kpi_write import kpi_checks_on_this_host

    out: dict[str, Any] = {
        "ran": False,
        "skipped": True,
        "reason": "",
        "result": "",
        "project": (project_name or "").strip(),
        "record_id": (record_id or "").strip(),
    }
    name = out["project"]
    if not name:
        out["reason"] = "no_project"
        return out
    if not kpi_checks_on_this_host():
        out["reason"] = "non_roy_host"
        return out
    app_id = os.getenv("LARK_APP_ID", "").strip()
    app_secret = os.getenv("LARK_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        out["reason"] = "missing_lark_credentials"
        return out
    try:
        token = get_tenant_access_token(app_id, app_secret)
        rows = list_records(
            token,
            config.workflow_base_app_token,
            config.workflow_progress_table_id,
        )
    except Exception:
        logger.exception("early final: list progress failed project=%r", name)
        out["reason"] = "list_failed"
        return out
    name_field = str(
        getattr(config, "workflow_project_name_field", "") or "项目名称 Project Name"
    )
    hit = pick_early_final_progress_row(
        rows,
        project_name=name,
        name_field=name_field,
        record_id=out["record_id"],
    )
    if not hit:
        out["reason"] = "progress_missing"
        return out
    rid = str(hit.get("record_id") or out["record_id"] or "").strip()
    fields = hit.get("fields") or {}
    out["record_id"] = rid
    coord = _coord_value(fields if isinstance(fields, dict) else {})
    if coord != _HELD_COORD:
        out["reason"] = f"not_held:{coord or 'empty'}"
        return out
    try:
        audited = audit_first_check(
            token,
            config,
            rid,
            fields if isinstance(fields, dict) else {},
            project_name=name,
            final=True,
            final_trigger="submit",
            first_check_date=first_check_date_for(rid),
        )
        send_result_post(token, config, audited["markdown"])
        mark_rounds_done(rid, rounds=("first", "second"))
    except Exception:
        logger.exception("early final failed project=%r record=%s", name, rid)
        out["reason"] = "audit_or_send_failed"
        return out
    try:
        remember_posted(rid)
    except Exception:
        # Post already sent; do not treat a sent-state file permission error as
        # a failed final review.
        logger.exception(
            "early final remember_posted failed project=%r record=%s", name, rid
        )
    out["ran"] = True
    out["skipped"] = False
    out["reason"] = "ok"
    out["result"] = str(audited.get("result") or "")
    out["valid"] = bool(audited.get("valid"))
    try:
        from bot.workflow_events import log_delivery

        log_delivery(
            "kpi_early_final",
            "kpi result push",
            project_name=name,
            record_id=rid,
            text=f"补交触发终审：{out['result']}",
        )
    except Exception:
        logger.exception("early final log failed project=%r", name)
    return out
