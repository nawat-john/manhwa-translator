# Experiments and workflow guides

These documents preserve completed experiments and their limitations. Experimental adapters are not automatically enabled in the extension.

| Topic | Guide | Results |
|---|---|---|
| Model optimization and OCR precision | [Optimization](OPTIMIZATION.md) | [Vocabulary trimming](VOCAB_TRIM.md) |
| Balloon grouping | [Implementation and ten-panel trial](BALLOON-GROUPING-RESULTS.md) | Same document |
| Sentence LoRA | [Training and reproduction](LORA.md) | [Evaluation](LORA-RESULTS.md) |
| Context LoRA | [Protocol](CONTEXT.md) | [Evaluation](CONTEXT-RESULTS.md), [image comparison](CONTEXT-PAGES-RESULTS.md) |
| Training data | [Datasets](DATASETS.md), [generation plan](TRAINING_DATA_PLAN.md) | [6,000-pair corpus](../data/ko-en-dialogue-6k-v1/README.md) |
| Japanese batch/PDF pipeline | [Original workflow](JAPANESE.md) | Local outputs in `translator/output/` |

Raw evidence is in [reports](../reports/). Image galleries, model weights and generated jobs are local artifacts excluded from Git. Commands retain their original working-directory assumptions; the main [translator README](../README.md) uses commands from the project root.
