import tempfile
from pathlib import Path
import unittest

import numpy as np
from PIL import Image
from split_webtoon import read_source, split_sources, image_context, restore_slice


class WebtoonTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='webtoon-split-'))

    def sources(self, image, heights):
        files, top = [], 0
        for i, height in enumerate(heights):
            file = self.root / f'{i:04d}.png'
            Image.fromarray(image[top:top + height]).save(file)
            files.append(file)
            top += height
        self.assertEqual(top, len(image))
        return files

    def test_gutter_across_file_boundary_and_pixel_exact_roundtrip(self):
        image = np.full((160, 80, 3), (130, 60, 90), np.uint8)
        image[50:82] = 255  # A 32px gutter split 10/22 between source files.
        image[120:145] = 0  # Black gutters work too.
        files = self.sources(image, [60, 50, 50])
        manifest = split_sources([read_source(f) for f in files], self.root / 'pages')
        self.assertEqual([(p['top'], p['bottom']) for p in manifest['pages']], [(0, 66), (66, 132), (132, 160)])
        self.assertEqual(manifest['pages'][1]['parts'][0]['source'], '0001.png')
        top = 0
        for file in files:
            with Image.open(file) as original:
                restored = restore_slice(manifest, self.root / 'pages', top, top + original.height)
                np.testing.assert_array_equal(np.asarray(original), np.asarray(restored))
                top += original.height

    def test_context_loads_backwards_and_forwards_until_space_not_fixed_neighbour_count(self):
        image = np.full((400, 80, 3), (80, 150, 60), np.uint8)
        image[25:55] = 255
        image[345:375] = 255
        files = self.sources(image, [80] * 5)
        requested = []
        def load(index):
            requested.append(index)
            return files[index]
        sources, start, end, top, bottom = image_context(5, 2, load)
        self.assertEqual((start, end, top, bottom), (40, 360, 160, 240))
        self.assertEqual(set(requested), {0, 1, 2, 3, 4})
        self.assertEqual(len(requested), len(set(requested)))
        manifest = split_sources(sources, self.root / 'context', start, end)
        self.assertEqual(len(manifest['pages']), 1)
        np.testing.assert_array_equal(np.asarray(restore_slice(manifest, self.root / 'context', top, bottom)), image[160:240])

    def test_no_gaps_eof_and_blank_margins_do_not_lose_pixels(self):
        image = np.full((100, 80, 3), (100, 100, 100), np.uint8)
        image[:25] = 255
        image[-25:] = 255
        files = self.sources(image, [50, 50])
        sources, start, end, top, bottom = image_context(2, 0, lambda i: files[i])
        manifest = split_sources([read_source(f) for f in files], self.root / 'margin')
        self.assertEqual(len(manifest['pages']), 1)
        self.assertEqual(manifest['end'], 100)
        np.testing.assert_array_equal(np.asarray(restore_slice(manifest, self.root / 'margin', 0, 100)), image)
        image[:] = (100, 100, 100)
        files = self.sources(image, [50, 50])
        _, start, end, _, _ = image_context(2, 0, lambda i: files[i])
        self.assertEqual((start, end), (0, 100))

    def test_thin_or_partial_white_band_is_not_a_cut(self):
        image = np.full((130, 80, 3), (90, 60, 70), np.uint8)
        image[30:40] = 255
        image[60:100] = 255
        image[60:100, 40] = 0  # A vertical stroke crosses the supposed gutter.
        files = self.sources(image, [65, 65])
        manifest = split_sources([read_source(f) for f in files], self.root / 'narrow')
        self.assertEqual(len(manifest['pages']), 1)

    def test_mismatched_width_and_oversized_unbroken_content_fail_instead_of_cropping(self):
        a, b = self.root / 'a.png', self.root / 'b.png'
        Image.new('RGB', (80, 8100), (90, 60, 70)).save(a)
        Image.new('RGB', (81, 8100), (90, 60, 70)).save(b)
        with self.assertRaisesRegex(ValueError, 'same width'):
            split_sources([read_source(a), read_source(b)], self.root / 'bad')
        with self.assertRaisesRegex(ValueError, 'not splitting through'):
            split_sources([read_source(a), read_source(a)], self.root / 'large')


if __name__ == '__main__':
    unittest.main()
