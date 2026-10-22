"""Separate decoding cost from changes in generated translation length."""
import json
import statistics
import time

import torch
from peft import PeftModel
from transformers import M2M100ForConditionalGeneration, M2M100Tokenizer

from train_dialogue_lora import BASE, DATA, OUT


def main():
    torch.set_num_threads(4)
    tokenizer = M2M100Tokenizer.from_pretrained(BASE / 'original-tokenizer', src_lang='ko')
    keep = torch.tensor(json.loads((BASE / 'id-map.json').read_text())['new_to_old'], device='cuda')
    mapping = torch.full((128112,), -1, device='cuda', dtype=torch.long)
    mapping[keep] = torch.arange(len(keep), device='cuda')
    rows = [json.loads(line) for line in (DATA / 'test.jsonl').read_text(encoding='utf-8').splitlines()[:20]]
    inputs = [tokenizer(r['korean'], return_tensors='pt').to('cuda') for r in rows]
    for batch in inputs:
        batch['input_ids'] = mapping[batch['input_ids']]
        assert (batch['input_ids'] >= 0).all()
    results = {}
    for name in ('trimmed', 'lora_merged'):
        model = M2M100ForConditionalGeneration.from_pretrained(BASE, local_files_only=True).eval().to('cuda')
        if name == 'lora_merged':
            model = PeftModel.from_pretrained(model, OUT / 'best').merge_and_unload().eval()
        durations = []
        with torch.inference_mode():
            for repeat in range(4):
                for batch in inputs:
                    torch.cuda.synchronize()
                    started = time.perf_counter()
                    ids = model.generate(**batch, forced_bos_token_id=int(mapping[tokenizer.get_lang_id('en')]),
                                         min_new_tokens=32, max_new_tokens=32,
                                         num_beams=5, no_repeat_ngram_size=3)
                    torch.cuda.synchronize()
                    assert ids.shape[1] == 33
                    if repeat:
                        durations.append(time.perf_counter() - started)
        results[name] = {'median_seconds': statistics.median(durations), 'timings_seconds': durations}
        print(name, results[name]['median_seconds'], flush=True)
        del model
        torch.cuda.empty_cache()
    (OUT / 'fixed-length-benchmark.json').write_text(json.dumps(results, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
