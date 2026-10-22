import unittest

from context_data import conversation_rows, source_with_context
from build_context_probes import validate_cases


class Tokenizer:
    def __call__(self, text):
        return {'input_ids': text.split()}


class ContextDataTest(unittest.TestCase):
    def test_context_is_ordered_past_only_and_isolated_by_conversation(self):
        rows = [{'conversation_id': conv, 'turn': turn, 'korean': text, 'english': text}
                for conv, turn, text in [('a', 2, 'future'), ('b', 0, 'other'), ('a', 0, 'first'), ('a', 1, 'current')]]
        result = conversation_rows(rows, Tokenizer())
        current = next(r for r in result if r['current_korean'] == 'current')
        self.assertEqual(current['previous'], ['first'])
        self.assertEqual(current['korean'], 'Context: first\nCurrent: current')
        self.assertEqual(rows[2]['korean'], 'first')

    def test_budget_discards_oldest_context_never_current(self):
        source = source_with_context('now', ['old ' * 120, 'recent ' * 120, 'nearest'], Tokenizer())
        self.assertNotIn('old', source)
        self.assertIn('nearest', source)
        self.assertTrue(source.endswith('Current: now'))
        with self.assertRaises(ValueError):
            source_with_context('long ' * 129, [], Tokenizer())

    def test_probe_requires_distinct_targets_and_two_contexts(self):
        case = {'id': 'x', 'current': 'same', 'variants': [
            {'previous': ['first'], 'english': 'one'}, {'previous': ['second'], 'english': 'two'}]}
        self.assertEqual(validate_cases({'cases': [case]}, ['x']), [case])
        case['variants'][1]['english'] = 'one'
        with self.assertRaises(ValueError):
            validate_cases({'cases': [case]}, ['x'])


if __name__ == '__main__':
    unittest.main()
