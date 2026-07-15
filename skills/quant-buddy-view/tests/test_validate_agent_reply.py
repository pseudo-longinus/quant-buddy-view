import importlib
import sys
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

validator = importlib.import_module("validate_agent_reply")


class ValidateAgentReplyTest(unittest.TestCase):
    def setUp(self):
        self.url = "https://pages.quantbuddy.cn/pages/official/page_1.html"
        self.contract = {
            "terminal": True,
            "required": True,
            "template_ref": "generic_live_page_delivery_v1",
            "public_url": self.url,
        }

    def test_accepts_complete_template_with_missing_value_placeholders(self):
        draft = f"""**全球资产泡沫监测**

## 这份活页做了什么
监测主要市场，个别市场本轮未返回。

## 核心模块
| 模块 | 当前输出 |
|---|---|
| 估值 | -- |

## 重点怎么看
- 截至 2026-07-14 的最新可得数据。

## 能力边界
- 实际覆盖有限指数样本，不代表完整全球资产。

## 公开链接
- [打开实时活页]({self.url})
"""
        result = validator.validate_reply(self.contract, draft)
        self.assertTrue(result["valid"])

    def test_rejects_missing_section_url_sensitive_content_and_unresolved_field(self):
        draft = """## 核心模块
{latest_value}
Authorization: Bearer secret-token-value
C:\\Users\\name\\draft.md
"""
        result = validator.validate_reply(self.contract, draft)
        codes = [item["code"] for item in result["errors"]]
        self.assertIn("PUBLIC_URL_MISSING", codes)
        self.assertIn("REQUIRED_SECTION_MISSING", codes)
        self.assertIn("UNRESOLVED_FIELDS", codes)
        self.assertIn("SENSITIVE_CONTENT", codes)


if __name__ == "__main__":
    unittest.main()
