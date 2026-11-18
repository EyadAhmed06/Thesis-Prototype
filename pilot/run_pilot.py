"""Pilot run of small language models on the charging situations (role R1: the model decides alone).
Needs only Python 3 and Ollama (https://ollama.com) running on this computer. No other installs.

  ollama pull qwen2.5:0.5b
  ollama pull qwen2.5:1.5b
  ollama pull qwen2.5:3b
  python run_pilot.py                      # all 3 models, all situations in pilot_cases.jsonl
  python run_pilot.py --models qwen2.5:0.5b --limit 5      # quick check

Writes pilot_results.jsonl (one line per model x situation). Send that file back for scoring."""
import json, re, time, argparse, platform, subprocess, urllib.request

SYSTEM = ("You are the charging assistant in an electric car. Using only the facts given, decide: "
          "1) whether the driver must charge before reaching the destination, 2) if so, at which charger (its letter), "
          "3) up to what battery percentage to charge. Never break a rule: the plug must fit the car, the charger must be "
          "working and public, the battery must never drop below the reserve, and the driver's own limits (arrival time, budget) "
          "must be kept. Among decisions that keep every rule, choose the best one for the driver's goal. "
          'Answer with JSON only, exactly like {"charge": true, "charger": "B", "target_percent": 45} '
          'or {"charge": false, "charger": null, "target_percent": null}.')

SYSTEM_R3 = ("You turn an electric-car driver's request into settings for a charging planner. "
             'Answer with JSON only, exactly like {"goal": "fastest", "deadline": "14:30", "budget": 8.5}. '
             'goal is "fastest" or "cheapest"; deadline is the latest arrival time the driver states (24-hour HH:MM) or null; '
             'budget is the most the driver will spend on charging in dollars, or null.')

def ask(model, prompt, url, system=SYSTEM):
    body = json.dumps({"model": model, "system": system, "prompt": prompt, "stream": False, "format": "json",
                       "options": {"temperature": 0, "seed": 0, "num_ctx": 4096, "num_predict": 128}}).encode()
    req = urllib.request.Request(url + '/api/generate', data=body, headers={'Content-Type': 'application/json'})
    t = time.time(); r = json.loads(urllib.request.urlopen(req, timeout=600).read()); wall = time.time() - t
    return r, wall

def parse(text):
    try:
        m = re.search(r'\{.*\}', text, re.S); d = json.loads(m.group(0))
        ch = bool(d.get('charge')); L = d.get('charger'); t = d.get('target_percent')
        return dict(ok=True, charge=ch, charger=(str(L).strip().upper()[:1] if ch and L else None),
                    target=(float(t) / 100 if ch and t is not None else None))
    except Exception as e:
        return dict(ok=False, charge=False, charger=None, target=None)

def parse_r3(text):
    try:
        d = json.loads(re.search(r'\{.*\}', text, re.S).group(0))
        dl = d.get('deadline'); b = d.get('budget')
        if dl: h, m = str(dl).strip().split(':')[:2]; dl = int(h) * 60 + int(m[:2])
        return dict(ok=True, goal=str(d.get('goal', '')).lower().strip(), deadline_min=dl or None,
                    budget=(float(str(b).replace('$', '')) if b not in (None, '', 'null') else None))
    except Exception:
        return dict(ok=False, goal=None, deadline_min=None, budget=None)

def model_size(model, url):
    try: return [m for m in json.loads(urllib.request.urlopen(url + '/api/ps').read())['models'] if m['name'].startswith(model)][0].get('size')
    except Exception: return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--models', nargs='+', default=['qwen2.5:0.5b', 'qwen2.5:1.5b', 'qwen2.5:3b'])
    ap.add_argument('--cases', default='pilot_cases.jsonl'); ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--facts', default='with_energy', choices=['with_energy', 'without_energy'])
    ap.add_argument('--wording', type=int, default=0); ap.add_argument('--url', default='http://localhost:11434')
    ap.add_argument('--out', default='pilot_results.jsonl')
    ap.add_argument('--role', default='R1', choices=['R1', 'R3'], help='R1: model decides alone; R3: model only reads the request, the planner decides')
    a = ap.parse_args()
    cases = [json.loads(l) for l in open(a.cases, encoding='utf-8')]
    if a.limit: cases = cases[:a.limit]
    machine = dict(system=platform.platform(), cpu=platform.processor(), python=platform.python_version())
    with open(a.out, 'a', encoding='utf-8') as f:
        for model in a.models:
            ask(model, 'Say {"charge": false, "charger": null, "target_percent": null}', a.url)   # load the model once
            mem = model_size(model, a.url)
            for i, c in enumerate(cases):
                if a.role == 'R1':
                    prompt = c['facts'][a.facts] + '\n\nDriver says: "' + c['requests'][a.wording] + '"'
                    r, wall = ask(model, prompt, a.url); p = parse(r.get('response', ''))
                else:
                    r, wall = ask(model, 'Driver says: "' + c['requests'][a.wording] + '"', a.url, SYSTEM_R3); p = parse_r3(r.get('response', ''))
                row = dict(model=model, role=a.role, facts=a.facts, wording=a.wording, id=c['id'], raw=r.get('response'), **p,
                           wall_s=round(wall, 3), prompt_tokens=r.get('prompt_eval_count'), output_tokens=r.get('eval_count'),
                           prompt_s=(r.get('prompt_eval_duration') or 0) / 1e9, output_s=(r.get('eval_duration') or 0) / 1e9,
                           model_bytes_in_memory=mem, machine=machine)
                f.write(json.dumps(row) + '\n'); f.flush()
                print(f"{model} {i + 1}/{len(cases)} {c['id']}: {p} in {wall:.1f}s")

if __name__ == '__main__':
    main()
