from bot.workflow_form_received_notify import build_form_received_message


def test_form_received_copy():
    text = build_form_received_message(
        project="exampleapp",
        group="BOTCHAIN/exampleapp",
        bd_name="Ada",
        bd_open_id="ou_bd",
    )
    assert text.startswith(
        '<at user_id="ou_bd">Ada</at>'
    )
    assert "**Project:** `exampleapp`" in text
    assert "**Status:** Google Onboarding form received" in text
    assert "**TG group:** `BOTCHAIN/exampleapp`" in text
    assert (
        "**Form:** Submitted; Twitter, contract, logo and intro are in Lark"
        in text
    )
    assert "No action needed. Delivery Agent will pick this up in the midnight wallet digest" in text
    assert "**Please:**" not in text


def test_form_received_fallback_at():
    text = build_form_received_message(
        project="sparrowpost",
        group="",
        bd_name="Ada",
        bd_open_id="",
    )
    assert text.startswith("@Ada")
    assert "**TG group:** `not matched`" in text
