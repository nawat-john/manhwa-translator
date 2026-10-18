import http from 'node:http';
import { readdir, stat, mkdir, rename, rm } from 'node:fs/promises';
import { createReadStream } from 'node:fs';
import { spawn } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const translator = path.resolve(here, '../translator');
const pages = path.join(translator, 'work/pages');
const output = path.join(translator, 'work/lab');
const originalOutput = path.join(translator, 'work/out');
const upstream = path.join(translator, 'manga-image-translator');
export const validPage = name => /^\d{4}\.png$/.test(name);
async function exists(file) { try { return (await stat(file)).isFile(); } catch { return false; } }
async function resultPath(name) {
  const fresh = path.join(output, name);
  return await exists(fresh) ? fresh : path.join(originalOutput, name);
}

// shortcut: one in-memory job, add a persistent queue when serving multiple users.
let job = { status: 'idle', log: '' };
let worker;
function json(res, code, value) {
  res.writeHead(code, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
  res.end(JSON.stringify(value));
}
async function translate(name) {
  await mkdir(output, { recursive: true });
  const pending = path.join(output, `${name}.pending.png`);
  await rm(pending, { force: true });
  const args = ['-m', 'manga_translator', 'local', '-i', path.join(pages, name),
    '-o', pending, '-f', 'png', '--config-file', path.join(translator, 'config.json'),
    '--model-dir', path.join(translator, 'models'), '--font-path', path.join(upstream, 'fonts/anime_ace.ttf'),
    '--attempts', '1', '--use-gpu'];
  job = { status: 'running', page: name, started: Date.now(), log: '' };
  worker = spawn(path.join(translator, '.venv/Scripts/python.exe'), args, {
    cwd: upstream, windowsHide: true,
    env: { ...process.env, PYTHONPATH: upstream, PYTHONUNBUFFERED: '1', PYTHONIOENCODING: 'utf-8',
      HF_HOME: path.join(translator, 'hf-cache'), TORCH_HOME: path.join(translator, 'models/torch') },
  });
  const append = data => { job.log = (job.log + data.toString()).slice(-16000); };
  worker.stdout.on('data', append);
  worker.stderr.on('data', append);
  worker.on('error', error => { append(error.message); });
  worker.on('close', async code => {
    try {
      if (code !== 0 || !await exists(pending)) throw new Error(`Translation failed (exit ${code}). See log.`);
      await rename(pending, path.join(output, name));
      job.status = 'done';
    } catch (error) { job.status = 'error'; append(`\n${error.message}`); }
    job.finished = Date.now();
    worker = null;
  });
}

export function createServer() {
  return http.createServer(async (req, res) => {
    try {
      const expectedHost = `127.0.0.1:${req.socket.localPort}`;
      if (req.headers.host !== expectedHost) return json(res, 403, { error: 'Use the local 127.0.0.1 address.' });
      const url = new URL(req.url, `http://${expectedHost}`);
      res.setHeader('X-Content-Type-Options', 'nosniff');
      res.setHeader('Content-Security-Policy', "default-src 'self'; img-src 'self'; style-src 'self'; script-src 'self'; frame-ancestors 'none'");
      if (req.method === 'POST' && url.pathname === '/api/translate') {
        if (req.headers.origin !== `http://${expectedHost}`) return json(res, 403, { error: 'Origin rejected' });
        const name = url.searchParams.get('page') || '';
        if (!validPage(name) || !await exists(path.join(pages, name))) return json(res, 400, { error: 'Unknown page' });
        if (job.status === 'running') return json(res, 409, { error: 'A translation is already running' });
        // Reserve before awaiting filesystem work so two requests cannot start two GPU workers.
        job = { status: 'running', page: name, log: '' };
        try { await translate(name); } catch (error) { job.status = 'error'; throw error; }
        return json(res, 202, job);
      }
      if (req.method !== 'GET') return json(res, 405, { error: 'Method not allowed' });
      if (url.pathname === '/api/job') return json(res, 200, job);
      if (url.pathname === '/api/pages') {
        const names = (await readdir(pages)).filter(validPage).sort();
        const entries = await Promise.all(names.map(async name => ({ name, translated: await exists(await resultPath(name)) })));
        return json(res, 200, entries);
      }
      let file;
      let type;
      const match = /^\/image\/(original|translated)\/(\d{4}\.png)$/.exec(url.pathname);
      if (match) {
        file = match[1] === 'original' ? path.join(pages, match[2]) : await resultPath(match[2]);
        type = 'image/png';
      } else {
        const assets = { '/': ['index.html', 'text/html; charset=utf-8'], '/app.js': ['app.js', 'text/javascript; charset=utf-8'], '/style.css': ['style.css', 'text/css; charset=utf-8'] };
        const asset = Object.hasOwn(assets, url.pathname) ? assets[url.pathname] : null;
        if (!asset) return json(res, 404, { error: 'Not found' });
        file = path.join(here, asset[0]); type = asset[1];
      }
      if (!await exists(file)) return json(res, 404, { error: 'File not found' });
      res.writeHead(200, { 'Content-Type': type, 'Cache-Control': 'no-store' });
      createReadStream(file).on('error', () => res.destroy()).pipe(res);
    } catch (error) { json(res, 500, { error: error.message }); }
  });
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const server = createServer();
  server.listen(4173, '127.0.0.1', () => console.log('Manga Lab: http://127.0.0.1:4173'));
  server.on('error', error => { console.error(error.message); process.exitCode = 1; });
  process.on('SIGINT', () => { worker?.kill(); server.close(); });
}
