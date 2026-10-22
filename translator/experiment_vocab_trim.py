"""Build isolated vocab-trim experiments; never change the extension's models.

The translation artifact keeps the original SentencePiece tokenizer and requires
explicit ID mapping. It is not a drop-in Hugging Face tokenizer/model pair.
"""
import argparse
import gc
import html
import json
import os
from pathlib import Path
import time
import unicodedata

HERE = Path(__file__).resolve().parent
MODEL = 'facebook/m2m100_418M'
REVISION = '55c2e61bbf05dfb8d7abccdc3fae6fc8512fd636'
os.environ['HF_HOME'] = str(HERE / 'hf-cache')
os.environ['HF_HUB_OFFLINE'] = '1'

import cv2
import easyocr
import torch
from easyocr.utils import CTCLabelConverter
from transformers import M2M100ForConditionalGeneration, M2M100Tokenizer
from transformers.models.m2m_100.modeling_m2m_100 import M2M100ScaledWordEmbedding


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def sync():
    if torch.cuda.is_available():
        torch.cuda.synchronize()


def timed(call):
    sync()
    start = time.perf_counter()
    result = call()
    sync()
    return result, time.perf_counter() - start


def allowed_piece(piece):
    # Keep Latin/Hangul plus punctuation, symbols and numbers, including mixed names.
    return all(not ch.isalpha() or any(script in unicodedata.name(ch, '')
               for script in ('LATIN', 'HANGUL')) for ch in piece.replace('▁', ''))


def remap_inputs(ids, old_to_new):
    mapped = old_to_new[ids]
    if (mapped < 0).any():
        raise ValueError('Input contains a removed token; use the original model')
    return mapped


def generate(model, tokenizer, text, device, old_to_new=None, new_to_old=None):
    inputs = tokenizer(text, return_tensors='pt').to(device)
    english = tokenizer.get_lang_id('en')
    if old_to_new is not None:
        inputs['input_ids'] = remap_inputs(inputs['input_ids'], old_to_new)
        english = int(old_to_new[english])
    with torch.inference_mode():
        ids = model.generate(**inputs, forced_bos_token_id=english,
                             max_new_tokens=160, num_beams=5, no_repeat_ngram_size=3)[0]
    if new_to_old is not None:
        ids = new_to_old[ids]
    return tokenizer.decode(ids, skip_special_tokens=True).strip()


def translation_experiment(out, records, device):
    tokenizer = M2M100Tokenizer.from_pretrained(MODEL, revision=REVISION, src_lang='ko', local_files_only=True)
    calibration = [r['korean'] for page in records[:5] for r in page['regions']]
    cases = [(i, r['korean']) for i, page in enumerate(records) for r in page['regions']]
    assert calibration and any(i >= 5 for i, _ in cases), 'Need disjoint calibration/evaluation pages'
    keep = {idx for piece, idx in tokenizer.get_vocab().items() if allowed_piece(piece)}
    keep.update(tokenizer.all_special_ids)
    for text in calibration:
        keep.update(tokenizer(text)['input_ids'])
    print('Loading original translation model', flush=True)
    model = M2M100ForConditionalGeneration.from_pretrained(MODEL, revision=REVISION, local_files_only=True).eval().to(device)
    before = sum(p.numel() for p in model.parameters())
    old_size = model.config.vocab_size
    keep = sorted(idx for idx in keep if idx < old_size)
    new_to_old = torch.tensor(keep, device=device)
    old_to_new = torch.full((old_size,), -1, dtype=torch.long, device=device)
    old_to_new[new_to_old] = torch.arange(len(keep), device=device)
    for special in (model.config.bos_token_id, model.config.eos_token_id, model.config.pad_token_id,
                    model.config.decoder_start_token_id, tokenizer.get_lang_id('en'), tokenizer.get_lang_id('ko')):
        assert int(old_to_new[special]) >= 0
    assert model.get_input_embeddings().weight.data_ptr() == model.get_output_embeddings().weight.data_ptr()
    generate(model, tokenizer, calibration[0], device)
    if device == 'cuda':
        torch.cuda.reset_peak_memory_stats()
    baseline = []
    for i, text in cases:
        answer, seconds = timed(lambda: generate(model, tokenizer, text, device))
        baseline.append({'page': i, 'source': text, 'original': answer, 'original_seconds': seconds})
        print(f'Original translation page {i} checked', flush=True)
    baseline_peak = torch.cuda.max_memory_allocated() if device == 'cuda' else None

    probe = tokenizer(calibration[0], return_tensors='pt').to(device)
    decoder = torch.tensor([[model.config.decoder_start_token_id, tokenizer.get_lang_id('en')]], device=device)
    with torch.no_grad():
        expected = model(**probe, decoder_input_ids=decoder).logits.index_select(-1, new_to_old).cpu()
        embedding = model.get_input_embeddings()
        replacement = M2M100ScaledWordEmbedding(len(keep), embedding.embedding_dim,
            int(old_to_new[embedding.padding_idx]), embedding.embed_scale).to(device)
        replacement.weight.copy_(embedding.weight.index_select(0, new_to_old))
        model.set_input_embeddings(replacement)
        model.set_output_embeddings(torch.nn.Linear(embedding.embedding_dim, len(keep), bias=False).to(device))
        model.config.vocab_size = len(keep)
        for config in (model.config, model.generation_config):
            for name in ('bos_token_id', 'eos_token_id', 'pad_token_id', 'decoder_start_token_id'):
                value = getattr(config, name, None)
                if value is not None:
                    setattr(config, name, int(old_to_new[value]))
        model.tie_weights()
        probe['input_ids'] = remap_inputs(probe['input_ids'], old_to_new)
        actual = model(**probe, decoder_input_ids=remap_inputs(decoder, old_to_new)).logits.cpu()
        torch.testing.assert_close(actual, expected, rtol=1e-4, atol=1e-4)
    del embedding, expected, actual, probe, decoder
    gc.collect()
    if device == 'cuda':
        torch.cuda.empty_cache()
    after = sum(p.numel() for p in model.parameters())
    assert before - after == (old_size - len(keep)) * model.config.d_model
    assert model.model.encoder.embed_tokens.weight.data_ptr() == model.model.decoder.embed_tokens.weight.data_ptr()
    folder = out / 'translation'
    model.cpu().save_pretrained(folder)
    tokenizer.save_pretrained(folder / 'original-tokenizer')
    write_json(folder / 'id-map.json', {'new_to_old': keep, 'original_vocab_size': old_size})
    del model
    gc.collect()
    if device == 'cuda':
        torch.cuda.empty_cache()
    # Reload the saved artifact so the test also covers serialization and tied weights.
    model = M2M100ForConditionalGeneration.from_pretrained(folder, local_files_only=True).eval().to(device)
    generate(model, tokenizer, calibration[0], device, old_to_new, new_to_old)
    if device == 'cuda':
        torch.cuda.reset_peak_memory_stats()
    for row in baseline:
        ids = tokenizer(row['source'])['input_ids']
        row['missing_input_tokens'] = sum(int(old_to_new[idx]) < 0 for idx in ids)
        if row['missing_input_tokens']:
            row.update(trimmed=None, trimmed_seconds=None)
            continue
        answer, seconds = timed(lambda: generate(model, tokenizer, row['source'], device, old_to_new, new_to_old))
        row.update(trimmed=answer, trimmed_seconds=seconds)
        print(f"Translation page {row['page']} checked", flush=True)
    result = {
        'original_vocab': old_size, 'trimmed_vocab': len(keep),
        'original_parameters': before, 'trimmed_parameters': after,
        'weight_bytes_saved_fp32': (before - after) * 4,
        'saved_weight_bytes': sum(p.stat().st_size for p in folder.glob('*.safetensors')),
        'original_peak_allocated_bytes': baseline_peak,
        'trimmed_peak_allocated_bytes': torch.cuda.max_memory_allocated() if device == 'cuda' else None,
        'retained_logits_verified': True, 'cases': baseline,
    }
    del model
    gc.collect()
    if device == 'cuda':
        torch.cuda.empty_cache()
    return result


def ocr_experiment(out, records, panels, device):
    print('Loading original Korean/English OCR', flush=True)
    reader = easyocr.Reader(['ko', 'en'], gpu=device == 'cuda',
        model_storage_directory=str(HERE / 'models/easyocr'), download_enabled=False, verbose=False)
    originals = []
    boxes = []
    for page in records:
        image = cv2.imread(str(panels / page['source']), cv2.IMREAD_GRAYSCALE)
        assert image is not None
        horizontal, free = reader.detect(image)
        boxes.append((image, horizontal[0], free[0]))
    image, horizontal, free = boxes[0]
    reader.recognize(image, horizontal, free)
    for i, (image, horizontal, free) in enumerate(boxes):
        result, seconds = timed(lambda: reader.recognize(image, horizontal, free))
        originals.append({'page': i, 'original': [r[1] for r in result], 'original_seconds': seconds})
    original_chars = reader.character
    assert all(ord(ch) < 128 or 'HANGUL' in unicodedata.name(ch, '') for ch in original_chars)
    # Deliberately aggressive: demonstrate the coverage cost of fitting only five pages.
    calibration = set(''.join(text for row in originals[:5] for text in row['original']))
    chars = ''.join(ch for ch in original_chars if ord(ch) < 128 or ch in calibration)
    indices = [0] + [i + 1 for i, ch in enumerate(original_chars) if ch in chars]
    module = reader.recognizer.module if hasattr(reader.recognizer, 'module') else reader.recognizer
    before = sum(p.numel() for p in module.parameters())
    prediction = module.Prediction
    selected = torch.tensor(indices, device=prediction.weight.device)
    replacement = torch.nn.Linear(prediction.in_features, len(indices)).to(prediction.weight.device)
    with torch.no_grad():
        replacement.weight.copy_(prediction.weight[selected])
        replacement.bias.copy_(prediction.bias[selected])
        probe = torch.randn(2, 3, prediction.in_features, device=prediction.weight.device)
        torch.testing.assert_close(replacement(probe), prediction(probe).index_select(-1, selected))
    module.Prediction = replacement
    reader.character = chars
    reader.converter = CTCLabelConverter(chars, {}, {})
    after = sum(p.numel() for p in module.parameters())
    assert before - after == (len(original_chars) - len(chars)) * (prediction.in_features + 1)
    folder = out / 'ocr'
    folder.mkdir()
    torch.save({k: v.cpu() for k, v in module.state_dict().items()}, folder / 'recognizer.pt')
    write_json(folder / 'characters.json', {'characters': chars, 'original_characters': original_chars,
                                         'blank_id': 0, 'original_indices': indices})
    saved = torch.load(folder / 'recognizer.pt', weights_only=True, map_location=device)
    module.load_state_dict(saved, strict=True)
    del saved, prediction
    image, horizontal, free = boxes[0]
    reader.recognize(image, horizontal, free)
    for row, (image, horizontal, free) in zip(originals, boxes):
        result, seconds = timed(lambda: reader.recognize(image, horizontal, free))
        row.update(trimmed=[r[1] for r in result], trimmed_seconds=seconds,
            missing_original_characters=''.join(sorted(set(''.join(row['original'])) - set(chars))))
    return {
        'original_characters': len(original_chars), 'trimmed_characters': len(chars),
        'original_parameters': before, 'trimmed_parameters': after,
        'weight_bytes_saved_fp32': (before - after) * 4,
        'saved_weight_bytes': (folder / 'recognizer.pt').stat().st_size,
        'detector_unchanged_bytes': (HERE / 'models/easyocr/craft_mlt_25k.pth').stat().st_size,
        'ko_en_only_trim_removes_characters': 0, 'cases': originals,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=HERE / 'work/vocab-trim')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    torch.set_num_threads(4)
    torch.manual_seed(0)
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    source = HERE.parent / 'samples/naver-845456-25'
    records = json.loads((source / 'english-panels-10/ocr.json').read_text(encoding='utf-8'))[:10]
    report = {'model': MODEL, 'revision': REVISION,
        'device': device, 'gpu': torch.cuda.get_device_name() if device == 'cuda' else None,
        'torch': torch.__version__, 'precision': 'float32', 'calibration_pages': list(range(5)),
        'heldout_pages': list(range(5, 10)),
        'limitations': ['No human reference labels; agreement is not translation/OCR accuracy.',
            'Ten panels from one episode; not a cross-work generalization test.',
            'Warm single-pass inference times exclude startup and model loading.',
            'OCR times use fixed detection boxes; detection is not benchmarked.',
            'Translation tokenizer remains original; explicit ID mapping is required.',
            'OCR sample-based character trimming intentionally sacrifices unseen characters.']}
    report['translation'] = translation_experiment(args.out, records, device)
    write_json(args.out / 'report.json', report)
    report['ocr'] = ocr_experiment(args.out, records, source / 'panels', device)
    write_json(args.out / 'report.json', report)
    write_review(args.out, report)
    print(f"Report saved to {args.out / 'report.json'}", flush=True)


def write_review(out, report):
    cards = []
    for page in range(10):
        rows = []
        for case in report['translation']['cases']:
            if case['page'] == page:
                changed = ' class="changed"' if case['original'] != case['trimmed'] else ''
                rows.append(f'<tr{changed}><td>{html.escape(case["source"])}</td>'
                    f'<td>{html.escape(case["original"])}</td><td>{html.escape(case["trimmed"] or "Removed input token")}</td></tr>')
        ocr = report['ocr']['cases'][page]
        image = HERE.parent / f'samples/naver-845456-25/panels/{page:04d}.png'
        image_path = Path(os.path.relpath(image, out)).as_posix()
        cards.append(f'<section><h2>Panel {page} · {"calibration" if page < 5 else "held out"}</h2>'
            f'<details><summary>Original panel</summary><img src="{html.escape(image_path, quote=True)}" loading="lazy"></details>'
            '<h3>Translation (same cached Korean input)</h3><table><tr><th>Korean</th><th>Original model</th><th>Trimmed model</th></tr>'
            + ''.join(rows) + '</table><h3>OCR (same detection boxes)</h3><div class="pair"><pre>'
            + html.escape('\n'.join(ocr['original'])) + '</pre><pre>'
            + html.escape('\n'.join(ocr['trimmed'])) + '</pre></div></section>')
    (out / 'review.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1"><title>Vocabulary trim experiment</title>'
        '<style>body{font:16px/1.6 system-ui;max-width:1000px;margin:auto;padding:24px;background:#f4f5f2;color:#20372b}'
        'section{padding:20px;background:white;margin:20px 0;border-radius:12px}table{width:100%;border-collapse:collapse}'
        'td,th{padding:10px;text-align:left;border-bottom:1px solid #ddd}.changed{background:#fff0cc}'
        '.pair{display:grid;grid-template-columns:1fr 1fr;gap:16px}pre{white-space:pre-wrap;overflow-wrap:anywhere}'
        'img{max-width:100%;height:auto}summary{cursor:pointer}</style><h1>Original vs vocab-trimmed</h1>'
        '<p>Left: original. Right: trimmed. Yellow: changed translation. No human reference labels; '
        'agreement is not accuracy. OCR charset was selected using panels 0–4 only. '
        'The Chrome extension still uses the original models.</p>' + ''.join(cards) + '</html>', encoding='utf-8')


if __name__ == '__main__':
    main()
