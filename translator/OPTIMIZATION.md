# Current Korean → English runtime and synthetic-data pilot

Updated 2026-10-22. The pipeline now uses the installed trimmed MT base and FP16
EasyOCR on CUDA. CPU OCR retains FP32. Original model files are preserved.

## Translation base for LoRA

`models/m2m100-ko-en/` contains the verified 70,193-token base from
[the trimming experiment](VOCAB_TRIM.md): 237 MB less FP32 parameter storage.
The filter retains Latin/Hangul pieces, shared punctuation, numbers, symbols,
special tokens and calibration input pieces. Latin pieces are shared with other
languages, so this is a conservative reduction, not a linguistic partition of
all English and Korean words.

`korean_translation.py` maps original tokenizer IDs into the trimmed model and
maps generated IDs back. The English language ID is mapped as well. A source
containing a removed token (e.g. Hanja) uses the original model on CPU rather
than losing text. This rare fallback consumes additional RAM and is slower.
On a fresh checkout without the trimmed artifact, the original model is used.

For a fresh local trimmed installation, run `experiment_vocab_trim.py` into a
new output directory and copy its complete `translation/` directory to
`models/m2m100-ko-en/` (destination must not exist). Keep its model, tokenizer
and `id-map.json` together. Model artifacts remain outside Git.

LoRA must train against this same base and mapping. Tokenize both Korean inputs
and English targets with the saved original tokenizer, map their IDs, retain
the normal M2M100 language/EOS conventions, and keep padded label positions at
`-100`. Do not map the `-100` loss mask as a vocabulary index. Missing training
tokens must be rejected or addressed before training; LoRA cannot restore
deleted vocabulary rows. No LoRA training has been started yet.

## OCR precision results

Charset remains **1,008 characters**. `ocr_precision.py` converts detector and
recognizer weights and floating inputs to FP16; integer label IDs remain integer.
Outputs return to FP32 before EasyOCR's softmax, normalization and OpenCV
postprocessing. The wrapper does not modify site-packages.

On the RTX 3050 Laptop, all 10 panels had identical text to FP32, stable across
three passes per precision. Whole-OCR median time over 10 panels was
**3.987 → 2.994 seconds (24.9% less time)**. Peak allocated CUDA memory was
**1,388.58 → 928.77 MB**. Exported detector+recognizer checkpoints total
**99.23 → 49.66 MB**. Runtime currently loads the original EasyOCR checkpoints
and converts them in memory; the exported half checkpoints are experiment
artifacts, not replacements for EasyOCR's MD5-verified downloads.

Details: [OCR report](work/ocr-fp16/report.json).
This checks output agreement on one episode, not accuracy on unseen font styles.

## OmniRoute synthetic data

Local installation: OmniRoute 3.8.52, configured Gemini and OpenRouter providers.
The service was started on loopback at `http://127.0.0.1:20128`.
The user-supplied project `.env` key authenticated successfully. A real
[32-pair pilot](data/dialogue-pilot/README.md) was generated and reviewed:
21 training, 4 validation, 4 test pairs, and 3 held for correction after an
additional assistant audit. No LoRA training has started.

Put a valid **OmniRoute client API key** in the project `.env`, which Git ignores:

```dotenv
OMNIROUTE_BASE_URL=http://127.0.0.1:20128/v1
OMNIROUTE_API_KEY=your-local-gateway-key
```

Use model IDs from the authenticated `/v1/models` endpoint. The successful writer
was `gemini/gemini-3.1-flash-lite`; the successful reviewer was
`openrouter/minimax/minimax-m3.1-flash:free`. The Pro reviewer hit quota and
the legacy Flash endpoint returned 404 despite appearing in the catalog. Use
IDs that work with configured providers; catalog presence alone is not proof
of quota or availability. To create another pilot:

```powershell
translator/.venv/Scripts/python.exe -X utf8 translator/generate_dialogue_data.py --model gemini/gemini-3.1-flash-lite --review-model openrouter/minimax/minimax-m3.1-flash:free --out translator/work/dialogue-pilot-next
```

The script normally makes two bounded calls: one for 8 original conversations × 4 turns,
then one independent review of the 32 pairs. It checks language, structure,
duplicate Korean lines and complete reviewer coverage; only accepted pairs are
exported. Whole conversations are assigned to train/validation/test, with model
IDs, review verdicts and `synthetic=true`, `human_reviewed=false` recorded on
each example. No scraped webtoon text is sent to either teacher.
If review fails, rerun with `--resume` and the same output directory to reuse
`generated.json` and `generation.json`. Completed pilots cannot be overwritten.

This is a pipeline pilot, not enough training data for a quality claim. Review
samples with a Korean/English speaker before scaling. Keep a separate human
reference test set; using only synthetic references can reward teacher-specific
errors. Check output-use terms of the actual upstream models before scaling
distillation. A local router does not mean the teacher model runs locally.

## Verification

```powershell
translator/.venv/Scripts/python.exe -m unittest discover -s translator -p "test_*.py"
translator/.venv/Scripts/python.exe translator/benchmark_ocr_precision.py --out translator/work/ocr-fp16-next
translator/.venv/Scripts/python.exe -X utf8 translator/translate_korean_sample.py --input samples/naver-845456-25/panels/0007.png --output translator/work/optimized-next
```

A full OCR → trimmed MT → inpaint → render smoke test produced
[the translated image](work/optimized-smoke/0007.png). New extension jobs use the
new pipeline; existing sample caches retain their previous results, so use a
new output directory when comparing model versions.
