import importlib
import json
import sys
import unittest
from pathlib import Path
from unittest import mock


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

formula_package = importlib.import_module("formula_package")


class FormulaPackageQueryTest(unittest.TestCase):
    def test_summary_mode_returns_dates_and_interval_stats_without_raw_arrays(self):
        result = formula_package._compact_query_result({
            "code": 0,
            "success": True,
            "package_id": "pkg_1",
            "outputs": {
                "bubble": {
                    "read_mode": "range_data",
                    "data_id": "data_1",
                    "data": {
                        "range_data": {
                            "dates": ["2026-07-01", "2026-07-02", "2026-07-03"],
                            "values": [100, None, 110],
                        }
                    },
                    "error": None,
                }
            },
            "progress": [{"done": 1, "total": 1}],
            "done": {"code": 0},
        }, "summary")

        summary = result["outputs"]["bubble"]["summary"]
        self.assertEqual(summary["first_value"], 100.0)
        self.assertEqual(summary["latest_value"], 110.0)
        self.assertEqual(summary["first_date"], "2026-07-01")
        self.assertEqual(summary["latest_date"], "2026-07-03")
        self.assertAlmostEqual(summary["change_rate_pct"], 10.0)
        self.assertEqual(summary["valid_sample_count"], 2)
        rendered = json.dumps(result, ensure_ascii=False)
        self.assertNotIn('"dates"', rendered)
        self.assertNotIn('"values"', rendered)
        self.assertNotIn('"progress"', rendered)

    def test_query_sends_selected_outputs_and_optional_api_key(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def __iter__(self):
                return iter([
                    b"event: done\n",
                    b'data: {"code":0}\n',
                    b"\n",
                ])

        captured = {}

        def fake_open(req, timeout=None):
            captured["request"] = req
            return FakeResponse()

        with mock.patch.object(formula_package.C._NO_PROXY_OPENER, "open", side_effect=fake_open):
            result = formula_package.query_package(
                "https://example.test",
                "pkg_1",
                "sig",
                outputs=["bubble"],
                api_key="key-test",
            )

        body = json.loads(captured["request"].data.decode("utf-8"))
        self.assertEqual(body["outputs"], ["bubble"])
        self.assertEqual(captured["request"].headers["Authorization"], "Bearer key-test")
        self.assertEqual(result["code"], 0)


if __name__ == "__main__":
    unittest.main()
