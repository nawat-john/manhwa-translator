"""Train a reproducible LoRA on the audited corpus; select by validation loss."""
import json
import hashlib
import random
import time
from pathlib import Path

import torch
from peft import LoraConfig, TaskType, get_peft_model
from torch.utils.data import DataLoader
from transformers import M2M100ForConditionalGeneration, M2M100Tokenizer

HERE = Path(__file__).resolve().parent
BASE = HERE / 'models/m2m100-ko-en'
DATA = HERE / 'data/ko-en-dialogue-6k-v1'
OUT = HERE / 'models/ko-en-dialogue-lora-v1'


def encode(rows, tokenizer, mapping):
    encoded = []
    for row in rows:
        item = tokenizer(row['korean'], text_target=row['english'])
        for key in ('input_ids', 'labels'):
            item[key] = [mapping[i] for i in item[key]]
            if min(item[key]) < 0:
                raise ValueError('Corpus contains a removed token')
        encoded.append(item)
    return encoded


def collate(rows):
    batch = {}
    for key in ('input_ids', 'attention_mask', 'labels'):
        length = max(len(row[key]) for row in rows)
        pad = -100 if key == 'labels' else (1 if key == 'input_ids' else 0)
        batch[key] = torch.tensor([row[key] + [pad] * (length - len(row[key])) for row in rows])
    return batch


def main():
    torch.manual_seed(80421)
    random.seed(80421)
    torch.set_num_threads(4)
    OUT.mkdir(parents=True, exist_ok=True)
    keep = json.loads((BASE / 'id-map.json').read_text())['new_to_old']
    mapping = {old: new for new, old in enumerate(keep)}
    tokenizer = M2M100Tokenizer.from_pretrained(BASE / 'original-tokenizer', src_lang='ko', tgt_lang='en')
    loaders = {}
    for split in ('train', 'validation'):
        rows = [json.loads(line) for line in (DATA / f'{split}.jsonl').read_text(encoding='utf-8').splitlines()]
        loaders[split] = DataLoader(encode(rows, tokenizer, mapping), batch_size=8,
                                   shuffle=split == 'train', collate_fn=collate)
    model = M2M100ForConditionalGeneration.from_pretrained(BASE, dtype=torch.float16).to('cuda')
    model.config.use_cache = False
    model = get_peft_model(model, LoraConfig(task_type=TaskType.SEQ_2_SEQ_LM, r=16,
                           lora_alpha=32, lora_dropout=0.05, target_modules=['q_proj', 'v_proj']))
    model.gradient_checkpointing_enable()
    model.enable_input_require_grads()
    model.print_trainable_parameters()
    optimizer = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=0.0001)
    scaler = torch.amp.GradScaler('cuda')
    history = []
    started = time.monotonic()

    def validation():
        model.eval()
        total = tokens = 0
        with torch.no_grad(), torch.autocast('cuda', dtype=torch.float16):
            for batch in loaders['validation']:
                batch = {k: v.to('cuda') for k, v in batch.items()}
                n = int((batch['labels'] != -100).sum())
                total += model(**batch).loss.item() * n
                tokens += n
        return total / tokens

    baseline = validation()
    best = baseline
    print(json.dumps({'baseline_validation_loss': baseline}), flush=True)
    for epoch in range(1, 4):
        model.train()
        optimizer.zero_grad(set_to_none=True)
        for step, batch in enumerate(loaders['train'], 1):
            batch = {k: v.to('cuda') for k, v in batch.items()}
            with torch.autocast('cuda', dtype=torch.float16):
                loss = model(**batch).loss
            if not torch.isfinite(loss):
                raise RuntimeError('Non-finite training loss')
            scaler.scale(loss / 4).backward()
            if step % 4 == 0 or step == len(loaders['train']):
                scaler.unscale_(optimizer)
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                scaler.step(optimizer)
                scaler.update()
                optimizer.zero_grad(set_to_none=True)
            if step % 25 == 0:
                print(json.dumps({'epoch': epoch, 'batch': step, 'loss': loss.item(),
                                  'elapsed_s': round(time.monotonic() - started)}), flush=True)
        score = validation()
        history.append({'epoch': epoch, 'validation_loss': score})
        if score < best:
            best = score
            model.save_pretrained(OUT / 'best')
        report = {'baseline_validation_loss': baseline, 'history': history,
                  'best_validation_loss': best, 'elapsed_s': time.monotonic() - started,
                  'seed': 80421, 'batch_size': 8, 'gradient_accumulation': 4,
                  'learning_rate': 0.0001, 'base': str(BASE), 'dataset': str(DATA)}
        report['sha256'] = {str(path.relative_to(HERE)): hashlib.sha256(path.read_bytes()).hexdigest()
                            for path in [DATA / 'train.jsonl', DATA / 'validation.jsonl', BASE / 'id-map.json']}
        (OUT / 'training.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
