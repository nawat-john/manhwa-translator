# Manga Lab — Chrome extension for Naver

Initial version: a **Translate image · EN** button for `content_image_*` images on Naver webtoon reader pages. It uses EasyOCR + M2M100 + LaMa locally to translate Korean into English and displays the result in place. Click **View original / View English translation** to toggle immediately.

## Getting started on this machine

1. Open a terminal at the project root, run `npm run extension:serve` and leave it open.
2. Open `chrome://extensions` in Chrome and enable **Developer mode**.
3. Click **Load unpacked** and select `D:\Code\hanaori-san-scrape\extension`.
4. Open or refresh https://comic.naver.com/webtoon/detail?titleId=845456&no=25&week=wed.
5. Click **Translate image · EN** at the top-right of an image and wait for the button to change to **View original**.

The service automatically creates `config.local.js` to connect to this machine in step 1, so start it before loading the extension. Manga Lab and its service on port 4173 are not required.

If Chrome reports a missing `config.local.js`, start the service and reload the extension. If the service reports an invalid connection, reload the extension and refresh the Naver page.

## Behavior

- Click **Translate all · EN** at the bottom-right to translate the episode's images sequentially, show progress and replace each image with its result. It joins neighboring images in the same way as individual translation.
- Click **Stop after this image** to stop the queue once the current image finishes. Click Translate all again to continue, skipping images already translated or found to contain no text on this page. Service errors stop the queue and display the reason. Translated images can still be toggled back to their originals.
- Translation starts only after a button click. Refreshing or closing the page clears the queue and page state.
- Before translation, preceding/following images are joined until horizontal whitespace is found, then split into panels at that whitespace so text crossing file boundaries remains intact for OCR.
- Whitespace is a nearly all-white or all-black band across the full width, at least 24px thick. Splits use the middle of the band and preserve every pixel; text is not cut to meet a pixel limit.
- Translated panels are cropped back to the selected source image's coordinates, preserving image height and scroll position. The next image uses neighboring context in the same way.
- Only one image is translated at a time. If another is running, the service asks you to wait and retry.
- The original remains visible until the result is ready and decodable. Source image files are never overwritten.
- Each job has its own ID to prevent applying one image's result to another.
- If OCR finds no readable Korean text, the original is retained and a no-text message appears.
- Images added by lazy loading are supported; buttons reposition on scrolling/resizing.
- Toggling in the same tab reuses the loaded result without translating again.
- Leaving the page may not stop a local job. Results remain on disk, but refreshing does not restore the previous job state.
- If the service stops during a job, restart it and translate again. Interrupted jobs are not reported as complete.

## Data and permissions

The service listens only on `127.0.0.1:4174` and requires a locally generated token for every request. The token is stored in `translator/work/extension/token` and `extension/config.local.js`. **Do not share these two files.** Each machine should generate its own token when using published code.

The content script runs only on `https://comic.naver.com/webtoon/detail*`. The service worker has loopback host permission to communicate with the service. Source images are downloaded only from `https://image-comic.pstatic.net/webtoon/<title>/<episode>/...`; local paths, other servers and redirects are rejected.

Input images are validated: at most 20 MiB, static JPEG/PNG/WebP, at most 16 million pixels and no dimension above 16000px. Results are also limited to 20 MiB. The image list must be ordered, contain no duplicates, come from one episode and contain at most 300 images. Only images needed to find the selected image's boundaries are downloaded. Context is limited to 32 files or 80 MiB. If no whitespace is found within those limits, the job fails instead of cutting content.

Images and text are processed locally, without sending them to a translation API. The service may contact model download sources to download models or check caches.

Each job is stored in `translator/work/extension/<job-id>/`:

- `request.json`, `inputs/`: URL order and required source files.
- `panels/`, `context.json`: panels before translation and coordinate mapping to the source files.
- `translated/`: translated panels, with `ocr.json`, `translations.json` and `inputs.json` for text review and caching.
- `source.png`: translated content projected back onto the selected image's area, with the original dimensions.
- `job.json`, `worker.log`: status and troubleshooting details.

## Experimental limitations

This still uses the original experimental models. Korean translations can be incorrect, and sound-effect lettering may be missed. Joining images fixes text cut at file boundaries, but does not fix OCR or translation errors. Other whitespace colors and images without clear whitespace are unsupported, and joined images must have equal widths. Only Naver Korean → English is supported; the Japanese translation page is not connected, and canvas-based readers are unsupported.

A new Python worker starts and loads models for each image, adding startup time. CUDA uses the GPU when available; otherwise the CPU is used. Avoid running batch translation or Manga Lab translation simultaneously because the separate services share the GPU. Job files accumulate on disk; there is no automatic cleanup.

## Verification

```powershell
npm run test:extension
# Test Translate all with a mock service, without translation models
node extension/check-batch.mjs
& translator/.venv/Scripts/python.exe translator/test_korean_input.py
& translator/.venv/Scripts/python.exe translator/test_split_webtoon.py
# Start the service first: load the real extension in Playwright Chromium and translate a real image
node extension/check-browser.mjs
```

The extension service uses `translate_webtoon.py` to join images and project results back, while `translate_korean_sample.py` provides shared panel translation. To split and test the first 10 panels locally:

```powershell
& translator/.venv/Scripts/python.exe translator/split_webtoon.py samples/naver-845456-25 samples/naver-845456-25/panels
& translator/.venv/Scripts/python.exe translator/translate_korean_sample.py
```

On a new machine, set up the environment using `translator/README.md` and install EasyOCR as described in the Korean trial guide.

After upgrading from the single-file translation version, restart `npm run extension:serve`, reload the extension and refresh Naver so neighboring image lists can be sent. Previous trial results remain in `english-10`; new results are in `english-panels-10`, with separate caches and image fingerprint checks before reuse.
