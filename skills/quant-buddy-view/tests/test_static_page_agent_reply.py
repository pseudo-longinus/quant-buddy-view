import copy
import hashlib
import importlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

static_page = importlib.import_module("static_page")


VALUATION_REPLY_TEMPLATE = {
    "version": "reply_template_v2",
    "template_ref": "single_stock_valuation_quality_v1",
    "reply_scope": "full_answer",
    "output_format": "markdown",
}
GENERIC_REPLY_TEMPLATE = {
    "version": "reply_template_v2",
    "template_ref": "generic_live_page_delivery_v1",
    "reply_scope": "full_answer",
    "output_format": "markdown",
}
HYBRID_REPLY_TEMPLATE = {
    "version": "reply_template_v2",
    "template_ref": "capital_flow_quant_signal_v1",
    "reply_scope": "hybrid",
    "output_format": "markdown",
    "hybrid_composition": {
        "version": "hybrid_composition_v1",
        "strategy_ref": "template_first_page_enrichment_v1",
        "prompt": "保留资金量化骨架，并用当前活页的策略模块和实时输出补充。",
    },
}


class AgentReplyTemplatePublishFlowTest(unittest.TestCase):
    def _fork_manifest(self, source_template_id="page_source", source_html=None, **overrides):
        source_html = source_html or "<!doctype html><html><body><h1>来源模板</h1></body></html>"
        override_keys = set(overrides)
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        source_file = Path(temp_dir.name) / "source.html"
        source_file.write_text(source_html, encoding="utf-8")
        manifest = {
            "version": "fork_manifest_v1",
            "source_template_id": source_template_id,
            "source_url": "https://pages.quantbuddy.cn/pages/official/page_source.html",
            "source_html_file": str(source_file),
            "source_html_sha256": hashlib.sha256(source_html.encode("utf-8")).hexdigest(),
            "source_package_ids": [],
            "source_grant_ids": [],
            "source_signature_sha256": static_page._signature_hashes(source_html),
            "minimum_target_package_count": 0,
            "minimum_target_grant_count": 0,
            "credential_count_reduction_reason": "",
            "required_sections": [],
            "required_outputs": [],
            "card_runtime_required": False,
            "source_markers": [],
        }
        manifest.update(overrides)
        if "minimum_target_package_count" not in override_keys:
            manifest["minimum_target_package_count"] = len(manifest["source_package_ids"])
        if "minimum_target_grant_count" not in override_keys:
            manifest["minimum_target_grant_count"] = len(manifest["source_grant_ids"])
        return manifest

    def test_template_returns_non_terminal_reply_hint(self):
        template_record = {
            "code": 0,
            "template_id": "page_source",
            "page_id": "page_source",
            "download_url": "https://pages.quantbuddy.cn/pages/source/page_source.html",
            "agent_reply_template": VALUATION_REPLY_TEMPLATE,
        }

        with mock.patch.object(
            static_page.C,
            "load_config_require_key",
            return_value={"api_key": "test", "endpoint": "https://example.test"},
        ), mock.patch.object(
            static_page.C,
            "endpoint_of",
            return_value="https://example.test",
        ), mock.patch.object(
            static_page.C,
            "api_url",
            side_effect=lambda endpoint, path: endpoint + path,
        ), mock.patch.object(
            static_page.C,
            "http_json",
            return_value=copy.deepcopy(template_record),
        ):
            result = static_page.cmd_template({"template_id": "page_source"})

        self.assertNotIn("agent_reply_contract", result)
        self.assertEqual(result["agent_reply_hint"]["terminal"], False)
        self.assertEqual(result["agent_reply_hint"]["resource_role"], "source_template")
        self.assertEqual(
            result["agent_reply_hint"]["template_ref"],
            "single_stock_valuation_quality_v1",
        )
        self.assertNotIn("public_url", result["agent_reply_hint"])

    def test_download_defaults_to_non_terminal_existing_page_hint(self):
        metadata = {
            "code": 0,
            "page_id": "page_existing",
            "url": "https://pages.quantbuddy.cn/pages/user/page_existing.html",
            "sha256": "",
            "agent_reply_template": VALUATION_REPLY_TEMPLATE,
        }

        with mock.patch.object(
            static_page.C,
            "load_config_require_key",
            return_value={"api_key": "test", "endpoint": "https://example.test"},
        ), mock.patch.object(
            static_page.C,
            "endpoint_of",
            return_value="https://example.test",
        ), mock.patch.object(
            static_page.C,
            "api_url",
            side_effect=lambda endpoint, path: endpoint + path,
        ), mock.patch.object(
            static_page.C,
            "http_json",
            return_value=copy.deepcopy(metadata),
        ), mock.patch.object(
            static_page,
            "_fetch_oss",
            return_value=("<!doctype html><html></html>", None),
        ):
            result = static_page.cmd_download({"page_id": "page_existing"})

        self.assertNotIn("agent_reply_contract", result)
        self.assertEqual(result["agent_reply_hint"]["terminal"], False)
        self.assertEqual(result["agent_reply_hint"]["resource_role"], "existing_page")
        self.assertNotIn("public_url", result["agent_reply_hint"])

    def test_download_requires_explicit_final_response_for_terminal_contract(self):
        metadata = {
            "code": 0,
            "page_id": "page_existing",
            "url": "https://pages.quantbuddy.cn/pages/user/page_existing.html",
            "sha256": "",
            "agent_reply_template": VALUATION_REPLY_TEMPLATE,
        }

        with mock.patch.object(static_page.C, "load_config_require_key", return_value={"api_key": "test"}), \
             mock.patch.object(static_page.C, "endpoint_of", return_value="https://example.test"), \
             mock.patch.object(static_page.C, "api_url", side_effect=lambda endpoint, path: endpoint + path), \
             mock.patch.object(static_page.C, "http_json", return_value=copy.deepcopy(metadata)), \
             mock.patch.object(static_page, "_fetch_oss", return_value=("<!doctype html><html></html>", None)):
            result = static_page.cmd_download({
                "page_id": "page_existing",
                "final_response": True,
            })

        self.assertNotIn("agent_reply_hint", result)
        self.assertEqual(result["agent_reply_contract"]["terminal"], True)
        self.assertEqual(result["agent_reply_contract"]["operation"], "download")

    def test_published_template_download_failure_never_closes_direct_flow(self):
        with mock.patch.object(static_page.C, "load_config_require_key", return_value={"api_key": "test"}), \
             mock.patch.object(static_page.C, "endpoint_of", return_value="https://example.test"), \
             mock.patch.object(static_page.C, "api_url", side_effect=lambda endpoint, path: endpoint + path), \
             mock.patch.object(static_page.C, "http_json", return_value={"code": 1, "error": {"code": "PAGE_NOT_FOUND"}}):
            result = static_page.cmd_download({"page_id": "page_template", "final_response": True})

        self.assertNotIn("agent_reply_contract", result)
        self.assertEqual(result["error"]["code"], "PAGE_NOT_FOUND")

    def test_direct_finalize_returns_terminal_contract_for_same_template_url(self):
        response = {
            "code": 0,
            "task_id": "task_direct",
            "page_id": "page_template",
            "public_url": "https://pages.quantbuddy.cn/pages/official/page_template.html",
            "template_revision": "sha256-revision",
            "delivery_trace_id": "trace_delivery",
            "page_context": {"version": "page_context_v1", "summary": "全球资产泡沫监测"},
            "agent_reply_template": GENERIC_REPLY_TEMPLATE,
        }
        with mock.patch.object(static_page.C, "load_config_require_key", return_value={"api_key": "test"}), \
             mock.patch.object(static_page.C, "endpoint_of", return_value="https://example.test"), \
             mock.patch.object(static_page.C, "api_url", side_effect=lambda endpoint, path: endpoint + path), \
             mock.patch.object(static_page.C, "http_json", return_value=copy.deepcopy(response)) as request:
            result = static_page.cmd_direct_finalize({
                "task_id": "task_direct",
                "page_id": "page_template",
                "template_revision": "sha256-revision",
            })

        self.assertEqual(result["operation"], "direct_finalize")
        self.assertEqual(result["delivery_trace_id"], "trace_delivery")
        self.assertEqual(result["agent_reply_contract"]["terminal"], True)
        self.assertEqual(result["agent_reply_contract"]["operation"], "direct_finalize")
        self.assertEqual(result["agent_reply_contract"]["public_url"], response["public_url"])
        self.assertEqual(request.call_args.args[3]["template_revision"], "sha256-revision")

    def test_direct_deliver_queries_each_live_source_once_then_finalizes(self):
        template = {
            "code": 0,
            "page_id": "page_template",
            "download_url": "https://pages.quantbuddy.cn/pages/official/page_template.html",
            "template_revision": "sha256-revision",
            "package_ids": ["pkg_a", "pkg_b"],
            "grant_ids": ["dg_a"],
            "page_context": {"version": "page_context_v1", "summary": "测试直达"},
            "agent_reply_template": GENERIC_REPLY_TEMPLATE,
        }
        html = """<!doctype html><script>
        const packages = [
          {package_id:'pkg_a', signature:'secret-a'},
          {id:'pkg_b', sig:'secret-b'}
        ];
        const grants = [{id:'dg_a', sig:'secret-g'}];
        </script>"""
        finalized = {
            "code": 0,
            "operation": "direct_finalize",
            "task_id": "task_direct",
            "page_id": "page_template",
            "public_url": template["download_url"],
            "template_revision": "sha256-revision",
            "delivery_trace_id": "trace_delivery",
            "agent_reply_contract": {
                "terminal": True,
                "operation": "direct_finalize",
                "page_id": "page_template",
                "public_url": template["download_url"],
            },
        }
        with mock.patch.object(static_page, "cmd_template", return_value=copy.deepcopy(template)) as get_template, \
             mock.patch.object(static_page, "_fetch_oss", return_value=(html, None)) as fetch, \
             mock.patch.object(static_page, "_direct_query_package", side_effect=[
                 {"code": 0, "package_id": "pkg_a", "outputs": {"a": {"summary": {"latest_value": 1}}}},
                 {"code": 0, "package_id": "pkg_b", "outputs": {"b": {"summary": {"latest_value": 2}}}},
             ]) as query_package, \
             mock.patch.object(static_page, "_direct_query_grant", return_value={
                 "code": 0, "grant_id": "dg_a", "data": [{"date": "2026-07-15", "value": 3}],
                 "signature": "must-not-leak",
             }) as query_grant, \
             mock.patch.object(static_page, "_write_direct_grant_result", return_value=os.path.join(tempfile.gettempdir(), "qbv_task_direct_grant_dg_a.json")) as write_grant, \
             mock.patch.object(static_page, "cmd_direct_finalize", return_value=copy.deepcopy(finalized)) as finalize:
            result = static_page.cmd_direct_deliver({
                "task_id": "task_direct",
                "page_id": "page_template",
                "template_revision": "sha256-revision",
            })

        self.assertEqual(get_template.call_count, 1)
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(query_package.call_count, 2)
        self.assertEqual(query_grant.call_count, 1)
        self.assertEqual(write_grant.call_count, 1)
        self.assertEqual(finalize.call_count, 1)
        self.assertEqual(result["operation"], "direct_finalize")
        self.assertEqual(result["orchestration"], "direct_deliver")
        self.assertEqual(result["agent_reply_contract"]["terminal"], True)
        self.assertEqual(result["direct_data_evidence"]["package_query_count"], 2)
        self.assertEqual(result["direct_data_evidence"]["grant_query_count"], 1)
        rendered = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("secret-a", rendered)
        self.assertNotIn("secret-b", rendered)
        self.assertNotIn("secret-g", rendered)
        self.assertNotIn("must-not-leak", rendered)

    def test_direct_deliver_rejects_template_revision_change_before_fetch(self):
        template = {
            "code": 0,
            "page_id": "page_template",
            "download_url": "https://pages.quantbuddy.cn/pages/official/page_template.html",
            "template_revision": "new-revision",
            "package_ids": [],
            "grant_ids": [],
        }
        with mock.patch.object(static_page, "cmd_template", return_value=template), \
             mock.patch.object(static_page, "_fetch_oss") as fetch, \
             mock.patch.object(static_page, "cmd_direct_finalize") as finalize:
            result = static_page.cmd_direct_deliver({
                "task_id": "task_direct",
                "page_id": "page_template",
                "template_revision": "old-revision",
            })

        self.assertEqual(result["error"], "TEMPLATE_CHANGED")
        fetch.assert_not_called()
        finalize.assert_not_called()

    def test_direct_deliver_rejects_missing_credentials_without_query_or_finalize(self):
        template = {
            "code": 0,
            "page_id": "page_template",
            "download_url": "https://pages.quantbuddy.cn/pages/official/page_template.html",
            "template_revision": "sha256-revision",
            "package_ids": ["pkg_a", "pkg_missing"],
            "grant_ids": ["dg_missing"],
        }
        html = "<script>const p={package_id:'pkg_a',signature:'secret-a'};</script>"
        with mock.patch.object(static_page, "cmd_template", return_value=template), \
             mock.patch.object(static_page, "_fetch_oss", return_value=(html, None)), \
             mock.patch.object(static_page, "_direct_query_package") as query_package, \
             mock.patch.object(static_page, "_direct_query_grant") as query_grant, \
             mock.patch.object(static_page, "cmd_direct_finalize") as finalize:
            result = static_page.cmd_direct_deliver({
                "task_id": "task_direct",
                "page_id": "page_template",
                "template_revision": "sha256-revision",
            })

        self.assertEqual(result["error"], "DIRECT_DATA_EVIDENCE_MISSING")
        self.assertEqual(result["missing_package_ids"], ["pkg_missing"])
        self.assertEqual(result["missing_grant_ids"], ["dg_missing"])
        query_package.assert_not_called()
        query_grant.assert_not_called()
        finalize.assert_not_called()

    def test_direct_deliver_query_failure_never_finalizes(self):
        template = {
            "code": 0,
            "page_id": "page_template",
            "download_url": "https://pages.quantbuddy.cn/pages/official/page_template.html",
            "template_revision": "sha256-revision",
            "package_ids": ["pkg_a"],
            "grant_ids": [],
        }
        html = "<script>const p={package_id:'pkg_a',signature:'secret-a'};</script>"
        with mock.patch.object(static_page, "cmd_template", return_value=template), \
             mock.patch.object(static_page, "_fetch_oss", return_value=(html, None)), \
             mock.patch.object(static_page, "_direct_query_package", return_value={
                 "code": 1, "error": {"code": "UPSTREAM_TIMEOUT", "message": "timeout"}, "signature": "must-not-leak",
             }), \
             mock.patch.object(static_page, "cmd_direct_finalize") as finalize:
            result = static_page.cmd_direct_deliver({
                "task_id": "task_direct",
                "page_id": "page_template",
                "template_revision": "sha256-revision",
            })

        self.assertEqual(result["error"], "DIRECT_DATA_QUERY_FAILED")
        self.assertNotIn("must-not-leak", json.dumps(result, ensure_ascii=False))
        finalize.assert_not_called()

    def test_direct_grant_result_is_written_only_to_system_temp_and_redacted(self):
        with tempfile.TemporaryDirectory() as temp_dir, \
             mock.patch.object(static_page.tempfile, "gettempdir", return_value=temp_dir):
            result_file = static_page._write_direct_grant_result(
                "task/direct",
                "dg/one",
                {"code": 0, "signature": "secret", "nested": {"api_key": "key", "value": 3}},
            )
            payload = json.loads(Path(result_file).read_text(encoding="utf-8"))

        self.assertEqual(Path(result_file).parent, Path(temp_dir))
        self.assertNotIn("signature", payload)
        self.assertNotIn("api_key", payload["nested"])
        self.assertEqual(payload["nested"]["value"], 3)

    def test_static_page_subcommand_help_never_invokes_handler(self):
        handler = mock.Mock(return_value={"code": 0})
        with mock.patch.object(sys, "argv", ["static_page.py", "templates", "--help"]), \
             mock.patch.dict(static_page._COMMANDS, {"templates": handler}), \
             mock.patch.object(static_page.C, "emit") as emit, \
             self.assertRaises(SystemExit) as stopped:
            static_page.main()

        self.assertEqual(stopped.exception.code, 0)
        handler.assert_not_called()
        self.assertEqual(emit.call_args.args[0]["command"], "templates")

    def test_skill_requires_immediate_direct_link_before_next_tool(self):
        skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        workflow_text = (SKILL_ROOT / "workflows" / "new-session-paradigm-routing.md").read_text(encoding="utf-8")

        self.assertIn("下一条用户可见消息必须立即发送现成", skill_text)
        self.assertIn("中间不允许任何工具调用", skill_text)
        self.assertIn("direct_deliver", skill_text)
        self.assertIn("命中与这条消息之间禁止任何工具调用", workflow_text)

    def test_page_list_returns_non_terminal_existing_page_hints(self):
        payload = {
            "code": 0,
            "data": {
                "items": [{
                    "page_id": "page_existing",
                    "url": "https://pages.quantbuddy.cn/pages/user/page_existing.html",
                    "agent_reply_template": VALUATION_REPLY_TEMPLATE,
                }],
            },
        }

        with mock.patch.object(static_page.C, "load_config_require_key", return_value={"api_key": "test"}), \
             mock.patch.object(static_page.C, "endpoint_of", return_value="https://example.test"), \
             mock.patch.object(static_page.C, "api_url", side_effect=lambda endpoint, path: endpoint + path), \
             mock.patch.object(static_page.C, "http_json", return_value=copy.deepcopy(payload)):
            result = static_page.cmd_list({})

        item = result["data"]["items"][0]
        self.assertNotIn("agent_reply_contract", item)
        self.assertEqual(item["agent_reply_hint"]["terminal"], False)
        self.assertEqual(item["agent_reply_hint"]["resource_role"], "existing_page")

    def _capture_publish(self, params, template_result=None, update_overrides=None):
        params = copy.deepcopy(params)
        if params.get("source_template_id") and not params.get("fork_manifest") and not params.get("fork_manifest_file"):
            template_record = template_result or {}
            params["fork_manifest"] = self._fork_manifest(
                params["source_template_id"],
                source_url=template_record.get("download_url") or "",
                source_package_ids=template_record.get("package_ids") or [],
                source_grant_ids=template_record.get("grant_ids") or [],
            )
        captured = {}

        def fake_update(update_params):
            captured["update_params"] = copy.deepcopy(update_params)
            response = {
                "code": 0,
                "page_id": update_params["page_id"],
                "url": "https://pages.quantbuddy.cn/pages/test/page_test.html",
                "page_context": update_params.get("page_context"),
                "agent_reply_template": update_params.get("agent_reply_template"),
            }
            response.update(copy.deepcopy(update_overrides or {}))
            return static_page._attach_agent_reply_contract(response, operation="update")

        patches = [
            mock.patch.object(static_page, "cmd_update_progress", return_value={"code": 0}),
            mock.patch.object(static_page, "cmd_update", side_effect=fake_update),
        ]
        if template_result is not None:
            patches.append(mock.patch.object(static_page, "cmd_template", return_value=template_result))

        with patches[0], patches[1]:
            if len(patches) == 3:
                with patches[2]:
                    result = static_page.cmd_publish_final(copy.deepcopy(params))
            else:
                result = static_page.cmd_publish_final(copy.deepcopy(params))
        return result, captured

    def test_publish_final_requires_fork_manifest_for_source_template(self):
        params = {
            "page_id": "page_test",
            "html": "<!doctype html><html><body><h1>目标页</h1></body></html>",
            "source_template_id": "page_source",
        }
        template_result = {
            "code": 0,
            "page_id": "page_source",
            "download_url": "https://pages.quantbuddy.cn/pages/official/page_source.html",
            "agent_reply_template": VALUATION_REPLY_TEMPLATE,
        }

        with mock.patch.object(static_page, "cmd_template", return_value=template_result), \
             mock.patch.object(static_page, "cmd_update_progress") as update_progress, \
             mock.patch.object(static_page, "cmd_update") as update:
            result = static_page.cmd_publish_final(params)

        self.assertEqual(result["code"], 1)
        self.assertIn("fork_manifest", result["message"])
        update_progress.assert_not_called()
        update.assert_not_called()

    def test_publish_final_fails_closed_when_source_template_lookup_fails(self):
        params = {
            "page_id": "page_test",
            "html": "<!doctype html><html><body><h1>目标页</h1></body></html>",
            "source_template_id": "page_missing",
            "fork_manifest": self._fork_manifest(source_template_id="page_missing"),
        }

        with mock.patch.object(
            static_page,
            "cmd_template",
            return_value={"code": 1, "message": "PAGE_NOT_FOUND"},
        ), mock.patch.object(static_page, "cmd_update_progress") as update_progress, \
             mock.patch.object(static_page, "cmd_update") as update:
            result = static_page.cmd_publish_final(params)

        self.assertEqual(result["code"], 1)
        self.assertIn("无法读取 source_template_id", result["message"])
        update_progress.assert_not_called()
        update.assert_not_called()

    def test_publish_final_rejects_any_source_credential_overlap(self):
        params = {
            "page_id": "page_test",
            "html": (
                "<!doctype html><html><body><h1>目标页</h1>"
                "<script>const a={package_id:'pkg_source',signature:'sig_source'};"
                "const b={package_id:'pkg_new',signature:'sig_new'};"
                "const c={grant_id:'dg_new',signature:'grant_sig'};</script></body></html>"
            ),
            "source_template_id": "page_source",
            "fork_manifest": self._fork_manifest(
                source_package_ids=["pkg_source"],
                source_grant_ids=["dg_source"],
            ),
        }
        template_result = {
            "code": 0,
            "page_id": "page_source",
            "download_url": "https://pages.quantbuddy.cn/pages/official/page_source.html",
            "package_ids": ["pkg_source"],
            "grant_ids": ["dg_source"],
            "agent_reply_template": VALUATION_REPLY_TEMPLATE,
        }

        result, _ = self._capture_publish(
            params,
            template_result=template_result,
            update_overrides={
                "is_live": True,
                "package_ids": ["pkg_source", "pkg_new"],
                "grant_ids": ["dg_new"],
            },
        )

        self.assertEqual(result["code"], 1)
        self.assertIn("来源凭证", result["message"])
        self.assertNotIn("agent_reply_contract", result)

    def test_publish_final_rejects_leaked_source_signature_after_ids_change(self):
        source_html = (
            "<!doctype html><html><body><h1>来源页</h1>"
            "<script>const p={package_id:'pkg_source',signature:'sig_source'};</script>"
            "</body></html>"
        )
        params = {
            "page_id": "page_test",
            "html": (
                "<!doctype html><html><body><h1>目标页</h1>"
                "<script>const p={package_id:'pkg_new',signature:'sig_source'};</script>"
                "</body></html>"
            ),
            "source_template_id": "page_source",
            "fork_manifest": self._fork_manifest(
                source_html=source_html,
                source_package_ids=["pkg_source"],
            ),
        }
        template_result = {
            "code": 0,
            "page_id": "page_source",
            "download_url": "https://pages.quantbuddy.cn/pages/official/page_source.html",
            "package_ids": ["pkg_source"],
            "agent_reply_template": VALUATION_REPLY_TEMPLATE,
        }

        with mock.patch.object(static_page, "cmd_template", return_value=template_result), \
             mock.patch.object(static_page, "cmd_update_progress") as update_progress, \
             mock.patch.object(static_page, "cmd_update") as update:
            result = static_page.cmd_publish_final(params)

        self.assertEqual(result["code"], 1)
        self.assertIn("signature", result["message"])
        update_progress.assert_not_called()
        update.assert_not_called()

    def test_publish_final_rejects_missing_fork_required_section(self):
        params = {
            "page_id": "page_test",
            "html": "<!doctype html><html><body><h1>目标页</h1><h2>价格趋势</h2></body></html>",
            "source_template_id": "page_source",
            "fork_manifest": self._fork_manifest(required_sections=["价格趋势", "估值水位"]),
        }
        template_result = {
            "code": 0,
            "page_id": "page_source",
            "download_url": "https://pages.quantbuddy.cn/pages/official/page_source.html",
            "agent_reply_template": VALUATION_REPLY_TEMPLATE,
        }

        with mock.patch.object(static_page, "cmd_template", return_value=template_result), \
             mock.patch.object(static_page, "cmd_update_progress") as update_progress, \
             mock.patch.object(static_page, "cmd_update") as update:
            result = static_page.cmd_publish_final(params)

        self.assertEqual(result["code"], 1)
        self.assertIn("核心栏目", result["message"])
        self.assertIn("估值水位", result["message"])
        update_progress.assert_not_called()
        update.assert_not_called()

    def test_publish_final_rejects_missing_fork_required_output(self):
        params = {
            "page_id": "page_test",
            "html": "<!doctype html><html><body><h1>目标页</h1><script>const px=1;</script></body></html>",
            "source_template_id": "page_source",
            "fork_manifest": self._fork_manifest(required_outputs=["px", "ma20"]),
        }
        template_result = {
            "code": 0,
            "page_id": "page_source",
            "download_url": "https://pages.quantbuddy.cn/pages/official/page_source.html",
            "agent_reply_template": VALUATION_REPLY_TEMPLATE,
        }

        with mock.patch.object(static_page, "cmd_template", return_value=template_result), \
             mock.patch.object(static_page, "cmd_update_progress") as update_progress, \
             mock.patch.object(static_page, "cmd_update") as update:
            result = static_page.cmd_publish_final(params)

        self.assertEqual(result["code"], 1)
        self.assertIn("必需输出", result["message"])
        self.assertIn("ma20", result["message"])
        update_progress.assert_not_called()
        update.assert_not_called()

    def test_publish_final_rejects_missing_fork_card_runtime(self):
        params = {
            "page_id": "page_test",
            "html": "<!doctype html><html><body><h1>目标页</h1></body></html>",
            "source_template_id": "page_source",
            "fork_manifest": self._fork_manifest(card_runtime_required=True),
        }
        template_result = {
            "code": 0,
            "page_id": "page_source",
            "download_url": "https://pages.quantbuddy.cn/pages/official/page_source.html",
            "agent_reply_template": VALUATION_REPLY_TEMPLATE,
        }

        with mock.patch.object(static_page, "cmd_template", return_value=template_result), \
             mock.patch.object(static_page, "cmd_update_progress") as update_progress, \
             mock.patch.object(static_page, "cmd_update") as update:
            result = static_page.cmd_publish_final(params)

        self.assertEqual(result["code"], 1)
        self.assertIn("Card Runtime", result["message"])
        update_progress.assert_not_called()
        update.assert_not_called()

    def test_publish_final_accepts_complete_fork_manifest_with_new_credentials(self):
        params = {
            "page_id": "page_test",
            "html": (
                "<!doctype html><html><body><h1>行云科技</h1>"
                "<h2>价格趋势</h2><h2>估值水位</h2>"
                "<script>const px=1; const ma20=1;"
                "const p={package_id:'pkg_new',signature:'sig_new'};"
                "const g={grant_id:'dg_new',signature:'grant_sig'};</script>"
                "<template data-qb-card-template></template>"
                "<script data-qb-card-manifest>{}</script>"
                "<script data-qb-card-runtime></script></body></html>"
            ),
            "source_template_id": "page_source",
            "fork_manifest": self._fork_manifest(
                source_package_ids=["pkg_source"],
                source_grant_ids=["dg_source"],
                required_sections=["价格趋势", "估值水位"],
                required_outputs=["px", "ma20"],
                card_runtime_required=True,
                source_markers=["长江电力", "SH600900"],
            ),
        }
        template_result = {
            "code": 0,
            "page_id": "page_source",
            "download_url": "https://pages.quantbuddy.cn/pages/official/page_source.html",
            "package_ids": ["pkg_source"],
            "grant_ids": ["dg_source"],
            "agent_reply_template": VALUATION_REPLY_TEMPLATE,
        }

        result, _ = self._capture_publish(
            params,
            template_result=template_result,
            update_overrides={
                "is_live": True,
                "package_ids": ["pkg_new"],
                "grant_ids": ["dg_new"],
            },
        )

        self.assertEqual(result["code"], 0)
        self.assertTrue(result["fork_manifest_validation"]["ok"])
        self.assertEqual(result["agent_reply_contract"]["operation"], "publish_final")

    def test_publish_final_rejects_fork_credential_role_count_shrink(self):
        params = {
            "page_id": "page_test",
            "html": (
                "<!doctype html><html><body><h1>目标页</h1>"
                "<script>const p={package_id:'pkg_new',signature:'sig_new'};"
                "const g={grant_id:'dg_new',signature:'grant_sig'};</script></body></html>"
            ),
            "source_template_id": "page_source",
            "fork_manifest": self._fork_manifest(
                source_package_ids=["pkg_source_1", "pkg_source_2"],
                source_grant_ids=["dg_source_1", "dg_source_2"],
                minimum_target_package_count=2,
                minimum_target_grant_count=2,
            ),
        }
        template_result = {
            "code": 0,
            "page_id": "page_source",
            "download_url": "https://pages.quantbuddy.cn/pages/official/page_source.html",
            "package_ids": ["pkg_source_1", "pkg_source_2"],
            "grant_ids": ["dg_source_1", "dg_source_2"],
            "agent_reply_template": VALUATION_REPLY_TEMPLATE,
        }

        result, _ = self._capture_publish(
            params,
            template_result=template_result,
            update_overrides={
                "is_live": True,
                "package_ids": ["pkg_new"],
                "grant_ids": ["dg_new"],
            },
        )

        self.assertEqual(result["code"], 1)
        self.assertIn("能力缩水", result["message"])

    def test_publish_final_accepts_audited_credential_count_reduction(self):
        params = {
            "page_id": "page_test",
            "html": (
                "<!doctype html><html><body><h1>目标页</h1>"
                "<script>const p={package_id:'pkg_new',signature:'sig_new'};</script>"
                "</body></html>"
            ),
            "source_template_id": "page_source",
            "fork_manifest": self._fork_manifest(
                source_package_ids=["pkg_source_1", "pkg_source_2"],
                minimum_target_package_count=1,
                credential_count_reduction_reason="两个来源包合并为一个同口径目标包",
            ),
        }
        template_result = {
            "code": 0,
            "page_id": "page_source",
            "download_url": "https://pages.quantbuddy.cn/pages/official/page_source.html",
            "package_ids": ["pkg_source_1", "pkg_source_2"],
            "agent_reply_template": VALUATION_REPLY_TEMPLATE,
        }

        result, _ = self._capture_publish(
            params,
            template_result=template_result,
            update_overrides={"is_live": True, "package_ids": ["pkg_new"], "grant_ids": []},
        )

        self.assertEqual(result["code"], 0)
        self.assertEqual(
            result["fork_manifest_validation"]["credential_count_reduction_reason"],
            "两个来源包合并为一个同口径目标包",
        )

    def test_fork_prepare_downloads_source_and_writes_manifest(self):
        source_html = (
            "<!doctype html><html><body><h1>长江电力 SH600900</h1>"
            "<h2>价格趋势</h2><h2>估值水位</h2>"
            "<script>const p={package_id:'pkg_source',signature:'sig_source'};"
            "const g={grant_id:'dg_source',signature:'grant_sig'};</script>"
            "<template data-qb-card-template></template>"
            "<script data-qb-card-manifest>{}</script>"
            "<script data-qb-card-runtime></script></body></html>"
        )
        template_result = {
            "code": 0,
            "page_id": "page_source",
            "template_id": "page_source",
            "download_url": "https://pages.quantbuddy.cn/pages/official/page_source.html",
            "package_ids": ["pkg_source"],
            "packages": [{
                "package_id": "pkg_source",
                "formulas": ["px = 收盘价(长江电力)", "ma60=平均(\"px\",60)"],
            }],
            "grant_ids": ["dg_source"],
            "page_context": {"core_sections": ["价格趋势", "估值水位"]},
            "agent_reply_template": VALUATION_REPLY_TEMPLATE,
            "card_runtime_supported": True,
            "card_required_outputs": ["px", "ma20"],
        }

        with tempfile.TemporaryDirectory() as temp_dir, \
             mock.patch.object(static_page, "cmd_template", return_value=template_result), \
             mock.patch.object(static_page, "_fetch_oss", return_value=(source_html, None)):
            result = static_page.cmd_fork_prepare({
                "source_template_id": "page_source",
                "output_dir": temp_dir,
                "source_markers": ["长江电力", "SH600900"],
                "target_asset": "SZ300209",
                "asset_replacements": {
                    "长江电力": "行云科技",
                    "SH600900": "SZ300209",
                },
            })

            self.assertEqual(result["code"], 0)
            self.assertTrue(Path(result["html_file"]).exists())
            self.assertTrue(Path(result["working_html_file"]).exists())
            self.assertTrue(Path(result["manifest_file"]).exists())
            working_html = Path(result["working_html_file"]).read_text(encoding="utf-8")
            manifest = json.loads(Path(result["manifest_file"]).read_text(encoding="utf-8"))

        self.assertEqual(manifest["version"], "fork_manifest_v1")
        self.assertEqual(manifest["source_template_id"], "page_source")
        self.assertEqual(manifest["source_package_ids"], ["pkg_source"])
        self.assertEqual(manifest["source_grant_ids"], ["dg_source"])
        self.assertEqual(len(manifest["source_signature_sha256"]), 2)
        self.assertEqual(manifest["required_sections"], ["价格趋势", "估值水位"])
        self.assertEqual(manifest["required_outputs"], ["px", "ma20", "ma60"])
        self.assertEqual(manifest["minimum_target_package_count"], 1)
        self.assertEqual(manifest["minimum_target_grant_count"], 1)
        self.assertTrue(manifest["card_runtime_required"])
        self.assertEqual(manifest["source_markers"], ["长江电力", "SH600900"])
        self.assertEqual(manifest["target_asset"], "SZ300209")
        self.assertNotIn("长江电力", working_html)
        self.assertIn("行云科技", working_html)
        self.assertEqual(manifest["replacement_audit"][0]["count"], 1)
        self.assertEqual(result["agent_reply_hint"]["source_template_id"], "page_source")
        self.assertEqual(
            result["agent_reply_hint"]["template_ref"],
            "single_stock_valuation_quality_v1",
        )

    def test_fork_prepare_requires_reason_when_lowering_credential_count(self):
        source_html = (
            "<!doctype html><html><body><h1>来源页</h1>"
            "<script>"
            "const a={package_id:'pkg_source_1',signature:'sig_1'};"
            "const b={package_id:'pkg_source_2',signature:'sig_2'};"
            "</script></body></html>"
        )
        template_result = {
            "code": 0,
            "page_id": "page_source",
            "download_url": "https://pages.quantbuddy.cn/pages/official/page_source.html",
            "package_ids": ["pkg_source_1", "pkg_source_2"],
        }

        with tempfile.TemporaryDirectory() as temp_dir, \
             mock.patch.object(static_page, "cmd_template", return_value=template_result), \
             mock.patch.object(static_page, "_fetch_oss", return_value=(source_html, None)):
            result = static_page.cmd_fork_prepare({
                "source_template_id": "page_source",
                "output_dir": temp_dir,
                "minimum_target_package_count": 1,
            })

        self.assertEqual(result["code"], 1)
        self.assertIn("credential_count_reduction_reason", result["message"])

    def test_publish_final_restores_bound_fork_from_task_id(self):
        source_html = (
            "<!doctype html><html><body><h1>来源页</h1><h2>价格趋势</h2>"
            "<script>const px=1;const p={package_id:'pkg_source',signature:'sig_source'};</script>"
            "</body></html>"
        )
        template_result = {
            "code": 0,
            "page_id": "page_source",
            "template_id": "page_source",
            "download_url": "https://pages.quantbuddy.cn/pages/official/page_source.html",
            "package_ids": ["pkg_source"],
            "card_required_outputs": ["px"],
            "agent_reply_template": VALUATION_REPLY_TEMPLATE,
        }
        final_html = (
            "<!doctype html><html><body><h1>目标页</h1><h2>价格趋势</h2>"
            "<script>const px=1;const p={package_id:'pkg_new',signature:'sig_new'};</script>"
            "</body></html>"
        )

        with tempfile.TemporaryDirectory() as temp_dir, \
             mock.patch.dict(os.environ, {"QBV_FORK_BINDING_DIR": str(Path(temp_dir) / "bindings")}), \
             mock.patch.object(static_page, "cmd_template", return_value=template_result), \
             mock.patch.object(static_page, "_fetch_oss", return_value=(source_html, None)):
            prepared = static_page.cmd_fork_prepare({
                "task_id": "task-fork-bound",
                "source_template_id": "page_source",
                "output_dir": str(Path(temp_dir) / "fork"),
            })
            self.assertEqual(prepared["code"], 0)

            result, _ = self._capture_publish(
                {
                    "task_id": "task-fork-bound",
                    "page_id": "page_test",
                    "html": final_html,
                },
                template_result=template_result,
                update_overrides={
                    "is_live": True,
                    "package_ids": ["pkg_new"],
                    "grant_ids": [],
                },
            )

        self.assertEqual(result["code"], 0)
        self.assertEqual(
            result["agent_reply_template_resolution"]["source_template_id"],
            "page_source",
        )
        self.assertTrue(result["fork_manifest_validation"]["ok"])
        self.assertEqual(result["fork_task_binding"]["mode"], "task_binding")
        self.assertEqual(result["fork_task_binding"]["status"], "published")

    def test_bound_fork_cannot_publish_unrelated_dashboard_by_omitting_source(self):
        source_html = "<!doctype html><html><body><h1>来源页</h1><h2>必须保留的栏目</h2></body></html>"
        template_result = {
            "code": 0,
            "page_id": "page_source",
            "template_id": "page_source",
            "download_url": "https://pages.quantbuddy.cn/pages/official/page_source.html",
            "agent_reply_template": VALUATION_REPLY_TEMPLATE,
        }

        with tempfile.TemporaryDirectory() as temp_dir, \
             mock.patch.dict(os.environ, {"QBV_FORK_BINDING_DIR": str(Path(temp_dir) / "bindings")}), \
             mock.patch.object(static_page, "cmd_template", return_value=template_result), \
             mock.patch.object(static_page, "_fetch_oss", return_value=(source_html, None)):
            prepared = static_page.cmd_fork_prepare({
                "task_id": "task-fork-reject",
                "source_template_id": "page_source",
                "output_dir": str(Path(temp_dir) / "fork"),
            })
            self.assertEqual(prepared["code"], 0)

            with mock.patch.object(static_page, "cmd_update_progress") as update_progress, \
                 mock.patch.object(static_page, "cmd_update") as update:
                result = static_page.cmd_publish_final({
                    "task_id": "task-fork-reject",
                    "page_id": "page_test",
                    "html": "<!doctype html><html><body><h1>无关自建页</h1></body></html>",
                })

        self.assertEqual(result["code"], 1)
        self.assertIn("核心栏目", result["message"])
        self.assertEqual(result["fork_task_binding"]["mode"], "task_binding")
        update_progress.assert_not_called()
        update.assert_not_called()

    def test_fork_task_binding_rejects_conflicting_source_template(self):
        source_html = "<!doctype html><html><body><h1>来源页</h1></body></html>"
        template_result = {
            "code": 0,
            "page_id": "page_source",
            "template_id": "page_source",
            "download_url": "https://pages.quantbuddy.cn/pages/official/page_source.html",
        }

        with tempfile.TemporaryDirectory() as temp_dir, \
             mock.patch.dict(os.environ, {"QBV_FORK_BINDING_DIR": str(Path(temp_dir) / "bindings")}), \
             mock.patch.object(static_page, "cmd_template", return_value=template_result), \
             mock.patch.object(static_page, "_fetch_oss", return_value=(source_html, None)):
            prepared = static_page.cmd_fork_prepare({
                "task_id": "task-fork-conflict",
                "source_template_id": "page_source",
                "output_dir": str(Path(temp_dir) / "fork"),
            })
            self.assertEqual(prepared["code"], 0)

            with mock.patch.object(static_page, "cmd_update_progress") as update_progress, \
                 mock.patch.object(static_page, "cmd_update") as update:
                result = static_page.cmd_publish_final({
                    "task_id": "task-fork-conflict",
                    "page_id": "page_test",
                    "html": "<!doctype html><html><body><h1>目标页</h1></body></html>",
                    "source_template_id": "page_other",
                })

        self.assertEqual(result["code"], 1)
        self.assertEqual(result["error"], "FORK_TASK_BINDING_CONFLICT")
        update_progress.assert_not_called()
        update.assert_not_called()

    def test_fork_task_binding_is_isolated_by_task_id(self):
        source_html = "<!doctype html><html><body><h1>来源页</h1><h2>来源栏目</h2></body></html>"
        template_result = {
            "code": 0,
            "page_id": "page_source",
            "template_id": "page_source",
            "download_url": "https://pages.quantbuddy.cn/pages/official/page_source.html",
        }

        with tempfile.TemporaryDirectory() as temp_dir, \
             mock.patch.dict(os.environ, {"QBV_FORK_BINDING_DIR": str(Path(temp_dir) / "bindings")}), \
             mock.patch.object(static_page, "cmd_template", return_value=template_result), \
             mock.patch.object(static_page, "_fetch_oss", return_value=(source_html, None)):
            prepared = static_page.cmd_fork_prepare({
                "task_id": "task-fork-a",
                "source_template_id": "page_source",
                "output_dir": str(Path(temp_dir) / "fork"),
            })
            self.assertEqual(prepared["code"], 0)

            result, _ = self._capture_publish({
                "task_id": "task-unmatched-b",
                "page_id": "page_test",
                "html": "<!doctype html><html><body><h1>独立未命中页</h1></body></html>",
            })

        self.assertEqual(result["code"], 0)
        self.assertEqual(
            result["agent_reply_template_resolution"]["source_template_id"],
            "",
        )
        self.assertNotIn("fork_manifest_validation", result)

    def test_publish_final_fails_closed_when_update_returns_wrong_page_id(self):
        params = {
            "page_id": "page_test",
            "html": "<!doctype html><html><head><title>估值活页</title></head><body></body></html>",
            "agent_reply_template": VALUATION_REPLY_TEMPLATE,
        }

        result, _ = self._capture_publish(
            params,
            update_overrides={
                "page_id": "page_other",
                "url": "https://pages.quantbuddy.cn/pages/test/page_other.html",
            },
        )

        self.assertEqual(result["code"], 1)
        self.assertIn("page_id", result["message"])
        self.assertNotIn("agent_reply_contract", result)
        self.assertEqual(result["publish_final"]["final_html_published"], False)

    def test_publish_final_fails_closed_when_source_template_url_is_returned(self):
        source_url = "https://pages.quantbuddy.cn/pages/official/page_source.html"
        params = {
            "page_id": "page_test",
            "html": "<!doctype html><html><head><title>估值活页</title></head><body></body></html>",
            "source_template_id": "page_source",
        }
        template_result = {
            "code": 0,
            "page_id": "page_source",
            "download_url": source_url,
            "agent_reply_template": VALUATION_REPLY_TEMPLATE,
        }

        result, _ = self._capture_publish(
            params,
            template_result=template_result,
            update_overrides={"url": source_url},
        )

        self.assertEqual(result["code"], 1)
        self.assertIn("来源模板", result["message"])
        self.assertNotIn("agent_reply_contract", result)

    def test_publish_final_fails_closed_when_first_page_url_changes(self):
        params = {
            "page_id": "page_test",
            "first_page_url": "https://pages.quantbuddy.cn/pages/first/page_test.html",
            "html": "<!doctype html><html><head><title>估值活页</title></head><body></body></html>",
            "agent_reply_template": VALUATION_REPLY_TEMPLATE,
        }

        result, _ = self._capture_publish(params)

        self.assertEqual(result["code"], 1)
        self.assertIn("首链 URL", result["message"])
        self.assertNotIn("agent_reply_contract", result)

    def test_professional_live_publish_requires_user_package_or_grant(self):
        params = {
            "page_id": "page_test",
            "html": (
                "<!doctype html><html><head><title>估值活页</title></head><body>"
                "<script>const package_id='pkg_source'; const signature='sig_source'; "
                "queryFormulaPackage(package_id, signature);</script></body></html>"
            ),
            "source_template_id": "page_source",
        }
        template_result = {
            "code": 0,
            "page_id": "page_source",
            "download_url": "https://pages.quantbuddy.cn/pages/official/page_source.html",
            "package_ids": ["pkg_source"],
            "agent_reply_template": VALUATION_REPLY_TEMPLATE,
        }

        result, _ = self._capture_publish(
            params,
            template_result=template_result,
            update_overrides={"is_live": True, "package_ids": ["pkg_source"]},
        )

        self.assertEqual(result["code"], 1)
        self.assertIn("来源凭证", result["message"])
        self.assertNotIn("agent_reply_contract", result)

    def test_publish_final_infers_valuation_template_from_page_tags(self):
        params = {
            "page_id": "page_test",
            "html": "<!doctype html><html><body><h2>估值水位</h2><h2>财务质量</h2></body></html>",
            "title": "兆易创新 · 估值与财务质量",
            "description": "观察 PE、PB、PCF 历史水位以及 ROE、现金流和负债率。",
            "scene_tags": ["看标的"],
            "paradigm_tags": ["盈利质量", "价值陷阱"],
            "user_query": "做一个兆易创新的估值和财务质量活页",
        }

        result, captured = self._capture_publish(params)

        self.assertEqual(
            captured["update_params"]["agent_reply_template"],
            VALUATION_REPLY_TEMPLATE,
        )
        self.assertTrue(result["agent_reply_contract"]["required"])
        self.assertEqual(
            result["agent_reply_contract"]["template_ref"],
            "single_stock_valuation_quality_v1",
        )
        self.assertEqual(result["agent_reply_contract"]["terminal"], True)
        self.assertEqual(result["agent_reply_contract"]["operation"], "publish_final")
        self.assertEqual(result["agent_reply_contract"]["page_id"], "page_test")

    def test_publish_final_inherits_reply_template_from_source_template(self):
        params = {
            "page_id": "page_test",
            "html": "<!doctype html><html><head><title>估值活页</title></head><body><h2>估值水位</h2></body></html>",
            "source_template_id": "page_source",
        }
        template_result = {
            "code": 0,
            "page_id": "page_source",
            "agent_reply_template": VALUATION_REPLY_TEMPLATE,
        }

        result, captured = self._capture_publish(params, template_result=template_result)

        self.assertEqual(
            captured["update_params"]["agent_reply_template"],
            VALUATION_REPLY_TEMPLATE,
        )
        self.assertTrue(result["agent_reply_contract"]["required"])

    def test_publish_final_uses_generic_fallback_when_source_has_no_template(self):
        params = {
            "page_id": "page_test",
            "html": "<!doctype html><html><head><title>专项监控</title></head><body><h2>信号概览</h2></body></html>",
            "source_template_id": "page_source",
            "require_agent_reply_template": True,
        }
        template_result = {
            "code": 0,
            "page_id": "page_source",
            "agent_reply_template": None,
        }

        result, captured = self._capture_publish(params, template_result=template_result)

        self.assertEqual(result["code"], 0)
        self.assertEqual(captured["update_params"]["agent_reply_template"], GENERIC_REPLY_TEMPLATE)
        self.assertEqual(result["agent_reply_template_resolution"]["mode"], "generic_fallback")
        self.assertEqual(result["agent_reply_template_resolution"]["page_context_mode"], "regenerated")

    def test_progress_payload_preserves_reply_template_metadata(self):
        payload = static_page._progress_publish_payload(
            {"agent_reply_template": VALUATION_REPLY_TEMPLATE},
            "<!doctype html><html></html>",
            require_page_id=False,
        )

        self.assertEqual(payload["agent_reply_template"], VALUATION_REPLY_TEMPLATE)

    def test_progress_payload_suppresses_autotag_with_explicit_empty_tags(self):
        payload = static_page._progress_publish_payload(
            {},
            "<!doctype html><html></html>",
            require_page_id=False,
        )

        self.assertEqual(payload["scene_tags"], [])
        self.assertEqual(payload["paradigm_tags"], [])

    def test_formal_update_does_not_inherit_progress_tag_suppression(self):
        _, captured = self._capture_http_command(static_page.cmd_update, {
            "page_id": "page_existing",
            "html": "<!doctype html><html><head><title>正式活页</title></head><body><h1>正式活页</h1></body></html>",
        })

        self.assertNotIn("scene_tags", captured["body"])
        self.assertNotIn("paradigm_tags", captured["body"])

    def test_new_page_suppresses_terminal_contract_even_with_reply_metadata(self):
        result, _ = self._capture_http_command(static_page.cmd_new_page, {
            "title": "活页生成中",
            "agent_reply_template": VALUATION_REPLY_TEMPLATE,
        })

        self.assertNotIn("agent_reply_contract", result)
        self.assertEqual(result["agent_reply_hint"]["terminal"], False)
        self.assertEqual(result["agent_reply_hint"]["resource_role"], "existing_page")
        self.assertEqual(result["progress"]["page_status"], "running")

    def test_update_progress_suppresses_terminal_contract_even_with_reply_metadata(self):
        result, _ = self._capture_http_command(static_page.cmd_update_progress, {
            "page_id": "page_existing",
            "current_step": "verify",
            "agent_reply_template": VALUATION_REPLY_TEMPLATE,
        })

        self.assertNotIn("agent_reply_contract", result)
        self.assertEqual(result["agent_reply_hint"]["terminal"], False)
        self.assertEqual(result["progress"]["current_step"], "verify")

    def test_waiting_input_returns_resumable_non_terminal_hint(self):
        result, _ = self._capture_http_command(static_page.cmd_update_progress, {
            "task_id": "task_waiting",
            "page_id": "page_existing",
            "page_status": "waiting_input",
            "current_step": "formula_validation",
            "required_input": {
                "id": "market_scope",
                "prompt": "请选择本页市场口径",
                "options": [
                    {"value": "a_share", "label": "A股"},
                    {"value": "hk", "label": "港股"},
                ],
                "resume_step": "formula_validation",
            },
        })

        self.assertNotIn("agent_reply_contract", result)
        hint = result["agent_reply_hint"]
        self.assertEqual(hint["terminal"], False)
        self.assertEqual(hint["interaction_required"], True)
        self.assertEqual(hint["task_id"], "task_waiting")
        self.assertEqual(hint["page_id"], "page_existing")
        self.assertEqual(hint["resume_step"], "formula_validation")
        self.assertEqual(hint["required_input"]["id"], "market_scope")

    def test_running_progress_clears_waiting_input_contract(self):
        result, _ = self._capture_http_command(static_page.cmd_update_progress, {
            "task_id": "task_waiting",
            "page_id": "page_existing",
            "page_status": "running",
            "current_step": "formula_validation",
        })

        self.assertEqual(result["page_id"], "page_existing")
        self.assertEqual(result["progress"]["page_status"], "running")
        self.assertIsNone(result["progress"]["required_input"])
        self.assertEqual(result["agent_reply_hint"]["interaction_required"], False)

    def test_publish_final_respects_explicit_reply_template_clear(self):
        params = {
            "page_id": "page_test",
            "html": "<!doctype html><html><head><title>估值活页</title></head><body></body></html>",
            "title": "兆易创新 · 估值与财务质量",
            "scene_tags": ["看标的"],
            "paradigm_tags": ["盈利质量"],
            "agent_reply_template": None,
        }

        result, captured = self._capture_publish(params)

        self.assertIn("agent_reply_template", captured["update_params"])
        self.assertIsNone(captured["update_params"]["agent_reply_template"])
        self.assertEqual(result["agent_reply_contract"]["terminal"], True)
        self.assertEqual(result["agent_reply_contract"]["operation"], "publish_final")
        self.assertEqual(result["agent_reply_contract"]["required"], False)

    def test_source_hybrid_template_regenerates_page_context_without_inheriting_source_context(self):
        params = {
            "page_id": "page_test",
            "html": "<!doctype html><html><head><title>双动量策略</title></head><body><h2>策略信号</h2><h2>净值表现</h2></body></html>",
            "source_template_id": "page_source",
        }
        template_result = {
            "code": 0,
            "page_id": "page_source",
            "page_context": {"version": "page_context_v1", "summary": "来源模板上下文，不应复制。"},
            "agent_reply_template": HYBRID_REPLY_TEMPLATE,
        }

        result, captured = self._capture_publish(params, template_result=template_result)

        context = captured["update_params"]["page_context"]
        self.assertNotEqual(context["summary"], template_result["page_context"]["summary"])
        self.assertEqual(context["core_sections"], ["策略信号", "净值表现"])
        self.assertEqual(result["agent_reply_template_resolution"]["page_context_mode"], "regenerated")
        self.assertFalse(result["agent_reply_template_resolution"]["source_page_context_inherited"])

    def test_v2_hybrid_explicit_page_context_clear_fails_closed(self):
        params = {
            "page_id": "page_test",
            "html": "<!doctype html><html><head><title>双动量策略</title></head><body></body></html>",
            "agent_reply_template": HYBRID_REPLY_TEMPLATE,
            "page_context": None,
        }

        with mock.patch.object(static_page, "cmd_update_progress") as update_progress, \
             mock.patch.object(static_page, "cmd_update") as update:
            result = static_page.cmd_publish_final(copy.deepcopy(params))

        self.assertEqual(result["code"], 1)
        self.assertIn("page_context", result["message"])
        update_progress.assert_not_called()
        update.assert_not_called()

    def test_v1_hybrid_remains_compatible_without_page_context(self):
        params = {
            "agent_reply_template": {
                "version": "reply_template_v1",
                "template_ref": "capital_flow_quant_signal_v1",
                "reply_scope": "hybrid",
                "output_format": "markdown",
            },
        }
        self.assertIsNone(static_page._validate_reply_metadata_pair(params))

    def test_professional_reply_template_routing(self):
        cases = [
            ("宏观政策事件影响活页", "market_event_impact_v1"),
            ("机器人主题产业链机会", "sector_theme_opportunity_v1"),
            ("三只银行同业对比", "multi_asset_compare_v1"),
            ("双动量量化信号", "capital_flow_quant_signal_v1"),
            ("ETF基金估值", "fund_etf_bond_profile_v1"),
            ("英伟达美股财报跟踪", "hk_us_overseas_asset_v1"),
            ("兆易创新估值与财务质量", "single_stock_valuation_quality_v1"),
            ("某公司个股深度分析", "single_stock_deep_dive_v1"),
        ]
        for title, expected in cases:
            with self.subTest(title=title):
                meta = static_page._infer_agent_reply_template_from_publish_params({"title": title})
                self.assertEqual(meta["template_ref"], expected)

    def _capture_http_command(self, command, params):
        captured = {}

        def fake_http(method, url, headers, body, timeout=None):
            captured.update({"method": method, "url": url, "body": copy.deepcopy(body)})
            return {
                "code": 0,
                "page_id": body.get("page_id") or "page_new",
                "url": "https://pages.quantbuddy.cn/pages/test/page_new.html",
                "page_context": body.get("page_context"),
                "agent_reply_template": body.get("agent_reply_template"),
            }

        with mock.patch.object(static_page.C, "load_config_require_key", return_value={"api_key": "test", "endpoint": "https://example.test"}), \
             mock.patch.object(static_page.C, "endpoint_of", return_value="https://example.test"), \
             mock.patch.object(static_page.C, "api_url", side_effect=lambda endpoint, path: endpoint + path), \
             mock.patch.object(static_page.C, "http_json", side_effect=fake_http), \
             mock.patch.object(static_page, "_ensure_share_shell", side_effect=lambda html, _params: (html, {"ok": True})), \
             mock.patch.object(static_page, "_maybe_verify_card_runtime", return_value=None), \
             mock.patch.object(static_page, "_package_runtime_check", return_value={"status": "ok"}):
            result = command(copy.deepcopy(params))
        return result, captured

    def test_direct_upload_adds_generic_fallback_and_regenerated_page_context(self):
        result, captured = self._capture_http_command(static_page.cmd_upload, {
            "html": "<!doctype html><html><head><title>专项监控</title></head><body><h2>信号概览</h2></body></html>",
        })

        self.assertEqual(result["code"], 0)
        self.assertEqual(captured["body"]["agent_reply_template"], GENERIC_REPLY_TEMPLATE)
        self.assertEqual(captured["body"]["page_context"]["core_sections"], ["信号概览"])
        self.assertEqual(result["agent_reply_contract"]["terminal"], True)
        self.assertEqual(result["agent_reply_contract"]["operation"], "upload")
        self.assertEqual(result["agent_reply_contract"]["page_id"], "page_new")
        self.assertEqual(
            result["agent_reply_contract"]["public_url"],
            "https://pages.quantbuddy.cn/pages/test/page_new.html",
        )

    def test_page_context_ignores_shared_shell_modal_heading(self):
        result, captured = self._capture_http_command(static_page.cmd_upload, {
            "html": (
                "<!doctype html><html><head><title>专项监控</title></head><body>"
                "<main><h2>核心状态</h2></main>"
                "<div class='share-modal'><h2 id='sharePosterTitle'>分享海报</h2></div>"
                "</body></html>"
            ),
        })

        self.assertEqual(result["code"], 0)
        self.assertEqual(captured["body"]["page_context"]["core_sections"], ["核心状态"])

    def test_direct_update_preserves_metadata_when_omitted(self):
        result, captured = self._capture_http_command(static_page.cmd_update, {
            "page_id": "page_existing",
            "html": "<!doctype html><html><head><title>旧页更新</title></head><body></body></html>",
        })

        self.assertEqual(result["code"], 0)
        self.assertNotIn("page_context", captured["body"])
        self.assertNotIn("agent_reply_template", captured["body"])

    def test_direct_update_passes_explicit_v2_hybrid_metadata(self):
        context = {"version": "page_context_v1", "summary": "用于解释双动量策略信号。"}
        result, captured = self._capture_http_command(static_page.cmd_update, {
            "page_id": "page_existing",
            "html": "<!doctype html><html><head><title>双动量</title></head><body></body></html>",
            "page_context": context,
            "agent_reply_template": HYBRID_REPLY_TEMPLATE,
        })

        self.assertEqual(result["code"], 0)
        self.assertEqual(captured["body"]["page_context"], context)
        self.assertEqual(captured["body"]["agent_reply_template"], HYBRID_REPLY_TEMPLATE)

    def test_direct_update_passes_reply_contract_binding_marker(self):
        binding = {
            "version": "reply_contract_binding_v1",
            "profile_ref": "capital_quant_hybrid",
            "revision": "official_templates_202607_v1",
            "managed_by": "manual",
        }
        result, captured = self._capture_http_command(static_page.cmd_update, {
            "page_id": "page_existing",
            "html": "<!doctype html><html><head><title>策略页</title></head><body></body></html>",
            "reply_contract_binding": binding,
        })

        self.assertEqual(result["code"], 0)
        self.assertEqual(captured["body"]["reply_contract_binding"], binding)

    def test_init_reply_metadata_dry_run_plans_missing_page(self):
        page = {
            "page_id": "page_missing",
            "status": "active",
            "title": "情绪战法活页",
            "description": "涨跌停与资金面跟踪",
            "page_context": None,
            "agent_reply_template": None,
        }
        downloaded = {
            **page,
            "code": 0,
            "owner": "skill_test",
            "html": "<!doctype html><html><body><h2>情绪周期</h2><h2>资金验证</h2></body></html>",
            "scene_tags": [{"name": "做跟踪"}],
            "paradigm_tags": [{"name": "市场情绪周期"}],
        }

        with mock.patch.object(static_page, "cmd_list", return_value={"code": 0, "data": {"total": 1, "items": [page]}}), \
             mock.patch.object(static_page, "cmd_download", return_value=copy.deepcopy(downloaded)), \
             mock.patch.object(static_page, "cmd_update") as update:
            result = static_page.cmd_init_reply_metadata({"scope": "test_all"})

        self.assertEqual(result["code"], 0)
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["planned"], 1)
        self.assertEqual(result["results"][0]["status"], "planned")
        self.assertIn("agent_reply_template", result["results"][0]["missing"])
        self.assertEqual(result["results"][0]["template_ref"], "capital_flow_quant_signal_v1")
        update.assert_not_called()

    def test_init_reply_metadata_updates_with_inferred_metadata(self):
        page = {
            "page_id": "page_missing",
            "status": "active",
            "title": "某公司个股深度分析",
            "description": "经营与风险画像",
            "page_context": None,
            "agent_reply_template": None,
        }
        downloaded = {
            **page,
            "code": 0,
            "owner": "skill_test",
            "html": "<!doctype html><html><body><h2>公司画像</h2></body></html>",
            "scene_tags": [{"name": "看标的"}],
            "paradigm_tags": [],
        }
        updates = []

        def fake_update(params):
            updates.append(copy.deepcopy(params))
            return {"code": 0, "page_id": params["page_id"], "url": "https://pages.quantbuddy.cn/pages/test/page_missing.html"}

        with mock.patch.object(static_page, "cmd_list", return_value={"code": 0, "data": {"total": 1, "items": [page]}}), \
             mock.patch.object(static_page, "cmd_download", return_value=copy.deepcopy(downloaded)), \
             mock.patch.object(static_page, "cmd_update", side_effect=fake_update):
            result = static_page.cmd_init_reply_metadata({"dry_run": False})

        self.assertEqual(result["code"], 0)
        self.assertEqual(result["updated"], 1)
        self.assertEqual(result["results"][0]["status"], "updated")
        self.assertEqual(updates[0]["html"], downloaded["html"])
        self.assertFalse(updates[0]["ensure_share_shell"])
        self.assertEqual(updates[0]["agent_reply_template"]["template_ref"], "single_stock_deep_dive_v1")
        self.assertEqual(updates[0]["page_context"]["core_sections"], ["公司画像"])

    def test_update_template_returns_terminal_update_template_contract(self):
        template_record = {
            "code": 0,
            "template_id": "page_template",
            "page_id": "page_template",
            "download_url": "https://pages.quantbuddy.cn/pages/official/page_template.html",
            "agent_reply_template": VALUATION_REPLY_TEMPLATE,
        }
        with mock.patch.object(static_page.C, "load_config_require_key", return_value={"api_key": "test"}), \
             mock.patch.object(static_page.C, "endpoint_of", return_value="https://example.test"), \
             mock.patch.object(static_page.C, "api_url", side_effect=lambda endpoint, path: endpoint + path), \
             mock.patch.object(static_page.C, "http_json", return_value={"code": 0, "template_id": "page_template"}), \
             mock.patch.object(static_page, "cmd_template", return_value=copy.deepcopy(template_record)):
            result = static_page.cmd_update_template({
                "template_id": "page_template",
                "title": "更新后的模板",
            })

        contract = result["agent_reply_contract"]
        self.assertEqual(contract["terminal"], True)
        self.assertEqual(contract["operation"], "update_template")
        self.assertEqual(contract["page_id"], "page_template")
        self.assertEqual(contract["public_url"], template_record["download_url"])


if __name__ == "__main__":
    unittest.main()
