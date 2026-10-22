// Download the original images from the requested Korean test episode.
import { chromium } from 'playwright';
import { mkdir, writeFile, readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';

const source = 'https://comic.naver.com/webtoon/detail?titleId=845456&no=25&week=wed';
const directory = fileURLToPath(new URL('../samples/naver-845456-25/', import.meta.url));
const browser = await chromium.launch({ headless: true });
try {
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto(source, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForSelector('img#content_image_0', { state: 'attached', timeout: 30000 });
  const images = await page.locator('img[id^="content_image_"]').evaluateAll(elements =>
    elements.filter(image => /^content_image_\d+$/.test(image.id)).map(image => ({
      id: image.id,
      index: Number(image.id.slice('content_image_'.length)),
      url: new URL(image.getAttribute('data-src') || image.getAttribute('src'), location.href).href,
    })).sort((a, b) => a.index - b.index));
  assert.ok(images.length > 0, 'No content images found');
  images.forEach((image, index) => {
    assert.equal(image.index, index, 'Missing or duplicate image index');
    assert.equal(new URL(image.url).protocol, 'https:');
  });
  console.log(`Found ${images.length} images: ${images[0].id} through ${images.at(-1).id}`);
  await mkdir(directory, { recursive: true });
  const manifest = { source, title: await page.title(), downloadedAt: new Date().toISOString(), images: [] };
  for (const image of images) {
    const response = await context.request.get(image.url, { headers: { Referer: source }, timeout: 60000 });
    assert.ok(response.ok(), `${image.id}: HTTP ${response.status()}`);
    const mime = response.headers()['content-type']?.split(';')[0];
    const extension = { 'image/jpeg': 'jpg', 'image/png': 'png', 'image/webp': 'webp', 'image/gif': 'gif' }[mime];
    assert.ok(extension, `${image.id}: unexpected content type ${mime}`);
    const bytes = await response.body();
    assert.ok(bytes.length > 0, `${image.id}: empty image`);
    const filename = `${String(image.index).padStart(4, '0')}.${extension}`;
    const destination = path.join(directory, filename);
    try { await writeFile(destination, bytes, { flag: 'wx' }); }
    catch (error) {
      if (error.code !== 'EEXIST') throw error;
      assert.ok((await readFile(destination)).equals(bytes), `${filename} already exists with different content`);
    }
    manifest.images.push({ ...image, filename, bytes: bytes.length, sha256: createHash('sha256').update(bytes).digest('hex') });
    console.log(`${image.id} -> ${filename} (${bytes.length} bytes)`);
    await response.dispose();
  }
  await writeFile(path.join(directory, 'manifest.json'), JSON.stringify(manifest, null, 2) + '\n');
  console.log(`Saved ${manifest.images.length} originals to ${directory}`);
} finally { await browser.close(); }
