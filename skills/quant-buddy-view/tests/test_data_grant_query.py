import importlib
import sys
import unittest
from pathlib import Path
from unittest import mock


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

data_grant = importlib.import_module("data_grant")


class DataGrantQueryTest(unittest.TestCase):
    def test_query_uses_optional_api_key_for_audit_attribution(self):
        with mock.patch.object(data_grant, "_config", return_value=("https://example.test", "key-test")), \
             mock.patch.object(data_grant, "load_credential", return_value={"signature": "sig"}), \
             mock.patch.object(data_grant.C, "http_json", return_value={"code": 0, "data": {"value": 1}}) as request:
            result = data_grant.cmd_query({"grant_id": "dg_1"})

        self.assertEqual(result["code"], 0)
        headers = request.call_args.args[2]
        self.assertEqual(headers["Authorization"], "Bearer key-test")


if __name__ == "__main__":
    unittest.main()
