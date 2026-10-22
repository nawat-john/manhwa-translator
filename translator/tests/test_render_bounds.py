"""Regression: fixed-size English text must not grow outside its detection box."""
import sys
from pathlib import Path
from types import SimpleNamespace
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'manga-image-translator'))
from manga_translator.rendering import resize_regions_to_font_size

image = np.zeros((200, 100, 3), dtype=np.uint8)
box = np.array([[[10, 20], [50, 20], [50, 180], [10, 180]]])
region = SimpleNamespace(min_rect=box.copy(), font_size=30)
result = resize_regions_to_font_size(image, [region], 14, 0, -1)
np.testing.assert_array_equal(result[0], box)
np.testing.assert_array_equal(region.min_rect, box)
assert region.font_size == 14
edge = SimpleNamespace(min_rect=np.array([[[-3, -1], [110, -1], [110, 205], [-3, 205]]]), font_size=30)
clipped = resize_regions_to_font_size(image, [edge], 14, 0, -1)[0]
assert clipped[..., 0].min() == 0 and clipped[..., 0].max() == 99
assert clipped[..., 1].min() == 0 and clipped[..., 1].max() == 199
assert resize_regions_to_font_size(image, [], 14, 0, -1) == []
print('Fixed-size bounds, source immutability and page-edge clipping passed.')
