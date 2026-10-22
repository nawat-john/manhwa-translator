"""Reject invalid teacher output and prevent dialogue leakage between splits."""
import unittest
import json
import os
from pathlib import Path
import tempfile
from unittest.mock import patch
from generate_dialogue_data import SCENARIOS, main, validate_conversations, validate_reviews, split_rows


class DialogueTests(unittest.TestCase):
    def test_parallel_validation_and_duplicate_normalization(self):
        data = {'conversations': [{'id': 'friends', 'turns': [
            {'korean': text, 'english': 'Natural English.'}
            for text in ['안녕', '잘 지내?', '오늘 뭐 해?', 'ㅋㅋ']]}]}
        rows = validate_conversations(data, ['friends'])
        self.assertEqual(len(rows), 4)
        data['conversations'][0]['turns'][3]['korean'] = '안 녕!'
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            validate_conversations(data, ['friends'])
        data['conversations'][0]['turns'][3] = {'korean': 'new English only', 'english': '한국어'}
        with self.assertRaisesRegex(ValueError, 'language'):
            validate_conversations(data, ['friends'])

    def test_review_must_cover_all_rows_and_use_boolean_verdict(self):
        with self.assertRaises(ValueError):
            validate_reviews({'reviews': []}, ['friends-0'])
        with self.assertRaises(ValueError):
            validate_reviews({'reviews': [{'id': 'friends-0', 'accept': 'true', 'reason': 'ok'}]}, ['friends-0'])
        result = validate_reviews({'reviews': [{'id': 'friends-0', 'accept': False, 'reason': 'Wrong meaning'}]}, ['friends-0'])
        self.assertFalse(result['friends-0']['accept'])

    def test_whole_conversations_are_disjoint(self):
        rows = [{'conversation_id': scenario, 'korean': f'문장 {i}'}
                for i, scenario in enumerate(['friends', 'friends', 'directions', 'fantasy'])]
        result = split_rows(rows)
        self.assertEqual([len(result[k]) for k in ('train', 'validation', 'test')], [2, 1, 1])
        sets = [set(r['conversation_id'] for r in result[k]) for k in ('train', 'validation', 'test')]
        self.assertFalse(sets[0] & sets[1] or sets[0] & sets[2] or sets[1] & sets[2])
        rows[-1]['korean'] = rows[0]['korean']
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            split_rows(rows)

    def test_pilot_exports_only_accepted_rows_with_provenance(self):
        generated = {'conversations': [{'id': scenario, 'turns': [
            {'korean': f'대화 {i} 차례 {j}', 'english': f'Conversation {i}, turn {j}.'}
            for j in range(4)]} for i, (scenario, _) in enumerate(SCENARIOS)]}
        reviews = {'reviews': [{'id': f'{scenario}-{j}', 'accept': (i, j) != (0, 0), 'reason': 'Reviewed'}
                              for i, (scenario, _) in enumerate(SCENARIOS) for j in range(4)]}
        def teacher(base, key, model, system, prompt):
            return (generated if model == 'writer' else reviews), {'requested_model': model, 'returned_model': model}
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / 'pilot'
            with patch('generate_dialogue_data.load_env'), patch.dict(os.environ, {'OMNIROUTE_API_KEY': 'test-key'}), \
                    patch('generate_dialogue_data.call', side_effect=teacher), \
                    patch('sys.argv', ['generate', '--model', 'writer', '--review-model', 'reviewer', '--out', str(out)]):
                main()
            manifest = json.loads((out / 'manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(manifest['counts'], {'train': 23, 'validation': 4, 'test': 4})
            self.assertEqual(manifest['rejected'], 1)
            rows = [json.loads(line) for line in (out / 'train.jsonl').read_text(encoding='utf-8').splitlines()]
            self.assertTrue(all(row['synthetic'] and not row['human_reviewed'] and row['review']['accept'] for row in rows))

    def test_review_failure_can_resume_without_regenerating(self):
        generated = {'conversations': [{'id': scenario, 'turns': [
            {'korean': f'대화 {i} 차례 {j}', 'english': f'Conversation {i}, turn {j}.'}
            for j in range(4)]} for i, (scenario, _) in enumerate(SCENARIOS)]}
        reviews = {'reviews': [{'id': f'{scenario}-{j}', 'accept': True, 'reason': 'Reviewed'}
                              for scenario, _ in SCENARIOS for j in range(4)]}
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / 'pilot'
            argv = ['generate', '--model', 'writer', '--review-model', 'reviewer', '--out', str(out)]
            with patch('generate_dialogue_data.load_env'), patch.dict(os.environ, {'OMNIROUTE_API_KEY': 'test-key'}), \
                    patch('sys.argv', argv), patch('generate_dialogue_data.call', side_effect=[
                        (generated, {'requested_model': 'writer', 'returned_model': 'writer'}), RuntimeError('quota')]):
                with self.assertRaisesRegex(RuntimeError, 'quota'):
                    main()
            self.assertTrue((out / 'generation.json').exists())
            self.assertFalse((out / 'train.jsonl').exists())
            with patch('generate_dialogue_data.load_env'), patch.dict(os.environ, {'OMNIROUTE_API_KEY': 'test-key'}), \
                    patch('sys.argv', argv + ['--resume']), patch('generate_dialogue_data.call', return_value=(
                        reviews, {'requested_model': 'reviewer', 'returned_model': 'reviewer'})) as teacher:
                main()
                teacher.assert_called_once()
                self.assertEqual(teacher.call_args.args[2], 'reviewer')
            self.assertTrue((out / 'manifest.json').exists())


if __name__ == '__main__':
    unittest.main()
