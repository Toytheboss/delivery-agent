from __future__ import annotations

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


def test_kolmarket_two_same_title_picks_one():
    cid, reason = match_project_to_chat("KOLMarket", TITLES)
    assert cid in {15, 16}, reason
    assert cid is not None


def _amb() -> dict[int, str]:
    return {
        101: "Veris X Botchain",
        102: "VeriSettle <> Botchain",
        103: "Sent x Bot chain",
        104: "Sentinel X Botchain",
        105: "BOT Chain x Consent Registry",
        106: "Trace Chain <> Botchain",
        107: "Traceonchain X Botchain",
        108: "Link Chain <> Botchain",
        109: "Linkchain | BOT Chain",
        -100109: "Linkchain | BOT Chain",
        110: "BotChain <> Chainlink",
        111: "BOTCHAIN DEX <> BOTCHAIN",
        112: "ArcadeX <> Botchain (Live)",
        113: "CrossBiDex | BOT Chain",
        114: "The Card | BOT Chain",
        115: "TeavuUcard&botchain",
        117: "Dappbnb <> Botchain",
        118: "BotChain",
        119: "banshanbook&botchain",
        120: "BanshanBook&botchain",
        121: "Botfund <> Bot Chain",
        122: "BOTFUND <> Bot Chain",
        123: "Boost | BOT Chain",
        125: "BotID Protocol <> Botchain",
        127: "Agent Vault X Bot Chain",
        128: "AgentVault | BOT Chain",
        129: "CompulsePulse X Bot Chain",
        130: "Pulse Vote <> Botchain",
        131: "pulsegrid <> Botchain",
        -100123: "Boost | BOT Chain",
        -100114: "The Card | BOT Chain",
        -100111: "BOTCHAIN DEX <> BOTCHAIN",
        -100125: "BotID Protocol <> Botchain",
    }


def test_veris_not_verisettle():
    cid, reason = match_project_to_chat("Veris", _amb())
    assert cid == 101, reason


def test_sent_not_sentinel():
    cid, reason = match_project_to_chat("Sent", _amb())
    assert cid == 103, reason


def test_trace_chain_not_traceonchain():
    cid, reason = match_project_to_chat("Trace Chain", _amb())
    assert cid == 106, reason


def test_link_chain_not_linkchain():
    cid, reason = match_project_to_chat("Link Chain", _amb())
    assert cid == 108, reason


def test_linkchain_still_own_group():
    cid, reason = match_project_to_chat("Linkchain", _amb())
    assert cid == -100109, reason


def test_botchain_dex_not_other_dex():
    cid, reason = match_project_to_chat("BOTCHAIN DEX", _amb())
    assert cid == -100111, reason


def test_the_card_prefers_migrated():
    cid, reason = match_project_to_chat("The Card", _amb())
    assert cid == -100114, reason


def test_dappbnb_url_not_generic_botchain():
    cid, reason = match_project_to_chat(
        "https://dappbnb-botchain.vercel.app/", _amb()
    )
    assert cid == 117, reason


def test_banshanbook_duplicate_titles():
    cid, reason = match_project_to_chat("BanshanBook", _amb())
    assert cid in {119, 120}, reason
    assert cid is not None


def test_botfund_duplicate_titles():
    cid, reason = match_project_to_chat("BotFund", _amb())
    assert cid in {121, 122}, reason


def test_boost_prefers_migrated():
    cid, reason = match_project_to_chat("Boost", _amb())
    assert cid == -100123, reason


def test_botid_duplicate_titles():
    cid, reason = match_project_to_chat("Botid", _amb())
    assert cid == -100125, reason


def test_agentvault_same_project_two_titles():
    cid, reason = match_project_to_chat("AgentVault", _amb())
    assert cid in {127, 128}, reason
    assert cid is not None


def test_bot_chain_pulse_stays_unmatched():
    cid, _reason = match_project_to_chat("BOT Chain Pulse", _amb())
    assert cid is None


def test_botchain_slash_group_counts_when_bot_is_in_it():
    cid, reason = match_project_to_chat("mettelia", {201: "BOTCHAIN/mettelia"})
    assert cid == 201, reason
