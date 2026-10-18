// Shared configuration for pick-box.mjs and scrape.mjs
// Important: viewport/deviceScaleFactor must match in both scripts
// Otherwise, the selected capture box will shift
export default {
  // URLs to capture (scrape.mjs) — arrow navigation uses click.startUrl instead
  urls: ["https://comic-days.com/episode/3270375685434847971"],

  pad: 4, // Filename digits (4 → 0001.png)

  outDir: 'vol2',

  viewport: { width: 1280, height: 900 },
  deviceScaleFactor: 2, // 2 = double the image resolution

  waitFor: 'canvas', // Selector to wait for before capture (null = do not wait)
  scrollToBottom: true, // Scroll to the bottom first to trigger lazy loading
  settleMs: 600, // Wait after loading for images/fonts to settle
  politeDelayMs: 1200, // Delay between pages to avoid excessive requests

  headless: true,
  overwrite: false, // false = skip existing files (supports resuming)

  // Left-arrow mode (scrape-click.mjs) — snapshot → press arrow → wait for loading → repeat
  click: {
    startUrl: '', // Starting page (can also be passed via argv)

    // Choose a navigation method (priority: selector > key > point)
    key: null, // Press a keyboard key, e.g. 'ArrowLeft'
    selector: null, // Click a button by CSS selector
    point: { x: 0, y: 300 }, // Click screen coordinates — use { xPct, yPct } for relative coordinates

    maxPages: 500, // Prevent an endless loop
    afterClickMs: 5000, // Maximum wait after clicking (ends early if content changes)
    imgWaitMs: 8000, // Image loading timeout to prevent hanging on broken images
    startIndex: 1, // Starting sequence number for filenames/logs
    logFile: 'pages.log', // File containing the URL of each page
  },
};
