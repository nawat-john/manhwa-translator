// Capture box picker — open a browser and drag over the area to capture
//
//   node scripts/pick-box.mjs                 // Use the first page from config
//   node scripts/pick-box.mjs <url>           // Specify a page
//
// Page controls:
//   Drag mouse = draw a box
//   Enter     = Confirm and save to box.json
//   E         = Toggle element selection mode (hover and click)
//   Esc       = Clear the box and start again
import { chromium } from 'playwright';
import { writeFile } from 'node:fs/promises';
import cfg from '../config.mjs';

const url = process.argv[2] || cfg.click.startUrl || cfg.urls[0];

if (!url) {
  console.error('No URL — pass one via argv or set config.click.startUrl / config.urls');
  process.exit(1);
}

const browser = await chromium.launch({ headless: false });
const context = await browser.newContext({
  viewport: cfg.viewport,
  deviceScaleFactor: cfg.deviceScaleFactor,
});
const page = await context.newPage();

console.log(`Opening ${url}`);
await page.goto(url, { waitUntil: 'domcontentloaded' });
if (cfg.waitFor) {
  await page.waitForSelector(cfg.waitFor, { timeout: 15000 }).catch(() => {});
}

let resolveDone;
const picked = new Promise((r) => (resolveDone = r));
await page.exposeFunction('__pickDone', (payload) => resolveDone(payload));

await page.evaluate(() => {
  const Z = '2147483647';
  const overlay = document.createElement('div');
  overlay.style.cssText = `position:fixed;inset:0;z-index:${Z};cursor:crosshair;background:transparent`;

  const marquee = document.createElement('div');
  marquee.style.cssText =
    'position:fixed;border:2px solid #ff2d55;background:rgba(255,45,85,.12);pointer-events:none;display:none';

  const hud = document.createElement('div');
  hud.style.cssText =
    `position:fixed;left:12px;top:12px;z-index:${Z};font:12px/1.6 ui-monospace,monospace;` +
    'background:rgba(17,17,17,.92);color:#fff;padding:10px 12px;border-radius:8px;' +
    'white-space:pre;pointer-events:none;box-shadow:0 4px 16px rgba(0,0,0,.4)';

  document.body.append(overlay, marquee, hud);

  let mode = 'drag'; // 'drag' | 'element'
  let start = null;
  let box = null; // Page coordinates (page space), including scroll offset
  let selector = null;

  const round = (n) => Math.round(n);
  const draw = (r) => {
    marquee.style.display = 'block';
    marquee.style.left = `${r.left}px`;
    marquee.style.top = `${r.top}px`;
    marquee.style.width = `${r.width}px`;
    marquee.style.height = `${r.height}px`;
  };

  const render = () => {
    const lines = [
      mode === 'drag' ? '● Drag mode' : '● Element selection mode',
      box
        ? `x:${box.x}  y:${box.y}  w:${box.width}  h:${box.height}` +
          (selector ? `\nselector: ${selector}` : '')
        : 'No box selected',
      '',
      'Enter = Confirm   E = Toggle mode   Esc = Clear',
    ];
    hud.textContent = lines.join('\n');
  };

  const cssPath = (el) => {
    if (el.id) return `#${CSS.escape(el.id)}`;
    const parts = [];
    for (let n = el; n && n.nodeType === 1 && n !== document.body; n = n.parentElement) {
      if (n.id) {
        parts.unshift(`#${CSS.escape(n.id)}`);
        break;
      }
      const cls = [...n.classList]
        .filter((c) => !/\d/.test(c))
        .slice(0, 2)
        .map((c) => `.${CSS.escape(c)}`)
        .join('');
      const sibs = [...(n.parentElement?.children ?? [])].filter(
        (x) => x.tagName === n.tagName,
      );
      const nth = sibs.length > 1 ? `:nth-of-type(${sibs.indexOf(n) + 1})` : '';
      parts.unshift(n.tagName.toLowerCase() + cls + nth);
    }
    return parts.join(' > ');
  };

  // ---- Drag mode ----
  overlay.addEventListener('mousedown', (e) => {
    start = { x: e.clientX, y: e.clientY };
    selector = null;
  });
  overlay.addEventListener('mousemove', (e) => {
    if (!start) return;
    const r = {
      left: Math.min(start.x, e.clientX),
      top: Math.min(start.y, e.clientY),
      width: Math.abs(e.clientX - start.x),
      height: Math.abs(e.clientY - start.y),
    };
    draw(r);
    box = {
      x: round(r.left + window.scrollX),
      y: round(r.top + window.scrollY),
      width: round(r.width),
      height: round(r.height),
    };
    render();
  });
  overlay.addEventListener('mouseup', () => (start = null));

  // ---- Element selection mode ----
  const onHover = (e) => {
    if (mode !== 'element') return;
    const el = e.target;
    if (!el || el === document.body || el === overlay) return;
    const r = el.getBoundingClientRect();
    draw({ left: r.left, top: r.top, width: r.width, height: r.height });
    box = {
      x: round(r.left + window.scrollX),
      y: round(r.top + window.scrollY),
      width: round(r.width),
      height: round(r.height),
    };
    selector = cssPath(el);
    render();
  };
  const onPick = (e) => {
    if (mode !== 'element') return;
    e.preventDefault();
    e.stopPropagation();
    mode = 'drag';
    overlay.style.pointerEvents = 'auto';
    render();
  };
  document.addEventListener('mousemove', onHover, true);
  document.addEventListener('click', onPick, true);

  window.addEventListener(
    'keydown',
    (e) => {
      if (e.key === 'Enter' && box) {
        if (box.width < 2 || box.height < 2) return;
        window.__pickDone({ clip: box, selector });
      } else if (e.key === 'Escape') {
        box = null;
        selector = null;
        marquee.style.display = 'none';
        render();
      } else if (e.key.toLowerCase() === 'e') {
        mode = mode === 'drag' ? 'element' : 'drag';
        // Element mode needs pointer events to pass through the overlay
        overlay.style.pointerEvents = mode === 'element' ? 'none' : 'auto';
        render();
      }
    },
    true,
  );

  render();
});

const result = await picked;
await writeFile('box.json', `${JSON.stringify(result, null, 2)}\n`, 'utf8');
console.log('Saved to box.json:', result);
console.log('To use a selector instead of coordinates, remove the "clip" key from box.json');
await browser.close();
