"""Compare the original, trimmed and merged LoRA with identical decoding."""
import gc
import json
import statistics
import time

import torch
from peft import PeftModel
from sacrebleu.metrics import BLEU, CHRF
from transformers import M2M100ForConditionalGeneration, M2M100Tokenizer

from train_dialogue_lora import BASE, DATA, HERE, OUT
from korean_translation import REVISION


def main():
    torch.set_num_threads(4)
    rows = [json.loads(line) for line in (DATA / 'test.jsonl').read_text(encoding='utf-8').splitlines()]
    ocr_path = HERE.parent / 'samples/naver-845456-25/english-panels-10/ocr.json'
    real = [region['korean'] for page in json.loads(ocr_path.read_text(encoding='utf-8')) for region in page['regions']]
    tokenizer = M2M100Tokenizer.from_pretrained(BASE / 'original-tokenizer', src_lang='ko')
    keep = torch.tensor(json.loads((BASE / 'id-map.json').read_text())['new_to_old'], device='cuda')
    mapping = torch.full((128112,), -1, dtype=torch.long, device='cuda')
    mapping[keep] = torch.arange(len(keep), device='cuda')
    results = {}
    for name in ('original', 'trimmed', 'lora_merged'):
        model = M2M100ForConditionalGeneration.from_pretrained(
            HERE / f'hf-cache/hub/models--facebook--m2m100_418M/snapshots/{REVISION}' if name == 'original' else BASE,
            local_files_only=True).eval().to('cuda')
        if name == 'lora_merged':
            model = PeftModel.from_pretrained(model, OUT / 'best').merge_and_unload().eval()
        english = tokenizer.get_lang_id('en')
        if name != 'original':
            english = int(mapping[english])

        def translate(text):
            batch = tokenizer(text, return_tensors='pt').to('cuda')
            if name != 'original':
                batch['input_ids'] = mapping[batch['input_ids']]
                assert (batch['input_ids'] >= 0).all()
            with torch.inference_mode():
                ids = model.generate(**batch, forced_bos_token_id=english,
                                     num_beams=5, max_new_tokens=160, no_repeat_ngram_size=3)[0]
            if name != 'original':
                ids = keep[ids]
            return tokenizer.decode(ids, skip_special_tokens=True).strip()

        translate(rows[0]['korean'])
        predictions = []
        for i, row in enumerate(rows):
            predictions.append(translate(row['korean']))
            if (i + 1) % 50 == 0:
                print(f'{name}: {i+1}/{len(rows)}', flush=True)
        timings = []
        for _ in range(3):
            for row in rows[:50]:
                torch.cuda.synchronize()
                started = time.perf_counter()
                translate(row['korean'])
                torch.cuda.synchronize()
                timings.append(time.perf_counter() - started)
        refs = [[r['english'] for r in rows]]
        results[name] = {'bleu': BLEU().corpus_score(predictions, refs).score,
                         'chrf_plus_plus': CHRF(word_order=2).corpus_score(predictions, refs).score,
                         'median_seconds': statistics.median(timings),
                         'mean_seconds': statistics.mean(timings),
                         'p95_seconds': sorted(timings)[int(len(timings)*0.95)-1],
                         'predictions': predictions, 'timings_seconds': timings}
        results[name]['real_ocr'] = [{'korean': text, 'english': translate(text)} for text in real]
        (OUT / 'evaluation.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({name: {k:v for k,v in results[name].items() if k not in ('predictions','timings_seconds')}}), flush=True)
        del model
        gc.collect()
        torch.cuda.empty_cache()


if __name__ == '__main__':
    main()
