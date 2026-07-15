"""Offline regression tests for the card runtime artifact path.

覆盖 C（移除旧 ?cover=1、全面转 card runtime）后最容易回归的结构性问题：
- card_runtime_artifacts / card_runtime_script 产出的 embedded-card-v1 结构完整；
- build_dashboard._render_html 组装页面时嵌入 card runtime artifact、不再有旧的
  ?cover=1 内联卡（binding_script / QBLiveCardHydrate）或悬挂的 f-string slot。

纯离线：不触网、不需要 api_key（构建期取数在调用方 cmd 里，不在 _render_html）。
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import build_dashboard as BD
import live_card as LC


_LIVE_CARD_SPEC = {
    "theme": "blue",
    "title": "短线情绪一眼看懂",
    "description": "核心指标实时刷新，打开即取最新公式包输出。",
    "primary": {"output": "TEMP", "field": "value", "unit": "分"},
    "metrics": [
        {"label": "温度", "output": "TEMP", "field": "value", "unit": "分"},
        {"label": "涨停", "output": "LIMIT_UP", "field": "count"},
    ],
    "tags": ["实时取数", "重点摘要"],
}


def test_card_runtime_artifacts_structure():
    artifacts = LC.card_runtime_artifacts(
        _LIVE_CARD_SPEC,
        endpoint="https://www.quantbuddy.cn/skill",
        package_id="pkg_test",
        signature="sig_test",
        style=".essence-card{color:#000}",
    )
    # 四段结构齐全
    assert "<template data-qb-card-template>" in artifacts
    assert "data-qb-card-style" in artifacts
    assert "data-qb-card-manifest" in artifacts
    assert "data-qb-live-card" in artifacts  # 卡片模板根标记

    # manifest 可解析且字段正确
    start = artifacts.index("data-qb-card-manifest")
    body = artifacts[start:]
    json_text = body[body.index(">") + 1 : body.index("</script>")].strip()
    manifest = json.loads(json_text)
    assert manifest["kind"] == "embedded-card-v1"
    assert manifest["aspect_ratio"] == "4/3"
    assert manifest["package_id"] == "pkg_test"
    assert manifest["signature"] == "sig_test"
    assert manifest["endpoint"] == "https://www.quantbuddy.cn/skill"
    assert isinstance(manifest["required_outputs"], list)
    # metrics 里声明的 output 应进入取数清单
    assert "TEMP" in manifest["required_outputs"]


def test_card_runtime_script_exposes_runtime():
    script = LC.card_runtime_script()
    assert "data-qb-card-runtime" in script
    assert "QBCardRuntimeV1" in script
    assert ".mount" not in script or "mount:" in script  # mount 是对象方法


def test_render_html_emits_card_runtime_not_legacy():
    spec = {
        "title": "市场温度监测",
        "subtitle": "近端情绪速览",
        "package_id": "pkg_test",
        "live_card": _LIVE_CARD_SPEC,
        "panels": [],
    }
    # 纯组装调用（成功即证明 f-string 无悬挂的 live_card_* 变量导致的 NameError）
    html = BD._render_html(
        spec,
        title="市场温度监测",
        subtitle="近端情绪速览",
        panels=[],
        endpoint="https://www.quantbuddy.cn/skill",
        package_id="pkg_test",
        signature="sig_test",
        generated_at="2026-07-14T00:00:00+00:00",
    )

    # 新：card runtime artifact 已嵌入
    assert "data-qb-card-template" in html
    assert "data-qb-card-manifest" in html
    assert "qb-card-runtime-v1" in html

    # 旧：?cover=1 内联卡的运行时痕迹必须消失
    assert "qb-live-card-binding" not in html
    assert "QBLiveCardHydrate" not in html
    assert "?cover=1" not in html

    # 不能残留未替换的 f-string slot
    for slot in ("{live_card_html}", "{live_card_binding}", "{live_card_js}", "{live_card_css}"):
        assert slot not in html
