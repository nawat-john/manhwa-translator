"""Korean → English inference using a vocabulary-trimmed base when installed."""
from pathlib import Path
import json

import torch
from transformers import M2M100ForConditionalGeneration, M2M100Tokenizer

HERE = Path(__file__).resolve().parent
MODEL = 'facebook/m2m100_418M'
REVISION = '55c2e61bbf05dfb8d7abccdc3fae6fc8512fd636'
TRIMMED = HERE / 'models/m2m100-ko-en'


def remap_inputs(ids, old_to_new):
    mapped = old_to_new[ids]
    if (mapped < 0).any():
        raise ValueError('Input contains a removed token; use the original model')
    return mapped


class KoreanTranslator:
    def __init__(self, device):
        self.device = device
        self.old_to_new = self.new_to_old = None
        self.fallback = None
        if TRIMMED.is_dir():
            mapping = json.loads((TRIMMED / 'id-map.json').read_text(encoding='utf-8'))
            keep = mapping['new_to_old']
            if not keep or keep != sorted(set(keep)) or keep[0] < 0 or keep[-1] >= mapping['original_vocab_size']:
                raise ValueError('Invalid trimmed vocabulary mapping')
            self.tokenizer = M2M100Tokenizer.from_pretrained(TRIMMED / 'original-tokenizer', src_lang='ko', local_files_only=True)
            self.model = M2M100ForConditionalGeneration.from_pretrained(TRIMMED, local_files_only=True).eval().to(device)
            if len(keep) != self.model.config.vocab_size:
                raise ValueError('Trimmed model and vocabulary mapping do not match')
            self.new_to_old = torch.tensor(keep, device=device)
            self.old_to_new = torch.full((mapping['original_vocab_size'],), -1, dtype=torch.long, device=device)
            self.old_to_new[self.new_to_old] = torch.arange(len(keep), device=device)
            for token in [self.tokenizer.get_lang_id('ko'), self.tokenizer.get_lang_id('en'), *self.tokenizer.all_special_ids]:
                if token >= len(self.old_to_new) or int(self.old_to_new[token]) < 0:
                    raise ValueError('A required special token is missing')
            print(f'Loaded trimmed KO/EN base: {len(keep)} tokens', flush=True)
        else:
            self.tokenizer = M2M100Tokenizer.from_pretrained(MODEL, revision=REVISION, src_lang='ko')
            self.model = M2M100ForConditionalGeneration.from_pretrained(MODEL, revision=REVISION).eval().to(device)
            print('Trimmed base not installed; using original M2M100', flush=True)

    def translate(self, text):
        inputs = self.tokenizer(text, return_tensors='pt').to(self.device)
        english = self.tokenizer.get_lang_id('en')
        if self.old_to_new is not None:
            if (self.old_to_new[inputs['input_ids']] < 0).any():
                # Rare Hanja/foreign-script input must not silently become unknown tokens.
                if self.fallback is None:
                    print('Removed input token encountered; loading original model on CPU', flush=True)
                    self.fallback = M2M100ForConditionalGeneration.from_pretrained(MODEL, revision=REVISION).eval()
                with torch.inference_mode():
                    ids = self.fallback.generate(**{k: v.cpu() for k, v in inputs.items()},
                        forced_bos_token_id=english, max_new_tokens=160, num_beams=5, no_repeat_ngram_size=3)[0]
                return self.tokenizer.decode(ids, skip_special_tokens=True).strip()
            inputs['input_ids'] = remap_inputs(inputs['input_ids'], self.old_to_new)
            english = int(self.old_to_new[english])
        with torch.inference_mode():
            ids = self.model.generate(**inputs, forced_bos_token_id=english,
                                     max_new_tokens=160, num_beams=5, no_repeat_ngram_size=3)[0]
        if self.new_to_old is not None:
            ids = self.new_to_old[ids]
        return self.tokenizer.decode(ids, skip_special_tokens=True).strip()
