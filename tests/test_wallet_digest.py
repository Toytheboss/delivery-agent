from bot.workflow_lark_wallet_group import _build_digest_text, midnight_digest_sent_ts


def test_digest_names_each_filled_address_type():
    text = _build_digest_text(
        "2026-09-30",
        [
            ("AgenticID", [("主网合约", 1), ("收款地址", 1)]),
            ("aspecal", [("主网合约", 1)]),
            ("Iticket", [("主网合约", 1), ("收款地址", 1), ("做市钱包", 1)]),
            ("Bot folio", [("主网合约", 2), ("收款地址", 1)]),
        ],
        at_open_id="ou_angela",
        at_name="Angela-财务",
    )
    assert text.startswith('<at user_id="ou_angela">Angela-财务</at>\n')
    assert "【项目方地址日报】2026-09-30" in text
    assert "今日新增项目：4 个" in text
    assert "主网合约 5，收款地址 3，做市钱包 1" in text
    assert "地址字段" not in text
    assert "1. AgenticID：主网合约、收款地址" in text
    assert "2. aspecal：主网合约" in text
    assert "3. Iticket：主网合约、收款地址、做市钱包" in text
    assert "4. Bot folio：主网合约 2 个、收款地址" in text


def test_address_parts_counts_real_addresses_and_grant_column():
    from bot.workflow_lark_wallet_group import address_parts

    mainnet = "0x" + "11" * 20
    second = "0x" + "22" * 20
    grant = "0x" + "33" * 20
    assert address_parts(
        {
            "Mainnet Contract Addresss": f"{mainnet}\n{second}",
            "Grant Receiving Wallet": grant,
            "Treasury Address": "N/A",
        }
    ) == [("主网合约", 2), ("收款地址", 1)]


def test_digest_without_open_id_has_no_at():
    text = _build_digest_text("2026-09-22", [])
    assert "<at " not in text
    assert text.startswith("【项目方地址日报】2026-09-22")
    assert "今日暂无新的项目方地址写入。" in text


def test_midnight_digest_sent_ts_is_next_day_000002():
    assert midnight_digest_sent_ts("2026-09-24") == "2026-09-25T00:00:02+08:00"
    assert midnight_digest_sent_ts("2026-09-18") == "2026-09-19T00:00:02+08:00"

