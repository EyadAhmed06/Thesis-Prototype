"""Browser demo of the study (version 2 test). Runs fully offline on this computer.

    python prototype/demo_server.py            # then open http://localhost:8765 (opens by itself)
    python prototype/demo_server.py --port 9000 --url http://localhost:11434

Pick one of the 300 test situations, pick or type the driver's request, pick a model and a role, and press Ask.
The page shows, step by step: exactly what the model reads, its raw answer, the on-device safety check and retry (R2),
or the form it filled and the planner's choice (R3), and then the referee's verdict with the best possible plan.
Without Ollama you can still play "be the model": choose a charger and percentage yourself and the referee grades it.

The verdict uses the same referee code and the same stored SUMO drives as the benchmark (evbench), so a decision
gets the same grade here as in the results tables. Needs Python 3 with pandas and numpy (same as evbench); no SUMO."""
import sys, os, json, time, argparse, threading, webbrowser, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, 'referee')); sys.path.insert(0, os.path.join(ROOT, 'pilot'))
import numpy as np, pandas as pd
from referee import Referee
import baselines as B, score as S
import run_pilot_v2 as P
from score_pilot_v2 import form_to_settings, same_wishes
from select_cases import hhmm

V2 = os.path.join(ROOT, 'referee', 'cases_v2')
CASES = {}; ORDER = []
for l in open(os.path.join(V2, 'test_cases.jsonl'), encoding='utf-8'):
    c = json.loads(l); CASES[c['id']] = c; ORDER.append(c['id'])
DRIVES = json.load(open(os.path.join(V2, 'base', 'test_drives.json')))
R = Referee.__new__(Referee); R.ch = pd.read_csv(os.path.join(ROOT, 'referee', 'chargers.csv')).set_index('id')
PILOT_IDS = set(json.load(open(os.path.join(ROOT, 'pilot', 'pilot_v2_ids.json'))))
LOCK = threading.Lock()

def clean(x):
    if isinstance(x, dict): return {str(k): clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)): return [clean(v) for v in x]
    if isinstance(x, (np.bool_,)): return bool(x)
    if isinstance(x, np.integer): return int(x)
    if isinstance(x, (float, np.floating)): return None if np.isnan(x) else float(x)
    return x

def describe(c, dec):
    """The referee's verdict on one decision, in words and numbers."""
    with LOCK:
        g = S.grade_v2(c, dec, R, DRIVES)
        j = R.judge(c, DRIVES, dec['charge'], dec.get('charger'), dec.get('target'))
    inv = c['letters']
    out = dict(pred_letter=c['letters'].get(dec.get('charger')) if dec['charge'] else None, safe=g['safe'], passed=g['valid'], honest=g['honest'], same_as_referee=bool(g['top1']),
               broken=[b.replace(' Network network', ' network') for b in str(j.get('broken') or '').split('; ') if b],
               gives_up_really=S.broken_categories(j) if g['safe'] else None,
               arrive=hhmm(j['arrive_min']) if j.get('arrive_min') is not None and not pd.isna(j['arrive_min']) else None,
               cost=j.get('cost'), soc_end=j.get('soc_end'), gap=g.get('gap'), gap_unit=g.get('gap_unit'))
    return clean(out)

def best_plan(c):
    return dict(charge=c['must_charge'], letter=c['best_letter'], target=c['best_target'], gives_up=c['gives_up'],
                arrive=hhmm(c['best_arrive_min']), cost=c['best_cost'], soc_end=c['best_soc_end'], broken=c['best_broken'])

def wish_label(w):
    v = w.get('value'); t = w['type']
    if t == 'parked_at': v = hhmm(v)
    if t == 'min_arrival': v = f'{v:.0%}'
    return f"{t.replace('_', ' ')}{'' if v is None else ': ' + str(v)}"

def situation(cid):
    c = CASES[cid]
    return clean(dict(id=cid, facts=c['facts']['with_energy'], requests=c['requests'], goal=c['goal'],
                      deadline=hhmm(c['deadline_min']) if c.get('deadline_min') else None, budget=c.get('budget'),
                      wishes=[wish_label(w) for w in c['wishes']], held_out=c['held_out'], conflict=c['conflict'],
                      letters=sorted(c['letters'].values()), best=best_plan(c), pilot=cid in PILOT_IDS,
                      n_valid=c['n_valid'], close=c['close'], distractor=c['distractor']))

def ask_model(body, url):
    c = CASES[body['id']]; model, role, req = body['model'], body['role'], body['request'].strip()
    inv = {v: k for k, v in c['letters'].items()}; steps = []; t0 = time.time()
    if role.startswith('R3'):
        sysm = P.system_r3(P.FORM_FULL if role == 'R3-full' else P.FORM_KNOWN); user = f'Driver says: "{req}"'
        text, wall, r = P.ask(model, [{"role": "system", "content": sysm}, {"role": "user", "content": user}], url)
        f = P.parse_form(text)
        steps.append(dict(kind='prompt', title='What the model reads', system=sysm, user=user))
        steps.append(dict(kind='answer', title='The form the model filled', raw=text, seconds=wall, tokens=[r.get('prompt_eval_count'), r.get('eval_count')]))
        if f.get('ok'):
            goal, dl, bu, w = form_to_settings(f, c, R)
            with LOCK: d = B.planner(dict(c, goal=goal, deadline_min=dl, budget=bu), DRIVES, R, wishes=w)
            read = dict(goal=goal == c['goal'], deadline=dl == c.get('deadline_min'),
                        budget=(bu is None and c.get('budget') is None) or (bu is not None and c.get('budget') is not None and abs(bu - c['budget']) < 0.01),
                        wishes=same_wishes(w, c['wishes']))
            steps.append(dict(kind='planner', title='The exact planner decides from the form',
                              read=read, understood=dict(goal=goal, deadline=hhmm(dl) if dl else None, budget=bu, wishes=[wish_label(x) for x in w])))
            dec = dict(charge=d['charge'], charger=d['charger'], target=d['target'], gives_up=d['gives_up'])
        else:
            steps.append(dict(kind='check', title='Form not readable', problems=['the answer is not valid JSON']))
            dec = dict(charge=False, charger=None, target=None, gives_up=None)
    else:
        user = c['facts']['with_energy'] + f'\n\nDriver says: "{req}"'
        msgs = [{"role": "system", "content": P.SYSTEM}, {"role": "user", "content": user}]
        text, wall, r = P.ask(model, msgs, url); d = P.parse(text)
        steps.append(dict(kind='prompt', title='What the model reads', system=P.SYSTEM, user=user))
        steps.append(dict(kind='answer', title="The model's answer", raw=text, seconds=wall, tokens=[r.get('prompt_eval_count'), r.get('eval_count')]))
        if role == 'R2':
            probs = P.check_on_device(c, d)
            steps.append(dict(kind='check', title='Safety check on the device (only numbers from the fact sheet)', problems=probs))
            if probs:
                msgs += [{"role": "assistant", "content": text},
                         {"role": "user", "content": 'Your answer breaks these rules: ' + '; '.join(probs) + '. Decide again. Answer with JSON only.'}]
                text2, wall2, r2 = P.ask(model, msgs, url); d = P.parse(text2)
                steps.append(dict(kind='answer', title='Second try', raw=text2, seconds=wall2, tokens=[r2.get('prompt_eval_count'), r2.get('eval_count')]))
        dec = dict(charge=d['charge'], charger=inv.get(d['charger']) if d['charge'] else None, target=d['target'], gives_up=d['gives_up'])
        if d['charge'] and dec['charger'] is None: dec['charger'] = 'not in list'
    shown = dict(charge=dec['charge'], letter=c['letters'].get(dec['charger']) if dec['charge'] else None,
                 target=dec['target'], gives_up=dec['gives_up'])
    return clean(dict(steps=steps, decision=shown, verdict=describe(c, dec), best=best_plan(c), seconds=time.time() - t0))

def grade_manual(body):
    c = CASES[body['id']]; inv = {v: k for k, v in c['letters'].items()}
    ch = bool(body['charge']); dec = dict(charge=ch, charger=inv.get(body.get('letter')) if ch else None,
                                          target=float(body['target']) / 100 if ch and body.get('target') not in (None, '') else None,
                                          gives_up=body.get('gives_up') or [])
    return dict(verdict=describe(c, dec), best=clean(best_plan(c)))

class H(BaseHTTPRequestHandler):
    def send(self, obj, code=200, ctype='application/json'):
        b = obj if isinstance(obj, bytes) else json.dumps(obj).encode()
        self.send_response(code); self.send_header('Content-Type', ctype); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        u = urlparse(self.path); q = parse_qs(u.query)
        if u.path == '/': return self.send(open(os.path.join(HERE, 'demo.html'), 'rb').read(), ctype='text/html; charset=utf-8')
        if u.path.startswith('/ui/') and '..' not in u.path:
            return self.send(open(os.path.join(ROOT, u.path.lstrip('/')), 'rb').read(), ctype='text/css' if u.path.endswith('.css') else 'text/javascript')
        if u.path == '/api/maps': return self.send(open(os.path.join(V2, 'test_maps.json'), 'rb').read())
        if u.path == '/api/situations':
            return self.send([clean(dict(id=i, goal=CASES[i]['goal'], n_wishes=CASES[i]['n_wishes'], conflict=CASES[i]['conflict'],
                                         held_out=CASES[i]['held_out'], must_charge=CASES[i]['must_charge'], pilot=i in PILOT_IDS,
                                         request=CASES[i]['requests']['template'][0])) for i in ORDER])
        if u.path == '/api/situation': return self.send(situation(q['id'][0]))
        if u.path == '/api/models':
            try:
                t = json.loads(urllib.request.urlopen(self.server.ollama + '/api/tags', timeout=3).read())
                return self.send(dict(ok=True, models=sorted(m['name'] for m in t.get('models', []))))
            except Exception as ex: return self.send(dict(ok=False, models=[], error=str(ex)))
        self.send({'error': 'not found'}, 404)
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])) or b'{}')
        try:
            if self.path == '/api/ask': return self.send(ask_model(body, self.server.ollama))
            if self.path == '/api/grade': return self.send(grade_manual(body))
        except Exception as ex: return self.send({'error': f'{type(ex).__name__}: {ex}'}, 500)
        self.send({'error': 'not found'}, 404)
    def log_message(self, *a): pass

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--port', type=int, default=8765); ap.add_argument('--url', default='http://localhost:11434')
    ap.add_argument('--no-browser', action='store_true'); a = ap.parse_args()
    srv = ThreadingHTTPServer(('127.0.0.1', a.port), H); srv.ollama = a.url
    print(f'Demo running at http://localhost:{a.port}  (Ollama expected at {a.url}). Press Ctrl+C to stop.')
    if not a.no_browser: threading.Timer(1, lambda: webbrowser.open(f'http://localhost:{a.port}')).start()
    try: srv.serve_forever()
    except KeyboardInterrupt: pass

if __name__ == '__main__':
    main()
