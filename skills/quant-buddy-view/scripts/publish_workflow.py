#!/usr/bin/env python3
"""Deterministic QBV workflow: validate packages, register credentials, bind HTML, publish once."""

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import common as C
import data_grant as DG
import formula_package as FP
import static_page as SP


SCRIPT_DIR = Path(__file__).resolve().parent
BRIDGE = SCRIPT_DIR / "qbs_bridge.py"


def _failure(error, message, **extra):
    return {"code": 1, "error": error, "message": message, **extra}


def _marker_specs(packages, grants):
    specs = []
    for index, item in enumerate(packages):
        markers = item.get("markers") if isinstance(item, dict) else None
        if not isinstance(markers, dict):
            raise ValueError(f"packages[{index}].markers 必须是对象")
        specs.extend([
            (f"packages[{index}].markers.package_id", markers.get("package_id")),
            (f"packages[{index}].markers.signature", markers.get("signature")),
        ])
    for index, item in enumerate(grants):
        markers = item.get("markers") if isinstance(item, dict) else None
        if not isinstance(markers, dict):
            raise ValueError(f"grants[{index}].markers 必须是对象")
        specs.extend([
            (f"grants[{index}].markers.grant_id", markers.get("grant_id")),
            (f"grants[{index}].markers.signature", markers.get("signature")),
        ])
    normalized = []
    seen = set()
    for label, value in specs:
        marker = str(value or "").strip()
        if not marker or marker in seen:
            raise ValueError(f"{label} 缺失或与其他 marker 重复")
        seen.add(marker)
        normalized.append((label, marker))
    return normalized


def _run_qbs_package_set(task_id, user_query, packages):
    payload = {
        "task_id": task_id,
        "user_query": user_query,
        "packages": [
            {
                "name": str(item.get("name") or "").strip(),
                **dict(item.get("validation") or {}),
            }
            for item in packages
        ],
    }
    fd, params_file = tempfile.mkstemp(prefix="qbv_package_set_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False)
        completed = subprocess.run(
            [sys.executable, str(BRIDGE), "validate_package_set", f"@{params_file}"],
            cwd=SCRIPT_DIR.parent,
            env=dict(os.environ),
            capture_output=True,
            check=False,
        )
        try:
            result = json.loads(completed.stdout.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            return _failure("QBS_INVALID_RESPONSE", f"package-set 验证未返回合法 JSON: {exc}")
        if completed.returncode != 0 or not isinstance(result, dict) or result.get("code") != 0:
            return result if isinstance(result, dict) else _failure("QBS_PACKAGE_SET_FAILED", "package-set 验证失败")
        return result
    finally:
        try:
            os.unlink(params_file)
        except OSError:
            pass


def _replace_once(html, marker, value, label):
    count = html.count(marker)
    if count != 1:
        raise ValueError(f"{label} 必须在 HTML 中恰好出现一次，当前 {count} 次")
    return html.replace(marker, str(value), 1)


def run_workflow(params):
    params = dict(params or {})
    task_id = str(params.get("task_id") or "").strip()
    user_query = str(params.get("user_query") or "").strip()
    packages = params.get("packages")
    grants = params.get("grants") or []
    publish_params = params.get("publish_verified")
    if not task_id or not user_query:
        return _failure("QBV_TRACE_CONTEXT_REQUIRED", "task_id 和 user_query 必填")
    if not isinstance(packages, list) or not packages:
        return _failure("PACKAGES_REQUIRED", "packages 必须是非空数组")
    if not isinstance(grants, list):
        return _failure("INVALID_GRANTS", "grants 必须是数组")
    if not isinstance(publish_params, dict) or not publish_params.get("page_id"):
        return _failure("PUBLISH_PARAMS_REQUIRED", "publish_verified.page_id 必填")

    template_file = Path(str(params.get("html_template_file") or "")).resolve()
    prepared_file = Path(str(params.get("prepared_html_file") or "")).resolve()
    if not template_file.is_file() or not str(params.get("prepared_html_file") or "").strip():
        return _failure("HTML_FILES_REQUIRED", "html_template_file 必须存在，prepared_html_file 必填")
    if template_file == prepared_file:
        return _failure("SOURCE_HTML_IMMUTABLE", "prepared_html_file 不能覆盖 html_template_file")

    try:
        html = template_file.read_text(encoding="utf-8")
        marker_specs = _marker_specs(packages, grants)
        for label, marker in marker_specs:
            if html.count(marker) != 1:
                return _failure("HTML_MARKER_INVALID", f"{label} 必须在 HTML 中恰好出现一次")
    except (OSError, ValueError) as exc:
        return _failure("WORKFLOW_PREFLIGHT_FAILED", str(exc))

    C.set_trace_context(task_id, user_query)
    validation = _run_qbs_package_set(task_id, user_query, packages)
    if not isinstance(validation, dict) or validation.get("code") != 0:
        return _failure("PACKAGE_SET_VALIDATION_FAILED", "QBS package-set 验证失败", validation=validation)
    receipts = validation.get("validation_receipt_files") or []
    if len(receipts) != len(packages):
        return _failure("PACKAGE_SET_RECEIPTS_INCOMPLETE", "package-set 收据数量与公式包数量不一致", validation=validation)

    registered_packages = []
    for index, item in enumerate(packages):
        registration = dict(item.get("registration") or {})
        registration.update({"task_id": task_id, "user_query": user_query})
        result = FP.cmd_register(registration)
        if not (isinstance(result, dict) and result.get("code") == 0 and result.get("package_id") and result.get("signature")):
            return _failure("PACKAGE_REGISTER_FAILED", f"公式包注册失败: {item.get('name') or index}", failed_index=index, registered_packages=registered_packages)
        markers = item["markers"]
        html = _replace_once(html, markers["package_id"], result["package_id"], f"packages[{index}].package_id")
        html = _replace_once(html, markers["signature"], result["signature"], f"packages[{index}].signature")
        registered_packages.append({"name": str(item.get("name") or index), "package_id": result["package_id"]})

    registered_grants = []
    for index, item in enumerate(grants):
        registration = dict(item.get("registration") or {})
        registration.update({"task_id": task_id, "user_query": user_query})
        result = DG.cmd_register(registration)
        if not (isinstance(result, dict) and result.get("code") == 0 and result.get("grant_id") and result.get("signature")):
            return _failure("GRANT_REGISTER_FAILED", f"数据授权注册失败: {item.get('name') or index}", failed_index=index, registered_packages=registered_packages, registered_grants=registered_grants)
        markers = item["markers"]
        html = _replace_once(html, markers["grant_id"], result["grant_id"], f"grants[{index}].grant_id")
        html = _replace_once(html, markers["signature"], result["signature"], f"grants[{index}].signature")
        registered_grants.append({"name": str(item.get("name") or index), "grant_id": result["grant_id"]})

    prepared_file.parent.mkdir(parents=True, exist_ok=True)
    prepared_file.write_text(html, encoding="utf-8", newline="\n")
    verified_params = dict(publish_params)
    verified_params.update({
        "task_id": task_id,
        "user_query": user_query,
        "html_file": str(prepared_file),
        "validation_receipt_files": receipts,
    })
    published = SP.cmd_publish_verified(verified_params)
    return {
        "code": published.get("code", 1) if isinstance(published, dict) else 1,
        "success": bool(isinstance(published, dict) and published.get("code") == 0),
        "task_id": task_id,
        "package_count": len(registered_packages),
        "grant_count": len(registered_grants),
        "registered_packages": registered_packages,
        "registered_grants": registered_grants,
        "validation_receipt_files": receipts,
        "prepared_html_file": str(prepared_file),
        "publish_verified": published,
    }


def main():
    params = C.read_params(sys.argv[1:], env_var="QBV_WORKFLOW_PARAMS")
    try:
        result = run_workflow(params)
    except (FileNotFoundError, OSError, ValueError) as exc:
        result = _failure("WORKFLOW_ERROR", str(exc))
    emitted = dict(result)
    if isinstance(emitted.get("publish_verified"), dict):
        emitted["publish_verified"] = SP._publish_verified_cli_result(
            emitted["publish_verified"],
            params.get("task_id"),
        )
    C.emit(emitted, out_name="qbv_publish_workflow_out.txt")
    raise SystemExit(0 if result.get("code") == 0 else 1)


if __name__ == "__main__":
    main()
