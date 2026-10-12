"""因子观察台设计门槛回归测试。

直接在真实浏览器里执行 scripts/dashboard_design_checks.mjs 的 dashboardDesignMetrics，
对三类夹具断言：
1. 合规因子页（结论前置 + 因子导航 + 带日期指标 + ≤3 张主宽图）→ 无因子门槛问题；
2. 退化因子页（通用看板形态：无结论节点、无因子分组、指标缺日期、5 图纵堆）→ 命中门槛；
3. 非因子研究页 → 因子门槛不越界（scope guard）。
"""
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CHECKS = REPO / "skills" / "quant-buddy-view" / "scripts" / "dashboard_design_checks.mjs"

GOOD = """<!doctype html><html lang="zh-CN"><body>
<style>h1{font-size:38px}</style>
<main data-qb-page-design="commodity-factor-watch-v1" data-qb-delivery-kind="result">
<h1>原油涨跌怎么看？· 六因子观察台</h1>
<p data-qb-conclusion>价格与价差结构偏强：内外盘价差 34.5 元/桶（近一年 91% 分位），美元与库存方向相反，成本端形成压制。</p>
<nav data-qb-factor-nav><a href="#f1">①国际锚</a><a href="#f2">②内外盘</a><a href="#f3">③跨区价差</a><a href="#f4">④美元</a><a href="#f5">⑤库存</a><a href="#f6">⑥历史位置</a></nav>
<div data-qb-metric><b>741.6</b><span data-f="date">2026-10-12</span></div>
<div data-qb-fresh-cell data-cadence="daily">三地价格</div>
<div data-qb-fresh-cell data-cadence="snapshot">因子结论</div>
<article data-qb-chart data-chart-span="full"><div class="body line" style="height:200px"></div></article>
<article data-qb-chart data-chart-span="half"><div class="body line" style="height:200px"></div></article>
</main></body></html>"""

BAD = """<!doctype html><html lang="zh-CN"><body>
<main data-qb-page-design="research-v1" data-qb-delivery-kind="result">
<h1>原油六因子观察台</h1>
<div class="card card-number span-auto"><div class="card-head"><h2>沪原油主连 SC</h2></div><b class="big">734.1</b></div>
<section class="card span-full"><div class="card-head"><h2>图一</h2></div><div class="body line" style="height:200px"></div></section>
<section class="card span-full"><div class="card-head"><h2>图二</h2></div><div class="body line" style="height:200px"></div></section>
<section class="card span-full"><div class="card-head"><h2>图三</h2></div><div class="body line" style="height:200px"></div></section>
<section class="card span-full"><div class="card-head"><h2>图四</h2></div><div class="body line" style="height:200px"></div></section>
<section class="card span-full"><div class="card-head"><h2>图五</h2></div><div class="body line" style="height:200px"></div></section>
</main></body></html>"""

SCOPE = """<!doctype html><html lang="zh-CN"><body>
<main data-qb-page-design="research-v1" data-qb-delivery-kind="result">
<h1>估值水位观察</h1>
<div class="card card-number span-auto"><div class="card-head"><h2>PE</h2></div><b class="big">12.3</b></div>
<section class="card span-full"><div class="card-head"><h2>走势</h2></div><div class="body line" style="height:200px"></div></section>
<section class="card span-full"><div class="card-head"><h2>对比</h2></div><div class="body line" style="height:200px"></div></section>
</main></body></html>"""


GATE_PREFIXES = (
    "因子观察台缺少主结论节点", "主结论不在首屏", "主结论仍是占位文本", "首屏看不出",
    "因子卡数量", "实时指标缺少自身数据日期", "缺少数据节奏分层声明", "非折叠 full-width 图表",
)


def _factor_problems(problems):
    return [p for p in problems if str(p).startswith(GATE_PREFIXES)]


class FactorWatchGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = CHECKS.read_text(encoding="utf-8")
        source = source.replace("export function dashboardDesignMetrics", "function dashboardDesignMetrics")
        if "export " in source:
            raise AssertionError("checks module has unexpected exports")
        cls.harness_js = source + "\nwindow.__ddm = dashboardDesignMetrics;"
        from playwright.sync_api import sync_playwright
        cls._pw = sync_playwright().start()
        cls._browser = cls._pw.chromium.launch(channel="chrome")

    @classmethod
    def tearDownClass(cls):
        cls._browser.close()
        cls._pw.stop()

    def _run(self, html):
        page = self._browser.new_page(viewport={"width": 1440, "height": 1000})
        try:
            page.set_content(html)
            page.add_script_tag(content=self.harness_js)
            return page.evaluate("window.__ddm(false)")
        finally:
            page.close()

    def test_good_factor_page_passes_gates(self):
        result = self._run(GOOD)
        self.assertEqual(_factor_problems(result["problems"]), [],
                         f"合规因子页不应命中门槛: {result['problems']}")

    def test_degraded_factor_page_hits_gates(self):
        result = self._run(BAD)
        problems = _factor_problems(result["problems"])
        joined = " ".join(problems)
        self.assertIn("主结论", joined)
        self.assertIn("6 组因子", joined)
        self.assertIn("数据节奏分层", joined)
        self.assertIn("5 张纵向堆叠", joined)

    def test_non_factor_page_not_gated(self):
        result = self._run(SCOPE)
        self.assertEqual(_factor_problems(result["problems"]), [],
                         f"非因子页不应触发因子门槛: {result['problems']}")


if __name__ == "__main__":
    unittest.main()
