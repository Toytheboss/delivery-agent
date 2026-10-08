from __future__ import annotations

from bot.workflow_kpi3_website import (
    WebsiteProbe,
    build_kpi3_copy,
    evaluate_kpi3,
    extract_anchor_hrefs,
    html_has_logo,
    is_botchain_href,
    is_scan_href,
    kpi3_result_fields,
    page_has_botchain_name,
    visible_text,
)


def test_clickable_official_links_come_from_anchors_only():
    html = """
    <html><body>
      <a href="https://botchain.ai">BOT</a>
      <a href="https://scan.botchain.ai/tx/1">scan</a>
      <script>const rpc = "https://scan.botchain.ai"; const site = "https://botchain.ai";</script>
    </body></html>
    """
    hrefs = extract_anchor_hrefs(html, "https://example.com")
    assert any(is_botchain_href(h) for h in hrefs)
    assert any(is_scan_href(h) for h in hrefs)
    assert "https://botchain.ai" in hrefs


def test_script_only_official_urls_are_not_clickable():
    html = """
    <html><body>
      <script>window.cfg = { explorer: "https://scan.botchain.ai", home: "https://botchain.ai" }</script>
    </body></html>
    """
    hrefs = extract_anchor_hrefs(html, "https://tipjar.ink")
    assert hrefs == []
    assert not any(is_botchain_href(h) for h in hrefs)


def test_www_and_relative_botchain_hrefs_count():
    html = '<a href="https://www.botchain.ai/">x</a><a href="/">home</a>'
    hrefs = extract_anchor_hrefs(html, "https://scan.botchain.ai")
    assert any(is_botchain_href(h) for h in hrefs)


def test_botchain_name_passes_even_if_lark_name_is_a_url():
    probe = WebsiteProbe(
        url="https://www.tokendropper.site/",
        opened=True,
        hrefs=("https://botchain.ai", "https://scan.botchain.ai"),
        text="Token Dropper Running on BOT Chain Mainnet botchain.ai scan.botchain.ai",
        has_logo=False,
    )
    verdict = evaluate_kpi3(
        project_name="https://www.tokendropper.site/",
        probe=probe,
        url=probe.url,
    )
    assert verdict.passed
    assert verdict.has_name
    assert "- BOT Chain name: yes" in verdict.copy
    assert verdict.copy.endswith("- Result: passed")


def test_both_official_links_pass_without_the_name():
    probe = WebsiteProbe(
        url="https://novamint.example",
        opened=True,
        hrefs=("https://botchain.ai/", "https://scan.botchain.ai/"),
        text="Welcome to NovaMint",
        has_logo=True,
    )
    verdict = evaluate_kpi3(project_name="NovaMint", probe=probe, url=probe.url)
    assert verdict.passed
    assert not verdict.has_name
    assert verdict.reason == "passed"
    assert "- BOT Chain name: no" in verdict.copy
    assert "- https://botchain.ai: yes" in verdict.copy
    assert "- https://scan.botchain.ai: yes" in verdict.copy
    assert verdict.copy.endswith("- Result: passed")


def test_missing_one_official_link_fails():
    probe = WebsiteProbe(
        url="https://firmament.site",
        opened=True,
        hrefs=("https://scan.botchain.ai",),
        text="FIRMAMENT AI is live on BOT Chain",
        has_logo=False,
    )
    verdict = evaluate_kpi3(project_name="FIRMAMENT AI", probe=probe, url=probe.url)
    assert not verdict.passed
    assert verdict.has_name
    assert "- https://botchain.ai: no" in verdict.copy
    assert "- https://scan.botchain.ai: yes" in verdict.copy
    assert verdict.copy.endswith("- Result: failed")


def test_no_website_url_fails():
    verdict = evaluate_kpi3(project_name="Testing", probe=None, url="")
    assert not verdict.passed
    assert verdict.reason == "no_url"
    assert verdict.copy == "- Official website URL: not submitted\n- Result: failed"


def test_unreachable_site_fails():
    probe = WebsiteProbe(url="https://down.example", opened=False, hrefs=(), text="", has_logo=False, error="timeout")
    verdict = evaluate_kpi3(project_name="Testing", probe=probe, url=probe.url)
    assert not verdict.passed
    assert verdict.copy == "- Site opened: no\n- Result: failed"


def test_kpi3_result_fields_use_string_not_array():
    assert kpi3_result_fields(
        copy_field="KPI 3 - 官网展示验证",
        result_field="官网验证结果",
        copy=(
            "Website display verification: no official website URL submitted; "
            "website display verification failed"
        ),
        result="不通过",
    ) == {
        "KPI 3 - 官网展示验证": (
            "Website display verification: no official website URL submitted; "
            "website display verification failed"
        ),
        "官网验证结果": "不通过",
    }


def test_html_helpers():
    html = '<header><img class="brand-logo" src="/logo.png"></header><p>Hello NovaMint on BOT Chain</p>'
    assert html_has_logo(html)
    assert page_has_botchain_name(visible_text(html))
    assert not page_has_botchain_name("Hello NovaMint")
    assert page_has_botchain_name("Powered by Botchain")
    assert build_kpi3_copy(
        evaluate_kpi3(project_name="X", probe=None, url=""),
        "X",
    ).endswith("failed")


def test_browser_probe_runs_in_thread_when_asyncio_loop_is_active(monkeypatch):
    import asyncio

    import bot.workflow_kpi3_website as kpi3

    calls: list[str] = []
    expected = WebsiteProbe(
        url="https://example.com",
        opened=True,
        hrefs=("https://botchain.ai", "https://scan.botchain.ai"),
        text="BOT Chain",
        has_logo=True,
    )

    def fake_sync(url: str):
        calls.append(url)
        return expected

    monkeypatch.setattr(kpi3, "_browser_probe_sync", fake_sync)

    async def run():
        return kpi3._browser_probe("https://example.com")

    out = asyncio.run(run())
    assert out is expected
    assert calls == ["https://example.com"]
