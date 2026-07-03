(function () {
  function truthyParam(value) {
    return ["1", "true", "yes", "on", "show", "visible"].includes(String(value || "").toLowerCase());
  }

  function falsyParam(value) {
    return ["0", "false", "no", "off", "hide", "hidden"].includes(String(value || "").toLowerCase());
  }

  function shouldShowLiveCard(search) {
    var params = new URLSearchParams(search || window.location.search);
    if (truthyParam(params.get("hideEssence")) || truthyParam(params.get("hideCover"))) return false;
    var value = params.get("cover") || params.get("essence") || params.get("cardOnly");
    if (value != null) {
      if (truthyParam(value)) return true;
      if (falsyParam(value)) return false;
    }
    return false;
  }

  function applyVisibility(options) {
    var cfg = options || {};
    var show = cfg.show != null ? !!cfg.show : shouldShowLiveCard(cfg.search);
    var section = document.getElementById(cfg.sectionId || "essenceSection");
    document.documentElement.classList.toggle(cfg.modeClass || "essence-cover-mode", show);
    if (section) section.hidden = !show;
    return show;
  }

  function formatDate(value) {
    if (!value) return "";
    if (/^\d{4}-\d{2}-\d{2}$/.test(String(value))) return String(value);
    var date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value).slice(0, 10);
    return date.toISOString().slice(0, 10);
  }

  function text(value, fallback) {
    var raw = value == null ? "" : String(value).trim();
    return raw || fallback || "";
  }

  function setText(root, selector, value, fallback) {
    var el = root && root.querySelector(selector);
    if (el) el.textContent = text(value, fallback);
  }

  function setDate(root, value, fallback) {
    var el = root && root.querySelector("[data-qb-live-card-date]");
    var date = formatDate(value) || fallback || "";
    if (el) {
      el.textContent = date;
      if (el.tagName && el.tagName.toLowerCase() === "time") el.setAttribute("datetime", date);
    }
  }

  function setMetric(root, index, label, value) {
    if (!root) return;
    var item = root.querySelector('[data-qb-live-card-metric="' + index + '"]');
    if (!item) return;
    var valueEl = item.querySelector("b");
    var labelEl = item.querySelector("span");
    if (valueEl) valueEl.textContent = text(value, "—");
    if (labelEl) labelEl.textContent = text(label, "指标");
  }

  window.QBLiveCard = {
    truthyParam: truthyParam,
    falsyParam: falsyParam,
    shouldShow: shouldShowLiveCard,
    applyVisibility: applyVisibility,
    formatDate: formatDate,
    text: text,
    setText: setText,
    setDate: setDate,
    setMetric: setMetric
  };
})();
