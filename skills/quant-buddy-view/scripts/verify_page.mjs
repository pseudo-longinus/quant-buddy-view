#!/usr/bin/env node
/*
 * Verify a generated QuantBuddy page before upload/update.
 *
 * Usage:
 *   node scripts/verify_page.mjs output/pages/demo.html
 *   node scripts/verify_page.mjs https://pages.quantbuddy.cn/...
 *   node scripts/verify_page.mjs output/pages/demo.html --manifest output/pages/demo.manifest.json
 *   node scripts/verify_page.mjs output/pages/demo.html --require-browser
 */

import fs from 'node:fs';
import crypto from 'node:crypto';
import net from 'node:net';
import os from 'node:os';
import path from 'node:path';
import { spawn, spawnSync } from 'node:child_process';
import { pathToFileURL } from 'node:url';

const args = process.argv.slice(2);
const requireBrowser = args.includes('--require-browser');
const manifestIdx = args.indexOf('--manifest');
const manifestPath = manifestIdx >= 0 ? args[manifestIdx + 1] : '';
const valueFlags = new Set(['--manifest']);
const positionals = [];
for (let i = 0; i < args.length; i += 1) {
  const arg = args[i];
  if (valueFlags.has(arg)) {
    i += 1;
    continue;
  }
  if (arg.startsWith('--')) continue;
  positionals.push(arg);
}
const target = positionals[0];

const VIEWPORTS = [
  { name: 'desktop', width: 1440, height: 1000, mobile: false },
  { name: 'mobile390', width: 390, height: 844, mobile: true },
  { name: 'mobile320', width: 320, height: 720, mobile: true },
];
const CORE_ERROR_RE = /queryFormulaPackage|CORS|mixed-content|Failed to fetch|ReferenceError|TypeError/i;

function emit(obj) {
  process.stdout.write(JSON.stringify(obj, null, 2) + '\n');
}

function fail(message) {
  emit({ code: 1, message });
  process.exit(1);
}

if (!target) {
  fail('用法: node scripts/verify_page.mjs <html_file_or_url> [--manifest manifest.json] [--require-browser]');
}

function delay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function isUrl(v) {
  return /^https?:\/\//i.test(v);
}

function targetUrl(v) {
  if (isUrl(v)) return v;
  const abs = path.isAbsolute(v) ? v : path.resolve(process.cwd(), v);
  return pathToFileURL(abs).href;
}

async function readHtml(v) {
  if (isUrl(v)) {
    const resp = await fetch(v);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return await resp.text();
  }
  const abs = path.isAbsolute(v) ? v : path.resolve(process.cwd(), v);
  return fs.readFileSync(abs, 'utf8');
}

function staticChecks(html) {
  const problems = [];
  const placeholders = ['QB_SHARED_', 'replace_with_signature', 'pkg_replace', '__PLACEHOLDER__'];
  for (const token of placeholders) {
    if (html.includes(token)) problems.push(`占位符残留: ${token}`);
  }
  if (!/<h1\b[^>]*>[\s\S]*?<\/h1>/i.test(html)) problems.push('缺少 <h1>');
  if (/<script\s+src=["'][^"']*(assets\/data-kernel|assets\/qr-mini|templates\/_shared)/i.test(html)) {
    problems.push('仍引用本地运行时脚本，未内联公共资源');
  }
  const hasPackage = /(?:["']?(?:package_id|packageId)["']?)\s*:\s*["'][^"']+["']/.test(html);
  return { ok: problems.length === 0, problems, hasPackage };
}

async function loadPlaywright() {
  try {
    return await import('playwright');
  } catch {
    return null;
  }
}

async function launchPlaywrightBrowser(pw) {
  const attempts = [
    { channel: 'chrome', headless: true },
    { channel: 'msedge', headless: true },
    { headless: true },
  ];
  const errors = [];
  for (const options of attempts) {
    try {
      return await pw.chromium.launch(options);
    } catch (err) {
      errors.push(err && err.message ? err.message : String(err));
    }
  }
  throw new Error(errors.join(' | '));
}

async function playwrightBrowserChecks(pw, url) {
  const browser = await launchPlaywrightBrowser(pw);
  const results = [];
  const consoleErrors = [];
  try {
    for (const viewport of VIEWPORTS) {
      const page = await browser.newPage({ viewport: { width: viewport.width, height: viewport.height } });
      page.on('console', msg => {
        if (['error', 'warning'].includes(msg.type())) {
          const text = msg.text();
          if (CORE_ERROR_RE.test(text)) {
            consoleErrors.push({ viewport: viewport.name, type: msg.type(), text });
          }
        }
      });
      await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });
      await page.waitForTimeout(1200);
      const metrics = await page.evaluate(pageMetricsExpression);
      results.push(viewportResult(viewport, metrics));
      await page.close();
    }
  } finally {
    await browser.close();
  }
  return { checked: true, engine: 'playwright', viewports: results, consoleErrors };
}

function pageMetricsExpression() {
  const doc = document.documentElement;
  const bodyText = document.body ? document.body.innerText : '';
  const h1 = document.querySelector('h1');
  const visibleText = bodyText.replace(/\s+/g, '');
  const placeholderHits = ['QB_SHARED_', 'replace_with_signature', 'pkg_replace', '__PLACEHOLDER__']
    .filter(token => document.documentElement.innerHTML.includes(token));
  const placeholderOnly = visibleText.length > 0 && /^[—\-\s.0暂无数据等待取数加载中]+$/.test(visibleText);
  return {
    scrollWidth: doc.scrollWidth,
    clientWidth: doc.clientWidth,
    hasH1: !!(h1 && h1.textContent.trim()),
    placeholderHits,
    placeholderOnly,
  };
}

function viewportResult(viewport, metrics) {
  return {
    viewport: viewport.name,
    width: viewport.width,
    horizontalOverflow: metrics.scrollWidth > metrics.clientWidth + 2,
    hasH1: metrics.hasH1,
    placeholderHits: metrics.placeholderHits,
    placeholderOnly: metrics.placeholderOnly,
  };
}

function browserCandidates() {
  const env = [process.env.CHROME_PATH, process.env.EDGE_PATH, process.env.BROWSER].filter(Boolean);
  const win = [
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
    'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  ];
  const unix = ['/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser', '/usr/bin/microsoft-edge'];
  return [...env, ...(process.platform === 'win32' ? win : unix)];
}

function findBrowser() {
  for (const candidate of browserCandidates()) {
    if (candidate && fs.existsSync(candidate)) return candidate;
  }
  const names = process.platform === 'win32'
    ? ['msedge.exe', 'chrome.exe', 'chromium.exe', 'brave.exe']
    : ['google-chrome', 'chromium', 'chromium-browser', 'microsoft-edge', 'brave'];
  const lookup = process.platform === 'win32' ? 'where.exe' : 'which';
  for (const name of names) {
    const found = spawnSync(lookup, [name], { encoding: 'utf8' });
    if (found.status === 0 && found.stdout.trim()) {
      const first = found.stdout.trim().split(/\r?\n/)[0];
      if (first) return first;
    }
  }
  return '';
}

function waitForDebugEndpoint(proc) {
  return new Promise((resolve, reject) => {
    let output = '';
    const timer = setTimeout(() => {
      reject(new Error(`browser did not expose DevTools endpoint: ${output.slice(-500)}`));
    }, 10000);
    const onData = chunk => {
      output += chunk.toString();
      const match = output.match(/DevTools listening on (ws:\/\/[^\s]+)/);
      if (match) {
        clearTimeout(timer);
        resolve(match[1]);
      }
    };
    proc.stderr.on('data', onData);
    proc.stdout.on('data', onData);
    proc.once('exit', code => {
      clearTimeout(timer);
      reject(new Error(`browser exited before DevTools endpoint was ready: ${code}; ${output.slice(-500)}`));
    });
  });
}

async function fetchJson(url) {
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`HTTP ${resp.status} for ${url}`);
  return await resp.json();
}

async function pageWebSocketUrl(debugWs) {
  const port = (debugWs.match(/127\.0\.0\.1:(\d+)/) || debugWs.match(/localhost:(\d+)/) || [])[1];
  if (!port) throw new Error(`cannot parse DevTools port from ${debugWs}`);
  const base = `http://127.0.0.1:${port}`;
  for (let i = 0; i < 20; i += 1) {
    const targets = await fetchJson(`${base}/json/list`).catch(() => []);
    const page = targets.find(t => t.type === 'page' && t.webSocketDebuggerUrl);
    if (page) return page.webSocketDebuggerUrl;
    await delay(250);
  }
  throw new Error('no DevTools page target found');
}

class CdpSession {
  constructor(ws) {
    this.ws = ws;
    this.nextId = 1;
    this.pending = new Map();
    this.eventHandlers = new Set();
    ws.onmessage = event => {
      const msg = JSON.parse(event.data);
      if (msg.id && this.pending.has(msg.id)) {
        const { resolve, reject } = this.pending.get(msg.id);
        this.pending.delete(msg.id);
        if (msg.error) reject(new Error(msg.error.message || JSON.stringify(msg.error)));
        else resolve(msg.result || {});
        return;
      }
      for (const handler of this.eventHandlers) handler(msg);
    };
  }

  send(method, params = {}) {
    const id = this.nextId++;
    this.ws.send(JSON.stringify({ id, method, params }));
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      setTimeout(() => {
        if (this.pending.delete(id)) reject(new Error(`CDP timeout: ${method}`));
      }, 30000);
    });
  }

  onEvent(handler) {
    this.eventHandlers.add(handler);
    return () => this.eventHandlers.delete(handler);
  }

  waitForEvent(method, timeout = 30000) {
    return new Promise((resolve, reject) => {
      const off = this.onEvent(msg => {
        if (msg.method === method) {
          clearTimeout(timer);
          off();
          resolve(msg.params || {});
        }
      });
      const timer = setTimeout(() => {
        off();
        reject(new Error(`CDP event timeout: ${method}`));
      }, timeout);
    });
  }
}

class MinimalWebSocket {
  constructor(socket) {
    this.socket = socket;
    this.buffer = Buffer.alloc(0);
    this.onmessage = null;
    this.onerror = null;
    socket.on('data', chunk => this.handleData(chunk));
    socket.on('error', err => {
      if (this.onerror) this.onerror(err);
    });
  }

  handleData(chunk) {
    this.buffer = Buffer.concat([this.buffer, chunk]);
    while (this.buffer.length >= 2) {
      const b0 = this.buffer[0];
      const b1 = this.buffer[1];
      const opcode = b0 & 0x0f;
      const masked = (b1 & 0x80) !== 0;
      let len = b1 & 0x7f;
      let offset = 2;
      if (len === 126) {
        if (this.buffer.length < offset + 2) return;
        len = this.buffer.readUInt16BE(offset);
        offset += 2;
      } else if (len === 127) {
        if (this.buffer.length < offset + 8) return;
        len = Number(this.buffer.readBigUInt64BE(offset));
        offset += 8;
      }
      let mask = null;
      if (masked) {
        if (this.buffer.length < offset + 4) return;
        mask = this.buffer.subarray(offset, offset + 4);
        offset += 4;
      }
      if (this.buffer.length < offset + len) return;
      let payload = this.buffer.subarray(offset, offset + len);
      this.buffer = this.buffer.subarray(offset + len);
      if (mask) {
        payload = Buffer.from(payload.map((byte, i) => byte ^ mask[i % 4]));
      }
      if (opcode === 1 && this.onmessage) {
        this.onmessage({ data: payload.toString('utf8') });
      } else if (opcode === 8) {
        this.close();
      } else if (opcode === 9) {
        this.sendFrame(payload, 0x0a);
      }
    }
  }

  send(data) {
    this.sendFrame(Buffer.from(data), 0x01);
  }

  sendFrame(payload, opcode) {
    const mask = crypto.randomBytes(4);
    let header;
    if (payload.length < 126) {
      header = Buffer.from([0x80 | opcode, 0x80 | payload.length]);
    } else if (payload.length <= 0xffff) {
      header = Buffer.alloc(4);
      header[0] = 0x80 | opcode;
      header[1] = 0x80 | 126;
      header.writeUInt16BE(payload.length, 2);
    } else {
      header = Buffer.alloc(10);
      header[0] = 0x80 | opcode;
      header[1] = 0x80 | 127;
      header.writeBigUInt64BE(BigInt(payload.length), 2);
    }
    const masked = Buffer.alloc(payload.length);
    for (let i = 0; i < payload.length; i += 1) {
      masked[i] = payload[i] ^ mask[i % 4];
    }
    this.socket.write(Buffer.concat([header, mask, masked]));
  }

  close() {
    try {
      this.socket.end();
    } catch {}
  }
}

function openRawWebSocket(wsUrl) {
  return new Promise((resolve, reject) => {
    const parsed = new URL(wsUrl);
    const port = Number(parsed.port || 80);
    const host = parsed.hostname;
    const socket = net.createConnection({ host, port });
    const key = crypto.randomBytes(16).toString('base64');
    let buffer = Buffer.alloc(0);
    const timer = setTimeout(() => {
      socket.destroy();
      reject(new Error(`DevTools websocket handshake timeout: ${wsUrl}`));
    }, 10000);
    socket.once('connect', () => {
      socket.write([
        `GET ${parsed.pathname}${parsed.search} HTTP/1.1`,
        `Host: ${host}:${port}`,
        'Upgrade: websocket',
        'Connection: Upgrade',
        `Sec-WebSocket-Key: ${key}`,
        'Sec-WebSocket-Version: 13',
        '\r\n',
      ].join('\r\n'));
    });
    socket.on('data', chunk => {
      buffer = Buffer.concat([buffer, chunk]);
      const headerEnd = buffer.indexOf('\r\n\r\n');
      if (headerEnd < 0) return;
      const head = buffer.subarray(0, headerEnd).toString('utf8');
      const rest = buffer.subarray(headerEnd + 4);
      if (!/^HTTP\/1\.1 101\b/.test(head)) {
        clearTimeout(timer);
        socket.destroy();
        reject(new Error(`DevTools websocket handshake failed: ${head.split('\r\n')[0]}`));
        return;
      }
      clearTimeout(timer);
      socket.removeAllListeners('data');
      const ws = new MinimalWebSocket(socket);
      if (rest.length) ws.handleData(rest);
      resolve(ws);
    });
    socket.once('error', err => {
      clearTimeout(timer);
      reject(err);
    });
  });
}

async function openWebSocket(url) {
  if (typeof WebSocket !== 'function') return openRawWebSocket(url);
  const ws = new WebSocket(url);
  await new Promise((resolve, reject) => {
    ws.onopen = resolve;
    ws.onerror = () => reject(new Error(`cannot connect DevTools websocket: ${url}`));
  });
  return ws;
}

async function cdpBrowserChecks(url) {
  const browserPath = findBrowser();
  if (!browserPath) return { checked: false, skipped: true, reason: 'system Chrome/Edge browser not found' };

  const userDataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'qbv-verify-'));
  const proc = spawn(browserPath, [
    '--headless=new',
    '--remote-debugging-port=0',
    `--user-data-dir=${userDataDir}`,
    '--disable-gpu',
    '--no-first-run',
    '--no-default-browser-check',
    'about:blank',
  ], { stdio: ['ignore', 'pipe', 'pipe'] });

  try {
    const debugWs = await waitForDebugEndpoint(proc);
    const ws = await openWebSocket(await pageWebSocketUrl(debugWs));
    const cdp = new CdpSession(ws);
    const results = [];
    const consoleErrors = [];
    cdp.onEvent(msg => {
      if (msg.method === 'Runtime.exceptionThrown') {
        const text = msg.params?.exceptionDetails?.text || 'Runtime exception';
        if (CORE_ERROR_RE.test(text)) consoleErrors.push({ viewport: 'unknown', type: 'error', text });
      }
      if (msg.method === 'Runtime.consoleAPICalled') {
        const type = msg.params?.type || '';
        const text = (msg.params?.args || []).map(arg => String(arg.value || arg.description || '')).join(' ');
        if (['error', 'warning', 'warn'].includes(type) && CORE_ERROR_RE.test(text)) {
          consoleErrors.push({ viewport: 'unknown', type, text });
        }
      }
    });
    await cdp.send('Page.enable');
    await cdp.send('Runtime.enable');
    for (const viewport of VIEWPORTS) {
      await cdp.send('Emulation.setDeviceMetricsOverride', {
        width: viewport.width,
        height: viewport.height,
        deviceScaleFactor: 1,
        mobile: viewport.mobile,
      });
      const loaded = cdp.waitForEvent('Page.loadEventFired', 30000).catch(() => null);
      await cdp.send('Page.navigate', { url });
      await loaded;
      await delay(1200);
      const evaluated = await cdp.send('Runtime.evaluate', {
        expression: `(${pageMetricsExpression.toString()})()`,
        returnByValue: true,
        awaitPromise: true,
      });
      if (evaluated.exceptionDetails) {
        consoleErrors.push({ viewport: viewport.name, type: 'error', text: evaluated.exceptionDetails.text || 'Runtime.evaluate failed' });
        continue;
      }
      results.push(viewportResult(viewport, evaluated.result.value));
    }
    ws.close();
    return { checked: true, engine: 'system-browser', browser: browserPath, viewports: results, consoleErrors };
  } catch (err) {
    return { checked: false, skipped: true, reason: err && err.message ? err.message : String(err), browser: browserPath };
  } finally {
    try {
      proc.kill();
    } catch {}
    try {
      fs.rmSync(userDataDir, { recursive: true, force: true });
    } catch {}
  }
}

async function browserChecks(v) {
  const url = targetUrl(v);
  const pw = await loadPlaywright();
  let playwrightError = '';
  if (pw) {
    try {
      return await playwrightBrowserChecks(pw, url);
    } catch (err) {
      playwrightError = err && err.message ? err.message : String(err);
    }
  }

  const fallback = await cdpBrowserChecks(url);
  if (fallback.checked) {
    if (playwrightError) fallback.playwright_error = playwrightError;
    return fallback;
  }
  const prefix = pw
    ? `playwright failed: ${playwrightError}`
    : 'playwright package is not available';
  return {
    checked: false,
    skipped: true,
    reason: `${prefix}; ${fallback.reason}`,
    browser: fallback.browser || '',
  };
}

function summarize(staticResult, browserResult, options) {
  const problems = [...staticResult.problems];
  const warnings = [];
  if (browserResult.checked) {
    for (const r of browserResult.viewports) {
      if (r.horizontalOverflow) problems.push(`${r.viewport}: 存在横向溢出`);
      if (!r.hasH1) problems.push(`${r.viewport}: 缺少可见 h1`);
      if (r.placeholderHits.length) problems.push(`${r.viewport}: 占位符残留 ${r.placeholderHits.join(', ')}`);
      if (r.placeholderOnly) problems.push(`${r.viewport}: 核心内容疑似全是占位符`);
    }
    if (browserResult.consoleErrors.length) problems.push('控制台存在核心接口/运行时错误');
  } else {
    const warning = `浏览器视口检查未执行: ${browserResult.reason}`;
    warnings.push(warning);
    if (options.requireBrowser) problems.push(warning);
  }
  return { ok: problems.length === 0, problems, warnings };
}

function updateManifest(file, verification) {
  if (!file) return;
  const abs = path.isAbsolute(file) ? file : path.resolve(process.cwd(), file);
  if (!fs.existsSync(abs)) return;
  const data = JSON.parse(fs.readFileSync(abs, 'utf8'));
  data.verification = Object.assign({}, data.verification || {}, { page_verify: verification });
  fs.writeFileSync(abs, JSON.stringify(data, null, 2), 'utf8');
}

try {
  const html = await readHtml(target);
  const staticResult = staticChecks(html);
  const browserResult = await browserChecks(target);
  const summary = summarize(staticResult, browserResult, { requireBrowser });
  const result = {
    code: summary.ok ? 0 : 1,
    target,
    verification_level: browserResult.checked ? 'browser' : 'static-only',
    require_browser: requireBrowser,
    static: staticResult,
    browser: browserResult,
    warnings: summary.warnings,
    problems: summary.problems,
  };
  updateManifest(manifestPath, result);
  emit(result);
  process.exit(summary.ok ? 0 : 1);
} catch (err) {
  emit({ code: 1, target, message: err && err.message ? err.message : String(err) });
  process.exit(1);
}
