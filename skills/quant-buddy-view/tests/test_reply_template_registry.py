import json
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
REPLY_DIR = SKILL_ROOT / "reply-templates"


class ReplyTemplateRegistryTest(unittest.TestCase):
    def test_index_matches_markdown_templates(self):
        registry = json.loads((REPLY_DIR / "index.json").read_text(encoding="utf-8"))
        entries = registry.get("templates") or []
        ids = [entry.get("id") for entry in entries]
        files = [entry.get("file") for entry in entries]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(files), len(set(files)))

        markdown_files = {
            path.name for path in REPLY_DIR.glob("*_v1.md")
        }
        self.assertEqual(set(files), markdown_files)
        for entry in entries:
            path = REPLY_DIR / entry["file"]
            text = path.read_text(encoding="utf-8")
            self.assertIn(f"id: {entry['id']}", text)
            self.assertEqual(path.stem, entry["id"])

    def test_official_binding_manifest_has_23_unique_pages_and_valid_profiles(self):
        manifest_path = SKILL_ROOT / "migrations" / "official-template-bindings-v2.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        profiles = manifest.get("profiles") or {}
        bindings = manifest.get("bindings") or []
        self.assertEqual(manifest.get("binding_revision"), "official_templates_202607_v1")
        self.assertEqual(len(bindings), 23)
        self.assertEqual(len({item["page_id"] for item in bindings}), 23)
        self.assertEqual(len({item["title"] for item in bindings}), 23)
        for binding in bindings:
            profile = profiles[binding["profile"]]
            self.assertEqual(profile["page_context"]["version"], "page_context_v1")
            template = profile["agent_reply_template"]
            self.assertEqual(template["version"], "reply_template_v2")
            if template["reply_scope"] == "hybrid":
                self.assertEqual(
                    template["hybrid_composition"]["version"],
                    "hybrid_composition_v1",
                )


if __name__ == "__main__":
    unittest.main()
