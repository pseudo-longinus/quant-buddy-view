#!/usr/bin/env python3
"""Run a quant-buddy-skill tool inside the current QBV task context."""

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path


QBV_ROOT = Path(__file__).resolve().parents[1]


def _read_params(argv):
    if not argv:
        raw = os.environ.get("QBS_BRIDGE_PARAMS", "").strip()
    elif len(argv) == 1 and argv[0].startswith("@"):
        raw = Path(argv[0][1:]).read_text(encoding="utf-8-sig")
    else:
        raw = " ".join(argv)
    params = json.loads(raw or "{}")
    if not isinstance(params, dict):
        raise ValueError("参数必须是 JSON 对象")
    return params


def _qbs_root():
    override = os.environ.get("QBS_SKILL_ROOT", "").strip()
    return Path(override).resolve() if override else (QBV_ROOT.parent / "quant-buddy-skill").resolve()


def _session_key(task_id):
    return re.sub(r"[^0-9A-Za-z._-]+", "_", task_id).strip("._-")


def _session_path(qbs_root, session_key):
    return qbs_root / "output" / f".session.{session_key}.json"


def _session_ready(path, task_id):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return False
    return data.get("task_id") == task_id and data.get("task_id_locked") is True


def _invoke(call_script, tool_name, params, env):
    fd, path = tempfile.mkstemp(prefix="qbv_qbs_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(params, handle, ensure_ascii=False)
        return subprocess.run(
            [sys.executable, str(call_script), tool_name, f"@{path}"],
            cwd=call_script.parent.parent,
            env=env,
            capture_output=True,
            check=False,
        )
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def _invoke_payload(call_script, tool_name, params, env):
    completed = _invoke(call_script, tool_name, params, env)
    try:
        payload = json.loads(completed.stdout.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, {
            "code": 1,
            "error": "QBS_INVALID_RESPONSE",
            "message": f"{tool_name} 未返回合法 JSON: {exc}",
        }
    if completed.returncode != 0 or not isinstance(payload, dict):
        return None, payload if isinstance(payload, dict) else {
            "code": 1,
            "error": "QBS_CALL_FAILED",
            "message": f"{tool_name} 调用失败",
        }
    return payload, None


def _payload_status(payload):
    if not isinstance(payload, dict):
        return ""
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    return str(payload.get("status") or data.get("status") or "").strip().lower()


def _validate_package_set(call_script, params, env):
    packages = params.get("packages")
    if not isinstance(packages, list) or not packages:
        return {"code": 1, "error": "PACKAGES_REQUIRED", "message": "packages 必须是非空数组"}

    task_id = str(params.get("task_id") or "").strip()
    user_query = str(params.get("user_query") or "").strip()
    names = set()
    normalized = []
    for index, item in enumerate(packages):
        if not isinstance(item, dict):
            return {"code": 1, "error": "INVALID_PACKAGE", "message": f"packages[{index}] 必须是对象"}
        name = str(item.get("name") or "").strip()
        formulas = item.get("formulas")
        if not name or name in names:
            return {"code": 1, "error": "INVALID_PACKAGE_NAME", "message": f"packages[{index}].name 缺失或重复"}
        if not isinstance(formulas, list) or not formulas or len(formulas) > 20 or not all(isinstance(value, str) and value.strip() for value in formulas):
            return {"code": 1, "error": "INVALID_PACKAGE_FORMULAS", "message": f"packages[{index}].formulas 必须是 1..20 条非空字符串"}
        force_reusable = item.get("force_reusable_array")
        if force_reusable is not None and (
            not isinstance(force_reusable, list)
            or not all(isinstance(value, str) and value.strip() for value in force_reusable)
        ):
            return {"code": 1, "error": "INVALID_FORCE_REUSABLE", "message": f"packages[{index}].force_reusable_array 必须是字符串数组"}
        names.add(name)
        normalized.append({
            "name": name,
            "formulas": formulas,
            "force_reusable_array": force_reusable,
        })

    results = []
    receipts = []
    for item in normalized:
        batch_params = {
            "task_id": task_id,
            "user_query": user_query,
            "formulas": item["formulas"],
            "output_mode": "summary",
        }
        if item["force_reusable_array"] is not None:
            batch_params["force_reusable_array"] = item["force_reusable_array"]
        payload, error = _invoke_payload(call_script, "runMultiFormulaBatchStream", batch_params, env)
        if error:
            return {**error, "success": False, "task_id": task_id, "failed_package": item["name"], "packages": results}
        if payload.get("code") not in (0, None) or payload.get("success") is False:
            return {"code": 1, "error": "PACKAGE_VALIDATION_FAILED", "success": False, "task_id": task_id, "failed_package": item["name"], "result": payload, "packages": results}

        trace_id = str(payload.get("trace_id") or (payload.get("data") or {}).get("trace_id") or "").strip()
        job_id = str(payload.get("job_id") or (payload.get("data") or {}).get("job_id") or "").strip()
        if _payload_status(payload) == "deferred" or payload.get("_deferred"):
            if not trace_id:
                return {"code": 1, "error": "DEFERRED_CONTINUATION_MISSING", "success": False, "task_id": task_id, "failed_package": item["name"], "packages": results}
            payload, error = _invoke_payload(call_script, "resumeJob", {
                "task_id": task_id,
                "user_query": user_query,
                "trace_id": trace_id,
                "output_mode": "summary",
            }, env)
            if error:
                return {**error, "success": False, "task_id": task_id, "failed_package": item["name"], "packages": results}

        receipt = str(payload.get("validation_receipt_file") or "").strip()
        if payload.get("code") not in (0, None) or payload.get("success") is False or not receipt:
            return {
                "code": 1,
                "error": "PACKAGE_VALIDATION_INCOMPLETE",
                "success": False,
                "task_id": task_id,
                "failed_package": item["name"],
                "result": payload,
                "packages": results,
            }
        receipts.append(receipt)
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        results.append({
            "name": item["name"],
            "status": _payload_status(payload) or "completed",
            "formula_count": len(item["formulas"]),
            "trace_id": trace_id or None,
            "job_id": job_id or None,
            "validation_receipt_file": receipt,
            "summary": data.get("summary") if isinstance(data.get("summary"), dict) else {},
        })
    return {
        "code": 0,
        "success": True,
        "task_id": task_id,
        "package_count": len(results),
        "batch_count": len(results),
        "validation_receipt_files": receipts,
        "packages": results,
    }


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"code": 1, "error": "TOOL_REQUIRED", "message": "用法: qbs_bridge.py <tool> [@params.json]"}, ensure_ascii=False))
        return 1
    tool_name = sys.argv[1]
    if tool_name == "newSession":
        print(json.dumps({"code": 1, "error": "BRIDGE_OWNS_SESSION", "message": "qbs_bridge 自动继承 QBV task_id，不接受 newSession"}, ensure_ascii=False))
        return 1
    try:
        params = _read_params(sys.argv[2:])
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"code": 1, "error": "INPUT_ERROR", "message": str(exc)}, ensure_ascii=False))
        return 1

    task_id = str(params.get("task_id") or "").strip()
    user_query = str(params.get("user_query") or "").strip()
    if not task_id or not user_query:
        missing = [key for key, value in (("task_id", task_id), ("user_query", user_query)) if not value]
        print(json.dumps({"code": 1, "error": "QBV_TRACE_CONTEXT_REQUIRED", "missing": missing}, ensure_ascii=False))
        return 1

    qbs_root = _qbs_root()
    call_script = qbs_root / "scripts" / "call.py"
    if not call_script.is_file():
        print(json.dumps({"code": 1, "error": "QBS_NOT_FOUND", "message": str(call_script)}, ensure_ascii=False))
        return 1

    session_key = _session_key(task_id)
    if not session_key:
        print(json.dumps({"code": 1, "error": "INVALID_TASK_ID"}, ensure_ascii=False))
        return 1
    env = dict(os.environ)
    env["QBS_SESSION_KEY"] = session_key
    env.setdefault("PYTHONUTF8", "1")

    if not _session_ready(_session_path(qbs_root, session_key), task_id):
        bootstrap = _invoke(call_script, "newSession", {
            "task_mode": "inherit",
            "task_id": task_id,
            "task_source": "quant-buddy-view",
            "user_query": user_query,
        }, env)
        if bootstrap.returncode != 0:
            sys.stdout.buffer.write(bootstrap.stdout)
            sys.stderr.buffer.write(bootstrap.stderr)
            return bootstrap.returncode or 1

    params["task_id"] = task_id
    if tool_name == "validate_package_set":
        payload = _validate_package_set(call_script, params, env)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if payload.get("code") == 0 else 1
    result = _invoke(call_script, tool_name, params, env)
    sys.stdout.buffer.write(result.stdout)
    sys.stderr.buffer.write(result.stderr)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
