"""Interleave context/no-context timings to reduce run-order and thermal bias."""
import hashlib
import json
import statistics
import time

import torch
from peft import PeftModel
from transformers.utils import logging

from context_data import CONTEXT_OUT, conversation_rows, read_rows, source_with_context
from korean_translation import KoreanTranslator
from train_dialogue_lora import DATA


def main():
    logging.set_verbosity_error()
    torch.set_num_threads(4)
    translator = KoreanTranslator('cuda')
    translator.model = PeftModel.from_pretrained(translator.model, CONTEXT_OUT / 'best').merge_and_unload().eval()
    rows = [r for r in conversation_rows(read_rows(DATA / 'test.jsonl'), translator.tokenizer) if r['previous']][:30]
    inputs = [{mode: source_with_context(r['current_korean'], [] if mode == 'empty' else r['previous'], translator.tokenizer)
               for mode in ('empty', 'previous')} for r in rows]
    for mode in ('empty', 'previous'):
        translator.translate(inputs[0][mode])
    timings = {'empty': [], 'previous': []}
    predictions = {mode: {} for mode in timings}
    for repeat in range(3):
        for i, batch in enumerate(inputs):
            order = ['empty', 'previous'] if (i + repeat) % 2 else ['previous', 'empty']
            for mode in order:
                torch.cuda.synchronize()
                started = time.perf_counter()
                prediction = translator.translate(batch[mode])
                torch.cuda.synchronize()
                timings[mode].append(time.perf_counter() - started)
                predictions[mode][rows[i]['id']] = prediction
        print(f'Interleaved timing pass {repeat+1}/3', flush=True)
    assert translator.fallback is None, 'Unexpected CPU fallback invalidates timings'
    result = {'precision': 'FP32', 'inputs': len(rows), 'repeats': 3, 'num_beams': 5,
              'max_new_tokens': 160, 'batch_size': 1, 'same_merged_model_for_both': True,
              'adapter_sha256': hashlib.sha256((CONTEXT_OUT / 'best/adapter_model.safetensors').read_bytes()).hexdigest()}
    for mode, durations in timings.items():
        result[mode] = {'median_seconds': statistics.median(durations),
                        'mean_seconds': statistics.mean(durations), 'timings_seconds': durations,
                        'predictions': predictions[mode]}
    result['median_overhead_percent'] = 100 * (result['previous']['median_seconds'] / result['empty']['median_seconds'] - 1)
    (CONTEXT_OUT / 'interleaved-benchmark.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k not in ('empty', 'previous')}), flush=True)


if __name__ == '__main__':
    main()
