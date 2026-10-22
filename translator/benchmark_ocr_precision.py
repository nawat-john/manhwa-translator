"""Compare unchanged Korean/English OCR charset with FP32 and FP16 on ten panels."""
import argparse
import json
import math
from pathlib import Path
import statistics
import time

import easyocr
import torch
from ocr_precision import use_fp16

HERE = Path(__file__).resolve().parent


def read(reader, image):
    return reader.readtext(image.read_bytes(), paragraph=True, x_ths=0.7, y_ths=0.4)


def benchmark(reader, images):
    read(reader, images[0])
    read(reader, images[-1])
    torch.cuda.synchronize()
    torch.cuda.reset_peak_memory_stats()
    runs = []
    for repeat in range(3):
        rows = []
        for image in images:
            torch.cuda.synchronize()
            start = time.perf_counter()
            result = read(reader, image)
            torch.cuda.synchronize()
            rows.append({'file': image.name, 'seconds': time.perf_counter() - start,
                         'text': [row[1] for row in result], 'boxes': [row[0] for row in result]})
        runs.append(rows)
        print(f'OCR pass {repeat + 1}/3 complete', flush=True)
    return {'runs': runs, 'median_total_seconds': statistics.median(sum(row['seconds'] for row in run) for run in runs),
            'peak_cuda_allocated_bytes': torch.cuda.max_memory_allocated()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=HERE / 'work/ocr-fp16')
    args = parser.parse_args()
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA required for this FP16 experiment')
    args.out.mkdir(parents=True, exist_ok=False)
    torch.set_num_threads(4)
    torch.manual_seed(0)
    images = sorted((HERE.parent / 'samples/naver-845456-25/panels').glob('*.png'))[:10]
    assert len(images) == 10
    reader = easyocr.Reader(['ko', 'en'], gpu=True, download_enabled=False,
                           model_storage_directory=str(HERE / 'models/easyocr'), verbose=False)
    characters = reader.character
    report = {'gpu': torch.cuda.get_device_name(), 'torch': torch.__version__,
              'characters': len(characters), 'fp32': benchmark(reader, images)}
    use_fp16(reader)
    assert reader.character == characters
    for name, network in [('detector', reader.detector), ('recognizer', reader.recognizer)]:
        assert all(p.dtype == torch.float16 for p in network.parameters())
        torch.save({k: v.cpu() for k, v in network.network.state_dict().items()}, args.out / f'{name}-fp16.pth')
    report['fp16'] = benchmark(reader, images)
    report['matching_text_panels'] = sum(a['text'] == b['text'] for a, b in zip(report['fp32']['runs'][0], report['fp16']['runs'][0]))
    report['fp32_repeat_stable'] = all([r['text'] for r in run] == [r['text'] for r in report['fp32']['runs'][0]] for run in report['fp32']['runs'])
    report['fp16_repeat_stable'] = all([r['text'] for r in run] == [r['text'] for r in report['fp16']['runs'][0]] for run in report['fp16']['runs'])
    report['original_weight_bytes'] = sum((HERE / 'models/easyocr' / name).stat().st_size for name in ['craft_mlt_25k.pth', 'korean_g2.pth'])
    report['fp16_weight_bytes'] = sum(p.stat().st_size for p in args.out.glob('*.pth'))
    for precision in ('fp32', 'fp16'):
        assert all(math.isfinite(row['seconds']) and row['seconds'] > 0 for run in report[precision]['runs'] for row in run)
    (args.out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"FP16 text agreement: {report['matching_text_panels']}/10 panels", flush=True)
    print(f"Median seconds FP32/FP16: {report['fp32']['median_total_seconds']:.3f}/{report['fp16']['median_total_seconds']:.3f}", flush=True)


if __name__ == '__main__':
    main()
