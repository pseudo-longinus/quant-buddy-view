#!/usr/bin/env python3
r"""
静态页托管客户端 —— 把一份自包含 HTML 看板上传到对象存储，得到公开可分享链接。

对接接口文档：见 skill_server docs「静态页托管」对外接口文档。
工具说明文档：tools/static_page.md

静态页子命令（除直连 URL 验收外需 API Key）：
    new_page   首次会话先上传 iframe 友好的活页进度页，返回 page_id + 公开 url
    update_progress  更新同一个 page_id 的进度页 HTML；刷新由承接页面负责
    upload     上传 HTML，返回 page_id + 公开 url
    update     替换已有页面内容（URL / page_id 不变，已分享链接照常可用）
    publish_final  首链进度页最终发布封装：先进入 final_publish，失败时回写失败态
    download   取回已发布页面的 HTML（再编辑用）：服务端鉴权返回 url，脚本直连 OSS 下载
    list       列出我的页面
    init_reply_metadata  为缺少 page_context / agent_reply_template 的旧页面初始化回复元数据
    revoke     撤销页面（删对象 + 标记失效，链接立即 404）
    thumbnail  给页面设置 / 替换缩略图（纯展示封面，直传 PNG/JPG，独立于 HTML 上传）
    tags       查询 upload/update 可用标签（scene 场景 / paradigm 范式；recommend 仅后台维护）
    autotag    LLM 自动识别页面的场景/范式标签并落库（dry_run 只读预览；force 忽略缓存重打）
    publish_community    将自己的 active 普通页发布到社区（内部受控打 recommend:社区 标签）
    unpublish_community  取消社区发布（移除固定 recommend:社区 标签）
    templates  列出范式卡活页（默认官方精选；recommend="all" 或 include_community=true 合并官方精选+社区）
    template   官方精选详情：标题/说明/缩略图/关联公式包 + 公开下载链接（拿来克隆复用）
    direct_deliver  直达命中确定性执行：模板详情 → 单次实时查询 → direct_finalize
    direct_finalize  直达命中终态：校验模板 revision、实时查询证据和任务归属，返回交付 Trace
    fork_prepare  下载命中范式 HTML 并生成 fork_manifest_v1，供 publish_final 做来源/能力门禁
    fork_validate 在浏览器验收前对工作 HTML 复用 publish_final 的 fork 门禁（不发布）
    update_template  官方精选/旧模板安全改写：metadata 复查后走 updateTemplate
    retrofit_card_runtime  为已发布模板重建独立 card runtime artifact，可原链接写回
    verify_card_runtime  批量快速验收独立 card runtime artifact（下载 HTML + required_outputs + 独立 hydrate）

权限 / 权责（is_test 内部互通）：归属由 api_key（Bearer）认定。
  · 自己的页面（upload/update/download/list/revoke/thumbnail）：默认只能操作本人页面；
    is_test=true 的用户可 download / update / thumbnail 其他 is_test 用户的页面、并用 list 的
    scope=test_all 列出全部 test 用户页面。对普通（非 is_test）用户的页面一律 FORBIDDEN。
  · 官方精选（templates/template）：浏览 / 复制对**全体登录用户**开放，发现口径是后台
    推荐标签 recommend:官方精选；不再要求 is_template=true 或 template_status=published。
  · 官方精选标签、旧模板元数据、上下线、删除、把某个用户页转成旧公共模板都属于后台写操作，
    本 skill 侧默认只做「读取 + 复用」官方精选。
  · update_template 只作为已转 published template / 官方精选页需要保留原链接时的
    安全维护 helper；写回前必须复查 metadata，避免覆盖他人更新。

参数传递（规避 PowerShell GBK 截断）：优先级 SP_PARAMS 环境变量 > @file > 命令行 JSON > stdin

upload 参数：
    {
      "html":        "HTML 全文（与 html_file 二选一）",
      "html_file":   "本地 HTML 文件路径（与 html 二选一；常用 build_dashboard 的产物）",
      "title":       "可选，不传则服务端从 <title> 抽取",
      "description": "可选，页面说明（≤1000 字，列表/详情展示用）",
      "ttl_days":    "可选，默认 365",
      "thumbnail_file": "可选，本地 PNG/JPG；HTML 上传成功后再设封面，失败只返回 warning",
      "scene_tags":    "可选，场景标签（数组/逗号串/单值）；只能选已有，查无报 SCENE_TAG_NOT_FOUND",
      "paradigm_tags": "可选，范式标签（数组/逗号串/单值）；可选已有或现写新名自动入池(source=user)",
      "user_query": "可选，用户原始问题；用于 LLM 打标或显式标签来源溯源",
      "tagging_method": "可选，标签决策方式：manual / llm / migration / unknown；不要传 agent，LLM 自动识别请用 autotag",
      "tagging_source": "可选，标签来源系统：quant-buddy-view / growthX / skill_server / script / unknown",
      "tagging_meta": "可选，对象；高级标签来源审计，method/source/note 会透传服务端",
      "page_context": "可选，对象；当前活页用途、核心模块、主要输出、回复重点和能力限制",
      "agent_reply_template": "可选，对象；兼容 reply_template_v1/v2，template_ref 指向 reply-templates/ 稳定 id",
      "verify_card_runtime": "可选 true；上传前只验收 card runtime artifact，失败不上传"
    }
    标签：推荐标签仅后台维护，本脚本不暴露；范式标签现写即进共享池。
    先用 tags 子命令查询可用场景/范式：python scripts/static_page.py tags
new_page 参数：title / message / current_step / page_status / steps / required_input 可选；默认接入公共 share shell，
    上传一个不自刷新的 iframe 活页进度页，并返回 page_id / url / progress。
update_progress 参数：page_id 必填；title / message / current_step / page_status / steps / required_input 可选；
    只 update 同一个 URL 的 HTML 内容；仅传 current_step 时会自动推导前序完成、当前进行中、后序待开始。
    必须等用户决定时用 page_status=waiting_input + required_input{id,prompt,options?,resume_step}；
    用户回复后复用同一 task_id/page_id，以 page_status=running 恢复。
    message 是用户可见文案，避免 HTML / 公式包 / 本地浏览器验收 / page_id 等工程词。
    不在页面里写自动刷新、跳转或 parent 通信。
publish_final 参数：同 update；推荐用于首链进度页的最终正式发布。
    会先把进度页推进到 final_publish；若正式 update 失败，会自动把同一 page_id 更新为 failed 进度页。
    复用在线模板时传 source_template_id + fork_manifest_file；前者继承回复骨架，后者证明来源 HTML 已下载并声明 fork 门禁；page_context 必须按最终用户活页重新生成。
    同一 task_id 执行过 fork_prepare 后，publish_final 会自动恢复已绑定的来源与 manifest；省略或改写参数不能绕过 fork 门禁。
    无法匹配专业骨架时使用 generic_live_page_delivery_v1；v2 hybrid 缺 page_context / hybrid_composition 时 fail-closed。
update 参数：page_id 必填；title / description / ttl_days / scene_tags / paradigm_tags /
    user_query / tagging_method / tagging_source / tagging_meta /
    page_context / agent_reply_template / verify_card_runtime 仅在传了才改
    （description 传空串=清空，不传保留原值；标签字段传 [] 清空、不传保留原标签）。
    可同样传 thumbnail_file，HTML 更新成功后再替换封面；缩略图失败不回滚 HTML。
download 参数：
    {
      "page_id":  "要下载的页面（与 url 二选一）",
      "url":      "页面公开链接（与 page_id 二选一）",
      "save":     "可选，落盘路径（相对则相对 skill 根）；不传则把 html 直接放进返回 JSON",
      "final_response": "可选 true；仅在只读页面后直接回答时返回终态 contract，默认返回非终态 hint"
    }
    下载字节直连 OSS（public-read），不经服务端 → 不占服务端带宽。
thumbnail 参数：
    {
      "page_id":    "要设置缩略图的页面（必填）",
      "image_file": "本地图片路径（PNG/JPG，≤2MB，相对则相对 skill 根）"
    }
    直传图片到 OSS（pages/thumbnails/{page_id}.png，public-read），仅回写页面的 thumbnail_url；
    不动 HTML、不占活跃页配额。缩略图只是「列表/详情/模板墙」的展示封面，纯展示用。
tags 参数：{ "tag_type":可选("scene" 或 "paradigm") }；不传则同时返回 scene_tags / paradigm_tags。
init_reply_metadata 参数：{ "scope":"test_all", "dry_run":true, "page_ids":["page_xxx"], "max_pages":500 }；
    默认只 dry-run 扫描 is_test 可见页面，下载缺 page_context / agent_reply_template 的页面，
    根据现有 HTML、标题和标签推断回复元数据；dry_run=false 才用同一 HTML 写回初始化结果。
publish_community / unpublish_community 参数：{ "page_id":"page_xxx" }；仅 owner 可操作自己的 active 普通页。
templates 参数：{ "category":可选, "status":可选, "scene_tag_id":可选, "paradigm_tag_id":可选, "recommend_tag_id":可选, "recommend":可选("社区"/"all"/"both"), "include_community":可选 true, "page":1, "page_size":20 }；不传 recommend/include_community 时仍限定 recommend:官方精选；recommend="社区" 只查社区；recommend="all"/include_community=true 合并官方精选+社区（范式卡命中池，按 page_id 去重）。recommend_tag_id 是额外叠加筛选。
template  参数：{ "template_id":"tpl_xxx" }（或 "page_id":"page_xxx" 二选一）
direct_finalize 参数：{ "task_id":"本次 Trace task_id", "page_id":"page_xxx", "template_revision":"template 返回的 sha256" }
direct_deliver 参数：{ "task_id":"本次 Trace task_id", "page_id":"page_xxx", "template_revision":"templates 返回的 sha256" }
fork_prepare 参数：{ "task_id":"本次 Trace task_id", "source_template_id":"page_xxx", "output_dir":"output/forks/page_xxx", "source_markers":["原标的名","原代码"], "target_asset":"新代码", "asset_replacements":{"原标的名":"新标的名","原代码":"新代码"}, "minimum_target_package_count":可选, "minimum_target_grant_count":可选, "credential_count_reduction_reason":"数量下调时必填" }
verify_card_runtime 参数：{ "page_ids":["page_xxx"], "require_browser":true, "timeout_sec":180 }

用法示例：
    python scripts/static_page.py new_page '{"title":"贵州茅台估值质量分析","message":"正在确认活页方案"}'
    python scripts/static_page.py update_progress '{"page_id":"page_xxx","current_step":"formula_validation","message":"正在验证实时数据"}'
    python scripts/static_page.py publish_final '{"page_id":"page_xxx","html_file":"output/pages/final.html","title":"贵州茅台估值质量分析","source_template_id":"page_template_xxx","fork_manifest_file":"output/forks/page_template_xxx/page_template_xxx.fork-manifest.json","require_agent_reply_template":true}'
    python scripts/static_page.py upload '{"html_file":"output/pages/dash.html","title":"沪深300异动看板"}'
    python scripts/static_page.py update '{"page_id":"page_xxx","html_file":"output/pages/dash.html"}'
    python scripts/static_page.py download '{"page_id":"page_xxx","save":"output/pages/back.html"}'
    python scripts/static_page.py list '{"page":1,"page_size":20}'
    python scripts/static_page.py list '{"scope":"test_all"}'   # 仅 is_test：列出全部 test 用户页面
    python scripts/static_page.py init_reply_metadata '{"scope":"test_all","dry_run":true}'
    python scripts/static_page.py revoke '{"page_id":"page_xxx"}'
    python scripts/static_page.py thumbnail '{"page_id":"page_xxx","image_file":"output/pages/cover.png"}'
    python scripts/static_page.py tags '{}'                                      # 查询可用场景/范式标签
    python scripts/static_page.py tags '{"tag_type":"scene"}'                 # 只查场景标签
    python scripts/static_page.py publish_community '{"page_id":"page_xxx"}'   # 发布到社区（全员可发现）
    python scripts/static_page.py unpublish_community '{"page_id":"page_xxx"}' # 取消社区发布
    python scripts/static_page.py templates '{"page":1,"page_size":20}'        # 浏览官方精选
    python scripts/static_page.py template  '{"template_id":"page_xxx"}'        # 官方精选详情/拿下载链接克隆
    python scripts/static_page.py direct_finalize '{"task_id":"task_xxx","page_id":"page_xxx","template_revision":"sha256"}'
    python scripts/static_page.py fork_prepare '{"task_id":"task_xxx","source_template_id":"page_xxx","source_markers":["原标的名","原代码"],"target_asset":"新代码","asset_replacements":{"原标的名":"新标的名","原代码":"新代码"}}'
    python scripts/static_page.py verify_card_runtime '{"page_ids":["page_xxx","page_yyy"]}' # 快速批量验收 card artifact

输出：结果打印到 stdout（UTF-8），并写一份到临时目录 sp_out.txt。
读取型命令默认返回 agent_reply_hint（terminal=false）；来源模板 download_url 在 fork 分支不能当用户交付链接。direct 精确命中必须调用 `direct_finalize`，普通 published template 禁止用 `download(final_response:true)` 收口。
成功写入命令及 `direct_finalize` 返回 agent_reply_contract；`download(final_response:true)` 仅保留给普通自有页面的只读兼容。
contract.required=true 时，Agent 最终答复前必须读取本地回复模板，按模板格式输出并包含公开活页链接。
"""

import hashlib
import html as html_lib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse as _up
import urllib.request
from datetime import datetime, timezone

import compile_bespoke_page as CB
import card_runtime_retrofit as CRT
import common as C
import progress_page as PP

_PATH = {
    "upload":    "/skill/uploadStaticPage",
    "update":    "/skill/updateStaticPage",
    "download":  "/skill/getStaticPage",
    "list":      "/skill/listStaticPages",
    "revoke":    "/skill/revokeStaticPage",
    "thumbnail": "/skill/setPageThumbnail",
    "tags":      "/skill/listPageTags",
    "autotag":   "/skill/autoTagStaticPage",
    "publish_community":   "/skill/publishStaticPageToCommunity",
    "unpublish_community": "/skill/unpublishStaticPageFromCommunity",
    "templates": "/skill/listTemplates",
    "template":  "/skill/getTemplate",
    "direct_finalize": "/skill/finalizeDirectPage",
    "update_template": "/skill/updateTemplate",
}

_UPLOAD_TIMEOUT = 120
_DEFAULT_TIMEOUT = 60

# 服务端限制：单页 ≤ 2MB（这里只做一次本地早检，真正以服务端为准）
_MAX_HTML_BYTES = 2 * 1024 * 1024
# 缩略图上限（与服务端 setPageThumbnail 一致，2MB）
_MAX_THUMB_BYTES = 2 * 1024 * 1024
_SHARE_POSTER_VERSION = "snapshot-tall-v1"
_SHARE_SHELL_VERSION = "copy-link-v1"
_FORK_MANIFEST_VERSION = "fork_manifest_v1"
_FORK_TASK_BINDING_VERSION = "fork_task_binding_v1"
_VALIDATION_RECEIPT_VERSION = "qb_validation_receipt_v1"
_PROGRESS_SHELL_THEME = {
    "chrome_bg": "#ffffff",
    "header_bg": "#ffffff",
    "footer_bg": "#ffffff",
    "accent": "#fe9c3c",
    "accent_strong": "#8f4e00",
    "line": "#d9e0ea",
    "ink": "#111c2d",
    "muted": "#45474c",
}
_PACKAGE_ISSUE_RE = re.compile(
    r"formula[_ -]?package|package_id|signature|公式包|签名|查无|失效|无效|not[_ -]?found|invalid",
    re.I,
)
_REPLY_TEMPLATE_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_REPLY_TEMPLATE_FIELDS = ("version", "template_ref", "reply_scope", "output_format", "hybrid_composition")
_PAGE_CONTEXT_FIELDS = ("version", "summary", "core_sections", "primary_outputs", "reply_focus", "limitations")
_REPLY_CONTRACT_BINDING_FIELDS = ("version", "profile_ref", "revision", "managed_by")
_REPLY_TEMPLATE_VERSIONS = {"reply_template_v1", "reply_template_v2"}
_REPLY_SCOPES = {"full_answer", "hybrid"}
_HYBRID_COMPOSITION_VERSION = "hybrid_composition_v1"
_PAGE_CONTEXT_VERSION = "page_context_v1"
_MAX_REPLY_METADATA_BYTES = 8 * 1024
_MAX_PAGE_CONTEXT_BYTES = 8 * 1024
_MAX_PAGE_CONTEXT_TEXT = 1000
_MAX_PAGE_CONTEXT_ITEMS = 50
_MAX_PAGE_CONTEXT_ITEM = 128
_PAGE_CONTEXT_SENSITIVE_RE = re.compile(
    r"(?:\bapi[_ -]?key\b|\bbearer\s+[a-z0-9._-]+|\bsignature\s*[:=]|[a-zA-Z]:\\)",
    re.I,
)
_SINGLE_STOCK_VALUATION_REPLY_TEMPLATE = {
    "version": "reply_template_v2",
    "template_ref": "single_stock_valuation_quality_v1",
    "reply_scope": "full_answer",
    "output_format": "markdown",
}
_GENERIC_LIVE_PAGE_REPLY_TEMPLATE = {
    "version": "reply_template_v2",
    "template_ref": "generic_live_page_delivery_v1",
    "reply_scope": "full_answer",
    "output_format": "markdown",
}
_REPLY_FOCUS = {
    "market_event_impact_v1": "先给出事件结论，再解释传导链、受益受损方向和验证指标。",
    "sector_theme_opportunity_v1": "先判断主题所处阶段，再解释催化、产业链位置、风险和跟踪指标。",
    "single_stock_valuation_quality_v1": "先判断估值水位，再判断盈利与现金流质量，最后给出风险条件。",
    "single_stock_deep_dive_v1": "围绕公司画像、经营质量、估值、催化与风险形成完整个股结论。",
    "multi_asset_compare_v1": "使用同口径表格比较核心指标，明确相对优势、短板和适用场景。",
    "capital_flow_quant_signal_v1": "先概括信号与资金结构，再说明有效区间、失效条件和风险。",
    "fund_etf_bond_profile_v1": "先说明产品定位与风险收益特征，再解释持仓、流动性和适用场景。",
    "hk_us_overseas_asset_v1": "先说明海外资产核心驱动，再覆盖估值、汇率、流动性与事件风险。",
    "generic_live_page_delivery_v1": "概括活页用途、核心模块、当前可见结论、使用方法和能力边界。",
}
_PAGE_CONTEXT_SUMMARY = {
    "market_event_impact_v1": "用于呈现宏观市场、事件影响与跨资产传导的实时分析活页。",
    "sector_theme_opportunity_v1": "用于呈现行业或主题强弱、标的池、催化与风险的实时分析活页。",
    "single_stock_valuation_quality_v1": "用于呈现单只上市公司的估值水位与财务质量分析活页。",
    "single_stock_deep_dive_v1": "用于呈现单只上市公司的经营、估值、资金与风险综合分析活页。",
    "multi_asset_compare_v1": "用于呈现多个标的或资产的同口径比较与风险收益分析活页。",
    "capital_flow_quant_signal_v1": "用于呈现资金结构、量化信号、策略表现与失效条件的实时活页。",
    "fund_etf_bond_profile_v1": "用于呈现基金、ETF或债券产品的收益、估值、持仓与风险活页。",
    "hk_us_overseas_asset_v1": "用于呈现港股、美股或海外资产的行情、财务、估值与事件活页。",
    "generic_live_page_delivery_v1": "用于呈现当前页面的核心模块、实时输出与能力边界。",
}


def _record_url(record):
    if not isinstance(record, dict):
        return ""
    return record.get("download_url") or record.get("public_url") or record.get("url") or ""


def _agent_reply_template_metadata(value):
    if not isinstance(value, dict):
        return value
    out = {k: value.get(k) for k in _REPLY_TEMPLATE_FIELDS if k in value}
    if isinstance(out.get("hybrid_composition"), dict):
        out["hybrid_composition"] = dict(out["hybrid_composition"])
    return out


def _page_context_metadata(value):
    if not isinstance(value, dict):
        return value
    out = {k: value.get(k) for k in _PAGE_CONTEXT_FIELDS if k in value}
    for key in ("core_sections", "primary_outputs"):
        if isinstance(out.get(key), list):
            out[key] = list(out[key])
    return out


def _reply_contract_binding_metadata(value):
    if not isinstance(value, dict):
        return value
    return {k: value.get(k) for k in _REPLY_CONTRACT_BINDING_FIELDS if k in value}


def _normalize_reply_contract_binding(value):
    if value is None or value == {}:
        return None, None
    if not isinstance(value, dict):
        return None, {"code": 1, "message": "reply_contract_binding 必须是对象、null 或空对象"}
    normalized = {
        "version": str(value.get("version") or "").strip(),
        "profile_ref": str(value.get("profile_ref") or "").strip(),
        "revision": str(value.get("revision") or "").strip(),
        "managed_by": str(value.get("managed_by") or "").strip(),
    }
    if normalized["version"] != "reply_contract_binding_v1":
        return None, {"code": 1, "message": "reply_contract_binding.version 目前只支持 reply_contract_binding_v1"}
    for key in ("profile_ref", "revision"):
        if not _REPLY_TEMPLATE_ID_RE.match(normalized[key]):
            return None, {"code": 1, "message": f"reply_contract_binding.{key} 必须是稳定 id"}
    if normalized["managed_by"] not in ("manual", "system"):
        return None, {"code": 1, "message": "reply_contract_binding.managed_by 只能是 manual 或 system"}
    return normalized, None


def _normalize_agent_reply_template(value, *, require_local_file=True):
    if value is None or value == {}:
        return None, None
    if not isinstance(value, dict):
        return None, {"code": 1, "message": "agent_reply_template 必须是对象、null 或空对象"}
    version = str(value.get("version") or "reply_template_v1").strip()
    template_ref = str(value.get("template_ref") or "").strip()
    reply_scope = str(value.get("reply_scope") or "").strip()
    output_format = str(value.get("output_format") or "").strip()
    if version not in _REPLY_TEMPLATE_VERSIONS:
        return None, {"code": 1, "message": "agent_reply_template.version 只支持 reply_template_v1 / reply_template_v2"}
    if not template_ref:
        return None, {"code": 1, "message": "agent_reply_template.template_ref 必填"}
    template_file = _reply_template_path(template_ref)
    if not template_file:
        return None, {
            "code": 1,
            "message": "agent_reply_template.template_ref 只能使用 reply-templates/ 下的稳定 id",
            "template_ref": template_ref,
        }
    if require_local_file and not os.path.isfile(template_file):
        return None, {
            "code": 1,
            "message": "agent_reply_template.template_ref 对应的本地回复模板不存在",
            "template_ref": template_ref,
            "template_file": template_file,
        }
    if reply_scope not in _REPLY_SCOPES:
        return None, {"code": 1, "message": "agent_reply_template.reply_scope 只能是 full_answer 或 hybrid"}
    if output_format != "markdown":
        return None, {"code": 1, "message": "agent_reply_template.output_format 目前只支持 markdown"}
    normalized = {
        "version": version,
        "template_ref": template_ref,
        "reply_scope": reply_scope,
        "output_format": output_format,
    }
    composition = value.get("hybrid_composition")
    if version == "reply_template_v2" and reply_scope == "hybrid":
        if not isinstance(composition, dict):
            return None, {"code": 1, "message": "reply_template_v2 的 hybrid 必须提供 hybrid_composition"}
        comp_version = str(composition.get("version") or _HYBRID_COMPOSITION_VERSION).strip()
        strategy_ref = str(composition.get("strategy_ref") or "").strip()
        prompt = str(composition.get("prompt") or "").strip()
        if comp_version != _HYBRID_COMPOSITION_VERSION:
            return None, {"code": 1, "message": "hybrid_composition.version 目前只支持 hybrid_composition_v1"}
        if not _REPLY_TEMPLATE_ID_RE.match(strategy_ref):
            return None, {"code": 1, "message": "hybrid_composition.strategy_ref 必须是稳定 id"}
        if not prompt or len(prompt) > 2000:
            return None, {"code": 1, "message": "hybrid_composition.prompt 必填且不超过 2000 字符"}
        normalized["hybrid_composition"] = {
            "version": comp_version,
            "strategy_ref": strategy_ref,
            "prompt": prompt,
        }
    elif version == "reply_template_v2" and composition is not None:
        return None, {"code": 1, "message": "full_answer 不应携带 hybrid_composition"}
    if len(json.dumps(normalized, ensure_ascii=False).encode("utf-8")) > _MAX_REPLY_METADATA_BYTES:
        return None, {"code": 1, "message": "agent_reply_template 总大小不能超过 8KB"}
    return normalized, None


def _normalize_page_context(value):
    if value is None or value == {}:
        return None, None
    if not isinstance(value, dict):
        return None, {"code": 1, "message": "page_context 必须是对象、null 或空对象"}
    version = str(value.get("version") or _PAGE_CONTEXT_VERSION).strip()
    if version != _PAGE_CONTEXT_VERSION:
        return None, {"code": 1, "message": "page_context.version 目前只支持 page_context_v1"}
    summary = str(value.get("summary") or "").strip()
    if not summary:
        return None, {"code": 1, "message": "page_context.summary 必填"}
    normalized = {"version": version, "summary": summary}
    for key in ("core_sections", "primary_outputs"):
        raw = value.get(key)
        if raw is None:
            continue
        if not isinstance(raw, list):
            return None, {"code": 1, "message": f"page_context.{key} 必须是字符串数组"}
        if len(raw) > _MAX_PAGE_CONTEXT_ITEMS:
            return None, {"code": 1, "message": f"page_context.{key} 最多 {_MAX_PAGE_CONTEXT_ITEMS} 项"}
        items = []
        for item in raw:
            text = str(item or "").strip()
            if not text or len(text) > _MAX_PAGE_CONTEXT_ITEM:
                return None, {"code": 1, "message": f"page_context.{key} 每项必须非空且不超过 {_MAX_PAGE_CONTEXT_ITEM} 字符"}
            if text not in items:
                items.append(text)
        normalized[key] = items
    for key in ("summary", "reply_focus", "limitations"):
        text = str(value.get(key) or "").strip()
        if key == "summary":
            text = summary
        if len(text) > _MAX_PAGE_CONTEXT_TEXT:
            return None, {"code": 1, "message": f"page_context.{key} 不能超过 {_MAX_PAGE_CONTEXT_TEXT} 字符"}
        if text:
            normalized[key] = text
    serialized = json.dumps(normalized, ensure_ascii=False)
    if _PAGE_CONTEXT_SENSITIVE_RE.search(serialized):
        return None, {"code": 1, "message": "page_context 不能包含凭证、Bearer token 或本地绝对路径"}
    if len(serialized.encode("utf-8")) > _MAX_PAGE_CONTEXT_BYTES:
        return None, {"code": 1, "message": "page_context 总大小不能超过 8KB"}
    return normalized, None


def _strip_html_text(value):
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    text = html_lib.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _page_headings(html):
    headings = []
    for match in re.finditer(r"<h([2-3])\b([^>]*)>(.*?)</h\1>", str(html or ""), re.I | re.S):
        attrs = match.group(2)
        if re.search(r"\bid\s*=\s*(['\"])sharePosterTitle\1", attrs, re.I):
            continue
        text = _strip_html_text(match.group(3))
        if text and text not in headings and len(text) <= _MAX_PAGE_CONTEXT_ITEM:
            headings.append(text)
        if len(headings) >= 8:
            break
    return headings


def _infer_page_context_from_publish_params(params, *, html=None, template_ref=None):
    params = params or {}
    sections = _page_headings(html)
    if not sections:
        sections = list(_tag_names(params.get("paradigm_tags")))[:5]
    if not sections:
        sections = ["核心判断", "关键指标", "风险与限制"]
    raw_outputs = params.get("primary_outputs") or params.get("required_outputs") or params.get("card_required_outputs")
    outputs = []
    if isinstance(raw_outputs, list):
        outputs = [str(item).strip() for item in raw_outputs if str(item).strip()][:_MAX_PAGE_CONTEXT_ITEMS]
    if not outputs:
        outputs = ["页面核心结论", "关键指标解释", "公开活页链接"]
    context = {
        "version": _PAGE_CONTEXT_VERSION,
        "summary": _PAGE_CONTEXT_SUMMARY.get(template_ref, _PAGE_CONTEXT_SUMMARY["generic_live_page_delivery_v1"]),
        "core_sections": sections,
        "primary_outputs": outputs,
        "reply_focus": _REPLY_FOCUS.get(template_ref, _REPLY_FOCUS["generic_live_page_delivery_v1"]),
        "limitations": "仅依据活页当前可用数据解释；缺失字段标记为 --，不编造数据或提供保证性预测。",
    }
    normalized, error = _normalize_page_context(context)
    return None if error else normalized


def _tag_names(value):
    names = set()
    for item in value or []:
        if isinstance(item, str):
            name = item.strip()
        elif isinstance(item, dict):
            name = str(item.get("name") or "").strip()
        else:
            name = ""
        if name:
            names.add(name)
    return names


def _infer_agent_reply_template_from_publish_params(params):
    """Infer only high-confidence reply-template routes from publish metadata.

    This is deliberately narrower than the Agent's semantic routing. It exists
    as a fail-safe for final publication, where silently returning a generic
    publish summary is worse than attaching the known reply contract.
    """
    if not isinstance(params, dict):
        return None
    scene_tags = _tag_names(params.get("scene_tags"))
    paradigm_tags = _tag_names(params.get("paradigm_tags"))
    text = " ".join(str(params.get(key) or "") for key in ("title", "description", "user_query"))
    valuation_signal = any(token in text for token in ("估值", "PE", "PB", "PCF", "市盈率", "市净率"))
    quality_signal = any(token in text for token in ("财务", "质量", "盈利", "ROE", "现金流", "负债率"))
    valuation_paradigm = bool(paradigm_tags & {"盈利质量", "价值陷阱"})
    comparative_signal = any(token in text for token in ("行业", "板块", "组合", "对比", "比较", "多资产"))
    if (valuation_paradigm or (valuation_signal and quality_signal)) and not comparative_signal:
        return dict(_SINGLE_STOCK_VALUATION_REPLY_TEMPLATE)
    routes = [
        ("market_event_impact_v1", ("宏观", "事件", "政策", "新规", "财报事件", "基差", "盘前")),
        ("multi_asset_compare_v1", ("对比", "比较", "同业", "组合", "多资产", "A/H", "溢价")),
        ("sector_theme_opportunity_v1", ("行业", "主题", "主线", "产业链", "赛道", "轮动", "拥挤度")),
        ("capital_flow_quant_signal_v1", ("资金", "量化", "信号", "动量", "多因子", "涨跌停", "RSRS", "异动")),
        ("fund_etf_bond_profile_v1", ("基金", "ETF", "债券", "转债", "固收")),
        ("hk_us_overseas_asset_v1", ("港股", "美股", "海外", "英伟达", "纳斯达克", "汇率")),
    ]
    for template_ref, tokens in routes:
        if any(token in text for token in tokens):
            return {
                "version": "reply_template_v2",
                "template_ref": template_ref,
                "reply_scope": "full_answer",
                "output_format": "markdown",
            }
    if "看标的" in scene_tags or any(token in text for token in ("个股", "股票", "公司", "深度分析")):
        return {
            "version": "reply_template_v2",
            "template_ref": "single_stock_deep_dive_v1",
            "reply_scope": "full_answer",
            "output_format": "markdown",
        }
    return dict(_GENERIC_LIVE_PAGE_REPLY_TEMPLATE)


def _bool_param(value):
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def _resolve_publish_agent_reply_template(params, *, html=None):
    resolved = dict(params or {})
    explicit_template = "agent_reply_template" in resolved
    explicit_clear = explicit_template and resolved.get("agent_reply_template") in (None, {})
    required = _bool_param(resolved.get("require_agent_reply_template"))
    if explicit_clear:
        if required:
            return resolved, {"mode": "explicit_clear", "source_template_id": ""}, {
                "code": 1,
                "message": "publish_final 同时要求 Agent 回复模板并显式清空 agent_reply_template，参数冲突",
            }
        return resolved, {"mode": "explicit_clear", "source_template_id": ""}, None

    meta, meta_error = _normalize_agent_reply_template(resolved.get("agent_reply_template"))
    if meta_error:
        return resolved, {"mode": "invalid", "source_template_id": ""}, meta_error
    mode = "explicit" if isinstance(meta, dict) and meta.get("template_ref") else ""
    source_template_id = (
        resolved.get("source_template_id")
        or resolved.get("source_template_page_id")
        or ""
    )
    source_result = None

    source_record = {}
    if source_template_id:
        source_result = cmd_template({"page_id": source_template_id})
        if not (isinstance(source_result, dict) and source_result.get("code") == 0):
            source_message = (
                source_result.get("message")
                if isinstance(source_result, dict)
                else str(source_result or "")
            )
            return resolved, {
                "mode": "source_template_unavailable",
                "source_template_id": source_template_id,
            }, {
                "code": 1,
                "message": (
                    f"publish_final 无法读取 source_template_id={source_template_id}"
                    + (f": {source_message}" if source_message else "")
                ),
            }
        source_record = _template_record(source_result)
    if not mode and source_template_id:
        source_meta, source_meta_error = _normalize_agent_reply_template(source_record.get("agent_reply_template"))
        if not source_meta_error and isinstance(source_meta, dict) and source_meta.get("template_ref"):
            meta = source_meta
            mode = "source_template"

    if not mode:
        meta = _infer_agent_reply_template_from_publish_params(resolved)
        mode = "generic_fallback" if meta.get("template_ref") == "generic_live_page_delivery_v1" else "publish_metadata"

    if mode:
        resolved["agent_reply_template"] = meta

    explicit_page_context = "page_context" in resolved
    page_context, page_context_error = _normalize_page_context(resolved.get("page_context"))
    if page_context_error:
        return resolved, {"mode": mode or "invalid", "source_template_id": source_template_id}, page_context_error
    page_context_mode = "explicit" if page_context else ("explicit_clear" if explicit_page_context else "")
    if not explicit_page_context:
        page_context = _infer_page_context_from_publish_params(
            resolved,
            html=html,
            template_ref=meta.get("template_ref") if isinstance(meta, dict) else None,
        )
        if page_context:
            resolved["page_context"] = page_context
            page_context_mode = "regenerated"
    elif page_context:
        resolved["page_context"] = page_context

    if (
        isinstance(meta, dict)
        and meta.get("version") == "reply_template_v2"
        and meta.get("reply_scope") == "hybrid"
        and not page_context
    ):
        return resolved, {
            "mode": mode,
            "source_template_id": source_template_id,
            "page_context_mode": page_context_mode or "missing",
        }, {
            "code": 1,
            "message": "reply_template_v2 的 hybrid 正式发布必须提供当前活页重新生成的 page_context",
        }

    if required and not mode:
        error = {
            "code": 1,
            "message": "publish_final 要求 Agent 回复模板，但未能从参数、来源模板或页面 metadata 解析到模板",
            "source_template_id": source_template_id,
        }
        if isinstance(source_result, dict) and source_result.get("code") != 0:
            error["source_template"] = source_result
        return resolved, {"mode": "missing", "source_template_id": source_template_id}, error

    return resolved, {
        "mode": mode or "none",
        "source_template_id": source_template_id,
        "source_public_url": _record_url(source_record),
        "source_sha256": source_record.get("sha256") or "",
        "source_package_ids": source_record.get("package_ids") or [],
        "source_grant_ids": source_record.get("grant_ids") or [],
        "page_context_mode": page_context_mode or "none",
        "source_page_context_inherited": False,
    }, None


def _reply_template_path(template_ref):
    if not template_ref or not isinstance(template_ref, str):
        return ""
    if not _REPLY_TEMPLATE_ID_RE.match(template_ref):
        return ""
    return os.path.join(C.SKILL_ROOT, "reply-templates", template_ref + ".md")


def _agent_reply_template_contract(record, *, operation=None):
    if not isinstance(record, dict):
        return None
    meta, meta_error = _normalize_agent_reply_template(record.get("agent_reply_template"), require_local_file=False)
    if meta_error:
        return None
    meta = meta if isinstance(meta, dict) else {}
    template_ref = meta.get("template_ref") or ""
    template_file = _reply_template_path(template_ref)
    template_exists = bool(template_file and os.path.isfile(template_file))
    public_url = record.get("url") or record.get("public_url") or record.get("download_url") or ""
    page_context, _ = _normalize_page_context(record.get("page_context"))
    contract = {
        "terminal": True,
        "operation": operation or record.get("operation") or "",
        "page_id": record.get("page_id") or "",
        "required": bool(template_ref),
        "page_context": page_context,
        "public_url": public_url,
    }
    if template_ref:
        contract.update({
            "template_ref": template_ref,
            "template_file": template_file,
            "template_exists": template_exists,
            "reply_scope": meta.get("reply_scope") or "full_answer",
            "output_format": meta.get("output_format") or "markdown",
            "hybrid_composition": meta.get("hybrid_composition"),
            "final_response_required": "read_template_file_and_reply_in_template_format_plus_links",
            "final_response_steps": [
            "Read template_file before writing the final answer.",
            "Use that Markdown template as the final answer shape; do not replace it with a generic publish summary.",
            "Use page_context to understand what this page does; for hybrid replies also follow hybrid_composition.",
            "Include public_url.",
            "Fill missing data with -- instead of inventing values.",
            "Do not expose local file paths, api_key, signatures, or internal verification logs to the user.",
            ],
        })
    return contract


def _agent_reply_template_hint(record, *, resource_role):
    if not isinstance(record, dict):
        return None
    meta, meta_error = _normalize_agent_reply_template(record.get("agent_reply_template"), require_local_file=False)
    hint = {
        "terminal": False,
        "resource_role": resource_role,
        "page_context": _normalize_page_context(record.get("page_context"))[0],
    }
    if not meta_error and isinstance(meta, dict) and meta.get("template_ref"):
        hint.update({
            "template_ref": meta.get("template_ref"),
            "reply_scope": meta.get("reply_scope") or "full_answer",
            "output_format": meta.get("output_format") or "markdown",
            "hybrid_composition": meta.get("hybrid_composition"),
        })
    if resource_role == "source_template":
        hint["source_template_id"] = (
            record.get("source_template_id")
            or record.get("template_id")
            or record.get("page_id")
            or ""
        )
    return hint


def _attach_agent_reply_hint(record, *, resource_role):
    if not isinstance(record, dict):
        return record
    hint = _agent_reply_template_hint(record, resource_role=resource_role)
    if hint:
        record["agent_reply_hint"] = hint
    record.pop("agent_reply_contract", None)
    record.pop("agent_reply_template_file", None)
    return record


def _attach_agent_reply_contract(record, *, operation=None):
    if not isinstance(record, dict):
        return record
    contract = _agent_reply_template_contract(record, operation=operation)
    if not contract:
        return record
    record["agent_reply_contract"] = contract
    if contract.get("required"):
        record["agent_reply_template_file"] = contract.get("template_file") or ""
    else:
        record.pop("agent_reply_template_file", None)
    if contract.get("required") and not contract.get("template_exists"):
        _append_warning(record, {
            "type": "agent_reply_template_missing",
            "message": "agent_reply_template 指向的本地回复模板文件不存在，最终回复无法按模板生成",
            "template_ref": contract.get("template_ref"),
            "template_file": contract.get("template_file"),
        })
    return record


def _validate_agent_reply_template_param(params):
    if "agent_reply_template" not in params:
        return None
    _, error = _normalize_agent_reply_template(params.get("agent_reply_template"))
    return error


def _validate_page_context_param(params):
    if "page_context" not in params:
        return None
    _, error = _normalize_page_context(params.get("page_context"))
    return error


def _validate_reply_metadata_pair(params):
    template_error = _validate_agent_reply_template_param(params)
    if template_error:
        return template_error
    context_error = _validate_page_context_param(params)
    if context_error:
        return context_error
    if "reply_contract_binding" in params:
        _, binding_error = _normalize_reply_contract_binding(params.get("reply_contract_binding"))
        if binding_error:
            return binding_error
    template, _ = _normalize_agent_reply_template(params.get("agent_reply_template"))
    context, _ = _normalize_page_context(params.get("page_context"))
    if (
        template
        and template.get("version") == "reply_template_v2"
        and template.get("reply_scope") == "hybrid"
        and "page_context" in params
        and not context
    ):
        return {"code": 1, "message": "reply_template_v2 的 hybrid 必须同时提供非空 page_context"}
    return None


def _normalize_cover_response(out, *, reply_mode="none", resource_role="existing_page"):
    if not isinstance(out, dict):
        return out

    def attach_reply(record):
        if reply_mode == "terminal":
            _attach_agent_reply_contract(record)
        elif reply_mode == "hint":
            _attach_agent_reply_hint(record, resource_role=resource_role)

    attach_reply(out)
    data = out.get("data")
    if isinstance(data, dict):
        attach_reply(data)
        items = data.get("items")
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    attach_reply(item)
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                attach_reply(item)
    return out


def _template_record(out):
    if not isinstance(out, dict):
        return {}
    data = out.get("data")
    if isinstance(data, dict):
        for key in ("template", "item", "page"):
            if isinstance(data.get(key), dict):
                return data[key]
        return data
    return out

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


def _thumbnail_file_from_params(params):
    """Return optional thumbnail path from upload/update params."""
    for key in ("thumbnail_file", "thumbnail_image", "thumbnail_path"):
        value = params.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    value = params.get("thumbnail")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _result_message(out):
    if not isinstance(out, dict):
        return str(out)
    if out.get("message"):
        return str(out.get("message"))
    err = out.get("error")
    if isinstance(err, dict):
        return str(err.get("message") or err.get("code") or err)
    if err:
        return str(err)
    return json.dumps(out, ensure_ascii=False)[:500]


def _append_warning(out, warning):
    warnings = out.get("warnings")
    if not isinstance(warnings, list):
        warnings = []
    warnings.append(warning)
    out["warnings"] = warnings


def _attach_thumbnail_if_requested(out, params):
    """Upload thumbnail after HTML publish succeeds; never fail the publish result."""
    thumb_file = _thumbnail_file_from_params(params)
    if not thumb_file or not isinstance(out, dict) or out.get("code") != 0:
        return out
    page_id = out.get("page_id") or params.get("page_id")
    if not page_id:
        out["thumbnail_warning"] = "HTML 已发布，但响应里缺少 page_id，无法设置缩略图"
        _append_warning(out, {"type": "thumbnail_upload_skipped", "message": out["thumbnail_warning"]})
        return out

    thumb = cmd_thumbnail({"page_id": page_id, "image_file": thumb_file})
    out["thumbnail_upload"] = thumb
    if isinstance(thumb, dict) and thumb.get("code") == 0:
        out["thumbnail_url"] = thumb.get("thumbnail_url") or out.get("thumbnail_url") or ""
        return out

    message = _result_message(thumb)
    out["thumbnail_warning"] = f"HTML 已发布，但缩略图上传失败：{message}"
    _append_warning(out, {
        "type": "thumbnail_upload_failed",
        "message": message,
        "thumbnail_file": thumb_file,
    })
    return out


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
        r"\s*<div\b(?=[^>]*(?:id=[\"']qr[\"']|class=[\"'][^\"']*\bqr\b[^\"']*[\"']))[^>]*>[\s\S]*?手机扫码查看[\s\S]*?</div>",
        "",
        html,
        count=1,
    )
    if n:
        actions.append("removed_legacy_qr_div")

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
    short_pkg_re = re.compile(r'(?:["\']?id["\']?)\s*:\s*["\'](pkg_[^"\']+)["\']')
    short_sig_re = re.compile(r'(?:["\']?sig["\']?)\s*:\s*["\']([^"\']+)["\']')
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
    # Some published pages keep compact credential maps such as
    # `{id:'pkg_xxx',sig:'...'}`. Restrict the shorthand to pkg_ values so a
    # generic business object with id/sig fields cannot be mistaken for data credentials.
    for obj_match in re.finditer(r"\{[^{}]{0,4000}\}", html or "", flags=re.S):
        block = obj_match.group(0)
        pkg_match = short_pkg_re.search(block)
        sig_match = short_sig_re.search(block)
        if not (pkg_match and sig_match):
            continue
        key = (pkg_match.group(1), sig_match.group(1))
        if key not in seen:
            seen.add(key)
            pairs.append({"package_id": key[0], "signature": key[1]})
    return pairs


def _extract_grant_credentials(html):
    grant_re = re.compile(r'(?:["\']?(?:grant_id|grantId)["\']?)\s*:\s*["\']([^"\']+)["\']')
    sig_re = re.compile(r'(?:["\']?signature["\']?)\s*:\s*["\']([^"\']+)["\']')
    short_grant_re = re.compile(r'(?:["\']?id["\']?)\s*:\s*["\']((?:dg|grant)_[^"\']+)["\']')
    short_sig_re = re.compile(r'(?:["\']?sig["\']?)\s*:\s*["\']([^"\']+)["\']')
    pairs = []
    seen = set()
    for match in grant_re.finditer(html or ""):
        grant_id = match.group(1)
        window = html[max(0, match.start() - 500): min(len(html), match.end() + 1500)]
        sig_match = sig_re.search(window)
        signature = sig_match.group(1) if sig_match else ""
        key = (grant_id, signature)
        if key not in seen:
            seen.add(key)
            pairs.append({"grant_id": grant_id, "signature": signature})
    for obj_match in re.finditer(r"\{[^{}]{0,4000}\}", html or "", flags=re.S):
        block = obj_match.group(0)
        grant_match = short_grant_re.search(block)
        sig_match = short_sig_re.search(block)
        if not (grant_match and sig_match):
            continue
        key = (grant_match.group(1), sig_match.group(1))
        if key not in seen:
            seen.add(key)
            pairs.append({"grant_id": key[0], "signature": key[1]})
    return pairs


def _signature_hashes(html):
    signature_re = re.compile(r'(?:["\']?signature["\']?)\s*:\s*["\']([^"\']+)["\']')
    return sorted({
        hashlib.sha256(match.group(1).encode("utf-8")).hexdigest()
        for match in signature_re.finditer(html or "")
        if match.group(1)
    })


def _unique_strings(values):
    if values is None:
        return []
    if isinstance(values, str):
        values = [item.strip() for item in values.split(",")]
    elif not isinstance(values, (list, tuple, set)):
        values = [values]
    out = []
    seen = set()
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def _html_text(html):
    text = re.sub(r"(?is)<script\b[^>]*>.*?</script>", " ", html or "")
    text = re.sub(r"(?is)<style\b[^>]*>.*?</style>", " ", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html_lib.unescape(text)).strip()


def _html_headings(html, *, levels=(1, 2, 3)):
    headings = []
    seen = set()
    level_pattern = "|".join(str(int(level)) for level in levels)
    pattern = rf"(?is)<h(?:{level_pattern})\b[^>]*>(.*?)</h(?:{level_pattern})>"
    for match in re.finditer(pattern, html or ""):
        text = _html_text(match.group(1))
        if text and text not in seen:
            seen.add(text)
            headings.append(text)
    return headings


def _template_required_outputs(record):
    outputs = list(_unique_strings(record.get("card_required_outputs") or []))
    for package in record.get("packages") or []:
        if not isinstance(package, dict):
            continue
        for read in package.get("reads") or []:
            if isinstance(read, dict):
                output = str(read.get("output") or "").strip()
                if output and output not in outputs:
                    outputs.append(output)
        for formula in package.get("formulas") or []:
            if not isinstance(formula, str) or "=" not in formula:
                continue
            output = formula.split("=", 1)[0].strip().strip('"\'')
            if output and re.match(r"^[^()\s+\-*/]+$", output) and output not in outputs:
                outputs.append(output)
    return outputs


def _fork_path(value, *, base=None):
    path = str(value or "").strip()
    if not path:
        return ""
    if os.path.isabs(path):
        return os.path.abspath(path)
    return os.path.abspath(os.path.join(base or C.SKILL_ROOT, path))


def _fork_task_id(params):
    params = params if isinstance(params, dict) else {}
    context = C.current_trace_context()
    return str(params.get("task_id") or context.get("task_id") or "").strip()


def _fork_binding_root():
    override = str(os.environ.get("QBV_FORK_BINDING_DIR") or "").strip()
    if override:
        return os.path.abspath(override)
    return os.path.join(C.SKILL_ROOT, "output", "fork_task_bindings")


def _fork_binding_path(task_id):
    digest = hashlib.sha256(str(task_id or "").encode("utf-8")).hexdigest()
    return os.path.join(_fork_binding_root(), digest + ".json")


def _write_fork_task_binding(binding):
    task_id = str((binding or {}).get("task_id") or "").strip()
    if not task_id:
        return None, {"code": 1, "message": "fork task binding 缺少 task_id"}
    root = _fork_binding_root()
    path = _fork_binding_path(task_id)
    os.makedirs(root, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=".fork-binding-", suffix=".json", dir=root)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(binding, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temp_path, path)
    except Exception as exc:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        return None, {"code": 1, "message": f"写入 fork task binding 失败: {exc}"}
    return path, None


def _read_fork_task_binding(task_id):
    task_id = str(task_id or "").strip()
    if not task_id:
        return None, "", None
    path = _fork_binding_path(task_id)
    if not os.path.isfile(path):
        return None, path, None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            binding = json.load(handle)
    except Exception as exc:
        return None, path, {"code": 1, "message": f"读取 fork task binding 失败: {exc}"}
    if not isinstance(binding, dict) or binding.get("version") != _FORK_TASK_BINDING_VERSION:
        return None, path, {"code": 1, "message": "fork task binding 版本无效"}
    if str(binding.get("task_id") or "") != task_id:
        return None, path, {"code": 1, "message": "fork task binding 的 task_id 不一致"}
    return binding, path, None


def _bind_fork_task(params, manifest, manifest_file):
    task_id = _fork_task_id(params)
    if not task_id:
        return {
            "mode": "not_bound",
            "reason": "task_id_missing",
            "instruction": "正式 fork 流程必须传 task_id，才能让 publish_final 自动恢复来源门禁",
        }, None
    previous, _, read_error = _read_fork_task_binding(task_id)
    if read_error:
        return None, read_error
    binding = {
        "version": _FORK_TASK_BINDING_VERSION,
        "status": "prepared",
        "task_id": task_id,
        "source_template_id": str(manifest.get("source_template_id") or ""),
        "fork_manifest_file": os.path.abspath(manifest_file),
        "source_html_sha256": str(manifest.get("source_html_sha256") or ""),
        "source_url": str(manifest.get("source_url") or ""),
        "target_asset": str(manifest.get("target_asset") or ""),
        "working_html_file": os.path.abspath(str(manifest.get("working_html_file") or "")),
        "revision": int((previous or {}).get("revision") or 0) + 1,
        "bound_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
    }
    if previous and previous.get("source_template_id") != binding["source_template_id"]:
        binding["previous_source_template_id"] = previous.get("source_template_id")
    binding_file, write_error = _write_fork_task_binding(binding)
    if write_error:
        return None, write_error
    return {
        "mode": "task_binding",
        "status": binding["status"],
        "task_id": task_id,
        "source_template_id": binding["source_template_id"],
        "binding_file": binding_file,
        "revision": binding["revision"],
        "working_html_file": binding["working_html_file"],
    }, None


def _apply_fork_task_binding(params):
    resolved = dict(params or {})
    task_id = _fork_task_id(resolved)
    binding, binding_file, read_error = _read_fork_task_binding(task_id)
    if read_error:
        return resolved, None, read_error
    if not binding:
        return resolved, {"mode": "none", "task_id": task_id}, None

    bound_source = str(binding.get("source_template_id") or "")
    bound_manifest_file = os.path.abspath(str(binding.get("fork_manifest_file") or ""))
    explicit_source = str(
        resolved.get("source_template_id")
        or resolved.get("source_template_page_id")
        or ""
    )
    if explicit_source and explicit_source != bound_source:
        return resolved, None, {
            "code": 1,
            "error": "FORK_TASK_BINDING_CONFLICT",
            "message": (
                f"task_id={task_id} 已绑定来源 {bound_source}，"
                f"publish_final 不能改为 {explicit_source}"
            ),
        }

    explicit_manifest_file = str(resolved.get("fork_manifest_file") or "").strip()
    if explicit_manifest_file:
        explicit_manifest_file = _fork_path(explicit_manifest_file)
        if explicit_manifest_file != bound_manifest_file:
            return resolved, None, {
                "code": 1,
                "error": "FORK_TASK_BINDING_CONFLICT",
                "message": "publish_final 的 fork_manifest_file 与 task_id 已绑定文件不一致",
            }

    inline_manifest = resolved.get("fork_manifest")
    if inline_manifest is not None:
        try:
            with open(bound_manifest_file, "r", encoding="utf-8") as handle:
                bound_manifest = json.load(handle)
        except Exception as exc:
            return resolved, None, {"code": 1, "message": f"读取 task_id 绑定 manifest 失败: {exc}"}
        if inline_manifest != bound_manifest:
            return resolved, None, {
                "code": 1,
                "error": "FORK_TASK_BINDING_CONFLICT",
                "message": "publish_final 的内联 fork_manifest 与 task_id 已绑定 manifest 不一致",
            }
        resolved.pop("fork_manifest", None)

    resolved["source_template_id"] = bound_source
    resolved["fork_manifest_file"] = bound_manifest_file
    return resolved, {
        "mode": "task_binding",
        "status": binding.get("status") or "prepared",
        "task_id": task_id,
        "source_template_id": bound_source,
        "binding_file": binding_file,
        "fork_manifest_file": bound_manifest_file,
        "source_injected": not bool(explicit_source),
        "manifest_injected": not bool(explicit_manifest_file),
        "revision": binding.get("revision") or 1,
    }, None


def _mark_fork_task_published(binding_resolution, *, page_id, public_url):
    if not isinstance(binding_resolution, dict) or binding_resolution.get("mode") != "task_binding":
        return binding_resolution, None
    task_id = str(binding_resolution.get("task_id") or "")
    binding, _, read_error = _read_fork_task_binding(task_id)
    if read_error or not binding:
        return binding_resolution, read_error or {"code": 1, "message": "fork task binding 发布后丢失"}
    binding["status"] = "published"
    binding["page_id"] = str(page_id or "")
    binding["public_url"] = str(public_url or "")
    binding["published_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    binding_file, write_error = _write_fork_task_binding(binding)
    if write_error:
        return binding_resolution, write_error
    out = dict(binding_resolution)
    out["status"] = "published"
    out["binding_file"] = binding_file
    out["page_id"] = binding["page_id"]
    return out, None


def _load_fork_manifest(params):
    inline = params.get("fork_manifest")
    manifest_file = params.get("fork_manifest_file")
    if isinstance(inline, dict):
        return dict(inline), "", None
    if not manifest_file:
        return None, "", {"code": 1, "message": "带 source_template_id 的 publish_final 必须提供 fork_manifest 或 fork_manifest_file"}
    path = _fork_path(manifest_file)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            manifest = json.load(handle)
    except Exception as exc:
        return None, path, {"code": 1, "message": f"读取 fork_manifest 失败: {exc}"}
    if not isinstance(manifest, dict):
        return None, path, {"code": 1, "message": "fork_manifest 必须是 JSON 对象"}
    return manifest, path, None


def _validate_fork_manifest(params, template_resolution, final_html):
    source_template_id = str((template_resolution or {}).get("source_template_id") or "")
    if not source_template_id:
        return None, None

    manifest, manifest_file, error = _load_fork_manifest(params)
    if error:
        return None, error
    if manifest.get("version") != _FORK_MANIFEST_VERSION:
        return None, {"code": 1, "message": f"fork_manifest.version 必须是 {_FORK_MANIFEST_VERSION}"}
    if str(manifest.get("source_template_id") or "") != source_template_id:
        return None, {"code": 1, "message": "fork_manifest 的 source_template_id 与 publish_final 不一致"}

    source_file = _fork_path(manifest.get("source_html_file"))
    expected_sha = str(manifest.get("source_html_sha256") or "").strip().lower()
    if not source_file or not os.path.isfile(source_file):
        return None, {"code": 1, "message": "fork_manifest 缺少可读取的 source_html_file"}
    try:
        with open(source_file, "r", encoding="utf-8") as handle:
            source_html = handle.read()
    except Exception as exc:
        return None, {"code": 1, "message": f"读取 fork 来源 HTML 失败: {exc}"}
    actual_sha = hashlib.sha256(source_html.encode("utf-8")).hexdigest()
    if not expected_sha or actual_sha != expected_sha:
        return None, {"code": 1, "message": "fork_manifest 的来源 HTML SHA256 校验失败"}
    template_sha = str((template_resolution or {}).get("source_sha256") or "").strip().lower()
    if template_sha and actual_sha != template_sha:
        return None, {"code": 1, "message": "fork 来源 HTML SHA256 与模板 metadata 不一致"}

    source_url = str((template_resolution or {}).get("source_public_url") or "").strip().rstrip("/")
    manifest_url = str(manifest.get("source_url") or "").strip().rstrip("/")
    if source_url and manifest_url and source_url != manifest_url:
        return None, {"code": 1, "message": "fork_manifest 的 source_url 与来源模板不一致"}

    manifest_packages = set(_unique_strings(manifest.get("source_package_ids")))
    manifest_grants = set(_unique_strings(manifest.get("source_grant_ids")))
    manifest_signature_hashes = set(_unique_strings(manifest.get("source_signature_sha256")))
    html_packages = {item["package_id"] for item in _extract_package_credentials(source_html)}
    html_grants = {item["grant_id"] for item in _extract_grant_credentials(source_html)}
    html_signature_hashes = set(_signature_hashes(source_html))
    source_packages = set((template_resolution or {}).get("source_package_ids") or [])
    source_grants = set((template_resolution or {}).get("source_grant_ids") or [])
    if source_packages and not source_packages.issubset(manifest_packages):
        return None, {"code": 1, "message": "fork_manifest 的来源 package_ids 与模板 metadata 不一致"}
    if source_grants and not source_grants.issubset(manifest_grants):
        return None, {"code": 1, "message": "fork_manifest 的来源 grant_ids 与模板 metadata 不一致"}
    if html_packages and not html_packages.issubset(manifest_packages):
        return None, {"code": 1, "message": "fork_manifest 未完整记录来源 HTML 的 package_ids"}
    if html_grants and not html_grants.issubset(manifest_grants):
        return None, {"code": 1, "message": "fork_manifest 未完整记录来源 HTML 的 grant_ids"}
    if html_signature_hashes != manifest_signature_hashes:
        return None, {"code": 1, "message": "fork_manifest 未完整记录来源 HTML 的 signature 指纹"}
    try:
        minimum_packages = int(manifest.get("minimum_target_package_count", len(manifest_packages)) or 0)
        minimum_grants = int(manifest.get("minimum_target_grant_count", len(manifest_grants)) or 0)
    except (TypeError, ValueError):
        return None, {"code": 1, "message": "fork_manifest 的最低 package/grant 数量必须是非负整数"}
    if minimum_packages < 0 or minimum_grants < 0:
        return None, {"code": 1, "message": "fork_manifest 的最低 package/grant 数量必须是非负整数"}
    reduction_reason = str(manifest.get("credential_count_reduction_reason") or "").strip()
    if (
        minimum_packages < len(manifest_packages)
        or minimum_grants < len(manifest_grants)
    ) and not reduction_reason:
        return None, {
            "code": 1,
            "message": "fork_manifest 下调最低凭证数量时必须提供 credential_count_reduction_reason",
        }

    leaked_packages = sorted(package_id for package_id in manifest_packages if package_id in (final_html or ""))
    leaked_grants = sorted(grant_id for grant_id in manifest_grants if grant_id in (final_html or ""))
    leaked_signatures = sorted(set(_signature_hashes(final_html)) & manifest_signature_hashes)
    if leaked_packages or leaked_grants or leaked_signatures:
        leaked = leaked_packages + leaked_grants
        if leaked_signatures:
            leaked.append(f"signature({len(leaked_signatures)})")
        return None, {"code": 1, "message": "fork 目标 HTML 仍含来源凭证: " + ", ".join(leaked)}

    visible_text = _html_text(final_html)
    missing_sections = [
        section for section in _unique_strings(manifest.get("required_sections"))
        if section not in visible_text
    ]
    if missing_sections:
        return None, {"code": 1, "message": "fork 目标 HTML 缺少核心栏目: " + ", ".join(missing_sections)}

    missing_outputs = [
        output for output in _unique_strings(manifest.get("required_outputs"))
        if output not in (final_html or "")
    ]
    if missing_outputs:
        return None, {"code": 1, "message": "fork 目标 HTML 缺少必需输出: " + ", ".join(missing_outputs)}

    leftover_markers = [
        marker for marker in _unique_strings(manifest.get("source_markers"))
        if marker in (final_html or "")
    ]
    if leftover_markers:
        return None, {"code": 1, "message": "fork 目标 HTML 仍含来源标的文案: " + ", ".join(leftover_markers)}

    if manifest.get("card_runtime_required"):
        required_tokens = ("data-qb-card-template", "data-qb-card-manifest", "data-qb-card-runtime")
        if any(token not in (final_html or "") for token in required_tokens):
            return None, {"code": 1, "message": "fork 来源包含 Card Runtime，但目标 HTML 未保留完整 artifact"}

    summary = {
        "version": manifest.get("version"),
        "manifest_file": manifest_file,
        "source_template_id": source_template_id,
        "source_url": manifest_url or source_url,
        "source_html_file": source_file,
        "source_html_sha256": actual_sha,
        "source_package_ids": sorted(manifest_packages),
        "source_grant_ids": sorted(manifest_grants),
        "source_signature_sha256": sorted(manifest_signature_hashes),
        "minimum_target_package_count": minimum_packages,
        "minimum_target_grant_count": minimum_grants,
        "credential_count_reduction_reason": reduction_reason,
        "required_sections": _unique_strings(manifest.get("required_sections")),
        "required_outputs": _unique_strings(manifest.get("required_outputs")),
        "card_runtime_required": bool(manifest.get("card_runtime_required")),
    }
    return summary, None


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
    reply_resolution = None
    if not params.get("_suppress_agent_reply_fallback"):
        params, reply_resolution, reply_error = _resolve_publish_agent_reply_template(params, html=html)
        if reply_error:
            return reply_error
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
    card_runtime_verification = _maybe_verify_card_runtime(html, params)
    if isinstance(card_runtime_verification, dict) and not card_runtime_verification.get("ok"):
        return {
            "code": 1,
            "message": card_runtime_verification.get("message") or "card runtime artifact 验收未通过",
            "card_runtime_verification": card_runtime_verification,
        }
    metadata_err = _validate_reply_metadata_pair(params)
    if metadata_err:
        return metadata_err

    body = {"html": html}
    for k in ("title", "description", "ttl_days", "scene_tags", "paradigm_tags", "user_query", "tagging_method", "tagging_source", "tagging_meta", "page_context", "agent_reply_template", "reply_contract_binding"):
        if params.get(k) is not None:
            body[k] = params[k]
    if "page_context" in params and params.get("page_context") is None:
        body["page_context"] = None
    if "reply_contract_binding" in params and params.get("reply_contract_binding") is None:
        body["reply_contract_binding"] = None
    if "agent_reply_template" in params and params.get("agent_reply_template") is None:
        body["agent_reply_template"] = None
    out = C.http_json("POST", C.api_url(endpoint, _PATH["upload"]),
                      C.headers(api_key), body, timeout=_UPLOAD_TIMEOUT)
    if isinstance(out, dict):
        if reply_resolution:
            out["agent_reply_template_resolution"] = reply_resolution
        out["share_shell"] = shell_check
        if card_runtime_verification:
            out["card_runtime_verification"] = card_runtime_verification
        if out.get("code") == 0 or _server_mentions_package_issue(out):
            out["_package_runtime_check"] = _package_runtime_check(
                endpoint,
                html,
                force=bool(params.get("verify_packages")),
                publish_out=out,
            )
        out = _attach_thumbnail_if_requested(out, params)
        if out.get("code") == 0:
            _attach_agent_reply_contract(out, operation="upload")
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
    card_runtime_verification = _maybe_verify_card_runtime(html, params)
    if isinstance(card_runtime_verification, dict) and not card_runtime_verification.get("ok"):
        return {
            "code": 1,
            "message": card_runtime_verification.get("message") or "card runtime artifact 验收未通过",
            "card_runtime_verification": card_runtime_verification,
        }
    metadata_err = _validate_reply_metadata_pair(params)
    if metadata_err:
        return metadata_err

    body = {"page_id": params["page_id"], "html": html}
    for k in ("title", "description", "ttl_days", "scene_tags", "paradigm_tags", "user_query", "tagging_method", "tagging_source", "tagging_meta", "page_context", "agent_reply_template", "reply_contract_binding"):
        if params.get(k) is not None:
            body[k] = params[k]
    if "page_context" in params and params.get("page_context") is None:
        body["page_context"] = None
    if "reply_contract_binding" in params and params.get("reply_contract_binding") is None:
        body["reply_contract_binding"] = None
    if "agent_reply_template" in params and params.get("agent_reply_template") is None:
        body["agent_reply_template"] = None
    out = C.http_json("POST", C.api_url(endpoint, _PATH["update"]),
                      C.headers(api_key), body, timeout=_UPLOAD_TIMEOUT)
    if isinstance(out, dict):
        out["share_shell"] = shell_check
        if card_runtime_verification:
            out["card_runtime_verification"] = card_runtime_verification
        if out.get("code") == 0 or _server_mentions_package_issue(out):
            out["_package_runtime_check"] = _package_runtime_check(
                endpoint,
                html,
                force=bool(params.get("verify_packages")),
                publish_out=out,
            )
        out = _attach_thumbnail_if_requested(out, params)
        if out.get("code") == 0:
            _attach_agent_reply_contract(out, operation="update")
    return out


def _progress_state_and_html(params):
    state = PP.build_state(params)
    render_params = dict(params or {})
    render_params["updated_at"] = state["updated_at"]
    return state, PP.render_progress_html(render_params)


def _validate_progress_params(params):
    if str((params or {}).get("page_status") or "running").strip().lower() != "waiting_input":
        return None
    required_input = params.get("required_input")
    required_fields = ("id", "prompt", "resume_step")
    missing = [
        field for field in required_fields
        if not isinstance(required_input, dict) or not str(required_input.get(field) or "").strip()
    ]
    if missing:
        return {
            "code": 1,
            "error": "PROGRESS_INPUT_REQUIRED",
            "message": "waiting_input 需要 required_input.id、prompt 和 resume_step",
            "missing": missing,
        }
    return None


def _validate_progress_evidence(params):
    params = params or {}
    task_id = _fork_task_id(params)
    current_step = str(params.get("current_step") or "").strip()
    page_status = str(params.get("page_status") or "running").strip().lower()
    guarded_steps = {"package_register", "html_build", "verify", "final_publish"}
    if not task_id or current_step not in guarded_steps or page_status in ("failed", "waiting_input"):
        return None
    if str(params.get("validation_not_required_reason") or "").strip():
        return None

    receipt_files = params.get("validation_receipt_files")
    if isinstance(receipt_files, str):
        receipt_files = [receipt_files]
    if not isinstance(receipt_files, list) or not receipt_files:
        return {
            "code": 1,
            "error": "PROGRESS_EVIDENCE_REQUIRED",
            "message": f"task_id={task_id} 推进到 {current_step} 前需要已完成的验证收据",
        }

    invalid = []
    valid_count = 0
    for raw_path in receipt_files:
        path = _fork_path(raw_path)
        try:
            with open(path, "r", encoding="utf-8") as handle:
                receipt = json.load(handle)
        except Exception as exc:
            invalid.append({"file": path, "reason": f"read_failed: {exc}"})
            continue
        ok = (
            isinstance(receipt, dict)
            and receipt.get("version") == _VALIDATION_RECEIPT_VERSION
            and str(receipt.get("task_id") or "") == task_id
            and receipt.get("status") == "completed"
            and receipt.get("success") is True
            and not receipt.get("failures")
        )
        if ok:
            valid_count += 1
        else:
            invalid.append({
                "file": path,
                "reason": "receipt must match task_id and be completed success with no failures",
            })
    if invalid or valid_count == 0:
        return {
            "code": 1,
            "error": "PROGRESS_EVIDENCE_INVALID",
            "message": "验证收据失败、仍在排队或与当前 task_id 不一致，拒绝推进进度",
            "invalid_receipts": invalid,
        }
    return None


def _progress_publish_payload(params, html, *, require_page_id=False):
    payload = {"html": html}
    if require_page_id:
        payload["page_id"] = params.get("page_id")
    payload["ensure_share_shell"] = params.get("ensure_share_shell", True)
    payload["theme"] = params.get("theme") if isinstance(params.get("theme"), dict) else dict(_PROGRESS_SHELL_THEME)
    payload["_suppress_agent_reply_fallback"] = True
    # 进度快照不是正式业务页面，显式空标签可阻止服务端对临时文案异步自动打标。
    payload["scene_tags"] = params.get("scene_tags") if "scene_tags" in params else []
    payload["paradigm_tags"] = params.get("paradigm_tags") if "paradigm_tags" in params else []

    for k in (
        "ttl_days",
        "scene_tags",
        "paradigm_tags",
        "user_query",
        "tagging_method",
        "tagging_source",
        "tagging_meta",
        "page_context",
        "agent_reply_template",
    ):
        if params.get(k) is not None:
            payload[k] = params[k]
    if params.get("title") is not None:
        payload["title"] = params["title"]
    elif not require_page_id:
        payload["title"] = "活页生成中"
    if params.get("description") is not None:
        payload["description"] = params["description"]
    elif not require_page_id:
        payload["description"] = "活页生成进度，最终内容会在同一个链接显示。"
    return payload


def _attach_progress_result(out, state, params=None):
    if isinstance(out, dict):
        _attach_agent_reply_hint(out, resource_role="existing_page")
        hint = out.get("agent_reply_hint") if isinstance(out.get("agent_reply_hint"), dict) else None
        if hint is not None:
            waiting = state.get("page_status") == "waiting_input"
            hint["interaction_required"] = waiting
            if waiting:
                required_input = state.get("required_input") or {}
                trace_context = C.current_trace_context()
                hint.update({
                    "required_input": required_input,
                    "task_id": (params or {}).get("task_id") or trace_context.get("task_id") or "",
                    "page_id": (params or {}).get("page_id") or out.get("page_id") or "",
                    "public_url": out.get("url") or out.get("public_url") or "",
                    "resume_step": required_input.get("resume_step") or state.get("current_step") or "",
                })
        out["progress"] = state
        out["steps"] = state.get("steps") or []
        out["progress_page"] = {
            "mode": "progress_snapshot",
            "refresh_owner": "host_page",
            "auto_refresh": False,
        }
    return out


def cmd_new_page(params):
    validation_error = _validate_progress_params(params)
    if validation_error:
        return validation_error
    state, html = _progress_state_and_html(params)
    payload = _progress_publish_payload(params, html, require_page_id=False)
    out = cmd_upload(payload)
    return _attach_progress_result(out, state, params)


def cmd_update_progress(params):
    if not params.get("page_id"):
        return {"code": 1, "message": "update_progress 需要 page_id（要更新哪个进度页）"}
    validation_error = _validate_progress_params(params)
    if validation_error:
        return validation_error
    evidence_error = _validate_progress_evidence(params)
    if evidence_error:
        return evidence_error
    state, html = _progress_state_and_html(params)
    payload = _progress_publish_payload(params, html, require_page_id=True)
    out = cmd_update(payload)
    return _attach_progress_result(out, state, params)


def _publish_final_progress_params(params, *, page_status, message):
    progress_params = {
        "page_id": params.get("page_id"),
        "current_step": "final_publish",
        "page_status": page_status,
        "message": message,
    }
    for key in ("title", "theme", "steps", "ensure_share_shell", "page_context", "agent_reply_template", "task_id", "validation_receipt_files", "validation_not_required_reason"):
        if params.get(key) is not None:
            progress_params[key] = params[key]
    return progress_params


def _normalized_public_url(value):
    return str(value or "").strip().rstrip("/")


def _public_url_page_id(value):
    try:
        path = urllib.parse.urlparse(str(value or "")).path
    except Exception:
        return ""
    name = path.rsplit("/", 1)[-1]
    return name[:-5] if name.endswith(".html") else name


def _publish_final_validation_error(params, update_out, template_resolution, final_html):
    expected_page_id = str(params.get("page_id") or "")
    actual_page_id = str(update_out.get("page_id") or "")
    if actual_page_id != expected_page_id:
        return "publish_final 返回的 page_id 与首链 page_id 不一致"

    public_url = _record_url(update_out)
    if not public_url:
        return "publish_final 未返回最终 public_url"

    source_template_id = str((template_resolution or {}).get("source_template_id") or "")
    source_public_url = (template_resolution or {}).get("source_public_url") or ""
    if source_template_id and _public_url_page_id(public_url) == source_template_id:
        return "publish_final 错误返回了来源模板 URL"
    if source_public_url and _normalized_public_url(public_url) == _normalized_public_url(source_public_url):
        return "publish_final 错误返回了来源模板 URL"

    if _public_url_page_id(public_url) != expected_page_id:
        return "publish_final 返回的 public_url 不属于首链 page_id"

    first_page_url = params.get("first_page_url") or params.get("first_url")
    if first_page_url and _normalized_public_url(public_url) != _normalized_public_url(first_page_url):
        return "publish_final 返回的 public_url 与首链 URL 不一致"

    template = params.get("agent_reply_template") if isinstance(params.get("agent_reply_template"), dict) else {}
    template_ref = template.get("template_ref") or ""
    source_packages = set((template_resolution or {}).get("source_package_ids") or [])
    source_grants = set((template_resolution or {}).get("source_grant_ids") or [])
    final_packages = set(update_out.get("package_ids") or [])
    final_grants = set(update_out.get("grant_ids") or [])
    leaked_packages = sorted(final_packages & source_packages)
    leaked_grants = sorted(final_grants & source_grants)
    if leaked_packages or leaked_grants:
        return "fork 发布后仍含来源凭证: " + ", ".join(leaked_packages + leaked_grants)
    fork_manifest = (template_resolution or {}).get("fork_manifest") or {}
    minimum_packages = int(fork_manifest.get("minimum_target_package_count") or 0)
    minimum_grants = int(fork_manifest.get("minimum_target_grant_count") or 0)
    if len(final_packages) < minimum_packages or len(final_grants) < minimum_grants:
        return (
            "fork 目标实时凭证能力缩水: "
            f"package {len(final_packages)}/{minimum_packages}, "
            f"grant {len(final_grants)}/{minimum_grants}"
        )

    html_requires_live_data = bool(_extract_package_credentials(final_html)) or any(
        token in str(final_html or "")
        for token in ("queryFormulaPackage", "package_id", "packageId", "grant_id", "grantId")
    )
    professional_live = _bool_param(params.get("require_live_data")) or (
        bool(source_template_id)
        and template_ref != "generic_live_page_delivery_v1"
        and html_requires_live_data
    )
    if professional_live:
        if not final_packages and not final_grants:
            return "专业实时模板发布后缺少用户页面自己的 package_ids 或 grant_ids"
    return ""


def cmd_publish_final(params):
    if not params.get("page_id"):
        return {"code": 1, "message": "publish_final 需要 page_id（要发布到哪个活页链接）"}

    params, fork_task_binding, binding_error = _apply_fork_task_binding(params)
    if binding_error:
        binding_error.setdefault("page_id", params.get("page_id"))
        binding_error["fork_task_binding"] = {
            "mode": "error",
            "task_id": _fork_task_id(params),
        }
        return binding_error

    final_html, final_html_error = _read_html(params)
    if final_html_error:
        return final_html_error
    params, template_resolution, template_error = _resolve_publish_agent_reply_template(params, html=final_html)
    if template_error:
        return template_error
    fork_manifest_resolution, fork_manifest_error = _validate_fork_manifest(
        params,
        template_resolution,
        final_html,
    )
    if fork_manifest_error:
        fork_manifest_error.setdefault("page_id", params.get("page_id"))
        if isinstance(fork_task_binding, dict) and fork_task_binding.get("mode") == "task_binding":
            fork_manifest_error["fork_task_binding"] = fork_task_binding
        fork_manifest_error["fork_manifest_validation"] = {
            "ok": False,
            "source_template_id": (template_resolution or {}).get("source_template_id") or "",
        }
        return fork_manifest_error
    if fork_manifest_resolution:
        template_resolution["fork_manifest"] = fork_manifest_resolution

    running_message = (
        params.get("progress_message")
        or params.get("final_publish_message")
        or params.get("publish_message")
        or "正在完成活页生成"
    )
    progress_update = cmd_update_progress(_publish_final_progress_params(
        params,
        page_status="running",
        message=running_message,
    ))

    update_out = cmd_update(params)
    if isinstance(update_out, dict) and update_out.get("code") == 0:
        validation_error = _publish_final_validation_error(
            params,
            update_out,
            template_resolution,
            final_html,
        )
        if validation_error:
            update_out.pop("agent_reply_contract", None)
            update_out.pop("agent_reply_template_file", None)
        else:
            _attach_agent_reply_contract(update_out, operation="publish_final")
            update_out["progress_update"] = progress_update
            update_out["agent_reply_template_resolution"] = template_resolution
            if fork_manifest_resolution:
                update_out["fork_manifest_validation"] = {
                    "ok": True,
                    **fork_manifest_resolution,
                }
            if isinstance(fork_task_binding, dict) and fork_task_binding.get("mode") == "task_binding":
                fork_task_binding, binding_status_error = _mark_fork_task_published(
                    fork_task_binding,
                    page_id=update_out.get("page_id"),
                    public_url=_record_url(update_out),
                )
                update_out["fork_task_binding"] = fork_task_binding
                if binding_status_error:
                    _append_warning(update_out, {
                        "type": "fork_task_binding_status_update_failed",
                        "message": binding_status_error.get("message") or str(binding_status_error),
                    })
            update_out["publish_final"] = {
                "progress_step": "final_publish",
                "final_html_published": True,
            }
            if not (isinstance(progress_update, dict) and progress_update.get("code") == 0):
                _append_warning(update_out, {
                    "type": "progress_update_failed",
                    "message": _result_message(progress_update),
                })
            return update_out
    else:
        validation_error = ""

    failure_message = (
        params.get("failure_message")
        or params.get("progress_failure_message")
        or "活页生成遇到问题，请稍后重试。"
    )
    failed_update = cmd_update_progress(_publish_final_progress_params(
        params,
        page_status="failed",
        message=failure_message,
    ))
    message = validation_error or "正式活页发布失败"
    if isinstance(failed_update, dict) and failed_update.get("code") == 0:
        message += "，已回写失败进度页"
    else:
        message += "，且失败进度页回写未成功"

    return {
        "code": 1,
        "message": message,
        "page_id": params.get("page_id"),
        "update": update_out,
        "progress_update": progress_update,
        "progress_failed_update": failed_update,
        "publish_final": {
            "progress_step": "final_publish",
            "final_html_published": False,
        },
    }


def cmd_fork_validate(params):
    params, fork_task_binding, binding_error = _apply_fork_task_binding(params)
    if binding_error:
        return binding_error
    final_html, final_html_error = _read_html(params)
    if final_html_error:
        return final_html_error
    params, template_resolution, template_error = _resolve_publish_agent_reply_template(params, html=final_html)
    if template_error:
        return template_error
    validation, validation_error = _validate_fork_manifest(params, template_resolution, final_html)
    if validation_error:
        validation_error["fork_manifest_validation"] = {
            "ok": False,
            "source_template_id": (template_resolution or {}).get("source_template_id") or "",
        }
        return validation_error
    if not validation:
        return {"code": 1, "error": "FORK_CONTEXT_REQUIRED", "message": "fork_validate 需要已绑定的 fork task 或 source_template_id + manifest"}
    return {
        "code": 0,
        "message": "fork 工作 HTML 门禁校验通过，可以进入浏览器验收",
        "fork_manifest_validation": {"ok": True, **validation},
        "fork_task_binding": fork_task_binding,
        "html_sha256": hashlib.sha256(final_html.encode("utf-8")).hexdigest(),
    }


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
        "thumbnail_url": meta.get("thumbnail_url") or "",
        "url": meta.get("url"),
        "size": len(html.encode("utf-8")),
        "sha256": sha,
        "sha256_match": sha_ok,
        "is_live": bool(meta.get("is_live")),
        "package_ids": meta.get("package_ids") or [],
        "grant_ids": meta.get("grant_ids") or [],
        "page_context": meta.get("page_context"),
        "agent_reply_template": meta.get("agent_reply_template"),
        "reply_contract_binding": meta.get("reply_contract_binding"),
        "status": meta.get("status"),
        "community_status": meta.get("community_status") or "none",
        "scene_tags": meta.get("scene_tags") or [],
        "paradigm_tags": meta.get("paradigm_tags") or [],
        "recommend_tags": meta.get("recommend_tags") or [],
        "expires_at": meta.get("expires_at"),
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
    if _bool_param(params.get("final_response")):
        return _attach_agent_reply_contract(out, operation="download")
    return _attach_agent_reply_hint(out, resource_role="existing_page")


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
    return _normalize_cover_response(
        C.http_json("GET", url, C.headers(api_key), timeout=_DEFAULT_TIMEOUT),
        reply_mode="hint",
        resource_role="existing_page",
    )


def _valid_page_context(value):
    normalized, error = _normalize_page_context(value)
    return normalized if not error else None


def _valid_agent_reply_template(value):
    normalized, error = _normalize_agent_reply_template(value)
    return normalized if not error else None


def _reply_metadata_missing(record):
    missing = []
    if not _valid_page_context(record.get("page_context")):
        missing.append("page_context")
    if not _valid_agent_reply_template(record.get("agent_reply_template")):
        missing.append("agent_reply_template")
    return missing


def _iter_reply_metadata_targets(params):
    explicit_ids = params.get("page_ids") or params.get("pages")
    if explicit_ids:
        if isinstance(explicit_ids, str):
            explicit_ids = [item.strip() for item in re.split(r"[\s,]+", explicit_ids) if item.strip()]
        for page_id in explicit_ids:
            yield {"page_id": page_id}
        return

    scope = params.get("scope", "test_all")
    page_size = int(params.get("page_size", 50))
    max_pages = int(params.get("max_pages", 500))
    page = int(params.get("page", 1))
    seen = 0
    while seen < max_pages:
        batch = cmd_list({"scope": scope, "page": page, "page_size": min(page_size, max_pages - seen)})
        if not (isinstance(batch, dict) and batch.get("code") == 0):
            yield {"error": batch, "page": page}
            return
        data = batch.get("data") or {}
        items = data.get("items") or []
        if not items:
            return
        for item in items:
            seen += 1
            yield item
            if seen >= max_pages:
                return
        total = int(data.get("total") or 0)
        if page * page_size >= total:
            return
        page += 1


def _infer_reply_metadata_for_record(record, html):
    params = {
        "title": record.get("title") or "",
        "description": record.get("description") or "",
        "scene_tags": record.get("scene_tags") or [],
        "paradigm_tags": record.get("paradigm_tags") or [],
    }
    resolved, resolution, error = _resolve_publish_agent_reply_template(params, html=html)
    if error:
        return None, resolution, error
    metadata = {
        "page_context": resolved.get("page_context"),
        "agent_reply_template": resolved.get("agent_reply_template"),
    }
    error = _validate_reply_metadata_pair(metadata)
    if error:
        return None, resolution, error
    return metadata, resolution, None


def _compact_reply_metadata_plan(page_id, record, missing, metadata, resolution, *, status):
    template = metadata.get("agent_reply_template") if isinstance(metadata, dict) else {}
    context = metadata.get("page_context") if isinstance(metadata, dict) else {}
    return {
        "page_id": page_id,
        "title": record.get("title") or "",
        "owner": record.get("owner") or record.get("user_name") or "",
        "status": status,
        "missing": missing,
        "template_ref": template.get("template_ref") if isinstance(template, dict) else "",
        "page_context_summary": context.get("summary") if isinstance(context, dict) else "",
        "resolution": resolution,
    }


def cmd_init_reply_metadata(params):
    dry_run = params.get("dry_run", True)
    if isinstance(dry_run, str):
        dry_run = dry_run.strip().lower() not in ("0", "false", "no", "off")
    force = _bool_param(params.get("force"))
    include_revoked = _bool_param(params.get("include_revoked"))

    results = []
    scanned = 0
    planned = 0
    updated = 0
    failed = 0
    skipped = 0

    for seed in _iter_reply_metadata_targets(params):
        if seed.get("error"):
            failed += 1
            results.append({"status": "failed", "message": "列表读取失败", "page": seed.get("page"), "result": seed.get("error")})
            break
        page_id = seed.get("page_id")
        if not page_id:
            skipped += 1
            continue
        scanned += 1
        if seed.get("status") == "revoked" and not include_revoked:
            skipped += 1
            results.append({"page_id": page_id, "status": "skipped_revoked"})
            continue
        missing = ["page_context", "agent_reply_template"] if force else _reply_metadata_missing(seed)
        if not missing:
            skipped += 1
            results.append({"page_id": page_id, "status": "skipped_current"})
            continue

        downloaded = cmd_download({"page_id": page_id})
        if not (isinstance(downloaded, dict) and downloaded.get("code") == 0):
            failed += 1
            results.append({"page_id": page_id, "status": "failed", "stage": "download", "result": downloaded})
            continue
        if not force:
            missing = _reply_metadata_missing(downloaded)
            if not missing:
                skipped += 1
                results.append({"page_id": page_id, "status": "skipped_current"})
                continue

        metadata, resolution, error = _infer_reply_metadata_for_record(downloaded, downloaded.get("html") or "")
        if error:
            failed += 1
            results.append({"page_id": page_id, "status": "failed", "stage": "infer", "message": error.get("message"), "result": error})
            continue
        planned += 1
        plan = _compact_reply_metadata_plan(page_id, downloaded, missing, metadata, resolution, status="planned" if dry_run else "updating")
        if dry_run:
            results.append(plan)
            continue

        update_params = {
            "page_id": page_id,
            "html": downloaded.get("html") or "",
            "title": downloaded.get("title") or "",
            "page_context": metadata["page_context"],
            "agent_reply_template": metadata["agent_reply_template"],
            "ensure_share_shell": False,
        }
        if downloaded.get("description") is not None:
            update_params["description"] = downloaded.get("description")
        update = cmd_update(update_params)
        ok = isinstance(update, dict) and update.get("code") == 0
        if ok:
            updated += 1
            results.append({**plan, "status": "updated", "url": update.get("url")})
        else:
            failed += 1
            results.append({**plan, "status": "failed", "stage": "update", "result": update})

    return {
        "code": 0 if failed == 0 else 1,
        "dry_run": dry_run,
        "scope": params.get("scope", "test_all"),
        "scanned": scanned,
        "planned": planned,
        "updated": updated,
        "skipped": skipped,
        "failed": failed,
        "results": results,
    }


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
    return _http_multipart(C.api_url(endpoint, _PATH["thumbnail"]), api_key,
                           {"page_id": params["page_id"]},
                           "file", img_bytes, file_name, content_type)


def cmd_tags(params):
    cfg = C.load_config_require_key()
    endpoint, api_key = C.endpoint_of(cfg), cfg.get("api_key", "")
    qs_pairs = []
    if params.get("tag_type"):
        qs_pairs.append(("tag_type", params["tag_type"]))
    url = C.api_url(endpoint, _PATH["tags"])
    if qs_pairs:
        url += "?" + _up.urlencode(qs_pairs)
    return C.http_json("GET", url, C.headers(api_key), timeout=_DEFAULT_TIMEOUT)


def cmd_autotag(params):
    """LLM 自动打标：page_id → 给已上传页打标；html/html_file → 上传前预打标（自动 dry_run）。"""
    cfg = C.load_config_require_key()
    endpoint, api_key = C.endpoint_of(cfg), cfg.get("api_key", "")
    page_id = params.get("page_id")
    html = params.get("html")
    html_file = params.get("html_file")
    if not page_id and not html and not html_file:
        return {"code": 1, "message": "autotag 需要 page_id（给已上传页打标），或 html/html_file（上传前预打标，自动 dry_run）"}
    body = {}
    if page_id:
        body["page_id"] = page_id
    else:
        if html_file:
            path = html_file if os.path.isabs(html_file) else os.path.join(C.SKILL_ROOT, html_file)
            if not os.path.exists(path):
                return {"code": 1, "message": f"html_file 不存在: {path}"}
            with open(path, "r", encoding="utf-8") as f:
                html = f.read()
        body["html"] = html
        body["dry_run"] = True  # 无 page 只能预打标（服务端也会强制）
    # 显式传的 dry_run / force 透传（服务端兼容 bool / "true"）
    for k in ("dry_run", "force"):
        if params.get(k) is not None:
            body[k] = params[k]
    # LLM 调用可能较慢，用上传超时（120s）
    return C.http_json("POST", C.api_url(endpoint, _PATH["autotag"]),
                       C.headers(api_key), body, timeout=_UPLOAD_TIMEOUT)


def _cmd_community(params, path_key, label):
    cfg = C.load_config_require_key()
    endpoint, api_key = C.endpoint_of(cfg), cfg.get("api_key", "")
    if not params.get("page_id"):
        return {"code": 1, "message": f"{label} 需要 page_id"}
    body = {"page_id": params["page_id"]}
    return C.http_json("POST", C.api_url(endpoint, _PATH[path_key]),
                       C.headers(api_key), body, timeout=_DEFAULT_TIMEOUT)


def cmd_publish_community(params):
    return _cmd_community(params, "publish_community", "publish_community")


def cmd_unpublish_community(params):
    return _cmd_community(params, "unpublish_community", "unpublish_community")


def _templates_query(endpoint, api_key, params, recommend=None):
    qs_pairs = [("page", params.get("page", 1)), ("page_size", params.get("page_size", 20))]
    # 服务端默认限定 recommend:官方精选；*_tag_id / category / status 只做叠加筛选。
    for k in ("category", "status", "scene_tag_id", "paradigm_tag_id", "recommend_tag_id"):
        if params.get(k):
            qs_pairs.append((k, params[k]))
    if recommend:
        qs_pairs.append(("recommend", recommend))
    url = C.api_url(endpoint, _PATH["templates"]) + "?" + _up.urlencode(qs_pairs)
    return C.http_json("GET", url, C.headers(api_key), timeout=_DEFAULT_TIMEOUT)


def _merge_template_items(base, extra):
    """把 extra 响应里的 items 合并进 base（按 page_id/template_id 去重，base 优先）。"""
    if not (isinstance(base, dict) and isinstance(extra, dict)):
        return base
    bdata, edata = base.get("data"), extra.get("data")
    if not (isinstance(bdata, dict) and isinstance(edata, dict)):
        return base
    bitems, eitems = bdata.get("items"), edata.get("items")
    if not (isinstance(bitems, list) and isinstance(eitems, list)):
        return base
    seen = {it.get("page_id") or it.get("template_id") for it in bitems if isinstance(it, dict)}
    seen.discard(None)
    for it in eitems:
        if not isinstance(it, dict):
            continue
        key = it.get("page_id") or it.get("template_id")
        if key and key in seen:
            continue
        bitems.append(it)
        if key:
            seen.add(key)
    return base


def cmd_templates(params):
    cfg = C.load_config_require_key()
    endpoint, api_key = C.endpoint_of(cfg), cfg.get("api_key", "")
    # recommend 命中口径：不传 → 官方精选（服务端默认）；"社区" → 仅社区；
    # "all"/"both" 或 include_community=true → 合并官方精选 + 社区（范式卡命中池）。
    recommend = params.get("recommend")
    rec_norm = str(recommend).strip().lower() if recommend else ""
    include_community = bool(params.get("include_community")) or rec_norm in ("all", "both", "官方精选+社区")
    if include_community:
        base = _templates_query(endpoint, api_key, params)                       # 官方精选
        community = _templates_query(endpoint, api_key, params, recommend="社区")  # 社区
        merged = _merge_template_items(base, community)
        return _normalize_cover_response(merged, reply_mode="hint", resource_role="source_template")
    out = _templates_query(endpoint, api_key, params, recommend=(recommend if recommend else None))
    return _normalize_cover_response(out, reply_mode="hint", resource_role="source_template")


def cmd_template(params):
    cfg = C.load_config_require_key()
    endpoint, api_key = C.endpoint_of(cfg), cfg.get("api_key", "")
    tid = params.get("template_id") or params.get("page_id")
    if not tid:
        return {"code": 1, "message": "template 需要 template_id 或 page_id"}
    key = "template_id" if params.get("template_id") else "page_id"
    url = C.api_url(endpoint, _PATH["template"]) + "?" + _up.urlencode([(key, tid)])
    return _normalize_cover_response(
        C.http_json("GET", url, C.headers(api_key), timeout=_DEFAULT_TIMEOUT),
        reply_mode="hint",
        resource_role="source_template",
    )


def cmd_direct_finalize(params):
    cfg = C.load_config_require_key()
    endpoint, api_key = C.endpoint_of(cfg), cfg.get("api_key", "")
    task_id = str(params.get("task_id") or C.current_trace_context().get("task_id") or "").strip()
    page_id = str(params.get("page_id") or "").strip()
    template_revision = str(params.get("template_revision") or "").strip()
    if not task_id or not page_id or not template_revision:
        return {
            "code": 1,
            "error": "DIRECT_FINALIZE_PARAMS_REQUIRED",
            "message": "direct_finalize 需要 task_id、page_id、template_revision",
        }
    out = C.http_json(
        "POST",
        C.api_url(endpoint, _PATH["direct_finalize"]),
        C.headers(api_key),
        {
            "task_id": task_id,
            "page_id": page_id,
            "template_revision": template_revision,
        },
        timeout=_DEFAULT_TIMEOUT,
    )
    if not (isinstance(out, dict) and out.get("code") == 0):
        return out
    required = {
        "task_id": out.get("task_id"),
        "page_id": out.get("page_id"),
        "public_url": out.get("public_url") or out.get("url"),
        "template_revision": out.get("template_revision"),
        "delivery_trace_id": out.get("delivery_trace_id"),
    }
    missing = [key for key, value in required.items() if not value]
    if missing or required["task_id"] != task_id or required["page_id"] != page_id:
        return {
            "code": 1,
            "error": "DIRECT_FINALIZE_INCOMPLETE",
            "message": "direct_finalize 成功响应缺少强终态字段或任务归属不一致",
            "missing": missing,
        }
    out["operation"] = "direct_finalize"
    return _attach_agent_reply_contract(out, operation="direct_finalize")


def _direct_credential_map(items, id_key):
    grouped = {}
    for item in items or []:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get(id_key) or "").strip()
        signature = str(item.get("signature") or "").strip()
        if not item_id or not signature:
            continue
        grouped.setdefault(item_id, set()).add(signature)
    return grouped


def _direct_query_package(package_id, signature):
    import formula_package as FP
    return FP.cmd_query({
        "package_id": package_id,
        "signature": signature,
        "result_mode": "summary",
        "direct": True,
    })


def _direct_query_grant(grant_id, signature):
    import data_grant as DG
    return DG.cmd_query({"grant_id": grant_id, "signature": signature})


def _redact_direct_payload(value):
    """Remove capability credentials before persisting direct grant evidence locally."""
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            if normalized in {"signature", "api_key", "authorization", "bearer"}:
                continue
            out[key] = _redact_direct_payload(item)
        return out
    if isinstance(value, list):
        return [_redact_direct_payload(item) for item in value]
    return value


def _write_direct_grant_result(task_id, grant_id, result):
    safe_task = re.sub(r"[^0-9A-Za-z._-]+", "_", str(task_id or "")).strip("._-") or "task"
    safe_grant = re.sub(r"[^0-9A-Za-z._-]+", "_", str(grant_id or "")).strip("._-") or "grant"
    path = os.path.join(tempfile.gettempdir(), f"qbv_{safe_task}_grant_{safe_grant}.json")
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(_redact_direct_payload(result), handle, ensure_ascii=False, indent=2)
    return path


def _direct_failure(code, message, **extra):
    return {"code": 1, "error": code, "message": message, **extra}


def _run_direct_deliver(task_id, page_id, expected_revision):
    template_result = cmd_template({"task_id": task_id, "page_id": page_id})
    if not (isinstance(template_result, dict) and template_result.get("code") == 0):
        return template_result
    record = _template_record(template_result)
    current_revision = str(record.get("template_revision") or "").strip()
    if not current_revision or current_revision != expected_revision:
        return _direct_failure(
            "TEMPLATE_CHANGED",
            "模板已变化，请重新查询范式卡后再交付",
            current_template_revision=current_revision or None,
        )

    public_url = _record_url(record)
    if not public_url:
        return _direct_failure("DIRECT_TEMPLATE_URL_MISSING", "直达模板缺少公开 URL")
    html, fetch_error = _fetch_oss(public_url)
    if fetch_error:
        return fetch_error

    package_ids = _unique_strings(record.get("package_ids"))
    grant_ids = _unique_strings(record.get("grant_ids"))
    package_credentials = _direct_credential_map(_extract_package_credentials(html), "package_id")
    grant_credentials = _direct_credential_map(_extract_grant_credentials(html), "grant_id")
    missing_package_ids = sorted(item for item in package_ids if len(package_credentials.get(item, set())) != 1)
    missing_grant_ids = sorted(item for item in grant_ids if len(grant_credentials.get(item, set())) != 1)
    if missing_package_ids or missing_grant_ids:
        return _direct_failure(
            "DIRECT_DATA_EVIDENCE_MISSING",
            "模板当前实时凭证不完整或存在歧义，未执行取数与 finalize",
            missing_package_ids=missing_package_ids,
            missing_grant_ids=missing_grant_ids,
        )

    package_results = []
    for package_id in package_ids:
        signature = next(iter(package_credentials[package_id]))
        result = _direct_query_package(package_id, signature)
        if not (isinstance(result, dict) and result.get("code") == 0):
            return _direct_failure(
                "DIRECT_DATA_QUERY_FAILED",
                "公式包实时查询失败，未执行 finalize",
                failed_kind="formula_package",
                failed_id=package_id,
                result=_redact_direct_payload(result),
            )
        package_results.append({"package_id": package_id, "result": _redact_direct_payload(result)})

    grant_results = []
    for grant_id in grant_ids:
        signature = next(iter(grant_credentials[grant_id]))
        result = _direct_query_grant(grant_id, signature)
        if not (isinstance(result, dict) and result.get("code") == 0):
            return _direct_failure(
                "DIRECT_DATA_QUERY_FAILED",
                "数据授权实时查询失败，未执行 finalize",
                failed_kind="data_grant",
                failed_id=grant_id,
                result=_redact_direct_payload(result),
            )
        grant_results.append({
            "grant_id": grant_id,
            "result_file": _write_direct_grant_result(task_id, grant_id, result),
        })

    finalized = cmd_direct_finalize({
        "task_id": task_id,
        "page_id": page_id,
        "template_revision": current_revision,
    })
    if not (isinstance(finalized, dict) and finalized.get("code") == 0):
        return finalized

    out = dict(finalized)
    out["operation"] = "direct_finalize"
    out["orchestration"] = "direct_deliver"
    out["direct_data_evidence"] = {
        "package_results": package_results,
        "grant_results": grant_results,
        "package_query_count": len(package_results),
        "grant_query_count": len(grant_results),
    }
    return out


def cmd_direct_deliver(params):
    """Execute the evidence-producing portion of a direct delivery exactly once.

    The caller must already have emitted the selected template URL to the user.
    This command intentionally owns template detail loading, credential extraction,
    one query per current package/grant, and the single terminal finalize call.
    """
    previous_context = C.current_trace_context()
    task_id = str(params.get("task_id") or previous_context.get("task_id") or "").strip()
    page_id = str(params.get("page_id") or "").strip()
    expected_revision = str(params.get("template_revision") or "").strip()
    if not task_id or not page_id or not expected_revision:
        return _direct_failure(
            "DIRECT_DELIVER_PARAMS_REQUIRED",
            "direct_deliver 需要 task_id、page_id、template_revision",
        )
    C.configure_trace_context({"task_id": task_id, "user_query": previous_context.get("user_query")})
    try:
        return _run_direct_deliver(task_id, page_id, expected_revision)
    finally:
        C.set_trace_context(previous_context.get("task_id"), previous_context.get("user_query"))


def _exchange_for_code(code):
    code = str(code or "")
    if code.startswith(("4", "8")):
        return "BJ"
    if code.startswith(("5", "6", "9")):
        return "SH"
    return "SZ"


def _expand_asset_replacements(replacements):
    expanded = dict(replacements or {})
    for source, target in list(expanded.items()):
        source_code = str(source or "").strip()
        target_code = str(target or "").strip()
        if not (re.fullmatch(r"\d{6}", source_code) and re.fullmatch(r"\d{6}", target_code)):
            continue
        source_exchange = _exchange_for_code(source_code)
        target_exchange = _exchange_for_code(target_code)
        variants = {
            f"{source_exchange}{source_code}": f"{target_exchange}{target_code}",
            f"{source_exchange.lower()}{source_code}": f"{target_exchange.lower()}{target_code}",
            f"{source_code}.{source_exchange}": f"{target_code}.{target_exchange}",
            f"{source_exchange}.{source_code}": f"{target_exchange}.{target_code}",
        }
        for variant, replacement in variants.items():
            expanded.setdefault(variant, replacement)
    return expanded


def cmd_fork_prepare(params):
    source_template_id = params.get("source_template_id") or params.get("template_id") or params.get("page_id")
    if not source_template_id:
        return {"code": 1, "message": "fork_prepare 需要 source_template_id（或 template_id/page_id）"}

    template_result = cmd_template({"page_id": source_template_id})
    if not (isinstance(template_result, dict) and template_result.get("code") == 0):
        return template_result
    record = _template_record(template_result)
    source_url = record.get("download_url") or record.get("public_url") or record.get("url") or ""
    if not source_url:
        return {"code": 1, "message": "来源范式没有 download_url/public_url，无法准备 fork"}

    source_html, error = _fetch_oss(source_url)
    if error:
        return error
    source_sha = hashlib.sha256(source_html.encode("utf-8")).hexdigest()

    safe_id = re.sub(r"[^0-9A-Za-z._-]+", "_", str(source_template_id)).strip("._-") or "source"
    output_dir = _fork_path(params.get("output_dir") or os.path.join("output", "forks", safe_id))
    os.makedirs(output_dir, exist_ok=True)
    html_file = _fork_path(params.get("html_file") or f"{safe_id}.source.html", base=output_dir)
    working_html_file = _fork_path(params.get("working_html_file") or f"{safe_id}.fork.html", base=output_dir)
    manifest_file = _fork_path(params.get("manifest_file") or f"{safe_id}.fork-manifest.json", base=output_dir)
    os.makedirs(os.path.dirname(html_file) or output_dir, exist_ok=True)
    os.makedirs(os.path.dirname(working_html_file) or output_dir, exist_ok=True)
    os.makedirs(os.path.dirname(manifest_file) or output_dir, exist_ok=True)
    with open(html_file, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(source_html)

    replacements = params.get("asset_replacements") or {}
    if not isinstance(replacements, dict):
        return {"code": 1, "message": "fork_prepare.asset_replacements 必须是对象"}
    replacements = _expand_asset_replacements(replacements)
    working_html = source_html
    replacement_audit = []
    for source_value, target_value in sorted(replacements.items(), key=lambda item: len(str(item[0])), reverse=True):
        source_text = str(source_value or "")
        target_text = str(target_value or "")
        if not source_text:
            return {"code": 1, "message": "fork_prepare.asset_replacements 不允许空来源值"}
        count = working_html.count(source_text)
        if count == 0 and not _bool_param(params.get("allow_missing_replacements")):
            return {"code": 1, "message": f"fork_prepare 未在来源 HTML 找到替换项: {source_text}"}
        working_html = working_html.replace(source_text, target_text)
        replacement_audit.append({"source": source_text, "target": target_text, "count": count})
    with open(working_html_file, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(working_html)

    context = record.get("page_context") if isinstance(record.get("page_context"), dict) else {}
    source_packages = _unique_strings(
        list(_unique_strings(record.get("package_ids")))
        + [item["package_id"] for item in _extract_package_credentials(source_html)]
    )
    source_grants = _unique_strings(
        list(_unique_strings(record.get("grant_ids")))
        + [item["grant_id"] for item in _extract_grant_credentials(source_html)]
    )
    source_signature_hashes = _signature_hashes(source_html)
    source_h2 = [heading for heading in _html_headings(source_html, levels=(2,)) if heading not in ("分享海报",)]
    required_sections = _unique_strings(params.get("required_sections") or source_h2)
    required_outputs = _unique_strings(params.get("required_outputs") or _template_required_outputs(record))
    source_markers = _unique_strings(list(_unique_strings(params.get("source_markers"))) + list(replacements.keys()))
    card_runtime_required = bool(
        params.get("card_runtime_required")
        if "card_runtime_required" in params
        else record.get("card_runtime_supported")
        or all(token in source_html for token in ("data-qb-card-template", "data-qb-card-manifest", "data-qb-card-runtime"))
    )
    try:
        minimum_target_package_count = int(params.get("minimum_target_package_count", len(source_packages)))
        minimum_target_grant_count = int(params.get("minimum_target_grant_count", len(source_grants)))
    except (TypeError, ValueError):
        return {"code": 1, "message": "fork_prepare 的 minimum_target_package_count/minimum_target_grant_count 必须是非负整数"}
    if minimum_target_package_count < 0 or minimum_target_grant_count < 0:
        return {"code": 1, "message": "fork_prepare 的 minimum_target_package_count/minimum_target_grant_count 必须是非负整数"}
    reduction_reason = str(params.get("credential_count_reduction_reason") or "").strip()
    if (
        minimum_target_package_count < len(source_packages)
        or minimum_target_grant_count < len(source_grants)
    ) and not reduction_reason:
        return {
            "code": 1,
            "message": "fork_prepare 下调最低凭证数量时必须提供 credential_count_reduction_reason",
        }

    manifest = {
        "version": _FORK_MANIFEST_VERSION,
        "prepared_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "source_template_id": str(record.get("template_id") or record.get("page_id") or source_template_id),
        "source_url": source_url,
        "source_html_file": html_file,
        "working_html_file": working_html_file,
        "source_html_sha256": source_sha,
        "source_package_ids": source_packages,
        "source_grant_ids": source_grants,
        "source_signature_sha256": source_signature_hashes,
        "minimum_target_package_count": minimum_target_package_count,
        "minimum_target_grant_count": minimum_target_grant_count,
        "credential_count_reduction_reason": reduction_reason,
        "required_sections": required_sections,
        "context_sections": _unique_strings(context.get("core_sections") or []),
        "required_outputs": required_outputs,
        "source_headings": _html_headings(source_html),
        "source_markers": source_markers,
        "replacement_audit": replacement_audit,
        "target_asset": str(params.get("target_asset") or ""),
        "card_runtime_required": card_runtime_required,
        "agent_reply_template": record.get("agent_reply_template"),
        "page_context_reference": context or None,
    }
    with open(manifest_file, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

    fork_task_binding, binding_error = _bind_fork_task(params, manifest, manifest_file)
    if binding_error:
        binding_error.update({
            "source_template_id": manifest["source_template_id"],
            "manifest_file": manifest_file,
        })
        return binding_error

    out = {
        "code": 0,
        "source_template_id": manifest["source_template_id"],
        "source_url": source_url,
        "html_file": html_file,
        "working_html_file": working_html_file,
        "manifest_file": manifest_file,
        "source_html_sha256": source_sha,
        "source_package_ids": source_packages,
        "source_grant_ids": source_grants,
        "required_sections": required_sections,
        "required_outputs": required_outputs,
        "card_runtime_required": card_runtime_required,
        "replacement_audit": replacement_audit,
        "page_context": context or None,
        "agent_reply_template": record.get("agent_reply_template"),
        "fork_task_binding": fork_task_binding,
        "next_step": "基于 working_html_file 替换自己的凭证与目标文案；同 task 的 publish_final 会自动恢复绑定，仍应显式传 source_template_id 与 fork_manifest_file",
    }
    return _attach_agent_reply_hint(out, resource_role="source_template")


def _expected_template_metadata(params):
    expected = params.get("expected_metadata") if isinstance(params.get("expected_metadata"), dict) else {}
    for key in ("download_url", "title", "description", "category", "size", "sha256", "updated_at", "page_context", "agent_reply_template", "reply_contract_binding"):
        flag = "expected_" + key
        if flag in params:
            expected[key] = params[flag]
    return expected


def _metadata_changes(current, expected):
    changes = []
    for key, old in expected.items():
        if key not in current:
            continue
        now = current.get(key)
        if key == "agent_reply_template":
            now = _agent_reply_template_metadata(now)
            old = _agent_reply_template_metadata(old)
        elif key == "page_context":
            now = _page_context_metadata(now)
            old = _page_context_metadata(old)
        elif key == "reply_contract_binding":
            now = _reply_contract_binding_metadata(now)
            old = _reply_contract_binding_metadata(old)
        if isinstance(now, (dict, list)) or isinstance(old, (dict, list)):
            now_cmp = json.dumps(now or {}, ensure_ascii=False, sort_keys=True)
            old_cmp = json.dumps(old or {}, ensure_ascii=False, sort_keys=True)
        else:
            now_cmp = str(now or "")
            old_cmp = str(old or "")
        if now_cmp != old_cmp:
            changes.append({"field": key, "expected": old, "current": now})
    return changes


def cmd_update_template(params):
    """Safely update a published template without creating a replacement URL."""
    cfg = C.load_config_require_key()
    endpoint, api_key = C.endpoint_of(cfg), cfg.get("api_key", "")
    tid = params.get("template_id") or params.get("page_id")
    if not tid:
        return {"code": 1, "message": "update_template 需要 template_id 或 page_id"}

    before = cmd_template({"template_id": tid} if params.get("template_id") else {"page_id": tid})
    if not (isinstance(before, dict) and before.get("code") == 0):
        return {"code": 1, "message": "写回前读取模板失败", "template": before}
    current = _template_record(before)
    expected = _expected_template_metadata(params)
    if expected:
        changes = _metadata_changes(current, expected)
        if changes:
            return {
                "code": 1,
                "message": "模板 metadata 已变化，停止写回以避免覆盖他人更新",
                "changes": changes,
                "template": before,
            }

    body = {"template_id": current.get("template_id") or current.get("page_id") or tid}
    html = None
    if params.get("html") or params.get("html_file"):
        html, err = _read_html(params)
        if err:
            return err
        try:
            html, shell_check = _ensure_share_shell(html, params)
        except ValueError as e:
            return {"code": 1, "message": str(e)}
        card_runtime_verification = _maybe_verify_card_runtime(html, params)
        if isinstance(card_runtime_verification, dict) and not card_runtime_verification.get("ok"):
            return {
                "code": 1,
                "message": card_runtime_verification.get("message") or "card runtime artifact 验收未通过",
                "card_runtime_verification": card_runtime_verification,
            }
        body["html"] = html
    else:
        shell_check = None
        card_runtime_verification = None

    for key in ("title", "description", "category", "page_context", "agent_reply_template", "reply_contract_binding"):
        if params.get(key) is not None:
            body[key] = params[key]
    if "page_context" in params and params.get("page_context") is None:
        body["page_context"] = None
    if "reply_contract_binding" in params and params.get("reply_contract_binding") is None:
        body["reply_contract_binding"] = None
    if "agent_reply_template" in params and params.get("agent_reply_template") is None:
        body["agent_reply_template"] = None
    metadata_err = _validate_reply_metadata_pair(params)
    if metadata_err:
        return metadata_err

    out = C.http_json("POST", C.api_url(endpoint, _PATH["update_template"]),
                      C.headers(api_key), body, timeout=_UPLOAD_TIMEOUT)
    after = cmd_template({"template_id": body["template_id"]})
    if isinstance(out, dict):
        out["preflight_template"] = before
        out["postflight_template"] = after
        if out.get("code") == 0:
            delivered = _template_record(after) or current
            out["page_id"] = delivered.get("page_id") or delivered.get("template_id") or body["template_id"]
            out["public_url"] = _record_url(delivered)
            for key in ("page_context", "agent_reply_template", "reply_contract_binding"):
                if delivered.get(key) is not None:
                    out[key] = delivered.get(key)
        if shell_check:
            out["share_shell"] = shell_check
        if card_runtime_verification:
            out["card_runtime_verification"] = card_runtime_verification
    out = _normalize_cover_response(out)
    if isinstance(out, dict) and out.get("code") == 0:
        _attach_agent_reply_contract(out, operation="update_template")
    return out


def _fetch_public_html(url):
    if not url:
        raise ValueError("缺少可下载的 public/download URL")
    req = urllib.request.Request(url, headers={"Accept": "text/html,application/xhtml+xml"}, method="GET")
    with C._NO_PROXY_OPENER.open(req, timeout=_DEFAULT_TIMEOUT) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _default_retrofit_out_file(page_id):
    base = os.path.join(C.SKILL_ROOT, "output", "card-runtime-retrofit")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "%s.html" % (page_id or "page"))


def _run_card_runtime_verify(html_file, *, artifact_only=False, require_browser=True, timeout_sec=180):
    target = html_file
    cmd = ["node", os.path.join(C.SKILL_ROOT, "scripts", "verify_page.mjs"), target, "--card-runtime"]
    if require_browser:
        cmd.append("--require-browser")
    if artifact_only:
        cmd.append("--card-runtime-only")
    try:
        proc = subprocess.run(
            cmd,
            cwd=C.SKILL_ROOT,
            text=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_sec,
        )
    except subprocess.TimeoutExpired as exc:
        raw = ((exc.stdout or "") + "\n" + (exc.stderr or "")).strip()
        return {
            "code": 124,
            "message": "card runtime 验收超时",
            "target": target,
            "timeout_sec": timeout_sec,
            "raw": raw[-1000:],
        }
    raw = (proc.stdout or proc.stderr or "").strip()
    try:
        data = json.loads(raw) if raw else {}
    except Exception:
        data = {"code": proc.returncode, "raw": raw[-1000:]}
    data.setdefault("code", proc.returncode)
    return data


def _verify_card_runtime_html(html, *, require_browser=True, timeout_sec=180):
    with tempfile.TemporaryDirectory(prefix="qb_card_runtime_verify_") as td:
        path = os.path.join(td, "page.html")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(html)
        return _run_card_runtime_verify(
            path,
            artifact_only=True,
            require_browser=require_browser,
            timeout_sec=timeout_sec,
        )


def _maybe_verify_card_runtime(html, params):
    if not params.get("verify_card_runtime"):
        return None
    result = _verify_card_runtime_html(
        html,
        require_browser=params.get("verify_card_runtime_browser", True),
        timeout_sec=int(params.get("verify_card_runtime_timeout_sec", 180)),
    )
    return {
        "ok": isinstance(result, dict) and result.get("code") == 0,
        "mode": "card-runtime-only",
        "result": result,
        "message": "card runtime artifact 验收未通过" if not (isinstance(result, dict) and result.get("code") == 0) else "",
    }


def _as_list(value):
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return [value]


def _safe_stem(value):
    stem = re.sub(r"[^0-9A-Za-z._-]+", "_", str(value or "").strip())
    return stem.strip("._-") or "target"


def _card_runtime_verify_targets(params):
    targets = []
    for item in _as_list(params.get("targets")):
        if isinstance(item, dict):
            targets.append(dict(item))
        elif isinstance(item, str) and re.match(r"https?://", item, re.I):
            targets.append({"url": item})
        elif item:
            targets.append({"page_id": str(item)})
    for page_id in _as_list(params.get("page_ids")) + _as_list(params.get("page_id")):
        if page_id:
            targets.append({"page_id": str(page_id)})
    for template_id in _as_list(params.get("template_ids")) + _as_list(params.get("template_id")):
        if template_id:
            targets.append({"template_id": str(template_id)})
    for url in _as_list(params.get("urls")) + _as_list(params.get("url")):
        if url:
            targets.append({"url": str(url)})
    return targets


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _resolve_card_runtime_target(spec):
    spec = dict(spec or {})
    tid = spec.get("template_id") or spec.get("page_id")
    record = {}
    template = None
    url = spec.get("url") or spec.get("download_url")
    if tid:
        template = cmd_template({"template_id": tid} if spec.get("template_id") else {"page_id": tid})
        if not (isinstance(template, dict) and template.get("code") == 0):
            if not url:
                downloaded = cmd_download({"page_id": tid})
                if isinstance(downloaded, dict) and downloaded.get("code") == 0:
                    record = dict(downloaded)
                    record.pop("html", None)
                    url = record.get("download_url") or record.get("public_url") or record.get("url")
                    tid = record.get("template_id") or record.get("page_id") or tid
                else:
                    raise ValueError("读取模板失败: %s" % json.dumps(template, ensure_ascii=False)[:500])
        else:
            record = _template_record(template)
            url = url or record.get("download_url") or record.get("public_url") or record.get("url")
            tid = record.get("template_id") or record.get("page_id") or tid
    if not url:
        raise ValueError("缺少可验收的 url/download_url")
    return tid or "", url, record, template


def cmd_verify_card_runtime(params):
    """Fast batch verification for standalone card runtime artifacts."""
    targets = _card_runtime_verify_targets(params)
    if not targets:
        return {"code": 1, "message": "verify_card_runtime 需要 page_id/template_id/url 或对应列表"}

    out_dir = params.get("out_dir") or os.path.join(
        C.SKILL_ROOT,
        "output",
        "card-runtime-verify",
        datetime.now().strftime("%Y%m%d-%H%M%S"),
    )
    if not os.path.isabs(out_dir):
        out_dir = os.path.join(C.SKILL_ROOT, out_dir)
    os.makedirs(out_dir, exist_ok=True)
    summary_file = os.path.join(out_dir, "summary.json")
    require_browser = params.get("require_browser", True)
    timeout_sec = int(params.get("timeout_sec", 180))
    results = []

    def flush():
        _write_json(summary_file, {
            "code": 0 if all(item.get("code") == 0 for item in results) else 1,
            "checked": len(results),
            "passed": len([item for item in results if item.get("code") == 0]),
            "failed": len([item for item in results if item.get("code") != 0]),
            "out_dir": out_dir,
            "results": results,
        })

    for index, spec in enumerate(targets, start=1):
        entry = {"index": index, "input": spec}
        try:
            tid, url, record, template = _resolve_card_runtime_target(spec)
            label = tid or ("url_" + hashlib.sha1(url.encode("utf-8")).hexdigest()[:10])
            html_file = os.path.join(out_dir, _safe_stem(label) + ".html")
            html = _fetch_public_html(url)
            with open(html_file, "w", encoding="utf-8", newline="\n") as f:
                f.write(html)
            verification = _run_card_runtime_verify(
                html_file,
                artifact_only=True,
                require_browser=require_browser,
                timeout_sec=timeout_sec,
            )
            card_check = verification.get("card_runtime_check") if isinstance(verification, dict) else {}
            manifest = card_check.get("manifest") if isinstance(card_check, dict) else {}
            artifact = card_check.get("artifact_hydrate") if isinstance(card_check, dict) else {}
            entry.update({
                "code": verification.get("code") if isinstance(verification, dict) else 1,
                "page_id": tid,
                "url": url,
                "html_file": html_file,
                "json_file": os.path.join(out_dir, _safe_stem(label) + ".json"),
                "title": record.get("title") if isinstance(record, dict) else "",
                "required_outputs": (manifest or {}).get("required_outputs") or [],
                "artifact_text": (artifact or {}).get("text") or "",
                "problems": verification.get("problems") if isinstance(verification, dict) else ["verify_page 无法解析输出"],
                "verification": verification,
            })
            if template is not None:
                entry["template"] = {
                    "template_id": record.get("template_id") or record.get("page_id") or tid,
                    "download_url": record.get("download_url"),
                    "updated_at": record.get("updated_at"),
                    "sha256": record.get("sha256"),
                }
        except Exception as exc:
            fallback = spec.get("page_id") or spec.get("template_id") or spec.get("url") or "target_%s" % index
            entry.update({
                "code": 1,
                "page_id": spec.get("page_id") or spec.get("template_id") or "",
                "url": spec.get("url") or "",
                "json_file": os.path.join(out_dir, _safe_stem(fallback) + ".json"),
                "message": str(exc),
                "problems": [str(exc)],
            })
        _write_json(entry["json_file"], entry)
        results.append(entry)
        flush()

    failed = [item for item in results if item.get("code") != 0]
    return {
        "code": 1 if failed else 0,
        "checked": len(results),
        "passed": len(results) - len(failed),
        "failed": len(failed),
        "out_dir": out_dir,
        "summary_file": summary_file,
        "results": results,
    }


def cmd_retrofit_card_runtime(params):
    """Rebuild standalone card-runtime artifacts for a published template/page."""
    tid = params.get("template_id") or params.get("page_id")
    url = params.get("url") or params.get("download_url")
    if not tid and not url:
        return {"code": 1, "message": "retrofit_card_runtime 需要 page_id/template_id 或 url"}

    before = None
    record = {}
    if tid:
        before = cmd_template({"template_id": tid} if params.get("template_id") else {"page_id": tid})
        if not (isinstance(before, dict) and before.get("code") == 0):
            if not url:
                return {"code": 1, "message": "读取模板失败", "template": before}
        else:
            record = _template_record(before)
            url = url or record.get("download_url") or record.get("public_url") or record.get("url")
            tid = record.get("template_id") or record.get("page_id") or tid

    html = _fetch_public_html(url)
    next_html, info = CRT.retrofit_html(
        html,
        page_id=tid or params.get("page_id") or "",
        title=params.get("title") or record.get("title") or "",
    )

    out_file = params.get("out_file") or _default_retrofit_out_file(tid or params.get("page_id") or "page")
    if not os.path.isabs(out_file):
        out_file = os.path.join(C.SKILL_ROOT, out_file)
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    with open(out_file, "w", encoding="utf-8", newline="\n") as f:
        f.write(next_html)

    verify_default = _run_card_runtime_verify(out_file) if params.get("verify", True) else None
    if verify_default and verify_default.get("code") != 0:
        return {"code": 1, "message": "card runtime 独立验收未通过", "html_file": out_file, "retrofit": info, "verification": verify_default}

    update_result = None
    if params.get("update"):
        if not tid:
            return {"code": 1, "message": "url 模式不能 update；请传 page_id/template_id", "html_file": out_file, "retrofit": info}
        expected = _expected_template_metadata(params)
        if not expected and record:
            expected = {
                key: record.get(key)
                for key in ("download_url", "title", "description", "category", "size", "sha256", "updated_at")
                if record.get(key) is not None
            }
        update_params = {
            "template_id": tid,
            "html_file": out_file,
            "expected_metadata": expected,
        }
        update_result = cmd_update_template(update_params)
        err_code = ""
        if isinstance(update_result, dict):
            err = update_result.get("error") if isinstance(update_result.get("error"), dict) else {}
            template = update_result.get("template") if isinstance(update_result.get("template"), dict) else {}
            template_err = template.get("error") if isinstance(template.get("error"), dict) else {}
            err_code = str(err.get("code") or template_err.get("code") or update_result.get("code") or "")
        if not (isinstance(update_result, dict) and update_result.get("code") == 0) and err_code == "TEMPLATE_NOT_FOUND":
            update_result = cmd_update({
                "page_id": tid,
                "html_file": out_file,
            })
        if not (isinstance(update_result, dict) and update_result.get("code") == 0):
            return {"code": 1, "message": "写回失败", "html_file": out_file, "retrofit": info, "update": update_result}

    return {
        "code": 0,
        "page_id": tid or params.get("page_id") or "",
        "url": url,
        "html_file": out_file,
        "retrofit": info,
        "verification": verify_default,
        "update": update_result,
        "preflight_template": before,
    }


_COMMANDS = {
    "new_page": cmd_new_page,
    "update_progress": cmd_update_progress,
    "publish_final": cmd_publish_final,
    "upload": cmd_upload,
    "update": cmd_update,
    "download": cmd_download,
    "list": cmd_list,
    "init_reply_metadata": cmd_init_reply_metadata,
    "revoke": cmd_revoke,
    "thumbnail": cmd_thumbnail,
    "tags": cmd_tags,
    "autotag": cmd_autotag,
    "publish_community": cmd_publish_community,
    "unpublish_community": cmd_unpublish_community,
    "templates": cmd_templates,
    "template": cmd_template,
    "direct_deliver": cmd_direct_deliver,
    "direct_finalize": cmd_direct_finalize,
    "fork_prepare": cmd_fork_prepare,
    "fork_validate": cmd_fork_validate,
    "update_template": cmd_update_template,
    "retrofit_card_runtime": cmd_retrofit_card_runtime,
    "verify_card_runtime": cmd_verify_card_runtime,
}

_TRACE_REQUIRED_COMMANDS = {
    "new_page", "update_progress", "publish_final", "upload", "update", "update_template", "direct_deliver", "direct_finalize", "fork_validate",
}


def main():
    if len(sys.argv) >= 2 and sys.argv[1] in ("-h", "--help"):
        C.emit({"code": 0, "message": f"用法: static_page.py <{'|'.join(_COMMANDS)}> [params]"}, out_name="sp_out.txt")
        sys.exit(0)
    if len(sys.argv) < 2 or sys.argv[1] not in _COMMANDS:
        C.emit({"code": 1, "message": f"用法: static_page.py <{'|'.join(_COMMANDS)}> [params]",
                "doc": (__doc__ or "").strip()[:400]}, out_name="sp_out.txt")
        sys.exit(1)
    cmd = sys.argv[1]
    if any(arg in ("-h", "--help") for arg in sys.argv[2:]):
        C.emit({
            "code": 0,
            "command": cmd,
            "message": f"查看 {cmd} 用法请阅读 tools/static_page.md；帮助请求不会访问网络。",
        }, out_name="sp_out.txt")
        sys.exit(0)
    params = C.read_params(sys.argv[2:], env_var="SP_PARAMS")

    try:
        trace_err = C.require_trace_context() if cmd in _TRACE_REQUIRED_COMMANDS else None
        result = trace_err or _COMMANDS[cmd](params)
    except (FileNotFoundError, ValueError) as e:
        result = {"code": 1, "message": str(e)}
    C.emit(result, out_name="sp_out.txt")
    sys.exit(0 if (isinstance(result, dict) and result.get("code") == 0) else 1)


if __name__ == "__main__":
    main()
