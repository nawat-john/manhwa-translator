import { chromium } from 'playwright';
import assert from 'node:assert/strict';
import { mkdir, readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const extension = path.dirname(fileURLToPath(import.meta.url));
const browser = await chromium.launchPersistentContext('', {
  channel: 'chromium', headless: true, viewport: { width: 1360, height: 1000 },
  args: [`--disable-extensions-except=${extension}`, `--load-extension=${extension}`],
});
try {
  let submitted, createdJob;
  browser.on('request', request => {
    if (request.url() === 'http://127.0.0.1:4174/jobs' && request.method() === 'POST') submitted = request.postDataJSON();
  });
  browser.on('response', response => {
    if (response.url() === 'http://127.0.0.1:4174/jobs' && response.status() === 202) {
      response.json().then(job => { createdJob = job; }).catch(() => {});
    }
  });
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('https://comic.naver.com/webtoon/detail?titleId=845456&no=25&week=wed', { waitUntil: 'domcontentloaded', timeout: 60000 });
  const host = page.locator('[data-manga-lab="content_image_1"]');
  await host.waitFor({ timeout: 30000 });
  assert.equal(await page.locator('[data-manga-lab]').count(), 86);
  const image = page.locator('#content_image_1');
  await image.scrollIntoViewIfNeeded();
  await image.evaluate(image => image.decode());
  const source = await image.getAttribute('src');
  const sourceSet = await image.getAttribute('srcset');
  await host.getByRole('button').click();
  assert.equal(await host.getByRole('button').isDisabled(), true);
  await page.waitForFunction(() => {
    const host = document.querySelector('[data-manga-lab="content_image_1"]');
    return host && !host.shadowRoot.querySelector('button').disabled;
  }, null, { timeout: 15 * 60 * 1000, polling: 1000 });
  console.log('Button:', await host.getByRole('button').textContent());
  console.log('Status:', await host.locator('span').textContent());
  assert.match(await image.getAttribute('src'), /^data:image\/png;base64,/);
  assert.equal(submitted.urls.length, 86);
  assert.equal(submitted.index, 1);
  const context = JSON.parse(await readFile(path.resolve(extension, '../translator/work/extension', createdJob.id, 'context.json'), 'utf8'));
  assert.deepEqual(context.input_files, ['0000.img', '0001.img', '0002.img']);
  assert.equal(context.page_map.pages.length, 1);
  assert.ok(context.page_map.start < context.top && context.page_map.end > context.bottom);
  assert.deepEqual(await image.evaluate(image => [image.naturalWidth, image.naturalHeight]), [690, 1600]);
  await host.getByRole('button', { name: 'ดูต้นฉบับ' }).click();
  assert.equal(await image.getAttribute('src'), source);
  assert.equal(await image.getAttribute('srcset'), sourceSet);
  await host.getByRole('button', { name: 'ดูคำแปลอังกฤษ' }).click();
  assert.match(await image.getAttribute('src'), /^data:image\/png;base64,/);
  await page.setViewportSize({ width: 1000, height: 1000 });
  await image.scrollIntoViewIfNeeded();
  await page.waitForTimeout(300);
  const imageBox = await image.boundingBox(), buttonBox = await host.getByRole('button').boundingBox();
  assert.ok(buttonBox.x >= imageBox.x && buttonBox.x + buttonBox.width <= imageBox.x + imageBox.width + 1);
  await mkdir(path.resolve(extension, '../translator/work/extension/screenshots'), { recursive: true });
  await page.screenshot({ path: path.resolve(extension, '../translator/work/extension/screenshots/naver-translated.png') });
  await host.getByRole('button', { name: 'ดูต้นฉบับ' }).click();
  // An image element reused by the site must not keep a previous image's translation.
  await image.evaluate(image => { image.src = document.querySelector('#content_image_2').src; });
  await page.waitForTimeout(100);
  assert.equal(await host.getByRole('button').textContent(), 'แปลภาพนี้ · EN');
  const currentSource = await image.getAttribute('src');
  // Keep failure-path checks deterministic after the real GPU translation above.
  await browser.route('http://127.0.0.1:4174/jobs', route => route.fulfill({
    status: 503, contentType: 'application/json', body: JSON.stringify({ error: 'Test service unavailable' }),
  }));
  await host.getByRole('button').click();
  await page.waitForFunction(() => document.querySelector('[data-manga-lab="content_image_1"]').shadowRoot.querySelector('span').textContent.includes('Test service unavailable'));
  assert.equal(await image.getAttribute('src'), currentSource);
  await browser.unroute('http://127.0.0.1:4174/jobs');
  await browser.route('http://127.0.0.1:4174/jobs', route => route.fulfill({
    status: 202, contentType: 'application/json', body: JSON.stringify({ status: 'done', regions: 0 }),
  }));
  await host.getByRole('button').click();
  await page.waitForFunction(() => document.querySelector('[data-manga-lab="content_image_1"]').shadowRoot.querySelector('span').textContent.includes('ไม่พบข้อความ'));
  assert.equal(await image.getAttribute('src'), currentSource);
  await page.evaluate(() => {
    const image = document.createElement('img'); image.id = 'content_image_999';
    image.src = document.querySelector('#content_image_0').src; document.body.append(image);
  });
  await page.locator('[data-manga-lab="content_image_999"]').waitFor();
  assert.equal(await page.locator('[data-manga-lab="content_image_999"] button').count(), 1);
  assert.equal(errors.length, 0, errors.join('\n'));
  console.log('Neighbour stitching/whitespace split and projection verified; real translation, toggle, resizing, source invalidation, lazy images, failure and no-text handling passed.');
} finally { await browser.close(); }
