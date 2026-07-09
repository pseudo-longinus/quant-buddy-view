/* ============================================================
   观照量化 · 取数内核 (data-kernel)  —— 所有手搓页面共用的一份
   ------------------------------------------------------------
   只做一件事：把“去服务器拿数据”做对，让页面只管“长什么样”。
     连服务器 → 读 SSE 流 → 组装 outputs → 解包清洗 → 出错就喊
   口径与 build_dashboard 的渲染器一致，别再每页各抄各的、各踩各的坑。

   用法（把本段整体内联进页面 <script>，再调）：
     const out = await QB.query({ endpoint, package_id, signature });
     const px  = QB.series(out, 'SC_px', { dropZero:true }); // 价格：扔掉 0/空缺口
     const chg = QB.lastValue(out, 'IDXRET');                // 单值
     const top = QB.topValues(out, 'GAIN');                  // 榜单
     const d   = QB.fmtDate(QB.lastDate(out, 'IDXRET'));     // 日期 → 'YYYY-MM-DD'

     // 数据授权（免 key，凭 grant_id + signature；普通 JSON，不重算）：
     // 返回值同样是 out 直查表，key 用 grant_id，上面这些取值器直接复用。
     const gOut = await QB.queryGrant({ endpoint, grant_id, signature });
     const last = QB.lastValue(gOut, grant_id);

   设计取舍：
     · endpoint 由调用方传入、不写死 —— 测试环境填测试地址、正式环境填正式地址，保持灵活。
     · 清洗只统一“数据层”：缺口(null/NaN)永远扔；价格的假 0 按需扔；涨跌幅的 0 是合法平盘值不扔。
     · 出错（HTTP 失败 / 服务端 error 事件 / 三件套没填）一律 throw，页面 catch 后塞进自己的错误槽——
       绝不闷头返回空数据让页面画出一张“看着成功其实是错的”假图。
   ============================================================ */
const QB = (function () {
  'use strict';

  // 构建时由 compile_bespoke_page.py 注入本次生成所用的 quant-buddy-view 版本；
  // 未经编译（仍是占位符）时不发版本头，避免上报无意义的占位串。
  const SKILL_VERSION = '__QBV_SKILL_VERSION__';
  const SKILL_NAME = 'quant-buddy-view';
  const _hasSkillVer = SKILL_VERSION && SKILL_VERSION.indexOf('__QBV_') !== 0;

  // —— 有效数值：非 null、是有限数（NaN / Infinity 都不算）——
  const num = v => (typeof v === 'number' && isFinite(v)) ? v : null;

  function apiUrl(endpoint, path) {
    endpoint = String(endpoint || '').replace(/\/+$/, '');
    path = '/' + String(path || '').replace(/^\/+/, '');
    if (endpoint.endsWith('/skill') && path.startsWith('/skill/')) {
      path = path.slice('/skill'.length);
    }
    return endpoint + path;
  }

  function hasUsefulData(data) {
    if (data == null) return false;
    if (Array.isArray(data)) return data.length > 0;
    if (typeof data !== 'object') return data !== '';
    for (const k of ['range_data', 'last_value', 'last_day_stats', 'last_valid_per_asset']) {
      if (data[k] != null) return hasUsefulData(data[k]);
    }
    if (Array.isArray(data.values)) return data.values.some(v => Array.isArray(v) ? v.some(x => x != null) : v != null);
    if (Array.isArray(data.top_values) || Array.isArray(data.items) || Array.isArray(data.records)) {
      return (data.top_values || data.items || data.records).length > 0;
    }
    if ('value' in data) return data.value != null;
    return Object.keys(data).length > 0;
  }

  /* 连服务器 + 读 SSE 流，组装成 outputs 直查表（out['变量名'] 即该产出）。
     元信息（stale / recomputed）挂在 out.__done 上，需要时取。 */
  async function query(cfg, opts) {
    const { endpoint, package_id, signature } = cfg || {};
    if (!endpoint || !package_id || !signature)
      throw new Error('取数内核：endpoint / package_id / signature 三者必填');

    // 温和提醒（不强改）：https 页面连 http 地址，发布到线上会被浏览器拦（mixed-content）
    if (typeof location !== 'undefined' &&
        location.protocol === 'https:' && /^http:\/\//i.test(endpoint)) {
      console.warn('[取数内核] 页面是 https，endpoint 却是 http：' + endpoint +
        '\n  本地双击打开能用，但发布到 https 网站会被浏览器拦截（mixed-content）。' +
        '\n  发布前请把 endpoint 换成 https 地址。');
    }

    const status = opts && opts.status;
    if (status) {
      status.package_id = package_id;
      status.loading = true;
      status.ok = false;
      status.error = null;
      status.progress = [];
      status.startedAt = Date.now();
    }

    const resp = await fetch(apiUrl(endpoint, '/skill/queryFormulaPackage'), {
      method: 'POST',
      headers: Object.assign(
        { 'Content-Type': 'application/json' },
        _hasSkillVer ? { 'x-skill-version': SKILL_VERSION, 'x-skill-name': SKILL_NAME } : {}
      ),
      body: JSON.stringify({
        package_id,
        signature,
        outputs: Array.isArray(cfg.outputs) ? cfg.outputs : (Array.isArray(opts && opts.outputs) ? opts.outputs : undefined),
      }),
    });
    if (!resp.ok || !resp.body) throw new Error('HTTP ' + resp.status);

    const reader = resp.body.getReader(), dec = new TextDecoder();
    const out = {}; let buf = '';
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      const blocks = buf.split('\n\n'); buf = blocks.pop();
      for (const b of blocks) {
        const ev = (b.match(/event:\s*(.*)/) || [])[1];
        const m  = b.match(/data:\s*([\s\S]*)/);
        if (!ev || !m) continue;
        let dt; try { dt = JSON.parse(m[1]); } catch (e) { continue; }
        if (ev === 'result') {
          out[dt.output] = dt;
          if (status) status.lastOutput = dt.output;
        }
        else if (ev === 'progress') {
          out.__progress = out.__progress || [];
          out.__progress.push(dt);
          if (status) status.progress.push(dt);
        }
        else if (ev === 'error') {
          const msg = (dt.code || 'ERROR') + ': ' + (dt.message || '');
          if (status) status.error = msg;
          throw new Error(msg);
        }
        else if (ev === 'done')  out.__done = dt;
      }
    }
    const failed = Object.keys(out).filter(k => k.indexOf('__') !== 0 && out[k] && out[k].error);
    out.__status = {
      package_id,
      ok: failed.length === 0 && !(out.__done && out.__done.code && out.__done.code !== 0),
      error: failed.length ? failed.map(k => k + ': ' + out[k].error).join('; ') : null,
      failed,
      done: out.__done || null,
      progress: out.__progress || [],
    };
    if (status) Object.assign(status, out.__status, { loading: false });
    return out;
  }

  /* 数据授权取数：免 key，凭 grant_id + signature；普通 JSON POST（不重算，永远反映当下数据）。
     成功/失败都走同一份 throw-on-error 约定；成功时返回的 out 直查表与 query() 同形状，
     key 用 grant_id，series/lastValue/topValues/perAsset 等取值器直接复用。 */
  async function queryGrant(cfg) {
    const { endpoint, grant_id, signature } = cfg || {};
    if (!endpoint || !grant_id || !signature)
      throw new Error('取数内核：endpoint / grant_id / signature 三者必填');

    if (typeof location !== 'undefined' &&
        location.protocol === 'https:' && /^http:\/\//i.test(endpoint)) {
      console.warn('[取数内核] 页面是 https，endpoint 却是 http：' + endpoint +
        '\n  本地双击打开能用，但发布到 https 网站会被浏览器拦截（mixed-content）。' +
        '\n  发布前请把 endpoint 换成 https 地址。');
    }

    const resp = await fetch(apiUrl(endpoint, '/skill/queryDataGrant'), {
      method: 'POST',
      headers: Object.assign(
        { 'Content-Type': 'application/json' },
        _hasSkillVer ? { 'x-skill-version': SKILL_VERSION, 'x-skill-name': SKILL_NAME } : {}
      ),
      body: JSON.stringify({ grant_id, signature }),
    });
    let body = null;
    try { body = await resp.json(); } catch (e) { /* 非 JSON 响应，body 留 null，下面统一按失败处理 */ }
    if (!resp.ok || !body || body.code !== 0) {
      const err = (body && body.error) || {};
      throw new Error((err.code || ('HTTP ' + resp.status)) + (err.message ? (': ' + err.message) : ''));
    }

    const out = {};
    out[grant_id] = { output: grant_id, data: body.data, error: null, kind: body.kind };
    out.__status = { grant_id, kind: body.kind, ok: true, error: null };
    return out;
  }

  async function queryMany(packagesByRole, opts) {
    const entries = Object.entries(packagesByRole || {}).filter(([, cfg]) => cfg);
    const outputsByRole = {};
    const statusByRole = {};
    const onStatus = opts && typeof opts.onStatus === 'function' ? opts.onStatus : null;
    const slowMs = (opts && opts.slowMs) || 9000;

    await Promise.all(entries.map(async ([role, cfg]) => {
      const status = statusByRole[role] = { role, loading: true, ok: false, progress: [] };
      let slowTimer = null;
      if (onStatus) {
        onStatus({ role, phase: 'start', status });
        slowTimer = setTimeout(() => {
          if (status.loading) onStatus({ role, phase: 'slow', message: '取数仍在进行，可能正在重算公式包', status });
        }, slowMs);
      }
      try {
        const out = await query(cfg, { status });
        outputsByRole[role] = out;
        Object.assign(status, out.__status || {}, { role, loading: false });
        if (onStatus) onStatus({ role, phase: 'done', status, outputs: out });
      } catch (e) {
        status.loading = false;
        status.ok = false;
        status.error = e && e.message ? e.message : String(e);
        outputsByRole[role] = { __status: status };
        if (onStatus) onStatus({ role, phase: 'error', status });
      } finally {
        if (slowTimer) clearTimeout(slowTimer);
      }
    }));

    return {
      outputsByRole,
      statusByRole,
      outputs: outputsByRole,
      status: statusByRole,
    };
  }

  // —— 取某产出的原始 data 包 ——
  const _data = (out, key) => (out && out[key] && out[key].data) || null;

  function outputStatus(out, key) {
    if (!key) {
      const st = out && out.__status;
      return st || { ok: !!out, error: out ? null : 'empty output', hasData: !!out };
    }
    const item = out && out[key];
    if (!item) return { ok: false, output: key, error: 'missing output', hasData: false };
    const hasData = hasUsefulData(item.data);
    return {
      ok: !item.error && hasData,
      output: key,
      read_mode: item.read_mode,
      data_id: item.data_id,
      error: item.error || (hasData ? null : 'empty data'),
      hasData,
    };
  }

  /* 单值：last_value.{date,value}。value 必须是有效数值，否则返回 null（不吐 NaN/占位 0）。 */
  function lastValue(out, key) {
    const d = _data(out, key);
    return d && d.last_value ? num(d.last_value.value) : null;
  }
  function lastDate(out, key) {
    const d = _data(out, key);
    return d && d.last_value && d.last_value.date != null ? d.last_value.date : null;
  }

  /* 序列：range_data.{dates,values} → [{ d:日期, v:数值 }]
       · 永远扔掉 null / NaN（缺口）
       · dropZero=true 时把 0 也当缺口扔 —— 价格 / 成交额这类“不可能为 0”的数据要开；
         涨跌幅 / 收益率这类 0 是合法平盘值的，别开。 */
  function series(out, key, opts) {
    const dropZero = !!(opts && opts.dropZero);
    const d = _data(out, key);
    const r = d && d.range_data;
    if (!r || !r.values) return [];
    const pts = [];
    for (let i = 0; i < r.values.length; i++) {
      const v = num(r.values[i]);
      if (v === null) continue;           // 缺口
      if (dropZero && v === 0) continue;   // 价格的假 0
      pts.push({ d: r.dates ? r.dates[i] : i, v });
    }
    return pts;
  }
  // 只要数值数组（画 sparkline 常用）：QB.values(out,'SC_px',{dropZero:true})
  function values(out, key, opts) { return series(out, key, opts).map(p => p.v); }

  /* 榜单：last_day_stats.top_values[]（[{ asset, name, value }, ...]）。 */
  function topValues(out, key) {
    const d = _data(out, key);
    return (d && d.last_day_stats && d.last_day_stats.top_values) || [];
  }
  function statDate(out, key) {
    const d = _data(out, key);
    return (d && d.last_day_stats && d.last_day_stats.date) || null;
  }

  function perAsset(out, key) {
    const d = _data(out, key);
    const p = d && d.last_valid_per_asset;
    if (!p) return [];
    if (Array.isArray(p)) return p;
    for (const k of ['items', 'records', 'rows', 'values']) {
      if (Array.isArray(p[k])) return p[k];
    }
    if (typeof p === 'object') {
      return Object.keys(p).map(asset => {
        const v = p[asset];
        return (v && typeof v === 'object') ? Object.assign({ asset }, v) : { asset, value: v };
      });
    }
    return [];
  }

  function perAssetMap(out, key) {
    const m = {};
    perAsset(out, key).forEach(row => {
      const asset = row && (row.asset || row.ticker || row.code || row.symbol || row.name);
      if (asset) m[asset] = row;
    });
    return m;
  }

  /* 日期：整数/字符串 YYYYMMDD → 'YYYY-MM-DD'（分隔符可换）。非 8 位原样返回，空值给占位。 */
  function fmtDate(d, sep) {
    if (d == null || d === '') return '—';
    const s = String(d), q = sep || '-';
    if (!/^\d{8}$/.test(s)) return s;
    return s.slice(0, 4) + q + s.slice(4, 6) + q + s.slice(6, 8);
  }

  return {
    query, queryMany, queryGrant, apiUrl,
    num, outputStatus,
    lastValue, lastDate, series, values, topValues, statDate,
    perAsset, perAssetMap,
    fmtDate
  };
})();
