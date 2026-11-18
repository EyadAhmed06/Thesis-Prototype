"""evbench: the whole study in one command.

    python evbench.py run                 # every stage, in order; stages whose settings and files are unchanged are skipped
    python evbench.py run --from models   # start at a stage (inputs, validation, situations, baselines, models, score, report)
    python evbench.py run --only report   # one stage
    python evbench.py status              # what is done, with fingerprints
    python evbench.py dashboard           # open the live page on finished results (no run)

Stages:
  1 inputs      road network (SUMO format) and the charger table, built from OpenStreetMap and AFDC if missing
  2 validation  SUMO energy against real trips (DEVRT Leaf e+, VED Michigan) from the stored replays
  3 situations  test and training situations with the referee's answers; checked against the frozen fingerprint
  4 baselines   simple methods graded by the referee
  5 models      small language models answer through Ollama (offline), in every role and wording set in the config
  6 score       every model answer graded by the referee
  7 report      outputs/report.html: all tables and charts, plus the fingerprints of every input and output
Settings live in evbench_config.json. Every stage writes outputs/manifest.json: what ran, when, how long, and the
SHA-256 of every file it used or made, so a second run can be compared byte for byte."""
import sys, os, json, time, hashlib, subprocess, argparse, gzip, shutil, platform, urllib.request, html
HERE = os.path.dirname(os.path.abspath(__file__))
REF, PILOT = os.path.join(HERE, 'referee'), os.path.join(HERE, 'pilot')
OUT = os.environ.get('EVBENCH_OUT') or os.path.join(HERE, 'outputs')   # where results go (default: outputs/)
SKIPPABLE = ['inputs', 'validation', 'situations', 'baselines']
STAGES = ['inputs', 'validation', 'situations', 'baselines', 'models', 'score', 'report']
PY = sys.executable

def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''): h.update(b)
    return h.hexdigest()
def say(msg):
    print(f'[{time.strftime("%H:%M:%S")}] {msg}', flush=True)
    if 'live' in sys.modules: sys.modules['live'].log(msg)
def run(cmd, cwd=None, capture=False):
    say('  $ ' + ' '.join(os.path.relpath(c, HERE) if os.path.isabs(c) and c.startswith(HERE) else c for c in cmd))
    r = subprocess.run(cmd, cwd=cwd or HERE, capture_output=capture, text=True)
    if r.returncode != 0:
        raise SystemExit(f'step failed: {" ".join(cmd)}\n{(r.stderr or "")[-2000:] if capture else ""}')
    return r.stdout if capture else ''

class Manifest:
    def unchanged(self, stage, cfg_hash):
        """True if the stage finished before with the same settings and every file it made is still byte-identical."""
        r = self.d['stages'].get(stage)
        if not r or r.get('config') != cfg_hash or not r['files']: return False
        return all(os.path.exists(os.path.join(HERE, f)) and sha(os.path.join(HERE, f)) == h for f, h in r['files'].items())
    def __init__(self):
        os.makedirs(OUT, exist_ok=True); self.path = os.path.join(OUT, 'manifest.json')
        self.d = json.load(open(self.path)) if os.path.exists(self.path) else {'stages': {}}
    def record(self, stage, files, seconds, note='', cfg_hash=''):
        self.d['stages'][stage] = dict(finished=time.strftime('%Y-%m-%d %H:%M:%S'), seconds=round(seconds, 1), note=note, config=cfg_hash,
                                       files={os.path.relpath(f, HERE): sha(f) for f in files if os.path.exists(f)})
        self.d['machine'] = dict(system=platform.platform(), python=platform.python_version())
        json.dump(self.d, open(self.path, 'w'), indent=1)

# ---------------------------------------------------------------- stages
def st_inputs(cfg, m):
    net = os.path.join(HERE, cfg['network']); gz = net + '.gz'; ch = os.path.join(REF, 'chargers.csv')
    if not os.path.exists(net):
        if os.path.exists(gz):
            say('  unpacking the stored road network'); shutil.copyfileobj(gzip.open(gz), open(net, 'wb'))
        else:
            if not (cfg.get('osm_pbf') and cfg.get('afdc_csv')): raise SystemExit('no road network: set osm_pbf and afdc_csv in the config')
            run([PY, os.path.join(HERE, 'build_network.py'), cfg['osm_pbf'], cfg['afdc_csv']])
    if not os.path.exists(ch):
        run([PY, os.path.join(REF, 'stations.py'), cfg['afdc_csv'], net, ch])
    return [net, ch], 'road network and charger table ready'

def st_validation(cfg, m):
    out = os.path.join(OUT, 'validation.json'); v = {}
    import pandas as pd, numpy as np
    d = pd.read_csv(os.path.join(HERE, 'sim-validation', 'devrt', 'devrt_replay.csv'))
    e = (d.sim_slope - d.meas_Wh) / d.meas_Wh
    v['devrt'] = dict(trips=len(d), km=round(float(d.km.sum()), 1), total_ratio=round(float(d.sim_slope.sum() / d.meas_Wh.sum()), 3),
                      median_trip_error=round(float(e.abs().median()), 3))
    txt = run([PY, os.path.join(REF, 'fit_temp.py'), os.path.join(HERE, 'sim-validation', 'replay.csv')], cwd=OUT, capture=True)
    v['ved_heating_fit'] = txt.strip().splitlines()
    json.dump(v, open(out, 'w'), indent=1)
    tc = os.path.join(OUT, 'temp_correction.json')
    return [out, tc], f"DEVRT total {v['devrt']['total_ratio']:.3f} of measured"

def situation_fields(path):
    keys = ['id', 'origin_edge', 'dest_edge', 'depart_min', 'soc0', 'temp_c', 'goal', 'deadline_min', 'budget', 'wishes', 'candidates',
            'letters', 'must_charge', 'best_charger', 'best_target', 'best_level', 'gives_up', 'facts']
    rows = [{k: json.loads(l).get(k) for k in keys} for l in open(path)]
    return hashlib.sha256(json.dumps(rows, sort_keys=True, default=str).encode()).hexdigest()

def st_situations(cfg, m):
    v2 = os.path.join(REF, 'cases_v2'); test = os.path.join(v2, 'test_cases.jsonl')
    frozen = json.load(open(os.path.join(v2, 'FROZEN_test_v2.json')))['sha256_situations_and_answers']
    if os.path.exists(test) and not cfg.get('regenerate_situations'):
        h = situation_fields(test)
        if h != frozen: raise SystemExit(f'test set does not match its frozen fingerprint ({h[:12]} vs {frozen[:12]})')
        return [test, os.path.join(v2, 'train_cases.jsonl')], 'stored test set matches the frozen fingerprint'
    # full regeneration from the road network: SUMO drives every leg again (about 10 minutes)
    net = os.path.join(HERE, cfg['network']); tmp = os.path.join(OUT, 'regenerated'); os.makedirs(tmp, exist_ok=True)
    g = cfg['generation']
    run([PY, os.path.join(REF, 'gen_cases.py'), net, 'test', str(g['test_raw']), str(g['test_seed']), tmp])
    os.rename(os.path.join(tmp, 'test_labelled.json'), os.path.join(tmp, 'a_labelled.json')); os.rename(os.path.join(tmp, 'test_drives.json'), os.path.join(tmp, 'a_drives.json'))
    run([PY, os.path.join(REF, 'gen_cases.py'), net, 'test', str(g['extra_raw']), str(g['extra_seed']), tmp, str(g['extra_id_start'])])
    run([PY, os.path.join(REF, 'gen_cases.py'), net, 'train', str(g['train_raw']), str(g['train_seed']), tmp])
    base = os.path.join(tmp, 'base'); os.makedirs(base, exist_ok=True)
    a, b = json.load(open(os.path.join(tmp, 'a_labelled.json'))), json.load(open(os.path.join(tmp, 'test_labelled.json')))
    json.dump([{k: v for k, v in c.items() if k != 'options'} for c in a + b], open(os.path.join(base, 'test_labelled.json'), 'w'))
    D = json.load(open(os.path.join(tmp, 'a_drives.json'))); D.update(json.load(open(os.path.join(tmp, 'test_drives.json'))))
    json.dump(D, open(os.path.join(base, 'test_drives.json'), 'w'))
    json.dump([{k: v for k, v in c.items() if k != 'options'} for c in json.load(open(os.path.join(tmp, 'train_labelled.json')))], open(os.path.join(base, 'train_labelled.json'), 'w'))
    shutil.copy(os.path.join(tmp, 'train_drives.json'), os.path.join(base, 'train_drives.json'))
    run([PY, os.path.join(REF, 'make_v2.py'), base, 'test', str(g['test_keep']), str(g['wish_seed_test']), tmp])
    run([PY, os.path.join(REF, 'make_v2.py'), base, 'train', '0', str(g['wish_seed_train']), tmp])
    h = situation_fields(os.path.join(tmp, 'test_cases.jsonl'))
    note = 'regenerated test set ' + ('MATCHES' if h == frozen else 'DIFFERS FROM') + ' the frozen fingerprint'
    say('  ' + note)
    return [os.path.join(tmp, 'test_cases.jsonl'), os.path.join(tmp, 'train_cases.jsonl')], note

def st_baselines(cfg, m):
    v2 = os.path.join(REF, 'cases_v2')
    run([PY, os.path.join(REF, 'run_baselines_v2.py'), v2, 'test', OUT, os.path.join(v2, 'base', 'test_drives.json')])
    return [os.path.join(OUT, 'test_v2_baselines_summary.csv'), os.path.join(OUT, 'test_v2_baselines_rows.csv')], 'baselines graded'

def ollama_ok(url):
    try: urllib.request.urlopen(url + '/api/tags', timeout=5).read(); return True
    except Exception: return False

def ids_file(cfg):
    if cfg['models_on'] == 'pilot': return os.path.join(PILOT, 'pilot_v2_ids.json')
    p = os.path.join(OUT, 'all_ids.json')
    json.dump([json.loads(l)['id'] for l in open(os.path.join(REF, 'cases_v2', 'test_cases.jsonl'))], open(p, 'w')); return p

def st_models(cfg, m):
    url = cfg['ollama_url']; res = os.path.join(OUT, 'model_answers.jsonl')
    if not ollama_ok(url):
        raise SystemExit(f'Ollama is not running at {url}. Start Ollama, then run: python evbench.py run --from models')
    have = json.loads(urllib.request.urlopen(url + '/api/tags').read())['models']; names = {x['name'] for x in have}
    missing = [x for x in cfg['models'] if x not in names and x + ':latest' not in names]
    if missing: raise SystemExit('models not downloaded yet: ' + ', '.join(f'ollama pull {x}' for x in missing))
    ids = ids_file(cfg); profiles = cfg.get('edge_profiles') or [dict(name='laptop', threads=0)]
    plan = [(profiles[0], w, r) for w in cfg['wordings'] for r in cfg['roles']]
    eo = cfg.get('edge_on', {}); plan += [(p, w, r) for p in profiles[1:] for w in eo.get('wordings', cfg['wordings']) for r in eo.get('roles', cfg['roles'])]
    for prof, wording, role in plan:
        say(f'  {role}, {wording} requests, profile {prof["name"]}' + (f' ({prof["threads"]} CPU threads)' if prof.get('threads') else ''))
        run([PY, os.path.join(PILOT, 'run_pilot_v2.py'), '--models', *cfg['models'], '--role', role, '--wording', wording,
             '--facts', cfg['facts'], '--cases', os.path.join(REF, 'cases_v2', 'test_cases.jsonl'), '--ids', ids, '--url', url, '--out', res,
             '--profile', prof['name'], '--threads', str(prof.get('threads') or 0)])
    return [res], f"{sum(1 for _ in open(res))} answers stored"

def st_score(cfg, m):
    res = os.path.join(OUT, 'model_answers.jsonl')
    if not os.path.exists(res): raise SystemExit('no model answers yet: run the models stage first')
    out = os.path.join(OUT, 'model_scores.csv')
    run([PY, os.path.join(PILOT, 'score_pilot_v2.py'), os.path.join(REF, 'cases_v2', 'test_cases.jsonl'),
         os.path.join(REF, 'cases_v2', 'base', 'test_drives.json'), res, out])
    return [out, out.replace('.csv', '_summary.csv')], 'model answers graded'

def st_report(cfg, m):
    import report
    p = report.build(HERE, OUT, m.d); return [p], os.path.relpath(p, HERE)

FUN = dict(inputs=st_inputs, validation=st_validation, situations=st_situations, baselines=st_baselines, models=st_models, score=st_score, report=st_report)

def planned_answers(cfg):
    n = len(json.load(open(ids_file(cfg)))); profiles = cfg.get('edge_profiles') or [{}]; eo = cfg.get('edge_on', {})
    per = len(cfg['wordings']) * len(cfg['roles']) + (len(profiles) - 1) * len(eo.get('wordings', cfg['wordings'])) * len(eo.get('roles', cfg['roles']))
    return n * len(cfg['models']) * per

def wait_dashboard(srv):
    if srv is None or not sys.stdin.isatty(): return
    say('the live dashboard stays open: press Ctrl+C here to close it')
    try:
        while True: time.sleep(1)
    except KeyboardInterrupt: pass

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('command', choices=['run', 'status', 'dashboard']); ap.add_argument('--from', dest='start', choices=STAGES)
    ap.add_argument('--only', choices=STAGES); ap.add_argument('--config', default=os.path.join(HERE, 'evbench_config.json'))
    ap.add_argument('--force', action='store_true', help='redo stages even if their outputs are unchanged')
    ap.add_argument('--no-dashboard', action='store_true', help='do not open the live page')
    a = ap.parse_args(); cfg = json.load(open(a.config)); m = Manifest()
    ch = hashlib.sha256(json.dumps(cfg, sort_keys=True).encode()).hexdigest()
    sys.path.insert(0, REF); sys.path.insert(0, HERE)
    if a.command == 'status':
        for s in STAGES:
            r = m.d['stages'].get(s)
            print(f"{s:11s} " + (f"done {r['finished']} ({r['seconds']} s)  {r['note']}" if r else 'not run'))
            for f, h in (r or {}).get('files', {}).items(): print(f'            {h[:16]}  {f}')
        return
    srv = None
    if a.command == 'dashboard' or (cfg.get('live_dashboard', True) and not a.no_dashboard):
        import live
        live.STATE.update(config=dict(models=cfg['models'], roles=cfg['roles'], wordings=cfg['wordings'], models_on=cfg['models_on'],
                                      edge_profiles=cfg.get('edge_profiles', []), edge_on=cfg.get('edge_on', {})),
                          planned_answers=planned_answers(cfg))
        srv = live.start(HERE, OUT)
    if a.command == 'dashboard':
        live.STATE.update(running=False); wait_dashboard(srv) if srv and sys.stdin.isatty() else None; return
    todo = [a.only] if a.only else STAGES[STAGES.index(a.start) if a.start else 0:]
    if 'models' in todo and not a.only and not ollama_ok(cfg['ollama_url']) and not a.start:
        say('note: Ollama is not running, so the run will stop at the models stage (stages before it still run)')
    L = sys.modules.get('live')
    if L: L.STATE.update(running=True, started=time.time(), stages={s: 'waiting' for s in todo})
    try:
        for s in todo:
            say(f'stage {STAGES.index(s) + 1}/7: {s}'); t = time.time()
            if L: L.STATE['current'] = s; L.STATE['stages'][s] = 'running'
            # stages 1-4 are skipped when nothing changed; models resumes by itself; score and report are quick and always redone
            if s in SKIPPABLE and not a.force and not a.only and m.unchanged(s, ch):
                say('  unchanged since last run (same settings, same files): skipped')
                if L: L.STATE['stages'][s] = 'done'
                continue
            files, note = FUN[s](cfg, m); m.record(s, files, time.time() - t, note, ch); say(f'  done: {note}')
            if L: L.STATE['stages'][s] = 'done'
        say(f'finished. Open {os.path.relpath(os.path.join(OUT, "report.html"), HERE)}')
    except (SystemExit, Exception) as ex:
        if not isinstance(ex, SystemExit): import traceback; traceback.print_exc()
        if L: L.STATE['stages'][L.STATE['current']] = 'error'; L.STATE['error'] = f'{type(ex).__name__}: {ex}' if not isinstance(ex, SystemExit) else str(ex)
        print(ex); 
        if L: L.STATE['running'] = False
        wait_dashboard(srv); sys.exit(1)
    if L: L.STATE.update(running=False, current=None)
    wait_dashboard(srv)

if __name__ == '__main__':
    main()
