# Korean conversational LoRA

Install `requirements-lora.txt` into the existing translator virtual environment.
The existing CUDA PyTorch installation must remain installed.

```powershell
translator/.venv/Scripts/python.exe -X utf8 translator/train_dialogue_lora.py
translator/.venv/Scripts/python.exe -X utf8 translator/evaluate_dialogue_lora.py
translator/.venv/Scripts/python.exe -X utf8 translator/judge_dialogue_lora.py
translator/.venv/Scripts/python.exe -X utf8 translator/benchmark_lora_decode.py
```

Training uses `data/ko-en-dialogue-6k-v1/train.jsonl` (5,000 pairs) and chooses
the best of three epochs using the separate 500-pair validation split.
It freezes the trimmed M2M100 base and trains rank-16 query/value LoRA adapters
(alpha 32, dropout 0.05, AdamW learning rate 0.0001, batch 8, accumulation 4).
Both source and target IDs are remapped to the trimmed vocabulary. Target padding
is excluded from loss. CUDA FP16 autocast, gradient scaling and gradient
checkpointing fit training onto the 4 GB RTX 3050 Laptop GPU.

Artifacts are local and ignored by Git: `models/ko-en-dialogue-lora-v1/`.
`best/` contains the selected adapter, not a standalone translation model.
Training again overwrites this experiment's checkpoints; preserve the directory
before starting another experiment.

Evaluation compares pinned original M2M100, the trimmed baseline, and the selected
adapter merged into the trimmed model, all in FP32 with batch-one decoding:
five beams, maximum 160 new tokens, no repeated trigrams. Test references are
used only after checkpoint selection. Scores are corpus BLEU and chrF++.
Latency excludes model loading and includes tokenization, GPU generation and
decoding. After warm-up, the same first 50 test inputs are timed three times;
CUDA is synchronized around each measurement. OCR and rendering are excluded.
Actual generated lengths can differ between models.

The additional fixed-length benchmark generates exactly 32 new tokens per input
with five beams on the first 20 test inputs, one warm-up pass and three timed
passes. It excludes tokenization and decoding and is diagnostic, not normal
translation latency.

The blind judge sees Korean and randomly assigned A/B translations, without
model identities or reference answers. It compares a fixed random sample of
100 test pairs and the existing first-ten-panel OCR texts. The free MiniMax
judge is different from the Gemini data writer and NVIDIA data reviewer.
Its answers are estimates, not Korean human review. Corpus scores against
synthetic references measure agreement with the synthetic teacher and cannot
establish general translation accuracy. The small OCR sample is diagnostic,
especially where recognition has already truncated a word.

The experiment does not change which model the extension server loads.
