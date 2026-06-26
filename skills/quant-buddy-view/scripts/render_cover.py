#!/usr/bin/env python3
r"""
模板封面生成器（零强依赖、跨环境）。

设计目标：在任意用户环境都能产出一张「和真实页面同款浅色风」的 1200x675 封面，
不依赖 Pillow，也不强制 `npm i playwright`。

工作方式：
  1. 纯 Python 把封面拼成一份**自包含 SVG 海报**（版式 + 真实数据曲线全是矢量），
     再包进一个 margin:0 的 HTML。封面设计完全在 SVG/CSS 里，天然贴合页面视觉。
  2. 栅格化成 PNG —— 按可用性自动选后端：
       ① 系统 Edge / Chrome 无头：`--headless --screenshot`（Windows 基本自带 Edge，零安装）
       ② 纯 Python：cairosvg 或 svglib(+rlPyCairo)，装了就用
       ③ 都没有 → 直接产出 SVG 当封面（<img>/OG 均可渲染，零依赖兜底）
  右侧曲线用「构建期已校验数据」内联绘制，确定、离线、不闪，仍是真实走势。

参数（RT_PARAMS > @file > JSON > stdin）:
    {
      "title": "封面标题",
      "subtitle": "可选副标题",
      "template_type": "可选模板分类/意图，如 看标的",
      "data_mode": "实时取数",
      "tags": ["A股", "实时取数"],
      "series": [["2026-06-01", 1.0], ["2026-06-02", 1.2]],
      "out_file": "output/thumbnails/cover.png"
    }
"""

import base64
import datetime
import math
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
from html import escape as _esc

import common as C

WIDTH = 1200
HEIGHT = 675

# ── 调色板：与真实页面 _render_html 的 CSS 变量一致（浅色编辑风）──
BG = "#f3f6fa"
SURFACE = "#ffffff"
INK = "#101827"
MUTED = "#697586"
BORDER = "#dde5ef"
BORDER_STRONG = "#bfccda"
GOLD = "#d8a54b"
GOLD_SOFT = "#f5d28f"
BLUE = "#2454a6"
BLUE_SOFT = "#e0e9f7"
UP = "#c2412d"      # A股 涨=红
DOWN = "#16845b"    # A股 跌=绿
GRID = "#eef2f7"

FONT_STACK = ("'Microsoft YaHei','PingFang SC','Noto Sans CJK SC',"
              "'Hiragino Sans GB','Source Han Sans SC',sans-serif")

# 内部分类词 → 中文展示名
_DISPLAY_CATEGORY = {
    "看标的": "个股分析",
    "factor": "选股因子",
    "gauge": "估值水位",
    "radar": "指数异动",
    "waves": "商品多空",
    "monitor": "盘面监控",
}


def _display_category(text):
    raw = str(text or "").strip()
    return _DISPLAY_CATEGORY.get(raw, _DISPLAY_CATEGORY.get(raw.lower(), raw or "公共模板"))


def _variant_from_text(text):
    text = str(text or "").lower()
    rules = [
        ("factor", ("因子", "选股", "筛选", "评分", "rank", "screener", "topn")),
        ("gauge", ("估值", "水位", "泡沫", "pe", "pb", "valuation", "gauge")),
        ("radar", ("异动", "成分股", "指数", "监控", "复盘", "anomaly", "index")),
        ("waves", ("商品", "期货", "多空", "commodity", "futures", "spread")),
    ]
    for variant, keywords in rules:
        if any(k in text for k in keywords):
            return variant
    return "monitor"


def _slug(text):
    text = re.sub(r"[^0-9A-Za-z一-鿿]+", "-", str(text or "cover")).strip("-")
    return (text or "cover")[:48]


def _resolve_out_file(params):
    out_file = params.get("out_file")
    if out_file:
        return out_file if os.path.isabs(out_file) else os.path.join(C.SKILL_ROOT, out_file)
    out_dir = os.path.join(C.SKILL_ROOT, "output", "thumbnails")
    return os.path.join(out_dir, _slug(params.get("title")) + ".png")


# ────────────────────────────────────────────────
# 文本宽度估算 + 折行（无字体引擎，CJK≈1.0em / Latin≈0.55em 经验值）
# ────────────────────────────────────────────────

def _char_w(ch, fs):
    o = ord(ch)
    if o >= 0x2E80 or 0x3000 <= o <= 0x303F or 0xFF00 <= o <= 0xFFEF:
        return fs * 1.0  # CJK / 全角
    if ch in "iIl.,:;'!|()[]":
        return fs * 0.30
    if ch.isdigit() or ch.isupper():
        return fs * 0.60
    if ch == " ":
        return fs * 0.30
    return fs * 0.52


def _text_w(s, fs):
    return sum(_char_w(c, fs) for c in str(s))


def _wrap(text, fs, max_w, max_lines):
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if not text:
        return []
    lines, cur = [], ""
    for ch in text:
        if _text_w(cur + ch, fs) > max_w and cur:
            lines.append(cur)
            cur = ch
            if len(lines) >= max_lines:
                break
        else:
            cur += ch
    if cur and len(lines) < max_lines:
        lines.append(cur)
    if len(lines) >= max_lines and _text_w(text, fs) > _text_w("".join(lines), fs):
        last = lines[-1]
        while last and _text_w(last + "…", fs) > max_w:
            last = last[:-1]
        lines[-1] = (last + "…") if last else "…"
    return lines


def _fit_lines(text, max_w, max_lines, start_fs, min_fs):
    for fs in range(start_fs, min_fs - 1, -2):
        lines = _wrap(text, fs, max_w, max_lines)
        if lines and len(lines) <= max_lines and all(_text_w(l, fs) <= max_w for l in lines):
            return fs, lines
    return min_fs, _wrap(text, min_fs, max_w, max_lines) or [str(text)]


# ────────────────────────────────────────────────
# 真实序列归一
# ────────────────────────────────────────────────

def _safe_float(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(value):
        return float(value)
    if isinstance(value, str):
        t = value.strip().replace(",", "")
        try:
            return float(t) if t else None
        except ValueError:
            return None
    return None


def _coerce_series(value):
    if value is None:
        return []
    if isinstance(value, dict):
        for key in ("points", "series", "data", "values"):
            pts = _coerce_series(value.get(key))
            if pts:
                return pts
        dates = value.get("dates") or value.get("x") or value.get("labels")
        vals = value.get("values") or value.get("y")
        if isinstance(dates, list) and isinstance(vals, list):
            if vals and isinstance(vals[0], list):
                vals = vals[0]
            return _coerce_series([[dates[i], vals[i]] for i in range(min(len(dates), len(vals)))])
        return []
    if not isinstance(value, list):
        return []
    pts = []
    for idx, item in enumerate(value):
        x, y = idx, None
        if isinstance(item, dict):
            x = item.get("x", item.get("date", item.get("time", item.get("label", idx))))
            for key in ("y", "value", "close", "price", "score"):
                y = _safe_float(item.get(key))
                if y is not None:
                    break
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            x, y = item[0], _safe_float(item[1])
        else:
            y = _safe_float(item)
        if y is not None:
            pts.append({"x": str(x), "y": y})
    return pts[-260:]  # 支持长周期（约一年交易日）到最新日期的曲线


def _series_from_params(params):
    for key in ("series", "chart_series", "preview_series", "chart_data"):
        pts = _coerce_series(params.get(key))
        if pts:
            return pts
    return []


def _format_axis_label(label):
    text = str(label or "")
    if re.fullmatch(r"\d{8}", text):
        return text[4:6] + "-" + text[6:8]
    if len(text) > 8:
        return text[-8:]
    return text


# ────────────────────────────────────────────────
# SVG 拼装
# ────────────────────────────────────────────────

def _rect(x, y, w, h, fill, rx=0, stroke=None, sw=1):
    s = f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}"'
    if rx:
        s += f' rx="{rx}" ry="{rx}"'
    s += f' fill="{fill}"'
    if stroke:
        s += f' stroke="{stroke}" stroke-width="{sw}"'
    return s + "/>"


def _text(x, y, text, fs, fill, *, bold=False, anchor="start"):
    weight = "700" if bold else "400"
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-family={_q(FONT_STACK)} '
            f'font-size="{fs}" font-weight="{weight}" fill="{fill}" '
            f'text-anchor="{anchor}">{_esc(str(text))}</text>')


def _q(v):
    return '"' + str(v).replace('"', "'") + '"'


def _logo_data_uri(params):
    cands = []
    for key in ("logo_file", "brand_logo_file"):
        v = params.get(key)
        if isinstance(v, str) and v.strip():
            cands.append(v.strip())
    cands += [
        r"D:\project\quantbuddy-web\public\logo-quantbuddy-white.png",
        r"D:\project\qb-codex-workspace\quantbuddy-web\public\logo-quantbuddy-white.png",
        os.path.join(C.SKILL_ROOT, "assets", "logo-quantbuddy-white.png"),
    ]
    for p in cands:
        p = p if os.path.isabs(p) else os.path.join(C.SKILL_ROOT, p)
        if os.path.exists(p):
            try:
                with open(p, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode("ascii")
                return "data:image/png;base64," + b64
            except Exception:
                continue
    return None


def _chart_svg(points, box):
    """右侧图表：白卡 + 浅网格 + 蓝线 + 浅蓝填充 + 红涨/绿跌收尾点。"""
    x0, y0, x1, y1 = box
    out = [_rect(x0, y0, x1 - x0, y1 - y0, SURFACE, rx=14, stroke=BORDER, sw=1)]
    px0, py0, px1, py1 = x0 + 44, y0 + 30, x1 - 70, y1 - 46
    for i in range(6):
        gx = px0 + i * (px1 - px0) / 5
        out.append(f'<line x1="{gx:.1f}" y1="{py0:.1f}" x2="{gx:.1f}" y2="{py1:.1f}" stroke="{GRID}" stroke-width="1"/>')
        gy = py0 + i * (py1 - py0) / 5
        out.append(f'<line x1="{px0:.1f}" y1="{gy:.1f}" x2="{px1:.1f}" y2="{gy:.1f}" stroke="{GRID}" stroke-width="1"/>')

    if len(points) < 2:
        out.append(_text((x0 + x1) / 2, (y0 + y1) / 2, "缺少真实曲线数据", 18, MUTED, anchor="middle"))
        return "".join(out), False

    vals = [p["y"] for p in points]
    mn, mx = min(vals), max(vals)
    if mx == mn:
        mx += 1
        mn -= 1
    pad = (mx - mn) * 0.08
    mn -= pad
    mx += pad
    coords = []
    n = len(points)
    for i, p in enumerate(points):
        x = px0 + i * (px1 - px0) / max(1, n - 1)
        y = py1 - (p["y"] - mn) / (mx - mn) * (py1 - py0)
        coords.append((x, y))
    pts_attr = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
    area_attr = f"{coords[0][0]:.1f},{py1:.1f} " + pts_attr + f" {coords[-1][0]:.1f},{py1:.1f}"
    out.append(f'<polygon points="{area_attr}" fill="{BLUE_SOFT}"/>')
    out.append(f'<polyline points="{pts_attr}" fill="none" stroke="{BLUE}" stroke-width="3" '
               f'stroke-linejoin="round" stroke-linecap="round"/>')

    rose = vals[-1] >= vals[0]
    end_color = UP if rose else DOWN
    lx, ly = coords[-1]
    out.append(f'<line x1="{lx:.1f}" y1="{py0:.1f}" x2="{lx:.1f}" y2="{py1:.1f}" stroke="{BORDER_STRONG}" stroke-width="1"/>')
    out.append(f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="7" fill="{SURFACE}" stroke="{end_color}" stroke-width="3"/>')

    for idx, val in enumerate((mx, (mx + mn) / 2, mn)):
        label = f"{val:.2f}".rstrip("0").rstrip(".")
        yy = [py0, (py0 + py1) / 2, py1][idx] + 4
        out.append(_text(px1 + 12, yy, label, 14, MUTED))
    out.append(_text(px0, py1 + 22, _format_axis_label(points[0]["x"]), 14, MUTED))
    out.append(_text((px0 + px1) / 2, py1 + 22, _format_axis_label(points[n // 2]["x"]), 14, MUTED, anchor="middle"))
    out.append(_text(px1, py1 + 22, _format_axis_label(points[-1]["x"]), 14, MUTED, anchor="end"))
    return "".join(out), True


def _fullbleed_svg(params):
    """全幅裸图风：整张就是真实数据曲线，无品牌无标题（标题由官网卡片在图外展示）。"""
    points = _series_from_params(params)
    raw_cat = (params.get("template_type") or params.get("category")
               or _variant_from_text(" ".join([str(params.get("title") or ""),
                                                str(params.get("subtitle") or "")])))
    category = _display_category(raw_cat)

    el = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" '
          f'viewBox="0 0 {WIDTH} {HEIGHT}">']
    el.append('<defs><linearGradient id="area" x1="0" y1="0" x2="0" y2="1">'
              f'<stop offset="0" stop-color="{BLUE}" stop-opacity="0.22"/>'
              f'<stop offset="1" stop-color="{BLUE}" stop-opacity="0.02"/>'
              '</linearGradient></defs>')
    el.append(_rect(0, 0, WIDTH, HEIGHT, SURFACE))
    el.append(_rect(0.5, 0.5, WIDTH - 1, HEIGHT - 1, "none", stroke=BORDER, sw=1))

    px0, py0, px1, py1 = 64, 60, 1118, 600
    if len(points) < 2:
        el.append(_text(WIDTH / 2, HEIGHT / 2, "缺少真实曲线数据", 20, MUTED, anchor="middle"))
        el.append("</svg>")
        return "".join(el), category, "missing"

    vals = [p["y"] for p in points]
    mn, mx = min(vals), max(vals)
    if mx == mn:
        mx += 1
        mn -= 1
    pad = (mx - mn) * 0.10
    mn -= pad
    mx += pad

    # 水平网格 + 右侧数值刻度
    for i in range(5):
        gy = py0 + i * (py1 - py0) / 4
        el.append(f'<line x1="{px0}" y1="{gy:.1f}" x2="{px1}" y2="{gy:.1f}" stroke="{GRID}" stroke-width="1"/>')
        val = mx - i * (mx - mn) / 4
        label = f"{val:.2f}".rstrip("0").rstrip(".")
        el.append(_text(px1 + 14, gy + 5, label, 15, MUTED))

    n = len(points)
    coords = []
    for i, p in enumerate(points):
        x = px0 + i * (px1 - px0) / max(1, n - 1)
        y = py1 - (p["y"] - mn) / (mx - mn) * (py1 - py0)
        coords.append((x, y))
    pts_attr = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
    area_attr = f"{coords[0][0]:.1f},{py1:.1f} " + pts_attr + f" {coords[-1][0]:.1f},{py1:.1f}"
    el.append(f'<polygon points="{area_attr}" fill="url(#area)"/>')
    el.append(f'<polyline points="{pts_attr}" fill="none" stroke="{BLUE}" stroke-width="3" '
              f'stroke-linejoin="round" stroke-linecap="round"/>')

    rose = vals[-1] >= vals[0]
    end_color = UP if rose else DOWN
    lx, ly = coords[-1]
    el.append(f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="8" fill="{SURFACE}" stroke="{end_color}" stroke-width="3"/>')
    last_label = f"{vals[-1]:.2f}".rstrip("0").rstrip(".")
    el.append(_text(lx - 16, ly - 14, last_label, 20, end_color, bold=True, anchor="end"))

    # 底部日期刻度（约 5 个，覆盖整段周期到最新日期）
    k = 4
    for i in range(k + 1):
        idx = int(round(i * (n - 1) / k))
        x = px0 + idx * (px1 - px0) / max(1, n - 1)
        anchor = "start" if i == 0 else ("end" if i == k else "middle")
        el.append(_text(x, py1 + 30, _format_axis_label(points[idx]["x"]), 15, MUTED, anchor=anchor))

    el.append("</svg>")
    return "".join(el), category, "series"


def build_cover_svg(params):
    """默认全幅裸图风；style=poster 时回到「左文字+右图」品牌海报。"""
    style = str(params.get("style") or params.get("cover_style") or "chart").lower()
    if style in ("poster", "branded", "split"):
        return _poster_svg(params)
    return _fullbleed_svg(params)


def _poster_svg(params):
    title = str(params.get("title") or "QuantBuddy 看板")
    display_title = str(params.get("cover_title") or params.get("template_title") or title)
    template = str(params.get("template") or params.get("page_type") or "公共模板")
    subtitle = str(params.get("subtitle") or params.get("description") or "数据自动更新的可分享量化看板")
    raw_cat = (params.get("template_type") or params.get("category")
               or _variant_from_text(" ".join([title, template, subtitle])))
    category = _display_category(raw_cat)
    mode_label = str(params.get("data_mode") or "实时取数")
    tags = [str(t).strip() for t in (params.get("tags") or []) if str(t).strip()][:3] or ["公共模板", "可复用"]
    points = _series_from_params(params)
    asof = datetime.datetime.now().strftime("%Y-%m-%d")
    chart_used = bool(points)

    el = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" '
          f'viewBox="0 0 {WIDTH} {HEIGHT}">']
    el.append(_rect(0, 0, WIDTH, HEIGHT, BG))
    el.append(_rect(0.5, 0.5, WIDTH - 1, HEIGHT - 1, "none", stroke=BORDER, sw=1))

    # 深色品牌栏 + 金下边框（呼应页面 .share-shell）
    el.append(_rect(0, 0, WIDTH, 90, INK))
    el.append(_rect(0, 90, WIDTH, 4, GOLD))
    logo = _logo_data_uri(params)
    if logo:
        el.append(f'<image href="{logo}" x="54" y="22" width="230" height="46" '
                  f'preserveAspectRatio="xMinYMid meet"/>')
    else:
        el.append(_text(54, 58, "QuantBuddy", 30, SURFACE, bold=True))
    el.append(_text(WIDTH - 54, 57, "quantbuddy.cn", 19, GOLD_SOFT, bold=True, anchor="end"))

    # 左：eyebrow（金点 + 中文分类）
    left = 72
    el.append(f'<circle cx="{left + 6}" cy="142" r="6" fill="{GOLD}"/>')
    el.append(_text(left + 22, 149, category, 22, MUTED, bold=True))

    # 标题（自适应 1~2 行，偏大以填充上部）
    t_fs, t_lines = _fit_lines(display_title, 440, 2, 66, 40)
    ty = 196 if len(t_lines) > 1 else 214
    step = int(t_fs * 1.16)
    for line in t_lines:
        el.append(_text(left, ty, line, t_fs, INK, bold=True))
        ty += step
    # 副标题
    s_fs, s_lines = _fit_lines(subtitle, 432, 2, 23, 16)
    sy = ty + 6
    for line in s_lines:
        el.append(_text(left, sy, line, s_fs, MUTED))
        sy += int(s_fs * 1.5)

    # 细分隔线：给左栏下半部分一个锚，压掉中部大留白
    el.append(_rect(left, 372, 404, 1, BORDER))

    # 左下信息卡（更高更宽、间距更大，整体下压填满左栏）
    def info_card(y, label, value, accent):
        w, h = 404, 48
        el.append(_rect(left, y, w, h, SURFACE, rx=10, stroke=BORDER, sw=1))
        el.append(_rect(left, y + 8, 4, h - 16, accent, rx=2))
        el.append(_text(left + 20, y + 30, label, 16, MUTED))
        el.append(_text(left + 20 + _text_w(label, 16) + 14, y + 30, value, 18, INK, bold=True))

    info_card(398, "模板类型", category, GOLD)
    info_card(458, "数据模式", mode_label, BLUE)

    # tags
    cx = left
    for tag in tags:
        w = _text_w(tag, 15) + 30
        el.append(_rect(cx, 530, w, 36, SURFACE, rx=18, stroke=BORDER_STRONG, sw=1))
        el.append(_text(cx + 15, 553, tag, 15, MUTED))
        cx += w + 10

    # 右：图表卡（伪投影 + 卡片，整体放大、贴近上下边以减少右侧留白）
    card = (512, 126, 1148, 566)
    el.append(_rect(card[0] + 4, card[1] + 6, card[2] - card[0], card[3] - card[1], "#e0e7f0", rx=14))
    chart_markup, chart_used = _chart_svg(points, card)
    el.append(chart_markup)

    # 底部信息行
    fy = 612
    el.append(_rect(left, fy - 14, WIDTH - 54 - left, 1, BORDER))
    el.append(_rect(left, fy + 2, 10, 12, GOLD))
    foot = f"数据更新 {asof}  ·  实时取数 · 公共模板"
    el.append(_text(left + 20, fy + 14, foot, 16, MUTED))

    el.append("</svg>")
    return "".join(el), category, ("series" if chart_used else "missing")


def _wrap_html(svg):
    return ("<!doctype html><html><head><meta charset='utf-8'>"
            "<style>*{margin:0;padding:0}html,body{width:" + str(WIDTH) + "px;height:"
            + str(HEIGHT) + "px;overflow:hidden;background:" + BG + "}</style></head>"
            "<body>" + svg + "</body></html>")


# ────────────────────────────────────────────────
# 栅格化：系统 Edge / Chrome 无头
# ────────────────────────────────────────────────

def _find_browser():
    env = os.environ.get("QB_VIEW_CHROME", "").strip()
    if env and os.path.exists(env):
        return env
    cands = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    ]
    for c in cands:
        if os.path.exists(c):
            return c
    for name in ("msedge", "chrome", "chromium", "google-chrome", "chromium-browser", "brave"):
        p = shutil.which(name)
        if p:
            return p
    return None


def _rasterize(browser, html_path, out_png, timeout=60):
    url = pathlib.Path(html_path).resolve().as_uri()
    for headless in ("--headless=new", "--headless"):
        with tempfile.TemporaryDirectory(prefix="qb_cover_") as ud:
            args = [
                browser, headless,
                f"--screenshot={out_png}",
                f"--window-size={WIDTH},{HEIGHT}",
                "--force-device-scale-factor=1",
                "--hide-scrollbars", "--disable-gpu", "--no-sandbox",
                "--no-first-run", "--no-default-browser-check",
                "--disable-extensions", "--disable-background-networking",
                f"--user-data-dir={ud}",
                url,
            ]
            try:
                subprocess.run(args, capture_output=True, timeout=timeout)
            except (subprocess.TimeoutExpired, OSError):
                continue
            if os.path.exists(out_png) and os.path.getsize(out_png) > 1000:
                return True
    return False


def _png_dims(path):
    """纯 Python 读 PNG IHDR 宽高，校验确实是张图（不依赖 Pillow）。"""
    try:
        with open(path, "rb") as f:
            head = f.read(24)
        if len(head) >= 24 and head[:8] == b"\x89PNG\r\n\x1a\n":
            import struct
            return struct.unpack(">II", head[16:24])
    except Exception:
        pass
    return None


def capture_page_cover(cover_html, out_png, height, timeout=90):
    """用系统 Edge/Chrome 无头，把「封面模式页」cover_html 截成整页 PNG。

    height=按 panel 估算的内容高度（=窗口高度）。Edge 只截视口，所以靠窗口高度拿到整页。
    成功返回 out_png 路径；无浏览器/失败返回 None。不依赖 Pillow。
    """
    browser = _find_browser()
    if not browser or not cover_html or not os.path.exists(cover_html):
        return None
    url = pathlib.Path(cover_html).resolve().as_uri()
    h = max(700, min(5000, int(height or 1600)))
    out_png = os.path.abspath(out_png)  # Edge 对相对 --screenshot 路径会静默失败，必须绝对路径
    os.makedirs(os.path.dirname(out_png) or ".", exist_ok=True)
    for headless in ("--headless=new", "--headless"):
        with tempfile.TemporaryDirectory(prefix="qb_pagecover_") as ud:
            args = [
                browser, headless,
                f"--screenshot={out_png}",
                f"--window-size={WIDTH},{h}",
                "--force-device-scale-factor=1",
                "--hide-scrollbars", "--disable-gpu", "--no-sandbox",
                "--no-first-run", "--no-default-browser-check",
                "--disable-extensions",
                f"--user-data-dir={ud}",
                url,
            ]
            try:
                subprocess.run(args, capture_output=True, timeout=timeout)
            except (subprocess.TimeoutExpired, OSError):
                continue
            if os.path.exists(out_png) and os.path.getsize(out_png) > 2000 and _png_dims(out_png):
                return out_png
    return None


def _find_cjk_font():
    cands = [
        r"C:\Windows\Fonts\simhei.ttf", r"C:\Windows\Fonts\msyh.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/source-han-sans/SourceHanSansSC-Regular.otf",
    ]
    for p in cands:
        if os.path.exists(p):
            return p
    return None


def _svg_to_png_python(svg_path, png_path):
    """无浏览器时的纯 Python SVG→PNG 兜底：依次尝试 cairosvg / svglib(+CJK 字体注册)。

    需要对应库已安装（pip 即可，无强依赖）；都没有则返回 None，调用方保留 SVG。
    """
    # 1) cairosvg：对内联 data:URI logo 与系统字体（含 CJK）支持最好。
    try:
        import cairosvg
        cairosvg.svg2png(url=svg_path, write_to=png_path,
                         output_width=WIDTH, output_height=HEIGHT)
        if os.path.exists(png_path) and os.path.getsize(png_path) > 1000:
            return "cairosvg"
    except Exception:
        pass
    # 2) svglib + reportlab(+rlPyCairo)：需要一个含中英文的 CJK 字体，否则中文渲染成方块。
    #    svglib 不会把我们的 font-family 列表解析到注册字体，所以这里直接**强制**把图里
    #    所有文字节点的字体改成注册好的 CJK 字体（simhei/Noto 等都含 Latin，视觉无碍）。
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.graphics import renderPM
        from reportlab.graphics.shapes import String
        from svglib.svglib import svg2rlg
        cjk = _find_cjk_font()
        if not (cjk and cjk.lower().endswith((".ttf", ".otf"))):
            return None  # 没有可注册的 CJK 字体就别出方块 PNG，保留 SVG 更好
        pdfmetrics.registerFont(TTFont("QB-CJK", cjk))
        def _force_font(node):
            for child in getattr(node, "contents", None) or []:
                if isinstance(child, String):
                    child.fontName = "QB-CJK"
                _force_font(child)

        def _draw_with_svglib(path):
            drawing = svg2rlg(path)
            if drawing is None:
                return False
            _force_font(drawing)
            renderPM.drawToFile(drawing, png_path, fmt="PNG", dpi=96)
            return os.path.exists(png_path) and os.path.getsize(png_path) > 1000

        try:
            ok = _draw_with_svglib(svg_path)
        except Exception:
            # svglib/reportlab may fail on SVG gradients. Keep the browser path fully
            # featured, but degrade the pure-Python fallback area fill to a solid tint.
            try:
                with open(svg_path, "r", encoding="utf-8") as f:
                    raw_svg = f.read()
                fallback_svg = re.sub(r"<defs>.*?</defs>", "", raw_svg, flags=re.S)
                fallback_svg = fallback_svg.replace('fill="url(#area)"', f'fill="{BLUE_SOFT}"')
                tmp_svg = svg_path + ".svglib.svg"
                with open(tmp_svg, "w", encoding="utf-8") as f:
                    f.write(fallback_svg)
                ok = _draw_with_svglib(tmp_svg)
            finally:
                try:
                    os.remove(svg_path + ".svglib.svg")
                except OSError:
                    pass
        if not ok:
            return None
        if os.path.exists(png_path) and os.path.getsize(png_path) > 1000:
            return "svglib"
    except Exception:
        pass
    return None


def render_cover(params):
    out_file = _resolve_out_file(params)
    base, _ext = os.path.splitext(out_file)
    svg_path = base + ".svg"
    html_path = base + ".cover.html"
    png_path = base + ".png"
    os.makedirs(os.path.dirname(out_file) or ".", exist_ok=True)

    try:
        svg, category, chart_source = build_cover_svg(params)
    except Exception as exc:
        return {"code": 1, "message": f"SVG 拼装失败: {exc}",
                "thumbnail_generation_status": "failed"}

    with open(svg_path, "w", encoding="utf-8") as f:
        f.write(svg)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(_wrap_html(svg))

    # 栅格化降级链：系统浏览器无头 → 纯 Python(cairosvg/svglib) → 裸 SVG。
    browser = _find_browser()
    backend = None
    out = svg_path
    if browser and _rasterize(browser, html_path, png_path):
        backend = "edge" if ("edge" in browser.lower() or "msedge" in browser.lower()) else "chrome"
        out = png_path
    else:
        py = _svg_to_png_python(svg_path, png_path)
        if py:
            backend = py
            out = png_path
        else:
            backend = "svg"

    return {
        "code": 0,
        "skipped": False,
        "out_file": out,
        "svg_file": svg_path,
        "html_file": html_path,
        "width": WIDTH,
        "height": HEIGHT,
        "size": os.path.getsize(out) if os.path.exists(out) else 0,
        "style": "quantbuddy-template-light",
        "category": category,
        "chart_source": chart_source,
        "real_chart_used": chart_source == "series",
        "rasterizer": backend,
        "browser": browser,
        "thumbnail_generation_status": "generated",
    }


def main():
    params = C.read_params(sys.argv[1:], env_var="RT_PARAMS")
    try:
        result = render_cover(params)
    except Exception as exc:
        result = {"code": 1, "message": str(exc), "thumbnail_generation_status": "failed"}
    C.emit(result, out_name="cover_out.txt")
    sys.exit(0 if isinstance(result, dict) and result.get("code") in (0, 2) else 1)


if __name__ == "__main__":
    main()
