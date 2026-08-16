import unittest

from bot.workflow_form_dispatch import match_project_to_chat


class ProjectChatMatchingTests(unittest.TestCase):
    def test_match_ignores_case_and_whitespace(self):
        chat_id, reason = match_project_to_chat(
            "Project X",
            {123: "PROJECT   X <> BOT Chain"},
        )
        self.assertEqual(chat_id, 123)
        self.assertIn("partial", reason)

    def test_ambiguous_match_is_not_auto_selected(self):
        chat_id, reason = match_project_to_chat(
            "Nova",
            {123: "Nova <> BOT Chain", 456: "NOVA team"},
        )
        self.assertIsNone(chat_id)
        self.assertIn("ambiguous", reason)

    def test_exact_and_partial_candidates_are_still_ambiguous(self):
        chat_id, reason = match_project_to_chat(
            "Nova",
            {123: "Nova", 456: "Nova <> BOT Chain"},
        )
        self.assertIsNone(chat_id)
        self.assertIn("ambiguous", reason)

    def test_single_candidate_can_match_in_either_direction(self):
        chat_id, reason = match_project_to_chat(
            "BOT Chain Builders Hub",
            {123: "BOTChainBuildersHub <> Mainnet"},
        )
        self.assertEqual(chat_id, 123)
        self.assertIn("partial", reason)


if __name__ == "__main__":
    unittest.main()
