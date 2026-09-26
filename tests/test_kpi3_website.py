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
    page_has_project_name,
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


def test_project_name_preferred_over_logo():
    probe = WebsiteProbe(
        url="https://subscribeone.example",
        opened=True,
        hrefs=("https://botchain.ai", "https://scan.botchain.ai"),
        text="SubscribeOne is live on BOT Chain",
        has_logo=True,
    )
    verdict = evaluate_kpi3(project_name="SubscribeOne", probe=probe, url=probe.url)
    assert verdict.passed
    assert verdict.has_name
    assert "project name SubscribeOne is visible" in verdict.copy
    assert verdict.copy.endswith("website display verification passed")


def test_logo_fallback_when_name_missing():
    probe = WebsiteProbe(
        url="https://example.com",
        opened=True,
        hrefs=("https://botchain.ai/", "https://scan.botchain.ai/"),
        text="Welcome to our protocol",
        has_logo=True,
    )
    verdict = evaluate_kpi3(project_name="NovaMint", probe=probe, url=probe.url)
    assert verdict.passed
    assert not verdict.has_name
    assert verdict.has_logo
    assert "project name not found, but logo is visible" in verdict.copy


def test_missing_one_official_link_fails():
    probe = WebsiteProbe(
        url="https://firmament.site",
        opened=True,
        hrefs=("https://scan.botchain.ai",),
        text="FIRMAMENT AI",
        has_logo=False,
    )
    verdict = evaluate_kpi3(project_name="FIRMAMENT AI", probe=probe, url=probe.url)
    assert not verdict.passed
    assert verdict.has_name
    assert "no clickable https://botchain.ai" in verdict.copy


def test_no_website_url_fails():
    verdict = evaluate_kpi3(project_name="Testing", probe=None, url="")
    assert not verdict.passed
    assert verdict.reason == "no_url"
    assert verdict.copy == (
        "Website display verification: no official website URL submitted; "
        "website display verification failed"
    )


def test_unreachable_site_fails():
    probe = WebsiteProbe(url="https://down.example", opened=False, hrefs=(), text="", has_logo=False, error="timeout")
    verdict = evaluate_kpi3(project_name="Testing", probe=probe, url=probe.url)
    assert not verdict.passed
    assert "website could not be opened" in verdict.copy


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
    html = '<header><img class="brand-logo" src="/logo.png"></header><p>Hello NovaMint</p>'
    assert html_has_logo(html)
    assert page_has_project_name("NovaMint", visible_text(html))
    assert build_kpi3_copy(
        evaluate_kpi3(project_name="X", probe=None, url=""),
        "X",
    ).endswith("failed")
