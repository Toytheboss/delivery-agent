from __future__ import annotations

from bot.workflow_live_onboard import (
    build_onboard_message,
    classify_case,
    parse_bd_person,
)


def test_classify_cases():
    assert classify_case(True, True) == 1
    assert classify_case(True, False) == 2
    assert classify_case(False, True) == 3
    assert classify_case(False, False) == 4


def test_parse_bd_person_from_user_field():
    oid, name = parse_bd_person(
        {"BD": [{"id": "ou_ella", "name": "Ella"}]},
        "BD",
    )
    assert oid == "ou_ella"
    assert name == "Ella"


def test_case1_message_uses_group_title_and_at():
    text = build_onboard_message(
        case=1,
        project="vritz",
        group="vritz <> Botchain",
        bd_name="Ella",
        bd_open_id="ou_ella",
    )
    assert text.startswith('<at user_id="ou_ella">Ella</at>')
    assert "**vritz** is live on mainnet" in text
    assert "Roy and Josh" in text
    assert "Onboarding Google Form has been sent to **vritz <> Botchain**" in text
    assert "Add Josh" not in text


def test_case2_asks_to_add_josh():
    text = build_onboard_message(
        case=2,
        project="vritz",
        group="vritz <> Botchain",
        bd_name="Ella",
        bd_open_id="ou_ella",
    )
    assert "Roy has joined" in text
    assert "Add Josh to the TG group" in text


def test_case3_asks_to_add_roy():
    text = build_onboard_message(
        case=3,
        project="vritz",
        group="vritz <> Botchain",
        bd_name="Ella",
        bd_open_id="ou_ella",
    )
    assert "Josh has joined" in text
    assert "Add Roy to the TG group" in text


def test_case4_form_not_sent():
    text = build_onboard_message(
        case=4,
        project="vritz",
        group="",
        bd_name="Ella",
        bd_open_id="ou_ella",
    )
    assert "were not detected" in text
    assert "Onboarding Google Form was not sent" in text
    assert "Create the project TG group" in text
