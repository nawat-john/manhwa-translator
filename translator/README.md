# Translation pipeline

The main workflow is Korean-to-English image translation for the Chrome extension. Japanese batch/PDF translation and the Lab remain available separately.

## Setup

1. Restore the pinned upstream checkout and local fixes using the [patch guide](patches/README.md).
2. From the project root, run `powershell -ExecutionPolicy Bypass -File translator/setup_env.ps1`. This Windows setup uses `D:/Code/python312/python.exe` and creates `translator/.venv/`.
3. Follow the [Korean runtime guide](docs/OPTIMIZATION.md) for EasyOCR, trimmed model artifacts and checks. LoRA tooling is described in the [training guide](docs/LORA.md).

Weights, the virtual environment and caches are local files excluded from Git. A fresh checkout does not include them.

## Current runtime

| File | Responsibility |
|---|---|
| `translate_webtoon.py` | Fetch neighbors, prepare panels and restore the selected image slice |
| `split_webtoon.py` | Join image boundaries and split at whitespace |
| `translate_korean_sample.py` | Shared OCR, translation, inpainting and rendering |
| `balloon_text.py` | Combine OCR fragments in the same enclosed white balloon |
| `korean_translation.py` | Trimmed M2M100 baseline and original-model fallback |
| `ocr_precision.py` | FP16 Korean/English OCR on CUDA |

The extension invokes this pipeline. Neither sentence LoRA nor context LoRA is enabled. See [balloon grouping results](docs/BALLOON-GROUPING-RESULTS.md) and [optimization](docs/OPTIMIZATION.md).

## Run and verify

From the project root:

```powershell
npm run extension:serve
npm run test:python
```

Translate ten sample panels:

```powershell
translator/.venv/Scripts/python.exe -X utf8 translator/translate_korean_sample.py
```

This needs the downloaded Naver sample in `samples/naver-845456-25/`. Default output is `english-balloon-panels-10/` inside that directory. For one local image, supply both `--input <image>` and `--output <new-directory>`. Use a new output directory when source images or OCR grouping change, to avoid stale caches.

## Research and other workflows

Research scripts retain their existing paths, shared imports and reproducible commands. Their documentation is collected in the [experiment index](docs/README.md). Corpora remain in `data/`, checked-in evidence in `reports/`, weights in `models/` and generated jobs in `work/`.

For Japanese page splitting, restart behavior, PDF generation and shim limitations, see the [Japanese workflow](docs/JAPANESE.md). The original detailed guide is retained there as historical documentation; use the current runtime guides above for Korean translation. Use the [Lab guide](../lab/README.md) for the comparison UI.
