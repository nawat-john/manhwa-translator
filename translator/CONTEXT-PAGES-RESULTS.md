# First ten webtoon panels: baseline versus context LoRA

**The context model is not clearly better on these actual images, and the
translation stage is slower. Keep the active extension baseline.** Both sets
of translated images and an original/baseline/context gallery were generated:
[open the ten-panel comparison](../samples/naver-845456-25/context-comparison-10-v1/index.html).
Images remain local and are excluded from Git.

The input is the same first ten whitespace-delimited panels from Naver episode
845456/25 used in the earlier sample. The existing image fingerprints were
verified. The same 24 OCR regions, boxes, font settings, LaMa inpainter and
renderer are used for both models. Two panels contain no recognized text and
remain pixel-identical to their originals.

Baseline is the trimmed M2M100 that the extension currently uses, **without
either LoRA**. The candidate is the merged context LoRA, seeing up to three
preceding raw Korean OCR regions in top/left reading order, across panels.
Neither model receives previous English translations. Scene boundaries and
speaker identities are not detected. Inference is FP32, batch one, five beams,
maximum 160 new tokens and no repeated trigrams.

## Actual translation time for all ten panels

Three passes per model, alternating model order between passes, warm-up excluded,
CUDA synchronized. Model loading, source-history assembly and OCR are excluded.
All 24 generated translations were identical across each model's three passes.

| Model | Pass 1 | Pass 2 | Pass 3 | Median |
|---|---:|---:|---:|---:|
| Current extension baseline | 4.172 s | 3.508 s | 3.356 s | **3.508 s** |
| Context LoRA | 7.024 s | 6.327 s | 6.012 s | **6.327 s** |

The candidate adds **2.820 seconds (+80.4%)** to the translation stage on this
specific sample. Its output has 130 whitespace-separated English words versus
71 for the baseline (+83.1%), consistent with more autoregressive decoding work.
Some additional words improve grammar; others are unsupported or copied history.
This does not isolate context cost from the effects of changing the model.

The earlier +1.4% experiment compared **the same context-trained model with
empty versus populated history on a different synthetic sample**. This trial
compares the active, unadapted extension model against the context-trained
model on the actual OCR sample. The two percentages answer different questions.

## Image creation, measured separately

| Stage for ten panels | Baseline | Context |
|---|---:|---:|
| Load LaMa | 0.775 s | 0.799 s |
| Inpainting | 6.241 s | 5.390 s |
| Text rendering | 30.802 s | 26.875 s |
| PNG writing and validation | 0.776 s | 0.829 s |
| Image-pipeline wall time including cache reads/preparation | 38.786 s | 34.097 s |

This stage ran **once per model, baseline first**, with the same algorithm and
shared process/font caches. Its variation is not evidence that the context
model accelerates image processing. Median translation plus that single image
pass sums to approximately 42.29 versus 40.42 seconds, excluding OCR and MT
loading; these are phase sums, not uninterrupted end-to-end runs or a reliable
total-speed comparison. Model-loading medians were 1.542 and 1.878 seconds.
OCR was reused, so no fresh OCR time or Chrome/network time is measured.

## Is the English better?

Two models compare randomly assigned A/B candidates without model names or
English reference answers. Both see the same current Korean OCR and preceding
Korean context. `Tie` includes equally bad candidates; `unclear` means that the
source fragment cannot be judged fairly. These are preferences, not accuracy.

| Judge | Baseline preferred | Context preferred | Tie | Unclear |
|---|---:|---:|---:|---:|
| MiniMax M3.1 Flash | 10 | 9 | 3 | 2 |
| NVIDIA Nemotron 3.5 Super | 8 | 9 | 6 | 1 |

They agree on context for 6 regions, baseline for 5, and a tie for 2. They
disagree on the remaining 11 regions. With only 24 reused OCR regions, duplicated
interjections, corrupted source and no Korean human reviewer, this does not
support a general quality gain. AI judges can also prefer a nicer-sounding
candidate when both miss the source meaning.

Concrete improvements include `right is.` becoming `It's right.` and
`You did it?` becoming `Did you do that?`.

There is also **history leaking into the current translation**:

| Current OCR | Baseline | Context |
|---|---|---|
| `저거` | `that` | `That is what.` |
| `어. 네???` | `Oh yeah ?` | `Oh. Are you doing that?` |
| `그` | `that` | `Are there such monsters in the world?` |

For the last example, the candidate repeats the preceding region's question
instead of translating the short current fragment. This is a model failure,
not missing current text in the context assembly: the current region is
retained after the `Current:` boundary. Training mostly used complete sentences;
the real OCR contains short reactions, stutters and incomplete words. Source
noise and region fragmentation need attention before enabling context globally.
The inspected panel 0007 visibly splits a single speech balloon into separate
OCR regions (`저거` and `아저씨가 한 거야?`), and splits the response and stutter
into additional regions. Correctly assembling utterances inside a balloon is
a more immediate issue than assuming preceding-region context will repair them.

## Reproduction and checks

```powershell
translator/.venv/Scripts/python.exe -X utf8 translator/compare_context_pages.py --output samples/naver-845456-25/context-comparison-10-v2
```

Use a fresh output directory; the script refuses to overwrite an existing
trial. It reuses the frozen OCR, measures fresh translations, renders both image
sets and calls the configured OmniRoute judges. Judge failures are recorded
without discarding generated images. No scraped images are sent to reviewers;
only the short OCR text and translation candidates are sent.

The original sample and active extension model are unchanged. Twenty output
PNGs were validated against source dimensions, blank panels were checked for
pixel equality, and all 30 gallery image links were checked. A three-column
preview of panel 0007 was visually inspected. Python tests: **27 passed**.

Numerical results and raw blind judgments are in
[reports/context-pages-10-v1](reports/context-pages-10-v1/summary.json).
