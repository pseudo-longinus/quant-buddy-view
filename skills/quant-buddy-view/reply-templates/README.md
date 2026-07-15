# Agent Reply Templates

`reply-templates/` stores Agent reply skeletons for Quant Buddy static pages. These are not page HTML templates. Page templates still come from the online `templates` / `template` static-page APIs.

Use these files when a static page metadata object contains:

```json
{
  "agent_reply_template": {
    "version": "reply_template_v2",
    "template_ref": "single_stock_valuation_quality_v1",
    "reply_scope": "full_answer",
    "output_format": "markdown"
  }
}
```

## Contract

- `template_ref` is the stable id of a Markdown file in this directory, without `.md`.
- `reply_scope` is either `full_answer` or `hybrid`.
- `full_answer` means the Agent should use the referenced skeleton as the whole answer shape.
- `hybrid` means the Agent should combine the referenced skeleton with the current page HTML, runtime data, and user context.
- `output_format` is currently `markdown`.
- `reply_template_v1` remains compatible. `reply_template_v2` hybrid replies require `hybrid_composition` and a top-level `page_context`.
- `page_context` is a sibling metadata object that describes the current page. Never copy a source template's context into a generated user page; regenerate it from the final page.
- `generic_live_page_delivery_v1` is the required fallback for new pages that do not match a professional skeleton.
- Keep template files focused on the final answer shape: section order, table headers, required disclaimers, and output constraints. Do not copy tool-routing or deprecated skill instructions into these files.

`index.json` is the registry for stable ids and source provenance. Each template file carries the same id in frontmatter so it can be read standalone.
