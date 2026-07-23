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
VERIFY_PAGE = SCRIPT_DIR / "verify_page.mjs"
DEFAULT_FORMULA_BEGIN_DATE = 20150101
CARD_RUNTIME_MARKERS = (
    "data-qb-card-template",
    "data-qb-card-style",
    "data-qb-card-manifest",
    "data-qb-card-runtime",
)
PREFLIGHT_IMAGE_DATA_URI = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw=="


def _failure(error, message, **extra):
    return {"code": 1, "error": error, "message": message, **extra}


def _marker_values(value, label):
    values = value if isinstance(value, list) else [value]
    if not values:
        raise ValueError(f"{label} 必须是非空 marker 或非空 marker 数组")
    normalized = []
    for index, item in enumerate(values):
        marker = str(item or "").strip()
        item_label = f"{label}[{index}]" if isinstance(value, list) else label
        if not marker:
            raise ValueError(f"{item_label} 缺失")
        normalized.append((item_label, marker))
    return normalized


def _marker_specs(packages, grants, images=None):
    specs = []
    for index, item in enumerate(packages):
        markers = item.get("markers") if isinstance(item, dict) else None
        if not isinstance(markers, dict):
            raise ValueError(f"packages[{index}].markers 必须是对象")
        specs.extend(_marker_values(markers.get("package_id"), f"packages[{index}].markers.package_id"))
        specs.extend(_marker_values(markers.get("signature"), f"packages[{index}].markers.signature"))
    for index, item in enumerate(grants):
        markers = item.get("markers") if isinstance(item, dict) else None
        if not isinstance(markers, dict):
            raise ValueError(f"grants[{index}].markers 必须是对象")
        specs.extend(_marker_values(markers.get("grant_id"), f"grants[{index}].markers.grant_id"))
        specs.extend(_marker_values(markers.get("signature"), f"grants[{index}].markers.signature"))
    for index, item in enumerate(images or []):
        if not isinstance(item, dict):
            raise ValueError(f"images[{index}] 必须是对象")
        specs.append((f"images[{index}].marker", item.get("marker")))
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


def _replace_marker_field(html, marker_value, replacement, label):
    for marker_label, marker in _marker_values(marker_value, label):
        html = _replace_once(html, marker, replacement, marker_label)
    return html


def _has_card_runtime_artifact(html):
    return any(marker in html for marker in CARD_RUNTIME_MARKERS)


def _card_runtime_preview_html(html, packages, grants, images):
    preview = html
    for index, item in enumerate(packages):
        markers = item["markers"]
        preview = _replace_marker_field(
            preview,
            markers.get("package_id"),
            f"pkg_qbv_preflight_{index}",
            f"packages[{index}].markers.package_id",
        )
        preview = _replace_marker_field(
            preview,
            markers.get("signature"),
            f"sig_qbv_preflight_{index}",
            f"packages[{index}].markers.signature",
        )
    for index, item in enumerate(grants):
        markers = item["markers"]
        preview = _replace_marker_field(
            preview,
            markers.get("grant_id"),
            f"grant_qbv_preflight_{index}",
            f"grants[{index}].markers.grant_id",
        )
        preview = _replace_marker_field(
            preview,
            markers.get("signature"),
            f"grant_sig_qbv_preflight_{index}",
            f"grants[{index}].markers.signature",
        )
    for index, item in enumerate(images or []):
        preview = _replace_once(
            preview,
            str(item.get("marker") or "").strip(),
            PREFLIGHT_IMAGE_DATA_URI,
            f"images[{index}].marker",
        )
    return preview


def _run_card_runtime_preflight(html):
    if not _has_card_runtime_artifact(html):
        return {"code": 0, "skipped": True, "reason": "HTML 未包含 Card Runtime artifact"}
    fd, preview_file = tempfile.mkstemp(prefix="qbv_card_runtime_preflight_", suffix=".html")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(html)
        try:
            completed = subprocess.run(
                ["node", str(VERIFY_PAGE), preview_file, "--card-runtime-structure-only"],
                cwd=SCRIPT_DIR.parent,
                env=dict(os.environ),
                capture_output=True,
                check=False,
                timeout=60,
            )
        except FileNotFoundError:
            return _failure("NODE_REQUIRED", "Card Runtime 发布前结构预检需要 Node.js")
        except subprocess.TimeoutExpired:
            return _failure("CARD_RUNTIME_PREFLIGHT_TIMEOUT", "Card Runtime 发布前结构预检超时")
        try:
            result = json.loads(completed.stdout.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            return _failure("CARD_RUNTIME_PREFLIGHT_INVALID_RESPONSE", f"结构预检未返回合法 JSON: {exc}")
        if completed.returncode != 0 or not isinstance(result, dict) or result.get("code") != 0:
            return result if isinstance(result, dict) else _failure("CARD_RUNTIME_PREFLIGHT_FAILED", "Card Runtime 结构预检失败")
        return result
    finally:
        try:
            os.unlink(preview_file)
        except OSError:
            pass


def _begin_date(value, label):
    if value is None or str(value).strip() == "":
        return DEFAULT_FORMULA_BEGIN_DATE
    if isinstance(value, bool):
        raise ValueError(f"{label} 必须是 YYYYMMDD 整数")
    try:
        normalized = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} 必须是 YYYYMMDD 整数") from exc
    if normalized < 20050104 or normalized > 20991231 or len(str(normalized)) != 8:
        raise ValueError(f"{label} 必须是 20050104..20991231 的 YYYYMMDD 整数")
    return normalized


def _normalize_package_begin_dates(packages, workflow_begin_date=None):
    default_begin_date = _begin_date(workflow_begin_date, "begin_date")
    normalized = []
    for index, item in enumerate(packages):
        if not isinstance(item, dict):
            raise ValueError(f"packages[{index}] 必须是对象")
        package = dict(item)
        validation = dict(package.get("validation") or {})
        registration = dict(package.get("registration") or {})
        validation_raw = validation.get("begin_date")
        registration_raw = registration.get("begin_date")
        if validation_raw is not None and registration_raw is not None:
            validation_date = _begin_date(validation_raw, f"packages[{index}].validation.begin_date")
            registration_date = _begin_date(registration_raw, f"packages[{index}].registration.begin_date")
            if validation_date != registration_date:
                raise ValueError(
                    f"packages[{index}] validation.begin_date 与 registration.begin_date 必须一致"
                )
            begin_date = validation_date
        else:
            begin_date = _begin_date(
                validation_raw if validation_raw is not None else registration_raw,
                f"packages[{index}].begin_date",
            ) if validation_raw is not None or registration_raw is not None else default_begin_date
        validation["begin_date"] = begin_date
        registration["begin_date"] = begin_date
        package["validation"] = validation
        package["registration"] = registration
        normalized.append(package)
    return normalized


def run_workflow(params):
    params = dict(params or {})
    task_id = str(params.get("task_id") or "").strip()
    user_query = str(params.get("user_query") or "").strip()
    packages = params.get("packages")
    grants = params.get("grants") or []
    images = params.get("images") or []
    publish_params = params.get("publish_verified")
    if not task_id or not user_query:
        return _failure("QBV_TRACE_CONTEXT_REQUIRED", "task_id 和 user_query 必填")
    if not isinstance(packages, list) or not packages:
        return _failure("PACKAGES_REQUIRED", "packages 必须是非空数组")
    if not isinstance(grants, list):
        return _failure("INVALID_GRANTS", "grants 必须是数组")
    if not isinstance(images, list):
        return _failure("INVALID_IMAGES", "images 必须是数组")
    if not isinstance(publish_params, dict) or not publish_params.get("page_id"):
        return _failure("PUBLISH_PARAMS_REQUIRED", "publish_verified.page_id 必填")

    try:
        packages = _normalize_package_begin_dates(packages, params.get("begin_date"))
    except ValueError as exc:
        return _failure("PACKAGE_BEGIN_DATE_INVALID", str(exc))

    template_file = Path(str(params.get("html_template_file") or "")).resolve()
    prepared_file = Path(str(params.get("prepared_html_file") or "")).resolve()
    if not template_file.is_file() or not str(params.get("prepared_html_file") or "").strip():
        return _failure("HTML_FILES_REQUIRED", "html_template_file 必须存在，prepared_html_file 必填")
    if template_file == prepared_file:
        return _failure("SOURCE_HTML_IMMUTABLE", "prepared_html_file 不能覆盖 html_template_file")

    try:
        html = template_file.read_text(encoding="utf-8")
        marker_specs = _marker_specs(packages, grants, images)
        for label, marker in marker_specs:
            if html.count(marker) != 1:
                return _failure("HTML_MARKER_INVALID", f"{label} 必须在 HTML 中恰好出现一次")
        prepared_images = []
        for index, item in enumerate(images):
            logical_name = str(item.get("logical_name") or item.get("name") or "").strip()
            if not logical_name:
                return _failure("IMAGE_PREFLIGHT_FAILED", f"images[{index}].logical_name 必填")
            path, image_error = SP._resolve_local_image_file(item)
            if image_error:
                return _failure("IMAGE_PREFLIGHT_FAILED", image_error.get("message") or f"images[{index}] 图片预检失败", failed_index=index)
            prepared_images.append({**item, "logical_name": logical_name, "resolved_image_file": path})
        preview_html = _card_runtime_preview_html(html, packages, grants, images)
        card_runtime_preflight = _run_card_runtime_preflight(preview_html)
        if not isinstance(card_runtime_preflight, dict) or card_runtime_preflight.get("code") != 0:
            return _failure(
                "CARD_RUNTIME_PREFLIGHT_FAILED",
                "Card Runtime 发布前结构预检失败；尚未执行公式验证或任何注册",
                card_runtime_preflight=card_runtime_preflight,
            )
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
        html = _replace_marker_field(html, markers["package_id"], result["package_id"], f"packages[{index}].package_id")
        html = _replace_marker_field(html, markers["signature"], result["signature"], f"packages[{index}].signature")
        registered_packages.append({"name": str(item.get("name") or index), "package_id": result["package_id"]})

    registered_grants = []
    for index, item in enumerate(grants):
        registration = dict(item.get("registration") or {})
        registration.update({"task_id": task_id, "user_query": user_query})
        result = DG.cmd_register(registration)
        if not (isinstance(result, dict) and result.get("code") == 0 and result.get("grant_id") and result.get("signature")):
            return _failure("GRANT_REGISTER_FAILED", f"数据授权注册失败: {item.get('name') or index}", failed_index=index, registered_packages=registered_packages, registered_grants=registered_grants)
        markers = item["markers"]
        html = _replace_marker_field(html, markers["grant_id"], result["grant_id"], f"grants[{index}].grant_id")
        html = _replace_marker_field(html, markers["signature"], result["signature"], f"grants[{index}].signature")
        registered_grants.append({"name": str(item.get("name") or index), "grant_id": result["grant_id"]})

    uploaded_images = []
    for index, item in enumerate(prepared_images):
        result = SP.cmd_image_upload({
            "task_id": task_id,
            "page_id": publish_params["page_id"],
            "image_file": item["resolved_image_file"],
            "logical_name": item["logical_name"],
        })
        image_url = result.get("url") if isinstance(result, dict) else ""
        if not (isinstance(result, dict) and result.get("code") == 0 and result.get("asset_id") and image_url):
            return _failure(
                "IMAGE_UPLOAD_FAILED",
                f"正文图片上传失败: {item.get('name') or index}",
                failed_index=index,
                registered_packages=registered_packages,
                registered_grants=registered_grants,
                uploaded_images=uploaded_images,
                image_result=result,
            )
        html = _replace_once(html, item["marker"], image_url, f"images[{index}].marker")
        uploaded_images.append({
            "name": str(item.get("name") or item["logical_name"]),
            "logical_name": item["logical_name"],
            "asset_id": result["asset_id"],
            "url": image_url,
            "sha256": result.get("sha256"),
        })

    prepared_file.parent.mkdir(parents=True, exist_ok=True)
    prepared_file.write_text(html, encoding="utf-8", newline="\n")
    verified_params = dict(publish_params)
    verified_params.update({
        "task_id": task_id,
        "user_query": user_query,
        "html_file": str(prepared_file),
        "validation_receipt_files": receipts,
        "_via_publish_workflow": SP._VIA_PUBLISH_WORKFLOW_SENTINEL,
    })
    published = SP.cmd_publish_verified(verified_params)
    return {
        "code": published.get("code", 1) if isinstance(published, dict) else 1,
        "success": bool(isinstance(published, dict) and published.get("code") == 0),
        "task_id": task_id,
        "package_count": len(registered_packages),
        "grant_count": len(registered_grants),
        "image_count": len(uploaded_images),
        "registered_packages": registered_packages,
        "registered_grants": registered_grants,
        "uploaded_images": uploaded_images,
        "card_runtime_preflight": card_runtime_preflight,
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
