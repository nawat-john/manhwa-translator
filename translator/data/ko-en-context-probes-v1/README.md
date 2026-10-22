# Synthetic context probes, version 1

160 paired Korean lexical-ambiguity cases: 100 train, 30 validation, 30 test.
Each case has one current sentence and two preceding contexts with different
English lexical senses. Both variants remain in the same split. Training
repeats each training variant twice when combined with the existing dialogue
corpus; held-out variants are never repeated into training.

Gemini writes cases and NVIDIA reviews both translations and the validity of
the ambiguity. No case is human-reviewed. This is a narrow synthetic diagnostic,
not a benchmark establishing accuracy on real Korean webtoons.

Normalized exact current sentences are excluded against every split of the
original corpus and globally within this corpus. The existing deduper also
excludes character-trigram Jaccard >= .9 near duplicates for normalized strings
of at least 12 characters. Shorter strings receive exact deduplication only.
Lexical families and construction patterns can overlap across splits.

`manifest.json` records file hashes; `batch-provenance.jsonl` records model
responses' metadata and all binary review verdicts, including rejected cases.
Full rejected candidate texts remain in the local ignored batch cache.
See [the experiment protocol](../../docs/CONTEXT.md) for training and evaluation.
