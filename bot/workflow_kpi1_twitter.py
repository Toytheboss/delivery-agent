"""KPI 1 Twitter originals in the last 30 days."""

from __future__ import annotations

import base64
import logging
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import requests

from bot.lark_bitable import update_record
from bot.project_logo import link_str, pick_site_url
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
_LINK_LIMIT = 5
_MEETS_AUDIT = "Meets the audit requirement"
_KPI2_LINK = "KPI 2 - PR 新闻链接验证"
_CHAIN_RE = re.compile(r"bot\s*chain|botchain", re.I)
_LIVE_RE = re.compile(
    r"\blive\b|\blaunched\b|\blaunch(?:ing|ed)?\b|\bmainnet\b|\bgo[\s-]?live\b",
    re.I,
)
_X_API_HOSTS = ("https://api.x.com", "https://api.twitter.com")
_MAX_TWEET_PAGES = 5
_BEARER_CACHE = ""
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


def _tweet_id(extra: dict[str, Any] | None) -> str:
    blob = extra or {}
    for key in ("id_str", "id", "idStr"):
        raw = blob.get(key)
        if raw is None:
            continue
        text = str(raw).strip()
        if text.isdigit():
            return text
    return ""


def original_status_links(
    handle: str,
    rows: list[tuple[datetime, str, dict[str, Any]]],
    *,
    since: datetime,
    limit: int | None = None,
) -> list[str]:
    who = (handle or "").strip().lstrip("@")
    if not who:
        return []
    if limit is not None and limit <= 0:
        return []
    ranked: list[tuple[datetime, str]] = []
    for dt, text, extra in rows:
        if dt < since or is_retweet(text, extra):
            continue
        tweet_id = _tweet_id(extra if isinstance(extra, dict) else None)
        if not tweet_id:
            continue
        ranked.append((dt, f"https://x.com/{who}/status/{tweet_id}"))
    ranked.sort(key=lambda item: item[0], reverse=True)
    links: list[str] = []
    seen: set[str] = set()
    for _dt, url in ranked:
        if url in seen:
            continue
        seen.add(url)
        links.append(url)
        if limit is not None and len(links) >= limit:
            break
    return links


def _compact_latin(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def tweet_has_project_name(text: str, project_name: str) -> bool:
    raw = (project_name or "").strip()
    if len(raw) < 2:
        return False
    blob = text or ""
    if re.search(r"[\u4e00-\u9fff]", raw):
        return raw.lower() in blob.lower()
    compact = _compact_latin(raw)
    if len(compact) < 3:
        return False
    return compact in _compact_latin(blob)


def is_mainnet_pr_tweet(
    text: str,
    extra: dict[str, Any] | None = None,
    *,
    project_name: str,
) -> bool:
    body = text or ""
    if is_retweet(body, extra):
        return False
    if not _CHAIN_RE.search(body) or not _LIVE_RE.search(body):
        return False
    return tweet_has_project_name(body, project_name)


def find_mainnet_pr_url(
    handle: str,
    rows: list[tuple[datetime, str, dict[str, Any]]],
    *,
    since: datetime,
    project_name: str,
) -> str:
    who = (handle or "").strip().lstrip("@")
    if not who:
        return ""
    ranked: list[tuple[datetime, str]] = []
    for dt, text, extra in rows:
        if dt < since:
            continue
        if not is_mainnet_pr_tweet(text, extra, project_name=project_name):
            continue
        tweet_id = _tweet_id(extra if isinstance(extra, dict) else None)
        if not tweet_id:
            continue
        ranked.append((dt, f"https://x.com/{who}/status/{tweet_id}"))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked[0][1] if ranked else ""


def maybe_write_kpi2_from_tweets(
    token: str,
    config: AppConfig,
    record_id: str,
    fields: dict[str, Any],
    *,
    project_name: str,
    handle: str,
    rows: list[tuple[datetime, str, dict[str, Any]]],
    since: datetime,
) -> str:
    """Fill empty KPI 2 from a mainnet-PR tweet. Never overwrites a filled cell."""
    link_field = str(
        getattr(config, "pr_capture_link_field", "") or _KPI2_LINK
    )
    if field_is_filled(fields, link_field):
        return ""
    url = find_mainnet_pr_url(
        handle, rows, since=since, project_name=project_name
    )
    if not url:
        return ""
    from bot.workflow_pr_capture import kpi2_pass_fields
    from bot.workflow_pr_weekly import log_capture_event

    rid = (record_id or "").strip()
    update_record(
        token,
        config.workflow_base_app_token,
        config.workflow_progress_table_id,
        rid,
        kpi2_pass_fields(link_field=link_field, url=url),
    )
    try:
        site = pick_site_url(
            fields,
            str(getattr(config, "workflow_live_link_field", "") or "已上线链接🔗"),
            str(getattr(config, "workflow_project_link_field", "") or "项目链接"),
        )
        log_capture_event(
            config, record_id=rid, project=project_name, url=url, site=site or ""
        )
    except Exception:
        logger.exception("kpi1: PR event log failed project=%r", project_name)
    logger.info("kpi1: filled KPI 2 from tweet project=%r url=%s", project_name, url)
    return url


def fill_kpi2_pr_from_twitter(
    token: str,
    config: AppConfig,
    record_id: str,
    fields: dict[str, Any],
    *,
    project_name: str = "",
) -> str:
    """When Twitter already passed, still hunt PR from the official timeline."""
    link_field = str(
        getattr(config, "pr_capture_link_field", "") or _KPI2_LINK
    )
    if field_is_filled(fields, link_field):
        return ""
    name = (project_name or "").strip() or _field_text(
        fields, config.workflow_project_name_field
    )
    wallet = find_wallet_row(token, config, name)
    url = wallet_twitter_url(wallet[1]) if wallet else ""
    handle = twitter_handle_from_url(url)
    if not handle:
        return ""
    since = now_shanghai() - timedelta(days=30)
    _source, rows = fetch_timeline(handle, since=since)
    if not rows:
        return ""
    return maybe_write_kpi2_from_tweets(
        token,
        config,
        record_id,
        fields,
        project_name=name,
        handle=handle,
        rows=rows,
        since=since,
    )


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


def x_api_configured() -> bool:
    if _env_bearer():
        return True
    return bool(_env_api_key() and _env_api_secret())


def _env_bearer() -> str:
    return (
        os.getenv("X_BEARER_TOKEN")
        or os.getenv("TWITTER_BEARER_TOKEN")
        or os.getenv("TWITTER_BEARER")
        or ""
    ).strip()


def _env_api_key() -> str:
    return (os.getenv("X_API_KEY") or os.getenv("TWITTER_API_KEY") or "").strip()


def _env_api_secret() -> str:
    return (
        os.getenv("X_API_SECRET")
        or os.getenv("TWITTER_API_SECRET")
        or os.getenv("TWITTER_API_KEY_SECRET")
        or ""
    ).strip()


def _utc_stamp(when: datetime) -> str:
    return when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fetch_app_bearer(key: str, secret: str) -> str:
    basic = base64.b64encode(f"{key}:{secret}".encode("utf-8")).decode("ascii")
    headers = {
        "Authorization": f"Basic {basic}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    for host in _X_API_HOSTS:
        try:
            resp = requests.post(
                f"{host}/oauth2/token",
                headers=headers,
                data={"grant_type": "client_credentials"},
                timeout=20,
            )
        except (OSError, requests.RequestException):
            logger.exception("kpi1: X OAuth2 token request failed host=%s", host)
            continue
        if resp.status_code != 200:
            logger.warning(
                "kpi1: X OAuth2 token HTTP %s host=%s", resp.status_code, host
            )
            continue
        try:
            token = str((resp.json() or {}).get("access_token") or "").strip()
        except ValueError:
            token = ""
        if token:
            return token
    return ""


def _x_bearer() -> str:
    global _BEARER_CACHE
    direct = _env_bearer()
    if direct:
        return direct
    if _BEARER_CACHE:
        return _BEARER_CACHE
    key, secret = _env_api_key(), _env_api_secret()
    if not key or not secret:
        return ""
    token = _fetch_app_bearer(key, secret)
    if token:
        _BEARER_CACHE = token
    return token


def _x_get(
    path: str,
    bearer: str,
    params: dict[str, Any] | None = None,
) -> requests.Response | None:
    headers = {"Authorization": f"Bearer {bearer}", "User-Agent": _UA}
    last: requests.Response | None = None
    for host in _X_API_HOSTS:
        try:
            resp = requests.get(
                f"{host}{path}", headers=headers, params=params, timeout=20
            )
        except (OSError, requests.RequestException):
            logger.exception("kpi1: X GET failed %s%s", host, path)
            continue
        remaining = resp.headers.get("x-rate-limit-remaining")
        if remaining is not None:
            logger.info(
                "kpi1: X %s HTTP %s remaining=%s", path, resp.status_code, remaining
            )
        if resp.status_code != 404:
            return resp
        last = resp
    return last


def _x_api(handle: str, since: datetime) -> list[tuple[datetime, str, dict[str, Any]]] | None:
    """Official X timeline. None = call failed. [] = user/tweets empty."""
    bearer = _x_bearer()
    if not bearer:
        return None
    user_resp = _x_get(f"/2/users/by/username/{handle}", bearer)
    if user_resp is None:
        return None
    if user_resp.status_code == 404:
        return []
    if user_resp.status_code >= 400:
        logger.warning(
            "kpi1: X user lookup HTTP %s handle=%s", user_resp.status_code, handle
        )
        return None
    try:
        user_id = str(((user_resp.json().get("data") or {}).get("id") or "")).strip()
    except ValueError:
        return None
    if not user_id:
        return []

    start = _utc_stamp(since)
    params: dict[str, Any] = {
        "max_results": 100,
        "exclude": "retweets,replies",
        "tweet.fields": "created_at,text",
        "start_time": start,
    }
    out: list[tuple[datetime, str, dict[str, Any]]] = []
    page = 0
    drop_start = False
    while page < _MAX_TWEET_PAGES:
        page += 1
        if drop_start:
            params.pop("start_time", None)
        tweet_resp = _x_get(f"/2/users/{user_id}/tweets", bearer, params)
        if tweet_resp is None:
            return None if not out else out
        if tweet_resp.status_code == 400 and not drop_start and "start_time" in params:
            logger.info("kpi1: X start_time rejected handle=%s; retry without it", handle)
            drop_start = True
            page -= 1
            continue
        if tweet_resp.status_code >= 400:
            logger.warning(
                "kpi1: X tweets HTTP %s handle=%s", tweet_resp.status_code, handle
            )
            return None if not out else out
        try:
            payload = tweet_resp.json()
        except ValueError:
            return None if not out else out
        rows = payload.get("data") or []
        oldest_on_page: datetime | None = None
        for item in rows:
            if not isinstance(item, dict):
                continue
            dt = _parse_created(item.get("created_at"))
            if dt is None:
                continue
            if oldest_on_page is None or dt < oldest_on_page:
                oldest_on_page = dt
            if dt >= since:
                out.append((dt, str(item.get("text") or ""), item))
        meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
        next_token = str((meta or {}).get("next_token") or "").strip()
        if not next_token:
            break
        if oldest_on_page is not None and oldest_on_page < since:
            break
        params["pagination_token"] = next_token
    return out


def fetch_timeline(
    handle: str, *, since: datetime
) -> tuple[str, list[tuple[datetime, str, dict[str, Any]]] | None]:
    """Return (source, rows). ``None`` rows means the official read failed."""
    if x_api_configured():
        api = _x_api(handle, since)
        if api is None:
            return "unread", None
        return "x_api", api
    syn = _syndication(handle)
    if syn:
        return "syndication", syn
    rss = _nitter_rss(handle)
    if rss:
        return "nitter", [(dt, text, {}) for dt, text in rss]
    return "unread", None


def collect_originals(
    handle: str, *, since: datetime
) -> tuple[int | None, str, list[str]]:
    """Count originals in ``since``..now and keep recent status URLs."""
    source, rows = fetch_timeline(handle, since=since)
    if rows is None:
        return None, "unread", []
    n = sum(1 for dt, text, extra in rows if dt >= since and not is_retweet(text, extra))
    return n, source, original_status_links(handle, rows, since=since)


def count_originals(handle: str, *, since: datetime) -> tuple[int | None, str]:
    """Count originals in ``since``..now. Prefer X API once credentials exist."""
    count, source, _links = collect_originals(handle, since=since)
    return count, source


def build_kpi1_copy(
    *,
    handle: str,
    count: int | None,
    reason: str,
    links: list[str] | None = None,
) -> str:
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
    passed = n >= _THRESHOLD
    suffix = "passed" if passed else "failed"
    text = (
        f"Twitter operations verification: official account{who} posted {n} "
        f"original posts in the last 30 days (threshold ≥{_THRESHOLD}); "
        f"Twitter operations verification {suffix}"
    )
    urls = [str(url).strip() for url in (links or []) if str(url).strip()]
    if passed:
        urls = urls[:_LINK_LIMIT]
        text = text + "\n" + _MEETS_AUDIT
    if urls:
        text = text + "\n" + "\n".join(urls)
    return text


def evaluate_kpi1(
    *,
    handle: str,
    count: int | None,
    unread: bool,
    links: list[str] | None = None,
) -> dict[str, Any]:
    if not handle:
        return {
            "passed": False,
            "reason": "no_account",
            "copy": build_kpi1_copy(handle="", count=None, reason="no_account"),
            "count": 0,
            "links": [],
        }
    if unread or count is None:
        return {
            "passed": False,
            "reason": "unread",
            "copy": build_kpi1_copy(handle=handle, count=None, reason="unread"),
            "count": None,
            "links": [],
        }
    passed = count >= _THRESHOLD
    urls = list(links or [])
    return {
        "passed": passed,
        "reason": "pass" if passed else "below_threshold",
        "copy": build_kpi1_copy(handle=handle, count=count, reason="ok", links=urls),
        "count": count,
        "links": urls[:_LINK_LIMIT] if passed else urls,
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
    links: list[str] = []
    rows: list[tuple[datetime, str, dict[str, Any]]] = []
    if handle:
        source, fetched = fetch_timeline(handle, since=since)
        if fetched is None:
            unread = True
            logger.info("kpi1: handle=%s source=unread", handle)
        else:
            rows = fetched
            count = sum(
                1
                for dt, text, extra in rows
                if dt >= since and not is_retweet(text, extra)
            )
            links = original_status_links(handle, rows, since=since)
            logger.info(
                "kpi1: handle=%s source=%s count=%s links=%s",
                handle,
                source,
                count,
                len(links),
            )
    pr_url = ""
    if handle and rows:
        pr_url = maybe_write_kpi2_from_tweets(
            token,
            config,
            rid,
            fields,
            project_name=name,
            handle=handle,
            rows=rows,
            since=since,
        )
    verdict = evaluate_kpi1(handle=handle, count=count, unread=unread, links=links)
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
        "pr_url": pr_url,
    }
