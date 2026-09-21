from bot.workflow_form_dispatch import find_project_chat_matches, match_project_to_chat


TITLES = {
    1: "Botchain X CloudChain AI",
    2: "Archon web3 app <> botchain (mainnet)",
    3: "Nexar Network and Botchain",
    4: "BOT Chain | Space Runners",
    5: "Yolo Markets <> Botchain",
    6: "BOTLatch X Bot Chain",
    7: "Curtis.fi x BOT Chain",
    8: "Botchain <> Lumora ( Oracle)",
    9: "Depin Device Reg <> Botchain",
    10: "Assetlease Protocol X Botchain",
    11: "NAKAM ( Dexnetcom ) X Botchain",
    12: "Botseal | BOT Chain",
    13: "Botsea / Pixel Optimus <> BOT Chain",
    14: "Signal Sat <> Botchain",
    15: "Kolmarket X Botchain",
    16: "Kolmarket X Botchain",
    17: "AIdaovote x Botchain",
    18: "ShieldGuard <> Botchain",
}


def _ids(name: str) -> list[int]:
    return [cid for cid, _, _, _ in find_project_chat_matches(name, TITLES)]


def test_cloudchain_spacing():
    cid, reason = match_project_to_chat("Cloud Chain AI", TITLES)
    assert cid == 1, reason


def test_archon_web3_app():
    cid, reason = match_project_to_chat("Archon", TITLES)
    assert cid == 2, reason


def test_nexar_and_botchain():
    cid, reason = match_project_to_chat("Nexar Network", TITLES)
    assert cid == 3, reason


def test_space_runners_not_auto():
    cid, _reason = match_project_to_chat("Space", TITLES)
    assert cid is None


def test_yolo_plural():
    cid, reason = match_project_to_chat("Yolo Market", TITLES)
    assert cid == 5, reason


def test_bot_latch_compound():
    cid, reason = match_project_to_chat("Bot Latch", TITLES)
    assert cid == 6, reason


def test_curtis_fi():
    cid, reason = match_project_to_chat("Curtis", TITLES)
    assert cid == 7, reason


def test_lumora_oracle_paren():
    cid, reason = match_project_to_chat("Lumora", TITLES)
    assert cid == 8, reason


def test_depin_reg_abbrev():
    cid, reason = match_project_to_chat("DePIN Device Registry", TITLES)
    assert cid == 9, reason


def test_asset_lease_glued():
    cid, reason = match_project_to_chat("Asset lease", TITLES)
    assert cid == 10, reason


def test_nakam_parenthetical():
    cid, reason = match_project_to_chat("Nakam", TITLES)
    assert cid == 11, reason


def test_botsea_not_botseal():
    cid, reason = match_project_to_chat("Botsea", TITLES)
    assert cid == 13, reason


def test_pixel_optimus_shared_title():
    cid, reason = match_project_to_chat("Pixel Optimus", TITLES)
    assert cid == 13, reason


def test_signal_protocol_not_signal_sat():
    cid, _reason = match_project_to_chat("signal protocol", TITLES)
    assert cid is None


def test_aidaovote_case():
    cid, reason = match_project_to_chat("AIDAOVOTE", TITLES)
    assert cid == 17, reason


def test_shieldguard_spaces():
    cid, reason = match_project_to_chat("ShieldGuard", TITLES)
    assert cid == 18, reason


def test_kolmarket_two_same_title_still_ambiguous():
    cid, reason = match_project_to_chat("KOLMarket", TITLES)
    assert cid is None
    assert "ambiguous" in reason
