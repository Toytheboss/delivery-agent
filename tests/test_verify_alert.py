from datetime import datetime, timezone, timedelta

from bot.triggers import (
    delivery_alert_kind,
    delivery_alert_kind_for_internal,
    is_human_verify_request,
)
from bot.workflow_verify_alert import build_verify_alert_text, project_name_from_chat_title


TZ = timezone(timedelta(hours=8))


def test_verify_alert_copy_is_short_with_time():
    text = build_verify_alert_text(
        project_name="Forge",
        chat_title="Botchain <> Forge",
        sender_username="Syedeth1",
        sender_id=1,
        text="proceed mainnet verification",
        when=datetime(2026, 10, 21, 19, 12, tzinfo=TZ),
    )
    assert text == (
        "主网上线 Verify 提醒：Forge - @Syedeth1 · Botchain <> Forge (2026-10-21 19:12)"
    )
    assert "原文" not in text
    assert "UTC+8" not in text


def test_project_name_from_chat_title():
    assert project_name_from_chat_title("TipStream <> Botchain") == "TipStream"


def test_verify_alert_only_matches_proceed_mainnet_verification():
    assert delivery_alert_kind("proceed mainnet verification") == "verify"
    assert delivery_alert_kind("Please proceed mainnet verification now") == "verify"
    assert delivery_alert_kind("PROCEED MAINNET VERIFICATION") == "verify"
    assert delivery_alert_kind("please verify") is None
    assert delivery_alert_kind("verify again") is None
    assert delivery_alert_kind("mainnet verification") is None
    assert delivery_alert_kind("Can you verify") is None
    assert delivery_alert_kind_for_internal("need verify") is None
    assert delivery_alert_kind_for_internal("proceed mainnet verification") == "verify"


def test_please_verify_still_silences_faq():
    assert is_human_verify_request("please verify")
    assert is_human_verify_request("proceed mainnet verification")
    assert not is_human_verify_request("how is the weather")
