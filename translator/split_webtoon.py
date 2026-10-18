"""Join ordered webtoon strips and cut only inside full-width horizontal whitespace."""
import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image

MIN_GAP = 24
WHITE = 245
BLACK = 10


def validate_source(file):
    with Image.open(file) as image:
        if (image.format not in {'JPEG', 'PNG', 'WEBP'} or getattr(image, 'n_frames', 1) != 1
                or image.width * image.height > 16_000_000 or max(image.size) > 16_000):
            raise ValueError('Use a static JPEG/PNG/WebP, at most 16 megapixels and 16000px per side')
        image.verify()


def read_source(file):
    file = Path(file)
    validate_source(file)
    with Image.open(file) as image:
        rgb = np.asarray(image.convert('RGB'))
        # shortcut: white/black full-width gutters; coloured separators need a separate rule.
        blank = np.all(rgb >= WHITE, axis=(1, 2)) | np.all(rgb <= BLACK, axis=(1, 2))
        return {'path': file, 'width': image.width, 'height': image.height, 'blank': blank}


def gap_cuts(blank):
    edges = np.diff(np.r_[False, blank, False].astype(np.int8))
    return [(int(a) + int(b)) // 2 for a, b in zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1))
            if b - a >= MIN_GAP]


def layout(sources):
    if not sources or len({source['width'] for source in sources}) != 1:
        raise ValueError('Source images must have the same width; no automatic resizing is performed')
    offsets = [0]
    for source in sources:
        offsets.append(offsets[-1] + source['height'])
    return offsets, gap_cuts(np.concatenate([source['blank'] for source in sources]))


def image_context(count, target, load):
    """Load neighbours until both ends of the selected image have safe whitespace boundaries."""
    if not 0 <= target < count:
        raise ValueError('Invalid target image index')
    first = last = target
    sources = [read_source(load(target))]
    while True:
        offsets, cuts = layout(sources)
        top, bottom = offsets[target - first:target - first + 2]
        before = [cut for cut in cuts if cut <= top]
        after = [cut for cut in cuts if cut >= bottom]
        need_before = not before and first > 0
        need_after = not after and last < count - 1
        if not need_before and not need_after:
            return sources, before[-1] if before else 0, after[0] if after else offsets[-1], top, bottom
        if len(sources) >= 32:
            raise ValueError('No safe whitespace boundary within 32 strips; refusing to cut through content')
        if need_before:
            first -= 1
            sources.insert(0, read_source(load(first)))
        elif need_after:
            last += 1
            sources.append(read_source(load(last)))


def split_sources(sources, output_dir, start=0, end=None):
    output_dir = Path(output_dir)
    offsets, cuts = layout(sources)
    end = offsets[-1] if end is None else end
    if not 0 <= start < end <= offsets[-1]:
        raise ValueError('Invalid split interval')
    # Keep all pixels, including blank margins and the final unfinished-looking tail.
    content = np.flatnonzero(~np.concatenate([source['blank'] for source in sources])[start:end]) + start
    cuts = [start] + [cut for cut in cuts if len(content) and content[0] < cut < content[-1]] + [end]
    width = sources[0]['width']
    output_dir.mkdir(parents=True, exist_ok=True)
    pages = []
    for number, (top, bottom) in enumerate(zip(cuts, cuts[1:])):
        if bottom - top > 16000 or width * (bottom - top) > 16_000_000:
            raise ValueError(f'Unbroken content at rows {top}:{bottom} exceeds image limits; not splitting through it')
        canvas = Image.new('RGB', (width, bottom - top))
        parts = []
        for index, source in enumerate(sources):
            a, b = max(top, offsets[index]), min(bottom, offsets[index + 1])
            if a >= b:
                continue
            with Image.open(source['path']) as image:
                canvas.paste(image.convert('RGB').crop((0, a - offsets[index], width, b - offsets[index])), (0, a - top))
            parts.append({'source': source['path'].name, 'source_top': a - offsets[index],
                          'source_bottom': b - offsets[index], 'page_top': a - top})
        filename = f'{number:04d}.png'
        destination = output_dir / filename
        if destination.resolve() in {source['path'].resolve() for source in sources}:
            raise ValueError('Output must not overwrite source images')
        temporary = destination.with_suffix('.tmp.png')
        canvas.save(temporary)
        temporary.replace(destination)
        canvas.close()
        pages.append({'file': filename, 'top': top, 'bottom': bottom, 'parts': parts})
    manifest = {'version': 1, 'white': WHITE, 'black': BLACK, 'min_gap': MIN_GAP, 'width': width,
                'start': start, 'end': end, 'pages': pages}
    temporary = output_dir / 'page_map.tmp'
    temporary.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    temporary.replace(output_dir / 'page_map.json')
    return manifest


def restore_slice(manifest, translated_dir, top, bottom):
    """Project translated panels back onto one original strip without changing browser layout."""
    if not manifest['start'] <= top < bottom <= manifest['end']:
        raise ValueError('Requested image is outside the translated interval')
    image = Image.new('RGB', (manifest['width'], bottom - top))
    covered = 0
    for page in manifest['pages']:
        a, b = max(top, page['top']), min(bottom, page['bottom'])
        if a >= b:
            continue
        with Image.open(Path(translated_dir) / page['file']) as panel:
            if panel.size != (manifest['width'], page['bottom'] - page['top']):
                raise ValueError('Translated panel dimensions do not match the source')
            image.paste(panel.crop((0, a - page['top'], panel.width, b - page['top'])), (0, a - top))
        covered += b - a
    if covered != bottom - top:
        raise ValueError('Missing translated rows')
    return image


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    manifest_file = args.source / 'manifest.json'
    if manifest_file.exists():
        files = [args.source / entry['filename'] for entry in json.loads(manifest_file.read_text(encoding='utf-8'))['images']]
    else:
        files = sorted(args.source.glob('*.jpg'))
    result = split_sources([read_source(file) for file in files], args.output)
    print(f'{len(files)} source strips -> {len(result["pages"])} panels; {result["end"]} rows preserved')
