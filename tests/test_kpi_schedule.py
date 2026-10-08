from datetime import date, datetime
from zoneinfo import ZoneInfo

from bot.workflow_kpi_schedule import due_round, mark_rounds_done, select_due

SH = ZoneInfo("Asia/Shanghai")


def _row(record_id: str, name: str, live: str, status: str = "主网上线") -> dict:
    return {
        "record_id": record_id,
        "fields": {
            "项目名称 Project Name": name,
            "项目状态": status,
            "主网上线时间": datetime.fromisoformat(live).replace(tzinfo=SH).isoformat(),
        },
    }


def test_first_round_is_seven_days_after_live():
    live = datetime(2026, 9, 30, tzinfo=SH)
    assert due_round(live, date(2026, 10, 6), first_done=False, second_done=False) is None
    assert due_round(live, date(2026, 10, 7), first_done=False, second_done=False) == "first"


def test_second_round_waits_until_the_first_is_sent():
    live = datetime(2026, 9, 30, tzinfo=SH)
    assert due_round(live, date(2026, 10, 21), first_done=False, second_done=False) == "first"
    assert due_round(live, date(2026, 10, 20), first_done=True, second_done=False) is None
    assert due_round(live, date(2026, 10, 21), first_done=True, second_done=False) == "second"
    assert due_round(live, date(2026, 10, 21), first_done=True, second_done=True) is None


def test_september_and_already_posted_projects_stay_off_the_calendar():
    records = [
        _row("old", "September", "2026-09-29"),
        _row("posted", "swing", "2026-09-30"),
        _row("fresh", "Newone", "2026-09-30"),
        _row("deploying", "Later", "2026-10-01", status="主网部署中"),
    ]
    due = select_due(
        records,
        today=date(2026, 10, 7),
        state={"first": {}, "second": {}},
        status_field="项目状态",
        name_field="项目名称 Project Name",
        already_posted={"posted"},
    )
    assert [item["project"] for item in due] == ["Newone"]
    assert due[0]["round"] == "first"


def test_mark_rounds_done_skips_calendar_second(tmp_path):
    path = tmp_path / "kpi_schedule_state.json"
    mark_rounds_done("rec-held", rounds=("first", "second"), day=date(2026, 10, 10), path=path)
    live = datetime(2026, 10, 1, tzinfo=SH)
    assert due_round(live, date(2026, 10, 22), first_done=True, second_done=True) is None
    records = [_row("rec-held", "HeldProj", "2026-10-01")]
    due = select_due(
        records,
        today=date(2026, 10, 22),
        state={
            "first": {"rec-held": "2026-10-08"},
            "second": {"rec-held": "2026-10-10"},
        },
        status_field="项目状态",
        name_field="项目名称 Project Name",
        already_posted=set(),
    )
    assert due == []
