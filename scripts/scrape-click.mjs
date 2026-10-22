// Left-arrow scraper — repeat snapshot → click → wait for loading → snapshot …
//
//   node scripts/scrape-click.mjs                 // Use config.click settings
//   node scripts/scrape-click.mjs <url>           // Start at this URL
//   node scripts/scrape-click.mjs <url> 60        // Limit the page count
//
// Each page URL is logged with its sequence number (see cfg.click.logFile)
import { chromium } from 'playwright';
import { mkdir, readFile, writeFile, appendFile, access } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import path from 'node:path';
import cfg from '../config.mjs';

const box = await readFile('box.json', 'utf8')
  .then(JSON.parse)
  .catch(() => {
    console.error('box.json not found — run `node scripts/pick-box.mjs <url>` first');
    process.exit(1);
  });

const click = cfg.click ?? {};
const startUrl = process.argv[2] || click.startUrl || cfg.urls[0];
const maxPages = Number(process.argv[3] ?? click.maxPages ?? 200);
const afterClickMs = click.afterClickMs ?? 5000;
const logFile = click.logFile ?? 'pages.log';

if (!startUrl) {
  console.error('No starting URL — set config.click.startUrl or pass one via argv');
  process.exit(1);
}

const exists = (p) => access(p).then(() => true, () => false);

// Click coordinates accept pixels { x, y } or proportions { xPct, yPct }
const toPoint = (pt) => ({
  x: Math.round(pt.x ?? pt.xPct * cfg.viewport.width),
  y: Math.round(pt.y ?? pt.yPct * cfg.viewport.height),
});

// ---- Find the "left arrow" ----------------------------------------------------
// Priority: selector > key > point > heuristic
const findNext = async (page) => {
  if (click.selector) {
    const loc = page.locator(click.selector).first();
    return (await loc.count())
      ? { loc, how: `selector: ${click.selector}` }
      : { missing: `Selector "${click.selector}" not found on this page` };
  }
  if (click.key) {
    return { key: click.key, how: `Press key ${click.key}` };
  }
  if (click.point) {
    const p = toPoint(click.point);
    return { point: p, how: `Click coordinates ${p.x},${p.y}` };
  }

  const guess = await page.evaluate(() => {
    const HINT = /prev|left|back|前|戻|‹|«|◀|←|<</i;
    const NEG = /next|right|forward|›|»|▶|→|>>/i;
    const cands = [
      ...document.querySelectorAll('a,button,[role="button"],[class*="arrow"],[class*="nav"]'),
    ];
    let best = null;
    const seen = [];
    for (const el of cands) {
      const r = el.getBoundingClientRect();
      if (r.width < 8 || r.height < 8 || r.width > 400) continue;
      const style = getComputedStyle(el);
      if (style.visibility === 'hidden' || style.display === 'none') continue;
      const text = [
        el.getAttribute('aria-label'),
        el.getAttribute('title'),
        el.className?.baseVal ?? el.className,
        el.id,
        el.textContent?.trim().slice(0, 24),
      ]
        .filter(Boolean)
        .join(' ');
      let score = 0;
      if (HINT.test(text)) score += 10;
      if (NEG.test(text)) score -= 10;
      // The left arrow is usually in the left half of the screen
      if (r.left + r.width / 2 < innerWidth / 2) score += 3;
      const info = {
        score,
        tag: el.tagName.toLowerCase(),
        text: text.slice(0, 70),
        x: Math.round(r.left + r.width / 2),
        y: Math.round(r.top + r.height / 2),
        w: Math.round(r.width),
        h: Math.round(r.height),
      };
      seen.push(info);
      if (score > 0 && (!best || score > best.score)) best = info;
    }
    seen.sort((a, b) => b.score - a.score);
    return { best, seen: seen.slice(0, 12), total: cands.length };
  });

  if (!guess.best) {
    return {
      missing: 'The heuristic could not find an arrow button',
      cands: guess.seen,
      total: guess.total,
    };
  }
  return {
    point: { x: guess.best.x, y: guess.best.y },
    how: `Heuristic (${guess.best.tag} "${guess.best.text}" @${guess.best.x},${guess.best.y})`,
  };
};

// Rough page signature — only used to end the post-click wait early
// Not used to detect the end of the book (that uses the captured image hash)
const signature = (page) =>
  page.evaluate(() =>
    [
      location.href,
      document.body?.innerText?.length ?? 0,
      ...[...document.images].map((i) => i.currentSrc || i.src),
    ].join('|'),
  );

const settle = async (page) => {
  if (cfg.waitFor) await page.waitForSelector(cfg.waitFor, { timeout: 15000 }).catch(() => {});
  // Image loading needs a timeout — broken or untriggered lazy images
  // never emit a 'load' event, so an unlimited wait would hang forever
  await page
    .evaluate((ms) => {
      const pending = [...document.images]
        .filter((i) => !i.complete)
        .map(
          (i) =>
            new Promise((r) => {
              i.addEventListener('load', r, { once: true });
              i.addEventListener('error', r, { once: true });
            }),
        );
      return Promise.race([
        Promise.all(pending),
        new Promise((r) => setTimeout(r, ms)), // Timeout
      ]);
    }, click.imgWaitMs ?? 8000)
    .catch(() => {});
  await page.waitForTimeout(cfg.settleMs);
};

// Return a buffer without writing a file so its hash can be compared with the previous page
const capture = (page) =>
  box.selector && !box.clip
    ? page.locator(box.selector).first().screenshot()
    : page.screenshot({ fullPage: true, clip: box.clip });

const hash = (buf) => createHash('md5').update(buf).digest('hex');

// ---- Start ------------------------------------------------------------
await mkdir(cfg.outDir, { recursive: true });

const browser = await chromium.launch({ headless: cfg.headless });
const context = await browser.newContext({
  viewport: cfg.viewport,
  deviceScaleFactor: cfg.deviceScaleFactor,
});
const page = await context.newPage();

console.log(`Opening ${startUrl}`);
await page.goto(startUrl, { waitUntil: 'domcontentloaded', timeout: 60000 });
await settle(page);

await appendFile(logFile, `\n# ${new Date().toISOString()}  start=${startUrl}\n`, 'utf8');

let prevUrl = null;
let prevShot = null; // Previous image hash — detects duplicate pages
let stuck = 0;
let announced = false;

const first = click.startIndex ?? 1;
let n = first;

while (n < first + maxPages) {
  const seq = String(n).padStart(cfg.pad, '0');
  const out = path.join(cfg.outDir, `${seq}.png`);
  const url = page.url();

  // 1) snapshot
  let dup = false;
  try {
    const buf = await capture(page);
    const shot = hash(buf);
    dup = shot === prevShot;

    if (dup) {
      // Identical to the previous image — navigation did not advance; keep the sequence number
      if (++stuck >= 2) {
        console.log(`Duplicate image ${stuck} times in a row — likely the end of the book; stopping at page ${n - 1}`);
        break;
      }
      console.log(`Duplicate image (${stuck}/2) — trying another click`);
    } else {
      stuck = 0;
      prevShot = shot;
      if (!cfg.overwrite && (await exists(out))) {
        console.log(`Skip  ${out}`);
      } else {
        await writeFile(out, buf);
        console.log(`Saved ${out}  ${url}`);
      }
      // Log this page URL and mark changes from the previous URL
      const changed = prevUrl && url !== prevUrl;
      await appendFile(logFile, `${seq}\t${url}${changed ? '\t<- url changed' : ''}\n`, 'utf8');
      prevUrl = url;
      n++;
    }
  } catch (err) {
    console.warn(`Failed page ${seq}: ${err.message.split('\n')[0]}`);
    n++;
  }

  // 2) Navigate to the next page — key / selector / coordinates
  const next = await findNext(page);
  if (next.missing) {
    console.log(`Cannot continue: ${next.missing} — stopping`);
    if (next.cands) {
      console.log(`Candidates on this page (${next.total}), sorted by score:`);
      for (const c of next.cands) {
        console.log(`  ${String(c.score).padStart(3)}  ${c.tag}  ${c.w}x${c.h} @${c.x},${c.y}  ${c.text}`);
      }
      console.log('Choose one for config.click.selector, or use click.key / click.point instead');
    }
    await page.screenshot({ path: 'debug-page.png', fullPage: true }).catch(() => {});
    break;
  }
  if (!announced) {
    console.log(`Next page via: ${next.how}`);
    announced = true;
  }

  const before = await signature(page);
  try {
    if (next.key) await page.keyboard.press(next.key);
    else if (next.loc) await next.loc.click({ timeout: 10000 });
    else await page.mouse.click(next.point.x, next.point.y);
  } catch (err) {
    console.warn(`Click failed: ${err.message.split('\n')[0]} — stopping`);
    break;
  }

  // 3) Wait for loading — end early if content changes, otherwise wait for afterClickMs
  const deadline = Date.now() + afterClickMs;
  let after = before;
  while (Date.now() < deadline) {
    await page.waitForTimeout(250);
    after = await signature(page).catch(() => before);
    if (after !== before) break;
  }
  if (page.url() !== url) {
    await page.waitForLoadState('domcontentloaded', { timeout: afterClickMs }).catch(() => {});
  }
  await settle(page);
  // Detect the end of the book at the start of the next iteration by comparing captures

  await page.waitForTimeout(cfg.politeDelayMs);
}

await browser.close();
console.log(`\nURL list saved to ${logFile}`);
