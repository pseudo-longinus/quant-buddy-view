"""build_dashboard 面板编排单测：evidence-first 重排、hero 结论、图表自动成对。

只测纯函数层（不触网、不出 HTML），浏览器层验收由 verify_page 集成链覆盖。
"""
import importlib
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "skills" / "quant-buddy-view" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_dashboard as BD


def _panel(kind, **kw):
    base = {"type": kind}
    base.update(kw)
    return base


class EvidenceFirstTests(unittest.TestCase):
    def test_number_led_spec_gets_reordered(self):
        # 原油页形态：7 个 number 开头 + 5 张图 + text 垫底
        panels = ([_panel("number", output=f"n{i}") for i in range(7)]
                  + [_panel("line", output=f"c{i}") for i in range(5)]
                  + [_panel("text", text="结论垫底", title="速读")])
        out = BD._evidence_first_panels({}, panels)
        # >4 个 number → 只保前 4 个关键值在首屏，其余随主图后展开
        self.assertEqual([p["type"] for p in out[:4]], ["number"] * 4)
        self.assertEqual(out[4]["type"], "line")
        self.assertEqual(out[-1]["type"], "text")
        self.assertEqual(len(out), len(panels))
        # 剩余 3 个 number 仍在主图之后
        tail_numbers = [p for p in out[5:] if p["type"] == "number"]
        self.assertEqual(len(tail_numbers), 3)

    def test_four_or_fewer_numbers_stay_front(self):
        panels = ([_panel("number", output=f"n{i}") for i in range(3)]
                  + [_panel("line", output="main")]
                  + [_panel("text", text="口径", title="口径")])
        out = BD._evidence_first_panels({}, panels)
        self.assertEqual([p["type"] for p in out[:3]], ["number", "number", "number"])
        self.assertEqual(out[3]["type"], "line")

    def test_authored_layout_untouched(self):
        panels = [_panel("number", output="n1"), _panel("line", output="c1")]
        out = BD._evidence_first_panels({"layout_order": "authored"}, panels)
        self.assertEqual(out[0]["type"], "number")

    def test_target_selector_panels_untouched(self):
        panels = [_panel("number", output="n1"),
                  _panel("line", output="c1", target_selector="#x"),
                  _panel("line", output="c2")]
        out = BD._evidence_first_panels({}, panels)
        self.assertEqual(out[0]["type"], "number")


class HeroConclusionTests(unittest.TestCase):
    def test_hero_panel_redirected_with_marker(self):
        panels = [_panel("text", hero=True, text="主判断：偏强。", title="结论"),
                  _panel("line", output="c1")]
        out, html = BD._apply_hero_conclusion({}, panels, "2026-10-12 08:00:00")
        self.assertEqual(out[0]["target_selector"], "#qb-hero-conclusion")
        self.assertNotIn("hero", out[0])
        self.assertIn("data-qb-conclusion", html)
        self.assertIn("2026-10-12", html)

    def test_no_hero_returns_empty(self):
        panels = [_panel("line", output="c1")]
        out, html = BD._apply_hero_conclusion({}, panels, "2026-10-12 08:00:00")
        self.assertEqual(html, "")
        self.assertEqual(out, panels)

    def test_multiple_hero_rejected(self):
        panels = [_panel("text", hero=True, text="a"), _panel("text", hero=True, text="b")]
        with self.assertRaises(ValueError):
            BD._apply_hero_conclusion({}, panels, "2026-10-12")

    def test_hero_with_target_selector_rejected(self):
        panels = [_panel("text", hero=True, text="a", target_selector="#y")]
        with self.assertRaises(ValueError):
            BD._apply_hero_conclusion({}, panels, "2026-10-12")


class ChartPairingTests(unittest.TestCase):
    def test_over_three_charts_auto_half(self):
        panels = ([_panel("number", output="n1")]
                  + [_panel("line", output=f"c{i}") for i in range(5)]
                  + [_panel("text", text="口径", title="口径")])
        out = BD._pair_chart_panels({}, panels)
        charts = [p for p in out if p["type"] == "line"]
        self.assertNotIn("span", charts[0])  # 主图保留默认 full
        for c in charts[1:]:
            self.assertEqual(c["span"], "half")

    def test_three_or_fewer_untouched(self):
        panels = [_panel("line", output=f"c{i}") for i in range(3)]
        out = BD._pair_chart_panels({}, panels)
        self.assertNotIn("span", out[0])
        self.assertNotIn("span", out[2])

    def test_explicit_span_respected(self):
        panels = ([_panel("line", output="c0")]
                  + [_panel("line", output="c1", span="full")]
                  + [_panel("line", output=f"c{i}") for i in range(2, 5)])
        out = BD._pair_chart_panels({}, panels)
        charts = [p for p in out if p["type"] == "line"]
        self.assertEqual(charts[1]["span"], "full")  # 显式 full 不覆盖
        self.assertEqual(charts[2]["span"], "half")

    def test_candlestick_and_table_excluded(self):
        panels = ([_panel("line", output=f"c{i}") for i in range(3)]
                  + [_panel("candlestick", output="k1")]
                  + [_panel("table", outputs=["t1"])])
        out = BD._pair_chart_panels({}, panels)
        kline = next(p for p in out if p["type"] == "candlestick")
        table = next(p for p in out if p["type"] == "table")
        self.assertNotIn("span", kline)
        self.assertNotIn("span", table)

    def test_authored_and_embedded_skipped(self):
        panels = [_panel("line", output=f"c{i}") for i in range(5)]
        out = BD._pair_chart_panels({"layout_order": "authored"}, panels)
        self.assertTrue(all("span" not in p for p in out))


if __name__ == "__main__":
    unittest.main()
