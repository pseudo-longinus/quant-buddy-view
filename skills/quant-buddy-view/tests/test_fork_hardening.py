import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import build_dashboard
import static_page


class ForkHardeningTest(unittest.TestCase):
    def test_prepared_fork_task_rejects_build_dashboard(self):
        with tempfile.TemporaryDirectory() as temp_dir, \
             mock.patch.dict(os.environ, {"QBV_FORK_BINDING_DIR": temp_dir}):
            binding_file, error = static_page._write_fork_task_binding({
                "version": "fork_task_binding_v1",
                "status": "prepared",
                "task_id": "task-bound",
                "source_template_id": "page_source",
                "fork_manifest_file": str(Path(temp_dir) / "manifest.json"),
                "working_html_file": str(Path(temp_dir) / "working.html"),
            })
            self.assertIsNone(error)
            self.assertTrue(Path(binding_file).is_file())

            result = build_dashboard.cmd_build({"task_id": "task-bound"})

        self.assertEqual(result["code"], 1)
        self.assertEqual(result["error"], "FORK_TASK_BOUND")
        self.assertEqual(result["working_html_file"], str(Path(temp_dir) / "working.html"))

    def test_asset_replacements_expand_common_exchange_code_variants(self):
        expanded = static_page._expand_asset_replacements({
            "中国银行": "工商银行",
            "601988": "601398",
        })
        self.assertEqual(expanded["中国银行"], "工商银行")
        self.assertEqual(expanded["601988"], "601398")
        self.assertEqual(expanded["SH601988"], "SH601398")
        self.assertEqual(expanded["601988.SH"], "601398.SH")
        self.assertEqual(expanded["sh601988"], "sh601398")

    def test_progress_cannot_advance_with_failed_or_deferred_receipt(self):
        for status, success in (("failed", False), ("deferred", True)):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as temp_dir:
                receipt = Path(temp_dir) / "receipt.json"
                receipt.write_text(json.dumps({
                    "version": "qb_validation_receipt_v1",
                    "task_id": "task-receipt",
                    "status": status,
                    "success": success,
                    "failures": [] if success else [{"code": "EVALUATION_FAILED"}],
                }), encoding="utf-8")
                result = static_page._validate_progress_evidence({
                    "task_id": "task-receipt",
                    "current_step": "package_register",
                    "validation_receipt_files": [str(receipt)],
                })
                self.assertEqual(result["error"], "PROGRESS_EVIDENCE_INVALID")

    def test_progress_accepts_completed_success_receipt_for_same_task(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            receipt = Path(temp_dir) / "receipt.json"
            receipt.write_text(json.dumps({
                "version": "qb_validation_receipt_v1",
                "task_id": "task-receipt",
                "status": "completed",
                "success": True,
                "failures": [],
            }), encoding="utf-8")
            result = static_page._validate_progress_evidence({
                "task_id": "task-receipt",
                "current_step": "package_register",
                "validation_receipt_files": [str(receipt)],
            })
        self.assertIsNone(result)

    def test_fork_validate_reuses_publish_gate_without_writing_page(self):
        binding = {"mode": "task_binding", "status": "prepared", "task_id": "task-a"}
        validation = {"version": "fork_manifest_v1", "source_template_id": "page-source"}
        with mock.patch.object(static_page, "_apply_fork_task_binding", return_value=({"html": "<html>ok</html>"}, binding, None)), \
             mock.patch.object(static_page, "_resolve_publish_agent_reply_template", return_value=({}, {"source_template_id": "page-source"}, None)), \
             mock.patch.object(static_page, "_validate_fork_manifest", return_value=(validation, None)), \
             mock.patch.object(static_page, "cmd_update") as update:
            result = static_page.cmd_fork_validate({"task_id": "task-a", "html": "<html>ok</html>"})
        self.assertEqual(result["code"], 0)
        self.assertTrue(result["fork_manifest_validation"]["ok"])
        update.assert_not_called()


if __name__ == "__main__":
    unittest.main()
