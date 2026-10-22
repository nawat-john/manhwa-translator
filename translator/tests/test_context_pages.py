import unittest

from compare_context_pages import ordered_records, parse_reviews


class ContextPagesTest(unittest.TestCase):
    def test_reading_order_does_not_mutate_original_ocr(self):
        records = [{'source': '0001.png', 'regions': []}, {'source': '0000.png', 'regions': [
            {'box': [[20, 40], [30, 40], [30, 50], [20, 50]], 'korean': 'second'},
            {'box': [[20, 10], [30, 10], [30, 20], [20, 20]], 'korean': 'first'}]}]
        result = ordered_records(records)
        self.assertEqual(result[0]['source'], '0000.png')
        self.assertEqual([r['korean'] for r in result[0]['regions']], ['first', 'second'])
        self.assertEqual(records[1]['regions'][0]['korean'], 'second')

    def test_reviews_distinguish_unclear_source_from_tied_candidates(self):
        for answer in [{'x': 'unclear', 'y': 'tie'}, {'verdicts': {'x': 'unclear', 'y': 'tie'}}]:
            self.assertEqual(parse_reviews(answer, ['x', 'y']), {'x': 'unclear', 'y': 'tie'})
        for answer in [[], {}, {'x': 'A'}, {'x': True, 'y': 'tie'}, {'x': 'A', 'y': 'maybe'}]:
            with self.assertRaises(ValueError):
                parse_reviews(answer, ['x', 'y'])


if __name__ == '__main__':
    unittest.main()
