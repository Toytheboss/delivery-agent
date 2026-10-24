from __future__ import annotations

from bot.project_logo import (
    _is_botchain_payload,
    _is_rejected_logo_url,
    _prefer_svg_candidates,
    _svg_file_from_markup,
    logo_candidates_from_html,
)
from bot.workflow_logo_fill import upgrade_twitter_avatar_url


def test_reject_botchain_partner_logo_url():
    assert _is_rejected_logo_url("https://www.pocketlm.my.id/botchain-logo.svg")
    assert _is_rejected_logo_url("https://botchain.ai/logo.png")
    assert _is_rejected_logo_url("https://app.example/vite.svg")
    assert not _is_rejected_logo_url("https://www.pocketlm.my.id/icon.svg")
    assert not _is_rejected_logo_url("https://vaultlock-app.vercel.app/logo.png")
    assert not _is_rejected_logo_url("https://doomtax-botchain.vercel.app/icon.svg")


def test_html_candidates_skip_botchain_logo():
    html = """
    <html><head>
    <link rel="icon" href="/botchain-logo.svg">
    <link rel="icon" href="/icon.svg">
    </head><body>
    <header><img class="logo" src="/botchain-logo.svg" alt="botchain">
    <img class="logo" src="/icon.svg" alt="pocketlm"></header>
    </body></html>
    """
    cands = logo_candidates_from_html(html, "https://www.pocketlm.my.id/")
    assert any(u.endswith("/icon.svg") for u in cands)
    assert not any("botchain-logo" in u for u in cands)


def test_svg_markup_saved_as_vector_file():
    data, fname = _svg_file_from_markup(
        '<svg width="24" height="24" viewBox="0 0 24 24"><path d="M4 4h16v16H4z"/></svg>'
    )
    assert fname == "logo.svg"
    assert b"<svg" in data
    assert b"xmlns" in data


def test_svg_file_preferred_over_og_and_apple_touch():
    html = """
    <html><head>
    <link rel="apple-touch-icon" href="/apple-touch-icon.png">
    <meta property="og:image" content="/og.png">
    <link rel="icon" href="/icon.svg">
    </head><body>
    <header><img class="logo" src="/logo.svg" alt="vault"></header>
    </body></html>
    """
    cands = logo_candidates_from_html(html, "https://vaultlock-app.vercel.app/")
    assert not any(u.endswith("/og.png") for u in cands)
    ordered = _prefer_svg_candidates(cands)
    assert ordered[0].endswith(".svg")
    assert any(u.endswith("/logo.svg") for u in ordered)


def test_botchain_payload_rejected():
    assert _is_botchain_payload(b'<svg id="botchain-logo"></svg>')
    assert _is_botchain_payload(
        b'<svg width="1031" height="205" viewBox="0 0 1031 205" fill="none"></svg>'
    )
    assert not _is_botchain_payload(b'<svg viewBox="0 0 24 24"><path d="M4 4"/></svg>')
    assert _svg_file_from_markup('<svg id="botchain-logo"><path d="M1 1"/></svg>') is None


def test_twitter_avatar_url_upgrades_to_400():
    urls = upgrade_twitter_avatar_url(
        "https://pbs.twimg.com/profile_images/1/foo_normal.jpg"
    )
    assert urls[0] == "https://pbs.twimg.com/profile_images/1/foo_400x400.jpg"
    assert "https://pbs.twimg.com/profile_images/1/foo_normal.jpg" in urls
