#!/usr/bin/env python3
"""为一次 quant-buddy-view 用户任务建立可贯穿后端接口的 task_id。

用法：
  python scripts/trace_context.py begin '{"user_query":"生成茅台估值活页"}'
  python scripts/trace_context.py begin '{"task_id":"已有 task_id","user_query":"..."}'

后续每个 static_page / formula_package / data_grant 命令都必须复用返回的 task_id。
"""

import sys
import uuid

import common as C


def cmd_begin(params):
    cfg = C.load_config_require_key()
    endpoint, api_key = C.endpoint_of(cfg), cfg.get("api_key", "")
    task_id = str(params.get("task_id") or uuid.uuid4()).strip()
    user_query = str(params.get("user_query") or "").strip()
    if not user_query:
        return {"code": 1, "error": "USER_QUERY_REQUIRED", "message": "trace begin 需要 user_query（用户原始问题）"}

    # configure_trace_context（不是 set_trace_context）：本次调用没带 api_key 字段时保留当前已生效的
    # 覆盖，不清空——begin 常是任务第一个调用，read_params() 刚从同一份 params 里读出的 api_key 覆盖
    # 不该被这一行自己冲掉。
    C.configure_trace_context({"task_id": task_id, "user_query": user_query})
    body = {"task_id": task_id, "user_query": user_query}
    if params.get("agent_model"):
        body["agent_model"] = params["agent_model"]
    out = C.http_json(
        "POST",
        C.api_url(endpoint, "/skill/session/begin"),
        C.headers(api_key),
        body,
        timeout=30,
    )
    if not (isinstance(out, dict) and out.get("code") == 0):
        return {
            "code": 1,
            "error": "TRACE_BEGIN_FAILED",
            "message": "服务端 Trace 上下文创建失败，未开始后续发布流程",
            "server_response": out,
        }
    task_root = C.task_temp_dir(task_id, create=True)
    return {
        "code": 0,
        "task_id": task_id,
        "user_query": user_query,
        "task_temp_dir": str(task_root),
        "next_step": "templates",
        "instruction": (
            "后续每个 quant-buddy-view 命令都传入此 task_id，并只使用 task_temp_dir 保存任务产物。"
            "下一步先用 templates(recommend=\"all\") 查范式卡判定 fork/自建；未查模板前禁止 new_page，"
            "否则会被 ROUTING_TEMPLATES_REQUIRED 拦下。"
        ),
    }


_COMMANDS = {"begin": cmd_begin}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in _COMMANDS:
        C.emit({"code": 1, "message": "用法: trace_context.py begin [params]"}, out_name="trace_out.txt")
        sys.exit(1)
    params = C.read_params(sys.argv[2:], env_var="TRACE_PARAMS")
    result = _COMMANDS[sys.argv[1]](params)
    C.emit(result, out_name="trace_out.txt")
    sys.exit(0 if isinstance(result, dict) and result.get("code") == 0 else 1)


if __name__ == "__main__":
    main()
