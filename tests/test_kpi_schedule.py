from datetime import date, datetime
from zoneinfo import ZoneInfo

from bot.workflow_kpi_schedule import (
    due_round,
    mark_rounds_done,
    select_due,
    select_september_held,
)

SH = ZoneInfo("Asia/Shanghai")
BEFORE = datetime(2026, 10, 13, 12, tzinfo=SH)
AFTER = datetime(2026, 10, 16, 10, tzinfo=SH)


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
    assert (
        due_round(
            live, date(2026, 10, 6), first_done=False, second_done=False, at=BEFORE
        )
        is None
    )
    assert (
        due_round(
            live, date(2026, 10, 7), first_done=False, second_done=False, at=BEFORE
        )
        == "first"
    )


def test_second_round_waits_until_the_first_is_sent():
    live = datetime(2026, 9, 30, tzinfo=SH)
    assert (
        due_round(
            live, date(2026, 10, 21), first_done=False, second_done=False, at=BEFORE
        )
        == "first"
    )
    assert (
        due_round(
            live, date(2026, 10, 20), first_done=True, second_done=False, at=BEFORE
        )
        is None
    )
    assert (
        due_round(
            live, date(2026, 10, 21), first_done=True, second_done=False, at=BEFORE
        )
        == "second"
    )
    assert (
        due_round(
            live, date(2026, 10, 21), first_done=True, second_done=True, at=BEFORE
        )
        is None
    )


def test_after_cutover_first_is_three_days_and_second_is_two_weeks_later():
    live = datetime(2026, 10, 16, tzinfo=SH)
    assert (
        due_round(
            live, date(2026, 10, 18), first_done=False, second_done=False, at=AFTER
        )
        is None
    )
    assert (
        due_round(
            live, date(2026, 10, 19), first_done=False, second_done=False, at=AFTER
        )
        == "first"
    )
    assert (
        due_round(
            live, date(2026, 11, 1), first_done=True, second_done=False, at=AFTER
        )
        is None
    )
    assert (
        due_round(
            live, date(2026, 11, 2), first_done=True, second_done=False, at=AFTER
        )
        == "second"
    )


def test_september_and_already_posted_projects_stay_off_the_calendar():
    records = [
        _row("old", "September", "2026-09-29"),
        _row("posted", "pebble", "2026-09-30"),
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
        at=BEFORE,
    )
    assert [item["project"] for item in due] == ["Newone"]
    assert due[0]["round"] == "first"


def test_september_held_batch_skips_other_rows():
    records = [
        _row("held", "Held", "2026-09-12"),
        _row("passed", "Passed", "2026-09-12"),
        _row("october", "October", "2026-10-02"),
        _row("deploying", "Deploying", "2026-09-20", status="主网部署中"),
        _row("done", "Already", "2026-09-08"),
    ]
    records[0]["fields"]["KPI Final"] = ["暂扣整改"]
    records[1]["fields"]["KPI Final"] = ["通过"]
    records[2]["fields"]["KPI Final"] = ["暂扣整改"]
    records[3]["fields"]["KPI Final"] = ["暂扣整改"]
    records[4]["fields"]["KPI Final"] = ["暂扣整改"]
    due = select_september_held(
        records,
        state={"second": {"done": "2026-10-15"}},
        status_field="项目状态",
        name_field="项目名称 Project Name",
    )
    assert [item["project"] for item in due] == ["Held"]
    assert due[0]["round"] == "second"


def test_calendar_second_only_runs_while_held():
    records = [
        _row("held", "Held", "2026-10-01"),
        _row("passed", "Passed", "2026-10-01"),
        _row("valid", "ValidName", "2026-10-01"),
        _row("failed", "Failed", "2026-10-01"),
        _row("blank", "Blank", "2026-10-01"),
    ]
    records[0]["fields"]["KPI Final"] = ["暂扣整改"]
    records[1]["fields"]["KPI Final"] = ["通过"]
    records[2]["fields"]["KPI Final"] = ["有效 KPI"]
    records[3]["fields"]["KPI Final"] = ["不通过"]
    due = select_due(
        records,
        today=date(2026, 10, 18),
        state={
            "first": {
                "held": "2026-10-08",
                "passed": "2026-10-08",
                "valid": "2026-10-08",
                "failed": "2026-10-08",
                "blank": "2026-10-08",
            },
            "second": {},
        },
        status_field="项目状态",
        name_field="项目名称 Project Name",
        already_posted=set(),
        at=AFTER,
    )
    assert [item["project"] for item in due] == ["Held"]
    assert due[0]["round"] == "second"


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
