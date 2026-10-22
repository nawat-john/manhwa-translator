# Manga image translator

Translate Korean webtoon images into English and display the translated image over the original in Chrome. The local pipeline joins image boundaries, splits at horizontal whitespace, groups OCR by enclosed white balloons, translates with M2M100, removes original text with LaMa, and renders English.

## Run the extension

After installing the [Python environment and models](translator/README.md), run from the project root:

```powershell
npm ci
npm run extension:serve
```

Open `chrome://extensions`, enable Developer mode, choose **Load unpacked**, and select `extension/`. Refresh the Naver reader and use **Translate image** or **Translate all**. See the [extension guide](extension/README.md).

The active Korean runtime uses the trimmed baseline translation model and FP16 OCR on CUDA. Experimental LoRA adapters are not enabled. OCR and translation can still make mistakes.

## Project layout

| Path | Purpose |
|---|---|
| `extension/` | Chrome UI and local translation service |
| `translator/` | Python pipeline, setup and research scripts |
| `translator/tests/` | Python tests |
| `translator/docs/` | Training guides and experiment results |
| `translator/data/`, `translator/reports/` | Versioned training data and evaluation evidence |
| `scripts/` | Image download, capture and verification tools |
| `lab/` | Japanese image translation comparison UI |
| `docs/` | Original browser capture guide |
| `samples/`, `vol*/` | Local inputs and translated samples, excluded from Git |
| `translator/models/`, `translator/work/` | Local weights and generated jobs, excluded from Git |

## Common commands

Run commands from the project root:

```powershell
npm test                        # Node service tests and Python tests (Windows venv)
npm run scrape:naver             # Download the configured Naver sample episode
npm run verify:naver             # Check downloaded images
npm run lab                      # Japanese comparison UI at http://127.0.0.1:4173
```

The original commands (`npm run pick`, `npm run scrape`, `npm run scrape:click`, `npm run debug`) remain available. Settings stay in `config.mjs` and `box.json`; see the [capture guide](docs/CAPTURE.md).

## Results and development

- [Translator setup and workflow](translator/README.md)
- [Experiment and training index](translator/docs/README.md)
- [Latest balloon grouping comparison](samples/naver-845456-25/balloon-merged-10-v2/index.html) (local artifacts)
- [Japanese Lab guide](lab/README.md)

Git tracks code, non-secret configuration, training data and reports. `.env`, downloaded images, model weights, environments and generated outputs stay local. On a new machine, follow the [upstream patch guide](translator/patches/README.md) before setting up Python. Local sample links require the corresponding files. Git history is not an off-machine backup.
