"""Evaluate source-context LoRA, including identical-current counterfactual pairs."""
import gc
import json
import statistics
import time

import torch
from peft import PeftModel
from sacrebleu.metrics import BLEU, CHRF
from transformers import M2M100ForConditionalGeneration, M2M100Tokenizer
from transformers.utils import logging

from context_data import CONTEXT_OUT, PROBES, conversation_rows, read_rows, source_with_context
from train_dialogue_lora import BASE, DATA, HERE, OUT


def metrics(predictions, references):
    return {'bleu': BLEU().corpus_score(predictions, [references]).score,
            'chrf_plus_plus': CHRF(word_order=2).corpus_score(predictions, [references]).score}


def main():
    logging.set_verbosity_error()
    torch.set_num_threads(4)
    tokenizer = M2M100Tokenizer.from_pretrained(BASE / 'original-tokenizer', src_lang='ko', tgt_lang='en')
    regular = conversation_rows(read_rows(DATA / 'test.jsonl'), tokenizer)
    probes = read_rows(PROBES / 'test.jsonl')
    ocr = json.loads((HERE.parent / 'samples/naver-845456-25/english-panels-10/ocr.json').read_text(encoding='utf-8'))
    real = [r['korean'] for page in sorted(ocr, key=lambda p: p['source'])
            for r in sorted(page['regions'], key=lambda r: (min(p[1] for p in r['box']), min(p[0] for p in r['box'])))]
    keep = torch.tensor(json.loads((BASE / 'id-map.json').read_text())['new_to_old'], device='cuda')
    mapping = torch.full((128112,), -1, dtype=torch.long, device='cuda')
    mapping[keep] = torch.arange(len(keep), device='cuda')
    english = int(mapping[tokenizer.get_lang_id('en')])
    results = {}
    cached = json.loads((OUT / 'evaluation.json').read_text(encoding='utf-8'))
    original_order = [r['id'] for r in read_rows(DATA / 'test.jsonl')]
    for model_name, adapter in [('trimmed', None), ('sentence_lora', OUT / 'best'), ('context_lora', CONTEXT_OUT / 'best')]:
        model = M2M100ForConditionalGeneration.from_pretrained(BASE, local_files_only=True).eval().to('cuda')
        if adapter:
            model = PeftModel.from_pretrained(model, adapter).merge_and_unload().eval()

        def inputs(text):
            batch = tokenizer(text, return_tensors='pt').to('cuda')
            assert (batch['input_ids'] != tokenizer.unk_token_id).all()
            batch['input_ids'] = mapping[batch['input_ids']]
            assert (batch['input_ids'] >= 0).all()
            return batch

        def translate(text):
            with torch.inference_mode():
                ids = model.generate(**inputs(text), forced_bos_token_id=english, num_beams=5,
                                     max_new_tokens=160, no_repeat_ngram_size=3)[0]
            return tokenizer.decode(keep[ids], skip_special_tokens=True).strip()

        def loss(text, target):
            labels = tokenizer(text, text_target=target, return_tensors='pt')['labels'].to('cuda')
            labels = mapping[labels]
            assert (labels >= 0).all()
            with torch.inference_mode():
                return model(**inputs(text), labels=labels, use_cache=False).loss.item()

        modes = ['empty', 'previous', 'shuffled'] if model_name == 'context_lora' else ['raw', 'prefix_context']
        for mode in modes:
            torch.cuda.reset_peak_memory_stats()
            name = model_name if mode == 'raw' else f'context_{mode}' if model_name == 'context_lora' else f'{model_name}_{mode}'

            def source(current, previous):
                return current if mode == 'raw' else source_with_context(current, [] if mode == 'empty' else previous, tokenizer)

            result = {'model': model_name, 'context_mode': mode, 'precision': 'FP32', 'merged': bool(adapter)}
            if mode in ('raw', 'empty', 'previous'):
                if mode == 'raw':
                    saved = cached['trimmed' if model_name == 'trimmed' else 'lora_merged']['predictions']
                    by_id = dict(zip(original_order, saved))
                    predictions = [by_id[r['id']] for r in regular]
                    result['regular_predictions_reused_from_v1'] = True
                else:
                    predictions = []
                    for i, row in enumerate(regular):
                        predictions.append(translate(source(row['current_korean'], row['previous'])))
                        if (i + 1) % 50 == 0:
                            print(f'{name}: regular {i+1}/{len(regular)}', flush=True)
                result['regular'] = {**metrics(predictions, [r['english'] for r in regular]), 'predictions': predictions}
                result['regular']['mean_input_tokens'] = statistics.mean(
                    len(tokenizer(source(r['current_korean'], r['previous']))['input_ids']) for r in regular)
                result['regular']['mean_output_words'] = statistics.mean(len(p.split()) for p in predictions)
                translate(source(regular[0]['current_korean'], regular[0]['previous']))
                durations = []
                for _ in range(3):
                    for row in regular[:50]:
                        text = source(row['current_korean'], row['previous'])
                        torch.cuda.synchronize()
                        started = time.perf_counter()
                        translate(text)
                        torch.cuda.synchronize()
                        durations.append(time.perf_counter() - started)
                result['latency'] = {'median_seconds': statistics.median(durations),
                                     'mean_seconds': statistics.mean(durations), 'timings_seconds': durations}
                result['real_ocr'] = [{'korean': text, 'previous': real[max(0, i-3):i],
                                       'english': translate(source(text, real[max(0, i-3):i]))}
                                      for i, text in enumerate(real)]
            cases = []
            both = 0
            for i, probe in enumerate(probes):
                decisions = []
                memo = {}
                for v, variant in enumerate(probe['variants']):
                    previous = variant['previous']
                    if mode == 'shuffled':
                        previous = probes[(i + 7) % len(probes)]['variants'][v]['previous']
                    text = source(probe['current'], previous)
                    if text not in memo:
                        memo[text] = (translate(text), [loss(text, t['english']) for t in probe['variants']])
                    prediction, scores = memo[text]
                    correct = scores[v] < scores[1-v]
                    decisions.append(correct)
                    cases.append({'id': f"{probe['id']}-{v}", 'current': probe['current'],
                                  'previous': previous, 'reference': variant['english'], 'prediction': prediction,
                                  'correct_loss': scores[v], 'alternative_loss': scores[1-v], 'rank_correct': correct})
                both += all(decisions)
            result['probes'] = {**metrics([c['prediction'] for c in cases], [c['reference'] for c in cases]),
                                'contrastive_accuracy': sum(c['rank_correct'] for c in cases) / len(cases),
                                'both_variants_correct_pairs': both, 'pairs': len(probes), 'cases': cases}
            result['peak_cuda_allocated_bytes'] = torch.cuda.max_memory_allocated()
            results[name] = result
            (CONTEXT_OUT / 'evaluation.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps({'name': name, 'probes_accuracy': result['probes']['contrastive_accuracy'],
                              'both_correct': both, 'median_seconds': result.get('latency', {}).get('median_seconds')}), flush=True)
        del model
        gc.collect()
        torch.cuda.empty_cache()


if __name__ == '__main__':
    main()
