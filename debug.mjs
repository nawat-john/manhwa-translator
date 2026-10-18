// Debugger — open one page and report its contents and navigation behavior
//
//   node debug.mjs                    // Use click.startUrl / urls[0]
//   node debug.mjs <url>              // Specify a URL
//   node debug.mjs <url> 5            // Press the arrow 5 times (default: 3)
//   node debug.mjs <url> 3 --headed   // Show the browser and keep it open until Ctrl+C
//
// Output: console report and files in debug/
//   full-N.png = Full page   clip-N.png = capture box from box.json
import { chromium } from 'playwright';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import path from 'node:path';
import cfg from './config.mjs';

const args = process.argv.slice(2).filter((a) => !a.startsWith('--'));
const flag = (name) => process.argv.includes(`--${name}`);

const click = cfg.click ?? {};
// Accepted argv: <url> <steps> / <url> / <steps> / no arguments
const argUrl = args.find((a) => /^\w+:/.test(a));
const argSteps = args.find((a) => /^\d+$/.test(a));
const url = argUrl || click.startUrl || cfg.urls[0];
const steps = Number(argSteps ?? 3);
const headed = flag('headed');
const outDir = 'debug';

if (!url) {
  console.error('No URL — pass one via argv or set config.click.startUrl / config.urls');
  process.exit(1);
}

const box = await readFile('box.json', 'utf8').then(JSON.parse).catch(() => null);
const hash = (b) => createHash('md5').update(b).digest('hex').slice(0, 12);
const ms = (t) => `${((Date.now() - t) / 1000).toFixed(2)}s`;

await mkdir(outDir, { recursive: true });

console.log(`— config —`);
console.log(`  url            ${url}`);
console.log(`  viewport       ${cfg.viewport.width}x${cfg.viewport.height} @${cfg.deviceScaleFactor}x`);
console.log(`  waitFor        ${cfg.waitFor ?? '(no wait)'}`);
console.log(`  box.json       ${box ? JSON.stringify(box.clip ?? box.selector) : '(none)'}`);
console.log(`  Navigation  ${click.selector ?? click.key ?? JSON.stringify(click.point) ?? '(heuristic)'}`);
console.log(`  headless       ${!headed}\n`);

const browser = await chromium.launch({ headless: !headed, slowMo: headed ? 200 : 0 });
const context = await browser.newContext({
  viewport: cfg.viewport,
  deviceScaleFactor: cfg.deviceScaleFactor,
});
const page = await context.newPage();

// ---- Capture page events ----
const errors = [];
const failedReqs = [];
page.on('console', (m) => {
  if (m.type() === 'error' || m.type() === 'warning') {
    errors.push(`[console.${m.type()}] ${m.text().slice(0, 200)}`);
  }
});
page.on('pageerror', (e) => errors.push(`[pageerror] ${e.message.split('\n')[0]}`));
page.on('requestfailed', (r) =>
  failedReqs.push(`${r.failure()?.errorText ?? '?'}  ${r.url().slice(0, 120)}`),
);
page.on('framenavigated', (f) => {
  if (f === page.mainFrame()) console.log(`  » navigate → ${f.url()}`);
});

// ---- Load page ----
let t = Date.now();
console.log('— Load page —');
try {
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
  console.log(`  domcontentloaded  ${ms(t)}`);
} catch (err) {
  console.error(`  goto failed: ${err.message.split('\n')[0]}`);
  await browser.close();
  process.exit(1);
}

if (cfg.waitFor) {
  t = Date.now();
  const ok = await page
    .waitForSelector(cfg.waitFor, { timeout: 15000 })
    .then(() => true, () => false);
  console.log(`  waitFor "${cfg.waitFor}"  ${ok ? `found ${ms(t)}` : 'not found (15s timeout)'}`);
}

t = Date.now();
const imgReport = await page.evaluate((wait) => {
  const pending = [...document.images].filter((i) => !i.complete);
  return Promise.race([
    Promise.all(
      pending.map(
        (i) =>
          new Promise((r) => {
            i.addEventListener('load', () => r('load'), { once: true });
            i.addEventListener('error', () => r('error'), { once: true });
          }),
      ),
    ).then((rs) => ({ pending: pending.length, results: rs })),
    new Promise((r) => setTimeout(() => r({ pending: pending.length, timeout: true }), wait)),
  ]);
}, click.imgWaitMs ?? 8000);
console.log(
  `  Wait for images: ${imgReport.pending} pending  ${ms(t)}` +
    (imgReport.timeout ? '  ← reached imgWaitMs (some images did not emit load/error)' : ''),
);
await page.waitForTimeout(cfg.settleMs);

// ---- Inspect page contents ----
const dom = await page.evaluate(() => {
  const vis = (el) => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 40 && r.height > 40 && s.visibility !== 'hidden' && s.display !== 'none';
  };
  const desc = (el) => {
    const r = el.getBoundingClientRect();
    const src = el.currentSrc || el.src || '';
    return {
      tag: el.tagName.toLowerCase(),
      rect: `${Math.round(r.width)}x${Math.round(r.height)} @${Math.round(r.left)},${Math.round(r.top)}`,
      note: el.tagName === 'CANVAS' ? `canvas ${el.width}x${el.height}` : src.slice(-70),
      broken: el.tagName === 'IMG' && el.complete && el.naturalWidth === 0,
    };
  };
  const HINT = /prev|left|back|前|戻|‹|«|◀|←/i;
  return {
    title: document.title,
    href: location.href,
    scroll: { h: document.body.scrollHeight, w: document.body.scrollWidth },
    media: [...document.querySelectorAll('img,canvas')].filter(vis).map(desc).slice(0, 15),
    imgTotal: document.images.length,
    canvasTotal: document.querySelectorAll('canvas').length,
    arrows: [...document.querySelectorAll('a,button,[role="button"],[class*="arrow"],[class*="nav"]')]
      .filter((el) => {
        const txt = `${el.getAttribute('aria-label') ?? ''} ${el.className} ${el.id} ${el.textContent?.trim().slice(0, 20) ?? ''}`;
        return HINT.test(txt);
      })
      .map((el) => {
        const r = el.getBoundingClientRect();
        return {
          tag: el.tagName.toLowerCase(),
          cls: String(el.className).slice(0, 50),
          label: el.getAttribute('aria-label') ?? el.textContent?.trim().slice(0, 20) ?? '',
          rect: `${Math.round(r.width)}x${Math.round(r.height)} @${Math.round(r.left)},${Math.round(r.top)}`,
        };
      })
      .slice(0, 10),
  };
});

console.log(`\n— Page contents —`);
console.log(`  title       ${dom.title}`);
console.log(`  url         ${dom.href}`);
console.log(`  page size   ${dom.scroll.w}x${dom.scroll.h}`);
console.log(`  img ${dom.imgTotal} images / ${dom.canvasTotal} canvases — visible:`);
for (const m of dom.media) {
  console.log(`    ${m.tag.padEnd(6)} ${m.rect.padEnd(22)} ${m.broken ? 'Failed to load! ' : ''}${m.note}`);
}
if (!dom.media.length) console.log('    (No visible images/canvases — waitFor may not match, or content may be inside an iframe)');

const frames = page.frames().filter((f) => f !== page.mainFrame());
if (frames.length) {
  console.log(`  iframes: ${frames.length}:`);
  for (const f of frames) console.log(`    ${f.url().slice(0, 110)}`);
}

console.log(`  Candidate "left arrow" buttons: ${dom.arrows.length ? '' : '(none)'}`);
for (const a of dom.arrows) {
  console.log(`    ${a.tag.padEnd(7)} ${a.rect.padEnd(22)} ${a.label}  .${a.cls}`);
}

// ---- Inspect keydown listeners via CDP ----
try {
  const cdp = await context.newCDPSession(page);
  for (const target of ['window', 'document']) {
    const { result } = await cdp.send('Runtime.evaluate', { expression: target });
    const { listeners } = await cdp.send('DOMDebugger.getEventListeners', {
      objectId: result.objectId,
    });
    const keys = listeners.filter((l) => l.type.startsWith('key'));
    console.log(
      `  keydown listener on ${target}: ${
        keys.length ? keys.map((k) => `${k.type} (${k.scriptId}:${k.lineNumber})`).join(', ') : 'none'
      }`,
    );
  }
} catch (err) {
  console.log(`  (Could not read listeners: ${err.message.split('\n')[0]})`);
}

// ---- Check capture box ----
const shoot = async (tag) => {
  const full = await page.screenshot({ fullPage: true });
  await writeFile(path.join(outDir, `full-${tag}.png`), full);
  let clip = null;
  try {
    clip =
      box?.selector && !box?.clip
        ? await page.locator(box.selector).first().screenshot()
        : await page.screenshot({ fullPage: true, clip: box?.clip });
    await writeFile(path.join(outDir, `clip-${tag}.png`), clip);
  } catch (err) {
    console.log(`  Box capture failed: ${err.message.split('\n')[0]}`);
  }
  return { full: hash(full), clip: clip ? hash(clip) : null, bytes: clip?.length ?? 0 };
};

console.log(`\n— Capture the first page —`);
let prev = await shoot('0');
console.log(`  full=${prev.full}  clip=${prev.clip} (${(prev.bytes / 1024).toFixed(0)} KB)`);
console.log(`  Files: ${outDir}/full-0.png, ${outDir}/clip-0.png — open them to check the capture box`);

// ---- Press the arrow and check what changes ----
const press = async () => {
  if (click.selector) {
    const loc = page.locator(click.selector).first();
    if (!(await loc.count())) return `Selector not found: ${click.selector}`;
    await loc.click({ timeout: 10000 });
    return `Click ${click.selector}`;
  }
  if (click.point) {
    const p = {
      x: Math.round(click.point.x ?? click.point.xPct * cfg.viewport.width),
      y: Math.round(click.point.y ?? click.point.yPct * cfg.viewport.height),
    };
    await page.mouse.click(p.x, p.y);
    return `Click ${p.x},${p.y}`;
  }
  const key = click.key ?? 'ArrowLeft';
  await page.keyboard.press(key);
  return `Press ${key}`;
};

for (let i = 1; i <= steps; i++) {
  console.log(`\n— Step ${i} —`);
  const urlBefore = page.url();
  t = Date.now();
  let how;
  try {
    how = await press();
  } catch (err) {
    console.log(`  Click failed: ${err.message.split('\n')[0]}`);
    break;
  }
  console.log(`  ${how}`);

  // Watch for changes in the captured image
  const deadline = Date.now() + (click.afterClickMs ?? 5000);
  let changedAt = null;
  while (Date.now() < deadline) {
    await page.waitForTimeout(250);
    try {
      const shot =
        box?.selector && !box?.clip
          ? await page.locator(box.selector).first().screenshot()
          : await page.screenshot({ fullPage: true, clip: box?.clip });
      if (hash(shot) !== prev.clip) {
        changedAt = ms(t);
        break;
      }
    } catch {
      /* Cannot capture during navigation; skip this attempt */
    }
  }
  console.log(
    changedAt
      ? `  Captured image changed at +${changedAt}`
      : `  Captured image did not change within ${(click.afterClickMs ?? 5000) / 1000}s  ← this is the problem`,
  );
  console.log(`  url  ${page.url() === urlBefore ? 'unchanged' : `changed → ${page.url()}`}`);

  await page.waitForTimeout(cfg.settleMs);
  prev = await shoot(String(i));
  console.log(`  full=${prev.full}  clip=${prev.clip} (${(prev.bytes / 1024).toFixed(0)} KB)`);
}

// ---- Summarize captured events ----
if (errors.length) {
  console.log(`\n— Page errors (${errors.length}) —`);
  for (const e of errors.slice(0, 15)) console.log(`  ${e}`);
}
if (failedReqs.length) {
  console.log(`\n— Failed requests (${failedReqs.length}) —`);
  for (const r of failedReqs.slice(0, 15)) console.log(`  ${r}`);
}

console.log(`\nAll images are in ${outDir}/ — compare full-*.png and clip-*.png to check whether the page changed`);

if (headed) {
  console.log('Keeping the browser open — press Ctrl+C to close');
  await new Promise(() => {});
}
await browser.close();
