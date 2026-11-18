"""Offline prototype: a small language model on this computer plans an EV charging stop.

Everything runs locally. Needs Python 3 (standard library only) and Ollama with a model pulled, for example
    ollama pull qwen2.5:1.5b
Then:
    python app.py                         # menu: pick a situation and a wording
    python app.py --situation 3 --wording 1 --model qwen2.5:3b
    python app.py --situation 3 --own     # type your own request for that situation

What happens for each situation:
 1. The model reads the fact sheet and the driver's sentence and decides (charge?, which charger, up to what %).
 2. An on-device checker tests the answer against facts the car itself knows (plug, status, access, enough battery).
    If something is broken it tells the model why and lets it try once more (role R2).
 3. The referee's verdict is shown: whether the decision keeps every rule and how it compares with the best option.
    The referee's numbers were computed beforehand in SUMO and are stored in demo_situations.json, so no internet
    and no simulator are needed here.
"""
import json, os, re, sys, time, argparse, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
SYSTEM = ("You are the charging assistant in an electric car. Using only the facts given, decide: "
          "1) whether the driver must charge before reaching the destination, 2) if so, at which charger (its letter), "
          "3) up to what battery percentage to charge. Never break a rule: the plug must fit the car, the charger must be "
          "working and public, the battery must never drop below the reserve, and the driver's own limits (arrival time, budget) "
          "must be kept. Among decisions that keep every rule, choose the best one for the driver's goal. "
          'Answer with JSON only, exactly like {"charge": true, "charger": "B", "target_percent": 45} '
          'or {"charge": false, "charger": null, "target_percent": null}.')


def hhmm(m): m = int(round(m)); return f'{m // 60:02d}:{m % 60:02d}'


def ask(model, prompt, url, history=None):
    msgs = [{"role": "system", "content": SYSTEM}] + (history or []) + [{"role": "user", "content": prompt}]
    body = json.dumps({"model": model, "messages": msgs, "stream": False, "format": "json",
                       "options": {"temperature": 0, "seed": 0, "num_ctx": 4096, "num_predict": 128}}).encode()
    req = urllib.request.Request(url + '/api/chat', data=body, headers={'Content-Type': 'application/json'})
    t = time.time(); r = json.loads(urllib.request.urlopen(req, timeout=600).read())
    return r.get('message', {}).get('content', ''), time.time() - t, r


def parse(text):
    try:
        d = json.loads(re.search(r'\{.*\}', text, re.S).group(0))
        ch = bool(d.get('charge')); L = d.get('charger'); t = d.get('target_percent')
        return dict(charge=ch, letter=(str(L).strip().upper()[:1] if ch and L else None),
                    target=(float(t) / 100 if ch and t is not None else None))
    except Exception:
        return None


def check_on_device(s, dec, car, reserve):
    """Only what the car can know from the fact sheet. Returns a list of problems (empty = looks fine)."""
    cap = car['usable_kwh']; now = s['soc0'] * cap; floor = reserve * cap; p = []
    if dec is None: return ['the answer is not valid JSON in the requested format']
    if not dec['charge']:
        if now - s['direct_kwh'] < floor:
            p.append(f"without charging the battery would arrive at {(now - s['direct_kwh']) / cap:.0%}, below the {reserve:.0%} reserve")
        return p
    c = s['chargers'].get(dec['letter'])
    if c is None: return [f"there is no charger {dec['letter']} in the list"]
    plugs = set(c['plugs'].split()); mine = set(car['plugs_dc'] if c['level'] == 'DC' else car['plugs_ac'])
    if not plugs & mine: p.append(f"charger {dec['letter']} has no plug that fits this car")
    if not c['working']: p.append(f"charger {dec['letter']} is out of service")
    if not c['public']: p.append(f"charger {dec['letter']} is private")
    if now - c['kwh_to'] < floor: p.append(f"the battery would be at {(now - c['kwh_to']) / cap:.0%} when reaching {dec['letter']}, below the reserve")
    if dec['target'] is None: p.append('no target percentage was given')
    elif dec['target'] * cap - c['kwh_from'] < floor:
        p.append(f"charging to {dec['target']:.0%} leaves {(dec['target'] * cap - c['kwh_from']) / cap:.0%} at the destination, below the reserve")
    return p


def referee_verdict(s, dec):
    """Look the decision up in the referee's precomputed table of every option."""
    if dec is None: return None, 'no usable answer'
    if not dec['charge']:
        o = [o for o in s['options'] if not o['charge']]
        return (o[0], None) if o else (None, 'not charging was not an option')
    c = s['chargers'].get(dec['letter'])
    if c is None: return None, 'charger not in the list'
    if dec['target'] is None: return None, 'no target given'
    t = min(1.0, max(0.2, -(-round(dec['target'] * 100) // 5) * 5 / 100))   # round up to the 5% grid the referee uses
    o = [o for o in s['options'] if o['charge'] and o['charger'] == c['id'] and abs(o['target'] - t) < 1e-6]
    if not o: return None, f'charging at {dec["letter"]} to {t:.0%} is not possible (battery already above it, or unreachable)'
    return o[0], None


def describe(s, dec, letter_of):
    if dec is None: return 'no usable answer'
    return 'do not charge' if not dec['charge'] else f"charge at {dec['letter']} to {dec['target']:.0%}" if dec['target'] is not None else f"charge at {dec['letter']} (no target)"


def run(s, request, model, url, car, reserve, verify, own):
    print('\n' + '=' * 78 + f"\nSITUATION {s['id']}\n" + '=' * 78)
    print(s['facts']['with_energy']); print(f'\nDriver says: "{request}"\n')
    prompt = s['facts']['with_energy'] + '\n\nDriver says: "' + request + '"'
    try:
        text, wall, raw = ask(model, prompt, url)
    except (urllib.error.URLError, ConnectionError) as e:
        sys.exit(f'Could not reach Ollama at {url} ({e}). Start Ollama and pull the model first: ollama pull {model}')
    dec = parse(text); total = wall
    print(f"[model {model}] {describe(s, dec, None)}   ({wall:.1f} s, {raw.get('prompt_eval_count')} tokens in, {raw.get('eval_count')} out)")
    problems = check_on_device(s, dec, car, reserve)
    if problems:
        print('[on-device check] problems: ' + '; '.join(problems))
        if verify:
            fb = 'Your answer breaks these rules: ' + '; '.join(problems) + '. Decide again. Answer with JSON only.'
            text2, wall2, _ = ask(model, fb, url, history=[{"role": "user", "content": prompt}, {"role": "assistant", "content": text}])
            dec = parse(text2); total += wall2
            print(f"[model, second try] {describe(s, dec, None)}   ({wall2:.1f} s)")
            p2 = check_on_device(s, dec, car, reserve)
            print('[on-device check] ' + ('passes' if not p2 else 'still broken: ' + '; '.join(p2)))
    else:
        print('[on-device check] passes')
    print(f'[time to decide] {total:.1f} s')
    o, why = referee_verdict(s, dec)
    print('\nREFEREE (computed beforehand in SUMO on the real road network)')
    if own:
        print('  You typed your own request, so the referee\'s best answer below is for the original request:')
        print(f'  "{s["requests"][0]}"')
    if o is None:
        print(f'  Decision cannot be carried out: {why}')
    else:
        cost = f"${o['cost']:.2f}"
        print(f"  Outcome: arrive {hhmm(o['arrive_min'])}, charging cost {cost}, battery at destination {o['soc_end']:.0%}")
        if not own: print('  Keeps every rule' if o['valid'] else f"  BREAKS A RULE: {o['broken']}")
    best = 'do not charge' if not s['must_charge'] else f"charge at {s['best_letter']} to {s['best_target']:.0%}"
    print(f"  Best option: {best} (arrive {hhmm(s['best_arrive_min'])}, cost ${s['best_cost']:.2f})")
    if o is not None and o['valid'] and not own:
        gap = (o['arrive_min'] - s['best_arrive_min'], 'min later') if s['goal'] == 'fastest' else (o['cost'] - s['best_cost'], 'dollars more')
        print('  Same result as the best option' if abs(gap[0]) < 0.05 else f"  Compared with the best: {gap[0]:.1f} {gap[1]}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--model', default='qwen2.5:1.5b'); ap.add_argument('--url', default='http://localhost:11434')
    ap.add_argument('--situation', type=int); ap.add_argument('--wording', type=int, default=0, choices=[0, 1, 2])
    ap.add_argument('--own', action='store_true', help='type your own request instead of the stored one')
    ap.add_argument('--no-verify', action='store_true', help='role R1 only: no on-device check and retry')
    a = ap.parse_args()
    data = json.load(open(os.path.join(HERE, 'demo_situations.json'), encoding='utf-8'))
    S = data['situations']
    while True:
        n = a.situation
        if n is None:
            print('\nSituations:')
            for i, s in enumerate(S):
                rules = ', '.join(x for x, v in (('deadline', s['deadline_min']), ('budget', s['budget'])) if v is not None) or 'no limits'
                print(f"  {i:2d}. {s['goal']:8s} {rules:18s} {s['temp_c']:4d} C  battery {s['soc0']:.0%}")
            try: r = input('Pick a number (q to quit): ').strip()
            except EOFError: return
            if r.lower().startswith('q'): return
            if not r.isdigit() or int(r) >= len(S): continue
            n = int(r)
        s = S[n]
        req = input('Your request: ').strip() if a.own else s['requests'][a.wording]
        run(s, req, a.model, a.url, data['car'], data['reserve'], not a.no_verify, a.own)
        if a.situation is not None: return


if __name__ == '__main__':
    main()
