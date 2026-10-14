from __future__ import annotations

from bot.workflow_live_link_sync import (
    extract_http_site_url,
    live_link_empty,
    process_new_progress_records,
    sync_live_links_once,
)


def test_extract_http_site_url_from_plain_and_url_cell():
    assert (
        extract_http_site_url("See https://Example.COM/app now")
        == "https://Example.COM/app"
    )
    assert (
        extract_http_site_url({"link": "http://foo.bar/", "text": "site"})
        == "http://foo.bar/"
    )
    assert extract_http_site_url("example.com/no-scheme") == ""
    assert extract_http_site_url("") == ""


def test_live_link_empty():
    assert live_link_empty({}, "已上线链接🔗")
    assert live_link_empty({"已上线链接🔗": ""}, "已上线链接🔗")
    assert not live_link_empty(
        {"已上线链接🔗": {"link": "https://live.example/"}}, "已上线链接🔗"
    )


def test_sync_fills_empty_live_link_and_skips_filled(monkeypatch):
    rows = [
        {
            "record_id": "rec_empty",
            "fields": {
                "项目名称 Project Name": "Alpha",
                "项目链接": "Official https://alpha.example/path",
                "已上线链接🔗": "",
            },
        },
        {
            "record_id": "rec_filled",
            "fields": {
                "项目名称 Project Name": "Beta",
                "项目链接": "https://beta-new.example/",
                "已上线链接🔗": {"link": "https://beta-old.example/"},
            },
        },
        {
            "record_id": "rec_bare",
            "fields": {
                "项目名称 Project Name": "Gamma",
                "项目链接": "gamma.example",
                "已上线链接🔗": "",
            },
        },
    ]
    writes: list[tuple[str, dict]] = []

    class Cfg:
        workflow_live_link_sync_enabled = True
        workflow_base_app_token = "app"
        workflow_progress_table_id = "tbl"
        workflow_live_link_field = "已上线链接🔗"
        workflow_project_link_field = "项目链接"
        workflow_project_name_field = "项目名称 Project Name"

    monkeypatch.setenv("LARK_APP_ID", "id")
    monkeypatch.setenv("LARK_APP_SECRET", "secret")
    monkeypatch.setattr(
        "bot.workflow_live_link_sync.get_tenant_access_token", lambda *_a, **_k: "tok"
    )
    monkeypatch.setattr(
        "bot.workflow_live_link_sync.update_record",
        lambda token, app, table, rid, payload: writes.append((rid, payload)),
    )
    monkeypatch.setattr(
        "bot.workflow_kpi_write.kpi_checks_on_this_host", lambda: True
    )

    stats = sync_live_links_once(Cfg(), records=rows)
    assert stats["updated"] == 1
    assert stats["skipped_filled"] == 1
    assert stats["skipped_no_url"] == 1
    assert writes == [
        (
            "rec_empty",
            {
                "已上线链接🔗": {
                    "link": "https://alpha.example/path",
                    "text": "https://alpha.example/path",
                }
            },
        )
    ]
    assert rows[1]["fields"]["已上线链接🔗"]["link"] == "https://beta-old.example/"


def test_process_new_progress_records_baselines_then_syncs_only_newcomers(
    monkeypatch, tmp_path
):
    writes: list[str] = []

    class Cfg:
        workflow_live_link_sync_enabled = True
        workflow_live_link_sync_state_file = str(tmp_path / "seen.json")
        workflow_base_app_token = "app"
        workflow_progress_table_id = "tbl"
        workflow_live_link_field = "已上线链接🔗"
        workflow_project_link_field = "项目链接"
        workflow_project_name_field = "项目名称 Project Name"

    monkeypatch.setenv("LARK_APP_ID", "id")
    monkeypatch.setenv("LARK_APP_SECRET", "secret")
    monkeypatch.setattr(
        "bot.workflow_live_link_sync.get_tenant_access_token", lambda *_a, **_k: "tok"
    )
    monkeypatch.setattr(
        "bot.workflow_live_link_sync.update_record",
        lambda token, app, table, rid, payload: writes.append(rid),
    )
    monkeypatch.setattr(
        "bot.workflow_kpi_write.kpi_checks_on_this_host", lambda: True
    )

    existing = [
        {
            "record_id": "rec_old",
            "fields": {
                "项目名称 Project Name": "Old",
                "项目链接": "https://old.example/",
                "已上线链接🔗": "",
            },
        }
    ]
    first = process_new_progress_records(Cfg(), existing)
    assert first["new"] == 0
    assert first["updated"] == 0
    assert writes == []

    with_new = existing + [
        {
            "record_id": "rec_new",
            "fields": {
                "项目名称 Project Name": "New",
                "项目链接": "https://new.example/",
                "已上线链接🔗": "",
            },
        }
    ]
    second = process_new_progress_records(Cfg(), with_new)
    assert second["new"] == 1
    assert second["updated"] == 1
    assert writes == ["rec_new"]
