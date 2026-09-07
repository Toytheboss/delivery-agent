"""Fetch project site header logo and upload to Lark Bitable attachment field."""

from __future__ import annotations

import base64
import io
import json
import logging
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse, unquote

import requests

from bot.lark_bitable import update_record

logger = logging.getLogger(__name__)

API = "https://open.larksuite.com/open-apis"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Paths that are unlikely to be the marketing homepage for logo scraping.
_NON_HOME_PATH_RE = re.compile(
    r"^/(proof|app|dashboard|admin|login|signup|docs?|api|whitepaper|"
    r"blog|news|faq|support|download|bridge|swap|stake|mint)(/|$)",
    flags=re.I,
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
        if any(
            x in m.lower()
            for x in ("telegram", "t.me", "x.com", "twitter", "linkedin", "@")
        ):
            continue
        found.append("https://" + m.lstrip("/"))
    out: list[str] = []
    seen: set[str] = set()
    for u in found:
        u = u.rstrip(").,;'\">]")
        low = u.lower()
        if any(
            b in low
            for b in (
                "t.me/",
                "telegram.",
                "x.com/",
                "twitter.com",
                "linkedin.com",
                "docs.google",
            )
        ):
            continue
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def pick_site_url(
    fields: dict[str, Any], live_link_field: str, project_link_field: str
) -> str | None:
    urls = extract_urls(link_str(fields.get(live_link_field)))
    if not urls:
        urls = extract_urls(link_str(fields.get(project_link_field)))
    return urls[0] if urls else None


def _site_variants(site: str) -> list[str]:
    """Homepage-first variants: origin, https upgrade, strip non-home paths."""
    raw = (site or "").strip()
    if not raw:
        return []
    if "://" not in raw:
        raw = "https://" + raw
    parsed = urlparse(raw)
    scheme = parsed.scheme or "https"
    netloc = parsed.netloc
    if not netloc:
        return [raw]
    origin = f"{scheme}://{netloc}"
    path = parsed.path or "/"
    variants: list[str] = []

    def add(u: str) -> None:
        if u and u not in variants:
            variants.append(u)

    # Prefer marketing homepage over deep links (/proof, /app, ...).
    if path in ("", "/") or _NON_HOME_PATH_RE.match(path):
        add(origin + "/")
    else:
        add(raw if raw.endswith("/") or "." in path.rsplit("/", 1)[-1] else raw)
        add(origin + "/")
    if scheme == "http":
        add("https://" + netloc + "/")
    add(raw)
    return variants


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
    headers = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
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
    if "text/html" in ctype or "application/json" in ctype:
        return False
    stripped = data.lstrip()
    is_svg = stripped.startswith(b"<svg") or (
        stripped.startswith(b"<?xml") and b"<svg" in data[:800]
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


def _image_quality_ok(data: bytes, fname: str) -> bool:
    """Reject tiny/corrupt rasters that are usually wrong favicons/screenshots."""
    if not data:
        return False
    low = (fname or "").lower()
    stripped = data.lstrip()
    if stripped.startswith(b"<svg") or (
        stripped.startswith(b"<?xml") and b"<svg" in data[:800]
    ):
        return len(data) >= 32
    # ICO can be small but useful; allow slightly lower floor.
    if low.endswith(".ico") or data[:4] == b"\x00\x00\x01\x00":
        return len(data) >= 64
    # Very small PNG/JPG screenshots are usually empty chrome, not logos.
    if len(data) < 280:
        return False
    return True


def _fname_for(data: bytes, url: str) -> str:
    if data.lstrip().startswith(b"<svg") or (
        data.lstrip().startswith(b"<?xml") and b"<svg" in data[:800]
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
    if url.startswith("data:image/svg"):
        return "logo.svg"
    return "logo.png"


def _decode_data_uri(url: str) -> tuple[bytes, str] | None:
    if not url.startswith("data:image"):
        return None
    try:
        header, payload = url.split(",", 1)
    except ValueError:
        return None
    try:
        if ";base64" in header.lower():
            raw = base64.b64decode(payload, validate=False)
        else:
            raw = unquote(payload).encode("utf-8", errors="ignore")
    except Exception:
        return None
    ext = "png"
    h = header.lower()
    if "svg" in h:
        ext = "svg"
    elif "jpeg" in h or "jpg" in h:
        ext = "jpg"
    elif "webp" in h:
        ext = "webp"
    elif "gif" in h:
        ext = "gif"
    elif "x-icon" in h or "vnd.microsoft.icon" in h:
        ext = "ico"
    if len(raw) < 32:
        return None
    fname = f"logo.{ext}"
    if not _image_quality_ok(raw, fname):
        return None
    return raw, fname


def download_image(url: str) -> tuple[bytes, str] | None:
    if not url:
        return None
    if url.startswith("data:image"):
        return _decode_data_uri(url)
    if url.startswith("data:"):
        return None
    # Truncated data URIs sometimes appear from regex; skip junk.
    if "data:image" in url and not url.startswith("data:"):
        return None
    r = http_get(url, timeout=10.0)
    if r is None:
        return None
    data = r.content or b""
    ctype = r.headers.get("content-type") or ""
    if not _is_image_bytes(data, ctype):
        return None
    fname = _fname_for(data, url)
    if not _image_quality_ok(data, fname):
        return None
    return data, fname


def _attr(tag: str, name: str) -> str | None:
    m = re.search(rf"""{name}\s*=\s*["']([^"']+)["']""", tag, flags=re.I)
    return m.group(1).strip() if m else None


def _extract_data_image_uris(html: str) -> list[str]:
    """Pull full data:image... URIs (including unquoted / percent-encoded SVG)."""
    out: list[str] = []
    for m in re.finditer(
        r"data:image\/[a-z0-9.+-]+(?:;[^,=\s\"'>]+)?,.*?(?=[\"'\s\)]|$)",
        html,
        flags=re.I,
    ):
        uri = m.group(0).rstrip("\"')>;,")
        if len(uri) >= 40:
            out.append(uri)
    return out


def logo_candidates_from_html(html: str, base_url: str) -> list[str]:
    scored: list[tuple[int, int, str]] = []

    def add(url: str | None, score: int, order: int) -> None:
        if not url:
            return
        url = url.strip()
        if not url or url.startswith("javascript:"):
            return
        # Prefer absolute / joined; keep full data URIs intact.
        if url.startswith("data:"):
            scored.append((-score, order, url))
        else:
            scored.append((-score, order, urljoin(base_url, url)))

    order = 0
    head = html[:20000]
    body_m = re.search(r"<body[^>]*>(.*)$", html, flags=re.I | re.S)
    top = (body_m.group(1) if body_m else html)[:40000]
    header_chunks = re.findall(
        r"<(?:header|nav)[^>]*>.*?</(?:header|nav)>",
        top,
        flags=re.I | re.S,
    )
    region = "\n".join(header_chunks) if header_chunks else top[:20000]

    for tag in re.findall(r"<img\b[^>]*>", region, flags=re.I):
        src = (
            _attr(tag, "src")
            or _attr(tag, "data-src")
            or _attr(tag, "data-lazy-src")
            or _attr(tag, "data-original")
        )
        srcset = _attr(tag, "srcset") or _attr(tag, "data-srcset")
        if srcset and (not src or src.startswith("data:image/gif")):
            # pick largest candidate from srcset
            parts = [p.strip().split(" ")[0] for p in srcset.split(",") if p.strip()]
            if parts:
                src = parts[-1]
        alt = (_attr(tag, "alt") or "").lower()
        cls = (_attr(tag, "class") or "").lower()
        tid = (_attr(tag, "id") or "").lower()
        blob = f"{alt} {cls} {tid} {(src or '').lower()}"
        score = 40
        if any(k in blob for k in ("logo", "brand", "site-title", "navbar-brand")):
            score += 55
        if any(
            k in blob
            for k in ("avatar", "icon-user", "profile", "hero", "banner", "bg-", "cover")
        ):
            score -= 35
        if src and any(
            src.lower().endswith(e) for e in (".svg", ".png", ".webp", ".jpg", ".jpeg")
        ):
            score += 10
        if src and "/_next/image" in src:
            score += 15
        add(src, score, order)
        order += 1

    # Whole-page imgs with explicit logo/brand hints (outside header scrape window).
    for tag in re.findall(r"<img\b[^>]*>", html[:80000], flags=re.I):
        blob = tag.lower()
        if not any(k in blob for k in ("logo", "brand", "navbar-brand", "site-title")):
            continue
        src = (
            _attr(tag, "src")
            or _attr(tag, "data-src")
            or _attr(tag, "data-lazy-src")
            or _attr(tag, "data-original")
        )
        add(src, 70, order)
        order += 1

    for m in re.finditer(r"""<link\b[^>]*>""", head, flags=re.I):
        tag = m.group(0)
        rel = (_attr(tag, "rel") or "").lower()
        href = _attr(tag, "href")
        sizes = (_attr(tag, "sizes") or "").lower()
        if "apple-touch-icon" in rel:
            score = 48
            if "180" in sizes or "192" in sizes:
                score += 8
            add(href, score, order)
        elif "icon" in rel and "mask-icon" not in rel:
            score = 28
            if "32" in sizes or "48" in sizes or "96" in sizes or "192" in sizes:
                score += 10
            if href and href.lower().endswith(".svg"):
                score += 12
            add(href, score, order)
        elif "manifest" in rel and href:
            add(href, 5, order)  # marker; expanded later
        order += 1

    for pat, score in (
        (r"""property=["']og:image:secure_url["'][^>]*content=["']([^"']+)["']""", 22),
        (r"""property=["']og:image["'][^>]*content=["']([^"']+)["']""", 18),
        (r"""content=["']([^"']+)["'][^>]*property=["']og:image["']""", 18),
        (r"""name=["']twitter:image["'][^>]*content=["']([^"']+)["']""", 14),
        (r"""content=["']([^"']+)["'][^>]*name=["']twitter:image["']""", 14),
        (r""""logo"\s*:\s*\{\s*"@type"\s*:\s*"ImageObject"[^}]*"url"\s*:\s*"([^"]+)" """, 45),
        (r""""logo"\s*:\s*"([^"]+)" """, 40),
    ):
        m = re.search(pat, head, flags=re.I | re.S)
        if m:
            add(m.group(1), score, order)
            order += 1

    # Inline CSS / Next media paths that look like logos.
    for m in re.finditer(
        r"""(?:url\(|["'])(/_next/static/media/[^"'\)\s]+\.(?:png|svg|webp|jpg|jpeg))""",
        html[:100000],
        flags=re.I,
    ):
        path = m.group(1)
        score = 30
        if "logo" in path.lower() or "brand" in path.lower():
            score += 40
        add(path, score, order)
        order += 1

    for m in re.finditer(
        r"""url\((['"]?)([^)'\"]+\.(?:png|svg|webp|jpg|jpeg|ico))\1\)""",
        html[:100000],
        flags=re.I,
    ):
        path = m.group(2)
        score = 20
        if any(k in path.lower() for k in ("logo", "brand", "icon")):
            score += 35
        add(path, score, order)
        order += 1

    for uri in _extract_data_image_uris(region + "\n" + head):
        score = 45 if "svg" in uri[:40].lower() else 25
        add(uri, score, order)
        order += 1

    scored.sort()
    out: list[str] = []
    seen: set[str] = set()
    for _, _, u in scored:
        key = u if u.startswith("data:") else u.split("?", 1)[0]
        if key not in seen:
            seen.add(key)
            out.append(u)
    return out


def _manifest_icons(manifest_url: str) -> list[str]:
    r = http_get(manifest_url, timeout=8.0)
    if r is None or not r.content:
        return []
    try:
        data = r.json()
    except Exception:
        try:
            data = json.loads(r.text)
        except Exception:
            return []
    icons = data.get("icons") or []
    ranked: list[tuple[int, str]] = []
    for icon in icons:
        if not isinstance(icon, dict):
            continue
        src = str(icon.get("src") or "").strip()
        if not src:
            continue
        sizes = str(icon.get("sizes") or "0x0")
        try:
            w = int(sizes.split("x")[0])
        except Exception:
            w = 0
        ranked.append((w, urljoin(manifest_url, src)))
    ranked.sort(reverse=True)
    return [u for _, u in ranked]


def _expand_manifest_candidates(candidates: list[str], base_url: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for u in candidates:
        low = u.lower()
        if low.endswith("manifest.json") or low.endswith("site.webmanifest") or "/manifest" in low:
            for icon in _manifest_icons(u):
                if icon not in seen:
                    seen.add(icon)
                    out.append(icon)
            continue
        if u not in seen:
            seen.add(u)
            out.append(u)
    # Common manifest locations if none referenced.
    if not any("manifest" in c.lower() for c in candidates):
        p = urlparse(base_url)
        origin = f"{p.scheme}://{p.netloc}"
        for path in ("/manifest.json", "/site.webmanifest", "/manifest.webmanifest"):
            for icon in _manifest_icons(origin + path):
                if icon not in seen:
                    seen.add(icon)
                    out.append(icon)
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
      el.getAttribute('src') || '', el.getAttribute('aria-label') || '',
      el.getAttribute('data-testid') || ''
    ].join(' ').toLowerCase();
    return /logo|brand|navbar-brand|site-title|site-logo/.test(blob);
  };
  const absUrl = (u) => {
    try { return new URL(u, location.href).href; } catch { return u || ''; }
  };
  const bgUrl = (el) => {
    const bg = getComputedStyle(el).backgroundImage || '';
    const m = bg.match(/url\\(["']?(.*?)["']?\\)/i);
    return m ? absUrl(m[1]) : '';
  };
  const pickImg = (root) => {
    const imgs = [...root.querySelectorAll('img')].filter(img => {
      const r = img.getBoundingClientRect();
      return r.width >= 12 && r.height >= 12 && r.top < 200 && r.left < 560;
    });
    imgs.sort((a, b) => {
      const sa = (isLogoish(a) ? 0 : 1) * 1000 + a.getBoundingClientRect().left
        + a.getBoundingClientRect().top * 0.25;
      const sb = (isLogoish(b) ? 0 : 1) * 1000 + b.getBoundingClientRect().left
        + b.getBoundingClientRect().top * 0.25;
      return sa - sb;
    });
    return imgs[0] || null;
  };
  const header = document.querySelector(
    'header, nav, [class*="navbar" i], [class*="header" i], [class*="topbar" i]'
  ) || document.body;
  const img = pickImg(header) || pickImg(document.body);
  if (img) {
    const src = img.currentSrc || img.src || '';
    if (src) return { type: 'url', src: absUrl(src) };
    return { type: 'el', selector: 'img' };
  }
  // CSS background logos in the header band.
  const nodes = [...header.querySelectorAll('a, div, span, i, button')].slice(0, 80);
  for (const el of nodes) {
    const r = el.getBoundingClientRect();
    if (r.top > 160 || r.left > 480 || r.width < 14 || r.height < 14) continue;
    if (r.width > 420 || r.height > 160) continue;
    const u = bgUrl(el);
    if (u && /^https?:|^data:image/i.test(u) && !/gradient/i.test(u)) {
      const logoish = isLogoish(el) || /logo|brand/i.test(u);
      if (logoish || (r.width <= 220 && r.height <= 100)) {
        return { type: 'url', src: u };
      }
    }
  }
  const svg = [...document.querySelectorAll('header svg, nav svg, a svg, [class*="logo" i] svg')]
    .find(el => {
      const r = el.getBoundingClientRect();
      return r.width >= 12 && r.height >= 12 && r.top < 180 && r.left < 480;
    });
  if (svg) return { type: 'el', selector: 'svg' };
  const brand = document.querySelector(
    '[class*="logo" i], [id*="logo" i], [aria-label*="logo" i], a[class*="brand" i]'
  );
  if (brand) {
    const r = brand.getBoundingClientRect();
    if (r.width >= 20 && r.height >= 12 && r.top < 200) {
      return { type: 'brand' };
    }
  }
  const icon = document.querySelector('link[rel*="apple-touch-icon"], link[rel*="icon"]');
  if (icon && icon.href) return { type: 'url', src: icon.href };
  // Text-only brand sites: signal header clip fallback.
  return { type: 'clip' };
}
"""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=UA,
                ignore_https_errors=True,
                viewport={"width": 1280, "height": 800},
            )
            page = context.new_page()
            page.set_default_timeout(25000)
            page.goto(site, wait_until="domcontentloaded")
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass
            page.wait_for_timeout(1200)
            info = page.evaluate(js) or {"type": "clip"}
            result: tuple[bytes, str] | None = None
            if info.get("type") == "url" and info.get("src"):
                result = download_image(info["src"])
            if result is None:
                # Element screenshot for svg/img/brand text.
                selectors = [
                    "header [class*='logo' i]",
                    "nav [class*='logo' i]",
                    "[class*='logo' i]",
                    "a[class*='brand' i]",
                    "header svg",
                    "nav svg",
                    "header img",
                    "nav img",
                    "header a",
                    "nav a",
                ]
                for sel in selectors:
                    try:
                        loc = page.locator(sel).first
                        if not loc.is_visible(timeout=600):
                            continue
                        box = loc.bounding_box()
                        if not box:
                            continue
                        if box["width"] < 12 or box["height"] < 12:
                            continue
                        if box["y"] > 220:
                            continue
                        png = loc.screenshot(type="png")
                        if png and _image_quality_ok(png, "logo.png"):
                            result = (png, "logo.png")
                            break
                    except Exception:
                        continue
            if result is None:
                # Top-left brand strip — works for text-only SPA headers.
                try:
                    png = page.screenshot(
                        type="png",
                        clip={"x": 0, "y": 0, "width": 280, "height": 96},
                    )
                    if png and _image_quality_ok(png, "logo.png"):
                        result = (png, "logo.png")
                except Exception:
                    pass
            browser.close()
            return result
    except Exception:
        logger.debug("browser logo fetch failed for %s", site, exc_info=True)
        return None


def _try_candidates(candidates: list[str]) -> tuple[bytes, str] | None:
    for img_url in candidates:
        got = download_image(img_url)
        if got:
            return got
    return None


def fetch_logo_from_site(site: str) -> tuple[bytes, str] | None:
    tried_pages: set[str] = set()
    for variant in _site_variants(site):
        page = http_get(variant, timeout=15.0)
        if page is None or page.text is None:
            continue
        final_url = page.url or variant
        key = final_url.rstrip("/")
        if key in tried_pages:
            continue
        tried_pages.add(key)
        html = page.text or ""
        # Tiny SPA shells (<1KB) rarely contain assets; still try common paths + browser.
        candidates = logo_candidates_from_html(html, final_url)
        candidates = _expand_manifest_candidates(candidates, final_url)
        got = _try_candidates(candidates)
        if got:
            return got
        p = urlparse(final_url)
        origin = f"{p.scheme}://{p.netloc}"
        for path in (
            "/apple-touch-icon.png",
            "/apple-touch-icon-precomposed.png",
            "/favicon.ico",
            "/favicon.png",
            "/favicon.svg",
            "/icon.svg",
            "/icon.png",
            "/logo.svg",
            "/logo.png",
            "/logo.webp",
            "/brand.svg",
            "/brand.png",
            "/assets/logo.svg",
            "/assets/logo.png",
            "/images/logo.svg",
            "/images/logo.png",
            "/static/logo.svg",
            "/static/logo.png",
            "/vite.svg",
        ):
            got = download_image(origin + path)
            if got:
                return got

    # Browser fallback on homepage-first variants.
    for variant in _site_variants(site)[:2]:
        got = fetch_logo_via_browser(variant)
        if got:
            return got
    return None


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
        files = {
            "file": (file_name, io.BytesIO(file_bytes), "application/octet-stream")
        }
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
