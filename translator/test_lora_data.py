import unittest

from train_dialogue_lora import collate, encode
from judge_dialogue_lora import parse_verdicts


class TrainingDataTest(unittest.TestCase):
    def test_judge_accepts_only_complete_unambiguous_choices(self):
        for answer in [{'x': 'A'}, {'verdicts': {'x': 'A'}}]:
            self.assertEqual(parse_verdicts(answer, ['x']), {'x': 'A'})
        for answer in [[], {}, {'x': 'maybe'}, {'x': True}, {'x': 'A', 'extra': 'B'}]:
            with self.assertRaises(ValueError):
                parse_verdicts(answer, ['x'])

    def test_labels_are_remapped_before_loss_mask_padding(self):
        class Tokenizer:
            def __call__(self, source, text_target):
                return {'input_ids': [7, 2], 'attention_mask': [1, 1], 'labels': [9, 8, 2] if source == 'long' else [9, 2]}
        rows = encode([{'korean': s, 'english': 'target'} for s in ['long', 'short']],
                      Tokenizer(), {7: 3, 9: 5, 8: 4, 2: 2})
        batch = collate(rows)
        self.assertEqual(batch['labels'].tolist(), [[5, 4, 2], [5, 2, -100]])
        self.assertEqual(batch['input_ids'].tolist(), [[3, 2], [3, 2]])


if __name__ == '__main__':
    unittest.main()
