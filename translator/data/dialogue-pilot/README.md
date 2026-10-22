# Synthetic Korean → English pilot

Generated 2026-10-22 through local OmniRoute. Writer: Gemini 3.1 Flash Lite.
Independent model reviewer: MiniMax M3.1 Flash via OpenRouter's free endpoint.

32 pairs were generated in 8 conversations. The model reviewer accepted all 32;
an additional Codex assistant audit excluded 3 training pairs for unnatural
phrasing or added meaning. Final counts: **train 21 / validation 4 / test 4**;
3 originals are preserved in `rejected.jsonl` with the additional audit reason.

All labels are synthetic and **none are human-reviewed**. This is a pipeline
smoke test, not a sufficient LoRA corpus or a trustworthy quality benchmark.
Whole conversations are assigned to one split. The original model reviews
remain unchanged so the limits of automatic quality filtering are visible.

- `manifest.json`: counts, actual model IDs, usage, limitations.
- `train.jsonl`, `validation.jsonl`, `test.jsonl`: final accepted examples.
- `rejected.jsonl`, `assistant-audit.json`: pairs held for correction and reasons.
- `generated.json`, `generation.json`, `reviews.json`: original generation/review provenance.
- `vocab-audit.json`: all 32 generated pairs, both source and target, use the
  installed 70,193-token base without missing tokens.

The first Pro reviewer request hit quota (429); the old Flash reviewer endpoint
was unavailable (404). Generation was retained and reviewed through MiniMax
without regenerating it. `generation.json` metadata was recovered from the
successful local gateway call log after that initial reviewer failure.

Regenerate new pilots with [generate_dialogue_data.py](../../generate_dialogue_data.py).
Use a new output directory. If only review fails, use `--resume` with the same
writer and another available reviewer; the script does not call the generator
again. API keys and router storage are excluded from this dataset and Git.
