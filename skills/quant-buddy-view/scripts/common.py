#!/usr/bin/env python3
r"""
quant-buddy-view 共享底座（self-contained，不依赖 quant-buddy-skill 的 call.py/executor.py）。

把原 quant-buddy-skill 里散落在 executor.py / call.py 的几样基础能力收敛到一处，
让本 skill 的三个工具（formula_package / static_page / build_dashboard）共用同一套：

  - 配置加载            load_config()  /  endpoint_of(cfg)
  - 版本 & 渠道请求头    SKILL_VERSION / SKILL_CHANNEL / headers()
  - 无代理 HTTP          _NO_PROXY_OPENER / http_json()
  - 入参解析 & 输出       read_params() / emit()

认证模型：register/list/revoke/refresh 与 static_page 凭 config.json 的 api_key（Bearer）
认身份；query 取数以 package/grant + signature 为能力凭证，CLI 本地有 api_key 时会可选附带用于审计归因。
每次用户任务先由
trace_context.py begin 建立 task_id，后续脚本通过入参复用，headers() 自动透传 x-task-id。
"""

import io
import json
import os
import re
import subprocess
import sys
import time
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

_TRACE_TASK_ID = None
_TRACE_USER_QUERY = None


def set_trace_context(task_id=None, user_query=None):
    """设置当前进程的 Trace Context；供 read_params / trace_context.py 共用。"""
    global _TRACE_TASK_ID, _TRACE_USER_QUERY
    _TRACE_TASK_ID = str(task_id).strip() if task_id else None
    _TRACE_USER_QUERY = str(user_query).strip() if user_query else None
    return {"task_id": _TRACE_TASK_ID, "user_query": _TRACE_USER_QUERY}


def configure_trace_context(params=None):
    """从参数或环境变量恢复本次任务上下文，不使用会互相覆盖的全局 session 文件。"""
    params = params if isinstance(params, dict) else {}
    nested = params.get("trace_context") if isinstance(params.get("trace_context"), dict) else {}
    task_id = params.get("task_id") or nested.get("task_id") or os.environ.get("QBV_TASK_ID")
    user_query = params.get("user_query") or nested.get("user_query") or os.environ.get("QBV_USER_QUERY")
    return set_trace_context(task_id, user_query)


def current_trace_context():
    return {"task_id": _TRACE_TASK_ID, "user_query": _TRACE_USER_QUERY}


def cleanup_task_temp_files(task_id):
    """删除本任务按 qbv_<task_id>_*.json 命名的临时参数文件，只允许操作系统临时目录。"""
    safe_task = re.sub(r"[^0-9A-Za-z._-]+", "_", str(task_id or "")).strip("._-")
    if not safe_task:
        return []
    temp_root = os.path.realpath(tempfile.gettempdir())
    deleted = []
    for name in os.listdir(temp_root):
        if not (name.startswith(f"qbv_{safe_task}_") and name.endswith(".json")):
            continue
        path = os.path.realpath(os.path.join(temp_root, name))
        if os.path.dirname(path) != temp_root:
            continue
        try:
            os.remove(path)
            deleted.append(path)
        except OSError:
            continue
    return deleted


def require_trace_context():
    if _TRACE_TASK_ID:
        return None
    return {
        "code": 1,
        "error": "TRACE_CONTEXT_REQUIRED",
        "message": (
            "发布/更新活页前必须先运行 scripts/trace_context.py begin，"
            "并把返回的 task_id 传给本次任务的每个 quant-buddy-view 命令。"
        ),
    }

def headers(api_key=None, accept=None):
    h = {
        "Content-Type": "application/json; charset=utf-8",
        "x-skill-version": SKILL_VERSION,
        "x-skill-name": SKILL_NAME,
    }
    if SKILL_CHANNEL:
        h["x-skill-channel"] = SKILL_CHANNEL
    if _TRACE_TASK_ID:
        h["x-task-id"] = _TRACE_TASK_ID
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
# 静默自更新：每次使用时按 GitHub tag 检查新版本，有则后台静默更新
#   发现走 GitHub tags API；应用复用 scripts/self_update.py（--trust-tls）。
#   全程 best-effort：任何异常都不得影响当前工具命令。
# ────────────────────────────────────────────────

SELF_UPDATE_SCRIPT = os.path.join(SCRIPT_DIR, "self_update.py")
VERSION_CHECK_STATE_FILE = os.path.join(SKILL_ROOT, "output", ".version_check_state.json")
SELF_UPDATE_STATE_FILE = os.path.join(SKILL_ROOT, "output", ".self_update_state.json")
GITHUB_TAGS_API = "https://api.github.com/repos/pseudo-longinus/quant-buddy-view/tags"
# 匿名 GitHub API 限流 60 次/小时/IP：默认 1 小时才检查一次
VERSION_CHECK_TTL = int(os.environ.get("QBV_VERSION_CHECK_TTL_SECONDS", "3600") or "3600")
VERSION_CHECK_HTTP_TIMEOUT = 4          # GitHub 请求短超时，避免拖慢当前命令
SELF_UPDATE_DAILY_FAIL_CAP = 1          # 同版本当日失败上限，超过则当天不再下载

# 进程内内存标记：本次运行是否已对某 target_version 触发过（一个进程最多一次）
_SELF_UPDATE_TRIED_THIS_RUN = set()


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _today_str() -> str:
    return time.strftime("%Y-%m-%d")


def _cmp_version(target: str, current: str) -> bool:
    """target 是否比 current 新（语义化按点分数字比较，容忍前缀 v）。"""
    def parse(v):
        if not v:
            return None
        t = str(v).strip().lstrip("vV")
        parts = t.split(".")
        nums = []
        for p in parts:
            if not re.fullmatch(r"\d+", p):
                return None
            nums.append(int(p))
        return tuple(nums)

    a, b = parse(target), parse(current)
    if a is None or b is None:
        return str(target or "").lstrip("vV") != str(current or "").lstrip("vV")
    w = max(len(a), len(b))
    a = a + (0,) * (w - len(a))
    b = b + (0,) * (w - len(b))
    return a > b


def _read_json_file(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def _write_json_file(path, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _in_dev_checkout() -> bool:
    """SKILL_ROOT 处于 git 工作副本（上溯存在 .git）时视为源码/调试目录，跳过自更新，
    避免把开发中的仓库副本静默覆盖（与 SKILL.md「源码 checkout 调试不要 bundle 覆盖」一致）。
    先 realpath 解析 junction/symlink：全局安装若是指向 git 源码仓库的 junction，也能识别并跳过。"""
    try:
        d = os.path.realpath(SKILL_ROOT)
    except Exception:
        d = SKILL_ROOT
    while True:
        if os.path.exists(os.path.join(d, ".git")):
            return True
        parent = os.path.dirname(d)
        if parent == d:
            return False
        d = parent


def _should_run_version_check() -> bool:
    """TTL 节流：未强制、且距上次检查不足 TTL、且版本未变 → 不检查。
    决定检查后立刻写回时间戳，使失败也照样被节流。"""
    if _truthy_env("QBV_FORCE_VERSION_CHECK"):
        return True
    st = _read_json_file(VERSION_CHECK_STATE_FILE)
    if st.get("skill_version") != SKILL_VERSION:
        return True
    try:
        age = time.time() - float(st.get("ts") or 0)
    except Exception:
        age = VERSION_CHECK_TTL + 1
    return age >= VERSION_CHECK_TTL


def _fetch_latest_tag():
    """拉 GitHub tags，返回 (version_without_v, zipball_url) 里语义最大的一个；失败返回 (None, None)。"""
    req = urllib.request.Request(
        GITHUB_TAGS_API,
        headers={"User-Agent": "quant-buddy-view-self-update", "Accept": "application/vnd.github+json"},
    )
    with _NO_PROXY_OPENER.open(req, timeout=VERSION_CHECK_HTTP_TIMEOUT) as resp:
        tags = json.loads(resp.read().decode("utf-8"))
    best_name, best_url = None, None
    for t in tags if isinstance(tags, list) else []:
        name = (t or {}).get("name") or ""
        url = (t or {}).get("zipball_url") or ""
        if not name or not url:
            continue
        if best_name is None or _cmp_version(name, best_name):
            best_name, best_url = name, url
    if not best_name:
        return None, None
    return best_name.lstrip("vV"), best_url


def _self_update_gate(target_version: str) -> bool:
    """去重 + 当日失败上限：本进程已试过、或同日同版本失败已达上限 → 不触发。"""
    if not target_version:
        return False
    if target_version in _SELF_UPDATE_TRIED_THIS_RUN:
        return False
    st = _read_json_file(SELF_UPDATE_STATE_FILE)
    if st.get("date") == _today_str() and st.get("target_version") == target_version:
        if st.get("status") == "failed" and int(st.get("attempts") or 0) >= SELF_UPDATE_DAILY_FAIL_CAP:
            return False
    return True


def _spawn_self_update(target_version: str, zip_url: str) -> None:
    """后台、静默、不阻塞地触发 self_update.py（--trust-tls）。子进程会自行写 .self_update_state.json。"""
    if not os.path.exists(SELF_UPDATE_SCRIPT):
        return
    cmd = [
        sys.executable, SELF_UPDATE_SCRIPT,
        "--url", zip_url,
        "--version", target_version,
        "--trust-tls",
        "--skill-root", SKILL_ROOT,
    ]
    kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "stdin": subprocess.DEVNULL}
    if os.name == "nt":
        # DETACHED_PROCESS | CREATE_NO_WINDOW：脱离当前控制台、无窗口
        kwargs["creationflags"] = 0x00000008 | 0x08000000
        kwargs["close_fds"] = True
    else:
        kwargs["start_new_session"] = True
        kwargs["close_fds"] = True
    subprocess.Popen(cmd, **kwargs)
    _SELF_UPDATE_TRIED_THIS_RUN.add(target_version)


def maybe_check_update() -> None:
    """每次工具运行的入口钩子：静默检查 GitHub 新 tag，有则后台自更新。任何异常都吞掉。"""
    try:
        if _truthy_env("QBV_DISABLE_SELF_UPDATE"):
            return
        if not SKILL_VERSION:
            return
        if _in_dev_checkout():
            return
        if not _should_run_version_check():
            return
        # 记录本次检查时间戳（无论后续成败），保证 TTL 节流
        _write_json_file(VERSION_CHECK_STATE_FILE, {"skill_version": SKILL_VERSION, "ts": int(time.time())})
        latest, zip_url = _fetch_latest_tag()
        if not latest or not zip_url:
            return
        if not _cmp_version(latest, SKILL_VERSION):
            return
        if not _self_update_gate(latest):
            return
        _spawn_self_update(latest, zip_url)
    except Exception:
        # 自更新永不影响当前工具命令
        pass


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
    maybe_check_update()  # 每次工具运行时静默检查/触发自更新（best-effort，永不阻塞或报错）
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
        params = json.loads(raw)
        configure_trace_context(params)
        return params
    except json.JSONDecodeError as e:
        if from_argv:
            flags = _parse_flags(argv)
            if flags is not None:
                configure_trace_context(flags)
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
