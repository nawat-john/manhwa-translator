import { chromium } from 'playwright';
import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
import { setTimeout } from 'node:timers/promises';

const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('http://127.0.0.1:4173');
  await page.locator('#pages button').first().waitFor();
  await page.locator('#search').fill('0010');
  await page.locator('#pages button').click();
  await page.waitForFunction(() => ['original', 'translated'].every(id => {
    const image = document.getElementById(id); return image.complete && image.naturalWidth > 0;
  }));
  assert.match(await page.locator('#title').textContent(), /0010/);
  await page.locator('button[data-mode="original"]').click();
  assert.equal(await page.locator('#translated-panel').isVisible(), false);
  await page.locator('button[data-mode="compare"]').click();
  assert.equal(await page.locator('#translated-panel').isVisible(), true);
  await mkdir('lab/screenshots', { recursive: true });
  await page.screenshot({ path: 'lab/screenshots/desktop.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: 'lab/screenshots/mobile.png', fullPage: true });
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  assert.deepEqual(errors, []);
  console.log('Desktop/mobile, navigation, image loading and comparison modes passed.');
  if (process.argv.includes('--translate')) {
    let job = await (await fetch('http://127.0.0.1:4173/api/job')).json();
    if (job.status !== 'running') await page.locator('#translate').click();
    const deadline = Date.now() + 600000;
    do {
      await setTimeout(2000);
      job = await (await fetch('http://127.0.0.1:4173/api/job')).json();
    } while (job.status === 'running' && Date.now() < deadline);
    console.log(JSON.stringify(job));
    assert.equal(job.status, 'done');
  }
} finally { await browser.close(); }
