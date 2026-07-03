#!/usr/bin/env python3
"""Shared helpers for QuantBuddy live cover cards."""

import datetime
from html import escape as html_escape
import json
import re


LIVE_CARD_MARKER = "data-qb-live-card"
CSS_TOKEN = "<!-- QB_LIVE_CARD_CSS -->"
JS_TOKEN = "<!-- QB_LIVE_CARD_JS -->"


def has_live_card(html):
    return bool(re.search(r"\bdata-qb-live-card(?:\s|=|>)", html or "", flags=re.I))


def _clean_text(value, fallback=""):
    text = "" if value is None else str(value).strip()
    return text or fallback


def _theme(value):
    value = _clean_text(value, "orange").lower()
    return value if value in ("red", "blue", "green", "orange") else "orange"


def _date(value=None):
    text = _clean_text(value)
    if re.match(r"^\d{4}-\d{2}-\d{2}$", text):
        return text
    return datetime.date.today().isoformat()


def _metric_items(config):
    metrics = config.get("metrics") if isinstance(config.get("metrics"), list) else []
    out = []
    for i, item in enumerate(metrics[:3]):
        if isinstance(item, dict):
            out.append({
                "label": _clean_text(item.get("label"), f"指标{i + 1}"),
                "value": _clean_text(item.get("value"), "待更新"),
                "output": _clean_text(item.get("output")),
                "field": _clean_text(item.get("field") or item.get("value_field")),
                "unit": _clean_text(item.get("unit")),
            })
        else:
            out.append({"label": f"指标{i + 1}", "value": _clean_text(item, "待更新")})
    if not out:
        out = [
            {"label": "核心指标", "value": "待更新"},
            {"label": "变化", "value": "待更新"},
            {"label": "水位", "value": "待更新"},
        ]
    return out


def normalize_config(config=None, *, fallback_title="", fallback_description=""):
    if config is True:
        config = {}
    if not isinstance(config, dict):
        config = {}
    metrics = _metric_items(config)
    title = _clean_text(config.get("title"), fallback_title or "页面核心结论一眼看懂")
    description = _clean_text(config.get("description"), fallback_description or "核心指标实时更新，打开页面即按最新数据刷新。")
    primary = config.get("primary") if isinstance(config.get("primary"), dict) else {}
    tags = config.get("tags") if isinstance(config.get("tags"), list) else []
    tags = [_clean_text(t) for t in tags if _clean_text(t)][:3]
    if not tags:
        tags = ["实时取数", "重点摘要"]
    return {
        "title": title,
        "description": description,
        "theme": _theme(config.get("theme")),
        "date": _date(config.get("date")),
        "date_output": _clean_text(config.get("date_output")),
        "metrics": metrics,
        "primary": {
            "label": _clean_text(primary.get("label"), metrics[0]["label"]),
            "value": _clean_text(primary.get("value"), metrics[0]["value"]),
            "output": _clean_text(primary.get("output"), metrics[0].get("output", "")),
            "field": _clean_text(primary.get("field") or primary.get("value_field"), metrics[0].get("field", "")),
            "unit": _clean_text(primary.get("unit"), metrics[0].get("unit", "")),
        },
        "tags": tags,
    }


def card_html(config=None, *, fallback_title="", fallback_description=""):
    cfg = normalize_config(config, fallback_title=fallback_title, fallback_description=fallback_description)
    metrics = []
    for i, item in enumerate(cfg["metrics"]):
        metrics.append(
            '<div class="live-card-metric" data-qb-live-card-metric="{i}"'
            '{output}{field}{unit}><b>{value}</b><span>{label}</span></div>'.format(
                i=i,
                output=f' data-qb-live-card-output="{html_escape(item.get("output", ""), quote=True)}"' if item.get("output") else "",
                field=f' data-qb-live-card-field="{html_escape(item.get("field", ""), quote=True)}"' if item.get("field") else "",
                unit=f' data-qb-live-card-unit="{html_escape(item.get("unit", ""), quote=True)}"' if item.get("unit") else "",
                value=html_escape(item["value"]),
                label=html_escape(item["label"]),
            )
        )
    tags = "\n".join(f'          <span class="live-card-tag">{html_escape(tag)}</span>' for tag in cfg["tags"])
    primary = cfg["primary"]
    return """<section class="essence-section" id="essenceSection" aria-label="宽宝活卡" hidden>
      <article class="essence-card" id="essenceCard" data-qb-live-card data-theme="{theme}">
        <div class="live-card-meta">
          <span data-qb-live-card-brand></span>
          <time data-qb-live-card-date datetime="{date}">{date}</time>
        </div>
        <h1 data-qb-live-card-title>{title}</h1>
        <p data-qb-live-card-description>{description}</p>
        <section class="live-card-core-grid" data-qb-live-card-core>
          <div class="live-card-primary" data-qb-live-card-primary-output="{primary_output}" data-qb-live-card-primary-field="{primary_field}" data-qb-live-card-primary-unit="{primary_unit}">
            <div class="live-card-primary-value" data-qb-live-card-primary>{primary_value}</div>
            <div class="live-card-primary-label">{primary_label}</div>
          </div>
          <div class="live-card-panel">
            <div class="live-card-metric-grid">
              {metrics}
            </div>
          </div>
        </section>
        <div class="live-card-tags">
{tags}
        </div>
      </article>
    </section>""".format(
        theme=html_escape(cfg["theme"], quote=True),
        date=html_escape(cfg["date"], quote=True),
        title=html_escape(cfg["title"]),
        description=html_escape(cfg["description"]),
        primary_output=html_escape(primary.get("output", ""), quote=True),
        primary_field=html_escape(primary.get("field", ""), quote=True),
        primary_unit=html_escape(primary.get("unit", ""), quote=True),
        primary_value=html_escape(primary.get("value", "待更新")),
        primary_label=html_escape(primary.get("label", "核心指标")),
        metrics="\n              ".join(metrics),
        tags=tags,
    )


def binding_script(config=None, *, fallback_title="", fallback_description=""):
    cfg = normalize_config(config, fallback_title=fallback_title, fallback_description=fallback_description)
    data = json.dumps(cfg, ensure_ascii=False).replace("</", "<\\/")
    return """<script id="qb-live-card-binding">
(function(){
  var cfg = __CFG__;
  function isObj(v){ return v && typeof v === "object" && !Array.isArray(v); }
  function unwrap(data){
    if (data && data.data != null && (data.read_mode || data.data_id || data.error == null)) data = data.data;
    if (isObj(data)) {
      var keys = ["last_value", "last_day_stats", "last_valid_per_asset", "range_data"];
      for (var i = 0; i < keys.length; i++) if (data[keys[i]] != null) return unwrap(data[keys[i]]);
    }
    return data;
  }
  function fmt(v, unit){
    if (v == null || v === "") return "待更新";
    if (typeof v === "number" && isFinite(v)) {
      var abs = Math.abs(v);
      v = abs >= 100 ? v.toFixed(0) : abs >= 10 ? v.toFixed(1) : v.toFixed(2);
    }
    return String(v) + (unit ? " " + unit : "");
  }
  function firstUseful(data, field){
    data = unwrap(data);
    if (Array.isArray(data)) {
      for (var i = data.length - 1; i >= 0; i--) {
        var item = data[i];
        if (Array.isArray(item)) {
          for (var j = item.length - 1; j >= 0; j--) if (item[j] != null && item[j] !== "") return item[j];
        } else if (isObj(item)) {
          if (field && item[field] != null) return item[field];
          var vals = Object.keys(item).map(function(k){ return item[k]; }).filter(function(v){ return v != null && v !== ""; });
          if (vals.length) return vals[vals.length - 1];
        } else if (item != null && item !== "") {
          return item;
        }
      }
    }
    if (isObj(data)) {
      if (field && data[field] != null) return data[field];
      if (Array.isArray(data.values)) {
        for (var k = data.values.length - 1; k >= 0; k--) if (data.values[k] != null) return data.values[k];
      }
      var dateKeys = ["trade_date", "date", "asof", "as_of"];
      for (var d = 0; d < dateKeys.length; d++) if (data[dateKeys[d]] != null && field === dateKeys[d]) return data[dateKeys[d]];
      var keys = Object.keys(data).filter(function(k){ return data[k] != null && data[k] !== ""; });
      if (keys.length) return data[keys[keys.length - 1]];
    }
    return data;
  }
  function outputValue(outputs, spec){
    if (!spec || !spec.output || !outputs) return null;
    return firstUseful(outputs[spec.output], spec.field);
  }
  function findDate(outputs){
    var spec = { output: cfg.date_output, field: "date" };
    var value = outputValue(outputs, spec);
    if (value) return value;
    if (!outputs) return cfg.date;
    var keys = Object.keys(outputs);
    for (var i = 0; i < keys.length; i++) {
      var out = unwrap(outputs[keys[i]]);
      var date = firstUseful(out, "trade_date") || firstUseful(out, "date");
      if (date) return date;
    }
    return cfg.date;
  }
  function hydrate(outputs){
    outputs = outputs || window.LAST_OUTPUTS || window.__QB_COVER_OUTPUTS__ || {};
    if (!window.QBLiveCard) return;
    QBLiveCard.applyVisibility();
    QBLiveCard.setDate(document, findDate(outputs), cfg.date);
    QBLiveCard.setText(document, "[data-qb-live-card-title]", cfg.title);
    QBLiveCard.setText(document, "[data-qb-live-card-description]", cfg.description);
    var primary = document.querySelector("[data-qb-live-card-primary]");
    if (primary) {
      var pv = outputValue(outputs, cfg.primary);
      primary.textContent = fmt(pv != null ? pv : cfg.primary.value, cfg.primary.unit);
    }
    (cfg.metrics || []).forEach(function(metric, index){
      var value = outputValue(outputs, metric);
      QBLiveCard.setMetric(document, index, metric.label, fmt(value != null ? value : metric.value, metric.unit));
    });
  }
  window.QBLiveCardHydrate = hydrate;
  document.addEventListener("DOMContentLoaded", function(){ hydrate(); });
  window.addEventListener("qb:outputs", function(ev){ hydrate(ev.detail && ev.detail.outputs || ev.detail || {}); });
})();
</script>""".replace("__CFG__", data)


def _insert_before(pattern, fragment, html):
    match = re.search(pattern, html, flags=re.I)
    if not match:
        return html, 0
    return html[:match.start()] + fragment + "\n" + html[match.start():], 1


def _inject_after_main(html, fragment):
    match = re.search(r"<main\b[^>]*>", html or "", flags=re.I)
    if match:
        return html[:match.end()] + "\n    " + fragment + "\n" + html[match.end():], "inserted_after_main"
    match = re.search(r"<body\b[^>]*>", html or "", flags=re.I)
    if match:
        return html[:match.end()] + "\n  <main>\n    " + fragment + "\n  </main>\n" + html[match.end():], "inserted_after_body"
    return fragment + "\n" + html, "prepended"


def ensure_assets(html):
    actions = []
    if "live-card.css" not in html and CSS_TOKEN not in html and ".essence-card[data-qb-live-card]" not in html:
        html, count = _insert_before(r"</head>", CSS_TOKEN, html)
        if count:
            actions.append("inserted_live_card_css")
    if "live-card.js" not in html and JS_TOKEN not in html and "window.QBLiveCard" not in html:
        html, count = _insert_before(r"</body>", JS_TOKEN, html)
        if count:
            actions.append("inserted_live_card_js")
    return html, actions


def inject(html, config=None, *, fallback_title="", fallback_description=""):
    actions = []
    if not has_live_card(html):
        fragment = card_html(config, fallback_title=fallback_title, fallback_description=fallback_description)
        html, action = _inject_after_main(html, fragment)
        actions.append(action)
    html, asset_actions = ensure_assets(html)
    actions.extend(asset_actions)
    if "qb-live-card-binding" not in html:
        script = binding_script(config, fallback_title=fallback_title, fallback_description=fallback_description)
        html, count = _insert_before(r"</body>", script, html)
        if count:
            actions.append("inserted_live_card_binding")
    return html, actions


def dashboard_config(spec, panels):
    raw = spec.get("live_card")
    if not raw:
        return None
    if raw is True:
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    metrics = raw.get("metrics") if isinstance(raw.get("metrics"), list) else []
    if not metrics:
        ordered = [p for p in panels if isinstance(p, dict) and (p.get("type") or "").lower() == "number"]
        ordered += [p for p in panels if isinstance(p, dict) and p not in ordered]
        for panel in ordered[:3]:
            metrics.append({
                "label": panel.get("title") or panel.get("output") or "指标",
                "output": panel.get("output") or "",
                "field": panel.get("value_field") or "",
                "unit": panel.get("unit") or "",
                "value": "待更新",
            })
    cfg = dict(raw)
    cfg.setdefault("title", spec.get("live_card_title") or spec.get("title"))
    cfg.setdefault("description", spec.get("live_card_description") or spec.get("subtitle") or spec.get("description"))
    cfg.setdefault("metrics", metrics)
    cfg.setdefault("tags", ["实时取数", "重点摘要"])
    return normalize_config(cfg, fallback_title=spec.get("title", ""), fallback_description=spec.get("subtitle", ""))
