"""Translate ten whitespace-delimited webtoon panels, keeping OCR and translations for review."""
import asyncio
import argparse
import html
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time

HERE = Path(__file__).resolve().parent
UPSTREAM = HERE / 'manga-image-translator'
SOURCE = HERE.parent / 'samples/naver-845456-25'
OUT = SOURCE / 'english-panels-10'
os.environ['HF_HOME'] = str(HERE / 'hf-cache')
sys.path.insert(0, str(UPSTREAM))

import cv2
import easyocr
import numpy as np
from PIL import Image
import torch
from korean_translation import KoreanTranslator
from ocr_precision import use_fp16
from manga_translator.config import Inpainter, InpainterConfig
from manga_translator.inpainting import dispatch as inpaint, prepare
from manga_translator.rendering import dispatch as render
from manga_translator.utils import TextBlock, ModelWrapper
from split_webtoon import validate_source, read_source, split_sources


def save_json(file, data):
    temp = file.with_suffix('.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(file)


async def main(input_file=None, output_dir=OUT, source_dir=SOURCE, files=None):
    explicit_files = input_file is not None or files is not None
    OUT = output_dir
    SOURCE = input_file.parent if input_file else source_dir
    OUT.mkdir(parents=True, exist_ok=True)
    if input_file:
        files = [input_file]
    elif files is None:
        entries = json.loads((SOURCE / 'manifest.json').read_text(encoding='utf-8'))['images']
        panels = SOURCE / 'panels'
        page_map = split_sources([read_source(SOURCE / entry['filename']) for entry in entries], panels)
        files = [panels / page['file'] for page in page_map['pages'][:10]]
    if not files or len({file.parent for file in files}) != 1:
        raise ValueError('Input images must be in one directory')
    SOURCE = files[0].parent
    assert all(file.is_file() for file in files), 'Missing source images'
    for file in files:
        validate_source(file)
    inputs = [{'file': file.name, 'sha256': hashlib.sha256(file.read_bytes()).hexdigest()} for file in files]
    input_manifest = OUT / 'inputs.json'
    if input_manifest.exists() and json.loads(input_manifest.read_text(encoding='utf-8')) != inputs:
        raise ValueError('Input images changed; use a new output directory instead of stale OCR/translation caches')
    if not input_manifest.exists() and ((OUT / 'ocr.json').exists() or (OUT / 'translations.json').exists()):
        raise ValueError('Legacy cache has no source fingerprints; use a new output directory')
    save_json(input_manifest, inputs)
    torch.set_num_threads(4)
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    cache = OUT / 'ocr.json'
    if cache.exists():
        records = json.loads(cache.read_text(encoding='utf-8'))
    else:
        print('Loading Korean EasyOCR', flush=True)
        reader = easyocr.Reader(['ko', 'en'], gpu=device == 'cuda',
                                model_storage_directory=str(HERE / 'models/easyocr'), verbose=False)
        if device == 'cuda':
            use_fp16(reader)
        records = []
        for file in files:
            print(f'OCR {file.name}', flush=True)
            # shortcut: paragraph grouping can merge nearby captions; review ocr.json before production use.
            detected = reader.readtext(file.read_bytes(), paragraph=True, x_ths=0.7, y_ths=0.4)
            regions = []
            for box, text in detected:
                if not re.search('[\uac00-\ud7af\u1100-\u11ff]', text):
                    continue
                points = np.asarray(box, dtype=int)
                assert points.shape == (4, 2)
                regions.append({'box': points.tolist(), 'korean': text})
            records.append({'source': file.name, 'regions': regions})
            print(f'  {len(regions)} Korean regions', flush=True)
        save_json(cache, records)
        del reader
        torch.cuda.empty_cache()

    translations = OUT / 'translations.json'
    if translations.exists():
        records = json.loads(translations.read_text(encoding='utf-8'))
    else:
        model = KoreanTranslator(device)
        for record in records:
            print(f'Translating {record["source"]}', flush=True)
            for region in record['regions']:
                region['english'] = model.translate(region['korean'])
                assert region['english'], 'Empty translation'
                print(f'  {region["korean"]} -> {region["english"]}', flush=True)
        save_json(translations, records)
        del model
        torch.cuda.empty_cache()

    ModelWrapper._MODEL_DIR = str(HERE / 'models')
    print('Loading existing LaMa inpainter', flush=True)
    await prepare(Inpainter.lama_large, device)
    config = InpainterConfig(inpainter=Inpainter.lama_large, inpainting_precision='fp32')
    for record in records:
        destination = OUT / Path(record['source']).with_suffix('.png').name
        if destination.exists():
            continue
        print(f'Rendering {destination.name}', flush=True)
        with Image.open(SOURCE / record['source']) as source:
            image = np.array(source.convert('RGB'))
        mask = np.zeros(image.shape[:2], dtype=np.uint8)
        blocks = []
        for region in record['regions']:
            points = np.asarray(region['box'], dtype=np.int32)
            cv2.fillConvexPoly(mask, points, 255)
            blocks.append(TextBlock([points], texts=[region['korean']], translation=region['english'],
                                    font_size=28, direction='h', alignment='center', target_lang='ENG',
                                    fg_color=(0, 0, 0), bg_color=(255, 255, 255)))
        if blocks:
            mask = cv2.dilate(mask, np.ones((3, 3), dtype=np.uint8))
            clean = await inpaint(Inpainter.lama_large, image, mask, config, inpainting_size=1600, device=device)
            result = await render(clean, blocks, font_path=str(UPSTREAM / 'fonts/anime_ace.ttf'),
                                  font_size_fixed=28, font_size_minimum=1)
        else:
            result = image
        temp = destination.with_suffix('.tmp.png')
        Image.fromarray(result).save(temp)
        temp.replace(destination)
        with Image.open(destination) as check:
            check.load()
            assert check.size == (image.shape[1], image.shape[0])

    if explicit_files:
        print(f'Completed {len(files)} image(s): {OUT}', flush=True)
        return records

    cards = []
    for record in records:
        source = record['source']
        translated = Path(source).with_suffix('.png').name
        original_url = html.escape(Path(os.path.relpath(SOURCE / source, OUT)).as_posix(), quote=True)
        rows = ''.join(f'<tr><td>{html.escape(r["korean"])}</td><td>{html.escape(r["english"])}</td></tr>' for r in record['regions'])
        warning = '' if record['regions'] else '<p>No Korean text recognized: original image retained. Stylized sound effects may be missed.</p>'
        cards.append(f'<section><h2>{source} · Korean → English</h2>{warning}<div class="pair"><figure><figcaption>Original · whitespace split</figcaption><img loading="lazy" src="{original_url}"></figure><figure><figcaption>Machine translation</figcaption><img loading="lazy" src="{translated}"></figure></div><details><summary>OCR & translation ({len(record["regions"])} regions)</summary><table>{rows}</table></details></section>')
    (OUT / 'index.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Korean translation · 10 images</title><style>body{font:16px system-ui;background:#f3f5f1;color:#23382d;max-width:1450px;margin:auto;padding:25px}h1{font-size:30px}section{background:white;padding:20px;margin:30px 0;border-radius:12px}.pair{display:grid;grid-template-columns:1fr 1fr;gap:20px}figure{margin:0}img{width:100%}figcaption{padding:10px 0;color:#647569}table{width:100%;border-collapse:collapse}td{width:50%;padding:12px;border-bottom:1px solid #ddd}summary{cursor:pointer;margin:15px 0}@media(max-width:600px){body{padding:8px}.pair{gap:8px}section{padding:10px}}</style><h1>Korean → English / 10-image trial</h1><p>EasyOCR · M2M100 418M · LaMa · Local processing. Machine output: OCR errors, literal dialogue and cropped speech bubbles need review.</p>' + ''.join(cards) + '</html>', encoding='utf-8')
    assert len(list(OUT.glob('[0-9][0-9][0-9][0-9].png'))) == 10
    print(f'Completed 10 images: {OUT / "index.html"}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, help='Translate one local image instead of the ten-image sample')
    parser.add_argument('--output', type=Path, help='Isolated output directory for single-image mode')
    args = parser.parse_args()
    if bool(args.input) != bool(args.output):
        parser.error('--input and --output must be supplied together')
    started = time.monotonic()
    asyncio.run(main(args.input.resolve() if args.input else None, args.output.resolve() if args.output else OUT))
    print(f'Elapsed: {time.monotonic() - started:.1f}s')
