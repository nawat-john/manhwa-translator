// ตัวไล่ปัญหา — เปิดหน้าเดียว แล้วรายงานว่ามันเห็นอะไร กดแล้วเกิดอะไรขึ้น
//
//   node debug.mjs                    // ใช้ click.startUrl / urls[0]
//   node debug.mjs <url>              // ระบุ url เอง
//   node debug.mjs <url> 5            // กดลูกศร 5 ครั้ง (ค่าเริ่ม 3)
//   node debug.mjs <url> 3 --headed   // เปิดหน้าจอให้เห็น แล้วค้างไว้จนกด Ctrl+C
//
// ผลลัพธ์: รายงานบนจอ + ไฟล์ใน debug/
//   full-N.png = ทั้งหน้า   clip-N.png = เฉพาะกรอบใน box.json
import { chromium } from 'playwright';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import path from 'node:path';
import cfg from './config.mjs';

const args = process.argv.slice(2).filter((a) => !a.startsWith('--'));
const flag = (name) => process.argv.includes(`--${name}`);

const click = cfg.click ?? {};
// argv ยืดหยุ่น: <url> <steps> / <url> / <steps> / ไม่ใส่อะไรเลย
const argUrl = args.find((a) => /^\w+:/.test(a));
const argSteps = args.find((a) => /^\d+$/.test(a));
const url = argUrl || click.startUrl || cfg.urls[0];
const steps = Number(argSteps ?? 3);
const headed = flag('headed');
const outDir = 'debug';

if (!url) {
  console.error('ไม่มี URL — ส่งมาทาง argv หรือใส่ใน config.click.startUrl / config.urls');
  process.exit(1);
}

const box = await readFile('box.json', 'utf8').then(JSON.parse).catch(() => null);
const hash = (b) => createHash('md5').update(b).digest('hex').slice(0, 12);
const ms = (t) => `${((Date.now() - t) / 1000).toFixed(2)}s`;

await mkdir(outDir, { recursive: true });

console.log(`— config —`);
console.log(`  url            ${url}`);
console.log(`  viewport       ${cfg.viewport.width}x${cfg.viewport.height} @${cfg.deviceScaleFactor}x`);
console.log(`  waitFor        ${cfg.waitFor ?? '(ไม่รอ)'}`);
console.log(`  box.json       ${box ? JSON.stringify(box.clip ?? box.selector) : '(ไม่มี)'}`);
console.log(`  วิธีไปหน้าถัดไป  ${click.selector ?? click.key ?? JSON.stringify(click.point) ?? '(เดาเอง)'}`);
console.log(`  headless       ${!headed}\n`);

const browser = await chromium.launch({ headless: !headed, slowMo: headed ? 200 : 0 });
const context = await browser.newContext({
  viewport: cfg.viewport,
  deviceScaleFactor: cfg.deviceScaleFactor,
});
const page = await context.newPage();

// ---- ดักเหตุการณ์จากหน้าเว็บ ----
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

// ---- โหลดหน้า ----
let t = Date.now();
console.log('— โหลดหน้า —');
try {
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
  console.log(`  domcontentloaded  ${ms(t)}`);
} catch (err) {
  console.error(`  goto พลาด: ${err.message.split('\n')[0]}`);
  await browser.close();
  process.exit(1);
}

if (cfg.waitFor) {
  t = Date.now();
  const ok = await page
    .waitForSelector(cfg.waitFor, { timeout: 15000 })
    .then(() => true, () => false);
  console.log(`  waitFor "${cfg.waitFor}"  ${ok ? `เจอ ${ms(t)}` : 'ไม่เจอ (timeout 15s)'}`);
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
  `  รอรูปโหลด  ค้างอยู่ ${imgReport.pending} ใบ  ${ms(t)}` +
    (imgReport.timeout ? '  ← ชนเพดาน imgWaitMs (มีรูปที่ไม่ยิง load/error)' : ''),
);
await page.waitForTimeout(cfg.settleMs);

// ---- หน้านี้มีอะไรอยู่ ----
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

console.log(`\n— หน้านี้มีอะไร —`);
console.log(`  title       ${dom.title}`);
console.log(`  url         ${dom.href}`);
console.log(`  page size   ${dom.scroll.w}x${dom.scroll.h}`);
console.log(`  img ${dom.imgTotal} ใบ / canvas ${dom.canvasTotal} อัน — ที่มองเห็น:`);
for (const m of dom.media) {
  console.log(`    ${m.tag.padEnd(6)} ${m.rect.padEnd(22)} ${m.broken ? 'โหลดไม่ขึ้น! ' : ''}${m.note}`);
}
if (!dom.media.length) console.log('    (ไม่เจอรูป/canvas ที่มองเห็นเลย — waitFor อาจไม่ตรง หรือเนื้อหาอยู่ใน iframe)');

const frames = page.frames().filter((f) => f !== page.mainFrame());
if (frames.length) {
  console.log(`  iframe ${frames.length} อัน:`);
  for (const f of frames) console.log(`    ${f.url().slice(0, 110)}`);
}

console.log(`  ปุ่มที่เข้าข่าย "ลูกศรซ้าย": ${dom.arrows.length ? '' : '(ไม่มี)'}`);
for (const a of dom.arrows) {
  console.log(`    ${a.tag.padEnd(7)} ${a.rect.padEnd(22)} ${a.label}  .${a.cls}`);
}

// ---- ใครดัก keydown ไว้บ้าง (ผ่าน CDP) ----
try {
  const cdp = await context.newCDPSession(page);
  for (const target of ['window', 'document']) {
    const { result } = await cdp.send('Runtime.evaluate', { expression: target });
    const { listeners } = await cdp.send('DOMDebugger.getEventListeners', {
      objectId: result.objectId,
    });
    const keys = listeners.filter((l) => l.type.startsWith('key'));
    console.log(
      `  keydown listener บน ${target}: ${
        keys.length ? keys.map((k) => `${k.type} (${k.scriptId}:${k.lineNumber})`).join(', ') : 'ไม่มี'
      }`,
    );
  }
} catch (err) {
  console.log(`  (อ่าน listener ไม่ได้: ${err.message.split('\n')[0]})`);
}

// ---- แคปตามกรอบได้ไหม ----
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
    console.log(`  แคปตามกรอบพลาด: ${err.message.split('\n')[0]}`);
  }
  return { full: hash(full), clip: clip ? hash(clip) : null, bytes: clip?.length ?? 0 };
};

console.log(`\n— แคปหน้าแรก —`);
let prev = await shoot('0');
console.log(`  full=${prev.full}  clip=${prev.clip} (${(prev.bytes / 1024).toFixed(0)} KB)`);
console.log(`  ไฟล์อยู่ที่ ${outDir}/full-0.png, ${outDir}/clip-0.png — เปิดดูว่ากรอบตรงที่ต้องการไหม`);

// ---- กดลูกศรแล้วดูว่าอะไรขยับ ----
const press = async () => {
  if (click.selector) {
    const loc = page.locator(click.selector).first();
    if (!(await loc.count())) return `ไม่เจอ selector ${click.selector}`;
    await loc.click({ timeout: 10000 });
    return `คลิก ${click.selector}`;
  }
  if (click.point) {
    const p = {
      x: Math.round(click.point.x ?? click.point.xPct * cfg.viewport.width),
      y: Math.round(click.point.y ?? click.point.yPct * cfg.viewport.height),
    };
    await page.mouse.click(p.x, p.y);
    return `คลิก ${p.x},${p.y}`;
  }
  const key = click.key ?? 'ArrowLeft';
  await page.keyboard.press(key);
  return `กด ${key}`;
};

for (let i = 1; i <= steps; i++) {
  console.log(`\n— ครั้งที่ ${i} —`);
  const urlBefore = page.url();
  t = Date.now();
  let how;
  try {
    how = await press();
  } catch (err) {
    console.log(`  กดไม่ผ่าน: ${err.message.split('\n')[0]}`);
    break;
  }
  console.log(`  ${how}`);

  // เฝ้าดูว่าภาพในกรอบเปลี่ยนตอนไหน
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
      /* ระหว่าง navigate แคปไม่ได้ ข้ามไป */
    }
  }
  console.log(
    changedAt
      ? `  ภาพในกรอบเปลี่ยนที่ +${changedAt}`
      : `  ภาพในกรอบไม่เปลี่ยนเลยจนครบ ${(click.afterClickMs ?? 5000) / 1000}s  ← ตรงนี้คือปัญหา`,
  );
  console.log(`  url  ${page.url() === urlBefore ? 'เท่าเดิม' : `เปลี่ยน → ${page.url()}`}`);

  await page.waitForTimeout(cfg.settleMs);
  prev = await shoot(String(i));
  console.log(`  full=${prev.full}  clip=${prev.clip} (${(prev.bytes / 1024).toFixed(0)} KB)`);
}

// ---- สรุปเหตุการณ์ที่ดักไว้ ----
if (errors.length) {
  console.log(`\n— error จากหน้าเว็บ (${errors.length}) —`);
  for (const e of errors.slice(0, 15)) console.log(`  ${e}`);
}
if (failedReqs.length) {
  console.log(`\n— request ที่ล้ม (${failedReqs.length}) —`);
  for (const r of failedReqs.slice(0, 15)) console.log(`  ${r}`);
}

console.log(`\nภาพทั้งหมดอยู่ใน ${outDir}/ — เทียบ full-*.png กับ clip-*.png ว่าหน้าเปลี่ยนจริงไหม`);

if (headed) {
  console.log('เปิดค้างไว้ให้ดู — กด Ctrl+C เพื่อปิด');
  await new Promise(() => {});
}
await browser.close();
