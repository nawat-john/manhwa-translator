(() => {
  const states = new Map();
  let scheduled = false;
  let busy = false;
  let batching = false;
  let stopRequested = false;
  const toolbar = document.createElement('div');
  toolbar.dataset.mangaLabToolbar = '';
  Object.assign(toolbar.style, { position: 'fixed', bottom: '16px', right: '16px', zIndex: '2147483001', maxWidth: 'calc(100vw - 32px)' });
  const controls = toolbar.attachShadow({ mode: 'open' });
  controls.innerHTML = `<style>:host{font:13px/1.5 system-ui,Tahoma,sans-serif}section{background:#fff;color:#22382b;padding:12px;border:1px solid #ccd8d0;border-radius:12px;box-shadow:0 3px 18px #0003;max-width:320px}button{font:inherit;background:#24583f;color:white;border:0;border-radius:8px;padding:9px 14px;cursor:pointer}button:disabled{opacity:.55;cursor:wait}button:focus-visible{outline:3px solid #e5b636;outline-offset:2px}span{display:block;margin-top:6px;overflow-wrap:anywhere}</style><section><button type="button">แปลทั้งหมด · EN</button><span role="status" aria-live="polite">แปลภาพในตอนนี้ตามลำดับ</span></section>`;
  const allButton = controls.querySelector('button');
  const progress = controls.querySelector('span');
  document.body.append(toolbar);
  function updateButtons() {
    allButton.disabled = batching ? stopRequested : busy || states.size === 0;
    for (const state of states.values()) state.button.disabled = (busy || batching) && !state.translated;
  }
  const episodeImages = () => [...document.querySelectorAll('img[id^="content_image_"]')]
    .filter(image => /^content_image_\d+$/.test(image.id))
    .sort((a, b) => Number(a.id.slice(14)) - Number(b.id.slice(14)));
  allButton.onclick = async event => {
    if (!event.isTrusted) return;
    if (batching) {
      stopRequested = true;
      allButton.textContent = 'กำลังรอภาพปัจจุบันเสร็จ…';
      updateButtons();
      return;
    }
    if (busy) return;
    const images = episodeImages();
    let completed = 0;
    batching = true; stopRequested = false;
    allButton.textContent = 'หยุดหลังภาพนี้';
    updateButtons();
    try {
      for (const image of images) {
        if (stopRequested) break;
        if (!image.isConnected) throw new Error('รายการภาพเปลี่ยน กรุณาลองใหม่');
        const state = states.get(image);
        progress.textContent = `กำลังแปล ${completed + 1}/${images.length} ภาพ`;
        if (state.translated) show(state, true);
        else if (state.noTextURL !== sourceURL(image)) await translate(state);
        completed++;
      }
      progress.textContent = `${stopRequested ? 'หยุดแล้ว' : 'เสร็จแล้ว'} · ตรวจแล้ว ${completed}/${images.length} ภาพ (ภาพที่ไม่มีข้อความคงต้นฉบับไว้)`;
    } catch (error) {
      progress.textContent = `หยุดที่ ${completed}/${images.length} ภาพ · ${error.message} · กดแปลทั้งหมดเพื่อทำต่อ`;
    } finally {
      batching = false;
      allButton.textContent = 'แปลทั้งหมด · EN';
      updateButtons();
    }
  };
  const sourceURL = image => image.currentSrc || image.src;
  const send = async message => {
    try {
      const response = await chrome.runtime.sendMessage(message);
      if (response.error) throw new Error(response.error);
      return response;
    } catch (error) {
      if (/context invalidated/i.test(error.message)) throw new Error('Extension ถูกโหลดใหม่ กรุณารีเฟรชหน้าเว็บ');
      throw error;
    }
  };

  function position() {
    scheduled = false;
    for (const [image, state] of states) {
      if (!image.isConnected) {
        state.host.remove(); resize.unobserve(image); states.delete(image); continue;
      }
      const box = image.getBoundingClientRect();
      state.host.hidden = box.width === 0 || box.height === 0;
      Object.assign(state.host.style, {
        left: `${window.scrollX + box.left + Math.max(0, box.width - 264)}px`,
        top: `${window.scrollY + box.top + 8}px`, width: `${Math.min(256, box.width)}px`,
      });
    }
    toolbar.hidden = states.size === 0;
    updateButtons();
  }
  function schedule() {
    if (!scheduled) { scheduled = true; requestAnimationFrame(position); }
  }
  const resize = new ResizeObserver(schedule);

  function show(state, translated) {
    const image = state.image;
    if (translated) {
      image.removeAttribute('srcset');
      image.src = state.translated;
    } else {
      image.setAttribute('src', state.src);
      if (state.srcset !== null) image.setAttribute('srcset', state.srcset);
      else image.removeAttribute('srcset');
    }
    state.showing = translated;
    state.expectedSrc = image.getAttribute('src');
    state.expectedSrcset = image.getAttribute('srcset');
    state.button.textContent = translated ? 'ดูต้นฉบับ' : 'ดูคำแปลอังกฤษ';
    state.button.setAttribute('aria-pressed', String(translated));
    state.status.textContent = translated ? 'KO → EN · คำแปลอัตโนมัติ' : 'ต้นฉบับภาษาเกาหลี';
    schedule();
  }

  function attach(image) {
    if (states.has(image) || !/^content_image_\d+$/.test(image.id)) return;
    const host = document.createElement('div');
    host.dataset.mangaLab = image.id;
    Object.assign(host.style, { position: 'absolute', zIndex: '2147483000', pointerEvents: 'none' });
    const shadow = host.attachShadow({ mode: 'open' });
    shadow.innerHTML = `<style>:host{font:13px/1.5 system-ui,Tahoma,sans-serif;text-align:right}button{font:inherit;font-weight:600;color:white;background:#24583f;border:1px solid #fff9;border-radius:9px;padding:8px 14px;cursor:pointer;box-shadow:0 2px 10px #0003;pointer-events:auto}button:hover{background:#173e2c}button:focus-visible{outline:3px solid #f4c75f;outline-offset:3px}button:disabled{background:#56675d;cursor:wait}span{display:block;margin-top:4px;padding:4px 8px;background:#fffffff0;color:#22382b;border-radius:5px;font-size:11px;overflow-wrap:anywhere}span:empty{display:none}</style><button type="button" aria-pressed="false">แปลภาพนี้ · EN</button><span role="status" aria-live="polite"></span>`;
    const state = { image, host, button: shadow.querySelector('button'), status: shadow.querySelector('span'), showing: false };
    states.set(image, state);
    document.body.append(host);
    resize.observe(image);
    image.addEventListener('load', schedule);
    state.button.onclick = async event => {
      if (!event.isTrusted) return;
      if (state.translated) { show(state, !state.showing); return; }
      if (busy || batching) return;
      try { await translate(state); } catch { /* Error is displayed beside the image. */ }
    };
    updateButtons();
    schedule();
  }

  async function translate(state) {
      const image = state.image;
      const url = sourceURL(image);
      busy = true;
      updateButtons();
      state.src = image.getAttribute('src'); state.srcset = image.getAttribute('srcset');
      state.button.disabled = true;
      state.button.textContent = 'กำลังแปล…';
      state.status.textContent = 'กำลังต่อเนื้อหาข้ามรอยต่อภาพก่อนแปล';
      try {
        const episode = episodeImages();
        if (!episode.every((image, index) => image.id === `content_image_${index}`)) {
          throw new Error('ลำดับภาพยังโหลดไม่ครบ กรุณารอแล้วลองใหม่');
        }
        const urls = episode.map(image => {
          const state = states.get(image);
          return state?.translated ? state.originalURL : (image.getAttribute('data-src') || sourceURL(image));
        });
        state.originalURL = url;
        let job = await send({ type: 'translate', urls, index: episode.indexOf(image) });
        const deadline = Date.now() + 15 * 60 * 1000;
        while (job.status === 'running') {
          if (!image.isConnected || sourceURL(image) !== url) throw new Error('ภาพต้นทางเปลี่ยน กรุณากดแปลใหม่');
          if (Date.now() > deadline) throw new Error('รอนานเกิน 15 นาที กรุณาตรวจหน้าต่างบริการแปล');
          state.status.textContent = job.message || 'กำลังอ่าน แปล และวางข้อความ…';
          await new Promise(resolve => setTimeout(resolve, 1500));
          job = await send({ type: 'status', id: job.id });
        }
        if (job.status === 'error') throw new Error(job.message);
        if (!image.isConnected || sourceURL(image) !== url) throw new Error('ภาพต้นทางเปลี่ยน กรุณากดแปลใหม่');
        if (job.regions === 0) {
          state.noTextURL = url;
          state.status.textContent = 'ไม่พบข้อความเกาหลีที่อ่านได้ — คงภาพต้นฉบับไว้';
          return;
        }
        const result = await send({ type: 'result', id: job.id });
        const preview = new Image(); preview.src = result.image;
        await preview.decode();
        if (!image.isConnected || sourceURL(image) !== url) throw new Error('ภาพต้นทางเปลี่ยน กรุณากดแปลใหม่');
        state.translated = result.image;
        show(state, true);
      } catch (error) {
        state.status.textContent = error.message;
        throw error;
      } finally {
        busy = false;
        updateButtons();
        if (!state.translated) state.button.textContent = 'แปลภาพนี้ · EN';
      }
  }

  function scan(root) {
    if (root instanceof HTMLImageElement) attach(root);
    root.querySelectorAll?.('img[id^="content_image_"]').forEach(attach);
  }
  const observer = new MutationObserver(records => {
    for (const record of records) {
      for (const node of record.addedNodes) if (node.nodeType === 1) scan(node);
      if (record.type === 'attributes') {
        const state = states.get(record.target);
        if (state?.translated && (record.target.getAttribute('src') !== state.expectedSrc
            || record.target.getAttribute('srcset') !== state.expectedSrcset)) {
          state.translated = null; state.showing = false;
          state.button.textContent = 'แปลภาพนี้ · EN'; state.button.setAttribute('aria-pressed', 'false');
          state.status.textContent = '';
        }
      }
    }
    schedule();
  });
  observer.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['src', 'srcset'] });
  resize.observe(document.documentElement);
  window.addEventListener('resize', schedule);
  window.addEventListener('scroll', schedule, { passive: true });
  scan(document);
})();
