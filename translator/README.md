# hanaori-san vol. 1 — JA→EN overlay translation

Korean model size experiment: [vocabulary trimming results](VOCAB_TRIM.md).
Current Korean runtime, FP16 OCR and OmniRoute data setup: [optimization guide](OPTIMIZATION.md).
First full LoRA corpus size and generation plan: [training data plan](TRAINING_DATA_PLAN.md).
Completed synthetic KO→EN data: [5,000 train / 500 validation / 500 test](data/ko-en-dialogue-6k-v1/README.md).

Burns English translations into the scans in place of the Japanese, the way
Google Translate's camera overlay does, using
[manga-image-translator](https://github.com/zyddnys/manga-image-translator):
detect text → OCR → inpaint the original text away → translate → typeset the
English back into the bubble. Output is one PDF.

Everything — interpreter, venv, wheels, models, HF cache — lives on `D:`.

## Layout

| Path | What |
|---|---|
| `.venv\` | dedicated venv, built from `D:\Code\python312\python.exe` |
| `manga-image-translator\` | pinned upstream clone with local fixes; see [patches](patches/README.md) |
| `models\` | detector / OCR / inpainting weights (`--model-dir`) |
| `hf-cache\` | HuggingFace cache (`HF_HOME`), holds manga-ocr |
| `shims\pydensecrf-shim\` | stand-in for a dependency that cannot build here — see below |
| `work\pages\` | 388 single pages split from the 194 spreads |
| `work\out\` | translated pages |
| `work\queue\` | transient hardlinks handed to the worker each round |
| `work\logs\` | one log per worker round, plus the setup log |
| `work\state.json` | per-page status; the resume ledger |
| `work\page_map.json` | which spread and half each page came from |
| `output\` | the PDF and its build report |

## Running it

```powershell
.\setup_env.ps1                                  # once
D:\Code\hanaori-san-scrape\translator\.venv\Scripts\python.exe split_pages.py
D:\Code\hanaori-san-scrape\translator\.venv\Scripts\python.exe run_pipeline.py
D:\Code\hanaori-san-scrape\translator\.venv\Scripts\python.exe build_pdf.py
```

`run_pipeline.py --limit 3` translates only the first three pending pages —
useful for checking output quality before committing to the whole book.

## Not losing work

Three independent layers, because they fail differently.

**A page throws inside the worker.** `--ignore-errors` logs it and moves on, so
one bad page does not end the run. `--attempts 2` retries it first.

**The worker process dies** — CUDA OOM, a native crash in onnxruntime/opencv,
the machine rebooting. Nothing inside the worker can catch that, so
`run_pipeline.py` supervises it from outside and restarts it. Restarting is
cheap because the worker skips any page whose output already exists
(`mode/local.py:205`), so a restart resumes exactly where it stopped and never
recomputes a finished page.

**A page kills the process every time.** The supervisor watches for restarts
that produce zero new pages. After `--stall-tolerance` (default 2) such rounds,
the first still-pending page is the one blocking the queue, so it is marked
`quarantined` in `state.json` — with the reason and the tail of the log that
killed it — and skipped from then on. One poisonous page costs one page.

Beyond that: `state.json` is rewritten atomically after every round, so killing
the script at any moment loses at most the round in flight. `work\pages\` is
never mutated after the split; the worker reads a queue of hardlinks instead.
And `build_pdf.py` substitutes the untranslated original for any page that never
made it, so **the PDF is always complete and correctly ordered** — never missing
pages. Which pages fell back is printed and written to
`output\build-report.json`.

Interrupting and re-running `run_pipeline.py` is always safe.

## Decisions worth knowing

**Its own venv, not `D:\Code\.venv`.** The shared env has 245 packages
including `transformers` 5.x, chatterbox-tts and diffusers. This project pins
`pydantic==2.5.0`, `httpx==0.27.2`, `openai==1.63.0`, `numpy==1.26.4`;
installing it there downgrades all four. Same interpreter, separate
`site-packages`.

**`pydensecrf` is shimmed.** It is the one dependency with no wheel for
Windows + CPython 3.12, and building it from source needs an MSVC C++ toolchain
this machine does not have (VS 18 Community is installed without the C++
workload). It is imported at module scope in
`manga_translator/mask_refinement/text_mask_utils.py` for a dense-CRF pass that
tightens the inpainting mask against glyph edges. `shims\pydensecrf-shim`
satisfies the import and degrades that pass to identity, so the mask is the
connected-component mask it was already given — slightly looser, and it gets
dilated by `mask_dilation_offset: 20` immediately afterwards regardless. It is
filtered out of `requirements.txt` at install time rather than edited out of the
repo, so `git pull` in the clone stays clean.

To get the real one back: install the MSVC C++ build tools, then
`pip uninstall pydensecrf-shim` and
`pip install 'pydensecrf@https://github.com/lucasb-eyer/pydensecrf/archive/refs/heads/master.zip'`.

**Pages are cut at exactly `width // 2`.** Profiling ink per column across the
volume showed the gutter is a blank band 82–140 px wide sitting dead on the
midpoint, so no seam search is needed. The split reports spreads where art
bleeds across the fold (`0001`, `0002`, `0070`) — the cut lands on artwork
there, which is correct but worth an eye.

**Right half first.** These are right-to-left spreads, confirmed against the
printed page numbers: `0005.png` is p142 on the right, p143 on the left. So each
spread yields its right half first. Output pages are numbered `0001.png` onward
in reading order, which is what makes lexicographic sort work for every later
stage.

**Sugoi as the translator** (`config.json`) — a JA→EN-specific offline model, no
API key, no per-page cost. It translates line by line without cross-panel
context, so jokes that depend on setup-and-punchline across panels will read
flatter than a human translation. To switch to an LLM later, change
`translator.translator` in `config.json` to `gemini`, `chatgpt` or `deepseek`,
put the key in `manga-image-translator\.env`, and add `--context-size 2` in
`worker_cmd()`. Already-translated pages are not redone, so delete `work\out\`
first if you want the whole book re-translated.

**OCR is `mocr`** (manga-ocr), not the default `ocr48px` — it is trained on
exactly this: vertical Japanese text in manga bubbles.

**Do not pass `--save-text` to the worker.** Despite the name it is not an
extra output — `manga_translator.py:1105` dumps the translations to JSON and
calls `exit(-1)` before rendering, so the run produces no images at all. It is
exposed here as `run_pipeline.py --dump-text-only` so the behaviour is
unambiguous.

**Rendering** uses `anime_ace.ttf` (passed as `--font-path`; it is a CLI arg,
not a config key, and without it the renderer silently falls back to a generic
sans) with `renderer: default` and a **fixed `font_size: 14`**, tuned for these
1070 px-wide pages. Change it if the page size changes.

That fixed size is doing real work, and the reason is worth knowing. Detection
boxes the *vertical Japanese text column*, not the speech balloon — a column is
maybe 90 px wide where its balloon is 200 px. English set horizontally cannot
fit that width, and the renderer's answer is to grow the box rather than shrink
the type: `rendering/__init__.py:119-121,152-154` have the clip-to-bounds lines
deliberately commented out ("allow text to exceed detection box boundaries").
`font_size_offset` cannot counter it, because `:170-175` re-inflates the font by
up to 1.5x whenever the translation is longer than the original — which for
JA→EN is always. A fixed `font_size` is the one lever that survives: vertical
regions take the `single_axis_expanded` path and skip that re-inflation
entirely.

`renderer: manga2eng` looks like the right choice for JA→EN and is not: it
takes neither `font_size` nor `font_size_offset` (`manga_translator.py:1372`
passes only `line_spacing`) and sizes text to whatever `extract_ballon_region`
returns. In 4-koma panels where balloons touch the panel border it grabs the
whole panel, and the page renders unreadable.

**Known quality ceiling.** Text still overruns balloons on dense pages and
occasionally clips at the page edge. This is geometric, not a tuning failure:
short vertical Japanese becomes long horizontal English with nowhere to put it.
The largest available improvement is not a render setting but a shorter
translation — an LLM told to write terse manga dialogue produces lines that fit,
where Sugoi's literal output ("SOCIALLY SHE'S A RELATIVELY SAFE WOMAN", 38
characters for 12 Japanese ones) does not.
