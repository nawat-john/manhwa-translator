# Source-context experiment, 2026-10-22

**Result: a small translation model can use preceding Korean context without
adding model layers, but the gain here is modest and not sufficient to replace
the extension's current model.** The clearest training benefit is translating
only the current sentence instead of also translating the supplied history.

The experiment trains the same 2,359,296 query/value LoRA parameters on the
trimmed M2M100 base, with a 128-token source budget and up to three preceding
Korean turns. There are no previous English translations or future turns.
Three epochs on 5,400 examples took 909 seconds (15 minutes); validation loss
was 3.0807 before training and 1.6287, 1.5430 and 1.4962 after each epoch.
Epoch three was selected using validation loss, before test evaluation.

## Translation quality

The original 500 synthetic reference test sentences mostly do not require
context. BLEU/chrF++ are corpus similarity scores, not accuracy percentages.
The two old baselines reuse their frozen FP32 predictions from the first
experiment; the new model's predictions were generated for this experiment.

| Model/input | BLEU | chrF++ |
|---|---:|---:|
| Trimmed baseline, current sentence | 10.51 | 30.59 |
| Previous sentence LoRA, current sentence | 21.90 | 42.34 |
| New context LoRA, empty history | 21.30 | 41.75 |
| New context LoRA, preceding history | 21.82 | 42.40 |

Context adds 0.65 chrF++ over the same new model with empty history. Against
the previous sentence LoRA, overall quality on this test is essentially
unchanged (+0.05 chrF++, -0.08 BLEU).

## Does it actually respond to context?

Thirty fresh held-out pairs each have one identical current Korean sentence
and two preceding contexts selecting different lexical senses (60 variants).
The ranking diagnostic compares mean teacher-forced loss for the intended
English reference and the alternative sense. It does **not** measure whether
free generation produces a correct full translation. Without context, one
reference is preferred for both variants, giving 50% and zero pairs with both
variants ranked correctly.

| Model/input | Intended reference preferred, all 60 | Both variants correct, /30 | Reviewer-agreement subset, /32 |
|---|---:|---:|---:|
| Trimmed baseline, no history | 30 | 0 | 16 |
| Trimmed baseline, untrained context prefix | 37 | 7 | 19 |
| Previous sentence LoRA, no history | 30 | 0 | 16 |
| Previous sentence LoRA, untrained context prefix | 35 | 7 | 20 |
| New context LoRA, empty history | 30 | 0 | 16 |
| New context LoRA, correct history | 38 | 8 | 22 |
| New context LoRA, shuffled unrelated history | 34 | 5 | 19 |

The existing model already responds to context in its encoder. Training this
adapter adds little to the full-set ranking score over simply supplying a
prefix, but teaches the output format: literal `Context:`/`Current:` markers
appear in 58/60 trimmed-baseline prefix outputs, 60/60 old sentence-LoRA prefix
outputs, and 0/60 new context-LoRA outputs. This marker count is a formatting
diagnostic; its absence does not guarantee that every output excludes history.

Actual held-out example, `배가 엄청 크네요.`:

| Preceding context | New model output |
|---|---|
| Looking at a boat on the sea | `The boat is so big.` |
| Looking at a pregnant friend | `Your stomach is so big.` |
| Empty history, for either case | `The stomach is extremely large.` |

This demonstrates a noun-sense change, not a guarantee about pronouns or full
translation fidelity. Another held-out example changes `leg` to `bridge`
after a flood context. Failures remain: `말이 참 예쁘네요` produces
`The horse is so beautiful.` for both the words and horse contexts.

## Reference quality limits

Gemini generated all new cases and NVIDIA reviewed them before splitting.
An independent MiniMax audit, blind to model predictions, agreed on only
16/30 held-out pairs. Both full-set and agreement-subset scores are retained;
no test cases were relabeled, no checkpoints were chosen using test scores,
and no retraining followed the audit.

**Even agreement between two AI reviewers is not ground truth.** The agreement
subset still contains questionable references such as `It took an hour to cut
through the night.` The scores above are exploratory diagnostics, not a validated
Korean semantic benchmark. Lexical families and construction patterns also
overlap between training and test. A Korean human review or independently
curated references are needed before claiming a general accuracy improvement.

## Speed and size

The primary timing experiment alternates empty/correct history on the **same
merged FP32 model**, 30 inputs with preceding turns, three passes (90 timings
per condition), batch one and five beams. It uses the existing runtime
translator and includes tokenization, generation and decoding.

| History | Median ms/input | Mean ms/input |
|---|---:|---:|
| Empty | 458.7 | 498.2 |
| Up to three preceding Korean turns | 465.2 | 492.7 |

Median latency increases 1.4% (+6.5 ms); the mean decreases 1.1%. This small,
mixed difference does not establish a stable slowdown. Generated output can
change length, and the laptop's absolute timings drifted during sustained GPU
use; the interleaved comparison is more useful than comparing against the
previous experiment's milliseconds. These are local CUDA backend measurements,
not Chrome WebGPU or full-page timings. Loading, history assembly, OCR,
inpainting and rendering are excluded.

After merging there are still 424,596,480 model parameters. The saved adapter
is 9,457,520 bytes and adds no adapter modules at merged inference. PyTorch
peak live allocation during evaluation was approximately 1.76 GB with empty
history and 1.78 GB with history; these peaks exclude the CUDA driver and other
Windows applications and are not a fixed per-input memory guarantee.

## Real OCR and recommendation

The existing 24 OCR regions were also translated in top/left reading order.
History changes 17/24 outputs, but there are no reliable reference translations
for this small noisy sample. Some phrasing improves (`Did you do that you did?`
becomes `Did you do that?`); serious errors remain, including
`Wizards in the world are the magic jackets.` with or without history.
Changing outputs does not establish a real-webtoon accuracy improvement.
Scene boundaries and speaker identities are not detected in this experiment.

Keep the extension baseline active. This is a useful prototype of bounded
source context, not LLM-style reasoning or chapter memory. Before another
training experiment, improve context-reference quality and add a separate
properly transcribed webtoon evaluation set, including OCR fragments. Preserve
these test results instead of choosing another checkpoint against this test.

Reproduction: [CONTEXT.md](CONTEXT.md). Raw outputs, timing samples, audit and
metadata: [reports/context-v1](../reports/context-v1/summary.json). Local adapter:
`models/ko-en-context-lora-v1/best/` (ignored by Git). The extension's active
model and runtime were not changed.
