import importlib
import tempfile
import sys
import unittest
from pathlib import Path
from unittest import mock


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

common = importlib.import_module("common")
trace_context = importlib.import_module("trace_context")


class TraceContextTest(unittest.TestCase):
    def tearDown(self):
        common.set_trace_context(None, None)

    def test_headers_include_current_task_id(self):
        common.set_trace_context("task-123", "生成活页")
        headers = common.headers("sk-test")
        self.assertEqual(headers["x-task-id"], "task-123")
        self.assertNotIn("x-user-query", headers)

    def test_configure_from_params(self):
        context = common.configure_trace_context({"task_id": "task-param", "user_query": "问题"})
        self.assertEqual(context["task_id"], "task-param")
        self.assertIsNone(common.require_trace_context())

    def test_begin_reports_session_and_returns_task_id(self):
        with mock.patch.object(common, "load_config_require_key", return_value={"endpoint": "https://example.test", "api_key": "sk"}), mock.patch.object(
            common, "endpoint_of", return_value="https://example.test"
        ), mock.patch.object(common, "http_json", return_value={"code": 0, "success": True}) as request:
            result = trace_context.cmd_begin({"task_id": "task-reused", "user_query": "生成页面"})
        self.assertEqual(result["code"], 0)
        self.assertEqual(result["task_id"], "task-reused")
        body = request.call_args.args[3]
        headers = request.call_args.args[2]
        self.assertEqual(body["task_id"], "task-reused")
        self.assertEqual(headers["x-task-id"], "task-reused")

    def test_publish_requires_trace_context(self):
        common.set_trace_context(None, None)
        error = common.require_trace_context()
        self.assertEqual(error["error"], "TRACE_CONTEXT_REQUIRED")

    def test_cleanup_only_removes_current_task_temp_params(self):
        with tempfile.TemporaryDirectory() as temp_dir, mock.patch.object(common.tempfile, "gettempdir", return_value=temp_dir):
            own = Path(temp_dir) / "qbv_task-123_direct.json"
            other = Path(temp_dir) / "qbv_task-456_direct.json"
            own.write_text("{}", encoding="utf-8")
            other.write_text("{}", encoding="utf-8")
            deleted = common.cleanup_task_temp_files("task-123")
            self.assertEqual(len(deleted), 1)
            self.assertFalse(own.exists())
            self.assertTrue(other.exists())


if __name__ == "__main__":
    unittest.main()
