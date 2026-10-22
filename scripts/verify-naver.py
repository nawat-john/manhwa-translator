import hashlib
import json
from pathlib import Path
from PIL import Image

folder = Path('samples/naver-845456-25')
manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
assert [entry['index'] for entry in manifest['images']] == list(range(len(manifest['images'])))
total = 0
sizes = []
for entry in manifest['images']:
    file = folder / entry['filename']
    data = file.read_bytes()
    assert len(data) == entry['bytes']
    assert hashlib.sha256(data).hexdigest() == entry['sha256']
    with Image.open(file) as image:
        image.load()
        sizes.append(image.size)
    total += len(data)
print(f'Validated {len(sizes)} decoded images, {total / 1024 / 1024:.2f} MiB')
print(f'Widths: {sorted(set(w for w, h in sizes))}; heights: {min(h for w, h in sizes)}-{max(h for w, h in sizes)}')
