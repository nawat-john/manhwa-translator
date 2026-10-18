import http from 'node:http';
import { randomBytes, randomUUID, timingSafeEqual } from 'node:crypto';
import { mkdir, readFile, writeFile, rename, stat, open } from 'node:fs/promises';
import { spawn } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const translator = path.resolve(here, '../translator');
const defaultWork = path.join(translator, 'work/extension');
const maxBytes = 20 * 1024 * 1024;
const idPattern = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;

export function validImageURL(value) {
  try {
    const url = new URL(value);
    return url.protocol === 'https:' && url.hostname === 'image-comic.pstatic.net' && !url.port
      && !url.username && !url.password && /^\/webtoon\/\d+\/\d+\//.test(url.pathname);
  } catch { return false; }
}
export function validEpisodeRequest(body) {
  if (!Array.isArray(body?.urls) || body.urls.length < 1 || body.urls.length > 300
      || !Number.isInteger(body.index) || body.index < 0 || body.index >= body.urls.length
      || new Set(body.urls).size !== body.urls.length || !body.urls.every(validImageURL)) return false;
  const episode = new URL(body.urls[body.index]).pathname.split('/').slice(0, 4).join('/');
  return body.urls.every(url => new URL(url).pathname.split('/').slice(0, 4).join('/') === episode);
}
async function save(file, data) {
  await writeFile(file + '.tmp', JSON.stringify(data, null, 2));
  await rename(file + '.tmp', file);
}
function json(res, code, data) {
  res.writeHead(code, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' });
  res.end(JSON.stringify(data));
}
async function boundedBody(stream, limit) {
  let size = 0;
  const chunks = [];
  for await (const chunk of stream) {
    size += chunk.length;
    if (size > limit) throw new Error('Data exceeds the supported size limit');
    chunks.push(Buffer.from(chunk));
  }
  return Buffer.concat(chunks);
}

async function runTranslation(request, directory, progress, signal) {
  await writeFile(path.join(directory, 'request.json'), JSON.stringify(request));
  await progress('Joining adjacent images and splitting at whitespace → translating into English');
  const log = await open(path.join(directory, 'worker.log'), 'w');
  // shortcut: a fresh worker per image; keep models loaded when cold-start latency becomes a bottleneck.
  try {
    await new Promise((resolve, reject) => {
      signal.throwIfAborted();
      const child = spawn(path.join(translator, '.venv/Scripts/python.exe'),
        ['-u', path.join(translator, 'translate_webtoon.py'), directory], {
          cwd: translator, windowsHide: true,
          env: { ...process.env, PYTHONIOENCODING: 'utf-8', HF_HOME: path.join(translator, 'hf-cache') },
          stdio: ['ignore', log.fd, log.fd],
        });
      const stop = () => {
        // Windows venv Python launches a child: stop the owned process tree, not only its launcher.
        if (process.platform === 'win32' && child.pid) {
          spawn('taskkill', ['/PID', String(child.pid), '/T', '/F'], { windowsHide: true, stdio: 'ignore' })
            .on('error', () => child.kill());
        } else child.kill();
      };
      signal.addEventListener('abort', stop, { once: true });
      child.once('error', reject);
      child.once('close', code => {
        signal.removeEventListener('abort', stop);
        if (signal.aborted) reject(new Error('Translation stopped or timed out. Please try again'));
        else if (code === 0) resolve();
        else reject(new Error('Translation failed. See this job’s worker.log for details'));
      });
    });
  } finally { await log.close(); }
  const summary = JSON.parse(await readFile(path.join(directory, 'result.json'), 'utf8'));
  if (!Number.isInteger(summary.regions) || summary.regions < 0) throw new Error('Incomplete translation result');
  const result = path.join(directory, 'source.png');
  if ((await stat(result)).size > maxBytes) throw new Error('The output image exceeds 20 MiB');
  return summary;
}

export function createServer({ token, work = defaultWork, run = runTranslation } = {}) {
  if (!token || token.length < 32) throw new Error('A local authentication token is required');
  let active = null;
  const jobs = new Map();
  const abort = new AbortController();
  const server = http.createServer(async (req, res) => {
    try {
      if (req.headers.host !== `127.0.0.1:${req.socket.localPort}`) return json(res, 403, { error: 'Invalid host' });
      const supplied = Buffer.from(req.headers.authorization || '');
      const expected = Buffer.from(`Bearer ${token}`);
      if (supplied.length !== expected.length || !timingSafeEqual(supplied, expected)) return json(res, 401, { error: 'Start the translation service and reload the extension to connect to this machine' });
      if (req.headers.origin && !/^chrome-extension:\/\/[a-p]{32}$/.test(req.headers.origin)) return json(res, 403, { error: 'Origin rejected' });
      const url = new URL(req.url, 'http://127.0.0.1');
      if (req.method === 'POST' && url.pathname === '/jobs') {
        if (active) return json(res, 409, { error: 'Another image is being translated. Please wait for it to finish and try again' });
        let body;
        try { body = JSON.parse((await boundedBody(req, 256 * 1024)).toString('utf8')); }
        catch { return json(res, 400, { error: 'Invalid request body' }); }
        if (!validEpisodeRequest(body)) return json(res, 400, { error: 'Images must be in order and from the same Naver episode. Please reload the extension' });
        if (active) return json(res, 409, { error: 'Another image is being translated. Please wait and try again' });
        const id = randomUUID();
        active = id;
        const directory = path.join(work, id);
        const job = { id, status: 'running', message: 'Starting translation', url: body.urls[body.index], started: Date.now() };
        try {
          await mkdir(directory, { recursive: true });
          await save(path.join(directory, 'job.json'), job);
          jobs.set(id, job);
        } catch (error) { active = null; throw error; }
        json(res, 202, job);
        const progress = async message => { job.message = message; await save(path.join(directory, 'job.json'), job); };
        (async () => {
          let finished;
          try {
            const result = await run({ urls: body.urls, index: body.index }, directory, progress, AbortSignal.any([abort.signal, AbortSignal.timeout(14 * 60 * 1000)]));
            finished = { ...job, ...result, status: 'done', message: result.regions ? 'Translation complete' : 'No readable Korean text found' };
          } catch (error) { finished = { ...job, status: 'error', message: error.message }; }
          finished.finished = Date.now();
          try {
            await save(path.join(directory, 'job.json'), finished);
            jobs.set(id, finished);
          } catch (error) {
            jobs.set(id, { ...job, status: 'error', message: 'Could not save the translation result. Please check disk space' });
            throw error;
          }
          finally { active = null; }
        })().catch(error => console.error('Job save failed:', error.message));
        return;
      }
      const match = /^\/jobs\/([^/]+)(\/result)?$/.exec(url.pathname);
      if (req.method !== 'GET' || !match || !idPattern.test(match[1])) return json(res, 404, { error: 'Not found' });
      const directory = path.join(work, match[1]);
      let job;
      try { job = jobs.get(match[1]) || JSON.parse(await readFile(path.join(directory, 'job.json'), 'utf8')); }
      catch (error) { if (error.code === 'ENOENT') return json(res, 404, { error: 'Translation job not found' }); throw error; }
      if (job.status === 'running' && active !== job.id) {
        job.status = 'error'; job.message = 'The translation service stopped before the job finished. Please translate again';
      }
      if (!match[2]) return json(res, 200, job);
      if (job.status !== 'done') return json(res, 409, { error: 'The translation result is not ready' });
      const file = path.join(directory, 'source.png');
      if ((await stat(file)).size > maxBytes) return json(res, 413, { error: 'The result is too large' });
      return json(res, 200, { image: `data:image/png;base64,${(await readFile(file)).toString('base64')}` });
    } catch (error) {
      if (!res.headersSent) json(res, 500, { error: error.message });
      else res.destroy();
    }
  });
  server.on('close', () => abort.abort());
  return server;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  await mkdir(defaultWork, { recursive: true });
  const tokenFile = path.join(defaultWork, 'token');
  let token;
  try { token = (await readFile(tokenFile, 'utf8')).trim(); }
  catch (error) {
    if (error.code !== 'ENOENT') throw error;
    token = randomBytes(32).toString('hex'); await writeFile(tokenFile, token, { flag: 'wx' });
  }
  await writeFile(path.join(here, 'config.local.js'), `// Generated locally. Do not share this file.\nglobalThis.MANGA_LAB_TOKEN = ${JSON.stringify(token)};\n`);
  const server = createServer({ token });
  server.listen(4174, '127.0.0.1', () => console.log('Naver translator ready on 127.0.0.1:4174. Load the extension/ folder in Chrome.'));
  server.on('error', error => { console.error(error.message); process.exitCode = 1; });
  process.on('SIGINT', () => { server.close(); server.closeAllConnections(); });
}
