"""KPI 1 Twitter originals in the last 30 days."""

from __future__ import annotations

import logging
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import requests

from bot.lark_bitable import update_record
from bot.project_logo import link_str
from bot.workflow_form_chase import field_is_filled
from bot.workflow_form_dispatch import _field_text
from bot.workflow_kpi_write import (
    SH,
    field_result,
    find_wallet_row,
    merge_kpi_copy,
    merge_kpi_result,
    now_shanghai,
)

if TYPE_CHECKING:
    from bot.config_loader import AppConfig

logger = logging.getLogger(__name__)

_DEFAULT_COPY_FIELD = "KPI 1 - Twitter运营验证"
_DEFAULT_RESULT_FIELD = "推特验证结果"
_PASS = "通过"
_FAIL = "不通过"
_THRESHOLD = 5
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_NITTER_HOSTS = (
    "https://nitter.poast.org",
    "https://nitter.privacydev.net",
    "https://nitter.net",
)
_RESERVED_HANDLES = frozenset(
    {
        "i",
        "intent",
        "home",
        "search",
        "share",
        "explore",
        "settings",
        "compose",
        "messages",
        "notifications",
        "hashtag",
        "hashtags",
        "status",
    }
)
_TWITTER_FIELD_ALIASES = (
    "Link of Project X ( Formerly Twitter) Profile Page",
    "Project X ( Formerly Twitter) Profile Page",
    "Project X ( Formly Twitter) Profile Page",
    "Project X ( Formely Twitter) Profile Page",
)


def twitter_handle_from_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return ""
    if "://" not in raw:
        handle = raw.lstrip("@")
        if re.fullmatch(r"[A-Za-z0-9_]{1,15}", handle):
            return handle
        raw = "https://" + handle
    parsed = urlparse(raw)
    host = (parsed.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if host not in {
        "x.com",
        "twitter.com",
        "mobile.twitter.com",
        "vxtwitter.com",
        "fxtwitter.com",
        "nitter.net",
    }:
        handle = raw.strip().lstrip("@")
        if re.fullmatch(r"[A-Za-z0-9_]{1,15}", handle):
            return handle
        return ""
    parts = [p for p in parsed.path.split("/") if p]
    if not parts:
        return ""
    handle = parts[0].lstrip("@")
    if handle.lower() in _RESERVED_HANDLES:
        return ""
    return handle


def wallet_twitter_url(fields: dict[str, Any]) -> str:
    for name in _TWITTER_FIELD_ALIASES:
        if field_is_filled(fields, name):
            return link_str(fields.get(name)) or _field_text(fields, name)
    return ""


def is_retweet(text: str, extra: dict[str, Any] | None = None) -> bool:
    blob = extra or {}
    if blob.get("retweeted_status"):
        return True
    rest = str(blob.get("full_text") or blob.get("text") or text or "")
    return rest.lstrip().startswith("RT @")


def _parse_created(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            dt = parsedate_to_datetime(text)
        except (TypeError, ValueError):
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=SH)
    return dt.astimezone(SH)


def _nitter_rss(handle: str) -> list[tuple[datetime, str]]:
    out: list[tuple[datetime, str]] = []
    for host in _NITTER_HOSTS:
        try:
            resp = requests.get(
                f"{host}/{handle}/rss",
                headers={"User-Agent": _UA},
                timeout=20,
            )
            if resp.status_code != 200 or "<item>" not in resp.text:
                continue
            root = ET.fromstring(resp.text)
        except (OSError, requests.RequestException, ET.ParseError):
            continue
        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            pub = item.findtext("pubDate") or ""
            dt = _parse_created(pub)
            if dt is None:
                continue
            out.append((dt, title))
        if out:
            return out
    return out


def _syndication(handle: str) -> list[tuple[datetime, str, dict[str, Any]]]:
    try:
        resp = requests.get(
            "https://cdn.syndication.twimg.com/timeline/profile",
            params={"screen_name": handle},
            headers={"User-Agent": _UA},
            timeout=20,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
    except (OSError, requests.RequestException, ValueError):
        return []
    body = data.get("body") if isinstance(data, dict) else None
    if not isinstance(body, list):
        tweets = data.get("tweets") if isinstance(data, dict) else None
        if isinstance(tweets, dict):
            body = list(tweets.values())
        else:
            return []
    out: list[tuple[datetime, str, dict[str, Any]]] = []
    for item in body:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or item.get("full_text") or "")
        dt = _parse_created(item.get("created_at") or item.get("createdAt"))
        if dt is None:
            continue
        out.append((dt, text, item))
    return out


def _x_api(handle: str, since: datetime) -> list[tuple[datetime, str, dict[str, Any]]] | None:
    bearer = (
        os.getenv("X_BEARER_TOKEN")
        or os.getenv("TWITTER_BEARER_TOKEN")
        or os.getenv("TWITTER_BEARER")
        or ""
    ).strip()
    if not bearer:
        return None
    headers = {"Authorization": f"Bearer {bearer}"}
    try:
        user_resp = requests.get(
            f"https://api.twitter.com/2/users/by/username/{handle}",
            headers=headers,
            timeout=20,
        )
        user_resp.raise_for_status()
        user_id = ((user_resp.json().get("data") or {}).get("id") or "").strip()
        if not user_id:
            return []
        tweet_resp = requests.get(
            f"https://api.twitter.com/2/users/{user_id}/tweets",
            headers=headers,
            params={
                "max_results": 100,
                "exclude": "retweets,replies",
                "tweet.fields": "created_at,text",
                "start_time": since.astimezone(SH).strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
            timeout=20,
        )
        tweet_resp.raise_for_status()
        rows = tweet_resp.json().get("data") or []
    except (OSError, requests.RequestException, ValueError):
        logger.exception("kpi1: X API fetch failed handle=%s", handle)
        return None
    out: list[tuple[datetime, str, dict[str, Any]]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        dt = _parse_created(item.get("created_at"))
        if dt is None:
            continue
        out.append((dt, str(item.get("text") or ""), item))
    return out


def count_originals(handle: str, *, since: datetime) -> tuple[int | None, str]:
    api = _x_api(handle, since)
    if api is not None:
        n = sum(1 for dt, text, extra in api if dt >= since and not is_retweet(text, extra))
        return n, "x_api"
    syn = _syndication(handle)
    if syn:
        n = sum(1 for dt, text, extra in syn if dt >= since and not is_retweet(text, extra))
        return n, "syndication"
    rss = _nitter_rss(handle)
    if rss:
        n = sum(1 for dt, text in rss if dt >= since and not is_retweet(text))
        return n, "nitter"
    return None, "unread"


def build_kpi1_copy(*, handle: str, count: int | None, reason: str) -> str:
    if reason == "no_account":
        return (
            "Twitter operations verification: no official account submitted; "
            "Twitter operations verification failed"
        )
    who = f" @{handle}" if handle else ""
    if reason == "unread" or count is None:
        return (
            f"Twitter operations verification: official account{who} could not be "
            "read for original posts in the last 30 days; "
            "Twitter operations verification failed"
        )
    n = int(count)
    suffix = "passed" if n >= _THRESHOLD else "failed"
    return (
        f"Twitter operations verification: official account{who} posted {n} "
        f"original posts in the last 30 days (threshold ≥{_THRESHOLD}); "
        f"Twitter operations verification {suffix}"
    )


def evaluate_kpi1(*, handle: str, count: int | None, unread: bool) -> dict[str, Any]:
    if not handle:
        return {
            "passed": False,
            "reason": "no_account",
            "copy": build_kpi1_copy(handle="", count=None, reason="no_account"),
            "count": 0,
        }
    if unread or count is None:
        return {
            "passed": False,
            "reason": "unread",
            "copy": build_kpi1_copy(handle=handle, count=None, reason="unread"),
            "count": None,
        }
    passed = count >= _THRESHOLD
    return {
        "passed": passed,
        "reason": "pass" if passed else "below_threshold",
        "copy": build_kpi1_copy(handle=handle, count=count, reason="ok"),
        "count": count,
    }


def audit_kpi1_for_fields(
    token: str,
    config: AppConfig,
    record_id: str,
    fields: dict[str, Any],
    *,
    project_name: str = "",
) -> dict[str, Any]:
    rid = (record_id or "").strip()
    name = (project_name or "").strip() or _field_text(
        fields, config.workflow_project_name_field
    )
    copy_field = str(
        getattr(config, "workflow_kpi1_copy_field", "") or _DEFAULT_COPY_FIELD
    )
    result_field = str(
        getattr(config, "workflow_kpi1_result_field", "") or _DEFAULT_RESULT_FIELD
    )
    wallet = find_wallet_row(token, config, name)
    url = wallet_twitter_url(wallet[1]) if wallet else ""
    handle = twitter_handle_from_url(url)
    since = now_shanghai() - timedelta(days=30)
    count: int | None = None
    unread = False
    if handle:
        count, source = count_originals(handle, since=since)
        unread = source == "unread"
        logger.info("kpi1: handle=%s source=%s count=%s", handle, source, count)
    verdict = evaluate_kpi1(handle=handle, count=count, unread=unread)
    existing_copy = _field_text(fields, copy_field)
    existing_result = field_result(fields, result_field)
    copy = merge_kpi_copy(existing_copy, str(verdict["copy"]))
    result = merge_kpi_result(existing_result, passed=bool(verdict["passed"]))
    update_record(
        token,
        config.workflow_base_app_token,
        config.workflow_progress_table_id,
        rid,
        {copy_field: copy, result_field: result},
    )
    return {
        "result": result,
        "passed": result == _PASS,
        "reason": verdict["reason"],
        "copy": copy,
        "handle": handle,
        "count": verdict["count"],
        "project": name,
    }
