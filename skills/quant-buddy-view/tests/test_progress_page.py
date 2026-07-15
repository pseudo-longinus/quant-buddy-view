import sys
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import progress_page
import static_page


class ProgressPageWaitingInputTest(unittest.TestCase):
    def test_waiting_input_marks_current_step_as_waiting(self):
        state = progress_page.build_state({
            "page_status": "waiting_input",
            "current_step": "formula_validation",
            "required_input": {
                "id": "market_scope",
                "prompt": "请选择本页市场口径",
                "options": [
                    {"value": "a_share", "label": "A股"},
                    {"value": "hk", "label": "港股"},
                ],
                "resume_step": "formula_validation",
            },
        })

        statuses = {step["id"]: step["status"] for step in state["steps"]}
        self.assertEqual(state["page_status"], "waiting_input")
        self.assertEqual(statuses["template"], "done")
        self.assertEqual(statuses["formula_validation"], "waiting")
        self.assertEqual(statuses["package_register"], "pending")
        self.assertEqual(state["required_input"]["id"], "market_scope")

    def test_update_progress_rejects_waiting_input_without_required_fields(self):
        result = static_page.cmd_update_progress({
            "page_id": "page_existing",
            "page_status": "waiting_input",
            "current_step": "formula_validation",
            "required_input": {
                "id": "market_scope",
                "prompt": "请选择本页市场口径",
            },
        })

        self.assertEqual(result["code"], 1)
        self.assertEqual(result["error"], "PROGRESS_INPUT_REQUIRED")

    def test_waiting_input_renders_visible_prompt_and_options(self):
        page = progress_page.render_progress_html({
            "page_status": "waiting_input",
            "current_step": "formula_validation",
            "required_input": {
                "id": "market_scope",
                "prompt": "请选择本页市场口径",
                "options": [
                    {"value": "a_share", "label": "A股"},
                    {"value": "hk", "label": "港股"},
                ],
                "resume_step": "formula_validation",
            },
        })

        self.assertIn('data-page-status="waiting_input"', page)
        self.assertIn('class="required-input-panel"', page)
        self.assertIn("等待用户确认", page)
        self.assertIn("请选择本页市场口径", page)
        self.assertIn("A股", page)
        self.assertIn("港股", page)

    def test_running_state_discards_stale_required_input(self):
        state = progress_page.build_state({
            "page_status": "running",
            "current_step": "formula_validation",
            "required_input": {
                "id": "market_scope",
                "prompt": "请选择本页市场口径",
                "resume_step": "formula_validation",
            },
        })

        self.assertIsNone(state["required_input"])


if __name__ == "__main__":
    unittest.main()
