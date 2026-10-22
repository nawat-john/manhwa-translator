"""Bounded source-only context; never include future turns or another conversation."""
from collections import defaultdict
import json

from train_dialogue_lora import HERE, DATA

PROBES = HERE / 'data/ko-en-context-probes-v1'
DERIVED = HERE / 'work/ko-en-context-data-v1'
CONTEXT_OUT = HERE / 'models/ko-en-context-lora-v1'


def read_rows(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]


def source_with_context(current, previous, tokenizer):
    previous = previous[-3:]
    while True:
        source = 'Context: ' + '\n'.join(previous) + '\nCurrent: ' + current
        if len(tokenizer(source)['input_ids']) <= 128:
            return source
        if not previous:
            raise ValueError('Current sentence exceeds context input budget')
        previous = previous[1:]


def conversation_rows(rows, tokenizer):
    conversations = defaultdict(list)
    for row in rows:
        conversations[row['conversation_id']].append(row)
    result = []
    for conversation in conversations.values():
        previous = []
        turns = [r['turn'] for r in conversation]
        if len(set(turns)) != len(turns):
            raise ValueError('Duplicate conversation turn')
        for row in sorted(conversation, key=lambda r: r['turn']):
            result.append({**row, 'current_korean': row['korean'], 'previous': previous[-3:],
                           'korean': source_with_context(row['korean'], previous, tokenizer)})
            previous.append(row['korean'])
    return result


def main():
    from build_dialogue_corpus import load_vocabulary
    tokenizer, vocabulary = load_vocabulary()
    DERIVED.mkdir(parents=True, exist_ok=True)
    for split in ('train', 'validation', 'test'):
        rows = conversation_rows(read_rows(DATA / f'{split}.jsonl'), tokenizer)
        for probe in read_rows(PROBES / f'{split}.jsonl'):
            for variant, case in enumerate(probe['variants']):
                row = {'id': f"{probe['id']}-{variant}", 'conversation_id': probe['id'],
                             'turn': variant, 'current_korean': probe['current'], 'previous': case['previous'],
                             'korean': source_with_context(probe['current'], case['previous'], tokenizer),
                             'english': case['english'], 'probe': True}
                rows.append(row)
                if split == 'train':
                    rows.append({**row, 'id': row['id'] + '-repeat'})
        for row in rows:
            encoded = tokenizer(row['korean'], text_target=row['english'])
            ids = encoded['input_ids'] + encoded['labels']
            if tokenizer.unk_token_id in ids or not set(ids) <= vocabulary:
                raise ValueError('Unusable token in context data')
        (DERIVED / f'{split}.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows),
                                               encoding='utf-8', newline='\n')
        print(split, len(rows), flush=True)


if __name__ == '__main__':
    main()
