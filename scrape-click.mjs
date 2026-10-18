// scraper แบบกดลูกศรซ้าย — วน snapshot → คลิก → รอโหลด → snapshot …
//
//   node scrape-click.mjs                 // ใช้ค่าจาก config.click
//   node scrape-click.mjs <url>           // เริ่มจาก url นี้
//   node scrape-click.mjs <url> 60        // จำกัดจำนวนหน้า
//
// URL ของแต่ละหน้าถูกบันทึกลง log พร้อมเลขลำดับ (ดู cfg.click.logFile)
import { chromium } from 'playwright';
import { mkdir, readFile, writeFile, appendFile, access } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import path from 'node:path';
import cfg from './config.mjs';

const box = await readFile('box.json', 'utf8')
  .then(JSON.parse)
  .catch(() => {
    console.error('ไม่เจอ box.json — รัน `node pick-box.mjs <url>` ก่อน');
    process.exit(1);
  });

const click = cfg.click ?? {};
const startUrl = process.argv[2] || click.startUrl || cfg.urls[0];
const maxPages = Number(process.argv[3] ?? click.maxPages ?? 200);
const afterClickMs = click.afterClickMs ?? 5000;
const logFile = click.logFile ?? 'pages.log';

if (!startUrl) {
  console.error('ยังไม่ได้ตั้ง URL เริ่มต้น — ใส่ใน config.click.startUrl หรือส่งมาทาง argv');
  process.exit(1);
}

const exists = (p) => access(p).then(() => true, () => false);

// พิกัดคลิก รับได้ทั้งแบบพิกเซลตรง ๆ { x, y } และแบบสัดส่วน { xPct, yPct }
const toPoint = (pt) => ({
  x: Math.round(pt.x ?? pt.xPct * cfg.viewport.width),
  y: Math.round(pt.y ?? pt.yPct * cfg.viewport.height),
});

// ---- หา "ลูกศรซ้าย" ----------------------------------------------------
// ลำดับความสำคัญ: selector > key > point > เดาเอง
const findNext = async (page) => {
  if (click.selector) {
    const loc = page.locator(click.selector).first();
    return (await loc.count())
      ? { loc, how: `selector: ${click.selector}` }
      : { missing: `ไม่เจอ selector "${click.selector}" ในหน้านี้` };
  }
  if (click.key) {
    return { key: click.key, how: `กดคีย์ ${click.key}` };
  }
  if (click.point) {
    const p = toPoint(click.point);
    return { point: p, how: `คลิกพิกัด ${p.x},${p.y}` };
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
      // ลูกศรซ้ายมักอยู่ครึ่งซ้ายของจอ
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
      missing: 'heuristic หาปุ่มลูกศรไม่เจอ',
      cands: guess.seen,
      total: guess.total,
    };
  }
  return {
    point: { x: guess.best.x, y: guess.best.y },
    how: `เดาเอง (${guess.best.tag} "${guess.best.text}" @${guess.best.x},${guess.best.y})`,
  };
};

// ลายเซ็นหน้าแบบหยาบ ๆ — ใช้แค่ "ออกจากการรอเร็วขึ้น" หลังกด
// ไม่ใช่ตัวตัดสินว่าจบเล่ม (ตัวนั้นใช้ hash ของภาพที่แคปได้)
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
  // รอรูปโหลด แต่ต้องมีเพดานเวลา — รูปที่ error หรือ lazy ที่ยังไม่ยิง
  // จะไม่ส่ง event 'load' เลย ถ้ารอเปล่า ๆ คือค้างถาวร
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
        new Promise((r) => setTimeout(r, ms)), // เพดาน
      ]);
    }, click.imgWaitMs ?? 8000)
    .catch(() => {});
  await page.waitForTimeout(cfg.settleMs);
};

// คืนเป็น buffer ไม่เขียนไฟล์เอง — จะได้เอาไป hash เทียบหน้าก่อนหน้าได้ด้วย
const capture = (page) =>
  box.selector && !box.clip
    ? page.locator(box.selector).first().screenshot()
    : page.screenshot({ fullPage: true, clip: box.clip });

const hash = (buf) => createHash('md5').update(buf).digest('hex');

// ---- เริ่ม ------------------------------------------------------------
await mkdir(cfg.outDir, { recursive: true });

const browser = await chromium.launch({ headless: cfg.headless });
const context = await browser.newContext({
  viewport: cfg.viewport,
  deviceScaleFactor: cfg.deviceScaleFactor,
});
const page = await context.newPage();

console.log(`เปิด ${startUrl}`);
await page.goto(startUrl, { waitUntil: 'domcontentloaded', timeout: 60000 });
await settle(page);

await appendFile(logFile, `\n# ${new Date().toISOString()}  start=${startUrl}\n`, 'utf8');

let prevUrl = null;
let prevShot = null; // hash ของภาพหน้าก่อน — ใช้ดูว่าหน้าใหม่ซ้ำของเดิมไหม
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
      // ภาพเหมือนหน้าก่อนเป๊ะ — กดแล้วไม่ไปไหน ยังไม่กินเลขลำดับ
      if (++stuck >= 2) {
        console.log(`ภาพซ้ำหน้าเดิม ${stuck} ครั้งติด — น่าจะสุดเล่ม จบที่หน้า ${n - 1}`);
        break;
      }
      console.log(`ภาพซ้ำหน้าเดิม (${stuck}/2) — กดใหม่อีกที`);
    } else {
      stuck = 0;
      prevShot = shot;
      if (!cfg.overwrite && (await exists(out))) {
        console.log(`ข้าม  ${out}`);
      } else {
        await writeFile(out, buf);
        console.log(`ได้   ${out}  ${url}`);
      }
      // บันทึก url ของหน้านี้ + มาร์กตรงที่ url เปลี่ยนจากหน้าก่อน
      const changed = prevUrl && url !== prevUrl;
      await appendFile(logFile, `${seq}\t${url}${changed ? '\t<- url เปลี่ยน' : ''}\n`, 'utf8');
      prevUrl = url;
      n++;
    }
  } catch (err) {
    console.warn(`พลาด หน้า ${seq}: ${err.message.split('\n')[0]}`);
    n++;
  }

  // 2) ไปหน้าถัดไป — กดคีย์ / คลิก selector / คลิกพิกัด
  const next = await findNext(page);
  if (next.missing) {
    console.log(`ไปต่อไม่ได้: ${next.missing} — จบ`);
    if (next.cands) {
      console.log(`ตัวเลือกที่เจอในหน้า (${next.total} ตัว) เรียงตามคะแนน:`);
      for (const c of next.cands) {
        console.log(`  ${String(c.score).padStart(3)}  ${c.tag}  ${c.w}x${c.h} @${c.x},${c.y}  ${c.text}`);
      }
      console.log('เลือกมาสักตัวแล้วใส่ใน config.click.selector หรือใช้ click.key / click.point แทน');
    }
    await page.screenshot({ path: 'debug-page.png', fullPage: true }).catch(() => {});
    break;
  }
  if (!announced) {
    console.log(`ไปหน้าถัดไปด้วย: ${next.how}`);
    announced = true;
  }

  const before = await signature(page);
  try {
    if (next.key) await page.keyboard.press(next.key);
    else if (next.loc) await next.loc.click({ timeout: 10000 });
    else await page.mouse.click(next.point.x, next.point.y);
  } catch (err) {
    console.warn(`กดไม่ผ่าน: ${err.message.split('\n')[0]} — จบ`);
    break;
  }

  // 3) รอโหลด — ออกเร็วถ้าเนื้อหาเปลี่ยนแล้ว ไม่งั้นรอจนครบ afterClickMs
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
  // จบเล่มหรือยัง ตัดสินตอนต้นลูปรอบหน้า ด้วยการเทียบภาพที่แคปได้

  await page.waitForTimeout(cfg.politeDelayMs);
}

await browser.close();
console.log(`\nลิสต์ URL อยู่ใน ${logFile}`);
