"""Builds the fine-tuning data for RQ3 (LoRA) from the Detroit training situations only.

Each example is one chat in the exact format the model sees in the evaluation (same system prompts as
pilot/run_pilot_v2.py), with the correct answer as the assistant's reply:
  - deciding (roles R1/R2): fact sheet + request  ->  the correct decision JSON, for each of the 3 template wordings
  - form filling (R3-known, R3-full): request  ->  the correct form JSON, one wording each, rotating
10% of the training situations are kept aside as a validation set (by situation, never by wording).
No test situation is ever read. Usage: python prepare_lora_data.py   (writes lora_train.jsonl and lora_val.jsonl here)"""
import json, os, random, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(HERE, '..', 'pilot'))
import run_pilot_v2 as RP, adapt as AD

def chats(c):
    out = []
    for req in c['requests']['template']:
        out.append([{"role": "system", "content": RP.SYSTEM},
                    {"role": "user", "content": c['facts']['with_energy'] + f'\n\nDriver says: "{req}"'},
                    {"role": "assistant", "content": AD.answer_json(c)}])
    k = int(c['id'][-1]) % len(c['requests']['template'])
    for form, full in ((RP.FORM_KNOWN, False), (RP.FORM_FULL, True)):
        req = c['requests']['template'][k]; k = (k + 1) % len(c['requests']['template'])
        out.append([{"role": "system", "content": RP.system_r3(form)}, {"role": "user", "content": f'Driver says: "{req}"'},
                    {"role": "assistant", "content": AD.form_json(c, full)}])
    return out

def main():
    cases = [json.loads(l) for l in open(AD.default_train_path(), encoding='utf-8')]
    assert all(c['split'] == 'train' for c in cases), 'only training situations may be used'
    ids = sorted(c['id'] for c in cases); random.Random(7).shuffle(ids); val = set(ids[:len(ids) // 10])
    n = {'train': 0, 'val': 0}
    with open(os.path.join(HERE, 'lora_train.jsonl'), 'w', encoding='utf-8') as ft, open(os.path.join(HERE, 'lora_val.jsonl'), 'w', encoding='utf-8') as fv:
        for c in cases:
            part = 'val' if c['id'] in val else 'train'
            for m in chats(c):
                (fv if part == 'val' else ft).write(json.dumps({"messages": m}) + '\n'); n[part] += 1
    print(f"{len(cases)} training situations ({len(val)} kept for validation): {n['train']} training chats, {n['val']} validation chats")

if __name__ == '__main__':
    main()
