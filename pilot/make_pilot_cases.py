"""Pick 30 test situations for the laptop pilot: 15 must charge, 15 need not, round-robin over the difficulty cells.
Answers are left out of the file that goes to the laptop."""
import json, random
cs = [json.loads(l) for l in open('/mnt/project-files/referee/cases/test_cases.jsonl')]
random.seed(3); pick = []
for mc in (True, False):
    cells = {}
    for c in cs:
        if c['must_charge'] == mc: cells.setdefault((c['n_rules'], c['close'], c['distractor']), []).append(c)
    for v in cells.values(): random.shuffle(v)
    keys = sorted(cells); k = 0
    while sum(p['must_charge'] == mc for p in pick) < 15:
        v = cells[keys[k % len(keys)]]
        if v: pick.append(v.pop())
        k += 1
random.shuffle(pick)
with open('pilot_cases.jsonl', 'w') as f:
    for c in pick: f.write(json.dumps({'id': c['id'], 'facts': c['facts'], 'requests': c['requests']}) + '\n')
print(len(pick), sum(p['must_charge'] for p in pick), sum(p['close'] for p in pick), sum(p['distractor'] for p in pick))
