#!/usr/bin/env node
/*
 * Verify a generated QuantBuddy page before upload/update.
 *
 * Usage:
 *   node scripts/verify_page.mjs output/pages/demo.html
 *   node scripts/verify_page.mjs https://pages.quantbuddy.cn/...
 *   node scripts/verify_page.mjs output/pages/demo.html --manifest output/pages/demo.manifest.json
 *   node scripts/verify_page.mjs output/pages/demo.html --require-browser
 *   node scripts/verify_page.mjs output/pages/demo.html?cover=1 --require-browser --cover-card
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
const coverCard = args.includes('--cover-card');
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
const COVER_CARD_VIEWPORTS = [
  { name: 'cover720', width: 720, height: 540, mobile: false },
  { name: 'cover580', width: 580, height: 435, mobile: false },
  { name: 'cover390', width: 390, height: 292, mobile: true },
  { name: 'cover320', width: 320, height: 240, mobile: true },
];
const CORE_ERROR_RE = /queryFormulaPackage|CORS|mixed-content|Failed to fetch|ReferenceError|TypeError/i;

function emit(obj) {
  fs.writeSync(1, JSON.stringify(obj, null, 2) + '\n');
}

function fail(message) {
  emit({ code: 1, message });
  process.exit(1);
}

if (!target) {
  fail('用法: node scripts/verify_page.mjs <html_file_or_url> [--manifest manifest.json] [--require-browser] [--cover-card]');
}

function delay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function isUrl(v) {
  return /^https?:\/\//i.test(v);
}

function splitLocalTarget(v) {
  const hashIndex = v.indexOf('#');
  const beforeHash = hashIndex >= 0 ? v.slice(0, hashIndex) : v;
  const hash = hashIndex >= 0 ? v.slice(hashIndex) : '';
  const queryIndex = beforeHash.indexOf('?');
  if (queryIndex < 0) return { file: beforeHash, search: '', hash };
  return {
    file: beforeHash.slice(0, queryIndex),
    search: beforeHash.slice(queryIndex),
    hash,
  };
}

function targetUrl(v) {
  if (isUrl(v)) return v;
  const parts = splitLocalTarget(v);
  const abs = path.isAbsolute(parts.file) ? parts.file : path.resolve(process.cwd(), parts.file);
  const url = new URL(pathToFileURL(abs).href);
  url.search = parts.search;
  url.hash = parts.hash;
  return url.href;
}

async function readHtml(v) {
  if (isUrl(v)) {
    const resp = await fetch(v);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return await resp.text();
  }
  const parts = splitLocalTarget(v);
  const abs = path.isAbsolute(parts.file) ? parts.file : path.resolve(process.cwd(), parts.file);
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

async function playwrightBrowserChecks(pw, url, options = {}) {
  const browser = await launchPlaywrightBrowser(pw);
  const results = [];
  const consoleErrors = [];
  const viewports = options.coverCard ? COVER_CARD_VIEWPORTS : VIEWPORTS;
  const settleMs = options.coverCard ? 5000 : 1200;
  try {
    for (const viewport of viewports) {
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
      await page.waitForTimeout(settleMs);
      const metrics = await page.evaluate(pageMetricsExpression);
      results.push(viewportResult(viewport, metrics, options));
      await page.close();
    }
  } finally {
    await browser.close();
  }
  return { checked: true, engine: 'playwright', cover_card: !!options.coverCard, viewports: results, consoleErrors };
}

function pageMetricsExpression() {
  const doc = document.documentElement;
  const bodyText = document.body ? document.body.innerText : '';
  const h1 = document.querySelector('h1');
  const visibleText = bodyText.replace(/\s+/g, '');
  const placeholderHits = ['QB_SHARED_', 'replace_with_signature', 'pkg_replace', '__PLACEHOLDER__']
    .filter(token => document.documentElement.innerHTML.includes(token));
  const placeholderOnly = visibleText.length > 0 && /^[—\-\s.0暂无数据等待取数加载中]+$/.test(visibleText);
  const viewport = { width: window.innerWidth, height: window.innerHeight };
  const coverSelectors = [
    '[data-qb-live-card]',
    '#essenceCard',
    '[data-qb-cover-card]',
    '[data-cover-card]',
    '[data-qb-essence-card]',
    'article[class*="essence"]',
    'article[class*="cover"]',
    'article[class*="card"]',
  ];

  function elementLabel(el, source) {
    if (!el) return '';
    const id = el.id ? `#${el.id}` : '';
    const className = typeof el.className === 'string'
      ? el.className.trim().split(/\s+/).filter(Boolean).slice(0, 3).map(name => `.${name}`).join('')
      : '';
    return source || `${el.tagName.toLowerCase()}${id}${className}`;
  }

  function rectInfo(el) {
    if (!el) return null;
    const rect = el.getBoundingClientRect();
    return {
      x: Number(rect.x.toFixed(2)),
      y: Number(rect.y.toFixed(2)),
      width: Number(rect.width.toFixed(2)),
      height: Number(rect.height.toFixed(2)),
      right: Number(rect.right.toFixed(2)),
      bottom: Number(rect.bottom.toFixed(2)),
    };
  }

  function isVisible(el) {
    if (!el) return false;
    const style = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style.display !== 'none'
      && style.visibility !== 'hidden'
      && Number(style.opacity || 1) !== 0
      && rect.width > 1
      && rect.height > 1;
  }

  function parseCssColor(value) {
    const text = String(value || '').trim();
    const match = text.match(/rgba?\(([^)]+)\)/i);
    if (!match) return null;
    const parts = match[1].split(',').map(part => Number.parseFloat(part.trim()));
    if (parts.length < 3 || parts.slice(0, 3).some(part => Number.isNaN(part))) return null;
    return {
      r: Math.max(0, Math.min(255, parts[0])),
      g: Math.max(0, Math.min(255, parts[1])),
      b: Math.max(0, Math.min(255, parts[2])),
      a: parts.length >= 4 && !Number.isNaN(parts[3]) ? parts[3] : 1,
      raw: text,
    };
  }

  function colorLuma(color) {
    if (!color) return null;
    return Number((0.2126 * color.r + 0.7152 * color.g + 0.0722 * color.b).toFixed(2));
  }

  function effectiveBackgroundInfo(el) {
    let node = el;
    while (node && node.nodeType === 1) {
      const color = parseCssColor(window.getComputedStyle(node).backgroundColor);
      if (color && color.a >= 0.5) {
        return { color: color.raw, luma: colorLuma(color), selector: elementLabel(node, '') };
      }
      node = node.parentElement;
    }
    return { color: 'rgb(255, 255, 255)', luma: 255, selector: 'default-white' };
  }

  function fontInfo(el) {
    if (!el) return null;
    const style = window.getComputedStyle(el);
    return {
      size: Number.parseFloat(style.fontSize || '0') || 0,
      weight: style.fontWeight || '',
      text: (el.textContent || '').trim(),
    };
  }

  function darkAreaRatio(root, rootRect) {
    if (!root || !rootRect || !rootRect.width || !rootRect.height) return 0;
    const rootArea = rootRect.width * rootRect.height;
    let darkArea = 0;
    const nodes = [root, ...Array.from(root.querySelectorAll('*'))];
    for (const node of nodes) {
      if (!isVisible(node)) continue;
      const rect = node.getBoundingClientRect();
      const area = Math.max(0, rect.width) * Math.max(0, rect.height);
      if (area < 80) continue;
      const color = parseCssColor(window.getComputedStyle(node).backgroundColor);
      const luma = colorLuma(color);
      if (color && color.a >= 0.5 && luma != null && luma < 115) {
        darkArea += Math.min(area, rootArea);
      }
    }
    return Number(Math.min(1, darkArea / rootArea).toFixed(3));
  }

  let coverRoot = null;
  let coverSource = '';
  for (const selector of coverSelectors) {
    const found = document.querySelector(selector);
    if (found) {
      coverRoot = found;
      coverSource = selector;
      break;
    }
  }

  if (!coverRoot) {
    const candidates = Array.from(document.querySelectorAll(
      '[data-qb-cover-card], [data-cover-card], [data-qb-essence-card], article, main > section, main, [class*="essence"], [class*="cover"], [class*="card"]'
    ))
      .filter(isVisible)
      .map(el => {
        const rect = el.getBoundingClientRect();
        const area = rect.width * rect.height;
        const offsetPenalty = Math.abs(rect.left) + Math.abs(rect.top)
          + Math.abs(window.innerWidth - rect.right) + Math.abs(window.innerHeight - rect.bottom);
        return { el, score: area - offsetPenalty * 50 };
      })
      .sort((a, b) => b.score - a.score);
    if (candidates.length) {
      coverRoot = candidates[0].el;
      coverSource = elementLabel(coverRoot, '');
    }
  }

  const coverRect = rectInfo(coverRoot);
  const coverText = coverRoot && coverRoot.innerText ? coverRoot.innerText : '';
  const brandEl = coverRoot ? coverRoot.querySelector('[data-qb-live-card-brand]') : null;
  const dateEl = coverRoot ? coverRoot.querySelector('[data-qb-live-card-date]') : null;
  const titleEl = coverRoot ? coverRoot.querySelector('[data-qb-live-card-title]') : null;
  const descriptionEl = coverRoot ? coverRoot.querySelector('[data-qb-live-card-description]') : null;
  const coreEl = coverRoot ? coverRoot.querySelector('[data-qb-live-card-core]') : null;
  function visibleElements(selector) {
    if (!coverRoot) return [];
    return Array.from(coverRoot.querySelectorAll(selector)).filter(isVisible);
  }
  function textSize(el) {
    return el && el.innerText ? el.innerText.replace(/\s+/g, '').length : 0;
  }
  const infoChipCount = visibleElements([
    '[data-qb-live-card-chip]',
    '.qb-cover-pill',
    '.essence-kpi',
    '.live-card-metric'
  ].join(',')).length;
  const tagCount = visibleElements([
    '[data-qb-live-card-tag]',
    '.live-card-tag',
    '.essence-read > span',
    '.qb-cover-live'
  ].join(',')).length;
  const secondaryBlockCount = visibleElements([
    '.qb-cover-grid',
    '.qb-cover-footer',
    '.essence-summary',
    '.essence-points',
    '.live-card-rank',
    '.live-card-points'
  ].join(',')).length;
  const largeValueCount = visibleElements([
    '.qb-cover-temp .value',
    '.essence-score-value',
    '.live-card-primary-value',
    '[data-qb-live-card-primary-value]'
  ].join(',')).filter(el => {
    const fontSize = Number.parseFloat(getComputedStyle(el).fontSize || '0');
    return fontSize >= 34 && /[\d一二三四五六七八九十优良中差高低冷热]/.test(el.textContent || '');
  }).length;
  const graphicSelector = '[data-qb-live-card-visual], .qb-cover-bars, .live-card-snow, canvas, svg';
  const graphicCount = visibleElements(graphicSelector).filter(el => {
    const ancestor = el.parentElement && el.parentElement.closest(graphicSelector);
    if (ancestor && coverRoot.contains(ancestor)) return false;
    const rect = el.getBoundingClientRect();
    return rect.width >= 40 && rect.height >= 30;
  }).length;
  const coverPlaceholderHits = ['取数中', '判断生成中', '读取中', '加载中', '数据加载中', '等待取数', '暂无数据']
    .filter(token => coverText.includes(token));
  const dashCount = (coverText.match(/—/g) || []).length;
  const rootRatio = coverRect && coverRect.height > 0 ? coverRect.width / coverRect.height : 0;
  const tolerance = 3;
  const sizeTolerance = 6;
  const coverFillsViewport = !!coverRect
    && Math.abs(coverRect.x) <= tolerance
    && Math.abs(coverRect.y) <= tolerance
    && coverRect.width >= viewport.width - sizeTolerance
    && coverRect.height >= viewport.height - sizeTolerance
    && coverRect.right <= viewport.width + sizeTolerance
    && coverRect.bottom <= viewport.height + sizeTolerance;
  const coverRatioOk = !!coverRect && Math.abs(rootRatio - (4 / 3)) <= 0.035;
  const rootBackground = effectiveBackgroundInfo(coverRoot);
  const bodyBackground = effectiveBackgroundInfo(document.body || document.documentElement);
  const darkCoverage = darkAreaRatio(coverRoot, coverRect);

  return {
    scrollWidth: doc.scrollWidth,
    clientWidth: doc.clientWidth,
    scrollHeight: doc.scrollHeight,
    clientHeight: doc.clientHeight,
    hasH1: !!(h1 && h1.textContent.trim()),
    placeholderHits,
    placeholderOnly,
    cover: {
      rootFound: !!coverRoot,
      selector: elementLabel(coverRoot, coverSource),
      visible: isVisible(coverRoot),
      rect: coverRect,
      fillsViewport: coverFillsViewport,
      ratio: Number(rootRatio.toFixed(4)),
      ratioOk: coverRatioOk,
      placeholderHits: coverPlaceholderHits,
      dashCount,
      textLength: coverText.replace(/\s+/g, '').length,
      contentBudget: {
        titleLength: textSize(titleEl),
        descriptionLength: textSize(descriptionEl),
        infoChipCount,
        tagCount,
        secondaryBlockCount,
        largeValueCount,
        graphicCount,
      },
      rootHasLiveCardMarker: !!(coverRoot && coverRoot.hasAttribute('data-qb-live-card')),
      containsLegacyVisibleName: coverText.includes('精华卡'),
      background: {
        root: rootBackground,
        body: bodyBackground,
        darkAreaRatio: darkCoverage,
      },
      contract: {
        brand: fontInfo(brandEl),
        date: fontInfo(dateEl),
        title: fontInfo(titleEl),
        description: fontInfo(descriptionEl),
        coreFound: !!coreEl && isVisible(coreEl),
        dateLooksIso: !!(dateEl && /^\d{4}-\d{2}-\d{2}$/.test((dateEl.textContent || '').trim())),
      },
    },
  };
}

function viewportResult(viewport, metrics, options = {}) {
  const result = {
    viewport: viewport.name,
    width: viewport.width,
    horizontalOverflow: metrics.scrollWidth > metrics.clientWidth + 2,
    verticalOverflow: metrics.scrollHeight > metrics.clientHeight + 2,
    hasH1: metrics.hasH1,
    placeholderHits: metrics.placeholderHits,
    placeholderOnly: metrics.placeholderOnly,
  };
  if (options.coverCard) {
    result.cover = metrics.cover;
  }
  return result;
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

async function cdpBrowserChecks(url, options = {}) {
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
    const viewports = options.coverCard ? COVER_CARD_VIEWPORTS : VIEWPORTS;
    const settleMs = options.coverCard ? 5000 : 1200;
    for (const viewport of viewports) {
      await cdp.send('Emulation.setDeviceMetricsOverride', {
        width: viewport.width,
        height: viewport.height,
        deviceScaleFactor: 1,
        mobile: viewport.mobile,
      });
      const loaded = cdp.waitForEvent('Page.loadEventFired', 30000).catch(() => null);
      await cdp.send('Page.navigate', { url });
      await loaded;
      await delay(settleMs);
      const evaluated = await cdp.send('Runtime.evaluate', {
        expression: `(${pageMetricsExpression.toString()})()`,
        returnByValue: true,
        awaitPromise: true,
      });
      if (evaluated.exceptionDetails) {
        consoleErrors.push({ viewport: viewport.name, type: 'error', text: evaluated.exceptionDetails.text || 'Runtime.evaluate failed' });
        continue;
      }
      results.push(viewportResult(viewport, evaluated.result.value, options));
    }
    ws.close();
    return { checked: true, engine: 'system-browser', browser: browserPath, cover_card: !!options.coverCard, viewports: results, consoleErrors };
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

async function browserChecks(v, options = {}) {
  const url = targetUrl(v);
  const pw = await loadPlaywright();
  let playwrightError = '';
  if (pw) {
    try {
      return await playwrightBrowserChecks(pw, url, options);
    } catch (err) {
      playwrightError = err && err.message ? err.message : String(err);
    }
  }

  const fallback = await cdpBrowserChecks(url, options);
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
      if (options.coverCard) {
        if (r.verticalOverflow) problems.push(`${r.viewport}: 宽宝活卡存在纵向滚动`);
        const cover = r.cover;
        if (!cover || !cover.rootFound) {
          problems.push(`${r.viewport}: 未找到宽宝活卡根节点`);
        } else {
          const rect = cover.rect
            ? `${cover.rect.width}x${cover.rect.height} @ ${cover.rect.x},${cover.rect.y}`
            : 'no rect';
          if (!cover.visible) problems.push(`${r.viewport}: 宽宝活卡根节点不可见 (${cover.selector})`);
          if (!cover.fillsViewport) problems.push(`${r.viewport}: 宽宝活卡未填满 viewport (${cover.selector}; ${rect})`);
          if (!cover.ratioOk) problems.push(`${r.viewport}: 宽宝活卡比例不是 4:3 (${cover.selector}; ratio=${cover.ratio})`);
          if (!cover.rootHasLiveCardMarker) problems.push(`${r.viewport}: 宽宝活卡根节点缺少 data-qb-live-card`);
          if (cover.containsLegacyVisibleName) problems.push(`${r.viewport}: 宽宝活卡仍显示旧名称「精华卡」`);
          const bg = cover.background || {};
          if (bg.root && bg.root.luma != null && bg.root.luma < 155) {
            problems.push(`${r.viewport}: 宽宝活卡根背景不是官网浅色系 (${bg.root.color}; luma=${bg.root.luma})`);
          }
          if (bg.body && bg.body.luma != null && bg.body.luma < 155) {
            problems.push(`${r.viewport}: 宽宝活卡页面背景不是官网浅色系 (${bg.body.color}; luma=${bg.body.luma})`);
          }
          if (bg.darkAreaRatio != null && bg.darkAreaRatio > 0.55) {
            problems.push(`${r.viewport}: 宽宝活卡深色背景面积过大 (${Math.round(bg.darkAreaRatio * 100)}%)`);
          }
          const contract = cover.contract || {};
          if (!contract.brand) {
            problems.push(`${r.viewport}: 缺少 data-qb-live-card-brand 官方标签预留位`);
          } else if (contract.brand.text === '宽宝活卡' || contract.brand.text === '精华卡') {
            problems.push(`${r.viewport}: 左上角预留位不应显示固定文案「${contract.brand.text}」`);
          }
          if (!contract.date || !contract.date.text) problems.push(`${r.viewport}: 缺少 data-qb-live-card-date 更新日期`);
          else if (!contract.dateLooksIso) problems.push(`${r.viewport}: 更新日期格式不是 YYYY-MM-DD (${contract.date.text})`);
          if (!contract.title || !contract.title.text) problems.push(`${r.viewport}: 缺少 data-qb-live-card-title 标题`);
          if (!contract.description || !contract.description.text) problems.push(`${r.viewport}: 缺少 data-qb-live-card-description 描述`);
          if (!contract.coreFound) problems.push(`${r.viewport}: 缺少可见 data-qb-live-card-core 核心区`);
          const budget = cover.contentBudget || {};
          if (cover.textLength > 170) problems.push(`${r.viewport}: 宽宝活卡文本过多（${cover.textLength}/170）`);
          if (budget.titleLength > 24) problems.push(`${r.viewport}: 宽宝活卡标题过长（${budget.titleLength}/24）`);
          if (budget.descriptionLength > 56) problems.push(`${r.viewport}: 宽宝活卡描述过长（${budget.descriptionLength}/56）`);
          if (budget.infoChipCount > 3) problems.push(`${r.viewport}: 宽宝活卡解释指标过多（${budget.infoChipCount}/3）`);
          if (budget.tagCount > 3) problems.push(`${r.viewport}: 宽宝活卡短标签过多（${budget.tagCount}/3）`);
          if (budget.secondaryBlockCount > 0) problems.push(`${r.viewport}: 宽宝活卡仍包含二级阅读块（${budget.secondaryBlockCount} 个）`);
          if (budget.graphicCount > 1) problems.push(`${r.viewport}: 宽宝活卡图形表达过多（${budget.graphicCount}/1）`);
          if (budget.largeValueCount > 0 && budget.graphicCount > 0) {
            problems.push(`${r.viewport}: 宽宝活卡大数字与主图形同时出现，应二选一`);
          }
          for (const problem of [
            fontSizeProblem('左上角标签预留位', contract.brand, 8, 15),
            fontSizeProblem('更新日期', contract.date, 8, 15),
            fontSizeProblem('标题', contract.title, 16, 34),
            fontSizeProblem('描述', contract.description, 10, 17),
          ].filter(Boolean)) {
            problems.push(`${r.viewport}: ${problem}`);
          }
          if (cover.placeholderHits.length) problems.push(`${r.viewport}: 宽宝活卡仍处于占位态 ${cover.placeholderHits.join(', ')}`);
          if (cover.dashCount >= 3) problems.push(`${r.viewport}: 宽宝活卡缺失值过多（— x${cover.dashCount}）`);
          if (cover.textLength < 6) problems.push(`${r.viewport}: 宽宝活卡内容疑似空白或黑屏`);
        }
      }
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

function fontSizeProblem(label, info, min, max) {
  if (!info || !info.text) return '';
  const size = Number(info.size || 0);
  if (size < min || size > max) return `${label}字号不在统一范围 (${size}px, expected ${min}-${max}px)`;
  return '';
}

try {
  const html = await readHtml(target);
  const staticResult = staticChecks(html);
  const browserResult = await browserChecks(target, { coverCard });
  const summary = summarize(staticResult, browserResult, { requireBrowser, coverCard });
  const result = {
    code: summary.ok ? 0 : 1,
    target,
    verification_level: browserResult.checked ? 'browser' : 'static-only',
    require_browser: requireBrowser,
    cover_card: coverCard,
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
