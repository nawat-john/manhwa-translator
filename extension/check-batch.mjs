import assert from 'node:assert/strict';
import path from 'node:path';
import { chromium } from 'playwright';

const extension = path.resolve('extension');
const browser = await chromium.launchPersistentContext('', {
  channel: 'chromium', headless: true,
  args: [`--disable-extensions-except=${extension}`, `--load-extension=${extension}`],
});
try {
  const png = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=';
  const urls = Array.from({ length: 4 }, (_, i) => `https://image-comic.pstatic.net/webtoon/845456/25/${i}.png`);
  await browser.route('https://comic.naver.com/**', route => route.fulfill({ contentType: 'text/html', body:
    `<style>img{display:block;width:600px;height:200px}</style>${urls.map((url, i) => `<img id="content_image_${i}" src="${url}">`).join('')}` }));
  await browser.route('https://image-comic.pstatic.net/**', route => route.fulfill({ contentType: 'image/png', body: Buffer.from(png, 'base64') }));
  const submitted = [];
  let current, failure = false;
  const id = '11111111-1111-4111-8111-111111111111';
  await browser.route('http://127.0.0.1:4174/**', async route => {
    const req = route.request();
    let response;
    if (req.method() === 'POST') {
      assert.equal(current, undefined, 'jobs must run sequentially');
      const body = req.postDataJSON();
      assert.deepEqual(body.urls, urls, 'always send original URLs');
      submitted.push(body.index);
      if (failure) return route.fulfill({ status: 503, json: { error: 'test unavailable' } });
      current = body.index;
      response = { id, status: 'running' };
    } else if (req.url().endsWith('/result')) {
      response = { image: `data:image/png;base64,${png}` };
      current = undefined;
    } else {
      response = { id, status: 'done', regions: current === 1 ? 0 : 1 };
      if (current === 1) current = undefined;
    }
    await route.fulfill({ json: response });
  });
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('https://comic.naver.com/webtoon/detail?titleId=845456&no=25');
  const all = page.locator('[data-manga-lab-toolbar] button');
  const status = page.locator('[data-manga-lab-toolbar] span');
  const single = i => page.locator(`[data-manga-lab="content_image_${i}"] button`);
  await single(0).click();
  assert.equal(await all.isDisabled(), true, 'batch cannot overlap a single translation');
  await page.waitForFunction(() => !document.querySelector('[data-manga-lab-toolbar]').shadowRoot.querySelector('button').disabled);
  await all.click();
  await page.waitForFunction(() => document.querySelector('[data-manga-lab="content_image_1"]').shadowRoot.querySelector('button').textContent === 'Translating…');
  await all.click();
  await page.waitForFunction(() => document.querySelector('[data-manga-lab-toolbar]').shadowRoot.querySelector('span').textContent.startsWith('Stopped'));
  assert.deepEqual(submitted, [0, 1], 'stop finishes current image without starting the next');
  assert.equal(await page.locator('#content_image_1').getAttribute('src'), urls[1]);
  failure = true;
  await all.click();
  await page.waitForFunction(() => document.querySelector('[data-manga-lab-toolbar]').shadowRoot.querySelector('span').textContent.includes('test unavailable'));
  assert.deepEqual(submitted, [0, 1, 2], 'skip translated and no-text images; stop on errors');
  failure = false;
  await all.click();
  await page.waitForFunction(() => document.querySelector('[data-manga-lab-toolbar]').shadowRoot.querySelector('span').textContent.startsWith('Done'));
  assert.deepEqual(submitted, [0, 1, 2, 2, 3]);
  assert.match(await status.textContent(), /4\/4/);
  await single(2).click();
  assert.equal(await page.locator('#content_image_2').getAttribute('src'), urls[2]);
  await all.click();
  await page.waitForFunction(() => document.querySelector('[data-manga-lab-toolbar]').shadowRoot.querySelector('span').textContent.startsWith('Done'));
  assert.match(await page.locator('#content_image_2').getAttribute('src'), /^data:image/);
  assert.equal(submitted.length, 5, 'reuse completed results');
  assert.deepEqual(errors, []);
  console.log('PASS: single/batch locking, sequential order, stop/resume, no-text, error/retry, original URLs, cached results and toggling');
} finally {
  await browser.close();
}
