#!/usr/bin/env node
/*
 * Verify a generated QuantBuddy page before upload/update.
 *
 * Usage:
 *   node scripts/verify_page.mjs output/pages/demo.html
 *   node scripts/verify_page.mjs https://pages.quantbuddy.cn/...
 *   node scripts/verify_page.mjs output/pages/demo.html --manifest output/pages/demo.manifest.json
 */

import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const args = process.argv.slice(2);
const target = args.find(a => !a.startsWith('--'));
const manifestIdx = args.indexOf('--manifest');
const manifestPath = manifestIdx >= 0 ? args[manifestIdx + 1] : '';

function emit(obj) {
  process.stdout.write(JSON.stringify(obj, null, 2) + '\n');
}

function fail(message) {
  emit({ code: 1, message });
  process.exit(1);
}

if (!target) fail('用法: node scripts/verify_page.mjs <html_file_or_url> [--manifest manifest.json]');

function isUrl(v) {
  return /^https?:\/\//i.test(v);
}

async function readHtml(target) {
  if (isUrl(target)) {
    const resp = await fetch(target);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return await resp.text();
  }
  const abs = path.isAbsolute(target) ? target : path.resolve(process.cwd(), target);
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

async function browserChecks(target) {
  const pw = await loadPlaywright();
  if (!pw) {
    return { checked: false, skipped: true, reason: 'playwright package is not available' };
  }
  const browser = await pw.chromium.launch({ channel: 'chrome', headless: true }).catch(async () => {
    return pw.chromium.launch({ headless: true });
  });
  const url = isUrl(target)
    ? target
    : pathToFileURL(path.isAbsolute(target) ? target : path.resolve(process.cwd(), target)).href;
  const viewports = [
    { name: 'desktop', width: 1440, height: 1000 },
    { name: 'mobile390', width: 390, height: 844 },
    { name: 'mobile320', width: 320, height: 720 },
  ];
  const results = [];
  const consoleErrors = [];
  for (const viewport of viewports) {
    const page = await browser.newPage({ viewport: { width: viewport.width, height: viewport.height } });
    page.on('console', msg => {
      if (['error', 'warning'].includes(msg.type())) {
        const text = msg.text();
        if (/queryFormulaPackage|CORS|mixed-content|Failed to fetch|ReferenceError|TypeError/i.test(text)) {
          consoleErrors.push({ viewport: viewport.name, type: msg.type(), text });
        }
      }
    });
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await page.waitForTimeout(1200);
    const metrics = await page.evaluate(() => {
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
    });
    results.push({
      viewport: viewport.name,
      width: viewport.width,
      horizontalOverflow: metrics.scrollWidth > metrics.clientWidth + 2,
      hasH1: metrics.hasH1,
      placeholderHits: metrics.placeholderHits,
      placeholderOnly: metrics.placeholderOnly,
    });
    await page.close();
  }
  await browser.close();
  return { checked: true, viewports: results, consoleErrors };
}

function summarize(staticResult, browserResult) {
  const problems = [...staticResult.problems];
  if (browserResult.checked) {
    for (const r of browserResult.viewports) {
      if (r.horizontalOverflow) problems.push(`${r.viewport}: 存在横向溢出`);
      if (!r.hasH1) problems.push(`${r.viewport}: 缺少可见 h1`);
      if (r.placeholderHits.length) problems.push(`${r.viewport}: 占位符残留 ${r.placeholderHits.join(', ')}`);
      if (r.placeholderOnly) problems.push(`${r.viewport}: 核心内容疑似全是占位符`);
    }
    if (browserResult.consoleErrors.length) problems.push('控制台存在核心接口/运行时错误');
  }
  return { ok: problems.length === 0, problems };
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
  const summary = summarize(staticResult, browserResult);
  const result = {
    code: summary.ok ? 0 : 1,
    target,
    static: staticResult,
    browser: browserResult,
    problems: summary.problems,
  };
  updateManifest(manifestPath, result);
  emit(result);
  process.exit(summary.ok ? 0 : 1);
} catch (err) {
  emit({ code: 1, target, message: err && err.message ? err.message : String(err) });
  process.exit(1);
}
