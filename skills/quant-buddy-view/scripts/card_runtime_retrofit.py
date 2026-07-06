#!/usr/bin/env python3
"""Build standalone card-runtime artifacts for already published QBV pages."""

import hashlib
import html as _html
import json
import os
import re
import urllib.error
import urllib.request

import common as C


CARD_RUNTIME_KIND = "embedded-card-v1"
CARD_RUNTIME_VERSION = "1.0.1"
START = "<!-- QB_CARD_RUNTIME_ARTIFACTS_START -->"
END = "<!-- QB_CARD_RUNTIME_ARTIFACTS_END -->"


def first_tagged_block(html, tag, marker):
    match = re.search(r"<%s\b(?=[^>]*\b%s\b)[^>]*>([\s\S]*?)</%s>" % (tag, marker, tag), html or "", re.I)
    return (match.group(1).strip() if match else "")


def parse_manifest(html):
    text = first_tagged_block(html, "script", "data-qb-card-manifest")
    if text:
        data = json.loads(text)
        existing = _manifest_packages(data)
        legacy = _parse_legacy_packages(html)
        if legacy:
            seen = {
                (pkg.get("endpoint"), pkg.get("package_id"), pkg.get("signature"))
                for pkg in existing
            }
            merged = []
            for pkg in (data.get("packages") or []):
                if isinstance(pkg, dict):
                    merged.append(pkg)
            for pkg in legacy:
                key = (pkg.get("endpoint"), pkg.get("package_id"), pkg.get("signature"))
                if key in seen:
                    continue
                seen.add(key)
                merged.append(pkg)
            data["packages"] = merged
        packages = _manifest_packages(data)
        if not packages:
            raise ValueError("card manifest 缺少 package_id/signature/endpoint")
        return data

    packages = _parse_legacy_packages(html)
    if not packages:
        raise ValueError("未找到 script[data-qb-card-manifest] 或旧页公式包配置")
    first = packages[0]
    return {
        "version": CARD_RUNTIME_VERSION,
        "kind": CARD_RUNTIME_KIND,
        "endpoint": first["endpoint"],
        "package_id": first["package_id"],
        "signature": first["signature"],
        "packages": packages,
    }


def _key_pattern(key):
    if key == "package_id":
        return r"(?:package_id|packageId)"
    return re.escape(key)


def _extract_js_string(block, key):
    match = re.search(r"(?:['\"])?%s(?:['\"])?\s*:\s*(['\"])(.*?)\1" % _key_pattern(key), block or "", re.S)
    return match.group(2).strip() if match else ""


def _parse_legacy_packages(html):
    packages = []
    seen = set()
    package_key = r"(?:package_id|packageId)"
    pattern = re.compile(r"([A-Za-z_$][\w$-]*)\s*:\s*\{([^{}]*?\b%s\b[^{}]*?\bsignature\b[^{}]*?)\}" % package_key, re.S)
    for match in pattern.finditer(html or ""):
        role, block = match.group(1), match.group(2)
        endpoint = _extract_js_string(block, "endpoint")
        package_id = _extract_js_string(block, "package_id")
        signature = _extract_js_string(block, "signature")
        key = (endpoint, package_id, signature)
        if not endpoint or not package_id or not signature or key in seen:
            continue
        seen.add(key)
        packages.append({
            "role": role,
            "endpoint": endpoint,
            "package_id": package_id,
            "signature": signature,
        })
    if packages:
        return packages

    for match in re.finditer(r"\{([^{}]*?\b%s\b[^{}]*?\bsignature\b[^{}]*?)\}" % package_key, html or "", re.S):
        block = match.group(1)
        endpoint = _extract_js_string(block, "endpoint")
        package_id = _extract_js_string(block, "package_id")
        signature = _extract_js_string(block, "signature")
        key = (endpoint, package_id, signature)
        if not endpoint or not package_id or not signature or key in seen:
            continue
        seen.add(key)
        packages.append({
            "role": "package_%d" % (len(packages) + 1),
            "endpoint": endpoint,
            "package_id": package_id,
            "signature": signature,
        })
    if packages:
        return packages

    endpoint = _extract_js_string(html, "endpoint")
    package_pattern = re.compile(r"(?:['\"])?%s(?:['\"])?\s*:\s*(['\"])(.*?)\1" % package_key, re.S)
    for match in package_pattern.finditer(html or ""):
        package_id = match.group(2).strip()
        window = html[match.end(): min(len(html), match.end() + 1600)]
        signature = _extract_js_string(window, "signature")
        local_endpoint = _extract_js_string(window, "endpoint") or endpoint
        key = (local_endpoint, package_id, signature)
        if not local_endpoint or not package_id or not signature or key in seen:
            continue
        seen.add(key)
        packages.append({
            "role": "package_%d" % (len(packages) + 1),
            "endpoint": local_endpoint,
            "package_id": package_id,
            "signature": signature,
        })
    return packages


def _manifest_packages(manifest):
    packages = []
    for index, item in enumerate(manifest.get("packages") or [], start=1):
        if not isinstance(item, dict):
            continue
        endpoint = item.get("endpoint") or manifest.get("endpoint")
        package_id = item.get("package_id") or item.get("packageId")
        signature = item.get("signature")
        if endpoint and package_id and signature:
            packages.append({
                "role": item.get("role") or "package_%d" % index,
                "endpoint": endpoint,
                "package_id": package_id,
                "signature": signature,
                "outputs": list(item.get("outputs") or []),
            })
    if packages:
        return packages
    package_id = manifest.get("package_id") or manifest.get("packageId")
    if manifest.get("endpoint") and package_id and manifest.get("signature"):
        return [{
            "role": "default",
            "endpoint": manifest["endpoint"],
            "package_id": package_id,
            "signature": manifest["signature"],
            "outputs": list(manifest.get("required_outputs") or []),
        }]
    return []


def _api_url(endpoint, path):
    return C.api_url(endpoint, path)


def _post_json_stream(url, body, timeout=90):
    req = urllib.request.Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers=C.headers(accept="text/event-stream"),  # 带上 x-skill-version / x-skill-name
        method="POST",
    )
    try:
        with C._NO_PROXY_OPENER.open(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise ValueError("queryFormulaPackage HTTP %s: %s" % (exc.code, raw[:300]))


def _parse_sse(text):
    outputs = {}
    done = None
    for block in re.split(r"\n\s*\n", (text or "").replace("\r", "")):
        event = ""
        data_lines = []
        for line in block.split("\n"):
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data_lines.append(re.sub(r"^ ", "", line[5:]))
        if not data_lines:
            continue
        try:
            payload = json.loads("\n".join(data_lines))
        except Exception:
            continue
        if event == "result" and payload.get("output"):
            outputs[payload["output"]] = payload
        elif event == "done":
            done = payload
    return outputs, done


def query_all_outputs(manifest):
    all_outputs = {}
    resolved = []
    for pkg in _manifest_packages(manifest):
        raw = _post_json_stream(
            _api_url(pkg["endpoint"], "/skill/queryFormulaPackage"),
            {"package_id": pkg["package_id"], "signature": pkg["signature"]},
        )
        outputs, done = _parse_sse(raw)
        if not outputs:
            raise ValueError(
                "公式包 %s 未返回任何 outputs；done=%s"
                % (pkg["package_id"], json.dumps(done or {}, ensure_ascii=False))
            )
        keys = _sort_keys(outputs.keys())
        resolved.append({
            "role": pkg.get("role") or "package_%d" % (len(resolved) + 1),
            "endpoint": pkg["endpoint"],
            "package_id": pkg["package_id"],
            "signature": pkg["signature"],
            "outputs": keys,
        })
        for key, value in outputs.items():
            all_outputs.setdefault(key, value)
    if not all_outputs:
        raise ValueError("公式包未返回任何 outputs")
    manifest["_packages_resolved"] = resolved
    return all_outputs


def _e(text):
    return _html.escape(str(text or ""), quote=True)


def _title_from_html(html):
    match = re.search(r"<title[^>]*>([\s\S]*?)</title>", html or "", re.I)
    if not match:
        return ""
    return re.sub(r"\s+", " ", _html.unescape(match.group(1))).strip()


def _sort_keys(keys):
    return sorted(set(keys), key=lambda k: (k.lower(), k))


def _generic_card_keys(keys):
    def score(key):
        low = key.lower()
        if "proxy" in low:
            return (80, low)
        if "amount" in low or "volume" in low:
            return (70, low)
        groups = [
            (("score", "signal", "strength", "health"), 0),
            (("ret", "return", "pct", "mom"), 1),
            (("nav", "px", "price", "close"), 2),
            (("pe", "pb", "roe", "eps", "rev"), 3),
            (("count", "hit", "win", "rank"), 4),
        ]
        for words, rank in groups:
            if any(word in low for word in words):
                return (rank, low)
        return (20, low)
    return sorted(set(keys), key=score)


def _card(page_id, title, description, core, theme="orange"):
    return """<section class="qb-card-artifact" data-qb-live-card data-theme="{theme}">
  <div class="qb-card-meta">
    <span data-qb-live-card-brand></span>
    <time data-qb-live-card-date data-qb-bind="date">2026-07-03</time>
  </div>
  <h1 data-qb-live-card-title>{title}</h1>
  <p data-qb-live-card-description>{description}</p>
  <section class="qb-card-core" data-qb-live-card-core data-card-page="{page_id}">
{core}
  </section>
</section>""".format(
        theme=_e(theme),
        page_id=_e(page_id),
        title=_e(title),
        description=_e(description),
        core=core,
    )


def _metric(label, output, fmt="number", klass=""):
    return """    <div class="qb-mini-metric {klass}">
      <span>{label}</span>
      <b data-qb-value data-output="{output}" data-format="{fmt}">0</b>
    </div>""".format(label=_e(label), output=_e(output), fmt=_e(fmt), klass=_e(klass))


def _bar(label, output, fmt="pct"):
    return """    <div class="qb-card-bar-row">
      <span>{label}</span>
      <b data-qb-value data-output="{output}" data-format="{fmt}">0%</b>
      <i><em data-qb-bar data-output="{output}" data-format="{fmt}"></em></i>
    </div>""".format(label=_e(label), output=_e(output), fmt=_e(fmt))


def _group(label, outputs):
    return """    <div class="qb-card-bar-row" data-qb-group="{outputs}">
      <span>{label}</span>
      <b data-qb-group-score>0%</b>
      <i><em data-qb-group-bar></em></i>
    </div>""".format(label=_e(label), outputs=_e(" ".join(outputs)))


def _return_row(label, output, base=""):
    return """      <div class="qb-race-row">
        <span>{label}</span>
        <b data-qb-relative-return data-output="{output}" data-base="{base}">0%</b>
        <i><em data-qb-relative-return-bar data-output="{output}" data-base="{base}"></em></i>
      </div>""".format(label=_e(label), output=_e(output), base=_e(base))


def _value_row(label, output, fmt="number1"):
    return """      <div class="qb-race-row">
        <span>{label}</span>
        <b data-qb-value data-output="{output}" data-format="{fmt}">0</b>
        <i><em data-qb-bar data-output="{output}" data-format="{fmt}"></em></i>
      </div>""".format(label=_e(label), output=_e(output), fmt=_e(fmt))


def _spread_row(label, fut, spot):
    return """      <div class="qb-race-row">
        <span>{label}</span>
        <b data-qb-spread data-a="{fut}" data-b="{spot}">0</b>
        <i><em data-qb-spread-bar data-a="{fut}" data-b="{spot}"></em></i>
      </div>""".format(label=_e(label), fut=_e(fut), spot=_e(spot))


def _top_list(title, output, fmt="signed-pct", limit=4):
    return """    <div class="qb-top-list" data-qb-top-list data-output="{output}" data-format="{fmt}" data-limit="{limit}">
      <strong>{title}</strong>
      <div class="qb-top-list-body">
        <div><span>--</span><b>0</b></div>
        <div><span>--</span><b>0</b></div>
        <div><span>--</span><b>0</b></div>
      </div>
    </div>""".format(title=_e(title), output=_e(output), fmt=_e(fmt), limit=int(limit))


def _top_metric(label, output, fmt="signed-pct"):
    return """<div><span>{label}</span><b data-qb-top-value data-output="{output}" data-format="{fmt}">--</b></div>""".format(
        label=_e(label),
        output=_e(output),
        fmt=_e(fmt),
    )


def _industry_top_list(title, output, mask_keys, fmt="signed-pct", limit=4):
    return """    <div class="qb-top-list" data-qb-industry-top-list data-output="{output}" data-masks="{masks}" data-format="{fmt}" data-limit="{limit}">
      <strong>{title}</strong>
      <div class="qb-top-list-body">
        <div><span>--</span><b>0</b></div>
        <div><span>--</span><b>0</b></div>
        <div><span>--</span><b>0</b></div>
      </div>
    </div>""".format(title=_e(title), output=_e(output), masks=_e(" ".join(mask_keys)), fmt=_e(fmt), limit=int(limit))


def _industry_top_metric(label, output, mask_keys, fmt="signed-pct"):
    return """<div><span>{label}</span><b data-qb-industry-top-value data-output="{output}" data-masks="{masks}" data-format="{fmt}">--</b></div>""".format(
        label=_e(label),
        output=_e(output),
        masks=_e(" ".join(mask_keys)),
        fmt=_e(fmt),
    )


def _multi_spark(outputs, labels="", klass=""):
    return """    <svg class="qb-spark qb-multi-spark {klass}" data-qb-multi-spark data-outputs="{outputs}" data-labels="{labels}" viewBox="0 0 300 96" role="img" aria-label="走势对比"></svg>""".format(
        outputs=_e(" ".join(outputs)),
        labels=_e(labels),
        klass=_e(klass),
    )


def _build_page_card(page_id, title, keys):
    keys_set = set(keys)
    if page_id == "page_eebb0dac7e1f1a348f404ace":
        required = [k for k in [
            "LUCNT", "XD_PX", "XD_RET", "N1TOT", "PROMO1", "WINRATE1", "AVGRET1", "AVG5D1",
            "N2TOT", "PROMO2", "WINRATE2", "AVGRET2", "AVG5D2", "N3TOT", "PROMO3", "WINRATE3", "AVGRET3", "AVG5D3",
        ] if k in keys_set]
        core = """    <div class="qb-ladder-card">
      <div class="qb-ladder-thesis">
        <small>晋级关口 1→2</small>
        <b data-qb-value data-output="PROMO1" data-format="pct">0%</b>
        <span>次日晋级率</span>
      </div>
      <div class="qb-ladder-track" aria-label="连板晋级阶梯">
        <div class="qb-ladder-step is-first"><span>1连样本</span><b data-qb-value data-output="N1TOT" data-format="int">0</b><i data-qb-value data-output="AVGRET1" data-format="signed-pct">0%</i></div>
        <div class="qb-ladder-step is-second"><span>2连晋级</span><b data-qb-value data-output="PROMO2" data-format="pct">0%</b><i data-qb-value data-output="WINRATE2" data-format="pct">0%</i></div>
        <div class="qb-ladder-step is-third"><span>3连强度</span><b data-qb-value data-output="AVG5D3" data-format="signed-pct">0%</b><i data-qb-value data-output="PROMO3" data-format="pct">0%</i></div>
      </div>
    </div>"""
        return required, _card(page_id, "连板梯队体检", "主板1-3连板样本实时回测，沿阶梯看晋级与收益。", core, "red")

    if page_id == "page_429673b28e6229e9d315fbd5":
        groups = {
            "CPO": [k for k in keys if k.startswith("cpo")],
            "液冷/电力": [k for k in keys if k.startswith("vdc")],
            "机器人": [k for k in keys if k.startswith("bot")],
            "国产算力": [k for k in keys if k.startswith("gls") or k.startswith("bm")],
        }
        required = [k for vals in groups.values() for k in vals]
        core = "\n".join([_group(label, vals) for label, vals in groups.items() if vals])
        core += "\n    <div class=\"qb-card-tags\"><span>四线轮动</span><span>实时强弱</span><span>主题观察</span></div>"
        return required, _card(page_id, "AI四线轮动", "四条主线同步刷新，扫一眼看相对强弱。", core, "red")

    if page_id == "page_97d4c118b10e43f5581d850d":
        required = [k for k in [
            "REGIME", "ATKW", "T10_SCORE", "T10_ATK", "T10_DEF", "T10_RET", "T10_DIV", "T10_PE", "T10_MOM", "NAV", "NAV3Y", "IDXPX", "IDXPX3Y", "IDXRET",
        ] if k in keys_set]
        core = """    <div class="qb-card-visual-stack">
{spark}
      <div class="qb-regime-meter" data-qb-meter data-output="ATKW" data-format="pct">
        <div><span>防御</span><b data-qb-value data-output="ATKW" data-format="pct">0%</b><span>进攻</span></div>
        <i><em data-qb-meter-bar data-output="ATKW" data-format="pct"></em></i>
      </div>
      <div class="qb-window-strip">
        {rows}
      </div>
    </div>""".format(
            spark=_multi_spark([k for k in ["NAV", "IDXPX"] if k in keys_set], "组合 基准") if {"NAV", "IDXPX"} & keys_set else "",
            rows="\n".join([
                '<div><span>十强评分</span><b data-qb-value data-output="T10_SCORE" data-format="number1">0</b></div>' if "T10_SCORE" in keys_set else "",
                '<div><span>动量因子</span><b data-qb-value data-output="T10_MOM" data-format="number1">0</b></div>' if "T10_MOM" in keys_set else "",
                '<div><span>组合收益</span><b data-qb-value data-output="T10_RET" data-format="signed-pct">0%</b></div>' if "T10_RET" in keys_set else "",
            ]),
        )
        return required, _card(page_id, "十强组合攻守切换", "趋势滤波调节动量与防御因子，沪深300池每日重排。", core, "orange")

    if page_id == "page_950ff15cb39053c439dff1d8":
        required = [k for k in ["st_count", "st_absret", "st_turn", "st_hit5", "st_hit10", "mb_absret", "mb_turn", "mb_hit10"] if k in keys_set]
        core = """    <div class="qb-event-card">
      <div class="qb-event-window">
        <span>涨跌幅口径</span>
        <b>5→10</b>
        <i>ST新规</i>
      </div>
      <div class="qb-st-lanes">
        <div class="qb-st-lane is-hot"><span>ST池波动</span><b data-qb-value data-output="st_absret" data-format="pct-smart">0%</b><i><em data-qb-bar data-output="st_absret" data-format="pct-smart"></em></i></div>
        <div class="qb-st-lane"><span>主板对照</span><b data-qb-value data-output="mb_hit10" data-format="pct-smart">0%</b><i><em data-qb-bar data-output="mb_hit10" data-format="pct-smart"></em></i></div>
      </div>
      <div class="qb-event-chips">
        <div><span>10cm命中</span><b data-qb-value data-output="st_hit10" data-format="pct-smart">0%</b></div>
        <div><span>换手温度</span><b data-qb-value data-output="st_turn" data-format="pct-smart">0%</b></div>
        <div><span>样本数</span><b data-qb-value data-output="st_count" data-format="int">0</b></div>
      </div>
    </div>"""
        return required, _card(page_id, "ST新规波动追踪", "主板ST池与非ST对照组同口径追踪，打开即取最新。", core, "red")

    if page_id == "page_47685d2af5441d6c1d77a26e":
        stocks = [k for k in keys if k.endswith("_px") and k != "HS300_px"]
        required = stocks + (["HS300_px"] if "HS300_px" in keys_set else [])
        core = """    <div class="qb-risk-map">
      <div class="qb-risk-field">
        <i></i><i></i><i></i>
        <div class="qb-risk-radius"><span>分化半径</span><b data-qb-dispersion data-outputs="{stocks}">0%</b></div>
        <small>组合风险场</small>
      </div>
      <div class="qb-risk-summary">
        <div><span>最强暴露</span><b data-qb-best data-outputs="{stocks}">0%</b></div>
        <div><span>八股分化</span><b data-qb-dispersion data-outputs="{stocks}">0%</b></div>
        <div><span>基准锚</span><b data-qb-return data-output="HS300_px">0%</b></div>
      </div>
    </div>""".format(stocks=_e(" ".join(stocks)))
        return required, _card(page_id, "风险不按持仓等分", "八股组合实时重算：相关性、风险贡献与回撤一眼看清。", core, "orange")

    if page_id == "page_5e22e113941261d15ab1caaa":
        required = [k for k in ["dash_score", "dash_ret5", "dash_spec", "dash_low"] if k in keys_set]
        core = """    <div class="qb-card-dashboard">
      <div class="qb-score-orbit" data-qb-score-orbit data-output="dash_score">
        <b data-qb-value data-output="dash_score" data-format="number1">0</b>
        <span>主题强度</span>
      </div>
      <div class="qb-race-list compact">
{rows}
      </div>
    </div>""".format(rows="\n".join([
            _value_row("5日动量", "dash_ret5", "signed-pct") if "dash_ret5" in keys_set else "",
            _value_row("投机温度", "dash_spec", "number1") if "dash_spec" in keys_set else "",
            _value_row("低位扩散", "dash_low", "number1") if "dash_low" in keys_set else "",
        ]))
        return required, _card(page_id, "机器人主题热度盘", "强度、动量与扩散同步刷新，先看主题是否仍在扩散。", core, "green")

    if page_id == "page_f22b9f8a3033bc0f6018bdc0":
        required = [k for k in ["anom_score", "anom_ret", "anom_vol", "first_score", "breakout_score", "industry_score", "ind_ret1", "ind_breadth"] if k in keys_set]
        core = """    <div class="qb-alert-board">
      <div class="qb-alert-score"><span>异动总分</span><b data-qb-value data-output="anom_score" data-format="number1">0</b></div>
      <div class="qb-race-list compact">
{rows}
      </div>
    </div>""".format(rows="\n".join([
            _value_row("首板活跃", "first_score", "number1") if "first_score" in keys_set else "",
            _value_row("突破结构", "breakout_score", "number1") if "breakout_score" in keys_set else "",
            _value_row("异动涨幅", "anom_ret", "signed-pct") if "anom_ret" in keys_set else "",
            _value_row("异动放量", "anom_vol", "number1") if "anom_vol" in keys_set else "",
        ]))
        return required, _card(page_id, "全市场异动结构盘", "把首板、突破和行业扩散压成一张实时异动地图。", core, "blue")

    if page_id == "page_0a1258e91eadd8609728f249":
        required = [k for k in ["nvda_px", "nvda_rev_q", "nvda_pe"] if k in keys_set]
        core = """    <div class="qb-card-visual-stack">
{spark}
      <div class="qb-race-list compact">
{rows}
      </div>
    </div>""".format(
            spark=_multi_spark([k for k in ["nvda_rev_q", "nvda_px"] if k in keys_set], "收入 股价") if {"nvda_rev_q", "nvda_px"} & keys_set else "",
            rows="\n".join([
                _value_row("实时股价", "nvda_px", "number1") if "nvda_px" in keys_set else "",
                _value_row("季度收入", "nvda_rev_q", "number1") if "nvda_rev_q" in keys_set else "",
                _value_row("PE", "nvda_pe", "number1") if "nvda_pe" in keys_set else "",
            ]),
        )
        return required, _card(page_id, "英伟达收入路径重算", "收入预测、估值倍数和股价同屏刷新，盯住财报后的锚。", core, "green")

    if page_id == "page_fd3f58773ac4a0a0d7a6585e":
        metric_keys = [k for k in ["ret_20", "ret_5", "ret_60"] if k in keys_set]
        mask_keys = [k for k in keys if k.startswith("sw_")]
        required = metric_keys + mask_keys
        core = """    <div class="qb-card-visual-stack">
{top}
      <div class="qb-window-strip">
        {m5}
        {m20}
        {m60}
      </div>
    </div>""".format(
            top=_industry_top_list("20日强势行业", "ret_20", mask_keys, "signed-pct", 4) if "ret_20" in keys_set and mask_keys else _top_list("20日强势行业", "ret_20", "signed-pct", 4) if "ret_20" in keys_set else "",
            m5=_industry_top_metric("5日领涨", "ret_5", mask_keys, "signed-pct") if "ret_5" in keys_set and mask_keys else _top_metric("5日最强", "ret_5", "signed-pct") if "ret_5" in keys_set else "",
            m20=_industry_top_metric("20日领涨", "ret_20", mask_keys, "signed-pct") if "ret_20" in keys_set and mask_keys else _top_metric("20日最强", "ret_20", "signed-pct") if "ret_20" in keys_set else "",
            m60=_industry_top_metric("60日领涨", "ret_60", mask_keys, "signed-pct") if "ret_60" in keys_set and mask_keys else _top_metric("60日最强", "ret_60", "signed-pct") if "ret_60" in keys_set else "",
        )
        return required, _card(page_id, "行业轮动雷达", "三窗口同步看强势与拥挤，避免只盯单日涨跌。", core, "green")

    if page_id == "page_221a3ffae084d983d1b509d4":
        required = _generic_card_keys(keys)[:3]
        labels = ["一板家数", "二板家数", "三板以上"]
        rows = "\n".join([_value_row(labels[i], key, "int") for i, key in enumerate(required[:3])])
        core = """    <div class="qb-limit-structure">
      <div class="qb-signal-mark">涨停</div>
      <div class="qb-race-list compact">
{rows}
      </div>
    </div>""".format(rows=rows)
        return required, _card(page_id, "涨跌停结构复盘", "一板、二板与高标梯队同步刷新，看市场接力温度。", core, "red")

    if page_id == "page_4b488204774ddb45739d39cc":
        required = [k for k in ["RET20_CAM", "RET20_HG", "RET20_KC50"] if k in keys_set]
        core = """    <div class="qb-race-list">
{rows}
    </div>
    <div class="qb-card-tags"><span>AI硬科技</span><span>相对科创50</span><span>20日强弱</span></div>""".format(rows="\n".join([
            _value_row("寒武纪", "RET20_CAM", "signed-pct") if "RET20_CAM" in keys_set else "",
            _value_row("海光信息", "RET20_HG", "signed-pct") if "RET20_HG" in keys_set else "",
            _value_row("科创50", "RET20_KC50", "signed-pct") if "RET20_KC50" in keys_set else "",
        ]))
        return required, _card(page_id, "AI硬科技组合强弱", "组合与科创50同屏对照，先判断硬科技主线是否跑赢。", core, "blue")

    if page_id == "page_1256a77743fab9aa39838ce9":
        required = [k for k in ["IC_C0_fut_px", "IC_C1_fut_px", "IC_spot_px"] if k in keys_set]
        core = """    <div class="qb-basis-board">
      <div class="qb-basis-main">
        <span>主连基差</span>
        <b data-qb-spread data-a="IC_C0_fut_px" data-b="IC_spot_px">0</b>
      </div>
      <div class="qb-race-list compact">
{rows}
      </div>
    </div>""".format(rows="\n".join([
            _spread_row("主连-现货", "IC_C0_fut_px", "IC_spot_px") if {"IC_C0_fut_px", "IC_spot_px"} <= keys_set else "",
            _spread_row("次主连-现货", "IC_C1_fut_px", "IC_spot_px") if {"IC_C1_fut_px", "IC_spot_px"} <= keys_set else "",
            _value_row("现货锚", "IC_spot_px", "number1") if "IC_spot_px" in keys_set else "",
        ]))
        return required, _card(page_id, "股指期货基差监控", "主连、次主连和现货同口径刷新，重点看贴水收敛。", core, "blue")

    if page_id == "page_c0c1e05bdad501fbb40641a3":
        required = [k for k in ["OPT_NAV", "BENCH_NAV", "PRICE", "FINAL_OPT", "RSRS_STD", "POS_OPT"] if k in keys_set]
        core = """    <div class="qb-card-visual-stack">
{spark}
      <div class="qb-race-list compact">
{rows}
      </div>
    </div>""".format(
            spark=_multi_spark([k for k in ["OPT_NAV", "BENCH_NAV", "PRICE"] if k in keys_set], "RSRS 基准 价格") if {"OPT_NAV", "BENCH_NAV"} & keys_set else "",
            rows="\n".join([
                _value_row("优化净值", "FINAL_OPT", "number1") if "FINAL_OPT" in keys_set else "",
                _value_row("RSRS标准分", "RSRS_STD", "number1") if "RSRS_STD" in keys_set else "",
                _value_row("当前仓位", "POS_OPT", "pct") if "POS_OPT" in keys_set else "",
            ]),
        )
        return required, _card(page_id, "RSRS信号复现", "策略净值、基准与价格同屏，保留择时方法的走势语法。", core, "orange")

    if page_id == "page_daefbab88424b05228203555":
        stock_keys = [k for k in ["RET1_HAN", "RET1_HAI", "RET1_LAN", "RET1_JIN", "RET1_ZHO"] if k in keys_set]
        rel_keys = [k for k in ["RELCUM20_HAN", "RELCUM20_HAI", "RELCUM20_LAN", "RELCUM20_JIN", "RELCUM20_ZHO"] if k in keys_set]
        required = stock_keys + rel_keys[:3]
        labels = [("寒武纪", "RET1_HAN"), ("海光信息", "RET1_HAI"), ("澜起科技", "RET1_LAN"), ("金山办公", "RET1_JIN"), ("中芯国际", "RET1_ZHO")]
        core = """    <div class="qb-race-list">
{rows}
    </div>
    <div class="qb-card-tags"><span>五只首选</span><span>日内脉搏</span><span>相对科创50</span></div>""".format(rows="\n".join([
            _value_row(label, key, "signed-pct") for label, key in labels if key in keys_set
        ]))
        return required, _card(page_id, "AI科创链持仓脉搏", "五只首选按日涨跌同步刷新，方便持仓后复核主线。", core, "green")

    if page_id == "page_d4ca42720380d1b5bc3207c0":
        required = [k for k in ["pe_pctile", "pb_pctile", "pcf_pctile"] if k in keys_set]
        core = """    <div class="qb-valuation-waterline">
      <div class="qb-waterline" data-qb-meter data-output="pe_pctile" data-format="pct-smart">
        <span>PE水位</span><b data-qb-value data-output="pe_pctile" data-format="pct-smart">0%</b><i><em data-qb-meter-bar data-output="pe_pctile" data-format="pct-smart"></em></i>
      </div>
      <div class="qb-race-list compact">
{rows}
      </div>
    </div>""".format(rows="\n".join([
            _value_row("PB水位", "pb_pctile", "pct-smart") if "pb_pctile" in keys_set else "",
            _value_row("PCF水位", "pcf_pctile", "pct-smart") if "pcf_pctile" in keys_set else "",
            _value_row("PE水位", "pe_pctile", "pct-smart") if "pe_pctile" in keys_set else "",
        ]))
        return required, _card(page_id, "茅台估值水位体检", "PE、PB、PCF历史分位同屏，先看贵不贵。", core, "green")

    if page_id == "page_f455566c55945624ca734142":
        required = [k for k in ["px_csi300", "px_hsi", "fx_hkdcny"] if k in keys_set]
        core = """    <div class="qb-card-visual-stack">
{spark}
      <div class="qb-race-list compact">
{rows}
      </div>
    </div>""".format(
            spark=_multi_spark([k for k in ["px_csi300", "px_hsi"] if k in keys_set], "A股 港股") if {"px_csi300", "px_hsi"} & keys_set else "",
            rows="\n".join([
                _return_row("沪深300", "px_csi300") if "px_csi300" in keys_set else "",
                _return_row("恒生指数", "px_hsi") if "px_hsi" in keys_set else "",
                _value_row("港币兑人民币", "fx_hkdcny", "number1") if "fx_hkdcny" in keys_set else "",
            ]),
        )
        return required, _card(page_id, "A/H溢价结构观察", "A股、港股与汇率三条线同屏，判断溢价抬升来自哪里。", core, "blue")

    if page_id == "page_c0d9672a5bc7ee78160e17e9":
        required = [k for k in ["ret_3m", "ret_6m", "ret_12m"] if k in keys_set]
        core = """    <div class="qb-card-visual-stack">
{top}
      <div class="qb-window-strip">
        {m3}
        {m6}
        {m12}
      </div>
    </div>""".format(
            top=_top_list("低估高质银行", "ret_12m", "signed-pct", 4) if "ret_12m" in keys_set else "",
            m3=_top_metric("3月最强", "ret_3m", "signed-pct") if "ret_3m" in keys_set else "",
            m6=_top_metric("6月最强", "ret_6m", "signed-pct") if "ret_6m" in keys_set else "",
            m12=_top_metric("12月最强", "ret_12m", "signed-pct") if "ret_12m" in keys_set else "",
        )
        return required, _card(page_id, "银行低估高质排序", "三周期收益窗口压缩成一张排行，观察估值修复持续性。", core, "green")

    if page_id == "page_9083914f7f1af31ebbf13a33":
        required = [k for k in ["px_bank_index", "px_ccb", "px_cib"] if k in keys_set]
        core = """    <div class="qb-card-visual-stack">
{spark}
      <div class="qb-race-list compact">
{rows}
      </div>
    </div>""".format(
            spark=_multi_spark([k for k in ["px_cib", "px_ccb", "px_bank_index"] if k in keys_set], "招行/同业 行业") if {"px_cib", "px_ccb", "px_bank_index"} & keys_set else "",
            rows="\n".join([
                _return_row("招商银行", "px_cib", "px_bank_index") if {"px_cib", "px_bank_index"} <= keys_set else "",
                _return_row("建设银行", "px_ccb", "px_bank_index") if {"px_ccb", "px_bank_index"} <= keys_set else "",
                _return_row("银行指数", "px_bank_index") if "px_bank_index" in keys_set else "",
            ]),
        )
        return required, _card(page_id, "招行同业相对表现", "银行指数作锚，比较招行与同业是否跑出相对优势。", core, "blue")

    if page_id == "page_e8595ec9da843c88021859c4":
        required = [k for k in ["px_gx", "px_tf", "px_xys"] if k in keys_set]
        core = """    <div class="qb-card-visual-stack">
{spark}
      <div class="qb-race-list compact">
{rows}
      </div>
    </div>""".format(
            spark=_multi_spark([k for k in ["px_gx", "px_tf", "px_xys"] if k in keys_set], "光迅 天孚 新易盛") if {"px_gx", "px_tf", "px_xys"} & keys_set else "",
            rows="\n".join([
                _return_row("光迅科技", "px_gx") if "px_gx" in keys_set else "",
                _return_row("天孚通信", "px_tf") if "px_tf" in keys_set else "",
                _return_row("新易盛", "px_xys") if "px_xys" in keys_set else "",
            ]),
        )
        return required, _card(page_id, "光模块龙头竞速", "三只龙头同屏比相对走势，先看谁在贡献风险收益。", core, "orange")

    required = _generic_card_keys(keys)[:3]
    core = "\n".join([_metric(k, k, "number1") for k in required])
    return required, _card(page_id, title or "实时活卡", "核心输出实时刷新，打开即取最新。", core, "orange")


STYLE = r"""
.qb-card-artifact,.qb-card-artifact *{box-sizing:border-box}
.qb-card-artifact[data-qb-live-card]{
  --accent:#ef7a1a;--ink:#201713;--muted:#725f4c;--line:#ead8c6;--soft:#fff7ec;
  width:100%;height:100%;aspect-ratio:4/3;container-type:inline-size;display:grid;grid-template-rows:auto auto auto minmax(0,1fr);
  gap:clamp(4px,1.4%,9px);padding:clamp(12px,4.6%,24px);background:linear-gradient(135deg,#fffdf8 0%,#fff5e8 100%);
  color:var(--ink);font-family:"Inter","PingFang SC","Microsoft YaHei",system-ui,sans-serif;overflow:hidden;border-top:5px solid var(--accent)
}
.qb-card-artifact[data-theme=red]{--accent:#d71920}
.qb-card-artifact[data-theme=green]{--accent:#16825a;--line:#cfe5d9;--soft:#f1fbf5}
.qb-card-artifact[data-theme=blue]{--accent:#1f5fbf;--line:#d4e2f5;--soft:#f3f8ff}
.qb-card-meta{display:flex;align-items:center;justify-content:space-between;min-height:16px;font-size:clamp(10px,2.1cqw,13px);font-weight:800;color:var(--muted)}
.qb-card-meta [data-qb-live-card-brand]{min-width:1px}
.qb-card-artifact h1{margin:0;font-size:clamp(17px,5.1cqw,30px);line-height:1.06;font-weight:950;letter-spacing:0}
.qb-card-artifact p{margin:0;color:var(--muted);font-size:clamp(10px,2.5cqw,15px);font-weight:650;line-height:1.28}
.qb-card-core{min-height:0;display:grid;gap:clamp(5px,1.4cqw,9px);align-content:stretch}
.qb-hero-split{min-height:0;display:grid;grid-template-columns:minmax(70px,.72fr) 1fr;gap:10px;align-items:center}
.qb-signal-mark{display:grid;place-items:center;min-height:64px;border-radius:8px;background:linear-gradient(135deg,var(--accent),#ffb45f);color:#fff;font-size:clamp(25px,7cqw,46px);line-height:1;font-weight:950}
.qb-hero-split strong{display:block;font-size:clamp(26px,7.4cqw,48px);line-height:1;font-weight:950;color:var(--accent)}
.qb-hero-split span{display:block;margin-top:5px;color:var(--muted);font-size:clamp(10px,2.3cqw,13px);font-weight:800}
.qb-tier-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}
.qb-tier-grid>div,.qb-mini-metric{min-width:0;border:1px solid var(--line);border-radius:7px;background:rgba(255,255,255,.72);padding:8px}
.qb-tier-grid span,.qb-mini-metric span{display:block;color:var(--muted);font-size:clamp(10px,2.1cqw,12px);font-weight:800}
.qb-tier-grid b,.qb-mini-metric b{display:block;margin-top:4px;font-size:clamp(17px,4.3cqw,25px);line-height:1;font-weight:950}
.qb-tier-grid i{display:block;margin-top:3px;color:var(--accent);font-size:clamp(10px,2.1cqw,12px);font-style:normal;font-weight:850}
.qb-ladder-card{min-height:0;display:grid;grid-template-rows:auto minmax(0,1fr);gap:clamp(7px,2cqw,11px);align-items:stretch}
.qb-ladder-thesis{min-width:0;display:grid;grid-template-columns:auto auto minmax(0,1fr);gap:clamp(6px,1.8cqw,10px);align-items:center;border:1px solid rgba(215,25,32,.22);border-radius:8px;background:linear-gradient(90deg,#fff7ef,#ffe6da);padding:clamp(6px,1.6cqw,10px)}
.qb-ladder-thesis small{min-width:0;border-radius:999px;background:var(--accent);color:white;padding:clamp(4px,1cqw,6px) clamp(7px,2cqw,12px);font-size:clamp(9px,2.2cqw,12px);font-weight:950;white-space:nowrap}
.qb-ladder-thesis b{font-size:clamp(22px,6.6cqw,38px);line-height:1;font-weight:950;color:var(--accent)}
.qb-ladder-thesis span{min-width:0;color:var(--muted);font-size:clamp(9px,2.1cqw,12px);font-weight:850;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.qb-ladder-track{min-height:0;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:clamp(5px,1.5cqw,8px);align-items:end;position:relative}
.qb-ladder-track:before{content:"";position:absolute;left:9%;right:9%;bottom:20%;height:46%;border-left:2px solid rgba(215,25,32,.15);border-top:2px solid rgba(215,25,32,.15);transform:skewX(-18deg);pointer-events:none}
.qb-ladder-step{position:relative;min-width:0;display:grid;align-content:end;border:1px solid var(--line);border-radius:8px;background:rgba(255,255,255,.84);padding:clamp(6px,1.7cqw,10px);box-shadow:0 8px 18px rgba(120,66,24,.08)}
.qb-ladder-step.is-first{height:62%}
.qb-ladder-step.is-second{height:80%}
.qb-ladder-step.is-third{height:100%}
.qb-ladder-step span{min-width:0;color:var(--muted);font-size:clamp(9px,2.05cqw,12px);font-weight:850;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.qb-ladder-step b{display:block;margin-top:5px;font-size:clamp(15px,4cqw,23px);line-height:1;font-weight:950;color:var(--ink)}
.qb-ladder-step i{display:block;margin-top:4px;color:var(--accent);font-size:clamp(9px,2cqw,12px);font-style:normal;font-weight:900}
.qb-event-card{min-height:0;display:grid;grid-template-columns:minmax(78px,.72fr) minmax(0,1.28fr);grid-template-rows:minmax(0,1fr) auto;gap:clamp(6px,1.7cqw,10px);align-items:stretch}
.qb-event-window{grid-row:1/3;min-width:0;display:grid;align-content:center;justify-items:center;text-align:center;border:1px solid rgba(215,25,32,.24);border-radius:8px;background:linear-gradient(180deg,#fff6ed,#ffe3d4);padding:clamp(7px,2cqw,12px)}
.qb-event-window span,.qb-event-window i{color:var(--muted);font-size:clamp(9px,2.1cqw,12px);font-style:normal;font-weight:850}
.qb-event-window b{font-size:clamp(28px,8.5cqw,52px);line-height:.98;font-weight:950;color:var(--accent)}
.qb-st-lanes{min-height:0;display:grid;gap:clamp(5px,1.5cqw,8px)}
.qb-st-lane{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:5px 8px;align-items:center;border-bottom:1px solid rgba(234,216,198,.82);padding-bottom:clamp(5px,1.3cqw,8px)}
.qb-st-lane span{min-width:0;color:var(--ink);font-size:clamp(10px,2.25cqw,13px);font-weight:900;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.qb-st-lane b{font-size:clamp(11px,2.7cqw,15px);font-weight:950;color:var(--accent);text-align:right}
.qb-st-lane i{grid-column:1/3;display:block;height:clamp(8px,2.1cqw,12px);border-radius:999px;background:#f1e5d8;overflow:hidden}
.qb-st-lane em{display:block;width:8%;height:100%;border-radius:999px;background:linear-gradient(90deg,var(--accent),#ff8c3a)}
.qb-st-lane.is-hot i{background:#f7d8d3}
.qb-event-chips{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:clamp(4px,1.3cqw,7px)}
.qb-event-chips div{min-width:0;border:1px solid var(--line);border-radius:8px;background:rgba(255,255,255,.78);padding:clamp(5px,1.5cqw,8px)}
.qb-event-chips span{display:block;color:var(--muted);font-size:clamp(8px,1.95cqw,11px);font-weight:850;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.qb-event-chips b{display:block;margin-top:4px;color:var(--ink);font-size:clamp(13px,3.4cqw,20px);line-height:1;font-weight:950}
.qb-risk-map{min-height:0;display:grid;grid-template-columns:minmax(0,.95fr) minmax(0,1.05fr);gap:clamp(7px,2cqw,12px);align-items:stretch}
.qb-risk-field{position:relative;min-width:0;min-height:0;display:grid;place-items:center;overflow:hidden;border:1px solid var(--line);border-radius:8px;background:linear-gradient(135deg,#fffaf3,#ffe7d0)}
.qb-risk-field>i{position:absolute;display:block;border:1px solid rgba(239,122,26,.24);border-radius:50%;aspect-ratio:1}
.qb-risk-field>i:nth-child(1){width:86%}
.qb-risk-field>i:nth-child(2){width:62%}
.qb-risk-field>i:nth-child(3){width:38%;background:rgba(255,255,255,.42)}
.qb-risk-field:before,.qb-risk-field:after{content:"";position:absolute;background:rgba(239,122,26,.16)}
.qb-risk-field:before{width:1px;height:84%}
.qb-risk-field:after{height:1px;width:84%}
.qb-risk-radius{position:relative;z-index:1;display:grid;justify-items:center;text-align:center}
.qb-risk-radius span{color:var(--muted);font-size:clamp(9px,2.1cqw,12px);font-weight:850}
.qb-risk-radius b{margin-top:4px;color:var(--accent);font-size:clamp(23px,7cqw,40px);line-height:1;font-weight:950}
.qb-risk-field small{position:absolute;left:8px;bottom:7px;color:var(--muted);font-size:clamp(8px,1.9cqw,11px);font-weight:850}
.qb-risk-summary{min-height:0;display:grid;gap:clamp(5px,1.5cqw,8px)}
.qb-risk-summary div{min-width:0;display:grid;align-content:center;border:1px solid var(--line);border-radius:8px;background:rgba(255,255,255,.78);padding:clamp(6px,1.7cqw,10px)}
.qb-risk-summary span{color:var(--muted);font-size:clamp(9px,2.05cqw,12px);font-weight:850;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.qb-risk-summary b{min-width:0;margin-top:4px;color:var(--ink);font-size:clamp(12px,3.15cqw,19px);line-height:1.05;font-weight:950;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.qb-risk-summary div:nth-child(2) b{color:var(--accent)}
.qb-card-bar-row{display:grid;grid-template-columns:76px 54px 1fr;gap:8px;align-items:center;padding:7px 0;border-bottom:1px solid rgba(234,216,198,.8)}
.qb-card-bar-row span{font-size:clamp(10px,2.25cqw,13px);font-weight:850;color:var(--ink)}
.qb-card-bar-row b{font-size:clamp(11px,2.4cqw,14px);font-weight:950;color:var(--accent);text-align:right}
.qb-card-bar-row i{display:block;height:10px;border-radius:999px;background:#f1e5d8;overflow:hidden}
.qb-card-bar-row em{display:block;height:100%;width:8%;border-radius:999px;background:var(--accent)}
.qb-card-tags{display:flex;gap:6px;align-items:end;flex-wrap:wrap}
.qb-card-tags span{border:1px solid var(--line);border-radius:999px;background:#fffaf2;padding:4px 8px;font-size:clamp(9px,2cqw,11px);font-weight:850}
.qb-spark{width:100%;height:72px;border:1px solid var(--line);border-radius:8px;background:rgba(255,255,255,.66);overflow:hidden}
.qb-spark path{fill:none;stroke:var(--accent);stroke-width:4;stroke-linecap:round;stroke-linejoin:round}
.qb-card-visual-stack{min-height:0;display:grid;grid-template-rows:minmax(46px,1fr) auto;gap:clamp(5px,1.5cqw,8px)}
.qb-multi-spark{height:clamp(50px,20cqw,100px);background:linear-gradient(180deg,rgba(255,255,255,.9),var(--soft))}
.qb-multi-spark path:nth-child(2){stroke:#25364f;opacity:.78}
.qb-multi-spark path:nth-child(3){stroke:#8b6f50;opacity:.68}
.qb-race-list{min-height:0;display:grid;gap:clamp(4px,1.5cqw,7px)}
.qb-race-list.compact{gap:clamp(4px,1.3cqw,6px)}
.qb-race-row{display:grid;grid-template-columns:minmax(62px,.9fr) minmax(46px,.48fr) 1.3fr;gap:clamp(5px,1.7cqw,8px);align-items:center;min-height:clamp(22px,6.5cqw,34px);border:1px solid var(--line);border-radius:7px;background:rgba(255,255,255,.74);padding:4px 7px}
.qb-race-row span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--muted);font-size:clamp(9px,2.35cqw,12px);font-weight:850}
.qb-race-row b{font-size:clamp(12px,3.55cqw,19px);font-weight:950;line-height:1;color:var(--ink);text-align:right}
.qb-race-row i{display:block;height:clamp(5px,1.8cqw,8px);border-radius:999px;background:#efe3d6;overflow:hidden}
.qb-race-row em{display:block;height:100%;width:10%;border-radius:999px;background:var(--accent)}
.qb-regime-meter,.qb-waterline{border:1px solid var(--line);border-radius:8px;background:rgba(255,255,255,.75);padding:8px 10px}
.qb-regime-meter>div{display:flex;align-items:center;justify-content:space-between;color:var(--muted);font-size:clamp(10px,2.2cqw,12px);font-weight:850}
.qb-regime-meter b,.qb-waterline b{font-size:clamp(16px,4.2cqw,24px);color:var(--accent)}
.qb-regime-meter i,.qb-waterline i{display:block;height:10px;border-radius:999px;background:#eee3d5;overflow:hidden;margin-top:6px}
.qb-regime-meter em,.qb-waterline em{display:block;height:100%;width:50%;border-radius:999px;background:linear-gradient(90deg,#6f8fb3,var(--accent))}
.qb-window-strip{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px}
.qb-window-strip>div{min-width:0;border:1px solid var(--line);border-radius:8px;background:rgba(255,255,255,.78);padding:8px}
.qb-window-strip span{display:block;color:var(--muted);font-size:clamp(9px,2.2cqw,11px);font-weight:850}
.qb-window-strip b{display:block;margin-top:5px;font-size:clamp(15px,4.2cqw,23px);line-height:1;font-weight:950;color:var(--ink)}
.qb-top-list{min-height:0;border:1px solid var(--line);border-radius:9px;background:rgba(255,255,255,.76);padding:9px;display:grid;gap:7px}
.qb-top-list>strong{font-size:clamp(11px,2.5cqw,14px);line-height:1.1}
.qb-top-list-body{display:grid;gap:5px}
.qb-top-list-body>div{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;align-items:center;border-top:1px solid rgba(0,0,0,.06);padding-top:5px}
.qb-top-list-body span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--muted);font-size:clamp(10px,2.3cqw,12px);font-weight:820}
.qb-top-list-body b{font-size:clamp(12px,3.1cqw,16px);font-weight:950;color:var(--accent)}
.qb-card-dashboard,.qb-alert-board,.qb-basis-board,.qb-limit-structure,.qb-valuation-waterline{min-height:0;display:grid;gap:8px}
.qb-card-dashboard{grid-template-columns:.8fr 1.2fr;align-items:stretch}
.qb-score-orbit,.qb-alert-score,.qb-basis-main{display:grid;place-items:center;text-align:center;border:1px solid var(--line);border-radius:12px;background:radial-gradient(circle at 50% 40%,rgba(255,255,255,.98),var(--soft));padding:10px}
.qb-score-orbit b,.qb-alert-score b,.qb-basis-main b{font-size:clamp(28px,8cqw,46px);line-height:1;font-weight:950;color:var(--accent)}
.qb-score-orbit span,.qb-alert-score span,.qb-basis-main span{color:var(--muted);font-size:clamp(10px,2.3cqw,12px);font-weight:850}
.qb-alert-board,.qb-basis-board{grid-template-columns:.9fr 1.2fr;align-items:stretch}
.qb-limit-structure{grid-template-columns:.7fr 1.3fr;align-items:stretch}
"""


RUNTIME = r"""<script id="qb-card-runtime-v1" data-qb-card-runtime>
(function(){
  var INDUSTRY_NAMES = {
    sw_agri:"农林牧渔",sw_chem:"基础化工",sw_steel:"钢铁",sw_nonferrous:"有色金属",sw_electronics:"电子",sw_homeapp:"家用电器",sw_food:"食品饮料",sw_textile:"纺织服饰",sw_light:"轻工制造",sw_pharma:"医药生物",sw_utility:"公用事业",sw_transport:"交通运输",sw_realestate:"房地产",sw_retail:"商贸零售",sw_service:"社会服务",sw_conglomerate:"综合",
    sw_buildmat:"建筑材料",sw_build:"建筑装饰",sw_power:"电力设备",sw_defense:"国防军工",sw_computer:"计算机",sw_media:"传媒",sw_telecom:"通信",sw_bank:"银行",sw_broker:"非银金融",sw_auto:"汽车",sw_machine:"机械设备",sw_coal:"煤炭",sw_oil:"石油石化",sw_env:"环保",sw_beauty:"美容护理"
  };
  function isObj(v){ return v && typeof v === "object" && !Array.isArray(v); }
  function unwrap(v){
    if (v && v.data != null && (v.read_mode || v.data_id || v.error == null)) v = v.data;
    if (isObj(v)) {
      var keys = ["last_value", "last_day_stats", "last_valid_per_asset"];
      for (var i=0;i<keys.length;i++) if (v[keys[i]] != null) return unwrap(v[keys[i]]);
    }
    return v;
  }
  function range(output){
    var data = unwrap(output);
    if (isObj(data) && data.range_data) data = data.range_data;
    if (isObj(data) && Array.isArray(data.values)) return { values:data.values, dates:data.dates || [] };
    if (Array.isArray(data)) return { values:data, dates:[] };
    return { values:[], dates:[] };
  }
  function topValues(output){
    var data = unwrap(output);
    if (isObj(data) && data.top_values) data = data.top_values;
    if (isObj(data) && data.last_valid_per_asset) data = data.last_valid_per_asset;
    if (isObj(data) && Array.isArray(data.values)) data = data.values;
    var rows = [];
    if (Array.isArray(data)) {
      data.forEach(function(item, idx){
        if (isObj(item)) {
          var asset = item.asset || item.asset_code || item.symbol || item.code || "";
          var name = item.asset_name || item.name || item.asset || item.symbol || item.code || item.industry || item.label || ("#" + (idx + 1));
          var value = item.value != null ? item.value : numericFromObject(item);
          if (value != null && isFinite(Number(value))) rows.push({ asset:String(asset), name:String(name), value:Number(value) });
        } else if (item != null && isFinite(Number(item))) {
          rows.push({ name:"#" + (idx + 1), value:Number(item) });
        }
      });
    } else if (isObj(data)) {
      Object.keys(data).forEach(function(key){
        if (/date|range|total|valid|returned|asset|coverage|nan|shape|signature|id/i.test(key)) return;
        var item = data[key], value = isObj(item) ? numericFromObject(item) : item;
        if (value != null && isFinite(Number(value))) rows.push({ name:String(key), value:Number(value) });
      });
    }
    rows.sort(function(a,b){ return b.value - a.value; });
    return rows;
  }
  function assetRows(output){
    var data = output && output.data != null ? output.data : output;
    if (isObj(data) && data.last_valid_per_asset) data = data.last_valid_per_asset;
    if (isObj(data) && Array.isArray(data.values)) data = data.values;
    if (!Array.isArray(data)) {
      data = unwrap(output);
      if (isObj(data) && Array.isArray(data.values)) data = data.values;
    }
    var rows = [];
    if (!Array.isArray(data)) return rows;
    data.forEach(function(item, idx){
      if (!isObj(item)) return;
      var asset = item.asset || item.asset_code || item.symbol || item.code;
      var value = item.value != null ? item.value : numericFromObject(item);
      if (!asset || value == null || !isFinite(Number(value))) return;
      rows.push({
        asset:String(asset),
        name:String(item.asset_name || item.name || asset || ("#" + (idx + 1))),
        value:Number(value)
      });
    });
    return rows;
  }
  function avg(vals){
    vals = vals.filter(function(v){ return v != null && isFinite(Number(v)); }).map(Number);
    if (!vals.length) return null;
    return vals.reduce(function(a,b){ return a + b; }, 0) / vals.length;
  }
  function industryTopValues(outputs, metricKey, maskKeys){
    var metricByAsset = {};
    assetRows(outputs[metricKey]).forEach(function(row){ metricByAsset[row.asset] = row; });
    var rows = [];
    maskKeys.forEach(function(maskKey){
      var vals = [];
      assetRows(outputs[maskKey]).forEach(function(maskRow){
        if (!(Number(maskRow.value) > 0)) return;
        var metric = metricByAsset[maskRow.asset];
        if (metric && metric.value != null && isFinite(Number(metric.value))) vals.push(Number(metric.value));
      });
      var value = avg(vals);
      if (value != null) rows.push({ key:maskKey, name:INDUSTRY_NAMES[maskKey] || maskKey, value:value, count:vals.length });
    });
    rows.sort(function(a,b){ return b.value - a.value; });
    return rows;
  }
  function numericFromObject(obj){
    if (!isObj(obj)) return null;
    var preferred = ["value","score","ret","return","pct","pe","pb","roe","amount","price","close"];
    for (var i=0;i<preferred.length;i++) {
      var key = preferred[i];
      if (obj[key] != null && obj[key] !== "" && isFinite(Number(obj[key]))) return Number(obj[key]);
    }
    var vals = [];
    Object.keys(obj).forEach(function(key){
      if (/date|time|code|asset|symbol|name|industry/i.test(key)) return;
      var v = obj[key];
      if (v != null && v !== "" && isFinite(Number(v))) vals.push(Number(v));
    });
    if (!vals.length) return null;
    return vals.reduce(function(a,b){ return a + b; }, 0) / vals.length;
  }
  function lastValue(output){
    var data = unwrap(output);
    if (isObj(data) && data.value != null) return data.value;
    if (isObj(data) && Array.isArray(data.top_values)) {
      var topVals = data.top_values.map(function(item){ return item && item.value; }).filter(function(v){ return v != null && v !== "" && isFinite(Number(v)); }).map(Number);
      if (topVals.length) return topVals.reduce(function(a,b){ return a + b; }, 0) / topVals.length;
    }
    var ranged = range(output).values;
    for (var k=ranged.length-1;k>=0;k--) if (ranged[k] != null && ranged[k] !== "" && isFinite(Number(ranged[k]))) return Number(ranged[k]);
    if (Array.isArray(data)) {
      for (var j=data.length-1;j>=0;j--) {
        if (isObj(data[j])) {
          var objVal = numericFromObject(data[j]);
          if (objVal != null) return objVal;
        } else if (data[j] != null && data[j] !== "" && isFinite(Number(data[j]))) {
          return Number(data[j]);
        }
      }
    }
    if (isObj(data)) {
      var direct = numericFromObject(data);
      if (direct != null) return direct;
      var children = [];
      Object.keys(data).forEach(function(key){ if (isObj(data[key]) || Array.isArray(data[key])) children.push(lastValue({ data:data[key] })); });
      children = children.filter(function(v){ return v != null && isFinite(Number(v)); }).map(Number);
      if (children.length) return children.reduce(function(a,b){ return a + b; }, 0) / children.length;
    }
    if (data != null && data !== "" && isFinite(Number(data))) return Number(data);
    return null;
  }
  function firstValue(output){
    var r = range(output).values;
    for (var i=0;i<r.length;i++) if (r[i] != null && r[i] !== "" && isFinite(Number(r[i]))) return Number(r[i]);
    return lastValue(output);
  }
  function outputDate(output){
    var data = output && output.data != null ? output.data : output;
    if (isObj(data) && data.last_value && data.last_value.date) return data.last_value.date;
    var r = range(output);
    for (var i=r.dates.length-1;i>=0;i--) if (r.values[i] != null && r.dates[i]) return r.dates[i];
    return "";
  }
  function dateDigits(date){
    var digits = String(date || "").replace(/\D/g, "");
    return digits.length >= 8 ? digits.slice(0, 8) : "";
  }
  function formatDate(date){
    var digits = dateDigits(date);
    return digits ? digits.slice(0,4) + "-" + digits.slice(4,6) + "-" + digits.slice(6,8) : "";
  }
  function cardDate(outputs){
    var keys = Object.keys(outputs || {});
    var best = "";
    var bestNum = -1;
    for (var i=0;i<keys.length;i++) {
      var d = outputDate(outputs[keys[i]]);
      var digits = dateDigits(d);
      var n = digits ? Number(digits) : -1;
      if (n > bestNum) {
        bestNum = n;
        best = digits;
      }
    }
    return formatDate(best);
  }
  function ret(outputs, key){
    var out = outputs && outputs[key];
    var a = firstValue(out), b = lastValue(out);
    if (a == null || b == null || !isFinite(a) || !isFinite(b) || a === 0) return null;
    return (b / a - 1) * 100;
  }
  function pctSmart(v){
    if (v == null || !isFinite(Number(v))) return null;
    v = Number(v);
    return Math.abs(v) <= 1 ? v * 100 : v;
  }
  function fmt(v, format){
    if (v == null || v === "" || !isFinite(Number(v))) return "0";
    v = Number(v);
    if (format === "int") return String(Math.round(v));
    if (format === "pct") return (v * 100).toFixed(1) + "%";
    if (format === "pct-smart") return pctSmart(v).toFixed(1) + "%";
    if (format === "signed-pct") return (v >= 0 ? "+" : "") + pctSmart(v).toFixed(1) + "%";
    if (format === "return") return (v >= 0 ? "+" : "") + v.toFixed(1) + "%";
    if (format === "regime") return v >= 0.5 ? "进攻" : "防守";
    if (format === "number1") return v.toFixed(1);
    return Math.abs(v) >= 100 ? v.toFixed(0) : Math.abs(v) >= 10 ? v.toFixed(1) : v.toFixed(2);
  }
  function groupReturn(outputs, list){
    var vals = list.map(function(k){ return ret(outputs, k); }).filter(function(v){ return v != null && isFinite(v); });
    if (!vals.length) return null;
    return vals.reduce(function(a,b){ return a+b; }, 0) / vals.length;
  }
  function dispersion(outputs, list){
    var vals = list.map(function(k){ return ret(outputs, k); }).filter(function(v){ return v != null && isFinite(v); });
    if (!vals.length) return null;
    var avg = vals.reduce(function(a,b){ return a+b; }, 0) / vals.length;
    var variance = vals.reduce(function(a,b){ return a + Math.pow(b - avg, 2); }, 0) / vals.length;
    return Math.sqrt(variance);
  }
  function setBar(el, value){
    var width = Math.max(6, Math.min(100, Math.abs(value == null ? 0 : Number(value)) * 4));
    el.style.width = width.toFixed(0) + "%";
  }
  function percentForBar(value, format){
    if (value == null || !isFinite(Number(value))) return 0;
    if (format === "pct") return Number(value) * 100;
    if (format === "pct-smart" || format === "signed-pct") return pctSmart(value);
    return Number(value);
  }
  function setMeter(el, value, format){
    var width = Math.max(0, Math.min(100, percentForBar(value, format)));
    el.style.width = width.toFixed(0) + "%";
  }
  function drawSpark(el, outputs){
    var r = range(outputs[el.getAttribute("data-output")]);
    var vals = r.values.filter(function(v){ return v != null && isFinite(Number(v)); }).map(Number);
    if (vals.length < 2) return;
    vals = vals.slice(Math.max(0, vals.length - 80));
    var min = Math.min.apply(null, vals), max = Math.max.apply(null, vals);
    var span = max - min || 1;
    var points = vals.map(function(v, i){
      var x = 10 + i * (280 / Math.max(1, vals.length - 1));
      var y = 70 - ((v - min) / span) * 58;
      return [x.toFixed(1), y.toFixed(1)];
    });
    el.innerHTML = '<path d="M' + points.map(function(p){ return p[0] + ' ' + p[1]; }).join(' L') + '"/>';
  }
  function drawMultiSpark(el, outputs){
    var list = (el.getAttribute("data-outputs") || "").split(/\s+/).filter(Boolean);
    var series = list.map(function(key){
      var vals = range(outputs[key]).values.filter(function(v){ return v != null && isFinite(Number(v)); }).map(Number);
      if (vals.length < 2) return null;
      vals = vals.slice(Math.max(0, vals.length - 80));
      var first = vals[0] || 1;
      return vals.map(function(v){ return first ? (v / first - 1) * 100 : v; });
    }).filter(Boolean);
    if (!series.length) return;
    var all = [];
    series.forEach(function(vals){ all = all.concat(vals); });
    var min = Math.min.apply(null, all), max = Math.max.apply(null, all), span = max - min || 1;
    el.innerHTML = series.map(function(vals){
      var points = vals.map(function(v, i){
        var x = 10 + i * (280 / Math.max(1, vals.length - 1));
        var y = 82 - ((v - min) / span) * 68;
        return [x.toFixed(1), y.toFixed(1)];
      });
      return '<path d="M' + points.map(function(p){ return p[0] + ' ' + p[1]; }).join(' L') + '"/>';
    }).join("");
  }
  function spread(outputs, a, b){
    var av = lastValue(outputs[a]), bv = lastValue(outputs[b]);
    if (av == null || bv == null || !isFinite(Number(av)) || !isFinite(Number(bv))) return null;
    return Number(av) - Number(bv);
  }
  function relativeReturn(outputs, key, base){
    var value = ret(outputs, key);
    if (!base) return value;
    var baseValue = ret(outputs, base);
    if (value == null || baseValue == null) return value;
    return value - baseValue;
  }
  function renderTopList(el, outputs){
    var key = el.getAttribute("data-output");
    var format = el.getAttribute("data-format") || "";
    var limit = Math.max(1, Math.min(6, Number(el.getAttribute("data-limit") || 4)));
    var rows = topValues(outputs[key]).slice(0, limit);
    var body = el.querySelector(".qb-top-list-body");
    if (!body || !rows.length) return;
    body.innerHTML = rows.map(function(row){
      return "<div><span>" + String(row.name).replace(/[<>&]/g, "") + "</span><b>" + fmt(row.value, format) + "</b></div>";
    }).join("");
  }
  function renderTopValue(el, outputs){
    var key = el.getAttribute("data-output");
    var format = el.getAttribute("data-format") || "";
    var rows = topValues(outputs[key]);
    if (!rows.length) return;
    el.textContent = fmt(rows[0].value, format);
  }
  function renderIndustryTopList(el, outputs){
    var key = el.getAttribute("data-output");
    var masks = (el.getAttribute("data-masks") || "").split(/\s+/).filter(Boolean);
    var format = el.getAttribute("data-format") || "";
    var limit = Math.max(1, Math.min(6, Number(el.getAttribute("data-limit") || 4)));
    var rows = industryTopValues(outputs, key, masks).slice(0, limit);
    var body = el.querySelector(".qb-top-list-body");
    if (!body || !rows.length) return;
    body.innerHTML = rows.map(function(row){
      return "<div><span>" + String(row.name).replace(/[<>&]/g, "") + "</span><b>" + fmt(row.value, format) + "</b></div>";
    }).join("");
  }
  function renderIndustryTopValue(el, outputs){
    var key = el.getAttribute("data-output");
    var masks = (el.getAttribute("data-masks") || "").split(/\s+/).filter(Boolean);
    var format = el.getAttribute("data-format") || "";
    var rows = industryTopValues(outputs, key, masks);
    if (!rows.length) return;
    el.textContent = fmt(rows[0].value, format);
  }
  function hydrate(root, outputs){
    if (!root) return;
    outputs = outputs || {};
    var d = cardDate(outputs);
    if (d) Array.prototype.forEach.call(root.querySelectorAll('[data-qb-bind="date"]'), function(el){ el.textContent = d; el.setAttribute("datetime", d); });
    Array.prototype.forEach.call(root.querySelectorAll("[data-qb-value]"), function(el){
      var key = el.getAttribute("data-output");
      var format = el.getAttribute("data-format") || "";
      var value = format === "return" ? ret(outputs, key) : lastValue(outputs[key]);
      el.textContent = fmt(value, format);
    });
    Array.prototype.forEach.call(root.querySelectorAll("[data-qb-bar]"), function(el){
      var key = el.getAttribute("data-output");
      var format = el.getAttribute("data-format") || "";
      var value = percentForBar(lastValue(outputs[key]), format);
      setBar(el, value);
    });
    Array.prototype.forEach.call(root.querySelectorAll("[data-qb-group]"), function(row){
      var list = (row.getAttribute("data-qb-group") || "").split(/\s+/).filter(Boolean);
      var value = groupReturn(outputs, list);
      var score = row.querySelector("[data-qb-group-score]");
      var bar = row.querySelector("[data-qb-group-bar]");
      if (score) score.textContent = fmt(value, "return");
      if (bar) setBar(bar, value);
    });
    Array.prototype.forEach.call(root.querySelectorAll("[data-qb-sparkline]"), function(el){ drawSpark(el, outputs); });
    Array.prototype.forEach.call(root.querySelectorAll("[data-qb-multi-spark]"), function(el){ drawMultiSpark(el, outputs); });
    Array.prototype.forEach.call(root.querySelectorAll("[data-qb-top-list]"), function(el){ renderTopList(el, outputs); });
    Array.prototype.forEach.call(root.querySelectorAll("[data-qb-top-value]"), function(el){ renderTopValue(el, outputs); });
    Array.prototype.forEach.call(root.querySelectorAll("[data-qb-industry-top-list]"), function(el){ renderIndustryTopList(el, outputs); });
    Array.prototype.forEach.call(root.querySelectorAll("[data-qb-industry-top-value]"), function(el){ renderIndustryTopValue(el, outputs); });
    Array.prototype.forEach.call(root.querySelectorAll("[data-qb-meter-bar]"), function(el){
      var key = el.getAttribute("data-output");
      var format = el.getAttribute("data-format") || "";
      setMeter(el, lastValue(outputs[key]), format);
    });
    Array.prototype.forEach.call(root.querySelectorAll("[data-qb-spread]"), function(el){
      el.textContent = fmt(spread(outputs, el.getAttribute("data-a"), el.getAttribute("data-b")), "number1");
    });
    Array.prototype.forEach.call(root.querySelectorAll("[data-qb-spread-bar]"), function(el){
      setBar(el, spread(outputs, el.getAttribute("data-a"), el.getAttribute("data-b")));
    });
    Array.prototype.forEach.call(root.querySelectorAll("[data-qb-relative-return]"), function(el){
      el.textContent = fmt(relativeReturn(outputs, el.getAttribute("data-output"), el.getAttribute("data-base")), "return");
    });
    Array.prototype.forEach.call(root.querySelectorAll("[data-qb-relative-return-bar]"), function(el){
      setBar(el, relativeReturn(outputs, el.getAttribute("data-output"), el.getAttribute("data-base")));
    });
    Array.prototype.forEach.call(root.querySelectorAll("[data-qb-dispersion]"), function(el){
      var list = (el.getAttribute("data-outputs") || "").split(/\s+/).filter(Boolean);
      el.textContent = fmt(dispersion(outputs, list), "return");
    });
    Array.prototype.forEach.call(root.querySelectorAll("[data-qb-dispersion-bar]"), function(el){
      var list = (el.getAttribute("data-outputs") || "").split(/\s+/).filter(Boolean);
      setBar(el, dispersion(outputs, list));
    });
    Array.prototype.forEach.call(root.querySelectorAll("[data-qb-return]"), function(el){
      el.textContent = fmt(ret(outputs, el.getAttribute("data-output")), "return");
    });
    Array.prototype.forEach.call(root.querySelectorAll("[data-qb-return-bar]"), function(el){
      setBar(el, ret(outputs, el.getAttribute("data-output")));
    });
    Array.prototype.forEach.call(root.querySelectorAll("[data-qb-best]"), function(el){
      var list = (el.getAttribute("data-outputs") || "").split(/\s+/).filter(Boolean);
      var best = list.map(function(k){ return { k:k, v:ret(outputs,k) }; }).filter(function(x){ return x.v != null; }).sort(function(a,b){ return b.v-a.v; })[0];
      el.textContent = best ? best.k.replace(/_px$/,"") + " " + fmt(best.v, "return") : "0%";
    });
  }
  window.QBCardRuntimeV1 = {
    hydrate: function(root, outputs){ hydrate(root, outputs); },
    mount: function(root, options){
      var template = document.querySelector("template[data-qb-card-template]");
      if (!root || !template) return null;
      root.replaceChildren(template.content.cloneNode(true));
      hydrate(root, options && options.outputs || {});
      return { hydrate:function(outputs){ hydrate(root, outputs); }, dispose:function(){ root.replaceChildren(); } };
    },
    dispose: function(root){ if (root) root.replaceChildren(); }
  };
})();
</script>"""


def build_artifacts(page_id, title, manifest, output_keys):
    required, card = _build_page_card(page_id, title, _sort_keys(output_keys))
    missing = [k for k in required if k not in output_keys]
    if missing:
        raise ValueError("生成器引用了不存在的 outputs: %s" % ", ".join(missing))
    packages = manifest.get("_packages_resolved") or _manifest_packages(manifest)
    if not packages:
        raise ValueError("card manifest 缺少可用公式包")
    first = packages[0]
    package_blocks = []
    required_set = set(required)
    for pkg in packages:
        outputs = [key for key in (pkg.get("outputs") or []) if key in required_set]
        if not outputs:
            continue
        package_blocks.append({
            "role": pkg.get("role") or "package_%d" % (len(package_blocks) + 1),
            "endpoint": pkg["endpoint"],
            "package_id": pkg["package_id"],
            "signature": pkg["signature"],
            "outputs": outputs,
        })
    if not package_blocks:
        raise ValueError("required_outputs 未匹配到任何公式包")
    manifest2 = {
        "version": CARD_RUNTIME_VERSION,
        "kind": CARD_RUNTIME_KIND,
        "package_id": first["package_id"],
        "signature": first["signature"],
        "endpoint": first["endpoint"],
        "packages": package_blocks,
        "required_outputs": required,
        "aspect_ratio": "4/3",
    }
    manifest_text = json.dumps(manifest2, ensure_ascii=False, indent=2).replace("</", "<\\/")
    template = "<template data-qb-card-template>\n%s\n</template>" % card
    style = "<style data-qb-card-style>\n%s\n</style>" % STYLE.strip()
    manifest_block = "<script type=\"application/json\" data-qb-card-manifest>\n%s\n</script>" % manifest_text
    block = "\n".join([START, template, style, manifest_block, RUNTIME, END])
    digest = hashlib.sha256((template + style + manifest_block + RUNTIME).encode("utf-8")).hexdigest()
    return block, {
        "card_runtime_supported": True,
        "card_runtime_version": CARD_RUNTIME_VERSION,
        "card_runtime_kind": CARD_RUNTIME_KIND,
        "card_required_outputs": required,
        "card_artifact_hash": digest,
    }


def replace_artifact_block(html, block):
    pattern = re.compile(re.escape(START) + r"[\s\S]*?" + re.escape(END), re.I)
    if pattern.search(html or ""):
        return pattern.sub(lambda _m: block, html, count=1), "replace"
    if "</body>" in html.lower():
        return re.sub(r"</body\s*>", lambda _m: block + "\n</body>", html, count=1, flags=re.I), "append"
    return html + "\n" + block, "append"


def retrofit_html(html, *, page_id="", title=""):
    manifest = parse_manifest(html)
    outputs = query_all_outputs(manifest)
    output_keys = _sort_keys(outputs.keys())
    block, meta = build_artifacts(page_id, title or _title_from_html(html), manifest, output_keys)
    next_html, mode = replace_artifact_block(html, block)
    return next_html, {
        "mode": mode,
        "output_count": len(output_keys),
        "output_keys": output_keys,
        **meta,
    }
