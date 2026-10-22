"""Join OCR fragments only when they share an enclosed white region."""
import cv2
import numpy as np


def _text_rectangle(mask, bounds):
    """Largest rectangle inside the balloon and original text bounds."""
    x1, y1, x2, y2 = bounds
    heights = np.zeros(x2 - x1, dtype=int)
    best_area, best = 0, bounds
    for y in range(y1, y2):
        heights = np.where(mask[y, x1:x2], heights + 1, 0)
        stack = []
        for x, height in enumerate([*heights, 0]):
            start = x
            while stack and stack[-1][1] > height:
                start, previous = stack.pop()
                # Avoid placing a tall text column across the narrow neck of joined balloons.
                previous = min(previous, int((x - start) * 1.25))
                area = (x - start) * previous
                if area > best_area:
                    best_area = area
                    best = (x1 + start, y + 1 - previous, x1 + x, y + 1)
            if height and (not stack or stack[-1][1] < height):
                stack.append((start, height))
    return best


def merge_balloon_text(image, regions):
    white = (image.min(axis=2) > 200).astype(np.uint8)
    _, labels, stats, _ = cv2.connectedComponentsWithStats(white, 8)
    height, width = white.shape
    groups = {}
    for index, region in enumerate(regions):
        points = np.asarray(region['box'])
        x1, y1 = np.maximum(points.min(axis=0), 0)
        x2, y2 = np.minimum(points.max(axis=0), (width, height))
        counts = np.bincount(labels[y1:y2, x1:x2].ravel(), minlength=len(stats))
        counts[0] = 0
        label = int(counts.argmax())
        x, y, w, h, _ = stats[label]
        enclosed = label and x > 0 and y > 0 and x + w < width and y + h < height
        # shortcut: open, dark or colored balloons stay unchanged; add segmentation if these become common.
        key = ('balloon', label) if enclosed and counts[label] > .45 * (x2-x1) * (y2-y1) else ('single', index)
        groups.setdefault(key, []).append(region)
    result = []
    for key, members in groups.items():
        if len(members) == 1:
            result.append(members[0])
            continue
        members = sorted(members, key=lambda r: (min(p[1] for p in r['box']), min(p[0] for p in r['box'])))
        boxes = [box for member in members for box in member.get('source_boxes', [member['box']])]
        points = np.asarray(boxes).reshape(-1, 2)
        bounds = (*points.min(axis=0), *points.max(axis=0))
        interior = (labels == key[1]).astype(np.uint8)
        contours, _ = cv2.findContours(interior, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(interior, contours, -1, 1, cv2.FILLED)
        x1, y1, x2, y2 = map(int, _text_rectangle(interior, bounds))
        result.append({'box': [[x1,y1],[x2,y1],[x2,y2],[x1,y2]],
                       'source_boxes': boxes, 'balloon_outline': contours[0].reshape(-1, 2).tolist(),
                       'korean': ' '.join(m['korean'].strip() for m in members)})
    return sorted(result, key=lambda r: (min(p[1] for p in r['box']), min(p[0] for p in r['box'])))
