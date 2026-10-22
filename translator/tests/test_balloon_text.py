import unittest
import cv2
import numpy as np
from balloon_text import merge_balloon_text


def region(x, y, text):
    return {'box': [[x,y],[x+40,y],[x+40,y+20],[x,y+20]], 'korean': text}


class BalloonTextTests(unittest.TestCase):
    def test_same_enclosed_balloon_only_and_safe_render_rectangle(self):
        image = np.zeros((240, 300, 3), np.uint8)
        cv2.ellipse(image, (80, 100), (65, 85), 0, 0, 360, (255,255,255), -1)
        cv2.ellipse(image, (220, 100), (65, 85), 0, 0, 360, (255,255,255), -1)
        fragments = [region(60,60,'first'), region(60,110,'second'), region(200,60,'other')]
        result = merge_balloon_text(image, fragments)
        self.assertEqual(len(result), 2)
        merged = next(r for r in result if 'source_boxes' in r)
        self.assertEqual(merged['korean'], 'first second')
        self.assertEqual(len(merged['source_boxes']), 2)
        (x1,y1), _, (x2,y2), _ = merged['box']
        self.assertTrue((image[y1:y2,x1:x2] == 255).all())
        self.assertEqual(merge_balloon_text(image, result), result)

    def test_open_white_background_never_groups(self):
        fragments = [region(20,20,'first'), region(20,60,'second')]
        self.assertEqual(merge_balloon_text(np.full((150,150,3),255,np.uint8), fragments), fragments)


if __name__ == '__main__':
    unittest.main()
