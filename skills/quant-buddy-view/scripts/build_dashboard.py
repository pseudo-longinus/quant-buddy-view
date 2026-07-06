#!/usr/bin/env python3
r"""
看板生成器 —— 把「公式任务包 + 看板 spec」编译成一份自包含 HTML，可直接上传托管。

工具说明文档：tools/build_dashboard.md

输入一个 spec（描述标题 + 若干面板，每个面板把某个公式包产出渲染成 折线/柱/表格/数值），
输出一份 live 实时取数 HTML（样式内联，图表库引公网 CDN ECharts）。

  实时取数：HTML 内嵌 package_id + signature，打开时即时调用 queryFormulaPackage
            拉取最新数据并渲染，底层数据更新即自动重算，页面打开就是最新。
            构建期会先取一次数做质量体检（数据健康 + 单标的文案一致性），但不内联进 HTML，
            页面仍走浏览器实时取数。spec 不需要写 mode 字段。
  前提：① queryFormulaPackage 端点须对页面域名放开 CORS（当前 https 端点已满足）；
        ② signature 会随页面公开（公式包 query 本就以 signature 作能力令牌、设计上允许嵌入页面）。

参数（优先级：BD_PARAMS 环境变量 > @file > 命令行 JSON > stdin）：
    {
      "title":      "看板标题（必填，用于 <title> 与页头）",
      "subtitle":   "可选副标题",
      "description": "可选页面说明（≤1000 字，仅用于 static_page 列表/详情展示；显式传才透传给 upload/update，不传则不动）",
      "package_id": "公式包 id（缺省从最近一次本地凭证推断）",
      "signature":  "必需（缺省从本地凭证补全），写入页面供实时取数",
      "panels": [
        {
          "title":  "面板标题",
          "output": "对应公式包 reads 的产出名（= query 返回 outputs 的 key）",
          "type":   "line | bar | table | number | text | raw（默认 table）",
          "x":      "line/bar 横轴字段名（数据为对象数组时）",
          "y":      ["line/bar 纵轴字段名，可多条"],
          "value_field": "number 取值字段（缺省取首个数值）",
          "unit":   "number 单位（可选）",
          "description": "面板说明（可选）",
          "span":   "full | wide | auto（可选，默认按类型决定）",
          "text":   "text 面板正文（可选）"
        }
      ],
      "out_file":   "可选，输出 HTML 路径（默认 output/pages/<slug>.html）",
      "upload":     "可选 true，则生成后顺带调用 static_page 上传，返回公开 url",
      "update_page_id": "可选 page_xxx，则替换该已发布页面的内容（URL/page_id 不变），优先于新上传",
      "thumbnail_file": "可选，现成 PNG/JPG 缩略图；HTML 上传/更新成功后自动设封面",
      "thumbnail":  "可选 true 或对象；自动生成 1200x675 封面（默认全幅裸图，style=poster 可生成品牌海报；无浏览器则走纯 Python PNG 或 SVG 兜底，均不影响 HTML）",
      "brand":      "可选对象：name/cn_name/tagline/homepage/page_type/footer_note",
      "official_url": "可选，默认 https://www.quantbuddy.cn"
    }

用法示例：
    python scripts/build_dashboard.py @spec.json
    BD_PARAMS='{"title":"...","panels":[...],"upload":true}' python scripts/build_dashboard.py

输出：打印 {code, out_file, ...(upload 时含 url)}，并写一份到临时目录 bd_out.txt。
"""

import datetime
import hashlib
from html import escape as html_escape
import json
import math
import os
import pathlib
import re
import sys
import uuid
from urllib.parse import quote

import common as C
import formula_package as FP
import live_card as LC

PAGES_DIR = os.path.join(C.SKILL_ROOT, "output", "pages")
ASSETS_DIR = os.path.join(C.SKILL_ROOT, "assets")
SHARED_SHELL_DIR = os.path.join(C.SKILL_ROOT, "assets", "share-shell")

_ECHARTS_CDN = "https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"
_DEFAULT_OFFICIAL_URL = "https://www.quantbuddy.cn"
_DEFAULT_LOGO_PATH = os.path.join(ASSETS_DIR, "logo.svg")
_MAX_INLINE_LOGO_BYTES = 1_300_000


def _slug(title):
    s = re.sub(r"[^0-9A-Za-z一-鿿]+", "-", (title or "dashboard")).strip("-")
    return (s or "dashboard")[:40] + "-" + uuid.uuid4().hex[:8]


def _resolve_credential(params):
    """解析 package_id + signature：params 优先，其次本地凭证。返回 (pkg, sig, err)。"""
    pkg = params.get("package_id")
    sig = params.get("signature")
    if pkg and sig:
        return pkg, sig, None
    if pkg and not sig:
        cred = FP.load_credential(pkg)
        if cred:
            return pkg, cred.get("signature"), None
        return pkg, None, None  # signature 缺失，live 模式后续会报错
    # 未给 package_id：尝试取最近一次落盘的凭证
    cred_dir = os.path.join(C.SKILL_ROOT, "output", "formula_packages")
    if os.path.isdir(cred_dir):
        files = [os.path.join(cred_dir, f) for f in os.listdir(cred_dir) if f.endswith(".json")]
        if files:
            latest = max(files, key=os.path.getmtime)
            try:
                with open(latest, "r", encoding="utf-8") as f:
                    cred = json.load(f)
                return cred.get("package_id"), cred.get("signature"), None
            except Exception:
                pass
    return None, None, {"code": 1, "message": "未能确定 package_id：请在 spec 里指定，或先 register 落一份本地凭证"}


def _as_bool(value, default=True):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in ("0", "false", "no", "off", "否", "关闭")
    return bool(value)


def _share_config(spec):
    brand = spec.get("brand") if isinstance(spec.get("brand"), dict) else {}
    official_url = (
        spec.get("official_url")
        or brand.get("official_url")
        or brand.get("homepage")
        or _DEFAULT_OFFICIAL_URL
    )
    return {
        "brand_name": brand.get("name") or spec.get("brand_name") or "QuantBuddy",
        "brand_cn": brand.get("cn_name") or spec.get("brand_cn") or "观照量化",
        "tagline": brand.get("tagline") or spec.get("brand_tagline") or "Agent 调用 Skill 计算 · HTML 可调",
        "page_type": spec.get("page_type") or brand.get("page_type") or "量化看板",
        "official_url": official_url,
        "official_label": spec.get("official_label") or brand.get("official_label") or "开始使用",
        "show_qr": _as_bool(spec.get("show_qr", brand.get("show_qr")), True),
        "share_url": spec.get("share_url") or brand.get("share_url") or "",
        "share_title": spec.get("share_title") or brand.get("share_title") or "分享海报",
        "footer_note": spec.get("footer_note") or brand.get("footer_note") or "页面仅作市场观察与数据展示，不构成投资建议。",
    }


def _brand_logo_html():
    if not os.path.exists(_DEFAULT_LOGO_PATH):
        return "QB"
    try:
        if os.path.getsize(_DEFAULT_LOGO_PATH) > _MAX_INLINE_LOGO_BYTES:
            return "QB"
        with open(_DEFAULT_LOGO_PATH, "r", encoding="utf-8") as f:
            svg = f.read()
    except Exception:
        return "QB"

    if re.search(r"<\s*(script|foreignObject)\b|on\w+\s*=|(?:xlink:)?href\s*=|<\s*(image|use)\b", svg, re.I):
        return "QB"

    svg = re.sub(r"^\s*<\?xml[^>]*>\s*", "", svg, flags=re.I)
    svg = re.sub(r"<!doctype[^>]*>\s*", "", svg, flags=re.I)
    svg = re.sub(r"<!--.*?-->", "", svg, flags=re.S)
    svg = svg.strip()
    if not svg.lower().startswith("<svg"):
        return "QB"

    svg_open = re.search(r"<svg\b[^>]*>", svg, re.I)
    if svg_open and not re.search(r"\bviewBox\s*=", svg_open.group(0), re.I):
        width_match = re.search(r'\bwidth\s*=\s*["\']([0-9.]+)', svg_open.group(0), re.I)
        height_match = re.search(r'\bheight\s*=\s*["\']([0-9.]+)', svg_open.group(0), re.I)
        if width_match and height_match:
            view_box = f' viewBox="0 0 {width_match.group(1)} {height_match.group(1)}"'
            svg = svg[:svg_open.end() - 1] + view_box + svg[svg_open.end() - 1:]

    return re.sub(
        r"<svg\b",
        '<svg class="brand-logo-svg" aria-hidden="true" focusable="false"',
        svg,
        count=1,
        flags=re.I,
    )


def _read_text(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _logo_data_uri():
    if not os.path.exists(_DEFAULT_LOGO_PATH):
        return ""
    raw = _read_text(_DEFAULT_LOGO_PATH).strip()
    return "data:image/svg+xml;charset=utf-8," + quote(raw, safe="")


def _shared_shell_section(name):
    shell = _read_text(os.path.join(SHARED_SHELL_DIR, "shell.html"))
    m = re.search(
        rf"<!-- QB_SHELL_{name}_START -->(.*?)<!-- QB_SHELL_{name}_END -->",
        shell,
        flags=re.S,
    )
    if not m:
        raise ValueError(f"shell.html 缺少 {name} section")
    return m.group(1).strip().replace("__QB_LOGO_SRC__", _logo_data_uri())


def _shared_shell_css():
    return _read_text(os.path.join(SHARED_SHELL_DIR, "shell.css"))


def _shared_shell_js():
    return "\n".join([
        _read_text(os.path.join(ASSETS_DIR, "qr-mini.js")).strip(),
        _read_text(os.path.join(SHARED_SHELL_DIR, "poster.js")).strip(),
        _read_text(os.path.join(SHARED_SHELL_DIR, "shell.js")).strip(),
    ])


def _render_html(spec, *, title, subtitle, panels, endpoint, package_id, signature, generated_at):
    """组装 HTML。骨架自包含（样式/内核内联），数据走运行时实时取数：页面内联 endpoint+凭证 + 取数 JS。"""
    share = _share_config(spec)
    boot = {
        "mode": "live",
        "panels": panels,
        "generatedAt": generated_at,
        "share": {
            "enabled": share["show_qr"],
            "url": share["share_url"],
            "officialUrl": share["official_url"],
            "title": title or "看板",
            "subtitle": subtitle or "",
            "pageType": share["page_type"],
            "footerNote": share["footer_note"],
        },
        "endpoint": endpoint,
        "packageId": package_id,
        "signature": signature,
        # 构建时的 quant-buddy-view 版本/名，随实时取数上报给服务端 audit
        "skillVersion": C.SKILL_VERSION,
        "skillName": C.SKILL_NAME,
    }

    boot_json = json.dumps(boot, ensure_ascii=False)
    title_esc = html_escape(title or "看板")
    subtitle_esc = html_escape(subtitle or "")
    brand_name_esc = html_escape(share["brand_name"])
    brand_cn_esc = html_escape(share["brand_cn"])
    tagline_esc = html_escape(share["tagline"])
    page_type_esc = html_escape(share["page_type"])
    official_url_attr = html_escape(share["official_url"], quote=True)
    official_host_esc = html_escape(re.sub(r"^https?://", "", share["official_url"]).rstrip("/"))
    official_label_esc = html_escape(share["official_label"])
    share_title_esc = html_escape(share["share_title"])
    footer_note_esc = html_escape(share["footer_note"])
    brand_logo_html = _brand_logo_html()
    shared_header = _shared_shell_section("HEADER")
    shared_footer = _shared_shell_section("FOOTER")
    shared_modal = _shared_shell_section("MODAL")
    shared_css = _shared_shell_css()
    shared_runtime_js = _shared_shell_js()
    live_card_config = LC.dashboard_config(spec, panels)
    live_card_html = LC.card_html(live_card_config) if live_card_config else ""
    live_card_css = _read_text(os.path.join(ASSETS_DIR, "live-card.css")) if live_card_config else ""
    live_card_js = _read_text(os.path.join(ASSETS_DIR, "live-card.js")) if live_card_config else ""
    live_card_binding = LC.binding_script(live_card_config) if live_card_config else ""
    card_runtime_artifacts = LC.card_runtime_artifacts(
        live_card_config,
        endpoint=endpoint,
        package_id=package_id,
        signature=signature,
        style=live_card_css,
        fallback_title=title or "",
        fallback_description=subtitle or "",
    ) if live_card_config else ""
    card_runtime_js = LC.card_runtime_script() if live_card_config else ""

    # 渲染脚本：把任意 data 形态归一为 {columns, rows}，再按 panel.type 出图/表
    render_js = r"""
const BOOT = __BOOT__;
let LAST_OUTPUTS = {};

function apiUrl(endpoint, path) {
  endpoint = String(endpoint || '').replace(/\/+$/, '');
  path = '/' + String(path || '').replace(/^\/+/, '');
  if (endpoint.endsWith('/skill') && path.startsWith('/skill/')) {
    path = path.slice('/skill'.length);
  }
  return endpoint + path;
}

function fmtDate(v) {
  // 整数 / 8 位数字串 YYYYMMDD → YYYY-MM-DD；其它原样返回
  if (typeof v === 'number' && Number.isInteger(v) && v >= 10000101 && v <= 99991231) v = String(v);
  if (typeof v === 'string' && /^\d{8}$/.test(v)) return v.slice(0, 4) + '-' + v.slice(4, 6) + '-' + v.slice(6, 8);
  return v;
}

function normalize(data) {
  // 归一为 {columns:[...], rows:[[...]]}，兼容公式包各 read_mode 的 data 形态
  if (data == null) return {columns: [], rows: []};
  if (Array.isArray(data)) {
    if (data.length === 0) return {columns: [], rows: []};
    if (typeof data[0] === 'object' && data[0] !== null && !Array.isArray(data[0])) {
      const cols = []; data.forEach(o => Object.keys(o).forEach(k => { if (!cols.includes(k)) cols.push(k); }));
      return {columns: cols, rows: data.map(o => cols.map(c => o[c]))};
    }
    if (Array.isArray(data[0])) {
      const n = Math.max.apply(null, data.map(r => r.length));
      return {columns: Array.from({length: n}, (_, i) => 'c' + i), rows: data};
    }
    return {columns: ['value'], rows: data.map(v => [v])};
  }
  if (typeof data === 'object') {
    // 解包公式包按 read_mode 命名的外层 key：range_data / last_value / last_day_stats / last_valid_per_asset
    for (const wk of ['range_data', 'last_value', 'last_day_stats', 'last_valid_per_asset']) {
      if (data[wk] && typeof data[wk] === 'object') return normalize(data[wk]);
    }
    if (Array.isArray(data.columns) && Array.isArray(data.rows)) return {columns: data.columns, rows: data.rows};
    // 截面榜单：top_values / items / rows 是对象数组
    for (const ak of ['top_values', 'items', 'records']) {
      if (Array.isArray(data[ak])) return normalize(data[ak]);
    }
    // 序列：x 轴候选 + y 轴候选成对出现（range_data 的 dates/values 即走这里）
    const xk = ['dates', 'date', 'x', 'index', 'labels', 'categories'].find(k => Array.isArray(data[k]));
    const yk = ['values', 'y', 'series', 'data'].find(k => Array.isArray(data[k]));
    if (xk && yk) {
      const xs = data[xk], ys = data[yk];
      const yName = data.series_name || yk;
      // 裁掉尾部 null（range_data 最新若干日常未回填），整数日期归一为 YYYY-MM-DD
      const isNull = v => v == null || (typeof v === 'number' && !isFinite(v));
      let end = xs.length;
      while (end > 0 && isNull(ys[end - 1])) end--;
      const rows = [];
      for (let i = 0; i < end; i++) rows.push([fmtDate(xs[i]), ys[i]]);
      return {columns: [xk, yName], rows: rows};
    }
    if (Array.isArray(data.data)) return normalize(data.data);
    // 普通对象（如 last_value 的 {date,value}）→ key/value 两列
    const keys = Object.keys(data);
    return {columns: ['key', 'value'], rows: keys.map(k => [k, data[k]])};
  }
  return {columns: ['value'], rows: [[data]]};
}

function colIdx(tab, name) {
  const i = tab.columns.indexOf(name);
  return i >= 0 ? i : null;
}

function renderTable(el, tab, panel) {
  const cols = (panel.columns && panel.columns.length) ? panel.columns : tab.columns;
  const idx = cols.map(c => colIdx(tab, c));
  let h = '<table><thead><tr>' + cols.map(c => '<th>' + c + '</th>').join('') + '</tr></thead><tbody>';
  tab.rows.forEach(r => {
    h += '<tr>' + idx.map(i => '<td>' + fmt(i == null ? '' : r[i]) + '</td>').join('') + '</tr>';
  });
  h += '</tbody></table>';
  el.innerHTML = h;
}

function fmt(v) {
  if (v == null) return '';
  if (typeof v === 'number') return (Math.abs(v) >= 1e4 || (v % 1 !== 0)) ? v.toLocaleString(undefined, {maximumFractionDigits: 4}) : v;
  return String(v);
}

function esc(v) {
  return String(v == null ? '' : v)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function clsForNumber(v) {
  if (typeof v !== 'number' || !isFinite(v)) return '';
  if (v > 0) return ' up';
  if (v < 0) return ' down';
  return ' flat';
}

function lastRealNumber(tab, ci) {
  // 自底向上扫某列，返回末个有效数值（跳过 null/NaN/尾部空洞）
  if (ci == null) return null;
  for (let r = tab.rows.length - 1; r >= 0; r--) {
    const v = tab.rows[r][ci];
    if (typeof v === 'number' && isFinite(v)) return v;
  }
  return null;
}
function renderNumber(el, tab, panel) {
  let val = null;
  const f = panel.value_field;
  if (f && colIdx(tab, f) != null) {
    val = lastRealNumber(tab, colIdx(tab, f));
  } else {
    // 默认取「最后一个数值列」的末个有效值：对 range_data 的 [日期, 序列] 形态即取序列值，
    // 不再用 .find(第一个数字) 误命中日期列。末列若全空则向前回退到其它数值列。
    for (let c = tab.columns.length - 1; c >= 0; c--) {
      val = lastRealNumber(tab, c);
      if (val != null) break;
    }
  }
  const desc = panel.description ? '<div class="desc">' + esc(panel.description) + '</div>' : '';
  el.innerHTML = '<div class="big' + clsForNumber(val) + '">' + fmt(val) + (panel.unit ? '<span class="unit">' + esc(panel.unit) + '</span>' : '') + '</div>' + desc;
}

function renderText(el, panel) {
  const text = panel.text || panel.content || panel.description || '';
  el.innerHTML = '<div class="text-panel">' + esc(text).replace(/\n/g, '<br>') + '</div>';
}

function renderChart(el, tab, panel) {
  const chart = echarts.init(el);
  const xName = panel.x || tab.columns[0];
  const xi = colIdx(tab, xName);
  const xData = tab.rows.map(r => xi == null ? '' : r[xi]);
  let yCols = panel.y && panel.y.length ? panel.y : tab.columns.filter(c => c !== xName);
  // 只保留数值列
  yCols = yCols.filter(c => {
    const i = colIdx(tab, c);
    return i != null && tab.rows.some(r => typeof r[i] === 'number');
  });
  const series = yCols.map(c => {
    const i = colIdx(tab, c);
    return {name: c, type: panel.type === 'bar' ? 'bar' : 'line', smooth: panel.type !== 'bar',
            showSymbol: false, connectNulls: true, data: tab.rows.map(r => r[i])};
  });
  chart.setOption({
    tooltip: {trigger: 'axis'},
    legend: {data: yCols, top: 0, type: 'scroll'},
    color: ['#2454a6', '#7a8ca8', '#c03d3d', '#16845b', '#b2762d'],
    grid: {left: 56, right: 24, top: 34, bottom: 42},
    xAxis: {type: 'category', data: xData, boundaryGap: panel.type === 'bar',
            axisLine: {lineStyle: {color: '#bfccda'}}, axisTick: {show:false}, axisLabel: {color: '#697586'}},
    yAxis: {type: 'value', scale: true, axisLabel: {color: '#697586'}, splitLine: {lineStyle: {color: '#e8edf4'}}},
    series: series,
  });
  window.addEventListener('resize', () => chart.resize());
}

// 骨架先行：先把所有面板卡片铺出来，正文随产出到达再逐个填。
// PANEL_REG 存每个面板的 body/span/是否已填；OUTPUT_INDEX 把产出名映射到引用它的面板（一个产出可被多个面板复用）。
let PANEL_REG = [];
let OUTPUT_INDEX = {};

function createCard(panel) {
  const card = document.createElement('section');
  const type = panel.type || 'table';
  const defaultSpan = (type === 'line' || type === 'bar') ? 'full' : 'auto';
  const span = ['full', 'wide', 'auto'].includes(panel.span) ? panel.span : defaultSpan;
  card.className = 'card card-' + type + ' span-' + span;
  card.innerHTML = '<div class="card-head"><h3>' + esc(panel.title || panel.output || '') + '</h3>' +
    (panel.description && type !== 'number' && type !== 'text' ? '<p>' + esc(panel.description) + '</p>' : '') +
    '</div>';
  const body = document.createElement('div');
  body.className = 'body ' + type;
  card.appendChild(body);
  document.getElementById('grid').appendChild(card);
  return {body: body, span: span};
}

function renderPanelBody(body, panel, span, out) {
  const type = panel.type || 'table';
  if (!out) { body.innerHTML = '<p class="empty">无产出：' + (panel.output || '') + '</p>'; return; }
  if (out.error) { body.innerHTML = '<p class="empty err">取数失败：' + out.error + '</p>'; return; }
  const tab = normalize(out.data);
  try {
    if (type === 'raw') body.innerHTML = '<pre>' + JSON.stringify(out.data, null, 2) + '</pre>';
    else if (type === 'number') renderNumber(body, tab, panel);
    else if (type === 'table') renderTable(body, tab, panel);
    else { body.style.height = (panel.height || (span === 'full' ? 360 : 300)) + 'px'; renderChart(body, tab, panel); }
  } catch (e) {
    body.innerHTML = '<p class="empty">渲染失败: ' + e + '</p>';
  }
}

function buildSkeletons() {
  const grid = document.getElementById('grid');
  grid.innerHTML = '';
  PANEL_REG = [];
  OUTPUT_INDEX = {};
  BOOT.panels.forEach(panel => {
    const type = panel.type || 'table';
    const made = createCard(panel);
    const reg = {panel: panel, body: made.body, span: made.span, filled: false};
    PANEL_REG.push(reg);
    if (type === 'text') { renderText(made.body, panel); reg.filled = true; return; }
    made.body.innerHTML = '<p class="empty">加载中…</p>';
    const name = panel.output;
    if (name) (OUTPUT_INDEX[name] = OUTPUT_INDEX[name] || []).push(reg);
  });
}

// 某产出到达后，立刻渲染所有引用它的面板（先到先显）
function applyOutput(name, out) {
  (OUTPUT_INDEX[name] || []).forEach(reg => {
    renderPanelBody(reg.body, reg.panel, reg.span, out);
    reg.filled = true;
  });
}

function syncLiveCard(outputs) {
  try {
    const payload = outputs || LAST_OUTPUTS || {};
    window.dispatchEvent(new CustomEvent('qb:outputs', {detail: {outputs: payload}}));
    if (window.QBLiveCardHydrate) window.QBLiveCardHydrate(payload);
  } catch (e) {}
}

// 一次性渲染（封面模式 / 流式兜底）：先铺骨架，再把已知产出全部填上
function renderAll(outputs) {
  LAST_OUTPUTS = outputs || {};
  buildSkeletons();
  Object.keys(LAST_OUTPUTS).forEach(name => applyOutput(name, LAST_OUTPUTS[name]));
  syncLiveCard(LAST_OUTPUTS);
}

function parseSSEBlock(block) {
  // 解析单个 SSE 事件块（event/data 行）→ {output, out} 或 null（与服务端 query 的 result 事件对齐）
  let event = null;
  const dataLines = [];
  block.split('\n').forEach(line => {
    line = line.replace(/\r$/, '');
    if (line.startsWith(':')) return;
    if (line.startsWith('event:')) event = line.slice(6).trim();
    else if (line.startsWith('data:')) dataLines.push(line.slice(5).replace(/^ /, ''));
  });
  if (event !== 'result' || !dataLines.length) return null;
  try {
    const p = JSON.parse(dataLines.join('\n'));
    return {output: p.output, out: {read_mode: p.read_mode, data_id: p.data_id, data: p.data, error: p.error}};
  } catch (e) { return null; }
}

function parseSSE(text) {
  // 整段 SSE 文本 → outputs（流式兜底 / 封面模式用）。事件以空行分隔，先归一 CRLF 再按 \n\n 切块。
  const outputs = {};
  text.replace(/\r\n/g, '\n').split('\n\n').forEach(block => {
    const r = parseSSEBlock(block);
    if (r) outputs[r.output] = r.out;
  });
  return outputs;
}

async function fetchLive() {
  const setMsg = m => { document.getElementById('grid').innerHTML = '<p class="empty">' + m + '</p>'; };
  buildSkeletons();          // 先把面板骨架铺出来，产出到一个就渲染一个
  LAST_OUTPUTS = {};
  let resp;
  try {
    resp = await fetch(apiUrl(BOOT.endpoint, '/skill/queryFormulaPackage'), {
      method: 'POST',
      headers: Object.assign(
        {'Content-Type': 'application/json', 'Accept': 'text/event-stream'},
        BOOT.skillVersion ? {'x-skill-version': BOOT.skillVersion, 'x-skill-name': BOOT.skillName || 'quant-buddy-view'} : {}
      ),
      body: JSON.stringify({package_id: BOOT.packageId, signature: BOOT.signature}),
    });
  } catch (e) {
    setMsg('取数失败（可能是跨域/网络）：' + e);
    return;
  }
  if (!resp.ok) { setMsg('取数失败：HTTP ' + resp.status); return; }

  // 老环境不支持可读流：回退到一次性取整段再渲染
  if (!resp.body || typeof resp.body.getReader !== 'function') {
    const text = await resp.text();
    renderAll(parseSSE(text));
    return LAST_OUTPUTS;
  }

  const reader = resp.body.getReader();
  const dec = new TextDecoder();
  let buf = '';
  const handle = block => {
    const r = parseSSEBlock(block);
    if (!r) return;
    LAST_OUTPUTS[r.output] = r.out;
    applyOutput(r.output, r.out);   // 边收边渲染：先到先显
    syncLiveCard(LAST_OUTPUTS);
  };
  try {
    for (;;) {
      const {value, done} = await reader.read();
      if (done) break;
      // 删掉所有 \r，使 \n\n 切块对 LF / CRLF 两种分隔都成立
      buf += dec.decode(value, {stream: true}).replace(/\r/g, '');
      const blocks = buf.split('\n\n');
      buf = blocks.pop();           // 末段可能是半条事件，留到下个 chunk 续上
      blocks.forEach(handle);
    }
    if (buf.trim()) handle(buf);     // 收尾残留块
  } catch (e) {
    // 流中途断开：已渲染的保留，未到的面板维持「加载中」
  }
  // 收尾：始终没等到产出的非 text 面板，标注无产出
  PANEL_REG.forEach(reg => {
    if (!reg.filled && (reg.panel.type || 'table') !== 'text') {
      reg.body.innerHTML = '<p class="empty">无产出：' + (reg.panel.output || '') + '</p>';
    }
  });
  return LAST_OUTPUTS;
}

function panelDisplayValue(panel) {
  const out = LAST_OUTPUTS[panel.output];
  if (!out || out.error) return '—';
  const tab = normalize(out.data);
  if (!tab.rows.length) return '—';
  let value = null;
  if (panel.value_field && colIdx(tab, panel.value_field) != null) {
    value = lastRealNumber(tab, colIdx(tab, panel.value_field));
  } else {
    for (let c = tab.columns.length - 1; c >= 0; c--) {
      value = lastRealNumber(tab, c);
      if (value != null) break;
    }
  }
  return value == null ? '—' : fmt(value) + (panel.unit ? ' ' + panel.unit : '');
}

function panelListItems(panel) {
  const out = LAST_OUTPUTS[panel.output];
  if (!out || out.error) return [];
  const tab = normalize(out.data);
  if (!tab.rows.length) return [];
  return tab.rows.slice(-6).reverse().map(row => {
    const label = row[0] == null ? (panel.output || panel.title || '—') : row[0];
    const value = row.length > 1 ? row[row.length - 1] : row[0];
    return {label: String(label), value: fmt(value)};
  });
}

function getDashboardPosterData() {
  const share = BOOT.share || {};
  const numberPanels = BOOT.panels.filter(p => (p.type || '').toLowerCase() === 'number');
  let metrics = numberPanels.slice(0, 8).map(p => ({
    label: p.title || p.output || '指标',
    value: panelDisplayValue(p),
    sub: p.description || p.output || ''
  }));
  if (!metrics.length) {
    metrics = BOOT.panels.slice(0, 6).map(p => ({
      label: p.title || p.output || '指标',
      value: panelDisplayValue(p),
      sub: p.output || ''
    }));
  }
  const sections = BOOT.panels
    .filter(p => (p.type || '').toLowerCase() !== 'number' && (p.type || '').toLowerCase() !== 'text')
    .slice(0, 3)
    .map(p => ({
      title: p.title || p.output || '数据区',
      type: 'list',
      summary: p.description || '',
      items: panelListItems(p),
      height: 176
    }));
  return {
    headline: share.title || document.title,
    summary: share.subtitle || 'QuantBuddy 实时取数看板，打开页面即拉取最新公式包输出。',
    metrics,
    sections,
    asof: BOOT.generatedAt || ''
  };
}

document.addEventListener('DOMContentLoaded', () => {
  // 封面模式：构建期把已校验产出注入 window.__QB_COVER__，直接离线渲染整页内容（去头尾），
  // 供 Edge 无头截图当封面。正常上传页面无此全局，分支 inert。
  if (window.__QB_COVER__) {
    document.body.classList.add('qb-cover');
    try { renderAll((window.__QB_COVER__ && window.__QB_COVER__.outputs) || {}); } catch (e) {}
    return;
  }
  if (window.QBShareShell) {
    QBShareShell.init({
      templateName: (BOOT.share && BOOT.share.pageType) || '标准实时看板',
      title: () => (BOOT.share && BOOT.share.title) || document.title,
      subtitle: () => (BOOT.share && BOOT.share.subtitle) || '',
      asof: () => BOOT.generatedAt || '',
      onRefresh: fetchLive,
      getPosterData: getDashboardPosterData
    });
  }
  fetchLive();
});
"""
    render_js = render_js.replace("__BOOT__", boot_json)

    mode_note = "数据：打开时实时取最新"
    mode_label = "Live HTML"
    mode_label_esc = html_escape(mode_label)
    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title_esc}</title>
<style>
  :root {{
    color-scheme: light;
    --qb-ink: #101827;
    --qb-text: #1f2937;
    --qb-muted: #697586;
    --qb-canvas: #f3f6fa;
    --qb-surface: #ffffff;
    --qb-surface-soft: #f8fafc;
    --qb-border: #dde5ef;
    --qb-border-strong: #bfccda;
    --qb-accent: #d8a54b;
    --qb-up: #c2412d;
    --qb-down: #16845b;
    --qb-line: #2454a6;
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", Roboto, Helvetica, Arial, sans-serif;
         background: var(--qb-canvas); color: var(--qb-text); }}
  a {{ color: inherit; }}
  a:focus-visible {{ outline: 2px solid #d8a54b; outline-offset: 3px; }}
  .shell-inner {{ max-width: 1180px; margin: 0 auto; padding: 0 20px; }}
  .topbar {{ min-height: 62px; display:flex; align-items:center; justify-content:space-between; gap:16px; border-bottom:1px solid rgba(255,255,255,.1); }}
  .brand-lockup {{ display:flex; align-items:center; gap:10px; text-decoration:none; min-width:0; }}
  .brand-mark {{ width:34px; height:34px; flex:0 0 34px; border:1px solid rgba(216,165,75,.65); display:grid; place-items:center;
                font-weight:800; font-size:13px; color:#f5d28f; background:#fff; border-radius:8px; overflow:hidden; padding:4px; }}
  .brand-mark svg {{ width:100%; height:100%; display:block; }}
  .brand-name {{ font-weight:750; letter-spacing:.01em; }}
  .brand-cn {{ display:block; color:#aeb8c8; font-size:12px; font-weight:500; margin-top:1px; }}
  .official-link {{ display:inline-flex; align-items:center; justify-content:center; min-height:36px; padding:0 13px;
                   border:1px solid rgba(255,255,255,.18); border-radius:8px; text-decoration:none; color:#edf2f7;
                   background:rgba(255,255,255,.06); white-space:nowrap; font-size:13px; }}
  .official-link:hover {{ background:rgba(255,255,255,.12); }}
  .hero-grid {{ display:grid; grid-template-columns:minmax(0,1fr) 146px; gap:28px; align-items:end; padding:30px 0 28px; }}
  .eyebrow {{ margin: 0 0 8px; color: #a8b1c2; font-size: 12px; letter-spacing: .08em; text-transform: uppercase; }}
  h1 {{ margin: 0; font-size: 32px; line-height: 1.12; letter-spacing: 0; }}
  .subtitle {{ margin: 12px 0 0; color: #dbe2ee; max-width: 860px; font-size: 14px; }}
  .meta-row {{ display:flex; flex-wrap:wrap; gap:8px; margin-top:16px; }}
  .meta-pill {{ display:inline-flex; align-items:center; min-height:26px; padding:0 9px; border-radius:8px;
               background:rgba(255,255,255,.08); color:#cbd5e1; font-size:12px; }}
  .meta-pill-strong {{ background:rgba(216,165,75,.16); color:#f8e4b7; border:1px solid rgba(216,165,75,.34); }}
  .share-card {{ justify-self:end; width:146px; border:1px solid rgba(216,165,75,.38); border-radius:8px; padding:12px;
                background:linear-gradient(180deg, rgba(255,255,255,.08), rgba(255,255,255,.03)); }}
  .share-title {{ color:#f8e4b7; font-weight:700; font-size:13px; margin-bottom:9px; }}
  .share-body {{ display:grid; place-items:center; }}
  .qr-frame {{ width:116px; height:116px; padding:0; background:#fff; border-radius:6px; overflow:hidden; display:grid; place-items:center; }}
  .qr-frame canvas {{ width:116px; height:116px; display:block; }}
  .qr-fallback {{ color:#111827; font-size:12px; text-align:center; line-height:1.45; }}
  main {{ max-width: 1180px; margin: 0 auto; padding: 18px 20px 26px; }}
  #grid {{ display: grid; grid-template-columns: repeat(12, minmax(0, 1fr)); gap: 12px; align-items: stretch; }}
  .card {{ position:relative; background: var(--qb-surface); border: 1px solid var(--qb-border); border-radius: 8px; padding: 14px 16px;
          box-shadow: 0 10px 26px rgba(16,24,39,.045); min-width: 0; }}
  .card h3 {{ margin: 0; font-size: 13px; color:#2b3445; font-weight:700; }}
  .card-head {{ display:flex; flex-direction:column; gap:3px; margin-bottom: 10px; }}
  .card-head p {{ margin:0; color:var(--qb-muted); font-size:12px; }}
  .card .body {{ overflow: auto; }}
  .span-full {{ grid-column: span 12; }}
  .span-wide {{ grid-column: span 8; }}
  .span-auto {{ grid-column: span 4; }}
  .card-text {{ display:grid; grid-template-columns: 132px minmax(0,1fr); gap:16px; align-items:start;
               padding:15px 18px; border-color:#d7e0eb; background:linear-gradient(90deg, rgba(216,165,75,.10), rgba(255,255,255,.96) 34%, #fff); }}
  .card-text::before {{ content:""; position:absolute; inset:12px auto 12px 0; width:4px; border-radius:0 4px 4px 0; background:var(--qb-accent); }}
  .card-text .card-head {{ margin:0; padding-top:1px; }}
  .card-text h3 {{ color:#172033; font-size:14px; }}
  .card-text .body {{ overflow:visible; }}
  .card-number {{ min-height: 112px; display:flex; flex-direction:column; justify-content:flex-start; gap:12px; padding:13px 15px 12px; background:linear-gradient(180deg,#fff,#fbfdff); }}
  .card-number .card-head {{ margin-bottom:0; min-height:18px; }}
  .card-number .body {{ overflow:visible; min-height:58px; display:flex; flex-direction:column; justify-content:flex-start; }}
  .card-number::before {{ content:""; position:absolute; left:14px; right:14px; top:0; height:3px; border-radius:0 0 3px 3px; background:#c7d2df; }}
  .card-number:has(.big.up)::before {{ background:var(--qb-up); }}
  .card-number:has(.big.down)::before {{ background:var(--qb-down); }}
  .card-line {{ padding:16px 18px 18px; border-color:#cfd9e6; box-shadow:0 14px 34px rgba(16,24,39,.06); }}
  .card-line .card-head {{ padding-bottom:8px; border-bottom:1px solid #edf1f6; }}
  .card-line h3 {{ font-size:15px; color:#172033; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
  th, td {{ border-bottom: 1px solid #eef0f2; padding: 6px 8px; text-align: right; white-space: nowrap; }}
  th:first-child, td:first-child {{ text-align: left; }}
  thead th {{ position: sticky; top: 0; background: #fafbfc; }}
  .big {{ font-size: 30px; line-height:1.1; font-weight: 760; padding: 3px 0 2px; letter-spacing:0; color:#111827; font-variant-numeric: tabular-nums; }}
  .big.up {{ color:var(--qb-up); }} .big.down {{ color:var(--qb-down); }} .big.flat {{ color:#667085; }}
  .big .unit {{ font-size: 16px; font-weight: 400; margin-left: 6px; opacity: .7; }}
  .desc {{ color:var(--qb-muted); font-size:12px; line-height:1.35; margin-top:2px; }}
  .text-panel {{ color:#334155; font-size:13px; line-height:1.7; max-height:7em; overflow:auto; padding-right:4px; }}
  .empty {{ color: #8a9099; padding: 12px 0; }}
  .empty.err {{ color: #d33; }}
  pre {{ margin: 0; font-size: 12px; white-space: pre-wrap; word-break: break-all; }}
  .site-footer {{ max-width: 1180px; margin: 0 auto; padding: 0 20px 24px; color: #697586; font-size: 12px; }}
  .footer-inner {{ border-top:1px solid #e2e7ef; padding-top:16px; display:flex; justify-content:space-between; gap:16px; align-items:flex-start; }}
  .footer-brand {{ color:#344054; font-weight:700; margin-bottom:4px; }}
  .footer-note {{ max-width:760px; line-height:1.7; }}
  .footer-link {{ color:#2454a6; text-decoration:none; white-space:nowrap; }}
  .footer-link:hover {{ text-decoration:underline; }}
  @media (max-width: 860px) {{
    .span-full, .span-wide, .span-auto {{ grid-column: span 12; }}
    .card-number.span-auto {{ grid-column: span 6; }}
    .topbar {{ min-height:58px; }}
    .brand-cn {{ max-width: clamp(150px, calc(100vw - 188px), 250px); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
    .brand-cn-name, .brand-dot {{ display:none; }}
    .official-link {{ min-height: 34px; padding: 0 10px; font-size: 12px; }}
    .hero-grid {{ grid-template-columns:1fr; padding:24px 0; gap:18px; }}
    h1 {{ font-size:26px; }}
    .share-card {{ display:none; }}
    main {{ padding:14px 12px 22px; }}
    #grid {{ gap:10px; }}
    .card-text {{ grid-template-columns:1fr; gap:8px; padding:13px 14px 14px; }}
    .card-text .card-head {{ margin-bottom:0; }}
    .text-panel {{ max-height:9em; }}
    .card-number {{ min-height:104px; gap:10px; padding:12px 12px 11px; }}
    .card-number .body {{ min-height:52px; }}
    .card-number::before {{ left:12px; right:12px; }}
    .big {{ font-size:24px; }}
    .big .unit {{ font-size:13px; margin-left:4px; }}
    .card-line {{ padding:14px 12px 16px; }}
    .footer-inner {{ flex-direction:column; }}
  }}
  @media (max-width: 360px) {{
    .topbar {{ min-height:70px; align-items:center; }}
    .brand-cn {{ max-width:150px; white-space:normal; line-height:1.22; }}
    .card-number.span-auto {{ grid-column: span 12; }}
  }}
  @media (prefers-color-scheme: dark) {{
    body {{ background:#0d1117; color:#c9d1d9; }}
    .card {{ background:#161b22; border-color:#30363d; box-shadow:none; }}
    .card h3 {{ color:#dbe2ee; }}
    .card-head p, .desc {{ color:#8b949e; }}
    .big {{ color:#f0f6fc; }}
    .text-panel {{ color:#c9d1d9; }}
    th, td {{ border-color:#21262d; }} thead th {{ background:#1b2129; }}
    .site-footer {{ color:#8b949e; }}
    .footer-inner {{ border-color:#30363d; }}
    .footer-brand {{ color:#dbe2ee; }}
    .footer-link {{ color:#8fb4ff; }}
  }}
  .std-hero {{ margin:0 0 14px; padding:16px 18px; background:#ffffff; border:1px solid var(--qb-border); border-radius:8px; }}
  .std-hero .eyebrow {{ margin:0 0 7px; color:#8a6a26; font-size:12px; letter-spacing:.06em; text-transform:uppercase; }}
  .std-hero h1 {{ color:#172033; }}
  .std-hero .subtitle {{ color:#475467; }}
  .std-hero .meta-pill {{ background:#eef3f8; color:#4b5b70; }}
  .std-hero .meta-pill-strong {{ background:rgba(216,165,75,.16); color:#87611d; border:1px solid rgba(216,165,75,.34); }}
{shared_css}
{live_card_css}
</style>
</head>
<body>
{shared_header}
<main>
  {live_card_html}
  {card_runtime_artifacts}
  <section class="std-hero">
    <div class="eyebrow">{mode_note}</div>
    <h1>{title_esc}</h1>
    {f"<p class='subtitle'>{subtitle_esc}</p>" if subtitle_esc else ""}
    <div class="meta-row">
      <span class="meta-pill">{page_type_esc}</span>
      <span class="meta-pill meta-pill-strong">Agent + Skill 生成</span>
      <span class="meta-pill">{mode_label_esc}</span>
    </div>
  </section>
  <div id="grid"></div>
</main>
{shared_footer}
{shared_modal}
<script src="{_ECHARTS_CDN}"></script>
<script>
{shared_runtime_js}
{live_card_js}
{render_js}
</script>
{card_runtime_js}
{live_card_binding}
</body>
</html>
"""
    return html


def _inspect_output_data(data):
    """对单个产出的 data 做结构体检：健康返回 None，否则返回疑因字符串。
    与前端 normalize 的解包口径一致，专门识别「取数没崩、但实质为空/无有效数值」的假成功。"""
    if data is None:
        return "data 为空（null）"
    if isinstance(data, dict):
        status = str(data.get("status") or "").lower()
        if status in ("failed", "fail", "error"):
            err = data.get("error") or data.get("message") or data.get("reason") or "未提供错误详情"
            return f"data.status={status}：{err}"
        if data.get("success") is False:
            err = data.get("error") or data.get("message") or data.get("reason") or "未提供错误详情"
            return f"data.success=false：{err}"
        # 解包按 read_mode 命名的外层 key（与前端 normalize 对齐）
        for wk in ("range_data", "last_value", "last_day_stats", "last_valid_per_asset"):
            inner = data.get(wk)
            if isinstance(inner, (dict, list)):
                return _inspect_output_data(inner)
        if "dates" in data or "values" in data:   # 序列（range_data）
            dates, values = data.get("dates"), data.get("values")
            if not dates or not values:
                return "range_data 的 dates/values 为空（疑似区间无数据/日期类型不符）"
            flat = []
            for v in values:
                flat.extend(v) if isinstance(v, list) else flat.append(v)
            if not any(isinstance(x, (int, float)) and not isinstance(x, bool) for x in flat):
                return "range_data values 不含有效数值（疑似全 null：日期类型/区间无数据/更新频率不匹配）"
            return None
        if "value" in data:                        # 单值（last_value）
            v = data.get("value")
            return None if isinstance(v, (int, float)) and not isinstance(v, bool) else "last_value.value 非有效数值"
        if data.get("top_values") or data.get("items") or data.get("records"):
            return None
        return None if data else "data 为空对象"
    if isinstance(data, list):
        return None if len(data) > 0 else "data 为空数组"
    if isinstance(data, str):
        return f"data 是字符串而非结构化数据：{data[:80]}"
    return None


def _inspect_outputs(panels, outputs):
    """逐 panel 体检其引用的产出，返回问题列表（空=全部健康）。"""
    problems = []
    for p in panels:
        if (p.get("type") or "").lower() == "text":
            continue
        name = p.get("output")
        out = outputs.get(name)
        if out is None:
            problems.append({"output": name, "reason": "取数结果缺该产出"})
            continue
        if out.get("error"):
            problems.append({"output": name, "reason": str(out.get("error"))})
            continue
        why = _inspect_output_data(out.get("data"))
        if why:
            problems.append({"output": name, "reason": why})
    return problems


def _is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _last_numeric(data):
    """Return (value, date) using the same last-effective-value idea as number cards."""
    if data is None:
        return None, None
    if isinstance(data, dict):
        for wk in ("range_data", "last_value", "last_day_stats", "last_valid_per_asset"):
            inner = data.get(wk)
            if isinstance(inner, (dict, list)):
                return _last_numeric(inner)
        if "dates" in data or "values" in data:
            dates, values = data.get("dates") or [], data.get("values") or []
            if isinstance(values, list):
                if values and all(_is_number(x) or x is None for x in values):
                    for i in range(len(values) - 1, -1, -1):
                        if _is_number(values[i]):
                            d = dates[i] if i < len(dates) else None
                            return float(values[i]), d
                if values and isinstance(values[0], list):
                    # Most range_data payloads are series-oriented: values[0][i].
                    for series in values:
                        if not isinstance(series, list):
                            continue
                        for i in range(len(series) - 1, -1, -1):
                            if _is_number(series[i]):
                                d = dates[i] if i < len(dates) else None
                                return float(series[i]), d
            return None, None
        if "value" in data and _is_number(data.get("value")):
            return float(data.get("value")), data.get("date")
        # Fallback for last_day_stats-like dicts: pick the last numeric field.
        for key in reversed(list(data.keys())):
            if _is_number(data.get(key)):
                return float(data.get(key)), data.get("date") or data.get("trade_date")
    if isinstance(data, list):
        for item in reversed(data):
            val, date = _last_numeric(item)
            if val is not None:
                return val, date
    return None, None


def _single_stock_facts(outputs):
    facts = {}
    for name in ("px", "chg", "ret20", "ret60", "pe", "pb", "amt_yi"):
        out = outputs.get(name) or {}
        val, date = _last_numeric(out.get("data"))
        if val is not None:
            facts[name] = {"value": val, "date": date}
    return facts


_NUM_RE = re.compile(r"[-+]?\d+(?:,\d{3})*(?:\.\d+)?")


def _numbers_near_keywords(text, keywords, radius=36):
    hits = []
    if not text:
        return hits
    for m in _NUM_RE.finditer(text):
        start, end = m.span()
        prev_ch = text[start - 1] if start > 0 else ""
        next_ch = text[end] if end < len(text) else ""
        raw = m.group(0)
        # Ignore ISO/date fragments such as 2026-06-16 or 2026年.
        if raw.startswith("-") and prev_ch.isdigit():
            continue
        if prev_ch in ("-", "/", ".") or next_ch in ("-", "/", ".", "年", "月", "日"):
            continue
        if len(raw) == 4 and raw.startswith("20"):
            continue
        window = text[max(0, start - radius): min(len(text), end + radius)]
        if any(k in window for k in keywords):
            try:
                hits.append(float(raw.replace(",", "")))
            except ValueError:
                pass
    return hits


def _close_enough(actual, claimed, *, abs_tol, rel_tol=0.0):
    return abs(actual - claimed) <= max(abs_tol, abs(actual) * rel_tol)


def _validate_single_stock_copy_consistency(params, panels, outputs):
    """Validate key prose numbers against the build-time verification outputs for single-stock pages."""
    if not _is_single_stock_candidate(params):
        return None, None
    if _as_bool(params.get("allow_inconsistent_copy"), False):
        return None, _single_stock_facts(outputs)

    facts = _single_stock_facts(outputs)
    text_parts = [str(params.get("subtitle") or "")]
    for p in panels:
        if isinstance(p, dict) and (p.get("type") or "").lower() == "text":
            text_parts.append(str(p.get("text") or p.get("content") or p.get("description") or ""))
    text = "\n".join(text_parts)

    metric_rules = [
        ("px", "最新收盘价", ("收盘", "收盘价", "最新价"), 0.05, 0.001),
        ("chg", "日涨跌幅", ("涨跌幅", "单日", "当日", "日涨"), 0.08, 0.0),
        ("ret20", "20日表现", ("20日", "20 日"), 0.12, 0.0),
        ("ret60", "60日表现", ("60日", "60 日"), 0.12, 0.0),
        ("pe", "PE(TTM)", ("PE", "市盈率"), 0.08, 0.001),
        ("pb", "PB", ("PB", "市净率"), 0.08, 0.001),
        ("amt_yi", "成交额(亿元)", ("成交额",), 0.2, 0.01),
    ]

    mismatches = []
    for output, label, keywords, abs_tol, rel_tol in metric_rules:
        fact = facts.get(output)
        if not fact:
            continue
        actual = fact["value"]
        claims = _numbers_near_keywords(text, keywords)
        if not claims:
            continue
        if any(_close_enough(actual, n, abs_tol=abs_tol, rel_tol=rel_tol) for n in claims):
            continue
        mismatches.append({
            "output": output,
            "label": label,
            "expected": round(actual, 4),
            "claimed_near_keywords": [round(n, 4) for n in claims[:6]],
        })

    if not mismatches:
        return None, facts
    return {
        "code": 1,
        "message": "单标的画像页文案与实时取数结果不一致，拒绝生成/上传",
        "mismatches": mismatches,
        "facts": {k: {"value": round(v["value"], 4), "date": v.get("date")} for k, v in facts.items()},
        "hint": "请用 build_dashboard 实时取数结果（最终 outputs）里的数值重写 subtitle 和阅读摘要，不要使用旧查询结果或手工估算值。",
    }, facts


def _is_single_stock_candidate(params):
    """Detect specs that claim to be the standard single-stock factsheet."""
    brand = params.get("brand") if isinstance(params.get("brand"), dict) else {}
    template = str(params.get("template") or params.get("page_template") or "").strip().lower()
    if template in ("single-stock", "single_stock", "stock-factsheet"):
        return True
    if str(params.get("template_contract") or "").strip().lower() in ("custom", "none", "off"):
        return False
    text = " ".join(
        str(v or "")
        for v in (
            params.get("title"),
            params.get("page_type"),
            brand.get("page_type"),
        )
    )
    return any(
        k in text
        for k in (
            "个股画像",
            "单股画像",
            "单标的画像",
            "股票画像",
            "单只股票",
            "单股",
        )
    )


def _validate_template_contract(params, panels):
    """Hard guardrails for reusable templates so agents do not silently emit stale layouts."""
    if not _is_single_stock_candidate(params):
        return None
    if _as_bool(params.get("allow_custom_single_stock"), False):
        return None

    outputs = {
        str(p.get("output"))
        for p in panels
        if isinstance(p, dict) and p.get("output")
    }
    required = {"px", "chg", "ret20", "ret60", "pe", "pb", "amt_yi"}
    missing = sorted(required - outputs)
    has_text = any((p.get("type") or "").lower() == "text" for p in panels if isinstance(p, dict))
    has_px_number = any(
        p.get("output") == "px" and (p.get("type") or "").lower() == "number"
        for p in panels
        if isinstance(p, dict)
    )
    has_px_line = any(
        p.get("output") == "px" and (p.get("type") or "").lower() == "line"
        for p in panels
        if isinstance(p, dict)
    )

    issues = []
    if missing:
        issues.append("缺少默认 outputs: " + ", ".join(missing))
    if not has_text:
        issues.append("缺少阅读摘要 text panel")
    if not has_px_number:
        issues.append("缺少最新收盘价 number panel（output=px）")
    if not has_px_line:
        issues.append("缺少近一年收盘价 line panel（output=px）")
    if not issues:
        return None

    return {
        "code": 1,
        "message": "单标的画像页未满足模板契约，拒绝生成旧版 1 条线 + 少量数字卡页面",
        "template": "online templates / single-stock contract",
        "issues": issues,
        "hint": "请先通过 static_page.py templates/template 复用在线个股画像模板；若自行构建 spec，保留 template=single-stock，并补齐阅读摘要、px/chg/ret20/ret60/pe/pb/amt_yi、subtitle 与日期口径。",
    }


def _manifest_path_for(out_file):
    root, _ext = os.path.splitext(out_file)
    return root + ".manifest.json"


def _write_manifest(out_file, manifest):
    path = _manifest_path_for(out_file)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    return path


def _resolve_local_path(path):
    if not path:
        return None
    return path if os.path.isabs(path) else os.path.join(C.SKILL_ROOT, path)


def _provided_thumbnail_file(params):
    for key in ("thumbnail_file", "thumbnail_image", "thumbnail_path"):
        value = params.get(key)
        if isinstance(value, str) and value.strip():
            return _resolve_local_path(value.strip())
    thumb = params.get("thumbnail")
    if isinstance(thumb, str) and thumb.strip():
        return _resolve_local_path(thumb.strip())
    if isinstance(thumb, dict):
        for key in ("file", "image_file", "thumbnail_file", "path"):
            value = thumb.get(key)
            if isinstance(value, str) and value.strip():
                return _resolve_local_path(value.strip())
    return None


def _auto_thumbnail_requested(params):
    for key in ("auto_thumbnail", "generate_thumbnail"):
        if key in params:
            return _as_bool(params.get(key), False)
    thumb = params.get("thumbnail")
    if isinstance(thumb, bool):
        return thumb
    if isinstance(thumb, dict):
        if any(isinstance(thumb.get(k), str) and thumb.get(k).strip()
               for k in ("file", "image_file", "thumbnail_file", "path")):
            return False
        if "enabled" in thumb:
            return _as_bool(thumb.get("enabled"), True)
        if "auto" in thumb:
            return _as_bool(thumb.get("auto"), True)
        if "generate" in thumb:
            return _as_bool(thumb.get("generate"), True)
        return True
    return False


def _thumbnail_tags(params):
    tags = params.get("tags") if isinstance(params.get("tags"), list) else []
    if tags:
        return tags
    out = []
    for key in ("template", "page_type", "category"):
        value = params.get(key)
        if value:
            out.append(value)
    if params.get("upload") or params.get("update_page_id"):
        out.append("可分享")
    out.append("实时取数")
    return out


def _thumb_number(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(value):
        return float(value)
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        if not text:
            return None
        try:
            value = float(text)
            return value if math.isfinite(value) else None
        except ValueError:
            return None
    return None


def _thumb_series_from_data(data):
    if data is None:
        return []
    if isinstance(data, dict):
        for key in ("range_data", "last_value", "last_day_stats", "last_valid_per_asset"):
            points = _thumb_series_from_data(data.get(key))
            if points:
                return points
        dates = data.get("dates") or data.get("x") or data.get("labels") or data.get("categories")
        values = data.get("values") or data.get("y") or data.get("series") or data.get("data")
        if isinstance(dates, list) and isinstance(values, list):
            if values and isinstance(values[0], list):
                values = values[0]
            pairs = []
            for i in range(min(len(dates), len(values))):
                pairs.append([dates[i], values[i]])
            return _thumb_series_from_data(pairs)
        if isinstance(data.get("columns"), list) and isinstance(data.get("rows"), list):
            columns = data["columns"]
            rows = data["rows"]
            numeric_idx = None
            for ci, _name in enumerate(columns):
                if any(_thumb_number(row[ci]) is not None for row in rows if isinstance(row, list) and ci < len(row)):
                    numeric_idx = ci
            if numeric_idx is None:
                return []
            x_idx = 0 if numeric_idx != 0 else (1 if len(columns) > 1 else None)
            points = []
            for ri, row in enumerate(rows):
                if not isinstance(row, list) or numeric_idx >= len(row):
                    continue
                y = _thumb_number(row[numeric_idx])
                if y is None:
                    continue
                x = row[x_idx] if x_idx is not None and x_idx < len(row) else ri
                points.append({"x": str(x), "y": y})
            return points[-260:]
        for key in ("points", "items", "records", "top_values"):
            points = _thumb_series_from_data(data.get(key))
            if points:
                return points
        return []
    if not isinstance(data, list):
        return []
    points = []
    for idx, item in enumerate(data):
        x = idx
        y = None
        if isinstance(item, dict):
            x = item.get("date", item.get("time", item.get("x", item.get("label", idx))))
            for key in ("value", "y", "close", "price", "score"):
                y = _thumb_number(item.get(key))
                if y is not None:
                    break
            if y is None:
                for val in item.values():
                    y = _thumb_number(val)
                    if y is not None:
                        break
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            x = item[0]
            y = _thumb_number(item[1])
        else:
            y = _thumb_number(item)
        if y is not None:
            points.append({"x": str(x), "y": y})
    return points[-260:]


def _thumbnail_series_from_outputs(panels, outputs):
    if not isinstance(outputs, dict):
        return []
    preferred = []
    fallback = []
    for panel in panels:
        if not isinstance(panel, dict) or not panel.get("output"):
            continue
        target = preferred if (panel.get("type") or "").lower() in ("line", "bar") else fallback
        target.append(panel.get("output"))
    for output in preferred + fallback:
        item = outputs.get(output)
        if not isinstance(item, dict) or item.get("error"):
            continue
        points = _thumb_series_from_data(item.get("data"))
        if len(points) >= 2:
            return points
    return []


def _default_thumbnail_file(out_file):
    base = os.path.splitext(os.path.basename(out_file))[0] or "dashboard"
    return os.path.join(C.SKILL_ROOT, "output", "thumbnails", base + ".png")


_COVER_MODE_CSS = (
    "<style id=\"qb-cover-css\">"
    ":root{color-scheme:light !important;}"
    "html,body{background:#f3f6fa !important;}"
    ".qb-head,[data-qb-share-shell],.qb-footer,[data-qb-share-shell-footer],"
    ".share-modal,#sharePosterModal,.qb-actions,#refresh,#shareBtn,.site-footer{display:none !important;}"
    "main{max-width:1200px !important;margin:0 auto !important;padding:24px !important;}"
    "@media (prefers-color-scheme: dark){"
    "body{background:#f3f6fa !important;color:#1f2937 !important;}"
    ".card{background:#fff !important;border-color:#dde5ef !important;box-shadow:none !important;}"
    ".card h3,.std-hero h1{color:#172033 !important;} .card-head p,.desc{color:#697586 !important;}"
    ".big{color:#111827 !important;} .text-panel{color:#334155 !important;}"
    "th,td{border-color:#eef0f2 !important;} thead th{background:#fafbfc !important;}}"
    "</style>"
)


def _echarts_local_path():
    """确保 ECharts 本地缓存存在（缺则一次性从 CDN 下载落盘），返回缓存绝对路径或 None。

    缓存到 assets/vendor/echarts.min.js；下载失败返回 None（封面页退回 CDN）。
    """
    cache = os.path.join(C.SKILL_ROOT, "assets", "vendor", "echarts.min.js")
    if os.path.exists(cache) and os.path.getsize(cache) > 200000:
        return cache
    try:
        import urllib.request
        req = urllib.request.Request(_ECHARTS_CDN, headers={"User-Agent": "qb-view"})
        with C._NO_PROXY_OPENER.open(req, timeout=30) as resp:
            data = resp.read()
        if len(data) < 200000:
            return None
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        with open(cache, "wb") as f:
            f.write(data)
        return cache
    except Exception:
        return None


def _build_cover_html(html, outputs):
    """把渲染好的页面 html 改成一次性「封面模式页」：本地 ECharts + 注入构建期产出 + 隐藏头尾 + 强制浅色。

    该文件只用于本地 Edge 无头截图，不上传；正常页面不含 window.__QB_COVER__，分支 inert。
    把 CDN ECharts 换成本地文件引用后，封面页无需联网、秒加载、图表同步画完——保证截图时页面已完全渲染。
    """
    # 用本地文件引用替换 CDN <script src>（file:// 页面可加载 file:// 脚本），去掉 ~8s CDN 等待。
    # 不内联文本：minified JS 里的 </script> 等序列会提前闭合标签、把源码当文本渲染。
    cache = _echarts_local_path()
    if cache:
        cdn_tag = '<script src="' + _ECHARTS_CDN + '"></script>'
        local_uri = pathlib.Path(cache).resolve().as_uri()
        html = html.replace(cdn_tag, '<script src="' + local_uri + '"></script>', 1)

    data = json.dumps({"outputs": outputs or {}}, ensure_ascii=False)
    boot = "<script>window.__QB_COVER__=" + data + ";</script>"
    if "</head>" in html:
        html = html.replace("</head>", _COVER_MODE_CSS + "</head>", 1)
    else:
        html = _COVER_MODE_CSS + html
    if "</body>" in html:
        html = html.replace("</body>", boot + "</body>", 1)
    else:
        html = html + boot
    return html


def _estimate_cover_height(panels):
    """按 panel 估算整页内容高度（用于 Edge 窗口高度）。宁可底部留白，不可裁切：上取整 ×1.1，cap[700,5000]。"""
    total = 150 + 60  # hero + main padding
    small = 0
    for p in panels or []:
        if not isinstance(p, dict):
            continue
        t = (p.get("type") or "table").lower()
        span = p.get("span") or ("full" if t in ("line", "bar") else "auto")
        if t in ("line", "bar") or span in ("full", "wide"):
            try:
                h = int(p.get("height") or 360)
            except (TypeError, ValueError):
                h = 360
            total += h + 80 + 16
        else:
            small += 1
    total += math.ceil(small / 2) * (240 + 16)
    return max(700, min(5000, int(total * 1.08)))


_THUMB_MAX_BYTES = 2 * 1024 * 1024


def _shrink_png_under(path, limit):
    """可选增强：截图超 2MB 时用 Pillow 降采样/转 JPEG 压到限内；无 Pillow 返回 None。"""
    try:
        from PIL import Image
    except Exception:
        return None
    try:
        img = Image.open(path).convert("RGB")
    except Exception:
        return None
    for scale in (1.0, 0.85, 0.7, 0.55, 0.42):
        im = img if scale == 1.0 else img.resize(
            (max(1, int(img.width * scale)), max(1, int(img.height * scale))), Image.LANCZOS)
        try:
            im.save(path, format="PNG", optimize=True)
            if os.path.getsize(path) <= limit:
                return path
            jpg = os.path.splitext(path)[0] + ".jpg"
            im.save(jpg, format="JPEG", quality=82, optimize=True)
            if os.path.getsize(jpg) <= limit:
                if os.path.abspath(jpg) != os.path.abspath(path):
                    try:
                        os.remove(path)
                    except OSError:
                        pass
                return jpg
        except Exception:
            continue
    return None


def _generate_page_cover(html_file, panels, outputs, thumb_out):
    """默认封面：截真实页面整页内容（去头尾、强制浅色、构建期数据离线渲染）。

    失败/无浏览器/超 2MB 又压不下来 → 返回 None，交回调用方走合成 SVG 兜底。
    """
    _generate_page_cover.last_reason = None
    try:
        import render_cover as RC
    except Exception:
        _generate_page_cover.last_reason = "render_cover_import_failed"
        return None
    if not RC._find_browser():
        _generate_page_cover.last_reason = "no_browser"
        return None
    try:
        with open(html_file, "r", encoding="utf-8") as f:
            html = f.read()
    except OSError:
        _generate_page_cover.last_reason = "html_read_failed"
        return None

    base = os.path.splitext(thumb_out)[0]
    cover_html_path = base + ".cover-page.html"
    out_png = base + ".png"
    shot = None
    try:
        with open(cover_html_path, "w", encoding="utf-8") as f:
            f.write(_build_cover_html(html, outputs or {}))
        shot = RC.capture_page_cover(cover_html_path, out_png, _estimate_cover_height(panels))
    except Exception as exc:
        _generate_page_cover.last_reason = f"capture_exception:{exc}"
        shot = None
    finally:
        try:
            os.remove(cover_html_path)
        except OSError:
            pass
    if not shot:
        if not _generate_page_cover.last_reason:
            _generate_page_cover.last_reason = "capture_failed"
        return None

    dims = RC._png_dims(shot)
    size = os.path.getsize(shot)
    if size > _THUMB_MAX_BYTES:
        smaller = _shrink_png_under(shot, _THUMB_MAX_BYTES)
        if not smaller:
            _generate_page_cover.last_reason = "over_2mb_unshrinkable"
            try:
                os.remove(shot)
            except OSError:
                pass
            return None
        shot = smaller
        size = os.path.getsize(shot)
        dims = RC._png_dims(shot) or dims
    return {
        "code": 0,
        "thumbnail_generation_status": "generated",
        "out_file": shot,
        "mode": "page",
        "rasterizer": "edge-page",
        "width": dims[0] if dims else None,
        "height": dims[1] if dims else None,
        "bytes": size,
    }


def _prepare_thumbnail(params, panels, out_file, outputs=None):
    provided = _provided_thumbnail_file(params)
    if provided:
        return {
            "file": provided,
            "status": "provided" if os.path.exists(provided) else "provided_missing",
            "generation": {"code": 0, "provided": True, "out_file": provided},
        }

    if not _auto_thumbnail_requested(params):
        return {"file": None, "status": "not_requested", "generation": None}

    thumb_cfg = params.get("thumbnail") if isinstance(params.get("thumbnail"), dict) else {}
    thumb_out = _resolve_local_path(thumb_cfg.get("out_file")) if thumb_cfg.get("out_file") else _default_thumbnail_file(out_file)
    render_params = {
        "title": params.get("title"),
        "subtitle": params.get("subtitle"),
        "description": params.get("description"),
        "template": params.get("template") or params.get("page_type"),
        # 分类/数据模式：默认裸图只记录元信息；style=poster 时用于 eyebrow 与信息卡。
        "template_type": thumb_cfg.get("template_type") or params.get("template_type") or params.get("category"),
        "category": thumb_cfg.get("category") or params.get("category"),
        "data_mode": thumb_cfg.get("data_mode") or params.get("data_mode"),
        "tags": thumb_cfg.get("tags") if isinstance(thumb_cfg.get("tags"), list) else _thumbnail_tags(params),
        "out_file": thumb_out,
    }
    for key in ("style", "cover_style"):
        if thumb_cfg.get(key):
            render_params[key] = thumb_cfg.get(key)
    # 封面曲线用「构建期已校验数据」内联绘制：显式 series 优先，否则从产出抽首个 line/bar 序列。
    series = thumb_cfg.get("series") or thumb_cfg.get("chart_series") or params.get("series") or params.get("chart_series")
    if not series:
        series = _thumbnail_series_from_outputs(panels, outputs or {})
    if series:
        render_params["series"] = series

    # 封面模式：page=截真实页面整页（默认）/ chart=合成全幅曲线 / poster=品牌海报。
    cover_mode = str(thumb_cfg.get("cover_mode") or params.get("cover_mode") or "page").lower()
    if cover_mode == "poster":
        render_params.setdefault("style", "poster")

    # 1) 默认：截真实页面整页内容（去头尾）。失败/无浏览器/超 2MB 压不下 → 回退合成。
    if cover_mode == "page":
        page_gen = _generate_page_cover(out_file, panels, outputs, thumb_out)
        if page_gen:
            return {"file": page_gen.get("out_file"), "status": "generated", "generation": page_gen}

    # 2) 合成 SVG 封面（chart/poster，或截图回退）：Edge 栅格化 → 纯 Python PNG → SVG 三层兜底。
    try:
        import render_cover as RC
        generation = RC.render_cover(render_params)
        if isinstance(generation, dict) and generation.get("code") == 0 and cover_mode == "page":
            generation["mode"] = "chart-fallback"
            generation["fallback_reason"] = getattr(_generate_page_cover, "last_reason", None) or "page_cover_failed"
        elif isinstance(generation, dict) and generation.get("code") == 0 and cover_mode in ("chart", "poster"):
            generation["mode"] = cover_mode
        if isinstance(generation, dict) and generation.get("code") == 0 and generation.get("bytes") is None:
            out = generation.get("out_file")
            if out and os.path.exists(out):
                generation["bytes"] = os.path.getsize(out)
    except Exception as exc:
        generation = {"code": 1, "message": str(exc), "thumbnail_generation_status": "failed"}

    if isinstance(generation, dict) and generation.get("code") == 0:
        return {"file": generation.get("out_file"), "status": "generated", "generation": generation}
    if isinstance(generation, dict) and generation.get("skipped"):
        return {"file": None, "status": "skipped", "generation": generation}
    return {"file": None, "status": "failed", "generation": generation}


def cmd_build(params):
    title = params.get("title")
    if not title:
        return {"code": 1, "message": "spec 缺少 title"}
    panels = params.get("panels")
    if not isinstance(panels, list) or not panels:
        return {"code": 1, "message": "spec.panels 必须是非空数组"}
    template_err = _validate_template_contract(params, panels)
    if template_err:
        return template_err
    # 页面实时取数；spec 不需要 mode 字段，旧 spec 里残留的 mode 兼容忽略。
    legacy_mode = (params.get("mode") or "").lower()

    pkg, sig, err = _resolve_credential(params)
    if err:
        return err
    if not pkg or not sig:
        return {"code": 1, "message": "需要 package_id + signature 才能在页面内实时取数（signature 可由本地凭证补全）"}

    endpoint = C.endpoint_of(C.load_config())  # query 无需 api_key，仅取 endpoint

    # 构建期取一次数：只用于质量体检 + 单标的文案一致性校验，不内联进 HTML（页面仍走运行时实时取数）。
    res = FP.query_package(endpoint, pkg, sig)
    if res.get("code") != 0:
        return {"code": 1, "message": "构建期取数失败，无法校验看板（公式 / 读取模式 / 凭证 / 端点 任一异常）",
                "failures": res.get("failures"), "query_result": res}
    verify_outputs = res.get("outputs") or {}
    # P0-1 数据体检：取数即便 code:0，也逐 panel 校验产出结构，杜绝「假成功看板」
    problems = _inspect_outputs(panels, verify_outputs)
    if problems:
        return {"code": 1,
                "message": "取数体检未通过，拒绝生成可能假成功的看板（请检查公式 / 读取模式 / 日期区间）",
                "failed_outputs": problems}
    copy_err, single_stock_facts = _validate_single_stock_copy_consistency(params, panels, verify_outputs)
    if copy_err:
        return copy_err

    generated_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    live_card_enabled = params.get("live_card") is not None and params.get("live_card") is not False
    html = _render_html(params, title=title, subtitle=params.get("subtitle"),
                        panels=panels, endpoint=endpoint, package_id=pkg, signature=sig,
                        generated_at=generated_at)

    out_file = params.get("out_file")
    if out_file:
        if not os.path.isabs(out_file):
            out_file = os.path.join(C.SKILL_ROOT, out_file)
    else:
        os.makedirs(PAGES_DIR, exist_ok=True)
        out_file = os.path.join(PAGES_DIR, _slug(title) + ".html")
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(html)

    thumbnail_info = _prepare_thumbnail(params, panels, out_file, verify_outputs)
    manifest = {
        "schema_version": 1,
        "page_id": None,
        "url": None,
        "html_file": out_file,
        "html_sha256": hashlib.sha256(html.encode("utf-8")).hexdigest(),
        "thumbnail_file": thumbnail_info.get("file"),
        "thumbnail_url": None,
        "thumbnail_generation_status": thumbnail_info.get("status") or "not_requested",
        "endpoint": endpoint,
        "formula_packages": {
            "DEFAULT": {
                "package_id": pkg,
                "outputs": [
                    p.get("output") for p in panels
                    if isinstance(p, dict) and p.get("output")
                ],
            }
        },
        "built_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "verification": {
            "build_time_query": "ok",
            "output_health": "ok",
            "publish_runtime_check": "not_run",
        },
        "live_card": {
            "enabled": live_card_enabled,
            "cover_card_url": None,
            "has_cover_card": False,
        },
    }
    if thumbnail_info.get("generation"):
        manifest["thumbnail_generation"] = thumbnail_info["generation"]
    manifest_path = _write_manifest(out_file, manifest)

    result = {
        "code": 0,
        "out_file": out_file,
        "mode": "live",
        "package_id": pkg,
        "panels": len(panels),
        "size": len(html.encode("utf-8")),
        "manifest": manifest_path,
        "thumbnail_file": thumbnail_info.get("file"),
        "thumbnail_generation_status": thumbnail_info.get("status") or "not_requested",
        "message": "已生成实时取数看板 HTML",
    }
    if thumbnail_info.get("generation"):
        result["thumbnail_generation"] = thumbnail_info["generation"]
    if legacy_mode and legacy_mode != "live":
        result["note"] = "spec 里的 mode 字段已忽略，页面按实时取数生成。"
    if single_stock_facts:
        result["facts"] = {
            k: {"value": round(v["value"], 4), "date": v.get("date")}
            for k, v in single_stock_facts.items()
        }

    update_page_id = params.get("update_page_id")
    if params.get("upload") or update_page_id:
        import static_page as SP
        # 页面说明（列表/详情展示用）：仅显式传 spec.description 时透传；不传则不动（update 保留原值）
        page_desc = params.get("description")
        thumbnail_file = thumbnail_info.get("file")
        if update_page_id:
            # 替换已发布页面：URL / page_id 不变，已分享链接照常可用
            up = SP.cmd_update({
                "page_id": update_page_id,
                "html_file": out_file,
                "title": title,
                "description": page_desc,
                "ttl_days": params.get("ttl_days"),
                "verify_packages": params.get("verify_packages"),
                "verify_cover_card": params.get("verify_cover_card", live_card_enabled),
                "cover_card_url": params.get("cover_card_url"),
                "has_cover_card": params.get("has_cover_card", live_card_enabled if live_card_enabled else None),
                "thumbnail_file": thumbnail_file,
            })
            result["update"] = up
            verb = "替换"
        else:
            up = SP.cmd_upload({
                "html_file": out_file,
                "title": title,
                "description": page_desc,
                "ttl_days": params.get("ttl_days"),
                "verify_packages": params.get("verify_packages"),
                "verify_cover_card": params.get("verify_cover_card", live_card_enabled),
                "cover_card_url": params.get("cover_card_url"),
                "has_cover_card": params.get("has_cover_card", live_card_enabled if live_card_enabled else None),
                "thumbnail_file": thumbnail_file,
            })
            result["upload"] = up
            verb = "上传"
        if up.get("code") == 0 and up.get("url"):
            result["url"] = up["url"]
            if up.get("thumbnail_url"):
                result["thumbnail_url"] = up.get("thumbnail_url")
            if up.get("cover_card_url"):
                result["cover_card_url"] = up.get("cover_card_url")
            if up.get("has_cover_card") is not None:
                result["has_cover_card"] = bool(up.get("has_cover_card"))
            manifest["page_id"] = up.get("page_id")
            manifest["url"] = up.get("url")
            manifest["thumbnail_url"] = up.get("thumbnail_url") or None
            manifest["live_card"]["cover_card_url"] = up.get("cover_card_url") or None
            manifest["live_card"]["has_cover_card"] = bool(up.get("has_cover_card"))
            if up.get("cover_verification"):
                manifest["verification"]["cover_card"] = "ok"
            if up.get("thumbnail_warning"):
                manifest["thumbnail_upload_warning"] = up.get("thumbnail_warning")
            manifest["verification"]["publish_runtime_check"] = (
                (up.get("_package_runtime_check") or {}).get("status")
                or "not_verifiable_by_publish_key"
            )
            manifest_path = _write_manifest(out_file, manifest)
            result["manifest"] = manifest_path
        elif up.get("code") != 0:
            result["message"] += f"（HTML 已生成，但{verb}失败，见 {'update' if update_page_id else 'upload'} 字段）"
            manifest["verification"]["publish_runtime_check"] = "upload_failed"
            manifest_path = _write_manifest(out_file, manifest)
            result["manifest"] = manifest_path

    return result


def main():
    params = C.read_params(sys.argv[1:], env_var="BD_PARAMS")
    try:
        result = cmd_build(params)
    except (FileNotFoundError, ValueError) as e:
        result = {"code": 1, "message": str(e)}
    C.emit(result, out_name="bd_out.txt")
    sys.exit(0 if (isinstance(result, dict) and result.get("code") == 0) else 1)


if __name__ == "__main__":
    main()
