from datetime import datetime, timezone, timedelta

from bot.workflow_verify_alert import build_verify_alert_text, project_name_from_chat_title


TZ = timezone(timedelta(hours=8))


def test_verify_alert_copy_is_short_with_time():
    text = build_verify_alert_text(
        project_name="TipStream",
        chat_title="TipStream <> Botchain",
        sender_username="brianwongjhh",
        sender_id=1,
        text="submitted for verification",
        when=datetime(2026, 10, 7, 16, 57, tzinfo=TZ),
    )
    assert text == (
        "Verify：TipStream\n"
        "@brianwongjhh · TipStream <> Botchain\n"
        "2026-10-07 16:57"
    )
    assert "原文" not in text
    assert "UTC+8" not in text


def test_project_name_from_chat_title():
    assert project_name_from_chat_title("TipStream <> Botchain") == "TipStream"
