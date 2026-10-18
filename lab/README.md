# Manga Lab

A Japanese → English test interface using images and models already installed in the project, without additional npm dependencies.

```powershell
npm run lab
```

Open **http://127.0.0.1:4173** (use this IP, not localhost).

- Search and select images from `translator/work/pages`, currently containing 388 test pages.
- Compare originals and translations side by side, expand either side, and download PNGs.
- Existing results are read from `translator/work/out`; new translations are saved in `translator/work/lab`.
- The translation button runs manga-image-translator with the existing config, manga-ocr, Sugoi, LaMa and CUDA, one page at a time.
- Lab results are replaced only after successful retranslation; failures preserve the previous result. Source images and the original output set are unchanged.
- Status and logs appear below the images. You can browse other pages while translation runs.
- The Python environment and models described in `translator/README.md` are required. The first run may download models. Do not run the batch pipeline alongside Lab because they share the GPU.

## Analysis and fixes

The existing pipeline covers splitting double-page images, OCR, translation, text removal and rendering. It produced all 388 output files, but file count is not a quality score. Page 0010, for example, has OCR errors and English text much longer than the Japanese, so both translation and placement need review.

Two fixes were made in the manga-image-translator clone:

1. `rendering/__init__.py`: when `font_size` is explicitly set, use the original detection box and clamp coordinates to the image instead of expanding the box to fit English text over the artwork. Existing rendering code wraps and shrinks text to fit. Very narrow Japanese text boxes can still produce small lettering; this does not detect bubble boundaries.
2. `__main__.py`: single-file translation previously ignored `-o` and always wrote `result/final.png`. It now respects the specified destination and does not force overwrite when the user supplies a destination.

Both patches are applied directly to the upstream clone. If you replace the clone or update upstream, verify that they remain applied. The original 388 images have not been retranslated with these patches.

## Path toward a Chrome extension

The suitable architecture for these models is **extension selects an image → local translation service → return the result → overlay it with an original-image toggle**. The models currently depend on Python/PyTorch/CUDA; moving the whole stack into an extension would require a separate runtime migration and performance testing effort.

This Lab is a quality-review base; its Japanese workflow does not yet have an extension or an API accepting arbitrary web images. Required next steps:

- Accept image files with type, file-size and pixel-count validation; store jobs under separate IDs.
- Start extension jobs from user selections and restrict permissions to the chosen capture method.
- Authenticate the extension with the local service before allowing its origin to call the API.
- Associate results with source images and config for correct caching.
- Test narrow bubbles, text on black backgrounds, decorative lettering, long images and pages without text.

The current API accepts only filenames from the test set, not arbitrary paths or URLs. It rejects cross-origin POST requests and Host headers that do not match the local IP.

## Verification

```powershell
npm run test:lab
# Start npm run lab in another terminal first
node lab/check-ui.mjs
node lab/check-ui.mjs --translate
& translator/.venv/Scripts/python.exe translator/test_render_bounds.py
```

`--translate` tests real GPU translation of page 0010. It takes longer than UI checks and writes new output only in the Lab directory. Screenshots are saved in `lab/screenshots/`.

Previous verification results: both API tests passed; the UI passed at 1440px and 390px; the text-bounds regression passed; and page 0010 was translated successfully on an RTX 3050 Laptop GPU in about 39 seconds. The new result is `translator/work/lab/0010.png`. Line wrapping improved, but narrow boxes still produce small text and some Japanese OCR errors remain. Quality has not been reviewed across every page.

Limitations: a translation job's state is stored in memory and cannot resume after server shutdown; completed results remain on disk. Review translations before use, especially names, jokes and text that OCR incorrectly combines across bubbles.
