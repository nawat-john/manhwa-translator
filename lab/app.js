const $ = id => document.getElementById(id);
let pages = [], selected = 0, busy = false, lastFinished = 0;
async function api(url, options) {
  const res = await fetch(url, options);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || 'An error occurred');
  return data;
}
function list() {
  const query = $('search').value.trim();
  $('pages').replaceChildren();
  pages.forEach((page, index) => {
    if (!page.name.includes(query)) return;
    const button = document.createElement('button');
    button.className = index === selected ? 'active' : '';
    button.setAttribute('aria-current', index === selected ? 'page' : 'false');
    button.textContent = `▤  ${page.name.slice(0, 4)}`;
    const status = document.createElement('small');
    status.textContent = page.translated ? 'Translated' : 'Awaiting translation';
    button.append(status);
    button.onclick = () => { selected = index; show(); };
    $('pages').append(button);
  });
  $('count').textContent = pages.length;
  $('total').textContent = pages.length;
  $('completed').textContent = pages.filter(p => p.translated).length;
}
function show() {
  const page = pages[selected];
  if (!page) { $('title').textContent = 'No images yet'; $('translate').disabled = true; return; }
  $('title').textContent = `Page ${page.name.slice(0, 4)}`;
  $('page-status').textContent = `${page.name} · Japanese → English`;
  $('original').src = `/image/original/${page.name}`;
  const result = `/image/translated/${page.name}?v=${lastFinished}`;
  $('translated').hidden = !page.translated;
  $('empty').hidden = page.translated;
  if (page.translated) $('translated').src = result;
  else $('translated').removeAttribute('src');
  $('download').hidden = !page.translated;
  $('download').href = result;
  $('download').download = `${page.name.slice(0, 4)}-en.png`;
  $('previous').disabled = selected === 0;
  $('next').disabled = selected === pages.length - 1;
  $('translate').disabled = busy;
  $('translate').textContent = busy ? 'Translating…' : page.translated ? 'Retranslate page ↗' : 'Translate page ↗';
  list();
}
$('search').oninput = list;
$('previous').onclick = () => { selected--; show(); };
$('next').onclick = () => { selected++; show(); };
document.querySelectorAll('[data-mode]').forEach(button => {
  if (button.tagName !== 'BUTTON') return;
  button.onclick = () => {
    $('viewer').dataset.mode = button.dataset.mode;
    document.querySelectorAll('.tabs button').forEach(tab => tab.setAttribute('aria-pressed', String(tab === button)));
  };
});
$('translate').onclick = async () => {
  busy = true; show();
  $('message').textContent = 'Starting the translation model…';
  try { await api(`/api/translate?page=${pages[selected].name}`, { method: 'POST' }); await poll(); }
  catch (error) { busy = false; show(); $('message').textContent = error.message; }
};
async function poll() {
  try {
    const job = await api('/api/job');
    busy = job.status === 'running';
    $('translate').disabled = busy || !pages.length;
    $('log').textContent = job.log || 'No translation jobs in this session';
    if (busy) {
      $('translate').textContent = 'Translating…';
      const elapsed = Math.round((Date.now() - (job.started || Date.now())) / 1000);
      $('message').textContent = `Translating ${job.page} · ${elapsed} seconds · You can browse other pages while waiting`;
    } else if (job.finished && job.finished !== lastFinished) {
      lastFinished = job.finished;
      pages = await api('/api/pages'); show();
      $('message').textContent = job.status === 'done' ? `Translated ${job.page} · Check that the text fits inside the bubbles` : `Failed to translate ${job.page} — open the log below for details`;
    }
  } catch (error) { $('message').textContent = `Cannot connect to the server: ${error.message}`; }
}
for (const id of ['original', 'translated']) $(id).onerror = () => { $('message').textContent = 'Could not load the image. Try selecting the page again'; };
async function init() {
  try {
    pages = await api('/api/pages'); show();
    $('message').textContent = pages.length ? 'Ready for review · Previous results are preserved while retranslating' : 'No images yet. Please run split_pages.py first';
    await poll();
    setInterval(poll, 1500);
  } catch (error) { $('message').textContent = error.message; $('translate').disabled = true; }
}
init();
