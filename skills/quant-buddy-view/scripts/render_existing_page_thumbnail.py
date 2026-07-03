#!/usr/bin/env python3
"""Render a thumbnail for an existing QuantBuddy page/template HTML.

This is the stable path for public templates that already have live package
credentials in their HTML. It does not wait for the browser to race live data:
it queries the formula package first, injects the verified outputs by
temporarily replacing ``QB.query`` in the local cover page, then screenshots the
page with system Edge/Chrome.

Parameters (RPT_PARAMS > @file > JSON > stdin):
    {
      "url": "https://pages.quantbuddy.cn/pages/page_xxx.html",
      "html_file": "optional local html",
      "out_file": "output/thumbnails/page_xxx.png",
      "page_id": "page_xxx",
      "upload": true
    }
"""

import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request

import common as C
import formula_package as FP
import live_card as LC
import render_cover as RC

WIDTH = 1200
HEIGHT = 675

_SCRIPT_CONFIG_RE = re.compile(r"<script>\s*const\s+CONFIG\s*=\s*\{", re.I)
_CFGS_RE = re.compile(r"\b(?:var|let|const)\s+CFGS\s*=", re.I)
_CONFIG_ASSIGN_RE = re.compile(r"\b(?:var|let|const)\s+CONFIG\s*=", re.I)
_LOAD_ALL_CALL_RE = re.compile(r"\bloadAll\s*\(\s*\)\s*;", re.I)
_LOAD_CALL_RE = re.compile(r"\bload\s*\(\s*\)\s*;", re.I)
_MAIN_CALL_RE = re.compile(r"\bmain\s*\(\s*\)\s*;", re.I)
_OBJECT_RE = re.compile(r"\{[^{}]{0,4000}\}", re.S)
_PACKAGE_RE = re.compile(r"(?:[\"']?package_id[\"']?|[\"']?packageId[\"']?)\s*:\s*[\"']([^\"']+)[\"']")
_SIGNATURE_RE = re.compile(r"(?:[\"']?signature[\"']?)\s*:\s*[\"']([^\"']+)[\"']")
_ENDPOINT_RE = re.compile(r"(?:[\"']?endpoint[\"']?)\s*:\s*[\"']([^\"']+)[\"']")
_ENDPOINT_REF_RE = re.compile(r"(?:[\"']?endpoint[\"']?)\s*:\s*([A-Za-z_$][\w$]*)")
_CONST_STRING_RE = re.compile(r"\b(?:var|let|const)\s+([A-Za-z_$][\w$]*)\s*=\s*[\"']([^\"']+)[\"']")


def _abs(path):
    if not path:
        return None
    return path if os.path.isabs(path) else os.path.join(C.SKILL_ROOT, path)


def _page_id_from_url(url):
    m = re.search(r"(page_[0-9a-zA-Z]+)\.html", str(url or ""))
    return m.group(1) if m else ""


def _default_out_file(params):
    page_id = params.get("page_id") or _page_id_from_url(params.get("url")) or "existing-page"
    return os.path.join(C.SKILL_ROOT, "output", "thumbnails", page_id + ".png")


def _fetch_url(url):
    req = urllib.request.Request(url, method="GET")
    with C._NO_PROXY_OPENER.open(req, timeout=90) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _read_html(params):
    if params.get("html"):
        return str(params["html"]), {"source": "params.html"}
    if params.get("html_file"):
        path = _abs(params["html_file"])
        with open(path, "r", encoding="utf-8-sig") as f:
            return f.read(), {"source": "html_file", "path": path}
    if params.get("url"):
        return _fetch_url(params["url"]), {"source": "url", "url": params["url"]}
    raise ValueError("Need one of html/html_file/url")


def _extract_credentials(html):
    endpoint = _ENDPOINT_RE.search(html or "")
    endpoint_value = endpoint.group(1) if endpoint else ""
    const_strings = dict(_CONST_STRING_RE.findall(html or ""))
    creds = []
    seen = set()

    # Prefer credentials paired inside the same JS object. This avoids matching
    # package #2/#3 with package #1's signature when a CFGS array is compact.
    for obj in _OBJECT_RE.finditer(html or ""):
        text = obj.group(0)
        pkg = _PACKAGE_RE.search(text)
        sig = _SIGNATURE_RE.search(text)
        if not (pkg and sig):
            continue
        ep = _ENDPOINT_RE.search(text)
        ep_ref = _ENDPOINT_REF_RE.search(text)
        ep_value = ep.group(1) if ep else const_strings.get(ep_ref.group(1), endpoint_value) if ep_ref else endpoint_value
        key = (pkg.group(1), sig.group(1))
        if key in seen:
            continue
        seen.add(key)
        creds.append({
            "package_id": pkg.group(1),
            "signature": sig.group(1),
            "endpoint": ep_value,
        })

    for pkg in _PACKAGE_RE.finditer(html or ""):
        window = html[pkg.end(): min(len(html), pkg.end() + 1200)]
        sig = _SIGNATURE_RE.search(window)
        if not sig:
            continue
        key = (pkg.group(1), sig.group(1))
        if key in seen:
            continue
        seen.add(key)
        creds.append({
            "package_id": pkg.group(1),
            "signature": sig.group(1),
            "endpoint": endpoint_value,
        })
    return creds


def _query_outputs(html):
    creds = _extract_credentials(html)
    if not creds:
        return None, {"status": "not_found"}
    outputs = {}
    packages = []
    failures = []
    for cred in creds:
        endpoint = cred.get("endpoint") or C.endpoint_of(C.load_config())
        res = FP.query_package(endpoint, cred["package_id"], cred["signature"])
        if not (isinstance(res, dict) and res.get("code") == 0):
            failures.append({
                "package_id": cred["package_id"],
                "error": (res.get("error") or res.get("message") or res) if isinstance(res, dict) else str(res),
            })
            continue
        pkg_outputs = res.get("outputs") or {}
        outputs.update(pkg_outputs)
        packages.append({
            "package_id": cred["package_id"],
            "endpoint": endpoint,
            "outputs_count": len(pkg_outputs),
        })
    if failures and not outputs:
        return None, {
            "status": "failed",
            "packages": packages,
            "failures": failures,
        }
    return outputs, {
        "status": "partial" if failures else "ok",
        "package_ids": [p["package_id"] for p in packages],
        "packages": packages,
        "failures": failures,
        "outputs_count": len(outputs),
    }


def _cover_css():
    return """
<style id="qb-template-thumbnail-capture">
  html, body { width: 1200px !important; min-width: 1200px !important; overflow: hidden !important; }
  .qb-head, .qb-footer, .share-modal, #sharePosterModal { display: none !important; }
  .qb-action, .qb-actions, button[id*="share" i] { visibility: hidden !important; }
</style>
"""


def _is_inside_script(html, pos):
    lower = html.lower()
    open_pos = lower.rfind("<script", 0, pos)
    close_pos = lower.rfind("</script>", 0, pos)
    return open_pos >= 0 and open_pos > close_pos


def _offline_patch_js(outputs):
    data = json.dumps(outputs, ensure_ascii=False).replace("</", "<\\/")
    return (
        "/* qb-cover-offline-data: injected before page data boot. */\n"
        f"window.__QB_COVER_OUTPUTS__ = {data};\n"
        "window.__QB_COVER__ = window.__QB_COVER__ || {};\n"
        "window.__QB_COVER__.outputs = window.__QB_COVER_OUTPUTS__;\n"
        "(function(){\n"
        "  function applyCoverData(){\n"
        "    try {\n"
        "      var api = window.QB || (typeof QB !== 'undefined' ? QB : null);\n"
        "      var query = async function(){ return window.__QB_COVER_OUTPUTS__ || {}; };\n"
        "      window.queryPackage = query;\n"
        "      if (api) {\n"
        "        api.query = query;\n"
        "        api.queryFormulaPackage = query;\n"
        "      }\n"
        "      window.__QB_COVER_PATCHED__ = true;\n"
        "      return true;\n"
        "    } catch (e) {\n"
        "      window.__QB_COVER_PATCH_ERROR__ = String(e && e.message || e);\n"
        "      return false;\n"
        "    }\n"
        "  }\n"
        "  if (!applyCoverData()) {\n"
        "    var tries = 0;\n"
        "    var timer = setInterval(function(){\n"
        "      if (applyCoverData() || ++tries > 40) clearInterval(timer);\n"
        "    }, 50);\n"
        "  }\n"
        "})();\n"
    )


def _insert_patch(html, patch_js):
    for pattern in (_LOAD_ALL_CALL_RE, _LOAD_CALL_RE, _MAIN_CALL_RE, _CFGS_RE, _CONFIG_ASSIGN_RE):
        m = pattern.search(html)
        if m:
            if _is_inside_script(html, m.start()):
                return html[:m.start()] + "\n" + patch_js + "\n" + html[m.start():]
            patch = '<script id="qb-cover-offline-data">\n' + patch_js + "</script>\n"
            return html[:m.start()] + patch + html[m.start():]

    patch = '<script id="qb-cover-offline-data">\n' + patch_js + "</script>\n"
    m = _SCRIPT_CONFIG_RE.search(html)
    if m:
        return html[:m.start()] + patch + html[m.start():]
    return html.replace("</body>", patch + "\n</body>", 1) if "</body>" in html else html + patch


def _inject_cover_html(html, outputs):
    html = html.replace("</head>", _cover_css() + "\n</head>", 1) if "</head>" in html else _cover_css() + html
    if outputs:
        html = _insert_patch(html, _offline_patch_js(outputs))
    return html


def _capture_exact(cover_html, out_png, *, width=WIDTH, height=HEIGHT, wait_ms=4000, query=""):
    browser = RC._find_browser()
    if not browser:
        return None, {"status": "failed", "reason": "no_browser"}
    out_png = os.path.abspath(out_png)
    os.makedirs(os.path.dirname(out_png) or ".", exist_ok=True)
    url = pathlib.Path(cover_html).resolve().as_uri()
    if query:
        url += ("&" if "?" in url else "?") + str(query).lstrip("?")
    last = ""
    for headless in ("--headless=new", "--headless"):
        with tempfile.TemporaryDirectory(prefix="qb_existing_thumb_") as ud:
            args = [
                browser, headless,
                f"--screenshot={out_png}",
                f"--window-size={int(width)},{int(height)}",
                "--force-device-scale-factor=1",
                "--hide-scrollbars", "--disable-gpu", "--no-sandbox",
                "--no-first-run", "--no-default-browser-check",
                "--disable-extensions",
                f"--virtual-time-budget={int(wait_ms)}",
                f"--user-data-dir={ud}",
                url,
            ]
            try:
                cp = subprocess.run(args, capture_output=True, timeout=max(30, int(wait_ms / 1000) + 60))
                last = (cp.stderr or cp.stdout or b"").decode("utf-8", errors="replace")[-500:]
            except (subprocess.TimeoutExpired, OSError) as exc:
                last = str(exc)
                continue
            if os.path.exists(out_png) and os.path.getsize(out_png) > 2000 and RC._png_dims(out_png):
                return out_png, {"status": "ok", "browser": browser, "rasterizer": "edge" if "edge" in browser.lower() or "msedge" in browser.lower() else "chrome"}
    return None, {"status": "failed", "reason": "capture_failed", "browser": browser, "last": last}


def _inject_live_card_capture_html(html, outputs):
    if outputs:
        html = _insert_patch(html, _offline_patch_js(outputs))
    return html


def _upload_if_requested(params, out_file):
    if not params.get("upload"):
        return None
    page_id = params.get("page_id") or _page_id_from_url(params.get("url"))
    if not page_id:
        return {"code": 1, "message": "upload=true needs page_id or a URL containing page_id"}
    import static_page as SP
    return SP.cmd_thumbnail({"page_id": page_id, "image_file": out_file})


def render_existing_page_thumbnail(params):
    html, source = _read_html(params)
    outputs, query = _query_outputs(html)
    out_file = _abs(params.get("out_file")) or _default_out_file(params)
    base, _ = os.path.splitext(out_file)
    cover_html = params.get("cover_html_file")
    cover_html = _abs(cover_html) if cover_html else base + ".cover-existing.html"
    os.makedirs(os.path.dirname(out_file) or ".", exist_ok=True)

    live_card_capture = None
    prefer_live = params.get("prefer_live_card", True) is not False
    if prefer_live and LC.has_live_card(html):
        live_cover_html = params.get("live_cover_html_file")
        live_cover_html = _abs(live_cover_html) if live_cover_html else base + ".live-card-cover.html"
        live_width = int(params.get("live_card_width") or params.get("width") or WIDTH)
        live_height = int(params.get("live_card_height") or round(live_width * 3 / 4))
        with open(live_cover_html, "w", encoding="utf-8") as f:
            f.write(_inject_live_card_capture_html(html, outputs))
        shot, live_card_capture = _capture_exact(
            live_cover_html,
            out_file,
            width=live_width,
            height=live_height,
            wait_ms=int(params.get("live_card_wait_ms") or params.get("wait_ms") or 1500),
            query="cover=1",
        )
        if shot:
            dims = RC._png_dims(shot)
            upload = _upload_if_requested(params, shot)
            return {
                "code": 0,
                "source": source,
                "mode": "live-card",
                "out_file": shot,
                "cover_html": live_cover_html,
                "width": dims[0] if dims else None,
                "height": dims[1] if dims else None,
                "bytes": os.path.getsize(shot),
                "sha256": hashlib.sha256(open(shot, "rb").read()).hexdigest(),
                "query": query,
                "capture": live_card_capture,
                "upload": upload,
                "thumbnail_url": upload.get("thumbnail_url") if isinstance(upload, dict) else None,
            }

    with open(cover_html, "w", encoding="utf-8") as f:
        f.write(_inject_cover_html(html, outputs))
    shot, capture = _capture_exact(
        cover_html,
        out_file,
        width=int(params.get("width") or WIDTH),
        height=int(params.get("height") or HEIGHT),
        wait_ms=int(params.get("wait_ms") or 4000),
    )
    if not shot:
        return {
            "code": 1,
            "source": source,
            "query": query,
            "capture": capture,
            "live_card_capture": live_card_capture,
            "cover_html": cover_html,
        }
    dims = RC._png_dims(shot)
    upload = _upload_if_requested(params, shot)
    return {
        "code": 0,
        "source": source,
        "out_file": shot,
        "cover_html": cover_html,
        "width": dims[0] if dims else None,
        "height": dims[1] if dims else None,
        "bytes": os.path.getsize(shot),
        "sha256": hashlib.sha256(open(shot, "rb").read()).hexdigest(),
        "query": query,
        "capture": capture,
        "live_card_capture": live_card_capture,
        "upload": upload,
        "thumbnail_url": upload.get("thumbnail_url") if isinstance(upload, dict) else None,
    }


def main():
    params = C.read_params(sys.argv[1:], env_var="RPT_PARAMS")
    try:
        result = render_existing_page_thumbnail(params)
    except Exception as exc:
        result = {"code": 1, "message": str(exc)}
    C.emit(result, out_name="render_existing_page_thumbnail_out.txt")
    sys.exit(0 if isinstance(result, dict) and result.get("code") == 0 else 1)


if __name__ == "__main__":
    main()
