import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from build_dialogue_corpus import Deduper, export, process_batch, review_verdicts, task_spec


class CorpusTests(unittest.TestCase):
    def test_deduplication_keeps_short_distinct_lines_and_blocks_near_copies(self):
        deduper = Deduper()
        self.assertTrue(deduper.add('안녕!'))
        self.assertFalse(deduper.add('안 녕?'))
        self.assertTrue(deduper.add('좋아'))
        self.assertTrue(deduper.add('싫어'))
        text = '오늘은 학교에서 친구들과 점심을 먹고 도서관에 들렀다가 집에 돌아가서 잠깐 쉬려고 해요 그리고 저녁에는 가족들과 함께 동네 공원을 산책할 계획이에요'
        self.assertTrue(deduper.add(text))
        self.assertFalse(deduper.add(text.replace('공원', '공항')))

    def test_resume_reviews_saved_generation_without_writer_call(self):
        spec = task_spec(0, 'train', 'writer', 'reviewer')
        generated = {'conversations': [{'id': t['id'], 'turns': [
            {'korean': f'새 대화 {i} 차례 {j}', 'english': f'New line {i} {j}.'} for j in range(4)]}
            for i, t in enumerate(spec['tasks'])]}
        reviews = {'accept': {f'{t["id"]}-{j}': True for t in spec['tasks'] for j in range(4)}}
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out / 'generated.json').write_text(json.dumps(generated), encoding='utf-8')
            (out / 'generation.json').write_text(json.dumps({'returned_model': 'writer'}))
            with patch('build_dialogue_corpus.retry_call', return_value=(reviews, {'returned_model': 'reviewer'})) as api:
                rows = process_batch(out, spec, 'http://localhost/v1', 'not-a-real-key')
                self.assertEqual(len(rows), 64)
                self.assertEqual(api.call_count, 1)
                self.assertEqual(api.call_args.args[2], 'reviewer')
            with patch('build_dialogue_corpus.retry_call') as api:
                self.assertEqual(len(process_batch(out, spec, 'http://localhost/v1', 'not-a-real-key')), 64)
                api.assert_not_called()

    def test_binary_verdicts_cannot_silently_coerce_strings_or_skip_ids(self):
        with self.assertRaises(ValueError):
            review_verdicts({'accept': {'a': 'false'}}, ['a'])
        with self.assertRaises(ValueError):
            review_verdicts({'accept': {'a': True}}, ['a', 'b'])
        self.assertFalse(review_verdicts({'accept': {'a': False}}, ['a'])['a']['accept'])

    def test_export_filters_review_vocab_duplicates_and_caps_splits(self):
        def tokenizer(ko, text_target):
            return {'input_ids': [1], 'labels': [99] if text_target == 'unsupported' else [3] if text_target == 'unknown' else [2]}
        tokenizer.unk_token_id = 3
        def row(ko, en, split='train', accepted=True):
            return {'korean': ko, 'english': en, 'split': split, 'review': {'accept': accepted}}
        rows = [row('다른 문장', 'unknown'), row('새 문장 하나', 'unsupported'), row('새 문장 하나', 'A new line.'),
                row('새 문장 하나!', 'Duplicate.'), row('새 문장 둘', 'Wrong.', accepted=False),
                row('평가용 문장', 'Validation.', 'validation'), row('테스트 문장', 'Test.', 'test'),
                row('초과 문장', 'Surplus.')]
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out / 'batches/0000').mkdir(parents=True)
            (out / 'batches/0000/reviewed.json').write_text(json.dumps(rows), encoding='utf-8')
            summary = export(out, {'train': 1, 'validation': 1, 'test': 1}, tokenizer, {1, 2})
            self.assertTrue(summary['complete'])
            rejected = [json.loads(x) for x in (out / 'rejected.jsonl').read_text().splitlines()]
            self.assertEqual(len(rejected), 5)
            self.assertIn('removed_vocabulary_token', {r['filter_reason'] for r in rejected})
            self.assertIn('original_tokenizer_unknown', {r['filter_reason'] for r in rejected})


if __name__ == '__main__':
    unittest.main()
