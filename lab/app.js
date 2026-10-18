const $ = id => document.getElementById(id);
let pages = [], selected = 0, busy = false, lastFinished = 0;
async function api(url, options) {
  const res = await fetch(url, options);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || 'เกิดข้อผิดพลาด');
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
    status.textContent = page.translated ? 'มีผลแปล' : 'รอแปล';
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
  if (!page) { $('title').textContent = 'ยังไม่มีภาพ'; $('translate').disabled = true; return; }
  $('title').textContent = `หน้า ${page.name.slice(0, 4)}`;
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
  $('translate').textContent = busy ? 'กำลังแปล…' : page.translated ? 'แปลหน้านี้ใหม่ ↗' : 'แปลหน้านี้ ↗';
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
  $('message').textContent = 'กำลังเริ่มโมเดลแปลภาษา…';
  try { await api(`/api/translate?page=${pages[selected].name}`, { method: 'POST' }); await poll(); }
  catch (error) { busy = false; show(); $('message').textContent = error.message; }
};
async function poll() {
  try {
    const job = await api('/api/job');
    busy = job.status === 'running';
    $('translate').disabled = busy || !pages.length;
    $('log').textContent = job.log || 'ยังไม่มีงานแปลในรอบนี้';
    if (busy) {
      $('translate').textContent = 'กำลังแปล…';
      const elapsed = Math.round((Date.now() - (job.started || Date.now())) / 1000);
      $('message').textContent = `กำลังแปล ${job.page} · ${elapsed} วินาที · สามารถดูหน้าอื่นระหว่างรอได้`;
    } else if (job.finished && job.finished !== lastFinished) {
      lastFinished = job.finished;
      pages = await api('/api/pages'); show();
      $('message').textContent = job.status === 'done' ? `แปล ${job.page} เสร็จแล้ว · ตรวจความพอดีของข้อความในบอลลูน` : `แปล ${job.page} ไม่สำเร็จ — เปิดบันทึกด้านล่างเพื่อดูสาเหตุ`;
    }
  } catch (error) { $('message').textContent = `เชื่อมต่อเซิร์ฟเวอร์ไม่ได้: ${error.message}`; }
}
for (const id of ['original', 'translated']) $(id).onerror = () => { $('message').textContent = 'โหลดภาพไม่สำเร็จ ลองเลือกหน้าอีกครั้ง'; };
async function init() {
  try {
    pages = await api('/api/pages'); show();
    $('message').textContent = pages.length ? 'พร้อมตรวจภาพ · ผลแปลเดิมจะถูกเก็บไว้เมื่อสั่งแปลใหม่' : 'ยังไม่มีภาพ กรุณารัน split_pages.py ก่อน';
    await poll();
    setInterval(poll, 1500);
  } catch (error) { $('message').textContent = error.message; $('translate').disabled = true; }
}
init();
