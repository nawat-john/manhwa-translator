import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { createServer, validPage } from './server.mjs';

test('page names cannot escape the image directory', () => {
  assert.ok(validPage('0001.png'));
  for (const name of ['../0001.png', '0001.png/..', '0001.png\n', 'config.json', 'C:\\0001.png']) assert.equal(validPage(name), false);
});

test('local API lists real images and rejects foreign writes and arbitrary files', async t => {
  const server = createServer();
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  t.after(() => new Promise(resolve => server.close(resolve)));
  const base = `http://127.0.0.1:${server.address().port}`;
  const response = await fetch(`${base}/api/pages`);
  assert.equal(response.status, 200);
  const pages = await response.json();
  assert.ok(pages.length > 0);
  assert.ok(pages.every(page => validPage(page.name) && typeof page.translated === 'boolean'));
  const image = await fetch(`${base}/image/original/${pages[0].name}`);
  assert.equal(image.headers.get('content-type'), 'image/png');
  assert.ok((await image.arrayBuffer()).byteLength > 0);
  assert.equal((await fetch(`${base}/api/translate?page=0001.png`, { method: 'POST', headers: { Origin: 'https://example.com' } })).status, 403);
  assert.equal((await fetch(`${base}/api/translate?page=../config.json`, { method: 'POST', headers: { Origin: base } })).status, 400);
  assert.equal((await fetch(`${base}/translator/config.json`)).status, 404);
  assert.equal((await fetch(`${base}/image/original/%2e%2e%2fconfig.json`)).status, 404);
  const foreignHostStatus = await new Promise((resolve, reject) => {
    http.get(`${base}/api/job`, { headers: { Host: 'attacker.example' } }, res => {
      res.resume(); resolve(res.statusCode);
    }).on('error', reject);
  });
  assert.equal(foreignHostStatus, 403);
});
