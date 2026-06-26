#!/usr/bin/env python3
r"""
静态页托管客户端 —— 把一份自包含 HTML 看板上传到对象存储，得到公开可分享链接。

对接接口文档：见 skill_server docs「静态页托管」对外接口文档。
工具说明文档：tools/static_page.md

八个子命令（全部需 API Key）：
    upload     上传 HTML，返回 page_id + 公开 url
    update     替换已有页面内容（URL / page_id 不变，已分享链接照常可用）
    download   取回已发布页面的 HTML（再编辑用）：服务端鉴权返回 url，脚本直连 OSS 下载
    list       列出我的页面
    revoke     撤销页面（删对象 + 标记失效，链接立即 404）
    thumbnail  给页面设置 / 替换缩略图（纯展示封面，直传 PNG/JPG，独立于 HTML 上传）
    templates  列出公共模板（全体登录用户可见 published；is_test 可见全部状态）
    template   公共模板详情：标题/说明/缩略图/关联公式包 + 公开下载链接（拿来克隆复用）

权限 / 权责（is_test 内部互通）：归属由 api_key（Bearer）认定。
  · 自己的页面（upload/update/download/list/revoke/thumbnail）：默认只能操作本人页面；
    is_test=true 的用户可 download / update / thumbnail 其他 is_test 用户的页面、并用 list 的
    scope=test_all 列出全部 test 用户页面。对普通（非 is_test）用户的页面一律 FORBIDDEN。
  · 公共模板（templates/template）：浏览 / 复制对**全体登录用户**开放，但普通用户只看得到
    已发布（published）的模板；is_test 用户可见 draft/offline 全部状态。
  · 模板的「提交 / 改写 / 上下线 / 把某个用户页转成公共模板」属于写操作，**本脚本不暴露**：
    提交/改写/上下线仅 is_test（走服务端 submit/update/publishTemplate）；把已有页面转公共模板
    是后台（growthX 管理端）动作。本 skill 侧只做「读取 + 复用」公共模板。

参数传递（规避 PowerShell GBK 截断）：优先级 SP_PARAMS 环境变量 > @file > 命令行 JSON > stdin

upload 参数：
    {
      "html":        "HTML 全文（与 html_file 二选一）",
      "html_file":   "本地 HTML 文件路径（与 html 二选一；常用 build_dashboard 的产物）",
      "title":       "可选，不传则服务端从 <title> 抽取",
      "description": "可选，页面说明（≤1000 字，列表/详情展示用）",
      "ttl_days":    "可选，默认 365"
    }
update 参数：page_id 必填；title / description / ttl_days 仅在传了才改（description 传空串=清空，不传保留原值）。
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
templates 参数：{ "category":可选, "status":可选(仅 is_test 生效), "page":1, "page_size":20 }
template  参数：{ "template_id":"tpl_xxx" }（或 "page_id":"page_xxx" 二选一）

用法示例：
    python scripts/static_page.py upload '{"html_file":"output/pages/dash.html","title":"沪深300异动看板"}'
    python scripts/static_page.py update '{"page_id":"page_xxx","html_file":"output/pages/dash.html"}'
    python scripts/static_page.py download '{"page_id":"page_xxx","save":"output/pages/back.html"}'
    python scripts/static_page.py list '{"page":1,"page_size":20}'
    python scripts/static_page.py list '{"scope":"test_all"}'   # 仅 is_test：列出全部 test 用户页面
    python scripts/static_page.py revoke '{"page_id":"page_xxx"}'
    python scripts/static_page.py thumbnail '{"page_id":"page_xxx","image_file":"output/pages/cover.png"}'
    python scripts/static_page.py templates '{"page":1,"page_size":20}'        # 浏览公共模板
    python scripts/static_page.py template  '{"template_id":"tpl_xxx"}'          # 模板详情/拿下载链接克隆

输出：结果打印到 stdout（UTF-8），并写一份到临时目录 sp_out.txt。
"""

import hashlib
import io
import json
import os
import re
import sys
import urllib.error
import urllib.parse as _up
import urllib.request

import compile_bespoke_page as CB
import common as C

_PATH = {
    "upload":    "/skill/uploadStaticPage",
    "update":    "/skill/updateStaticPage",
    "download":  "/skill/getStaticPage",
    "list":      "/skill/listStaticPages",
    "revoke":    "/skill/revokeStaticPage",
    "thumbnail": "/skill/setPageThumbnail",
    "templates": "/skill/listTemplates",
    "template":  "/skill/getTemplate",
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

    body = {"html": html}
    for k in ("title", "description", "ttl_days"):
        if params.get(k) is not None:
            body[k] = params[k]
    out = C.http_json("POST", C.api_url(endpoint, _PATH["upload"]),
                      C.headers(api_key), body, timeout=_UPLOAD_TIMEOUT)
    if isinstance(out, dict):
        out["share_shell"] = shell_check
        if out.get("code") == 0 or _server_mentions_package_issue(out):
            out["_package_runtime_check"] = _package_runtime_check(
                endpoint,
                html,
                force=bool(params.get("verify_packages")),
                publish_out=out,
            )
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

    body = {"page_id": params["page_id"], "html": html}
    for k in ("title", "description", "ttl_days"):
        if params.get(k) is not None:
            body[k] = params[k]
    out = C.http_json("POST", C.api_url(endpoint, _PATH["update"]),
                      C.headers(api_key), body, timeout=_UPLOAD_TIMEOUT)
    if isinstance(out, dict):
        out["share_shell"] = shell_check
        if out.get("code") == 0 or _server_mentions_package_issue(out):
            out["_package_runtime_check"] = _package_runtime_check(
                endpoint,
                html,
                force=bool(params.get("verify_packages")),
                publish_out=out,
            )
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
        "url": meta.get("url"),
        "size": len(html.encode("utf-8")),
        "sha256": sha,
        "sha256_match": sha_ok,
    }

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
    return C.http_json("GET", url, C.headers(api_key), timeout=_DEFAULT_TIMEOUT)


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
    return _http_multipart(endpoint + _PATH["thumbnail"], api_key,
                           {"page_id": params["page_id"]},
                           "file", img_bytes, file_name, content_type)


def cmd_templates(params):
    cfg = C.load_config_require_key()
    endpoint, api_key = C.endpoint_of(cfg), cfg.get("api_key", "")
    qs_pairs = [("page", params.get("page", 1)), ("page_size", params.get("page_size", 20))]
    for k in ("category", "status"):  # status 仅 is_test 生效（普通用户恒为 published）
        if params.get(k):
            qs_pairs.append((k, params[k]))
    url = f"{endpoint}{_PATH['templates']}?" + _up.urlencode(qs_pairs)
    return C.http_json("GET", url, C.headers(api_key), timeout=_DEFAULT_TIMEOUT)


def cmd_template(params):
    cfg = C.load_config_require_key()
    endpoint, api_key = C.endpoint_of(cfg), cfg.get("api_key", "")
    tid = params.get("template_id") or params.get("page_id")
    if not tid:
        return {"code": 1, "message": "template 需要 template_id 或 page_id"}
    key = "template_id" if params.get("template_id") else "page_id"
    url = f"{endpoint}{_PATH['template']}?" + _up.urlencode([(key, tid)])
    return C.http_json("GET", url, C.headers(api_key), timeout=_DEFAULT_TIMEOUT)


_COMMANDS = {
    "upload": cmd_upload,
    "update": cmd_update,
    "download": cmd_download,
    "list": cmd_list,
    "revoke": cmd_revoke,
    "thumbnail": cmd_thumbnail,
    "templates": cmd_templates,
    "template": cmd_template,
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
