from __future__ import annotations

from bot.project_logo import pick_site_url


def test_pick_site_url_uses_live_link_only():
    fields = {
        "已上线链接🔗": {"link": "https://live.example/", "text": "https://live.example/"},
        "项目链接": "https://project.example/",
    }
    assert pick_site_url(fields, "已上线链接🔗", "项目链接") == "https://live.example/"


def test_pick_site_url_does_not_fall_back_to_project_link():
    fields = {
        "已上线链接🔗": "",
        "项目链接": "https://project.example/",
    }
    assert pick_site_url(fields, "已上线链接🔗", "项目链接") is None


def test_pick_site_url_empty_when_live_missing():
    assert pick_site_url({}, "已上线链接🔗", "项目链接") is None
