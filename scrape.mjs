// ตัว scraper — วนทุก URL ใน config.urls แล้วแคปตามกรอบใน box.json
//
//   node scrape.mjs            // ทุก URL
//   node scrape.mjs 5 12       // เฉพาะลำดับที่ 5–12 ในลิสต์
import { chromium } from 'playwright';
import { mkdir, readFile, writeFile, access } from 'node:fs/promises';
import path from 'node:path';
import cfg from './config.mjs';

const box = await readFile('box.json', 'utf8')
  .then(JSON.parse)
  .catch(() => {
    console.error('ไม่เจอ box.json — รัน `node pick-box.mjs` ก่อน');
    process.exit(1);
  });

if (!cfg.urls.length) {
  console.error('config.urls ว่าง — ใส่ URL ลงไป หรือใช้ `node scrape-click.mjs` แทน');
  process.exit(1);
}

const from = Number(process.argv[2] ?? 1);
const to = Number(process.argv[3] ?? cfg.urls.length);

const jobs = cfg.urls
  .map((url, i) => ({ n: i + 1, url }))
  .filter(({ n }) => n >= from && n <= to);

const exists = (p) =>
  access(p).then(
    () => true,
    () => false,
  );

async function autoScroll(page) {
  await page.evaluate(async () => {
    const step = window.innerHeight * 0.8;
    for (let y = 0; y < document.body.scrollHeight; y += step) {
      window.scrollTo(0, y);
      await new Promise((r) => setTimeout(r, 120));
    }
    window.scrollTo(0, 0);
    await new Promise((r) => setTimeout(r, 150));
  });
}

async function capture(page, url, out) {
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
  if (cfg.waitFor) {
    await page.waitForSelector(cfg.waitFor, { timeout: 15000 }).catch(() => {});
  }
  if (cfg.scrollToBottom) await autoScroll(page);
  await page.waitForTimeout(cfg.settleMs);

  if (box.selector && !box.clip) {
    // โหมด selector — กรอบขยับตามอิลิเมนต์เอง ทนกว่าเวลาเลย์เอาต์เปลี่ยน
    await page.locator(box.selector).first().screenshot({ path: out });
  } else {
    // โหมดพิกัด — clip เทียบกับทั้งหน้าเพจ เพราะใส่ fullPage: true
    await page.screenshot({ path: out, fullPage: true, clip: box.clip });
  }
}

await mkdir(cfg.outDir, { recursive: true });

const browser = await chromium.launch({ headless: cfg.headless });
const context = await browser.newContext({
  viewport: cfg.viewport,
  deviceScaleFactor: cfg.deviceScaleFactor,
});
const page = await context.newPage();

const failed = [];
for (const { n, url } of jobs) {
  const out = path.join(cfg.outDir, `${String(n).padStart(cfg.pad, '0')}.png`);
  if (!cfg.overwrite && (await exists(out))) {
    console.log(`ข้าม  ${out}`);
    continue;
  }

  let lastErr;
  for (let attempt = 1; attempt <= 2; attempt++) {
    try {
      await capture(page, url, out);
      console.log(`ได้   ${out}`);
      lastErr = null;
      break;
    } catch (err) {
      lastErr = err;
      console.warn(`พลาด (ครั้งที่ ${attempt}) หน้า ${n}: ${err.message.split('\n')[0]}`);
      await page.waitForTimeout(2000);
    }
  }
  if (lastErr) failed.push({ n, url, error: lastErr.message.split('\n')[0] });

  await page.waitForTimeout(cfg.politeDelayMs);
}

await browser.close();

if (failed.length) {
  await writeFile('failed.json', `${JSON.stringify(failed, null, 2)}\n`, 'utf8');
  console.log(`\nไม่สำเร็จ ${failed.length} หน้า — ดูรายละเอียดใน failed.json`);
} else {
  console.log('\nครบทุกหน้า');
}
