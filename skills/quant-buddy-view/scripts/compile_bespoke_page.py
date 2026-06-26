#!/usr/bin/env python3
"""Compile a bespoke template into a self-contained QuantBuddy landing page.

The compiler replaces shared-shell placeholders and inlines local runtime assets.
Input is JSON via @file, CB_PARAMS, command JSON, or stdin:

{
  "template": "templates/valuation-financial-profile/page.template.html",
  "out_file": "output/pages/demo.html",
  "inline_data_kernel": true,
  "inline_qr_mini": true
}
"""

import os
import re
import sys
from urllib.parse import quote

import common as C


SHARED_DIR = os.path.join(C.SKILL_ROOT, "templates", "_shared", "share-shell")
ASSETS_DIR = os.path.join(C.SKILL_ROOT, "assets")
MAX_PAGE_BYTES = 2 * 1024 * 1024


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _resolve(path):
    if os.path.isabs(path):
        return path
    return os.path.join(C.SKILL_ROOT, path)


def _script_inline(path):
    return "<script>\n" + _read(path).strip() + "\n</script>"


def _style_inline(path):
    return "<style>\n" + _read(path).strip() + "\n</style>"


def _logo_data_uri():
    path = os.path.join(ASSETS_DIR, "logo.svg")
    raw = _read(path).strip()
    return "data:image/svg+xml;charset=utf-8," + quote(raw, safe="")


def _section(shell_html, name):
    m = re.search(
        rf"<!-- QB_SHELL_{name}_START -->(.*?)<!-- QB_SHELL_{name}_END -->",
        shell_html,
        flags=re.S,
    )
    if not m:
        raise ValueError(f"shell.html 缺少 {name} section")
    return m.group(1).strip().replace("__QB_LOGO_SRC__", _logo_data_uri())


def _replace(html, token, value):
    if token in html:
        return html.replace(token, value)
    return html


def _compile(html, params):
    replacements = params.get("replacements") if isinstance(params.get("replacements"), dict) else {}
    for old, new in replacements.items():
        html = html.replace(str(old), str(new))

    shell = _read(os.path.join(SHARED_DIR, "shell.html"))
    html = _replace(html, "<!-- QB_SHARED_SHELL_CSS -->", _style_inline(os.path.join(SHARED_DIR, "shell.css")))
    html = _replace(html, "<!-- QB_SHARED_SHELL_HEADER -->", _section(shell, "HEADER"))
    html = _replace(html, "<!-- QB_SHARED_SHELL_FOOTER -->", _section(shell, "FOOTER"))
    html = _replace(html, "<!-- QB_SHARED_SHELL_MODAL -->", _section(shell, "MODAL"))

    shared_js = "\n".join([
        _read(os.path.join(SHARED_DIR, "poster.js")).strip(),
        _read(os.path.join(SHARED_DIR, "shell.js")).strip(),
    ])
    html = _replace(html, "<!-- QB_SHARED_SHELL_JS -->", "<script>\n" + shared_js + "\n</script>")

    if params.get("inline_qr_mini", True):
        html = _replace(html, "<!-- QB_SHARED_QR_MINI -->", _script_inline(os.path.join(ASSETS_DIR, "qr-mini.js")))
    if params.get("inline_data_kernel", True):
        html = _replace(html, "<!-- QB_DATA_KERNEL -->", _script_inline(os.path.join(ASSETS_DIR, "data-kernel.js")))

    # Backstop for older templates that still reference local assets.
    html = re.sub(
        r'<script\s+src=["\'][^"\']*assets/qr-mini\.js["\']\s*>\s*</script>',
        lambda _m: _script_inline(os.path.join(ASSETS_DIR, "qr-mini.js")),
        html,
    )
    html = re.sub(
        r'<script\s+src=["\'][^"\']*assets/data-kernel\.js["\']\s*>\s*</script>',
        lambda _m: _script_inline(os.path.join(ASSETS_DIR, "data-kernel.js")),
        html,
    )
    html = re.sub(r'src=["\'][^"\']*assets/logo\.svg["\']', 'src="' + _logo_data_uri() + '"', html)
    return html


def _check(html):
    problems = []
    if re.search(r'<script\s+src=["\'][^"\']*(qr-mini|data-kernel|_shared)', html):
        problems.append("仍包含未内联的本地 script src")
    if "QB_SHARED_" in html or "__QB_LOGO_SRC__" in html:
        problems.append("仍包含公共组件占位符")
    for token in ("__PLACEHOLDER__", "pkg_replace", "replace_with_signature"):
        if token in html:
            problems.append(f"仍包含模板占位符: {token}")
    size = len(html.encode("utf-8"))
    if size > MAX_PAGE_BYTES:
        problems.append(f"页面超过 2MB: {size} bytes")
    return problems, size


def cmd_compile(params):
    src = params.get("template") or params.get("src") or params.get("html_file")
    if not src:
        return {"code": 1, "message": "缺少 template/src/html_file"}
    src_path = _resolve(src)
    out_file = params.get("out_file")
    if not out_file:
        base = os.path.splitext(os.path.basename(src_path))[0]
        out_file = os.path.join(C.SKILL_ROOT, "output", "pages", base + ".html")
    out_path = _resolve(out_file)
    html = _compile(_read(src_path), params)
    problems, size = _check(html)
    if problems and not params.get("allow_placeholders"):
        return {"code": 1, "message": "编译后静态检查未通过", "problems": problems, "size": size}
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(html)
    return {"code": 0, "out_file": out_path, "size": size, "warnings": problems}


def main():
    params = C.read_params(sys.argv[1:], env_var="CB_PARAMS")
    try:
        result = cmd_compile(params)
    except Exception as e:
        result = {"code": 1, "message": str(e)}
    C.emit(result, out_name="compile_bespoke_out.txt")
    sys.exit(0 if result.get("code") == 0 else 1)


if __name__ == "__main__":
    main()
