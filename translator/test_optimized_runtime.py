"""Check FP16 conversion boundaries and vocabulary coverage fallback without loading weights."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import torch
from korean_translation import KoreanTranslator
from ocr_precision import FP16Network, use_fp16


class TupleNetwork(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.projection = torch.nn.Linear(3, 2)

    def forward(self, image, labels):
        assert image.dtype == torch.float16
        assert labels.dtype == torch.long
        return self.projection(image), image


class OptimizedTests(unittest.TestCase):
    def test_fp16_preserves_integer_inputs_and_returns_fp32(self):
        wrapper = FP16Network(TupleNetwork())
        result, feature = wrapper(torch.ones(2, 3), torch.ones(2, dtype=torch.long))
        self.assertEqual(next(wrapper.parameters()).dtype, torch.float16)
        self.assertEqual(result.dtype, torch.float32)
        self.assertEqual(feature.dtype, torch.float32)
        self.assertTrue(torch.isfinite(result).all())
        with self.assertRaisesRegex(ValueError, 'CUDA'):
            use_fp16(SimpleNamespace(device='cpu'))

    def test_removed_source_token_uses_original_cpu_model(self):
        translator = KoreanTranslator.__new__(KoreanTranslator)
        translator.device = 'cpu'
        translator.old_to_new = torch.tensor([0, -1, 1])
        translator.new_to_old = torch.tensor([0, 2])
        translator.fallback = None
        translator.model = Mock()
        batch = Mock()
        batch.to.return_value = {'input_ids': torch.tensor([[1]])}
        translator.tokenizer = Mock(return_value=batch)
        translator.tokenizer.get_lang_id.return_value = 2
        translator.tokenizer.decode.return_value = 'Fallback translation'
        fallback = Mock()
        fallback.generate.return_value = torch.tensor([[0, 2]])
        with patch('korean_translation.M2M100ForConditionalGeneration.from_pretrained') as load:
            load.return_value.eval.return_value = fallback
            self.assertEqual(translator.translate('foreign script'), 'Fallback translation')
            self.assertEqual(translator.translate('foreign script'), 'Fallback translation')
            load.assert_called_once()
        translator.model.generate.assert_not_called()
        self.assertEqual(fallback.generate.call_count, 2)


if __name__ == '__main__':
    unittest.main()
