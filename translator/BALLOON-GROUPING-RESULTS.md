# Balloon grouping on the first ten panels

Implemented in the shared OCR pipeline, so new extension translations also use it.
White connected components above RGB 200 identify enclosed balloon interiors.
Fragments assigned predominantly to the same enclosed component are joined in top-to-bottom order.
Components touching the page boundary are excluded to avoid merging unrelated text through white page backgrounds.
No new models or dependencies are required. Existing OCR paragraph grouping remains in place.

Merged regions retain original OCR boxes for erasure, plus the enclosing contour to remove punctuation missed by OCR.
Rendering uses an interior rectangle with a limited height/width ratio so text avoids narrow connections between lobes.
Joined balloons now receive one translation in one lobe; other lobes can remain empty.
Old translation caches that would change grouping are rejected rather than silently reused or overwritten.
The default sample output is now `english-balloon-panels-10`, preserving the old trial.
The context comparison script also groups OCR before translation when run again; previous reports remain unchanged.

## Actual trial

Sources: unchanged `samples/naver-845456-25/panels/0000.png` through `0009.png`.
Reused the frozen EasyOCR output, then translated the joined text using the active trimmed M2M100 baseline, without LoRA.
Final images and comparison gallery: `samples/naver-845456-25/balloon-merged-10-v2/index.html`.
The v2 render reused v1 translations after asserting every grouped Korean input was identical; it changes layout/erasure only.

| Panel | Before | After |
|---|---:|---:|
| 0000 | 1 | 1 |
| 0001 | 6 | 2 |
| 0002 | 1 | 1 |
| 0003 | 0 | 0 |
| 0004 | 1 | 1 |
| 0005 | 0 | 0 |
| 0006 | 1 | 1 |
| 0007 | 5 | 2 |
| 0008 | 4 | 4 |
| 0009 | 5 | 3 |
| Total | 24 | 15 |

For example, `저거` + `아저씨가 한 거야?` becomes one input and translates to `Did you do that?`.
The lower balloon's `어. 네??? 마 맞아요` still becomes the incorrect `Oh yeah? not right.`.
Grouping fixes fragmentation, not OCR spelling, missing punctuation, or the translation model's handling of stutters.
No Korean-speaking reviewer checked these translations, so this is not an accuracy claim.

Grouping alone took 0.389 / 0.393 / 0.385 seconds for all ten in-memory RGB images on this machine.
This excludes OCR, file reads, translation and rendering; it is not an end-to-end speed comparison.

Checks: 29 unit tests passed, including same-balloon joining, separate-balloon isolation, open-background rejection,
safe rendering bounds and idempotence. All ten grouped sample records were also checked for idempotence.
Ten final PNGs retain source dimensions, and the two panels without OCR retain their pixels.
Rendered panels 0001 and 0007 were visually inspected after the layout/erasure correction.

Limits: dark/colored/open balloons fall back to existing regions. Enclosed white areas are a heuristic,
not a learned balloon detector. This has not been exercised interactively in Chrome or across the entire episode.
