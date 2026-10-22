# Browser image capture

Capture web pages with Playwright by dragging a custom capture box.

## File layout

| File | Purpose |
| --- | --- |
| `config.mjs` | Shared settings — URLs, page range, viewport and wait timings |
| `scripts/pick-box.mjs` | Opens a browser to select a box and saves coordinates to `box.json` |
| `scripts/scrape.mjs` | Iterates over pages **by URL**, capturing the box in `box.json` |
| `scripts/scrape-click.mjs` | Navigates with the **left arrow** — snapshot → click → wait for loading |
| `pages.log` | Page URLs and sequence numbers from arrow navigation |
| `scripts/debug.mjs` | Reports page contents and what happens after navigation |
| `debug/` | Images from `debug.mjs` (`full-N.png`, `clip-N.png`) |
| `box.json` | Capture box selection (generated automatically) |
| `failed.json` | Summary of failed captures (created on failure) |
| `vol1/` | Output image directory |

## Installation

```powershell
npm install
npx playwright install chromium
```

## Usage

### 1. Configure

Edit `config.mjs`.

- URLs have no page numbers, so there is no URL counter. Choose one:
  - `click.startUrl` — starting page for arrow navigation (the main workflow; see 3b).
  - `urls: []` — explicit URLs if you already know every page (for `scrape.mjs`).
- `pad` — filename digit count (`4` → `0001.png`).
- `waitFor` — selector to wait for before capture. Match the actual image/content, or use `null` to skip waiting.

### 2. Select a capture box

```powershell
npm run pick              # Uses click.startUrl (or urls[0]) from config
node scripts/pick-box.mjs <url>   # Or specify a page
```

A browser opens with a HUD in the top-left corner.

| Key / action | Result |
| --- | --- |
| Drag mouse | Draw a box; `x y w h` update live |
| `E` | Toggle **element selection** — hover to snap to an element, then click to lock |
| `Esc` | Clear the box and start again |
| `Enter` | Confirm, save to `box.json` and close the browser |

Element selection also saves a CSS selector.

### 3. Capture images from a URL list

```powershell
npm run scrape        # All URLs in config.urls
node scripts/scrape.mjs 5 12  # Only entries 5–12 in the list
```

- Output files are `vol1/0001.png`, `0002.png`, … (according to `pad`).
- Reruns skip existing files; set `overwrite: true` to replace them.
- Each failed page is retried once. Remaining failures are recorded in `failed.json`.

### 3b. Capture with left-arrow navigation

This is the main workflow because URLs do not contain page numbers; navigation must advance one page at a time.

```powershell
npm run scrape:click                       # Uses config.click.startUrl
node scripts/scrape-click.mjs <url>                # Start at this URL
node scripts/scrape-click.mjs <url> 60             # Limit to 60 pages
```

The loop is **snapshot → press left arrow → wait for loading → repeat**.

Choose one of three navigation methods in `config.click` (priority: `selector` > `key` > `point`).

| Key | Meaning |
| --- | --- |
| `key: 'ArrowLeft'` | Press the left-arrow key |
| `selector: '.btn-prev'` | Click a button by CSS selector |
| `point: { xPct: 0.25, yPct: 0.5 }` | Click relative viewport coordinates (for readers with left/right click zones) |

If `key: null` is set and no other method is provided, the script guesses the arrow button from `aria-label`, class, text and position. If none is found, it prints candidate elements with coordinates and dimensions and saves `debug-page.png`.

- `afterClickMs` (default 5000) — **maximum** wait after navigation; continues early if content changes.
- `imgWaitMs` (default 8000) — image loading timeout. **Do not remove it.** Broken images may never emit `load`, so an unlimited wait can hang forever.
- Each URL is appended to `pages.log` immediately after capture, preserving progress after a crash. A URL change is marked with `<- url changed`.

```text
0001    https://example.com/reader
0002    https://example.com/reader
0003    https://example.com/reader/ch2    <- url changed
```

- Stops at `maxPages`, when navigation fails, or when **the capture matches the previous page twice in a row** (the end of the book). Duplicates do not consume sequence numbers or create duplicate files in `vol1/`.
  - Detection deliberately compares image hashes rather than the DOM: readers that preload the whole book may retain the same `src` values on every page, making DOM comparison falsely detect the end on page two.
- Resume by setting `click.startIndex` after the last saved number. Existing files are skipped with `overwrite: false`, but the script still needs to click through those pages.

### 4. Debug (`debug.mjs`)

Run this before a long capture on a new website, or when the script hangs or captures the wrong content.

```powershell
npm run debug                     # URL from config, 3 arrow presses
node scripts/debug.mjs 5                  # 5 presses
node scripts/debug.mjs <url> 5            # Specify a URL
node scripts/debug.mjs <url> 3 --headed   # Show the browser until Ctrl+C
```

The report includes:

| Section | What to check |
| --- | --- |
| `domcontentloaded` / `waitFor` timings | Whether `waitFor` matches or times out; "not found" wastes 15 seconds per page |
| `Wait for images ... reached imgWaitMs` | Images that never emit `load`/`error`, which previously caused indefinite hangs |
| Visible `img`/`canvas` elements | Actual dimensions and positions to compare with `box.json`'s `clip`, including `Failed to load!` markers |
| `iframe` | Whether content is inside a child frame |
| Candidate left-arrow buttons | Options for `click.selector`, with coordinates |
| `keydown listener on window/document` | Whether the site handles keyboard input; avoid `click.key` if there are none |
| Each navigation step | When the captured image changes, whether the URL changes and the image hash |
| Page errors and failed requests | Console errors, page errors and blocked requests |

Files in `debug/` are `full-N.png` (full page) and `clip-N.png` (capture box), where `N` is the number of navigation steps. Compare them to verify that pages change and the capture box is correct.

## Important notes

### Coordinates or selector

`box.json` stores both:

```json
{
  "clip": { "x": 320, "y": 180, "width": 640, "height": 900 },
  "selector": "div.reader > img:nth-of-type(1)"
}
```

`scrape.mjs` prioritizes `clip`. **Remove `clip` and keep only `selector`** to use `locator().screenshot()`, which tolerates layout differences because the capture box follows the element.

If the content is contained in one clear element, try selector mode first; use coordinates if the selector is unstable.

### Keep the viewport settings consistent

Selected coordinates depend on `viewport` and `deviceScaleFactor` in config. **Rerun `pick` if either changes**, or the box will shift. Both scripts read the same configuration for this reason.

`deviceScaleFactor: 2` doubles image resolution at the cost of larger files.

### Coordinates use page space, not viewport space

`pick-box.mjs` includes `scrollX/scrollY`, and `scrape.mjs` captures with `fullPage: true` to match. You can select content below the fold without restoring the same scroll position before capture.

### Download standalone images directly

Screenshots contain browser-resized/recompressed images and may be less sharp than the originals. If you only need the image itself, download its `src` for full quality:

```js
const src = await page.locator('#page-img').getAttribute('src');
const res = await context.request.get(new URL(src, url).href);
await writeFile(out, await res.body());
```

`context.request` uses the browser context's cookies and configured headers, which can help with referer/authentication checks.

### Other Playwright capture options

```js
// Capture one element
await page.locator('#card').screenshot({ path: 'card.png' });

// Add padding around an element
const b = await page.locator('#card').boundingBox();
await page.screenshot({
  clip: { x: b.x - 16, y: b.y - 16, width: b.width + 32, height: b.height + 32 },
});

// Visual regression: mask changing content to avoid unstable tests
await expect(page).toHaveScreenshot({ clip: {...}, mask: [page.locator('.ads')] });
```

## Troubleshooting

| Symptom | Common cause |
| --- | --- |
| Blank / white image | `waitFor` does not match, or `settleMs` is too short; try 1500 |
| Partial image / missing content | Lazy loading has not triggered; check `scrollToBottom: true` |
| Capture box shifted | `viewport`/`deviceScaleFactor` changed after selection; rerun `pick` |
| Blocked / 429 | Increase `politeDelayMs` and try `headless: false` |
| Selector fails on some pages | Use `clip` mode or broaden the selector in `box.json` |

Set `headless: false` in config to inspect loading in the browser.

## Before a real run

Check the target site's `robots.txt` and terms of use, and avoid reducing `politeDelayMs` far below its default.
