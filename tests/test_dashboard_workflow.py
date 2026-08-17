import json
import tempfile
import unittest
from pathlib import Path

from bot.dashboard_snapshot import build_workflow_overview


class DashboardWorkflowOverviewTests(unittest.TestCase):
    def test_overview_uses_persisted_events_and_real_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            logo_path = root / "logo.jsonl"
            logo_path.write_text(
                json.dumps(
                    {
                        "ts": "2026-08-16T10:00:00+08:00",
                        "project_name": "Demo",
                        "status": "ok:http",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            workflow_path = root / "workflow.jsonl"
            workflow_path.write_text(
                "\n".join(
                    json.dumps(
                        {
                            "ts": ts,
                            "kind": "lark_sync_completed",
                            "source": "lark_sync",
                            "text": "Lark 知识库同步完成",
                            "status": "success",
                        },
                        ensure_ascii=False,
                    )
                    for ts in (
                        "2026-08-16T08:00:00+08:00",
                        "2026-08-16T09:00:00+08:00",
                    )
                )
                + "\n",
                encoding="utf-8",
            )

            class Config:
                workflow_logo_events_file = str(logo_path)
                workflow_events_file = str(workflow_path)
                workflow_deploy_status_watch_state_file = str(root / "missing.json")
                workflow_form_chase_state_file = str(root / "missing-chase.json")

            projects = {
                "total": 2,
                "matched": 1,
                "rows": [
                    {
                        "project": "Demo",
                        "stage": "live",
                        "form_sent": False,
                        "tg_bound": True,
                    },
                    {
                        "project": "Other",
                        "stage": "main_deploy",
                        "form_sent": False,
                        "tg_bound": False,
                        "tg_match_reason": "no title match",
                    },
                ],
            }
            payload = {
                "snapshot": {
                    "counters": {"wallet_digest_sent": {"week": 2}},
                    "derived": {"logo_fill_state": {"fail": 0}},
                    "wallet_lark": {
                        "total_rows": 4,
                        "projects_with_any_address": 3,
                    },
                },
                "qa": {"answered": [], "silent": []},
            }

            overview = build_workflow_overview(Config(), projects, payload)
            steps = {step["key"]: step for step in overview["funnel"]["steps"]}
            self.assertEqual(steps["bound"]["count"], 1)
            self.assertEqual(steps["wallet_incomplete"]["count"], 1)
            self.assertEqual(overview["exceptions_total"], 2)
            self.assertEqual(overview["activities"][0]["project"], "Demo")
            sync_rows = [
                item
                for item in overview["activities"]
                if item.get("kind") == "lark_sync_completed"
            ]
            self.assertEqual(len(sync_rows), 1)


if __name__ == "__main__":
    unittest.main()
