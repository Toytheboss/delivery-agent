from __future__ import annotations

from bot.project_logo import _is_rejected_logo_url, logo_candidates_from_html


def test_reject_botchain_partner_logo_url():
    assert _is_rejected_logo_url("https://www.pocketlm.my.id/botchain-logo.svg")
    assert _is_rejected_logo_url("https://botchain.ai/logo.png")
    assert _is_rejected_logo_url("https://app.example/vite.svg")
    assert not _is_rejected_logo_url("https://www.pocketlm.my.id/icon.svg")
    assert not _is_rejected_logo_url("https://vaultlock-app.vercel.app/logo.png")


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
