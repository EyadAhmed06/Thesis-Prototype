"""Version 2 of the model run (driver wishes + priority order; see redesign/SPEC.md).
Needs only Python 3 and Ollama running on this computer.

  python run_pilot_v2.py --role R1                       # model decides alone
  python run_pilot_v2.py --role R2                       # model decides, on-device safety check, one retry
  python run_pilot_v2.py --role R3-known                 # model only fills in a form (training wish types), exact planner decides
  python run_pilot_v2.py --role R3-full                  # same, form has every wish type (upper bound for reading-only)
Options: --models, --cases, --limit, --ids, --profile NAME --threads N (edge profile), --facts with_energy|without_energy, --wording template|paraphrase|human, --variant 0-2
Writes one line per model x situation to pilot_v2_results.jsonl. Send that file back for scoring."""
import json, re, time, argparse, platform, urllib.request

SYSTEM = ("You are the charging assistant in an electric car. Using only the facts given, decide: "
          "1) whether to charge before reaching the destination, 2) if so, at which charger (its letter), "
          "3) up to what battery percentage to charge. Safety rules can never be broken: the plug must fit the car, "
          "the charger must be working and public, and the battery must never drop below the reserve. "
          "Then keep as many of the driver's requests as you can, in this order of importance: the arrival time first, "
          "then the charging budget, then any other wishes. Among the decisions that keep the most, choose the best one "
          "for the driver's goal (fastest or cheapest). If you cannot keep everything, say what you give up, using only the "
          'words "arrival time", "budget" and "wishes". Answer with JSON only, exactly like '
          '{"charge": true, "charger": "B", "target_percent": 45, "gives_up": []} or '
          '{"charge": false, "charger": null, "target_percent": null, "gives_up": ["wishes"]}.')

FORM_KNOWN = ('{"goal": "fastest" or "cheapest", "deadline": "HH:MM" or null, "budget": dollars or null, '
              '"max_wait_minutes": number or null, "avoid_network": network name or null, "min_arrival_percent": number or null, '
              '"other": any other wish in the driver\'s words, or null}')
FORM_FULL = FORM_KNOWN[:-1].replace(', "other"', ', "parked_at": "HH:MM" or null, "free_only": true or false, '
                                     '"stop_city": city name or null, "no_fast": true or false, "other"') + '}'
def system_r3(form):
    return ("You turn an electric-car driver's request into settings for a charging planner. Fill in this form and answer "
            "with JSON only: " + form + ". Use null for anything the driver does not ask for.")

THREADS = None   # set by --threads: CPU threads Ollama may use (edge profile); None = Ollama's default (all cores)

def ask(model, messages, url):
    opts = {"temperature": 0, "seed": 0, "num_ctx": 4096, "num_predict": 160}
    if THREADS: opts["num_thread"] = THREADS
    body = json.dumps({"model": model, "messages": messages, "stream": False, "format": "json", "options": opts}).encode()
    req = urllib.request.Request(url + '/api/chat', data=body, headers={'Content-Type': 'application/json'})
    t = time.time(); r = json.loads(urllib.request.urlopen(req, timeout=600).read())
    return r.get('message', {}).get('content', ''), time.time() - t, r

def memory_gb(model, url):
    """Memory the loaded model takes, as Ollama reports it (/api/ps), in GB."""
    try:
        for m in json.loads(urllib.request.urlopen(url + '/api/ps', timeout=5).read()).get('models', []):
            if m.get('name') == model or m.get('model') == model: return round(m.get('size', 0) / 1e9, 3)
    except Exception: pass
    return None

def speed(r):
    """Timings Ollama measures itself (nanoseconds -> seconds, tokens per second)."""
    ns = lambda k: (r.get(k) or 0) / 1e9
    return dict(load_s=round(ns('load_duration'), 3), read_s=round(ns('prompt_eval_duration'), 3), write_s=round(ns('eval_duration'), 3),
                read_tok_s=round(r['prompt_eval_count'] / ns('prompt_eval_duration'), 1) if r.get('prompt_eval_count') and r.get('prompt_eval_duration') else None,
                write_tok_s=round(r['eval_count'] / ns('eval_duration'), 1) if r.get('eval_count') and r.get('eval_duration') else None)

def parse(text):
    try:
        d = json.loads(re.search(r'\{.*\}', text, re.S).group(0))
        ch = bool(d.get('charge')); L = d.get('charger'); t = d.get('target_percent'); g = d.get('gives_up')
        return dict(ok=True, charge=ch, charger=(str(L).strip().upper()[:1] if ch and L else None),
                    target=(float(t) / 100 if ch and t is not None else None),
                    gives_up=[str(x).lower().strip() for x in g] if isinstance(g, list) else None)
    except Exception:
        return dict(ok=False, charge=False, charger=None, target=None, gives_up=None)

def parse_form(text):
    try:
        d = json.loads(re.search(r'\{.*\}', text, re.S).group(0)); d['ok'] = True; return d
    except Exception:
        return dict(ok=False)

def check_on_device(c, dec):
    """Role R2: only safety rules, using only numbers printed in the fact sheet (shipped as c['device'])."""
    dv = c['device']; cap = dv['usable_kwh']; now = c['soc0'] * cap; floor = dv['reserve'] * cap; p = []
    if not dec['ok']: return ['the answer is not valid JSON in the requested format']
    if not dec['charge']:
        if now - dv['direct_kwh'] < floor: p.append(f"without charging the battery would arrive at {(now - dv['direct_kwh']) / cap:.0%}, below the reserve")
        return p
    x = dv['chargers'].get(dec['charger'])
    if x is None: return [f"there is no charger {dec['charger']} in the list"]
    if not x['plug_fits']: p.append(f"charger {dec['charger']} has no plug that fits this car")
    if not x['working']: p.append(f"charger {dec['charger']} is out of service")
    if not x['public']: p.append(f"charger {dec['charger']} is private")
    if now - x['kwh_to'] < floor: p.append(f"the battery would be at {(now - x['kwh_to']) / cap:.0%} when reaching {dec['charger']}, below the reserve")
    if dec['target'] is None: p.append('no target percentage was given')
    elif dec['target'] * cap - x['kwh_from'] < floor: p.append(f"charging to {dec['target']:.0%} leaves too little battery at the destination")
    return p

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--models', nargs='+', default=['qwen2.5:0.5b', 'qwen2.5:1.5b', 'qwen2.5:3b'])
    ap.add_argument('--cases', default='pilot_v2_cases.jsonl'); ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--facts', default='with_energy', choices=['with_energy', 'without_energy'])
    ap.add_argument('--wording', default='template', choices=['template', 'paraphrase', 'human']); ap.add_argument('--variant', type=int, default=0)
    ap.add_argument('--role', default='R1', choices=['R1', 'R2', 'R3-known', 'R3-full'])
    ap.add_argument('--url', default='http://localhost:11434'); ap.add_argument('--out', default='pilot_v2_results.jsonl')
    ap.add_argument('--ids', default=None, help='JSON file with the situation ids to run (default: all in --cases)')
    ap.add_argument('--profile', default='laptop', help='name of the edge profile, stored with every answer')
    ap.add_argument('--threads', type=int, default=0, help='CPU threads the model may use (0 = all)')
    a = ap.parse_args(); global THREADS; THREADS = a.threads or None
    cases = [json.loads(l) for l in open(a.cases, encoding='utf-8')]
    if a.ids:
        keep = json.load(open(a.ids)); order = {k: i for i, k in enumerate(keep)}
        cases = sorted([c for c in cases if c['id'] in order], key=lambda c: order[c['id']])
    cases = [c for c in cases if c['requests'].get(a.wording)]
    if a.limit: cases = cases[:a.limit]
    machine = dict(system=platform.platform(), cpu=platform.processor(), python=platform.python_version())
    done = set()   # resume: answers already in the output file are not asked again
    try:
        for l in open(a.out, encoding='utf-8'):
            r = json.loads(l); done.add((r['model'], r['role'], r['facts'], r['wording'], r['variant'], r.get('profile', 'laptop'), r['id']))
    except FileNotFoundError: pass
    with open(a.out, 'a', encoding='utf-8') as f:
        for model in a.models:
            todo = [c for c in cases if (model, a.role, a.facts, a.wording, a.variant, a.profile, c['id']) not in done]
            if not todo: print(f'{model} {a.role} {a.wording} {a.profile}: all {len(cases)} already answered'); continue
            ask(model, [{"role": "user", "content": 'Say {"ok": true}'}], a.url)   # load the model once
            t0 = time.time()
            for i, c in enumerate(todo):
                req = c['requests'][a.wording]; req = req[a.variant % len(req)]
                row = dict(model=model, role=a.role, facts=a.facts, wording=a.wording, variant=a.variant, profile=a.profile, threads=THREADS, id=c['id'], machine=machine)
                if a.role.startswith('R3'):
                    msgs = [{"role": "system", "content": system_r3(FORM_FULL if a.role == 'R3-full' else FORM_KNOWN)},
                            {"role": "user", "content": f'Driver says: "{req}"'}]
                    text, wall, r = ask(model, msgs, a.url); row.update(raw=text, form=parse_form(text), **speed(r))
                else:
                    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": c['facts'][a.facts] + f'\n\nDriver says: "{req}"'}]
                    text, wall, r = ask(model, msgs, a.url); dec = parse(text); row.update(raw=text, first=dec, **speed(r))
                    if a.role == 'R2':
                        problems = check_on_device(c, dec); row['problems'] = problems
                        if problems:
                            msgs += [{"role": "assistant", "content": text},
                                     {"role": "user", "content": 'Your answer breaks these rules: ' + '; '.join(problems) + '. Decide again. Answer with JSON only.'}]
                            text2, wall2, r = ask(model, msgs, a.url); dec = parse(text2); wall += wall2; row['raw_retry'] = text2
                    row['decision'] = dec
                row.update(wall_s=round(wall, 3), prompt_tokens=r.get('prompt_eval_count'), output_tokens=r.get('eval_count'), memory_gb=memory_gb(model, a.url))
                f.write(json.dumps(row) + '\n'); f.flush()
                left = (time.time() - t0) / (i + 1) * (len(todo) - i - 1)
                print(f"{model} {a.role} {a.wording} {a.profile} {i + 1}/{len(todo)} {c['id']} in {wall:.1f}s (about {left / 60:.0f} min left for this part)")

if __name__ == '__main__':
    main()
