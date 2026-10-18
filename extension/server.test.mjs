import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, readFile, writeFile } from 'node:fs/promises';
import { randomUUID } from 'node:crypto';
import os from 'node:os';
import path from 'node:path';
import http from 'node:http';
import { createServer, validImageURL, validEpisodeRequest } from './server.mjs';

const imageURL = 'https://image-comic.pstatic.net/webtoon/845456/25/test.jpg';
const token = 'a'.repeat(64);
const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

test('episode context must be unique, bounded, same episode and include the selected index', () => {
  const request = { urls: [imageURL, imageURL.replace('test.jpg', 'next.jpg')], index: 1 };
  assert.ok(validEpisodeRequest(request));
  for (const invalid of [{ urls: [imageURL, imageURL], index: 0 },
    { ...request, index: -1 }, { ...request, index: 2 }, { ...request, index: true },
    { urls: [imageURL, imageURL.replace('/25/', '/26/')], index: 0 },
    { urls: [imageURL, 'http://127.0.0.1/private'], index: 0 }, { url: imageURL },
    { urls: Array.from({ length: 301 }, (_, i) => imageURL + i), index: 0 }]) {
    assert.equal(validEpisodeRequest(invalid), false);
  }
});

test('image URL allowlist rejects credentials, other hosts, protocols and paths', () => {
  assert.equal(validImageURL(imageURL), true);
  for (const url of ['http://127.0.0.1/image.jpg', 'https://image-comic.pstatic.net.evil.com/webtoon/1/2/x.jpg',
    'file:///C:/secret', 'https://image-comic.pstatic.net/other/1.jpg',
    'https://user:password@image-comic.pstatic.net/webtoon/1/2/x', 'https://image-comic.pstatic.net:444/webtoon/1/2/x']) {
    assert.equal(validImageURL(url), false, url);
  }
});

test('authenticated job lifecycle, busy state, no-text, errors, restart and result isolation', async t => {
  const work = await mkdtemp(path.join(os.tmpdir(), 'manga-extension-test-'));
  let release;
  let calls = 0;
  const run = async (url, directory, progress) => {
    calls++;
    await progress('test processing');
    await new Promise(resolve => { release = resolve; });
    if (calls === 2) throw new Error('test worker failure');
    await writeFile(path.join(directory, 'source.png'), Buffer.from('test-result'));
    return { regions: calls === 3 ? 0 : 1 };
  };
  const server = createServer({ token, work, run });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  t.after(() => new Promise(resolve => server.close(resolve)));
  const base = `http://127.0.0.1:${server.address().port}`;
  const post = (body = { urls: [imageURL], index: 0 }, overrides = headers) => fetch(base + '/jobs', { method: 'POST', headers: overrides, body: JSON.stringify(body) });
  assert.equal((await post(undefined, {})).status, 401);
  assert.equal((await post(undefined, { ...headers, Origin: 'https://comic.naver.com' })).status, 403);
  assert.equal((await post({ url: 'http://127.0.0.1/private' })).status, 400);
  assert.equal((await fetch(base + '/jobs', { method: 'POST', headers, body: '{' })).status, 400);
  const hostStatus = await new Promise((resolve, reject) => {
    http.get(base + '/jobs', { headers: { ...headers, Host: 'evil.example' } }, res => { res.resume(); resolve(res.statusCode); }).on('error', reject);
  });
  assert.equal(hostStatus, 403);
  const first = await post();
  assert.equal(first.status, 202);
  const firstJob = await first.json();
  await new Promise(resolve => setTimeout(resolve, 20));
  assert.equal((await post()).status, 409);
  assert.equal((await fetch(`${base}/jobs/${firstJob.id}/result`, { headers })).status, 409);
  assert.equal((await fetch(`${base}/jobs/${firstJob.id}`, { headers: {} })).status, 401);
  release();
  const wait = async id => {
    for (let i = 0; i < 100; i++) {
      const job = await (await fetch(`${base}/jobs/${id}`, { headers })).json();
      if (job.status !== 'running') return job;
      await new Promise(resolve => setTimeout(resolve, 10));
    }
    throw new Error('Test job timed out');
  };
  assert.equal((await wait(firstJob.id)).status, 'done');
  const result = await (await fetch(`${base}/jobs/${firstJob.id}/result`, { headers })).json();
  assert.equal(Buffer.from(result.image.split(',')[1], 'base64').toString(), 'test-result');
  const second = await (await post()).json();
  await new Promise(resolve => setTimeout(resolve, 20)); release();
  assert.equal((await wait(second.id)).status, 'error');
  const third = await (await post()).json();
  await new Promise(resolve => setTimeout(resolve, 20)); release();
  assert.equal((await wait(third.id)).regions, 0);
  const stored = JSON.parse(await readFile(path.join(work, firstJob.id, 'job.json'), 'utf8'));
  const interrupted = randomUUID();
  await mkdir(path.join(work, interrupted));
  await writeFile(path.join(work, interrupted, 'job.json'), JSON.stringify({ ...stored, id: interrupted, status: 'running' }));
  assert.equal((await wait(interrupted)).status, 'error');
  assert.equal((await fetch(base + '/jobs/../../token', { headers })).status, 404);
  assert.equal((await fetch(base + '/token', { headers })).status, 404);
});
