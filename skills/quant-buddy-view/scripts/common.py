#!/usr/bin/env python3
r"""
quant-buddy-view 共享底座（self-contained，不依赖 quant-buddy-skill 的 call.py/executor.py）。

把原 quant-buddy-skill 里散落在 executor.py / call.py 的几样基础能力收敛到一处，
让本 skill 的三个工具（formula_package / static_page / build_dashboard）共用同一套：

  - 配置加载            load_config()  /  endpoint_of(cfg)
  - 版本 & 渠道请求头    SKILL_VERSION / SKILL_CHANNEL / headers()
  - 无代理 HTTP          _NO_PROXY_OPENER / http_json()
  - 入参解析 & 输出       read_params() / emit()

认证模型：本 skill 不维护会话 / task_id。register/list/revoke/refresh 与 static_page 凭
config.json 的 api_key（Bearer）认身份；query 取数无需 api_key（凭 package_id + signature）。
版本协商走请求头 x-skill-version / x-skill-name（见 headers()），与 task_id 无关。
"""

import io
import json
import os
import sys
import tempfile
import urllib.error
import urllib.request

SKILL_NAME = "quant-buddy-view"

# ── 跳过 Windows 注册表代理检测（proxy_bypass_registry 在某些环境极慢）──
# 空 ProxyHandler() 完全绕过系统代理。
_NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(SCRIPT_DIR)


# ────────────────────────────────────────────────
# 版本 / 渠道（打包时注入）
# ────────────────────────────────────────────────

def _read_skill_version() -> str:
    """从 SKILL.md frontmatter 读取 version 字段；失败返回空字符串。"""
    skill_md = os.path.join(SKILL_ROOT, "SKILL.md")
    try:
        with open(skill_md, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("version:"):
                    return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return ""


def _read_skill_channel() -> str:
    """从 config.json 读取 _channel 字段（打包时注入）；失败返回空字符串。"""
    cfg = os.path.join(SKILL_ROOT, "config.json")
    try:
        with open(cfg, "r", encoding="utf-8") as f:
            return json.load(f).get("_channel", "")
    except Exception:
        pass
    return ""


SKILL_VERSION = _read_skill_version()
SKILL_CHANNEL = _read_skill_channel()

# ── Windows 下强制 stdout/stderr 使用 UTF-8，避免服务端返回 emoji 时崩溃 ──
# line_buffering=True：每次 print 立即 flush，避免 PowerShell 首次读到空输出。
# 必须在任何 print 之前设置。
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)


# ────────────────────────────────────────────────
# 配置
# ────────────────────────────────────────────────

def load_config():
    """加载 config.json，叠加 config.local.json 覆盖，再叠加 QUANT_BUDDY_API_KEY 环境变量。

    缺 endpoint 抛 FileNotFoundError/ValueError；api_key 缺失只在需要时由调用方决定是否报错。
    """
    config_path = os.path.join(SKILL_ROOT, "config.json")
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"找不到配置文件: {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    local_path = os.path.join(SKILL_ROOT, "config.local.json")
    if os.path.exists(local_path):
        try:
            with open(local_path, "r", encoding="utf-8") as f:
                for k, v in (json.load(f) or {}).items():
                    if v not in (None, ""):
                        cfg[k] = v
        except Exception:
            pass
    env_key = os.environ.get("QUANT_BUDDY_API_KEY", "").strip()
    if env_key:
        cfg["api_key"] = env_key
    return cfg


def load_config_require_key():
    """加载配置并强制 api_key 非空（注册/上传/列表/撤销等写操作用）。"""
    cfg = load_config()
    if not cfg.get("api_key"):
        raise ValueError(
            "api_key 为空。请设置环境变量 QUANT_BUDDY_API_KEY，或在 config.json / "
            "config.local.json 中填入 api_key（从 https://www.quantbuddy.cn/login 获取）"
        )
    return cfg


def endpoint_of(cfg):
    """Return the configured QuantBuddy API endpoint."""
    endpoint = (cfg.get("endpoint") or "").rstrip("/")
    if not endpoint:
        raise ValueError("config.json 缺少 endpoint")
    return endpoint


def api_url(endpoint, path):
    """Join endpoint and API path without duplicating /skill.

    config.endpoint may be either a site root (https://host) or the skill root
    (https://host/skill). Most server paths are documented as /skill/xxx; this
    helper keeps both endpoint forms producing exactly one /skill segment.
    """
    endpoint = (endpoint or "").rstrip("/")
    if not endpoint:
        raise ValueError("endpoint 为空")
    path = "/" + str(path or "").lstrip("/")
    if endpoint.endswith("/skill") and path.startswith("/skill/"):
        path = path[len("/skill"):]
    return endpoint + path


# ────────────────────────────────────────────────
# HTTP
# ────────────────────────────────────────────────

def headers(api_key=None, accept=None):
    h = {
        "Content-Type": "application/json; charset=utf-8",
        "x-skill-version": SKILL_VERSION,
        "x-skill-name": SKILL_NAME,
    }
    if SKILL_CHANNEL:
        h["x-skill-channel"] = SKILL_CHANNEL
    if api_key:
        h["Authorization"] = f"Bearer {api_key}"
    if accept:
        h["Accept"] = accept
    return h


def http_json(method, url, hdrs, body=None, timeout=600):
    """发一个 JSON 请求并把响应解析为 dict；HTTP 错误体也尽量解析为 dict 返回。"""
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with _NO_PROXY_OPENER.open(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode("utf-8"))
        except Exception:
            return {"code": e.code, "success": False,
                    "error": {"message": getattr(e, "reason", str(e))}}
    except Exception as e:
        return {"code": 1, "success": False, "error": {"message": str(e)}}


# ────────────────────────────────────────────────
# 入参 / 输出
# ────────────────────────────────────────────────

def _coerce(v):
    """把命令行字符串值还原成 JSON 直觉类型：整数 / 浮点 / 布尔 / 其余原样字符串。"""
    low = v.lower()
    if low in ("true", "false"):
        return low == "true"
    try:
        return int(v)
    except ValueError:
        pass
    try:
        return float(v)
    except ValueError:
        pass
    return v


def _parse_flags(argv):
    """把命令行直觉写法 `--key value` / `--key=value` / `--flag` 解析成 dict。

    仅作为命令行 JSON 解析失败时的兜底——让 `list --scope test_all` 这类第一反应写法也能用。
    argv 里夹杂非 --flag 的散字时返回 None，交回上层按 JSON 报错（避免把 JSON 笔误误判成 flag）。
    """
    if not argv or not any(a.startswith("--") for a in argv):
        return None
    out = {}
    i, n = 0, len(argv)
    while i < n:
        tok = argv[i]
        if not tok.startswith("--"):
            return None
        key = tok[2:]
        if "=" in key:
            key, val = key.split("=", 1)
            out[key] = _coerce(val)
            i += 1
        elif i + 1 < n and not argv[i + 1].startswith("--"):
            out[key] = _coerce(argv[i + 1])
            i += 2
        else:  # 末尾或后接另一个 --flag：当布尔开关
            out[key] = True
            i += 1
    return out or None


def read_params(argv, env_var="VIEW_PARAMS"):
    """按 <env_var> > @file > 命令行 > stdin 优先级解析参数 dict。

    与 quant-buddy-skill 同款，规避 PowerShell GBK 命令行截断中文：优先用环境变量或 @file。
    命令行优先按 JSON 字符串解析；解析失败时兜底支持 `--key value` / `--key=value` 写法。
    """
    from_argv = False
    raw = os.environ.get(env_var, "").strip()
    if not raw and len(argv) >= 1:
        if argv[0].startswith("@"):
            with open(argv[0][1:], "r", encoding="utf-8-sig") as f:
                raw = f.read()
        else:
            raw = " ".join(argv)
            from_argv = True
    if not raw and not sys.stdin.isatty():
        raw = sys.stdin.buffer.read().decode("utf-8", errors="replace").strip()
    raw = raw or "{}"
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        if from_argv:
            flags = _parse_flags(argv)
            if flags is not None:
                return flags
        emit({"code": 1, "message": f"参数 JSON 解析失败: {e}", "raw": raw[:200],
              "hint": "参数用单个 JSON 字符串，如 list '{\"scope\":\"test_all\"}'；命令行也支持 --scope test_all"})
        sys.exit(1)


def emit(obj, out_name="view_out.txt"):
    """打印结果（dict→JSON，或原样字符串），并写一份到临时文件防终端缓冲吞输出。"""
    text = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False, indent=2)
    out_file = os.path.join(tempfile.gettempdir(), out_name)
    try:
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(text)
    except Exception:
        pass
    try:
        print(text)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "utf-8"
        sys.stdout.buffer.write((text + "\n").encode(enc, errors="replace"))
        sys.stdout.buffer.flush()
