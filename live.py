"""Live dashboard for evbench. Started by `python evbench.py run` (opens in the browser) or on its own with
`python evbench.py dashboard` to look through finished results. Grades every model answer as it arrives with the same
referee code as the score stage. Local only (127.0.0.1); nothing leaves the computer."""
import os, sys, json, time, threading, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

STATE = dict(running=False, started=None, stages={}, current=None, log=[], error=None, planned_answers=None, config={})
_G = {}   # lazily loaded grading data
_LOCK = threading.Lock()

def log(msg):
    STATE['log'] = (STATE['log'] + [f'{time.strftime("%H:%M:%S")} {msg}'])[-60:]

def _grader(here):
    with _LOCK:
        if not _G:
            sys.path.insert(0, os.path.join(here, 'referee')); sys.path.insert(0, os.path.join(here, 'pilot'))
            import pandas as pd
            from referee import Referee
            import score_pilot_v2 as SP
            v2 = os.path.join(here, 'referee', 'cases_v2')
            _G['cases'] = {json.loads(l)['id']: json.loads(l) for l in open(os.path.join(v2, 'test_cases.jsonl'), encoding='utf-8')}
            _G['drives'] = json.load(open(os.path.join(v2, 'base', 'test_drives.json')))
            R = Referee.__new__(Referee); R.ch = pd.read_csv(os.path.join(here, 'referee', 'chargers.csv')).set_index('id'); _G['R'] = R
            _G['SP'] = SP; _G['rows'] = []; _G['pos'] = 0; _G['file'] = None
    return _G

def _wish(w):
    from select_cases import hhmm
    v = w.get('value'); t = w['type']
    if t == 'parked_at': v = hhmm(v)
    if t == 'min_arrival': v = f'{v:.0%}'
    if t == 'avoid_network': v = str(v).replace(' Network', '')
    return t.replace('_', ' ') + ('' if v is None else f': {v}')

def answers(here, out, since):
    """Grade any new lines of outputs/model_answers.jsonl and return rows from index `since`."""
    G = _grader(here); p = os.path.join(out, 'model_answers.jsonl')
    if not os.path.exists(p): return []
    with _LOCK:
        if G['file'] != p: G['rows'], G['pos'], G['file'] = [], 0, p
        with open(p, encoding='utf-8') as f:
            f.seek(G['pos'])
            while True:
                l = f.readline()
                if not l or not l.endswith('\n'): break
                G['pos'] = f.tell(); r = json.loads(l); c = G['cases'].get(r['id'])
                if c is None: continue
                try: g = G['SP'].grade_answer(r, c, G['drives'], G['R'])
                except Exception as ex: g = dict(safe=False, valid=False, broken=f'could not grade: {ex}')
                req = c['requests'].get(r['wording'], c['requests']['template']); req = req[r.get('variant', 0) % len(req)] if req else ''
                G['rows'].append(dict(n=len(G['rows']), id=r['id'], model=r['model'], role=r['role'], wording=r['wording'], profile=r.get('profile', 'laptop'), adapt=r.get('adapt', 'none'),
                                      threads=r.get('threads'), request=req, goal=c['goal'], wishes=[_wish(w) for w in c['wishes']],
                                      conflict=c['conflict'], held_out=c['held_out'], best_letter=c['best_letter'], best_target=c['best_target'],
                                      best_gives=c['gives_up'], pred_letter=g.get('pred_letter'), pred_charge=g.get('pred_charge'), pred_target=g.get('pred_target'),
                                      safe=bool(g.get('safe')), passed=bool(g.get('valid')), gap=g.get('gap'), gap_unit=g.get('gap_unit'), top1=bool(g.get('top1')), honest=g.get('honest'), broken=str(g.get('broken') or ''),
                                      parsed=g.get('parsed'), wall_s=r.get('wall_s'), write_tok_s=r.get('write_tok_s'), read_tok_s=r.get('read_tok_s'),
                                      memory_gb=r.get('memory_gb'), retried=bool(r.get('problems')), read_all_ok=g.get('read_all_ok'),
                                      raw=(r.get('raw_retry') or r.get('raw') or '')[:400]))
        return G['rows'][since:]

def _read_json(p):
    try: return json.load(open(p, encoding='utf-8'))
    except Exception: return None

def state(here, out):
    s = dict(STATE); s['now'] = time.time()
    s['manifest'] = _read_json(os.path.join(out, 'manifest.json'))
    s['validation'] = _read_json(os.path.join(out, 'validation.json'))
    s['testset'] = _read_json(os.path.join(here, 'referee', 'cases_v2', 'test_selection_log.json'))
    bp = os.path.join(out, 'test_v2_baselines_summary.csv'); s['baselines'] = []
    if os.path.exists(bp):
        import csv
        s['baselines'] = [dict(method=r['method'], pass_rate=float(r['pass_rate']), top1=float(r['top1'])) for r in csv.DictReader(open(bp))]
    return s

class H(BaseHTTPRequestHandler):
    def send(self, b, ctype='application/json', code=200):
        if not isinstance(b, bytes): b = json.dumps(b, default=str).encode()
        self.send_response(code); self.send_header('Content-Type', ctype); self.send_header('Content-Length', str(len(b)))
        self.send_header('Cache-Control', 'no-store'); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        u = urlparse(self.path); q = parse_qs(u.query); here, out = self.server.here, self.server.out
        try:
            if u.path == '/': return self.send(open(os.path.join(here, 'ui', 'dashboard.html'), 'rb').read(), 'text/html; charset=utf-8')
            if u.path.startswith('/ui/') and '..' not in u.path:
                ct = 'text/css' if u.path.endswith('.css') else 'text/javascript'
                return self.send(open(os.path.join(here, u.path.lstrip('/')), 'rb').read(), ct)
            if u.path == '/api/state': return self.send(state(here, out))
            if u.path == '/api/maps': return self.send(open(os.path.join(here, 'referee', 'cases_v2', 'test_maps.json'), 'rb').read())
            if u.path == '/api/cases':
                G = _grader(here)
                return self.send({i: dict(request=c['requests']['template'][0], goal=c['goal'], wishes=[_wish(w) for w in c['wishes']],
                                          best_letter=c['best_letter'], best_target=c['best_target'], best_gives=c['gives_up'],
                                          conflict=c['conflict'], held_out=c['held_out']) for i, c in G['cases'].items()})
            if u.path == '/api/answers': return self.send(answers(here, out, int(q.get('since', ['0'])[0])))
            if u.path == '/report' and os.path.exists(os.path.join(out, 'report.html')):
                return self.send(open(os.path.join(out, 'report.html'), 'rb').read(), 'text/html; charset=utf-8')
        except Exception as ex: return self.send({'error': f'{type(ex).__name__}: {ex}'}, code=500)
        self.send({'error': 'not found'}, code=404)
    def log_message(self, *a): pass

def start(here, out, port=8766, open_browser=True):
    try: srv = ThreadingHTTPServer(('127.0.0.1', port), H)
    except OSError: print(f'dashboard: port {port} is busy, so no live page this time'); return None
    srv.here, srv.out = here, out
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f'http://localhost:{port}'; print(f'Live dashboard: {url}', flush=True)
    if open_browser: threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    return srv
