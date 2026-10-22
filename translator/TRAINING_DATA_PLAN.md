# Korean → English LoRA: first full corpus

## Recommended quantity

Start with **5,000 accepted training pairs**, **500 validation pairs**, and
**500 test pairs**. This is an engineering starting point for adapting an
already-trained translation model to spoken webtoon-style text, not a proven
optimal dataset size for M2M100. The 21-pair pilot is only a pipeline check.

The first training experiment should compare nested 1,000-, 3,000- and 5,000-pair
subsets against the same unchanged base and evaluation sets. Expand toward
10,000–20,000 only if quality continues to improve. More automatically generated
text is not a substitute for correcting noisy translations.

All 6,000 labels in this run are synthetic, including the two held-out splits.
They can measure fit to teacher style but cannot establish real-world translation
quality. A separate 300–500-pair, human-reviewed set from unseen episodes/works
is still needed before claiming that LoRA improves the product.

## Coverage and filtering

- 24 topic families: daily conversation, family, school, work, romance, fantasy,
  action, mysteries, gaming, shopping, travel and related webtoon situations.
- Casual banmal, polite dialogue, respectful speech and slang/interjections.
- 12 intent families including negation/refusal, correction, uncertainty,
  surprise, sarcasm, requests, apologies and urgent warnings.
- 16 conversations per API generation × 4 short turns = 64 candidate pairs.
- Each conversation is assigned to one split before generation. Topics can occur
  in multiple splits; complete conversations never cross splits.
- Independent reviewer checks each Korean line without assuming context. It
  rejects added events, gender, relationships, incorrect numbers/negation and
  unnatural phrasing. Reviewer acceptance is not human reference validation.
- NFKC-normalized source duplicates are excluded globally, as are character
  trigram near duplicates with Jaccard similarity >= 0.9 for longer lines.
  This is a textual similarity filter, not a semantic deduplication guarantee.
- Pilot source lines are excluded, including the pilot's held-out examples.
- Source and target must fit the installed trimmed vocabulary and be <=128
  tokens each. Pairs producing the original tokenizer's unknown token are also
  excluded; they must not silently become unknown labels during LoRA training.
  All labels remain text; actual training must apply the matching
  token ID map and keep padded loss labels at -100.

## Generation and operational limits

The working writer is Gemini 3.1 Flash Lite through OmniRoute. The bulk reviewer
is NVIDIA Nemotron 3.5 Super VL 120B A12B, with thinking disabled for this bounded
classification task and strict boolean JSON output enabled. Original generation,
reviews, model IDs and usage are retained per batch. No paid model fallback is
configured in the script.

Expect roughly 100–150 successful generation/review batches depending on
rejections and duplicates, not just 6,000/64 calls. Network or quota errors
retain completed generation for resume. HTTP 429 Retry-After is respected;
repeated failures stop the run rather than repeatedly hammering a provider.
The script uses at most three concurrent batch workers. It requests a boolean
decision for each exact pair ID; missing IDs or string-valued booleans are
rejected. Bulk verdicts do not include a free-text explanation.

The first 30B reviewer failed 5 of 20 AI-authored consistency controls and
sometimes rejected faithful references to an exam even when 시험 was explicit.
Its verdicts were discarded. The final 120B reviewer passed all 20 shuffled
controls. All saved source generations were retained and reviewed afresh under
the calibrated prompt. The controls are not a human evaluation benchmark and
their Korean source lines are excluded from the corpus.

Adding keys does not necessarily increase quota: [Gemini applies rate limits
per project, not per API key](https://ai.google.dev/gemini-api/docs/rate-limits).
[OpenRouter's free-model quota](https://openrouter.ai/docs/api-reference/limits)
also needs to be checked against the account's available allowance. This run
uses the configured provider access and does not create accounts or keys.

```powershell
translator/.venv/Scripts/python.exe -X utf8 translator/build_dialogue_corpus.py --out translator/work/dialogue-corpus-6k-v2 --workers 3
```

Rerun the same command to resume. Corpus configuration and prompts must match
the saved `config.json`. Progress is in `work/dialogue-corpus-6k-v2/manifest.json`;
raw and reviewed batches are in `work/dialogue-corpus-6k-v2/batches/`. Generated
models, raw logs and credentials remain outside Git. The completed and audited
[6,000-pair corpus](data/ko-en-dialogue-6k-v1/README.md) is versioned under `data/`.
It contains exactly 5,000 training, 500 validation and 500 test pairs, from
6,272 reviewed candidates. Unknown/removed tokens and cross-split conversation
overlap are zero after the final audit.

No LoRA training is part of this data-generation run.
