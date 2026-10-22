"""Check vocabulary filtering and non-contiguous token-ID remapping."""
import unittest
import torch
from experiment_vocab_trim import allowed_piece, remap_inputs


class VocabTrimTests(unittest.TestCase):
    def test_shared_pieces_and_hangul_are_retained(self):
        for piece in ('▁안녕', '▁hello', '▁K팝', '123', '…', '▁café', 'ㅋㅋ'):
            self.assertTrue(allowed_piece(piece), piece)
        for piece in ('▁你好', 'こんにちは', 'привет', 'hello世界'):
            self.assertFalse(allowed_piece(piece), piece)

    def test_mapping_roundtrip_and_removed_token_rejected(self):
        new_to_old = torch.tensor([0, 2, 5, 9])
        old_to_new = torch.full((10,), -1, dtype=torch.long)
        old_to_new[new_to_old] = torch.arange(4)
        inputs = torch.tensor([[9, 2, 0, 5]])
        mapped = remap_inputs(inputs, old_to_new)
        self.assertTrue(torch.equal(new_to_old[mapped], inputs))
        with self.assertRaisesRegex(ValueError, 'removed token'):
            remap_inputs(torch.tensor([[1]]), old_to_new)


if __name__ == '__main__':
    unittest.main()
