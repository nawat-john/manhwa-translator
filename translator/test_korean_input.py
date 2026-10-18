"""Check decoded image limits before loading translation models."""
import tempfile
from pathlib import Path
import unittest
from PIL import Image, UnidentifiedImageError
from translate_korean_sample import validate_source


class InputTests(unittest.TestCase):
    def test_image_validation(self):
        folder = Path(tempfile.mkdtemp(prefix='manga-input-test-'))
        valid = folder / 'source.img'
        Image.new('RGB', (20, 30), 'white').save(valid, format='PNG')
        validate_source(valid)
        huge = folder / 'wide.png'
        Image.new('RGB', (16001, 1)).save(huge)
        with self.assertRaises(ValueError):
            validate_source(huge)
        oversized = folder / 'oversized.png'
        Image.new('1', (4001, 4000)).save(oversized)
        with self.assertRaises(ValueError):
            validate_source(oversized)
        animated = folder / 'animated.webp'
        Image.new('RGB', (10, 10), 'black').save(animated, save_all=True,
            append_images=[Image.new('RGB', (10, 10), 'white')], duration=100)
        with self.assertRaises(ValueError):
            validate_source(animated)
        bad = folder / 'bad.jpg'
        bad.write_text('<html>Not an image</html>')
        with self.assertRaises(UnidentifiedImageError):
            validate_source(bad)


if __name__ == '__main__':
    unittest.main()
