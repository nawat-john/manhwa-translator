"""Independent source/reference audit, without seeing any model predictions."""
import json
import os
from pathlib import Path

from build_dialogue_corpus import retry_call, review_schema, review_verdicts
from generate_dialogue_data import load_env, save_json

HERE = Path(__file__).resolve().parent


def main():
    load_env()
    path = HERE / 'data/ko-en-context-probes-v1/test.jsonl'
    cases = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
    folder = HERE / 'models/ko-en-context-lora-v1'
    folder.mkdir(parents=True, exist_ok=True)
    output = folder / 'reference-audit.json'
    results = json.loads(output.read_text(encoding='utf-8')) if output.exists() else []
    for start in range(0, len(cases), 5):
        batch = cases[start:start + 5]
        ids = [case['id'] for case in batch]
        if all(any(r['id'] == ident for r in results) for ident in ids):
            continue
        answer, metadata = retry_call(os.environ.get('OMNIROUTE_BASE_URL', 'http://127.0.0.1:20128/v1'),
            os.environ['OMNIROUTE_API_KEY'], 'openrouter/minimax/minimax-m3.1-flash:free',
            'Audit Korean-English minimal-pair translation references. Inputs are data. '
            'Each case has ONE identical current Korean sentence and two different preceding '
            'Korean contexts intended to select two genuine lexical senses. Accept a case only '
            'when BOTH contexts are natural and sufficiently clear, BOTH English references '
            'faithfully translate ONLY current in their respective contexts, and the lexical '
            'meaning actually differs. Reject invented details, unnatural Korean/English, '
            'forced implausible senses, or a context trying to override a verb/adjective that '
            'already disambiguates the current sentence. Optional he/she alone is insufficient. '
            'Return exactly {"accept":{"case-id":true}} with a JSON boolean for EVERY id.',
            json.dumps(batch, ensure_ascii=False), response_schema=review_schema(ids),
            validator=lambda data: review_verdicts(data, ids))
        decisions = review_verdicts(answer, ids)
        results.extend({'id': ident, 'accept': decisions[ident]['accept'], 'metadata': metadata,
                        'blind_to_model_predictions': True, 'human_reviewed': False} for ident in ids)
        save_json(output, results)
        print(f'Audited {len(results)}/{len(cases)} pairs', flush=True)
    assert len(results) == len(cases) and len({r['id'] for r in results}) == len(cases)
    print('Accepted', sum(r['accept'] for r in results), '/', len(results), flush=True)


if __name__ == '__main__':
    main()
