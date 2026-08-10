"""Fetch project site header logo and upload to Lark Bitable attachment field."""

from __future__ import annotations

import base64
import io
import logging
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests

from bot.lark_bitable import update_record

logger = logging.getLogger(__name__)

API = "https://open.larksuite.com/open-apis"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def link_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, dict):
        return str(v.get("link") or v.get("url") or v.get("text") or "").strip()
    if isinstance(v, list) and v:
        return link_str(v[0])
    return str(v).strip()


def extract_urls(text: str) -> list[str]:
    if not text:
        return []
    text = text.replace("\n", " ")
    found = re.findall(r"https?://[^\s<>\"']+", text, flags=re.I)
    for m in re.findall(
        r"(?<![/@\w])(?:www\.)?[a-z0-9][-a-z0-9.]*\.[a-z]{2,}(?:/[^\s]*)?",
        text,
        flags=re.I,
    ):
        if "http" in m.lower():
            continue
        if any(x in m.lower() for x in ("telegram", "t.me", "x.com", "twitter", "linkedin", "@")):
            continue
        found.append("https://" + m.lstrip("/"))
    out: list[str] = []
    seen: set[str] = set()
    for u in found:
        u = u.rstrip(").,;'\">]")
        low = u.lower()
        if any(
            b in low
            for b in ("t.me/", "telegram.", "x.com/", "twitter.com", "linkedin.com", "docs.google")
        ):
            continue
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def pick_site_url(fields: dict[str, Any], live_link_field: str, project_link_field: str) -> str | None:
    urls = extract_urls(link_str(fields.get(live_link_field)))
    if not urls:
        urls = extract_urls(link_str(fields.get(project_link_field)))
    return urls[0] if urls else None


def _proxy_dict() -> dict[str, str] | None:
    raw = (
        os.getenv("HTTPS_PROXY")
        or os.getenv("https_proxy")
        or os.getenv("HTTP_PROXY")
        or os.getenv("http_proxy")
        or os.getenv("TELEGRAM_PROXY")
        or ""
    ).strip()
    if not raw:
        return None
    return {"http": raw, "https": raw}


def http_get(url: str, timeout: float = 12.0) -> requests.Response | None:
    headers = {"User-Agent": UA, "Accept": "*/*"}
    attempts: list[dict[str, str] | None] = [None]
    px = _proxy_dict()
    if px:
        attempts.append(px)
    for proxies in attempts:
        try:
            return requests.get(
                url,
                timeout=(4.0, timeout),
                headers=headers,
                proxies=proxies,
                allow_redirects=True,
            )
        except Exception:  # noqa: BLE001
            continue
    return None


def _is_image_bytes(data: bytes, ctype: str) -> bool:
    ctype = (ctype or "").lower()
    if "text/html" in ctype:
        return False
    stripped = data.lstrip()
    is_svg = stripped.startswith(b"<svg") or (
        stripped.startswith(b"<?xml") and b"<svg" in data[:500]
    )
    if is_svg:
        return len(data) >= 32
    if len(data) < 64:
        return False
    return (
        "image" in ctype
        or data[:8].startswith(b"\x89PNG")
        or data[:3] == b"\xff\xd8\xff"
        or data[:4] == b"\x00\x00\x01\x00"
        or data[:4] == b"RIFF"
        or is_svg
    )


def _fname_for(data: bytes, url: str) -> str:
    if data.lstrip().startswith(b"<svg") or (
        data.lstrip().startswith(b"<?xml") and b"<svg" in data[:500]
    ):
        return "logo.svg"
    if data[:3] == b"\xff\xd8\xff":
        return "logo.jpg"
    if data[:4] == b"\x00\x00\x01\x00" or url.lower().endswith(".ico"):
        return "logo.ico"
    if data[:4] == b"RIFF":
        return "logo.webp"
    path = urlparse(url).path.lower()
    for ext in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".ico"):
        if path.endswith(ext):
            return f"logo{ext if ext != '.jpeg' else '.jpg'}"
    return "logo.png"


def download_image(url: str) -> tuple[bytes, str] | None:
    if not url:
        return None
    if url.startswith("data:image"):
        try:
            header, b64 = url.split(",", 1)
            raw = base64.b64decode(b64)
            ext = "png"
            if "svg" in header:
                ext = "svg"
            elif "jpeg" in header or "jpg" in header:
                ext = "jpg"
            elif "webp" in header:
                ext = "webp"
            if len(raw) >= 32:
                return raw, f"logo.{ext}"
        except Exception:
            return None
        return None
    if url.startswith("data:"):
        return None
    r = http_get(url, timeout=10.0)
    if r is None:
        return None
    data = r.content or b""
    ctype = r.headers.get("content-type") or ""
    if not _is_image_bytes(data, ctype):
        return None
    return data, _fname_for(data, url)


def _attr(tag: str, name: str) -> str | None:
    m = re.search(rf"""{name}\s*=\s*["']([^"']+)["']""", tag, flags=re.I)
    return m.group(1).strip() if m else None


def logo_candidates_from_html(html: str, base_url: str) -> list[str]:
    scored: list[tuple[int, int, str]] = []

    def add(url: str | None, score: int, order: int) -> None:
        if not url:
            return
        url = url.strip()
        if not url or url.startswith("javascript:"):
            return
        scored.append((-score, order, urljoin(base_url, url)))

    order = 0
    head = html[:12000]
    body_m = re.search(r"<body[^>]*>(.*)$", html, flags=re.I | re.S)
    top = (body_m.group(1) if body_m else html)[:25000]
    header_chunks = re.findall(
        r"<(?:header|nav)[^>]*>.*?</(?:header|nav)>",
        top,
        flags=re.I | re.S,
    )
    region = "\n".join(header_chunks) if header_chunks else top[:12000]

    for tag in re.findall(r"<img\b[^>]*>", region, flags=re.I):
        src = _attr(tag, "src") or _attr(tag, "data-src") or _attr(tag, "data-lazy-src")
        srcset = _attr(tag, "srcset")
        if srcset and not src:
            src = srcset.split(",")[0].strip().split(" ")[0]
        alt = (_attr(tag, "alt") or "").lower()
        cls = (_attr(tag, "class") or "").lower()
        tid = (_attr(tag, "id") or "").lower()
        blob = f"{alt} {cls} {tid} {(src or '').lower()}"
        score = 40
        if any(k in blob for k in ("logo", "brand", "site-title", "navbar-brand")):
            score += 50
        if any(k in blob for k in ("avatar", "icon-user", "profile", "hero", "banner", "bg-")):
            score -= 30
        if src and any(src.lower().endswith(e) for e in (".svg", ".png", ".webp", ".jpg", ".jpeg")):
            score += 10
        add(src, score, order)
        order += 1

    for m in re.finditer(r"""<link\b[^>]*rel=["']([^"']+)["'][^>]*>""", head, flags=re.I):
        rel = m.group(1).lower()
        href = _attr(m.group(0), "href")
        if "apple-touch-icon" in rel:
            add(href, 35, order)
        elif "icon" in rel:
            add(href, 25, order)
        order += 1
    for m in re.finditer(
        r"""<link\b[^>]*href=["']([^"']+)["'][^>]*rel=["']([^"']+)["'][^>]*>""",
        head,
        flags=re.I,
    ):
        href, rel = m.group(1), m.group(2).lower()
        if "apple-touch-icon" in rel:
            add(href, 35, order)
        elif "icon" in rel:
            add(href, 25, order)
        order += 1

    for pat, score in (
        (r"""property=["']og:image["'][^>]*content=["']([^"']+)["']""", 20),
        (r"""content=["']([^"']+)["'][^>]*property=["']og:image["']""", 20),
        (r"""name=["']twitter:image["'][^>]*content=["']([^"']+)["']""", 15),
    ):
        m = re.search(pat, head, flags=re.I)
        if m:
            add(m.group(1), score, order)
            order += 1

    scored.sort()
    out: list[str] = []
    seen: set[str] = set()
    for _, _, u in scored:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def fetch_logo_via_browser(site: str) -> tuple[bytes, str] | None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None

    js = """
() => {
  const isLogoish = (el) => {
    const blob = [
      el.alt || '', el.className || '', el.id || '',
      el.getAttribute('src') || '', el.getAttribute('aria-label') || ''
    ].join(' ').toLowerCase();
    return /logo|brand|navbar-brand|site-title/.test(blob);
  };
  const pickImg = (root) => {
    const imgs = [...root.querySelectorAll('img')].filter(img => {
      const r = img.getBoundingClientRect();
      return r.width >= 12 && r.height >= 12 && r.top < 160 && r.left < 480;
    });
    imgs.sort((a, b) => {
      const sa = (isLogoish(a) ? 0 : 1) * 1000 + a.getBoundingClientRect().left + a.getBoundingClientRect().top;
      const sb = (isLogoish(b) ? 0 : 1) * 1000 + b.getBoundingClientRect().left + b.getBoundingClientRect().top;
      return sa - sb;
    });
    return imgs[0] || null;
  };
  const header = document.querySelector('header, nav, [class*="navbar"], [class*="header"]') || document.body;
  const img = pickImg(header) || pickImg(document.body);
  if (img) {
    const src = img.currentSrc || img.src || '';
    if (src && !src.startsWith('data:image/svg')) return { type: 'url', src };
    return { type: 'el' };
  }
  const svg = [...document.querySelectorAll('header svg, nav svg, a svg')]
    .find(el => {
      const r = el.getBoundingClientRect();
      return r.width >= 12 && r.height >= 12 && r.top < 160 && r.left < 400;
    });
  if (svg) return { type: 'el' };
  const icon = document.querySelector('link[rel*="icon"]');
  if (icon && icon.href) return { type: 'url', src: icon.href };
  return null;
}
"""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(user_agent=UA, ignore_https_errors=True)
            page = context.new_page()
            page.set_default_timeout(20000)
            page.goto(site, wait_until="domcontentloaded")
            try:
                page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass
            page.wait_for_timeout(800)
            info = page.evaluate(js)
            result: tuple[bytes, str] | None = None
            if info and info.get("type") == "url" and info.get("src"):
                result = download_image(info["src"])
            if result is None and info:
                loc = page.locator(
                    "header img, nav img, a img, header svg, nav svg, img"
                ).first
                try:
                    if loc.is_visible(timeout=2000):
                        png = loc.screenshot(type="png")
                        if png and len(png) >= 64:
                            result = (png, "logo.png")
                except Exception:
                    png = page.screenshot(
                        type="png",
                        clip={"x": 0, "y": 0, "width": 220, "height": 80},
                    )
                    if png and len(png) >= 64:
                        result = (png, "logo.png")
            browser.close()
            return result
    except Exception:
        logger.debug("browser logo fetch failed for %s", site, exc_info=True)
        return None


def fetch_logo_from_site(site: str) -> tuple[bytes, str] | None:
    page = http_get(site, timeout=15.0)
    if page is None or not page.text:
        p = urlparse(site if "://" in site else f"https://{site}")
        origin = f"{p.scheme or 'https'}://{p.netloc}"
        page = http_get(origin, timeout=15.0)
    if page is not None:
        final_url = page.url or site
        html = page.text or ""
        for img_url in logo_candidates_from_html(html, final_url):
            got = download_image(img_url)
            if got:
                return got
        p = urlparse(final_url)
        origin = f"{p.scheme}://{p.netloc}"
        for path in (
            "/apple-touch-icon.png",
            "/favicon.ico",
            "/favicon.png",
            "/logo.svg",
            "/logo.png",
            "/vite.svg",
        ):
            got = download_image(origin + path)
            if got:
                return got
    return fetch_logo_via_browser(site)


def upload_bitable_image(
    token: str,
    base_app_token: str,
    file_bytes: bytes,
    file_name: str,
) -> str:
    last: dict[str, Any] = {}
    for parent_type in ("bitable_image", "bitable_file"):
        data = {
            "file_name": file_name,
            "parent_type": parent_type,
            "parent_node": base_app_token,
            "size": str(len(file_bytes)),
        }
        files = {"file": (file_name, io.BytesIO(file_bytes), "application/octet-stream")}
        resp = requests.post(
            f"{API}/drive/v1/medias/upload_all",
            headers={"Authorization": f"Bearer {token}"},
            data=data,
            files=files,
            timeout=45,
        )
        last = resp.json()
        if last.get("code") == 0:
            ft = (last.get("data") or {}).get("file_token")
            if ft:
                return str(ft)
    raise RuntimeError(f"upload failed: {last}")


def fill_logo_for_record(
    token: str,
    base_app_token: str,
    table_id: str,
    record_id: str,
    project_name: str,
    site_url: str,
    logo_field: str,
) -> str:
    """Fetch logo from site and write attachment. Returns ok:... or error code."""
    logo = fetch_logo_from_site(site_url)
    if not logo:
        return "no_logo"
    data, fname = logo
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", project_name)[:40] or "project"
    ext = Path(fname).suffix or ".png"
    file_token = upload_bitable_image(token, base_app_token, data, f"{safe}{ext}")
    update_record(
        token,
        base_app_token,
        table_id,
        record_id,
        {logo_field: [{"file_token": file_token}]},
    )
    return f"ok:{len(data)}"
