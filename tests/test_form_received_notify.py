from bot.workflow_form_received_notify import build_form_received_message


def test_form_received_copy():
    text = build_form_received_message(
        project="mettelia",
        group="BOTCHAIN/mettelia",
        bd_name="Weison",
        bd_open_id="ou_387acc25ce11c7676a191e364655aa21",
    )
    assert text.startswith(
        '<at user_id="ou_387acc25ce11c7676a191e364655aa21">Weison</at>'
    )
    assert "**Project:** `mettelia`" in text
    assert "**Status:** Google Onboarding form received" in text
    assert "**TG group:** `BOTCHAIN/mettelia`" in text
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
        bd_name="Weison",
        bd_open_id="",
    )
    assert text.startswith("@Weison")
    assert "**TG group:** `not matched`" in text
