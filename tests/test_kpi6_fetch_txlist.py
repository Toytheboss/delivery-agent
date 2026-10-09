from __future__ import annotations

from unittest.mock import MagicMock, patch

from bot.workflow_kpi6_onchain import _MIN_TXS, _MIN_WALLETS, _PAGE_SIZE, fetch_txlist


def _tx(*, sender: str, to: str, ts: int, ok: bool = True) -> dict:
    return {
        "from": sender,
        "to": to,
        "timeStamp": str(ts),
        "isError": "0" if ok else "1",
        "hash": f"0x{sender[-4:]}{ts}",
        "contractAddress": "",
    }


def test_fetch_txlist_stops_when_kpi_thresholds_met():
    ca = "0x" + ("aa" * 20)
    # One page already has 3 wallets and 5 core txs to the contract.
    page1 = [
        _tx(sender="0x" + ("11" * 20), to=ca, ts=1005),
        _tx(sender="0x" + ("22" * 20), to=ca, ts=1004),
        _tx(sender="0x" + ("33" * 20), to=ca, ts=1003),
        _tx(sender="0x" + ("11" * 20), to=ca, ts=1002),
        _tx(sender="0x" + ("22" * 20), to=ca, ts=1001),
    ]
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"message": "OK", "result": page1}

    with patch("bot.workflow_kpi6_onchain.requests.get", return_value=mock_resp) as get:
        rows = fetch_txlist(ca)

    assert len(rows) == 5
    assert get.call_count == 1
    params = get.call_args.kwargs["params"]
    assert params["sort"] == "desc"
    assert params["offset"] == _PAGE_SIZE


def test_fetch_txlist_keeps_paging_until_enough_wallets():
    ca = "0x" + ("bb" * 20)
    # Page 1: only 2 wallets / 2 txs — not enough.
    page1 = [
        _tx(sender="0x" + ("11" * 20), to=ca, ts=2002),
        _tx(sender="0x" + ("22" * 20), to=ca, ts=2001),
    ] + [
        # pad so page looks "full" and pagination continues
        _tx(sender="0x" + ("11" * 20), to="0x" + ("00" * 20), ts=1900 - i)
        for i in range(_PAGE_SIZE - 2)
    ]
    page2 = [
        _tx(sender="0x" + ("33" * 20), to=ca, ts=1805),
        _tx(sender="0x" + ("11" * 20), to=ca, ts=1804),
        _tx(sender="0x" + ("22" * 20), to=ca, ts=1803),
        _tx(sender="0x" + ("33" * 20), to=ca, ts=1802),
        _tx(sender="0x" + ("11" * 20), to=ca, ts=1801),
    ]

    def _side_effect(*_a, **kwargs):
        page = int((kwargs.get("params") or {}).get("page") or 1)
        mock = MagicMock()
        mock.raise_for_status = MagicMock()
        mock.json.return_value = {
            "message": "OK",
            "result": page1 if page == 1 else page2,
        }
        return mock

    with patch("bot.workflow_kpi6_onchain.requests.get", side_effect=_side_effect) as get:
        rows = fetch_txlist(ca)

    assert get.call_count == 2
    assert len(rows) == _PAGE_SIZE + 5
    # Sanity: thresholds constants still match product rule.
    assert _MIN_WALLETS == 3 and _MIN_TXS == 5
