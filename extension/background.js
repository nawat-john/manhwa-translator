importScripts('config.local.js');

const base = 'http://127.0.0.1:4174';
async function request(message) {
  let route, options = {};
  if (message.type === 'translate') {
    if (!Array.isArray(message.urls) || message.urls.length > 300 || !message.urls.length
        || !Number.isInteger(message.index) || message.index < 0 || message.index >= message.urls.length
        || !message.urls.every(value => {
          const image = new URL(value);
          return image.protocol === 'https:' && image.hostname === 'image-comic.pstatic.net' && image.pathname.startsWith('/webtoon/');
        })) {
      throw new Error('รองรับเฉพาะภาพเว็บตูน Naver');
    }
    route = '/jobs';
    options = { method: 'POST', body: JSON.stringify({ urls: message.urls, index: message.index }) };
  } else if (['status', 'result'].includes(message.type) && /^[a-f0-9-]{36}$/.test(message.id)) {
    route = `/jobs/${message.id}${message.type === 'result' ? '/result' : ''}`;
  } else {
    throw new Error('คำขอไม่ถูกต้อง');
  }
  let response;
  try {
    response = await fetch(base + route, { ...options, signal: AbortSignal.timeout(15000),
      headers: { Authorization: `Bearer ${globalThis.MANGA_LAB_TOKEN}`, 'Content-Type': 'application/json' } });
  } catch {
    throw new Error('ติดต่อบริการแปลไม่ได้ — เปิด npm run extension:serve แล้วลองใหม่');
  }
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'บริการแปลเกิดข้อผิดพลาด');
  return data;
}

chrome.runtime.onMessage.addListener((message, sender, respond) => {
  if (sender.id !== chrome.runtime.id || !sender.tab || !sender.url?.startsWith('https://comic.naver.com/webtoon/detail')) {
    respond({ error: 'ไม่อนุญาตให้เรียกจากหน้านี้' });
    return false;
  }
  request(message).then(respond, error => respond({ error: error.message }));
  return true;
});
