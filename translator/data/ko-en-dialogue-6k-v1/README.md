# Korean → English spoken dialogue: 6k v1

Created 2026-10-22 for a first LoRA experiment on the trimmed M2M100 base.
**Every label is synthetic and none has been reviewed by a human.** The
validation/test sets measure agreement with synthetic references, not verified
translation quality on real webtoons. No LoRA model has been trained yet.

| Split | Pairs | Distinct conversations | Source tokens | Target tokens |
|---|---:|---:|---:|---:|
| [Train](train.jsonl) | 5,000 | 1,293 | 89,351 | 86,787 |
| [Validation](validation.jsonl) | 500 | 128 | 8,553 | 8,360 |
| [Test](test.jsonl) | 500 | 130 | 8,925 | 8,615 |

Training examples average 17.87 Korean input tokens and 17.36 English target
tokens, including language/EOS tokens. All source and target sequences are at
most 33 tokens here, below the 128-token filter limit. Three training epochs
would expose about 528,000 combined source/target tokens.

## Coverage and provenance

Gemini 3.1 Flash Lite generated original dialogues through OmniRoute. NVIDIA
Nemotron 3.5 Super VL 120B A12B independently reviewed each pair using strict
boolean decisions and no assumed missing context. Each conversation was assigned
to exactly one split before generation. Topics can occur across splits.

Requested coverage spans 24 topic families, 12 conversational intents, and four
register groups: banmal, polite conversation, respectful speech, and casual
slang/interjections. Topic/register statistics describe the generation prompts;
they are not independently annotated language labels.

The selected reviewer matched 20/20 AI-authored consistency controls. Some
controls also appear in the reviewer instructions, so this is **not** an
unbiased accuracy score. Pilot and control source texts are excluded from the
corpus. See [the quantity and generation plan](../../TRAINING_DATA_PLAN.md).

## Final audit

98 reviewed batches produced 6,272 candidate pairs. Final filtering excluded:

- 175 pairs containing an original-tokenizer unknown token.
- 14 pairs rejected by the final reviewer.
- 13 normalized duplicates or character-trigram near duplicates.
- 70 surplus pairs after their assigned split reached its target.

These are filter counts, not translation-accuracy estimates. Surplus and
unrepresentable pairs are not necessarily bad translations; their originals and
filter reasons remain in [rejected.jsonl](rejected.jsonl).

An independent final pass verified zero duplicate/near-duplicate sources under
the configured textual rule, zero conversations shared across splits, zero
pilot/control source overlap, zero unknown tokens, and zero removed-vocabulary
tokens. Character similarity filtering cannot guarantee semantic uniqueness.

## Files and training use

`korean` and `english` are the parallel text fields. Other fields record the
conversation, requested scenario, actual generator/reviewer IDs and synthetic
status. Bulk `review.reason` is null because the reviewer was asked for boolean
decisions only; no explanation is fabricated.

- [manifest.json](manifest.json): split statistics, filter counts, audit results,
  tokenizer/ID-map hashes, generator-code commit and data-file SHA-256 hashes.
- [config.json](config.json): targets, teacher IDs, seed and prompt digest.
- [batch-provenance.jsonl](batch-provenance.jsonl): 98 task definitions and the
  cached generation/review metadata and usage. Failed, discarded or calibration
  attempts are not included in those usage totals.

Use the same trimmed base and saved tokenizer/ID mapping during LoRA training.
Tokenize Korean sources and English targets with M2M100 language/EOS conventions,
remap both, and preserve -100 padding masks. Scenario/provenance fields are not
translation input. Keep validation/test out of training. Use validation for
model selection and reserve test for final reporting. Files use UTF-8 and LF line endings so Git
checkout preserves their recorded data hashes.

Start with nested 1k/3k/5k training subsets and the same evaluation sets before
considering 10k–20k. A separate human-reviewed set from unseen works is still
needed before claiming better real-world translation.
