#!/usr/bin/env python3
"""校验终态 contract 对应的最终 Markdown 草稿，防止漏章节、漏链接或泄露敏感信息。"""

import json
import os
import re
import sys

import common as C


_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_FENCED_MARKDOWN_RE = re.compile(r"```markdown\s*(.*?)```", re.IGNORECASE | re.DOTALL)
_UNRESOLVED_FIELD_RE = re.compile(r"\{[^{}\r\n]+\}")
_SENSITIVE_PATTERNS = [
    ("windows_local_path", re.compile(r"(?i)(?:^|[\s(])(?:[a-z]:\\|file:///)")),
    ("unix_local_path", re.compile(r"(?:^|[\s(])/(?:Users|home|tmp|var/tmp)/")),
    ("api_key", re.compile(r"(?i)\bapi[_ -]?key\b\s*[:=]")),
    ("authorization", re.compile(r"(?i)\bauthorization\b\s*[:=]")),
    ("bearer_token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]{8,}")),
    ("signature", re.compile(r"(?i)\bsignature(?:_hash)?\b\s*[:=]")),
]


def _read_json_or_object(params, key, file_key):
    value = params.get(key)
    if isinstance(value, dict):
        return value
    path = params.get(file_key)
    if not path:
        return None
    with open(path, "r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def _read_text(params, key, file_key):
    value = params.get(key)
    if isinstance(value, str):
        return value
    path = params.get(file_key)
    if not path:
        return ""
    with open(path, "r", encoding="utf-8-sig") as handle:
        return handle.read()


def _required_headings(template_ref):
    if not template_ref:
        return []
    safe_ref = re.sub(r"[^0-9A-Za-z._-]+", "", str(template_ref))
    path = os.path.join(C.SKILL_ROOT, "reply-templates", f"{safe_ref}.md")
    if not os.path.isfile(path):
        return []
    with open(path, "r", encoding="utf-8-sig") as handle:
        text = handle.read()
    fenced = _FENCED_MARKDOWN_RE.search(text)
    skeleton = fenced.group(1) if fenced else text
    return [heading.strip() for heading in _HEADING_RE.findall(skeleton)]


def validate_reply(contract_payload, draft):
    contract_payload = contract_payload if isinstance(contract_payload, dict) else {}
    contract = contract_payload.get("agent_reply_contract") if isinstance(contract_payload.get("agent_reply_contract"), dict) else contract_payload
    errors = []
    if contract.get("terminal") is not True:
        errors.append({"code": "TERMINAL_CONTRACT_REQUIRED", "message": "缺少 terminal=true 的终态 contract"})
    public_url = str(contract.get("public_url") or "").strip()
    if not public_url:
        errors.append({"code": "PUBLIC_URL_REQUIRED", "message": "终态 contract 缺少 public_url"})
    elif public_url not in draft:
        errors.append({"code": "PUBLIC_URL_MISSING", "message": "最终回复未包含终态 public_url"})

    required = _required_headings(contract.get("template_ref")) if contract.get("required") else []
    actual = [heading.strip() for heading in _HEADING_RE.findall(draft)]
    cursor = -1
    for heading in required:
        try:
            index = actual.index(heading, cursor + 1)
        except ValueError:
            errors.append({"code": "REQUIRED_SECTION_MISSING", "message": f"缺少或顺序错误的章节：## {heading}"})
            continue
        cursor = index

    unresolved = _UNRESOLVED_FIELD_RE.findall(draft)
    if unresolved:
        errors.append({
            "code": "UNRESOLVED_FIELDS",
            "message": "最终回复仍有模板字段未替换；缺失数据必须写 -- 或 本轮未返回",
            "fields": unresolved[:20],
        })
    for name, pattern in _SENSITIVE_PATTERNS:
        if pattern.search(draft):
            errors.append({"code": "SENSITIVE_CONTENT", "message": f"最终回复包含禁止内容：{name}"})

    return {
        "code": 0 if not errors else 1,
        "valid": not errors,
        "template_ref": contract.get("template_ref") or None,
        "required_sections": required,
        "errors": errors,
    }


def main():
    params = C.read_params(sys.argv[1:], env_var="REPLY_PARAMS")
    try:
        contract = _read_json_or_object(params, "contract", "contract_file")
        draft = _read_text(params, "draft", "draft_file")
        if not contract or not draft:
            result = {"code": 1, "valid": False, "errors": [{"code": "INPUT_REQUIRED", "message": "需要 contract/contract_file 和 draft/draft_file"}]}
        else:
            result = validate_reply(contract, draft)
            if result.get("valid") and params.get("cleanup_task_id"):
                result["cleaned_temp_files"] = C.cleanup_task_temp_files(params.get("cleanup_task_id"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result = {"code": 1, "valid": False, "errors": [{"code": "INPUT_ERROR", "message": str(exc)}]}
    C.emit(result, out_name="reply_validation_out.txt")
    sys.exit(0 if result.get("code") == 0 else 1)


if __name__ == "__main__":
    main()
