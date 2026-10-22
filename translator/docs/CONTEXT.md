# Small translation model with source context

This experiment keeps the trimmed M2M100 architecture and rank-16 query/value
LoRA. Input is `Context: <up to three preceding Korean turns>\nCurrent: <Korean>`;
the target contains only the translation of the current turn. There are no
previous English translations, future turns, summaries or speaker identities.
Oldest context is removed until the complete encoder input fits 128 tokens.

The original conversation IDs and turn numbers reconstruct source history
inside each original train/validation/test split. The existing corpus has
mostly self-contained targets, so additional paired lexical-ambiguity cases
provide an explicit reason to use context. A pair has one identical current
sentence, two preceding contexts and two different English lexical senses.
Gemini generates cases, NVIDIA reviews both variants, and token audits reject
unknown/removed tokens. These are synthetic labels, not human ground truth.

The additional corpus has 100 training pairs, 30 validation pairs and 30 test
pairs. Both variants stay in the same split. Exact and very close duplicate
current sentences are excluded globally, including against the original corpus;
lexical families and some construction patterns are shared across splits.
Training variants are repeated twice, making 5,400 training examples, including
5,000 original examples. Validation has 560 examples. AdamW, three epochs,
learning rate 0.0001, batch eight, accumulation four, seed 80421; all other
LoRA settings match the first experiment. Selection uses validation loss only.

Reproduce using the frozen tracked probe files (no API needed):

```powershell
translator/.venv/Scripts/python.exe -X utf8 translator/context_data.py
translator/.venv/Scripts/python.exe -X utf8 translator/train_dialogue_lora.py --data translator/work/ko-en-context-data-v1 --out translator/models/ko-en-context-lora-v1 --batch-size 8
translator/.venv/Scripts/python.exe -X utf8 translator/evaluate_context_lora.py
translator/.venv/Scripts/python.exe -X utf8 translator/audit_context_probes.py
translator/.venv/Scripts/python.exe -X utf8 translator/benchmark_context_lora.py
```

`build_context_probes.py` generates the probe corpus through the configured
OmniRoute gateway. Its batch cache is in `work/context-probes-v1/`; rerunning
generation can replace the frozen corpus and is not needed for reproduction.

Evaluation compares the trimmed baseline, the previous sentence LoRA, and the
new adapter with empty, correct and unrelated shuffled context. All inference
is FP32 with merged adapters, five beams and maximum 160 new tokens. The
original 500 reference test translations are scored separately from the 60
new contextual variants. Prior FP32 baseline predictions are reused for the
original 500 test cases; timings and probe predictions are measured anew.
For the probes, the old models also receive the same context prefix without
context training, to distinguish the effect of supplying context from training
the adapter to translate only the current sentence.
Latency is batch one on the same first 50 regular inputs, three timed passes
after warm-up, synchronized CUDA, including tokenizer/generation/decoding but
excluding loading, source-history assembly, OCR, inpainting and rendering.
GPU peak allocation excludes other Windows applications and driver overhead.

The additional paired timing run alternates empty/correct context on the same
merged model for 30 regular test inputs that have preceding turns, three passes.
It uses the existing runtime translator and reduces run-order/thermal bias.
Both variants include tokenization, generation and decoding. All measurements
are local CUDA backend timings, not Chrome WebGPU measurements.

MiniMax independently audits the 30 held-out reference pairs without seeing
model outputs. Preserve the full-set scores and separately report the subset
where both automated reviewers agree; do not relabel, retrain or select
checkpoints using this audit. Agreement still is not human validation.

The contrastive diagnostic ranks the correct English reference against the
alternative sense using mean teacher-forced token loss. A model ignoring
context necessarily chooses the same reference for both variants and scores
50% (except ties), with zero pairs correct on both variants. This is a ranking
test, not free-generation accuracy. Shuffled contexts come from another test
pair; they can occasionally still be relevant, so this is a noisy negative
control. Inspect actual predictions as well as scores.

Real OCR texts are ordered by panel filename and box top/left position.
They receive up to three previous raw OCR regions; scene boundaries and speaker
changes are not detected in this experiment. OCR errors can therefore propagate.
The existing 24-region sample is diagnostic and is not an independent new test.
No extension runtime or active model selection is changed by this experiment.
