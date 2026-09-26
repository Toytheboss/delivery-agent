"""KPI 3 website check: run once when a project goes mainnet-live.

Pass when the site opens, shows the project name (fallback: a logo), and has
clickable https://botchain.ai and https://scan.botchain.ai links. A missing
website URL is an automatic fail. Does not write KPI coordination or push groups.
"""

from __future__ import annotations

import html as html_lib
import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin, urlparse

import requests

from bot.lark_bitable import update_record
from bot.project_logo import _proxy_dict, pick_site_url
from bot.workflow_form_dispatch import _normalize_name

if TYPE_CHECKING:
    from bot.config_loader import AppConfig

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_DEFAULT_COPY_FIELD = "KPI 3 - 官网展示验证"
_DEFAULT_RESULT_FIELD = "官网验证结果"
_PASS = "通过"
_FAIL = "不通过"
_A_HREF_RE = re.compile(
    r"""<a\b[^>]*?\bhref\s*=\s*(?:["']([^"']+)["']|([^\s>]+))""",
    flags=re.I,
)
_IMG_RE = re.compile(r"<img\b[^>]*>", flags=re.I)
_SCRIPT_STYLE_RE = re.compile(r"(?is)<(script|style)\b[^>]*>.*?</\1>")
_TAG_RE = re.compile(r"(?is)<[^>]+>")

_BROWSER_UNAVAILABLE = False


@dataclass(frozen=True)
class WebsiteProbe:
    url: str
    opened: bool
    hrefs: tuple[str, ...]
    text: str
    has_logo: bool
    error: str = ""


@dataclass(frozen=True)
class Kpi3Verdict:
    passed: bool
    result: str
    copy: str
    url: str
    has_name: bool
    has_logo: bool
    has_botchain: bool
    has_scan: bool
    opened: bool
    reason: str


def kpi3_result_fields(
    *,
    copy_field: str,
    result_field: str,
    copy: str,
    result: str,
) -> dict[str, Any]:
    """SingleSelect must be a string, not the read-shape array."""
    return {copy_field: copy, result_field: result}


def href_host(url: str) -> str:
    try:
        host = (urlparse(url).netloc or "").lower()
    except ValueError:
        return ""
    if host.startswith("www."):
        host = host[4:]
    return host


def is_botchain_href(url: str) -> bool:
    return href_host(url) == "botchain.ai"


def is_scan_href(url: str) -> bool:
    return href_host(url) == "scan.botchain.ai"


def extract_anchor_hrefs(html: str, base_url: str = "") -> list[str]:
    """Collect <a href> only. Script/config URLs do not count as clickable."""
    out: list[str] = []
    seen: set[str] = set()
    for match in _A_HREF_RE.finditer(html or ""):
        raw = (match.group(1) or match.group(2) or "").strip()
        if not raw or raw.startswith(("#", "javascript:", "mailto:")):
            continue
        abs_url = urljoin(base_url, raw) if base_url else raw
        if abs_url not in seen:
            seen.add(abs_url)
            out.append(abs_url)
    return out


def visible_text(html: str) -> str:
    cleaned = _SCRIPT_STYLE_RE.sub(" ", html or "")
    cleaned = _TAG_RE.sub(" ", cleaned)
    return re.sub(r"\s+", " ", html_lib.unescape(cleaned)).strip()


def html_has_logo(html: str) -> bool:
    blob = html or ""
    for tag in _IMG_RE.findall(blob):
        low = tag.lower()
        if "logo" in low or "brand" in low:
            return True
    return bool(
        re.search(
            r"<(header|nav)\b[^>]*>[\s\S]{0,8000}?<img\b",
            blob,
            flags=re.I,
        )
    )


def page_has_project_name(project_name: str, text: str) -> bool:
    name = (project_name or "").strip()
    if not name or not (text or "").strip():
        return False
    needle = _normalize_name(name)
    haystack = text or ""
    if len(needle) < 3:
        return bool(re.search(rf"\b{re.escape(name)}\b", haystack, flags=re.I))
    return needle in _normalize_name(haystack)


def build_kpi3_copy(verdict: Kpi3Verdict, project_name: str) -> str:
    name = (project_name or "").strip() or "该项目"
    if verdict.reason == "no_url":
        return "官网展示验证，未提交官网链接，官网展示验证不通过"
    if not verdict.opened:
        return "官网展示验证，官网无法访问，官网展示验证不通过"

    identity = ""
    if verdict.has_name:
        identity = f"可见项目名称 {name}"
    elif verdict.has_logo:
        identity = "未见项目名称但可见 Logo"
    else:
        identity = "未见项目名称或 Logo"

    bot = "https://botchain.ai"
    scan = "https://scan.botchain.ai"
    if verdict.has_botchain and verdict.has_scan:
        links = f"页面有可点击的 {bot} 和 {scan}"
    elif verdict.has_scan and not verdict.has_botchain:
        links = f"有可点击的 {scan}，但没有可点击的 {bot}"
    elif verdict.has_botchain and not verdict.has_scan:
        links = f"有可点击的 {bot}，但没有可点击的 {scan}"
    else:
        links = f"没有可点击的 {bot} 和 {scan}"

    suffix = "官网展示验证通过" if verdict.passed else "官网展示验证不通过"
    return f"官网展示验证，官网可访问，{identity}，{links}，{suffix}"


def evaluate_kpi3(
    *,
    project_name: str,
    probe: WebsiteProbe | None,
    url: str = "",
) -> Kpi3Verdict:
    if not url:
        verdict = Kpi3Verdict(
            passed=False,
            result=_FAIL,
            copy="",
            url="",
            has_name=False,
            has_logo=False,
            has_botchain=False,
            has_scan=False,
            opened=False,
            reason="no_url",
        )
        return Kpi3Verdict(**{**verdict.__dict__, "copy": build_kpi3_copy(verdict, project_name)})
    if probe is None or not probe.opened:
        verdict = Kpi3Verdict(
            passed=False,
            result=_FAIL,
            copy="",
            url=url,
            has_name=False,
            has_logo=bool(probe.has_logo) if probe else False,
            has_botchain=False,
            has_scan=False,
            opened=False,
            reason="unreachable",
        )
        return Kpi3Verdict(**{**verdict.__dict__, "copy": build_kpi3_copy(verdict, project_name)})

    hrefs = probe.hrefs
    has_botchain = any(is_botchain_href(h) for h in hrefs)
    has_scan = any(is_scan_href(h) for h in hrefs)
    has_name = page_has_project_name(project_name, probe.text)
    has_logo = bool(probe.has_logo)
    identity_ok = has_name or has_logo
    passed = identity_ok and has_botchain and has_scan
    if not identity_ok:
        reason = "no_name_or_logo"
    elif not has_botchain or not has_scan:
        reason = "missing_official_link"
    else:
        reason = "passed"
    verdict = Kpi3Verdict(
        passed=passed,
        result=_PASS if passed else _FAIL,
        copy="",
        url=url,
        has_name=has_name,
        has_logo=has_logo,
        has_botchain=has_botchain,
        has_scan=has_scan,
        opened=True,
        reason=reason,
    )
    return Kpi3Verdict(**{**verdict.__dict__, "copy": build_kpi3_copy(verdict, project_name)})


def _http_probe(url: str, timeout: float = 12.0) -> WebsiteProbe:
    try:
        resp = requests.get(
            url,
            timeout=timeout,
            allow_redirects=True,
            headers={"User-Agent": UA},
            proxies=_proxy_dict(),
        )
    except Exception as exc:  # noqa: BLE001
        return WebsiteProbe(url=url, opened=False, hrefs=(), text="", has_logo=False, error=str(exc)[:160])
    html = resp.text or ""
    final = str(resp.url or url)
    opened = 200 <= int(resp.status_code or 0) < 400
    return WebsiteProbe(
        url=final,
        opened=opened,
        hrefs=tuple(extract_anchor_hrefs(html, final)),
        text=visible_text(html),
        has_logo=html_has_logo(html),
        error="" if opened else f"http {resp.status_code}",
    )


def _browser_probe(url: str) -> WebsiteProbe | None:
    global _BROWSER_UNAVAILABLE
    if _BROWSER_UNAVAILABLE:
        return None
    os.environ.setdefault(
        "PLAYWRIGHT_BROWSERS_PATH",
        str(ROOT / ".cache" / "ms-playwright"),
    )
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    js = """
() => {
  const hrefs = [...document.querySelectorAll('a[href]')].map(a => a.href);
  const img = document.querySelector(
    'img[alt*="logo" i], img[class*="logo" i], img[id*="logo" i], header img, nav img'
  );
  return {
    title: document.title || '',
    text: (document.body && document.body.innerText || '').slice(0, 40000),
    hrefs,
    hasLogo: Boolean(img)
  };
}
"""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_default_timeout(15000)
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(1500)
            data = page.evaluate(js) or {}
            browser.close()
    except Exception as exc:  # noqa: BLE001
        logger.info("kpi3: playwright probe failed url=%s err=%s", url[:80], str(exc)[:120])
        if "Executable doesn't exist" in str(exc) or "playwright" in str(exc).lower() and "chromium" in str(exc).lower():
            _BROWSER_UNAVAILABLE = True
        return None
    hrefs = tuple(str(x) for x in (data.get("hrefs") or []) if str(x).strip())
    title = str(data.get("title") or "")
    text = f"{title} {data.get('text') or ''}".strip()
    return WebsiteProbe(
        url=url,
        opened=True,
        hrefs=hrefs,
        text=text,
        has_logo=bool(data.get("hasLogo")),
    )


def probe_website(url: str) -> WebsiteProbe:
    http = _http_probe(url)
    needs_browser = (not http.opened) or (not any(is_botchain_href(h) for h in http.hrefs)) or (
        not any(is_scan_href(h) for h in http.hrefs)
    )
    if not needs_browser:
        return http
    browser = _browser_probe(url)
    if browser is None:
        return http
    if not browser.opened and http.opened:
        return http
    merged_hrefs = tuple(dict.fromkeys([*http.hrefs, *browser.hrefs]))
    return WebsiteProbe(
        url=browser.url or http.url,
        opened=http.opened or browser.opened,
        hrefs=merged_hrefs,
        text=browser.text or http.text,
        has_logo=http.has_logo or browser.has_logo,
        error=browser.error or http.error,
    )


def _state_path(config: AppConfig) -> Path:
    return ROOT / str(
        getattr(config, "workflow_kpi3_state_file", "data/kpi3_website_state.json")
    )


def _load_state(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    results = raw.get("results") if isinstance(raw, dict) else None
    if not isinstance(results, dict):
        return {}
    return {str(k): str(v) for k, v in results.items()}


def _save_state(path: Path, results: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"results": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def audit_kpi3_for_fields(
    token: str,
    config: AppConfig,
    record_id: str,
    fields: dict[str, Any],
    *,
    project_name: str = "",
) -> str:
    """Write KPI 3 copy + result for one live record. Skip if already audited."""
    if not getattr(config, "workflow_kpi3_enabled", True):
        return "disabled"
    rid = (record_id or "").strip()
    if not rid:
        return "no_record"
    path = _state_path(config)
    state = _load_state(path)
    if rid in state:
        return f"already:{state[rid]}"

    from bot.workflow_form_dispatch import _field_text

    name = (project_name or "").strip() or _field_text(
        fields, config.workflow_project_name_field
    )
    url = pick_site_url(
        fields,
        str(getattr(config, "workflow_live_link_field", "") or "已上线链接🔗"),
        str(getattr(config, "workflow_project_link_field", "") or "项目链接"),
    ) or ""
    probe = probe_website(url) if url else None
    verdict = evaluate_kpi3(project_name=name, probe=probe, url=url)
    copy_field = str(
        getattr(config, "workflow_kpi3_copy_field", "") or _DEFAULT_COPY_FIELD
    )
    result_field = str(
        getattr(config, "workflow_kpi3_result_field", "") or _DEFAULT_RESULT_FIELD
    )
    payload = kpi3_result_fields(
        copy_field=copy_field,
        result_field=result_field,
        copy=verdict.copy,
        result=verdict.result,
    )
    try:
        update_record(
            token,
            config.workflow_base_app_token,
            config.workflow_progress_table_id,
            rid,
            payload,
        )
    except Exception:
        logger.exception("kpi3: failed to write result project=%r record=%s", name, rid)
        return "write_failed"
    state[rid] = verdict.result
    _save_state(path, state)
    logger.info(
        "kpi3: %s project=%r record=%s url=%s reason=%s",
        verdict.result,
        name,
        rid,
        (url or "")[:80],
        verdict.reason,
    )
    return verdict.result


async def audit_kpi3_for_live_record(
    config: AppConfig,
    token: str,
    record_id: str,
    fields: dict[str, Any],
    *,
    project_name: str = "",
) -> str:
    import asyncio

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        lambda: audit_kpi3_for_fields(
            token, config, record_id, fields, project_name=project_name
        ),
    )
