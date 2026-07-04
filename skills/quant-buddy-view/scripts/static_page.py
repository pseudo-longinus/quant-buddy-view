#!/usr/bin/env python3
r"""
静态页托管客户端 —— 把一份自包含 HTML 看板上传到对象存储，得到公开可分享链接。

对接接口文档：见 skill_server docs「静态页托管」对外接口文档。
工具说明文档：tools/static_page.md

静态页子命令（除直连 URL 验收外需 API Key）：
    upload     上传 HTML，返回 page_id + 公开 url
    update     替换已有页面内容（URL / page_id 不变，已分享链接照常可用）
    download   取回已发布页面的 HTML（再编辑用）：服务端鉴权返回 url，脚本直连 OSS 下载
    list       列出我的页面
    revoke     撤销页面（删对象 + 标记失效，链接立即 404）
    thumbnail  给页面设置 / 替换缩略图（纯展示封面，直传 PNG/JPG，独立于 HTML 上传）
    tags       查询 upload/update 可用标签（scene 场景 / paradigm 范式；recommend 仅后台维护）
    publish_community    将自己的 active 普通页发布到社区（内部受控打 recommend:社区 标签）
    unpublish_community  取消社区发布（移除固定 recommend:社区 标签）
    templates  列出官方精选页面（后台 recommend:官方精选 标签口径）
    template   官方精选详情：标题/说明/缩略图/关联公式包 + 公开下载链接（拿来克隆复用）
    update_template  官方精选/旧模板安全改写：metadata 复查后走 updateTemplate
    retrofit_card_runtime  为已发布模板重建独立 card runtime artifact，可原链接写回
    verify_card_runtime  批量快速验收独立 card runtime artifact（下载 HTML + required_outputs + 独立 hydrate）

权限 / 权责（is_test 内部互通）：归属由 api_key（Bearer）认定。
  · 自己的页面（upload/update/download/list/revoke/thumbnail）：默认只能操作本人页面；
    is_test=true 的用户可 download / update / thumbnail 其他 is_test 用户的页面、并用 list 的
    scope=test_all 列出全部 test 用户页面。对普通（非 is_test）用户的页面一律 FORBIDDEN。
  · 官方精选（templates/template）：浏览 / 复制对**全体登录用户**开放，发现口径是后台
    推荐标签 recommend:官方精选；不再要求 is_template=true 或 template_status=published。
  · 官方精选标签、旧模板元数据、上下线、删除、把某个用户页转成旧公共模板都属于后台写操作，
    本 skill 侧默认只做「读取 + 复用」官方精选。
  · update_template 只作为已转 published template / 官方精选页需要保留原链接时的
    安全维护 helper；写回前必须复查 metadata，避免覆盖他人更新。

参数传递（规避 PowerShell GBK 截断）：优先级 SP_PARAMS 环境变量 > @file > 命令行 JSON > stdin

upload 参数：
    {
      "html":        "HTML 全文（与 html_file 二选一）",
      "html_file":   "本地 HTML 文件路径（与 html 二选一；常用 build_dashboard 的产物）",
      "title":       "可选，不传则服务端从 <title> 抽取",
      "description": "可选，页面说明（≤1000 字，列表/详情展示用）",
      "ttl_days":    "可选，默认 365",
      "thumbnail_file": "可选，本地 PNG/JPG；HTML 上传成功后再设封面，失败只返回 warning",
      "scene_tags":    "可选，场景标签（数组/逗号串/单值）；只能选已有，查无报 SCENE_TAG_NOT_FOUND",
      "paradigm_tags": "可选，范式标签（数组/逗号串/单值）；可选已有或现写新名自动入池(source=user)",
      "verify_cover_card": "可选 true；上传前验收默认页和 ?cover=1 宽宝活卡，失败不上传",
      "verify_card_runtime": "可选 true；上传前只验收 card runtime artifact，失败不上传",
      "cover_card_url": "可选，模板库 live iframe URL",
      "has_cover_card": "可选，模板库是否展示 live card"
    }
    标签：推荐标签仅后台维护，本脚本不暴露；范式标签现写即进共享池。
    先用 tags 子命令查询可用场景/范式：python scripts/static_page.py tags
update 参数：page_id 必填；title / description / ttl_days / scene_tags / paradigm_tags /
    cover_card_url / has_cover_card / verify_cover_card / verify_card_runtime 仅在传了才改
    （description 传空串=清空，不传保留原值；标签字段传 [] 清空、不传保留原标签）。
    可同样传 thumbnail_file，HTML 更新成功后再替换封面；缩略图失败不回滚 HTML。
download 参数：
    {
      "page_id":  "要下载的页面（与 url 二选一）",
      "url":      "页面公开链接（与 page_id 二选一）",
      "save":     "可选，落盘路径（相对则相对 skill 根）；不传则把 html 直接放进返回 JSON"
    }
    下载字节直连 OSS（public-read），不经服务端 → 不占服务端带宽。
thumbnail 参数：
    {
      "page_id":    "要设置缩略图的页面（必填）",
      "image_file": "本地图片路径（PNG/JPG，≤2MB，相对则相对 skill 根）"
    }
    直传图片到 OSS（pages/thumbnails/{page_id}.png，public-read），仅回写页面的 thumbnail_url；
    不动 HTML、不占活跃页配额。缩略图只是「列表/详情/模板墙」的展示封面，纯展示用。
tags 参数：{ "tag_type":可选("scene" 或 "paradigm") }；不传则同时返回 scene_tags / paradigm_tags。
publish_community / unpublish_community 参数：{ "page_id":"page_xxx" }；仅 owner 可操作自己的 active 普通页。
templates 参数：{ "category":可选, "status":可选, "scene_tag_id":可选, "paradigm_tag_id":可选, "recommend_tag_id":可选, "page":1, "page_size":20 }；默认已限定 recommend:官方精选，recommend_tag_id 是额外叠加筛选。
template  参数：{ "template_id":"tpl_xxx" }（或 "page_id":"page_xxx" 二选一）
verify_card_runtime 参数：{ "page_ids":["page_xxx"], "require_browser":true, "timeout_sec":180 }

用法示例：
    python scripts/static_page.py upload '{"html_file":"output/pages/dash.html","title":"沪深300异动看板"}'
    python scripts/static_page.py update '{"page_id":"page_xxx","html_file":"output/pages/dash.html"}'
    python scripts/static_page.py download '{"page_id":"page_xxx","save":"output/pages/back.html"}'
    python scripts/static_page.py list '{"page":1,"page_size":20}'
    python scripts/static_page.py list '{"scope":"test_all"}'   # 仅 is_test：列出全部 test 用户页面
    python scripts/static_page.py revoke '{"page_id":"page_xxx"}'
    python scripts/static_page.py thumbnail '{"page_id":"page_xxx","image_file":"output/pages/cover.png"}'
    python scripts/static_page.py tags '{}'                                      # 查询可用场景/范式标签
    python scripts/static_page.py tags '{"tag_type":"scene"}'                 # 只查场景标签
    python scripts/static_page.py publish_community '{"page_id":"page_xxx"}'   # 发布到社区（全员可发现）
    python scripts/static_page.py unpublish_community '{"page_id":"page_xxx"}' # 取消社区发布
    python scripts/static_page.py templates '{"page":1,"page_size":20}'        # 浏览官方精选
    python scripts/static_page.py template  '{"template_id":"page_xxx"}'        # 官方精选详情/拿下载链接克隆
    python scripts/static_page.py verify_card_runtime '{"page_ids":["page_xxx","page_yyy"]}' # 快速批量验收 card artifact

输出：结果打印到 stdout（UTF-8），并写一份到临时目录 sp_out.txt。
"""

import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse as _up
import urllib.request
from datetime import datetime

import compile_bespoke_page as CB
import card_runtime_retrofit as CRT
import common as C

_PATH = {
    "upload":    "/skill/uploadStaticPage",
    "update":    "/skill/updateStaticPage",
    "download":  "/skill/getStaticPage",
    "list":      "/skill/listStaticPages",
    "revoke":    "/skill/revokeStaticPage",
    "thumbnail": "/skill/setPageThumbnail",
    "tags":      "/skill/listPageTags",
    "publish_community":   "/skill/publishStaticPageToCommunity",
    "unpublish_community": "/skill/unpublishStaticPageFromCommunity",
    "templates": "/skill/listTemplates",
    "template":  "/skill/getTemplate",
    "update_template": "/skill/updateTemplate",
}

_UPLOAD_TIMEOUT = 120
_DEFAULT_TIMEOUT = 60

# 服务端限制：单页 ≤ 2MB（这里只做一次本地早检，真正以服务端为准）
_MAX_HTML_BYTES = 2 * 1024 * 1024
# 缩略图上限（与服务端 setPageThumbnail 一致，2MB）
_MAX_THUMB_BYTES = 2 * 1024 * 1024
_SHARE_POSTER_VERSION = "snapshot-tall-v1"
_SHARE_SHELL_VERSION = "copy-link-v1"
_PACKAGE_ISSUE_RE = re.compile(
    r"formula[_ -]?package|package_id|signature|公式包|签名|查无|失效|无效|not[_ -]?found|invalid",
    re.I,
)


def _with_cover_query(url):
    if not url:
        return ""
    url = str(url)
    if "cover=" in url:
        return url
    sep = "&" if "?" in url else "?"
    return url + sep + "cover=1"


def _attach_cover_fields(out, *, base_url=None, params=None):
    """Normalize cover-card fields in service responses without hiding raw data."""
    if not isinstance(out, dict):
        return out
    params = params or {}
    explicit_url = params.get("cover_card_url")
    explicit_has = params.get("has_cover_card")
    if explicit_url and not out.get("cover_card_url"):
        out["cover_card_url"] = explicit_url
    elif out.get("has_cover_card") and not out.get("cover_card_url"):
        out["cover_card_url"] = _with_cover_query(base_url or out.get("url") or out.get("public_url") or out.get("download_url"))
    elif params.get("verify_cover_card") and base_url and not out.get("cover_card_url"):
        out["cover_card_url"] = _with_cover_query(base_url)

    if explicit_has is not None:
        out["has_cover_card"] = bool(explicit_has)
    elif out.get("cover_card_url"):
        out["has_cover_card"] = True
    else:
        out.setdefault("has_cover_card", False)
    return out


def _record_url(record):
    if not isinstance(record, dict):
        return ""
    return record.get("cover_card_url") or record.get("download_url") or record.get("public_url") or record.get("url") or ""


def _normalize_cover_response(out):
    if not isinstance(out, dict):
        return out
    _attach_cover_fields(out, base_url=_record_url(out))
    data = out.get("data")
    if isinstance(data, dict):
        _attach_cover_fields(data, base_url=_record_url(data))
        items = data.get("items")
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    _attach_cover_fields(item, base_url=_record_url(item))
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                _attach_cover_fields(item, base_url=_record_url(item))
    return out


def _template_record(out):
    if not isinstance(out, dict):
        return {}
    data = out.get("data")
    if isinstance(data, dict):
        for key in ("template", "item", "page"):
            if isinstance(data.get(key), dict):
                return data[key]
        return data
    return out

_SHELL_THEME_VARS = {
    "--qb-shell-bg",
    "--qb-shell-chrome-bg",
    "--qb-shell-header-bg",
    "--qb-shell-footer-bg",
    "--qb-shell-surface",
    "--qb-shell-panel",
    "--qb-shell-panel-2",
    "--qb-shell-line",
    "--qb-shell-ink",
    "--qb-shell-muted",
    "--qb-shell-dim",
    "--qb-shell-accent",
    "--qb-shell-accent-strong",
    "--qb-shell-green",
}


def _sub_count(pattern, repl, html, flags=re.S, count=0):
    html2, replaced = re.subn(pattern, repl, html, count=count, flags=flags)
    return html2, replaced


def _inject_before(pattern, insertion, html, flags=0):
    if insertion in html:
        return html, 0
    html2, count = re.subn(pattern, lambda m: insertion + "\n" + m.group(0), html, count=1, flags=flags)
    return html2, count


def _inject_after_body(insertion, html):
    if insertion in html:
        return html, 0
    html2, count = re.subn(
        r"<body\b[^>]*>",
        lambda m: m.group(0) + "\n" + insertion,
        html,
        count=1,
        flags=re.I,
    )
    return html2, count


def _hero_spacing_style():
    return """<style id="qb-retrofit-preserve-hero">
.share-card.qb-retrofit-qr-placeholder{visibility:hidden;min-height:171px;pointer-events:none}
</style>"""


def _script_inline(text):
    return "<script>\n" + text.strip() + "\n</script>"


def _shared_poster_js():
    return CB._read(os.path.join(CB.SHARED_DIR, "poster.js"))


def _shared_shell_js():
    return "\n".join([
        CB._read(os.path.join(CB.SHARED_DIR, "poster.js")).strip(),
        CB._read(os.path.join(CB.SHARED_DIR, "shell.js")).strip(),
    ])


def _share_runtime_is_current(html):
    return (
        "QB_SHARE_POSTER_VERSION" in html and _SHARE_POSTER_VERSION in html
        and "QB_SHARE_SHELL_VERSION" in html and _SHARE_SHELL_VERSION in html
    )


def _upgrade_share_poster_runtime(html):
    if _share_runtime_is_current(html):
        return html, 0, ""
    if "window.QBSharePoster" not in html and "window.QBShareShell" not in html:
        return html, 0, ""

    shared_js = _script_inline(_shared_shell_js())
    combined_re = (
        r"<script>\s*\(function\(\)\{.*?"
        r"window\.QBSharePoster\s*=.*?"
        r"window\.QBShareShell\s*=.*?"
        r"</script>"
    )
    html2, count = re.subn(combined_re, lambda _m: shared_js, html, count=1, flags=re.S)
    if count:
        return html2, count, "upgraded_share_runtime"

    poster_only = _script_inline(_shared_poster_js())
    html2, count = _inject_before(r"</body>", poster_only, html, flags=re.I)
    if count:
        return html2, count, "upgraded_share_poster"
    raise ValueError("公共页头页尾检查失败：无法升级分享海报运行时，HTML 缺少 </body>")


def _css_value(value):
    value = str(value or "").strip()
    if re.fullmatch(r"#[0-9a-fA-F]{3,8}", value):
        return value
    if re.fullmatch(r"rgba?\([0-9.,% ]+\)", value):
        return value
    if re.fullmatch(r"var\(--[a-zA-Z0-9_-]+\)", value):
        return value
    return ""


def _shell_theme_from_params(params):
    theme = params.get("theme") if isinstance(params.get("theme"), dict) else {}
    if not theme:
        return {}
    values = {}
    mapping = {
        "chrome_bg": "--qb-shell-chrome-bg",
        "bg": "--qb-shell-chrome-bg",
        "header_bg": "--qb-shell-header-bg",
        "footer_bg": "--qb-shell-footer-bg",
        "accent": "--qb-shell-accent",
        "accent_strong": "--qb-shell-accent-strong",
        "line": "--qb-shell-line",
        "ink": "--qb-shell-ink",
        "muted": "--qb-shell-muted",
    }
    for key, var_name in mapping.items():
        value = _css_value(theme.get(key))
        if value:
            values[var_name] = value
    return values


def _extract_existing_shell_theme(html):
    values = {}
    for name, value in re.findall(r"(--qb-shell-[a-z0-9-]+)\s*:\s*([^;{}]+)", html, flags=re.I):
        name = name.lower()
        if name in _SHELL_THEME_VARS:
            clean = _css_value(value)
            if clean:
                values[name] = clean
    return values


def _shell_theme_style(values):
    if not values:
        return ""
    lines = [f"  {name}: {values[name]};" for name in sorted(values)]
    return "<style id=\"qb-shell-theme\">\n:root {\n" + "\n".join(lines) + "\n}\n</style>"


def _install_shell_theme(html, params):
    if "id=\"qb-shell-theme\"" in html or "id='qb-shell-theme'" in html:
        return html, 0, ""
    explicit = _shell_theme_from_params(params)
    values = explicit or _extract_existing_shell_theme(html)
    style = _shell_theme_style(values)
    if not style:
        return html, 0, ""
    source = "inserted_shell_theme" if explicit else "preserved_shell_theme"
    token = "<!-- QB_SHARED_SHELL_CSS -->"
    if token in html:
        return html.replace(token, token + "\n" + style, 1), 1, source
    html, count = _inject_before(r"</head>", style, html, flags=re.I)
    return html, count, source


def _shell_bootstrap_script():
    return r"""<script id="qb-static-shell-guard">
(function(){
  if (window.__QB_STATIC_SHELL_GUARD__) return;
  window.__QB_STATIC_SHELL_GUARD__ = true;
  function text(v){ return String(v == null ? '' : v); }
  function summary(){
    if (window.BOOT && Array.isArray(BOOT.panels)) {
      var p = BOOT.panels.find(function(x){ return String(x.type || '').toLowerCase() === 'text'; });
      if (p && (p.text || p.content || p.description)) return text(p.text || p.content || p.description);
    }
    var hero = document.querySelector('header.share-shell h1, h1');
    return hero ? hero.innerText : (document.title || 'QuantBuddy 页面');
  }
  function posterData(){
    return {
      headline: document.title || 'QuantBuddy 页面',
      summary: summary(),
      metrics: [],
      sections: [],
      asof: (window.BOOT && BOOT.generatedAt) || ''
    };
  }
  async function refresh(){
    if (window.BOOT && BOOT.mode === 'live' && typeof window.fetchLive === 'function') return window.fetchLive();
    if (window.BOOT && typeof window.renderAll === 'function') return window.renderAll(BOOT.outputs || {});
  }
  document.addEventListener('DOMContentLoaded', function(){
    if (!window.QBShareShell || window.__QB_STATIC_SHELL_INIT__) return;
    window.__QB_STATIC_SHELL_INIT__ = true;
    QBShareShell.init({
      templateName: document.title || 'QuantBuddy 页面',
      title: function(){ return document.title || 'QuantBuddy 页面'; },
      subtitle: summary,
      asof: function(){ return (window.BOOT && BOOT.generatedAt) || ''; },
      onRefresh: refresh,
      getPosterData: posterData
    });
  });
})();
</script>"""


def _read_html(params):
    """从 html 或 html_file 取出 HTML 文本，返回 (html, err)。"""
    html = params.get("html")
    if not html and params.get("html_file"):
        path = params["html_file"]
        if not os.path.isabs(path):
            path = os.path.join(C.SKILL_ROOT, path)
        if not os.path.exists(path):
            return None, {"code": 1, "message": f"html_file 不存在: {path}"}
        with open(path, "r", encoding="utf-8-sig") as f:
            html = f.read()
    if not html:
        return None, {"code": 1, "message": "upload 需要 html 或 html_file 之一"}
    return html, None


def _thumbnail_file_from_params(params):
    """Return optional thumbnail path from upload/update params."""
    for key in ("thumbnail_file", "thumbnail_image", "thumbnail_path"):
        value = params.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    value = params.get("thumbnail")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _result_message(out):
    if not isinstance(out, dict):
        return str(out)
    if out.get("message"):
        return str(out.get("message"))
    err = out.get("error")
    if isinstance(err, dict):
        return str(err.get("message") or err.get("code") or err)
    if err:
        return str(err)
    return json.dumps(out, ensure_ascii=False)[:500]


def _append_warning(out, warning):
    warnings = out.get("warnings")
    if not isinstance(warnings, list):
        warnings = []
    warnings.append(warning)
    out["warnings"] = warnings


def _attach_thumbnail_if_requested(out, params):
    """Upload thumbnail after HTML publish succeeds; never fail the publish result."""
    thumb_file = _thumbnail_file_from_params(params)
    if not thumb_file or not isinstance(out, dict) or out.get("code") != 0:
        return out
    page_id = out.get("page_id") or params.get("page_id")
    if not page_id:
        out["thumbnail_warning"] = "HTML 已发布，但响应里缺少 page_id，无法设置缩略图"
        _append_warning(out, {"type": "thumbnail_upload_skipped", "message": out["thumbnail_warning"]})
        return out

    thumb = cmd_thumbnail({"page_id": page_id, "image_file": thumb_file})
    out["thumbnail_upload"] = thumb
    if isinstance(thumb, dict) and thumb.get("code") == 0:
        out["thumbnail_url"] = thumb.get("thumbnail_url") or out.get("thumbnail_url") or ""
        return out

    message = _result_message(thumb)
    out["thumbnail_warning"] = f"HTML 已发布，但缩略图上传失败：{message}"
    _append_warning(out, {
        "type": "thumbnail_upload_failed",
        "message": message,
        "thumbnail_file": thumb_file,
    })
    return out


def _run_verify(target, *, cover_card=False):
    script = os.path.join(C.SKILL_ROOT, "scripts", "verify_page.mjs")
    args = ["node", script, target, "--require-browser"]
    if cover_card:
        args.append("--cover-card")
    cp = subprocess.run(
        args,
        cwd=C.SKILL_ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=90,
    )
    raw = (cp.stdout or cp.stderr or "").strip()
    try:
        data = json.loads(raw)
    except Exception:
        data = {"code": cp.returncode, "message": raw[-1000:] or "verify_page 无输出"}
    data["_exit_code"] = cp.returncode
    return data


def _verify_cover_card_html(html):
    with tempfile.TemporaryDirectory(prefix="qb_cover_verify_") as td:
        path = os.path.join(td, "page.html")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(html)
        default_result = _run_verify(path, cover_card=False)
        if default_result.get("code") != 0:
            return {
                "ok": False,
                "stage": "default",
                "default": default_result,
                "message": "默认页面浏览器验收未通过",
            }
        cover_result = _run_verify(path + "?cover=1", cover_card=True)
        if cover_result.get("code") != 0:
            return {
                "ok": False,
                "stage": "cover",
                "default": default_result,
                "cover": cover_result,
                "message": "宽宝活卡浏览器验收未通过",
            }
        return {"ok": True, "default": default_result, "cover": cover_result}


def _maybe_verify_cover_card(html, params):
    if not params.get("verify_cover_card"):
        return None
    result = _verify_cover_card_html(html)
    if not result.get("ok"):
        return result
    return result


def _has_shared_header(html):
    return bool(re.search(r"<header\b[^>]*\bdata-qb-share-shell(?:\s|=|>)", html, flags=re.I))


def _has_shared_footer(html):
    return bool(re.search(r"<footer\b[^>]*\bdata-qb-share-shell-footer(?:\s|=|>)", html, flags=re.I))


def _has_shared_shell_css(html):
    return bool(re.search(r"\.qb-head\s*\{", html) and re.search(r"\.qb-footer\s*\{", html))


def _has_shared_modal(html):
    return bool(re.search(r"id=[\"']sharePosterModal[\"']", html, flags=re.I))


def _ensure_share_shell(html, params):
    """Preflight static-page HTML so published pages always carry the public shell."""
    if params.get("ensure_share_shell") is False:
        return html, {"checked": False, "skipped": True}

    actions = []

    html, n = _replace_old_body_qr(html, collapse=bool(params.get("collapse_qr_space")))
    if n:
        actions.append(f"cleaned_body_qr:{n}")

    html, n = _sub_count(
        r"<footer\b[^>]*class=[\"'][^\"']*\bsite-footer\b[^\"']*[\"'][^>]*>.*?</footer>",
        "",
        html,
        count=1,
    )
    if n:
        actions.append("removed_legacy_footer")

    html, n = _sub_count(
        r"\s*<script\b[^>]*src=[\"'][^\"']*(?:qrcode|QRCode)[^\"']*[\"'][^>]*>\s*</script>",
        "",
        html,
        flags=re.I,
    )
    if n:
        actions.append(f"removed_qrcode_script:{n}")

    html, n = _sub_count(
        r"\s*<div\b(?=[^>]*(?:id=[\"']qr[\"']|class=[\"'][^\"']*\bqr\b[^\"']*[\"']))[^>]*>[\s\S]*?手机扫码查看[\s\S]*?</div>",
        "",
        html,
        count=1,
    )
    if n:
        actions.append("removed_legacy_qr_div")

    html, n = _sub_count(
        r"\nfunction setupShareShell\(\) \{.*?\n\}\n\n(?=document\.addEventListener\('DOMContentLoaded')",
        "\n",
        html,
        count=1,
    )
    if n:
        actions.append("removed_legacy_setup")

    html, n = _sub_count(r"\s*setupShareShell\(\);\s*", "\n", html, flags=re.I)
    if n:
        actions.append(f"removed_legacy_setup_call:{n}")

    if not _has_shared_shell_css(html) and "<!-- QB_SHARED_SHELL_CSS -->" not in html:
        html, n = _inject_before(r"</head>", "<!-- QB_SHARED_SHELL_CSS -->", html, flags=re.I)
        if not n:
            raise ValueError("公共页头页尾检查失败：HTML 缺少 </head>，无法插入 share shell CSS")
        actions.append("inserted_shell_css")

    html, n, theme_action = _install_shell_theme(html, params)
    if n:
        actions.append(theme_action)

    if not _has_shared_header(html) and "<!-- QB_SHARED_SHELL_HEADER -->" not in html:
        html, n = _inject_after_body("<!-- QB_SHARED_SHELL_HEADER -->", html)
        if not n:
            raise ValueError("公共页头页尾检查失败：HTML 缺少 <body>，无法插入公共页头")
        actions.append("inserted_shell_header")

    if not _has_shared_footer(html) and "<!-- QB_SHARED_SHELL_FOOTER -->" not in html:
        html, n = _inject_before(r"</body>", "<!-- QB_SHARED_SHELL_FOOTER -->", html, flags=re.I)
        if not n:
            raise ValueError("公共页头页尾检查失败：HTML 缺少 </body>，无法插入公共页尾")
        actions.append("inserted_shell_footer")

    if not _has_shared_modal(html) and "<!-- QB_SHARED_SHELL_MODAL -->" not in html:
        html, n = _inject_before(r"</body>", "<!-- QB_SHARED_SHELL_MODAL -->", html, flags=re.I)
        if not n:
            raise ValueError("公共页头页尾检查失败：HTML 缺少 </body>，无法插入分享弹层")
        actions.append("inserted_shell_modal")

    if "QRMini" not in html and "<!-- QB_SHARED_QR_MINI -->" not in html:
        html, n = _inject_before(r"</body>", "<!-- QB_SHARED_QR_MINI -->", html, flags=re.I)
        if not n:
            raise ValueError("公共页头页尾检查失败：HTML 缺少 </body>，无法插入 QR 运行时")
        actions.append("inserted_qr_runtime")

    if "window.QBShareShell" not in html and "<!-- QB_SHARED_SHELL_JS -->" not in html:
        html, n = _inject_before(r"</body>", "<!-- QB_SHARED_SHELL_JS -->", html, flags=re.I)
        if not n:
            raise ValueError("公共页头页尾检查失败：HTML 缺少 </body>，无法插入 share shell JS")
        actions.append("inserted_shell_js")

    if "QBShareShell.init" not in html and "qb-static-shell-guard" not in html:
        html, n = _inject_before(r"</body>", _shell_bootstrap_script(), html, flags=re.I)
        if not n:
            raise ValueError("公共页头页尾检查失败：HTML 缺少 </body>，无法插入公共 shell 初始化脚本")
        actions.append("inserted_shell_bootstrap")

    html, n, runtime_action = _upgrade_share_poster_runtime(html)
    if n:
        actions.append(runtime_action)

    html = CB._compile(html, {"inline_qr_mini": True, "inline_data_kernel": True})
    problems = []
    if not _has_shared_header(html):
        problems.append("缺少公共页头 data-qb-share-shell")
    if not _has_shared_footer(html):
        problems.append("缺少公共页尾 data-qb-share-shell-footer")
    for token in ("手机扫码查看", "shareQrCanvas", "setupShareShell", "<footer class=\"site-footer\""):
        if token in html:
            problems.append(f"旧页面残留: {token}")
    if "QB_SHARED_" in html or "__QB_LOGO_SRC__" in html:
        problems.append("公共组件占位符未编译")
    if problems:
        raise ValueError("公共页头页尾检查失败：" + "；".join(problems))
    return html, {"checked": True, "actions": actions, "header": True, "footer": True}


def _replace_old_body_qr(html, collapse=False):
    share_card_repl = ""
    if not collapse:
        share_card_repl = '<aside class="share-card qb-retrofit-qr-placeholder" aria-hidden="true"></aside>'

    def is_legacy_qr_card(chunk):
        return bool(re.search(
            r"shareQrCanvas|手机扫码查看|\bqr-frame\b|\bqr-fallback\b|qrcode",
            chunk,
            flags=re.I,
        ))

    replaced = 0

    def replace_share_card(match):
        nonlocal replaced
        chunk = match.group(0)
        if replaced or not is_legacy_qr_card(chunk):
            return chunk
        replaced = 1
        return share_card_repl

    html = re.sub(
        r"\s*<aside\b[^>]*class=[\"'][^\"']*\bshare-card\b[^\"']*[\"'][^>]*>.*?</aside>",
        replace_share_card,
        html,
        flags=re.S | re.I,
    )
    count = replaced
    if count and share_card_repl:
        html, _ = _inject_before(r"</head>", _hero_spacing_style(), html, flags=re.I)
    html, extra = _sub_count(
        r"\s*<[^>]+id=[\"']shareQrCanvas[\"'][^>]*>.*?</[^>]+>",
        "",
        html,
        flags=re.S | re.I,
        count=1,
    )
    return html, count + extra


def _server_mentions_package_issue(out):
    if not isinstance(out, dict):
        return False
    try:
        text = json.dumps(out, ensure_ascii=False)
    except Exception:
        text = str(out)
    return bool(_PACKAGE_ISSUE_RE.search(text))


def _extract_package_credentials(html):
    pkg_re = re.compile(r'(?:["\']?(?:package_id|packageId)["\']?)\s*:\s*["\']([^"\']+)["\']')
    sig_re = re.compile(r'(?:["\']?signature["\']?)\s*:\s*["\']([^"\']+)["\']')
    pairs = []
    seen = set()
    for m in pkg_re.finditer(html or ""):
        pkg = m.group(1)
        window = html[max(0, m.start() - 500): min(len(html), m.end() + 1500)]
        sig_m = sig_re.search(window)
        if not sig_m:
            continue
        sig = sig_m.group(1)
        key = (pkg, sig)
        if key not in seen:
            seen.add(key)
            pairs.append({"package_id": pkg, "signature": sig})
    return pairs


def _package_runtime_check(endpoint, html, *, force=False, publish_out=None):
    if not force and not _server_mentions_package_issue(publish_out):
        return {
            "status": "not_verifiable_by_publish_key",
            "reason": "publish response did not indicate formula-package verification was needed",
        }
    creds = _extract_package_credentials(html)
    if not creds:
        return {
            "status": "not_verifiable_by_publish_key",
            "reason": "no package_id + signature pair found in page html",
        }

    import formula_package as FP
    packages = []
    all_ok = True
    for cred in creds:
        pkg = cred["package_id"]
        res = FP.query_package(endpoint, pkg, cred["signature"])
        ok = isinstance(res, dict) and res.get("code") == 0
        all_ok = all_ok and ok
        packages.append({
            "package_id": pkg,
            "ok": ok,
            "error": (res.get("error") or res.get("message")) if isinstance(res, dict) else str(res),
            "failures": res.get("failures") if isinstance(res, dict) else None,
        })
    return {
        "status": "query_with_signature_ok" if all_ok else "query_with_signature_failed",
        "packages": packages,
    }


def cmd_upload(params):
    cfg = C.load_config_require_key()
    endpoint, api_key = C.endpoint_of(cfg), cfg.get("api_key", "")

    html, err = _read_html(params)
    if err:
        return err
    try:
        html, shell_check = _ensure_share_shell(html, params)
    except ValueError as e:
        return {"code": 1, "message": str(e)}
    size = len(html.encode("utf-8"))
    if size > _MAX_HTML_BYTES:
        return {"code": 1, "message": f"HTML 体积 {size} 字节，超过单页上限 2MB（请精简内联数据/资源）"}
    head = html.lstrip()[:64].lower()
    if not (head.startswith("<!doctype html") or head.startswith("<html")):
        return {"code": 1, "message": "内容不是 HTML 文档（需以 <!doctype html> 或 <html> 开头）"}
    cover_verification = _maybe_verify_cover_card(html, params)
    if isinstance(cover_verification, dict) and not cover_verification.get("ok"):
        return {"code": 1, "message": cover_verification.get("message") or "宽宝活卡验收未通过", "cover_verification": cover_verification}
    card_runtime_verification = _maybe_verify_card_runtime(html, params)
    if isinstance(card_runtime_verification, dict) and not card_runtime_verification.get("ok"):
        return {
            "code": 1,
            "message": card_runtime_verification.get("message") or "card runtime artifact 验收未通过",
            "card_runtime_verification": card_runtime_verification,
        }

    body = {"html": html}
    for k in ("title", "description", "ttl_days", "scene_tags", "paradigm_tags", "cover_card_url", "has_cover_card"):
        if params.get(k) is not None:
            body[k] = params[k]
    if cover_verification and body.get("has_cover_card") is None:
        body["has_cover_card"] = True
    out = C.http_json("POST", C.api_url(endpoint, _PATH["upload"]),
                      C.headers(api_key), body, timeout=_UPLOAD_TIMEOUT)
    if isinstance(out, dict):
        out["share_shell"] = shell_check
        if cover_verification:
            out["cover_verification"] = cover_verification
            _attach_cover_fields(out, base_url=out.get("url"), params=params)
        if card_runtime_verification:
            out["card_runtime_verification"] = card_runtime_verification
        if out.get("code") == 0 or _server_mentions_package_issue(out):
            out["_package_runtime_check"] = _package_runtime_check(
                endpoint,
                html,
                force=bool(params.get("verify_packages")),
                publish_out=out,
            )
        out = _attach_thumbnail_if_requested(out, params)
    return out


def cmd_update(params):
    cfg = C.load_config_require_key()
    endpoint, api_key = C.endpoint_of(cfg), cfg.get("api_key", "")

    if not params.get("page_id"):
        return {"code": 1, "message": "update 需要 page_id（要替换哪个已发布页面）"}

    html, err = _read_html(params)
    if err:
        return err
    try:
        html, shell_check = _ensure_share_shell(html, params)
    except ValueError as e:
        return {"code": 1, "message": str(e)}
    size = len(html.encode("utf-8"))
    if size > _MAX_HTML_BYTES:
        return {"code": 1, "message": f"HTML 体积 {size} 字节，超过单页上限 2MB（请精简内联数据/资源）"}
    head = html.lstrip()[:64].lower()
    if not (head.startswith("<!doctype html") or head.startswith("<html")):
        return {"code": 1, "message": "内容不是 HTML 文档（需以 <!doctype html> 或 <html> 开头）"}
    cover_verification = _maybe_verify_cover_card(html, params)
    if isinstance(cover_verification, dict) and not cover_verification.get("ok"):
        return {"code": 1, "message": cover_verification.get("message") or "宽宝活卡验收未通过", "cover_verification": cover_verification}
    card_runtime_verification = _maybe_verify_card_runtime(html, params)
    if isinstance(card_runtime_verification, dict) and not card_runtime_verification.get("ok"):
        return {
            "code": 1,
            "message": card_runtime_verification.get("message") or "card runtime artifact 验收未通过",
            "card_runtime_verification": card_runtime_verification,
        }

    body = {"page_id": params["page_id"], "html": html}
    for k in ("title", "description", "ttl_days", "scene_tags", "paradigm_tags", "cover_card_url", "has_cover_card"):
        if params.get(k) is not None:
            body[k] = params[k]
    if cover_verification and body.get("has_cover_card") is None:
        body["has_cover_card"] = True
    out = C.http_json("POST", C.api_url(endpoint, _PATH["update"]),
                      C.headers(api_key), body, timeout=_UPLOAD_TIMEOUT)
    if isinstance(out, dict):
        out["share_shell"] = shell_check
        if cover_verification:
            out["cover_verification"] = cover_verification
            _attach_cover_fields(out, base_url=out.get("url") or params.get("url"), params=params)
        if card_runtime_verification:
            out["card_runtime_verification"] = card_runtime_verification
        if out.get("code") == 0 or _server_mentions_package_issue(out):
            out["_package_runtime_check"] = _package_runtime_check(
                endpoint,
                html,
                force=bool(params.get("verify_packages")),
                publish_out=out,
            )
        out = _attach_thumbnail_if_requested(out, params)
    return out

def _fetch_oss(url):
    """直连 OSS 拉取页面 HTML（public-read，无需鉴权），返回 (text, err)。"""
    req = urllib.request.Request(url, method="GET")
    try:
        with C._NO_PROXY_OPENER.open(req, timeout=_DEFAULT_TIMEOUT) as resp:
            return resp.read().decode("utf-8", errors="replace"), None
    except Exception as e:
        return None, {"code": 1, "message": f"从 OSS 下载失败: {e}", "url": url}


def cmd_download(params):
    cfg = C.load_config_require_key()
    endpoint, api_key = C.endpoint_of(cfg), cfg.get("api_key", "")

    if not params.get("page_id") and not params.get("url"):
        return {"code": 1, "message": "download 需要 page_id 或 url 之一"}

    # 1) 服务端鉴权 → 拿到公开 url + 元信息（不含字节）
    qs_pairs = [(k, params[k]) for k in ("page_id", "url") if params.get(k)]
    meta_url = C.api_url(endpoint, _PATH["download"]) + "?" + _up.urlencode(qs_pairs)
    meta = C.http_json("GET", meta_url, C.headers(api_key), timeout=_DEFAULT_TIMEOUT)
    if not (isinstance(meta, dict) and meta.get("code") == 0 and meta.get("url")):
        return meta  # 透传服务端错误（FORBIDDEN / PAGE_NOT_FOUND / NOT_ACTIVE 等）

    # 2) 客户端直连 OSS 下载 HTML（不经服务端，省带宽）
    html, err = _fetch_oss(meta["url"])
    if err:
        return err

    # 3) 校验完整性（与服务端记录的 sha256 比对）
    sha = hashlib.sha256(html.encode("utf-8")).hexdigest()
    sha_ok = (not meta.get("sha256")) or sha == meta.get("sha256")

    out = {
        "code": 0,
        "page_id": meta.get("page_id"),
        "owner": meta.get("owner"),
        "title": meta.get("title"),
        "description": meta.get("description"),
        "thumbnail_url": meta.get("thumbnail_url") or "",
        "url": meta.get("url"),
        "size": len(html.encode("utf-8")),
        "sha256": sha,
        "sha256_match": sha_ok,
        "is_live": bool(meta.get("is_live")),
        "package_ids": meta.get("package_ids") or [],
        "status": meta.get("status"),
        "community_status": meta.get("community_status") or "none",
        "scene_tags": meta.get("scene_tags") or [],
        "paradigm_tags": meta.get("paradigm_tags") or [],
        "recommend_tags": meta.get("recommend_tags") or [],
        "expires_at": meta.get("expires_at"),
        "cover_card_url": meta.get("cover_card_url") or "",
        "has_cover_card": bool(meta.get("has_cover_card")),
    }
    _attach_cover_fields(out, base_url=out.get("url"))

    # 4) 落盘或回传 html
    save = params.get("save")
    if save:
        path = save if os.path.isabs(save) else os.path.join(C.SKILL_ROOT, save)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        out["saved_to"] = path
    else:
        out["html"] = html
    return out


def cmd_list(params):
    cfg = C.load_config_require_key()
    endpoint, api_key = C.endpoint_of(cfg), cfg.get("api_key", "")
    qs_pairs = [("page", params.get("page", 1)), ("page_size", params.get("page_size", 20))]
    # scope=test_all（或 all=1）：仅 is_test 用户生效，列出全部 test 用户页面
    if params.get("scope"):
        qs_pairs.append(("scope", params["scope"]))
    if params.get("all"):
        qs_pairs.append(("all", params["all"]))
    url = C.api_url(endpoint, _PATH["list"]) + "?" + _up.urlencode(qs_pairs)
    return _normalize_cover_response(C.http_json("GET", url, C.headers(api_key), timeout=_DEFAULT_TIMEOUT))


def cmd_revoke(params):
    cfg = C.load_config_require_key()
    endpoint, api_key = C.endpoint_of(cfg), cfg.get("api_key", "")
    if not params.get("page_id"):
        return {"code": 1, "message": "revoke 需要 page_id"}
    body = {"page_id": params["page_id"]}
    return C.http_json("POST", C.api_url(endpoint, _PATH["revoke"]),
                       C.headers(api_key), body, timeout=_DEFAULT_TIMEOUT)


def _http_multipart(url, api_key, fields, file_field, file_bytes, file_name, file_type):
    """发一个 multipart/form-data POST（带文件的接口用，如缩略图上传）。

    common.http_json 只发 JSON，无法带文件；这里手搓 multipart 包体，复用同一套
    无代理 opener / 版本渠道头 / 错误体兜底解析。
    """
    boundary = "----qbview" + hashlib.sha1(os.urandom(16)).hexdigest()[:16]
    crlf = b"\r\n"
    buf = io.BytesIO()
    for k, v in (fields or {}).items():
        buf.write(b"--" + boundary.encode() + crlf)
        buf.write(f'Content-Disposition: form-data; name="{k}"'.encode() + crlf + crlf)
        buf.write(str(v).encode("utf-8") + crlf)
    buf.write(b"--" + boundary.encode() + crlf)
    buf.write(f'Content-Disposition: form-data; name="{file_field}"; filename="{file_name}"'.encode() + crlf)
    buf.write(f"Content-Type: {file_type}".encode() + crlf + crlf)
    buf.write(file_bytes + crlf)
    buf.write(b"--" + boundary.encode() + b"--" + crlf)

    hdrs = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Authorization": f"Bearer {api_key}",
        "x-skill-version": C.SKILL_VERSION,
        "x-skill-name": C.SKILL_NAME,
    }
    if C.SKILL_CHANNEL:
        hdrs["x-skill-channel"] = C.SKILL_CHANNEL
    req = urllib.request.Request(url, data=buf.getvalue(), headers=hdrs, method="POST")
    try:
        with C._NO_PROXY_OPENER.open(req, timeout=_UPLOAD_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode("utf-8"))
        except Exception:
            return {"code": e.code, "success": False,
                    "error": {"message": getattr(e, "reason", str(e))}}
    except Exception as e:
        return {"code": 1, "success": False, "error": {"message": str(e)}}


def cmd_thumbnail(params):
    cfg = C.load_config_require_key()
    endpoint, api_key = C.endpoint_of(cfg), cfg.get("api_key", "")
    if not params.get("page_id"):
        return {"code": 1, "message": "thumbnail 需要 page_id（给哪个页面设置缩略图）"}
    img_path = params.get("image_file") or params.get("image") or params.get("file")
    if not img_path:
        return {"code": 1, "message": "thumbnail 需要 image_file（本地图片路径，PNG/JPG）"}
    if not os.path.isabs(img_path):
        img_path = os.path.join(C.SKILL_ROOT, img_path)
    if not os.path.exists(img_path):
        return {"code": 1, "message": f"image_file 不存在: {img_path}"}
    with open(img_path, "rb") as f:
        img_bytes = f.read()
    if len(img_bytes) > _MAX_THUMB_BYTES:
        return {"code": 1, "message": f"缩略图体积 {len(img_bytes)} 字节，超过上限 2MB"}
    ext = os.path.splitext(img_path)[1].lower()
    content_type = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"
    file_name = os.path.basename(img_path)
    return _http_multipart(C.api_url(endpoint, _PATH["thumbnail"]), api_key,
                           {"page_id": params["page_id"]},
                           "file", img_bytes, file_name, content_type)


def cmd_tags(params):
    cfg = C.load_config_require_key()
    endpoint, api_key = C.endpoint_of(cfg), cfg.get("api_key", "")
    qs_pairs = []
    if params.get("tag_type"):
        qs_pairs.append(("tag_type", params["tag_type"]))
    url = C.api_url(endpoint, _PATH["tags"])
    if qs_pairs:
        url += "?" + _up.urlencode(qs_pairs)
    return C.http_json("GET", url, C.headers(api_key), timeout=_DEFAULT_TIMEOUT)


def _cmd_community(params, path_key, label):
    cfg = C.load_config_require_key()
    endpoint, api_key = C.endpoint_of(cfg), cfg.get("api_key", "")
    if not params.get("page_id"):
        return {"code": 1, "message": f"{label} 需要 page_id"}
    body = {"page_id": params["page_id"]}
    return C.http_json("POST", C.api_url(endpoint, _PATH[path_key]),
                       C.headers(api_key), body, timeout=_DEFAULT_TIMEOUT)


def cmd_publish_community(params):
    return _cmd_community(params, "publish_community", "publish_community")


def cmd_unpublish_community(params):
    return _cmd_community(params, "unpublish_community", "unpublish_community")


def cmd_templates(params):
    cfg = C.load_config_require_key()
    endpoint, api_key = C.endpoint_of(cfg), cfg.get("api_key", "")
    qs_pairs = [("page", params.get("page", 1)), ("page_size", params.get("page_size", 20))]
    # 服务端默认限定 recommend:官方精选；*_tag_id / category / status 只做叠加筛选。
    for k in ("category", "status", "scene_tag_id", "paradigm_tag_id", "recommend_tag_id"):
        if params.get(k):
            qs_pairs.append((k, params[k]))
    url = C.api_url(endpoint, _PATH["templates"]) + "?" + _up.urlencode(qs_pairs)
    return _normalize_cover_response(C.http_json("GET", url, C.headers(api_key), timeout=_DEFAULT_TIMEOUT))


def cmd_template(params):
    cfg = C.load_config_require_key()
    endpoint, api_key = C.endpoint_of(cfg), cfg.get("api_key", "")
    tid = params.get("template_id") or params.get("page_id")
    if not tid:
        return {"code": 1, "message": "template 需要 template_id 或 page_id"}
    key = "template_id" if params.get("template_id") else "page_id"
    url = C.api_url(endpoint, _PATH["template"]) + "?" + _up.urlencode([(key, tid)])
    return _normalize_cover_response(C.http_json("GET", url, C.headers(api_key), timeout=_DEFAULT_TIMEOUT))


def _expected_template_metadata(params):
    expected = params.get("expected_metadata") if isinstance(params.get("expected_metadata"), dict) else {}
    for key in ("download_url", "title", "description", "category", "size", "sha256", "updated_at"):
        flag = "expected_" + key
        if flag in params:
            expected[key] = params[flag]
    return expected


def _metadata_changes(current, expected):
    changes = []
    for key, old in expected.items():
        if key not in current:
            continue
        now = current.get(key)
        if str(now or "") != str(old or ""):
            changes.append({"field": key, "expected": old, "current": now})
    return changes


def cmd_update_template(params):
    """Safely update a published template without creating a replacement URL."""
    cfg = C.load_config_require_key()
    endpoint, api_key = C.endpoint_of(cfg), cfg.get("api_key", "")
    tid = params.get("template_id") or params.get("page_id")
    if not tid:
        return {"code": 1, "message": "update_template 需要 template_id 或 page_id"}

    before = cmd_template({"template_id": tid} if params.get("template_id") else {"page_id": tid})
    if not (isinstance(before, dict) and before.get("code") == 0):
        return {"code": 1, "message": "写回前读取模板失败", "template": before}
    current = _template_record(before)
    expected = _expected_template_metadata(params)
    if expected:
        changes = _metadata_changes(current, expected)
        if changes:
            return {
                "code": 1,
                "message": "模板 metadata 已变化，停止写回以避免覆盖他人更新",
                "changes": changes,
                "template": before,
            }

    body = {"template_id": current.get("template_id") or current.get("page_id") or tid}
    html = None
    if params.get("html") or params.get("html_file"):
        html, err = _read_html(params)
        if err:
            return err
        try:
            html, shell_check = _ensure_share_shell(html, params)
        except ValueError as e:
            return {"code": 1, "message": str(e)}
        cover_verification = _maybe_verify_cover_card(html, params)
        if isinstance(cover_verification, dict) and not cover_verification.get("ok"):
            return {"code": 1, "message": cover_verification.get("message") or "宽宝活卡验收未通过", "cover_verification": cover_verification}
        card_runtime_verification = _maybe_verify_card_runtime(html, params)
        if isinstance(card_runtime_verification, dict) and not card_runtime_verification.get("ok"):
            return {
                "code": 1,
                "message": card_runtime_verification.get("message") or "card runtime artifact 验收未通过",
                "card_runtime_verification": card_runtime_verification,
            }
        body["html"] = html
    else:
        shell_check = None
        cover_verification = None
        card_runtime_verification = None

    for key in ("title", "description", "category", "cover_card_url", "has_cover_card"):
        if params.get(key) is not None:
            body[key] = params[key]
    if cover_verification and body.get("has_cover_card") is None:
        body["has_cover_card"] = True
    if params.get("verify_cover_card") and not body.get("cover_card_url"):
        public_url = current.get("download_url") or current.get("public_url") or current.get("url")
        if public_url:
            body["cover_card_url"] = _with_cover_query(public_url)

    out = C.http_json("POST", C.api_url(endpoint, _PATH["update_template"]),
                      C.headers(api_key), body, timeout=_UPLOAD_TIMEOUT)
    after = cmd_template({"template_id": body["template_id"]})
    if isinstance(out, dict):
        out["preflight_template"] = before
        out["postflight_template"] = after
        if shell_check:
            out["share_shell"] = shell_check
        if cover_verification:
            out["cover_verification"] = cover_verification
            _attach_cover_fields(out, base_url=body.get("cover_card_url") or current.get("download_url"), params=body)
        if card_runtime_verification:
            out["card_runtime_verification"] = card_runtime_verification
    return _normalize_cover_response(out)


def _fetch_public_html(url):
    if not url:
        raise ValueError("缺少可下载的 public/download URL")
    req = urllib.request.Request(url, headers={"Accept": "text/html,application/xhtml+xml"}, method="GET")
    with C._NO_PROXY_OPENER.open(req, timeout=_DEFAULT_TIMEOUT) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _default_retrofit_out_file(page_id):
    base = os.path.join(C.SKILL_ROOT, "output", "card-runtime-retrofit")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "%s.html" % (page_id or "page"))


def _run_card_runtime_verify(html_file, *, cover=False, artifact_only=False, require_browser=True, timeout_sec=180):
    target = html_file + ("?cover=1" if cover else "")
    cmd = ["node", os.path.join(C.SKILL_ROOT, "scripts", "verify_page.mjs"), target, "--card-runtime"]
    if require_browser:
        cmd.append("--require-browser")
    if artifact_only:
        cmd.append("--card-runtime-only")
    if cover:
        cmd.append("--cover-card")
    try:
        proc = subprocess.run(
            cmd,
            cwd=C.SKILL_ROOT,
            text=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_sec,
        )
    except subprocess.TimeoutExpired as exc:
        raw = ((exc.stdout or "") + "\n" + (exc.stderr or "")).strip()
        return {
            "code": 124,
            "message": "card runtime 验收超时",
            "target": target,
            "timeout_sec": timeout_sec,
            "raw": raw[-1000:],
        }
    raw = (proc.stdout or proc.stderr or "").strip()
    try:
        data = json.loads(raw) if raw else {}
    except Exception:
        data = {"code": proc.returncode, "raw": raw[-1000:]}
    data.setdefault("code", proc.returncode)
    return data


def _verify_card_runtime_html(html, *, require_browser=True, timeout_sec=180):
    with tempfile.TemporaryDirectory(prefix="qb_card_runtime_verify_") as td:
        path = os.path.join(td, "page.html")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(html)
        return _run_card_runtime_verify(
            path,
            artifact_only=True,
            require_browser=require_browser,
            timeout_sec=timeout_sec,
        )


def _maybe_verify_card_runtime(html, params):
    if not params.get("verify_card_runtime"):
        return None
    result = _verify_card_runtime_html(
        html,
        require_browser=params.get("verify_card_runtime_browser", True),
        timeout_sec=int(params.get("verify_card_runtime_timeout_sec", 180)),
    )
    return {
        "ok": isinstance(result, dict) and result.get("code") == 0,
        "mode": "card-runtime-only",
        "result": result,
        "message": "card runtime artifact 验收未通过" if not (isinstance(result, dict) and result.get("code") == 0) else "",
    }


def _as_list(value):
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return [value]


def _safe_stem(value):
    stem = re.sub(r"[^0-9A-Za-z._-]+", "_", str(value or "").strip())
    return stem.strip("._-") or "target"


def _card_runtime_verify_targets(params):
    targets = []
    for item in _as_list(params.get("targets")):
        if isinstance(item, dict):
            targets.append(dict(item))
        elif isinstance(item, str) and re.match(r"https?://", item, re.I):
            targets.append({"url": item})
        elif item:
            targets.append({"page_id": str(item)})
    for page_id in _as_list(params.get("page_ids")) + _as_list(params.get("page_id")):
        if page_id:
            targets.append({"page_id": str(page_id)})
    for template_id in _as_list(params.get("template_ids")) + _as_list(params.get("template_id")):
        if template_id:
            targets.append({"template_id": str(template_id)})
    for url in _as_list(params.get("urls")) + _as_list(params.get("url")):
        if url:
            targets.append({"url": str(url)})
    return targets


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _resolve_card_runtime_target(spec):
    spec = dict(spec or {})
    tid = spec.get("template_id") or spec.get("page_id")
    record = {}
    template = None
    url = spec.get("url") or spec.get("download_url")
    if tid:
        template = cmd_template({"template_id": tid} if spec.get("template_id") else {"page_id": tid})
        if not (isinstance(template, dict) and template.get("code") == 0):
            if not url:
                downloaded = cmd_download({"page_id": tid})
                if isinstance(downloaded, dict) and downloaded.get("code") == 0:
                    record = dict(downloaded)
                    record.pop("html", None)
                    url = record.get("download_url") or record.get("public_url") or record.get("url")
                    tid = record.get("template_id") or record.get("page_id") or tid
                else:
                    raise ValueError("读取模板失败: %s" % json.dumps(template, ensure_ascii=False)[:500])
        else:
            record = _template_record(template)
            url = url or record.get("download_url") or record.get("public_url") or record.get("url")
            tid = record.get("template_id") or record.get("page_id") or tid
    if not url:
        raise ValueError("缺少可验收的 url/download_url")
    return tid or "", url, record, template


def cmd_verify_card_runtime(params):
    """Fast batch verification for standalone card runtime artifacts."""
    targets = _card_runtime_verify_targets(params)
    if not targets:
        return {"code": 1, "message": "verify_card_runtime 需要 page_id/template_id/url 或对应列表"}

    out_dir = params.get("out_dir") or os.path.join(
        C.SKILL_ROOT,
        "output",
        "card-runtime-verify",
        datetime.now().strftime("%Y%m%d-%H%M%S"),
    )
    if not os.path.isabs(out_dir):
        out_dir = os.path.join(C.SKILL_ROOT, out_dir)
    os.makedirs(out_dir, exist_ok=True)
    summary_file = os.path.join(out_dir, "summary.json")
    require_browser = params.get("require_browser", True)
    timeout_sec = int(params.get("timeout_sec", 180))
    results = []

    def flush():
        _write_json(summary_file, {
            "code": 0 if all(item.get("code") == 0 for item in results) else 1,
            "checked": len(results),
            "passed": len([item for item in results if item.get("code") == 0]),
            "failed": len([item for item in results if item.get("code") != 0]),
            "out_dir": out_dir,
            "results": results,
        })

    for index, spec in enumerate(targets, start=1):
        entry = {"index": index, "input": spec}
        try:
            tid, url, record, template = _resolve_card_runtime_target(spec)
            label = tid or ("url_" + hashlib.sha1(url.encode("utf-8")).hexdigest()[:10])
            html_file = os.path.join(out_dir, _safe_stem(label) + ".html")
            html = _fetch_public_html(url)
            with open(html_file, "w", encoding="utf-8", newline="\n") as f:
                f.write(html)
            verification = _run_card_runtime_verify(
                html_file,
                artifact_only=True,
                require_browser=require_browser,
                timeout_sec=timeout_sec,
            )
            card_check = verification.get("card_runtime_check") if isinstance(verification, dict) else {}
            manifest = card_check.get("manifest") if isinstance(card_check, dict) else {}
            artifact = card_check.get("artifact_hydrate") if isinstance(card_check, dict) else {}
            entry.update({
                "code": verification.get("code") if isinstance(verification, dict) else 1,
                "page_id": tid,
                "url": url,
                "html_file": html_file,
                "json_file": os.path.join(out_dir, _safe_stem(label) + ".json"),
                "title": record.get("title") if isinstance(record, dict) else "",
                "required_outputs": (manifest or {}).get("required_outputs") or [],
                "artifact_text": (artifact or {}).get("text") or "",
                "problems": verification.get("problems") if isinstance(verification, dict) else ["verify_page 无法解析输出"],
                "verification": verification,
            })
            if template is not None:
                entry["template"] = {
                    "template_id": record.get("template_id") or record.get("page_id") or tid,
                    "download_url": record.get("download_url"),
                    "updated_at": record.get("updated_at"),
                    "sha256": record.get("sha256"),
                }
        except Exception as exc:
            fallback = spec.get("page_id") or spec.get("template_id") or spec.get("url") or "target_%s" % index
            entry.update({
                "code": 1,
                "page_id": spec.get("page_id") or spec.get("template_id") or "",
                "url": spec.get("url") or "",
                "json_file": os.path.join(out_dir, _safe_stem(fallback) + ".json"),
                "message": str(exc),
                "problems": [str(exc)],
            })
        _write_json(entry["json_file"], entry)
        results.append(entry)
        flush()

    failed = [item for item in results if item.get("code") != 0]
    return {
        "code": 1 if failed else 0,
        "checked": len(results),
        "passed": len(results) - len(failed),
        "failed": len(failed),
        "out_dir": out_dir,
        "summary_file": summary_file,
        "results": results,
    }


def cmd_retrofit_card_runtime(params):
    """Rebuild standalone card-runtime artifacts for a published template/page."""
    tid = params.get("template_id") or params.get("page_id")
    url = params.get("url") or params.get("download_url")
    if not tid and not url:
        return {"code": 1, "message": "retrofit_card_runtime 需要 page_id/template_id 或 url"}

    before = None
    record = {}
    if tid:
        before = cmd_template({"template_id": tid} if params.get("template_id") else {"page_id": tid})
        if not (isinstance(before, dict) and before.get("code") == 0):
            if not url:
                return {"code": 1, "message": "读取模板失败", "template": before}
        else:
            record = _template_record(before)
            url = url or record.get("download_url") or record.get("public_url") or record.get("url")
            tid = record.get("template_id") or record.get("page_id") or tid

    html = _fetch_public_html(url)
    next_html, info = CRT.retrofit_html(
        html,
        page_id=tid or params.get("page_id") or "",
        title=params.get("title") or record.get("title") or "",
    )

    out_file = params.get("out_file") or _default_retrofit_out_file(tid or params.get("page_id") or "page")
    if not os.path.isabs(out_file):
        out_file = os.path.join(C.SKILL_ROOT, out_file)
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    with open(out_file, "w", encoding="utf-8", newline="\n") as f:
        f.write(next_html)

    verify_default = _run_card_runtime_verify(out_file, cover=False) if params.get("verify", True) else None
    verify_cover = _run_card_runtime_verify(out_file, cover=True) if params.get("verify_cover_card", True) else None
    if verify_default and verify_default.get("code") != 0:
        return {"code": 1, "message": "card runtime 独立验收未通过", "html_file": out_file, "retrofit": info, "verification": verify_default}
    if verify_cover and verify_cover.get("code") != 0:
        return {"code": 1, "message": "cover/card runtime 验收未通过", "html_file": out_file, "retrofit": info, "cover_verification": verify_cover}

    update_result = None
    if params.get("update"):
        if not tid:
            return {"code": 1, "message": "url 模式不能 update；请传 page_id/template_id", "html_file": out_file, "retrofit": info}
        expected = _expected_template_metadata(params)
        if not expected and record:
            expected = {
                key: record.get(key)
                for key in ("download_url", "title", "description", "category", "size", "sha256", "updated_at")
                if record.get(key) is not None
            }
        update_params = {
            "template_id": tid,
            "html_file": out_file,
            "expected_metadata": expected,
            "verify_cover_card": False,
        }
        if params.get("verify_cover_card") or params.get("has_cover_card"):
            update_params["has_cover_card"] = True
            update_params["cover_card_url"] = _with_cover_query(url)
        update_result = cmd_update_template(update_params)
        err_code = ""
        if isinstance(update_result, dict):
            err = update_result.get("error") if isinstance(update_result.get("error"), dict) else {}
            template = update_result.get("template") if isinstance(update_result.get("template"), dict) else {}
            template_err = template.get("error") if isinstance(template.get("error"), dict) else {}
            err_code = str(err.get("code") or template_err.get("code") or update_result.get("code") or "")
        if not (isinstance(update_result, dict) and update_result.get("code") == 0) and err_code == "TEMPLATE_NOT_FOUND":
            update_result = cmd_update({
                "page_id": tid,
                "html_file": out_file,
                "verify_cover_card": False,
                **({
                    "has_cover_card": True,
                    "cover_card_url": _with_cover_query(url),
                } if (params.get("verify_cover_card") or params.get("has_cover_card")) else {}),
            })
        if not (isinstance(update_result, dict) and update_result.get("code") == 0):
            return {"code": 1, "message": "写回失败", "html_file": out_file, "retrofit": info, "update": update_result}

    return {
        "code": 0,
        "page_id": tid or params.get("page_id") or "",
        "url": url,
        "html_file": out_file,
        "retrofit": info,
        "verification": verify_default,
        "cover_verification": verify_cover,
        "update": update_result,
        "preflight_template": before,
    }


_COMMANDS = {
    "upload": cmd_upload,
    "update": cmd_update,
    "download": cmd_download,
    "list": cmd_list,
    "revoke": cmd_revoke,
    "thumbnail": cmd_thumbnail,
    "tags": cmd_tags,
    "publish_community": cmd_publish_community,
    "unpublish_community": cmd_unpublish_community,
    "templates": cmd_templates,
    "template": cmd_template,
    "update_template": cmd_update_template,
    "retrofit_card_runtime": cmd_retrofit_card_runtime,
    "verify_card_runtime": cmd_verify_card_runtime,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in _COMMANDS:
        C.emit({"code": 1, "message": f"用法: static_page.py <{'|'.join(_COMMANDS)}> [params]",
                "doc": (__doc__ or "").strip()[:400]}, out_name="sp_out.txt")
        sys.exit(1)
    cmd = sys.argv[1]
    params = C.read_params(sys.argv[2:], env_var="SP_PARAMS")

    try:
        result = _COMMANDS[cmd](params)
    except (FileNotFoundError, ValueError) as e:
        result = {"code": 1, "message": str(e)}
    C.emit(result, out_name="sp_out.txt")
    sys.exit(0 if (isinstance(result, dict) and result.get("code") == 0) else 1)


if __name__ == "__main__":
    main()
