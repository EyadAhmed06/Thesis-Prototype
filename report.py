"""Builds outputs/report.html from the files the evbench stages wrote. Only reads numbers from those files:
anything that has not been run yet is shown as "not run yet", never estimated."""
import os, json, html, time
import pandas as pd

STAGE_TEXT = [
    ('inputs', 'Inputs', 'Michigan road network (OpenStreetMap, converted by SUMO netconvert) and the public charger table (AFDC).'),
    ('validation', 'Validation', 'SUMO energy use compared with real measured trips (DEVRT Leaf e+, VED Michigan).'),
    ('situations', 'Situations', 'Trips driven in SUMO; the referee works out every valid charging plan and the best one. Test set frozen by fingerprint.'),
    ('baselines', 'Baselines', 'Simple methods (random, nearest, rule, exact planner) graded by the referee.'),
    ('models', 'Models', 'Small language models answer offline through Ollama, in each role and wording.'),
    ('score', 'Score', 'Every model answer graded by the same referee.'),
    ('report', 'Report', 'This page.'),
]
ROLE_TEXT = {'R1': 'model decides alone', 'R2': 'model decides, safety check on the device, one retry',
             'R3-known': 'model fills a form (training wish types), exact planner decides',
             'R3-full': 'model fills a form (every wish type), exact planner decides'}

def e(x): return html.escape(str(x))
def pct(x): return '' if x is None or pd.isna(x) else f'{100 * float(x):.1f}%'
def bar(v, lo=None, hi=None):
    if v is None or pd.isna(v): return '<span class="muted">n/a</span>'
    ci = '' if lo is None or pd.isna(lo) else f'<span class="ci" style="left:{100*lo:.1f}%;width:{100*(hi-lo):.1f}%"></span>'
    txt = pct(v) + ('' if lo is None or pd.isna(lo) else f' <span class="muted">[{100*lo:.0f}, {100*hi:.0f}]</span>')
    return f'<div class="bar"><span class="fill" style="width:{100*v:.1f}%"></span>{ci}</div><span class="num">{txt}</span>'

def table(head, rows, cls=''):
    h = ''.join(f'<th>{e(x)}</th>' for x in head)
    b = ''.join('<tr>' + ''.join(f'<td>{x}</td>' for x in r) + '</tr>' for r in rows)
    return f'<div class="tw"><table class="{cls}"><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table></div>'

def build(here, out, manifest):
    st = manifest.get('stages', {}); parts = []
    # ---- pipeline flow
    flow = []
    for k, name, txt in STAGE_TEXT:
        r = st.get(k); done = r is not None or k == 'report'
        when = (f'done {e(r["finished"])}' if r else ('now' if k == 'report' else 'not run yet'))
        flow.append(f'<div class="step {"done" if done else "todo"}"><div class="sn">{STAGE_TEXT.index((k, name, txt)) + 1}</div>'
                    f'<div><b>{e(name)}</b><p>{e(txt)}</p><p class="muted">{when}{" · " + e(r["note"]) if r and r.get("note") else ""}</p></div></div>')
    parts.append('<h2>How the study runs</h2><p>One command, <code>python evbench.py run</code>, runs these steps in order. '
                 'Settings are in <code>evbench_config.json</code>.</p><div class="flow">' + ''.join(flow) + '</div>')

    # ---- validation
    vp = os.path.join(out, 'validation.json')
    if os.path.exists(vp):
        v = json.load(open(vp)); d = v['devrt']
        parts.append('<h2>2. Is the simulator\'s energy use realistic?</h2>' + table(
            ['Check', 'Result'],
            [['DEVRT: real Nissan Leaf e+ trips replayed in SUMO', f'{d["trips"]} trips, {d["km"]} km'],
             ['Total simulated energy / total measured', f'{d["total_ratio"]:.3f}'],
             ['Median error on one trip', pct(d['median_trip_error'])]]) +
            '<p>VED (Michigan) heating and cooling fit, as printed by <code>fit_temp.py</code>:</p><pre>' +
            e('\n'.join(v.get('ved_heating_fit', []))) + '</pre>')
    else: parts.append('<h2>2. Validation</h2><p class="muted">Not run yet.</p>')

    # ---- test set
    lp = os.path.join(here, 'referee', 'cases_v2', 'test_selection_log.json')
    fz = os.path.join(here, 'referee', 'cases_v2', 'FROZEN_test_v2.json')
    if os.path.exists(lp):
        L = json.load(open(lp)); fr = json.load(open(fz)) if os.path.exists(fz) else {}
        w = L.get('wishes 0/1/2', [0, 0, 0])
        rows = [['Situations driven in SUMO (solvable)', L['base situations']], ['Still the same best answer under energy and heating changes', L['robust with wishes']],
                ['Kept for the test', L['kept']], ['Driver must give something up (conflict)', L['conflict']],
                ['Must charge on the way', L['must charge']], ['Wishes per driver: 0 / 1 / 2', ' / '.join(map(str, w))],
                ['With a wish type never seen in training', L['with held-out wish type']], ['With a trap charger (broken, private or wrong plug)', L['with trap charger']],
                ['Budget below every on-time option', L.get('budget set below every on-time option', '')]]
        wt = ', '.join(f'{e(k)} {v}' for k, v in L['wish types'].items())
        gu = ', '.join(f'{e(k)} {v}' for k, v in L['gives up'].items())
        parts.append('<h2>3. The test</h2>' + table(['', 'Count'], [[e(a), e(b)] for a, b in rows]) +
                     f'<p>Wish types: {wt}.</p><p>What the best answer gives up: {gu}.</p>' +
                     (f'<p class="muted">Frozen fingerprint {e(fr.get("sha256_situations_and_answers", "")[:16])}…, '
                      f'checked by the situations stage: {e(st.get("situations", {}).get("note", "not checked yet"))}.</p>' if fr else ''))

    # ---- baselines
    bp = os.path.join(out, 'test_v2_baselines_summary.csv')
    if os.path.exists(bp):
        b = pd.read_csv(bp)
        rows = [[e(r.method), bar(r.pass_rate, r.pass_lo, r.pass_hi), pct(r.top1), pct(r.safe_rate), pct(getattr(r, 'honest_rate', None))] for r in b.itertuples()]
        parts.append('<h2>4. Baselines (no language model)</h2><p>Pass means the plan is safe and keeps as much as the best possible plan, '
                     'in the priority order arrival time, then budget, then wishes. Brackets are 95% Wilson intervals.</p>' +
                     table(['Method', 'Pass rate', 'Same charger as referee', 'Safe', 'Says honestly what it gives up'], rows, 'wide'))
    else: parts.append('<h2>4. Baselines</h2><p class="muted">Not run yet.</p>')

    sv = os.path.join(out, 'test_v2_sensitivity.csv')
    if os.path.exists(sv):
        t = pd.read_csv(sv)
        parts.append('<h2>How much the answer key depends on the assumptions</h2><p class="muted">Each line changes one assumption the robustness check does not vary, '
                     'recomputes every option from the stored drives, and counts the situations whose best answer (charge or not, charger and its kind) stays the same.</p>' +
                     table(['Change', 'Answer unchanged', 'Also same target'], [[e(r.variant), f'{int(r.same_answer)} of {int(r.situations)} ({pct(r.same_answer_share)})',
                            '' if r.same_including_target != r.same_including_target else e(int(r.same_including_target))] for r in t.itertuples()]))
    # ---- models
    sp = os.path.join(out, 'model_scores_summary.csv'); ap = os.path.join(out, 'model_answers.jsonl')
    if os.path.exists(sp):
        s = pd.read_csv(sp)
        if 'profile' not in s: s['profile'] = 'laptop'
        if 'adapt' not in s: s['adapt'] = 'none'
        s['adapt'] = s.adapt.fillna('none')
        main_p = s.profile.iloc[0] if 'laptop' not in set(s.profile) else 'laptop'
        rows = []
        # pass rate on the situations whose answer survives every sensitivity change (referee/sensitivity.py)
        stable = {}; idp = os.path.join(out, 'test_v2_stable_ids.json'); msp = os.path.join(out, 'model_scores.csv')
        if os.path.exists(idp) and os.path.exists(msp):
            ids = set(json.load(open(idp))); m = pd.read_csv(msp)
            for col, dflt in (('adapt', 'none'), ('profile', 'laptop')):
                if col not in m: m[col] = dflt
            m = m[m.id.isin(ids)]
            stable = {k: g.valid.astype(bool).mean() for k, g in m.groupby(['profile', 'adapt', 'model', 'role', 'wording'])}
        for r in s[(s.profile == main_p) & (s.adapt == 'none')].sort_values(['wording', 'model', 'role']).itertuples():
            rows.append([e(r.model), f'<b>{e(r.role)}</b>', e(r.wording), e(int(r.n)),
                         bar(r.pass_rate, r.pass_lo, r.pass_hi), pct(stable.get((r.profile, 'none', r.model, r.role, r.wording))), pct(r.pass_seen), pct(r.pass_held_out), pct(r.pass_conflict),
                         pct(r.safe_rate), pct(getattr(r, 'honest_rate', None)), pct(r.parsed), f'{r.wall_s_median:.1f} s'])
        machines = set()
        if os.path.exists(ap):
            for l in open(ap, encoding='utf-8'):
                m = json.loads(l).get('machine', {}); machines.add(f'{m.get("system", "")}, {m.get("cpu", "")}')
        parts.append(f'<h2>5–6. Small language models, graded by the referee</h2><p class="muted">Profile: {e(main_p)}. Roles: ' + '; '.join(f'<b>{k}</b> {e(v)}' for k, v in ROLE_TEXT.items()) + '.</p>' +
                     table(['Model', 'Role', 'Wording', 'Answers', 'Pass rate', 'Pass, answer-stable situations', 'Pass, seen wish types', 'Pass, unseen wish types',
                            'Pass, conflicts', 'Safe', 'Honest', 'Valid JSON', 'Median time'], rows, 'wide') +
                     '<p class="muted">Answers produced on: ' + e('; '.join(sorted(machines)) or 'unknown') + '.</p>')
        # edge: every profile, per model and role
        prof = {p['name']: p for p in json.load(open(os.path.join(here, 'evbench_config.json'))).get('edge_profiles', [])} if os.path.exists(os.path.join(here, 'evbench_config.json')) else {}
        er = []
        for r in s[s.adapt == 'none'].sort_values(['profile', 'model', 'role', 'wording']).itertuples():
            p = prof.get(r.profile, {}); tb, mb = p.get('time_budget_s'), p.get('memory_budget_gb')
            mem = getattr(r, 'memory_gb_max', None); fits = '' if not (tb and mb) else ('fits' if r.wall_s_median <= tb and (mem or 0) <= mb else 'does not fit')
            er.append([e(r.profile) + (f' ({int(r.threads)} threads)' if 'thread' not in str(r.profile) and getattr(r, 'threads', None) == getattr(r, 'threads', None) and getattr(r, 'threads', None) else ''),
                       e(r.model), e(r.role), e(r.wording), f'{r.wall_s_median:.1f} s', f'{r.wall_s_p95:.1f} s' if hasattr(r, 'wall_s_p95') else '',
                       '' if mem != mem or mem is None else f'{mem:.2f} GB', f'{r.read_tok_s_median:.0f} / {r.write_tok_s_median:.0f}' if getattr(r, 'read_tok_s_median', None) == getattr(r, 'read_tok_s_median', None) and getattr(r, 'read_tok_s_median', None) else '',
                       pct(r.pass_rate), (f'{e(fits)}<br><span class="muted">{tb} s, {mb} GB, {e(p.get("status", ""))}</span>' if fits else '')])
        parts.append('<h2>Edge: time, speed and memory on this computer</h2><p>Time to decide includes the retry in R2. Memory is what Ollama reports for the loaded model. '
                     'A phone and battery use are not measured.</p>' + table(['Profile', 'Model', 'Role', 'Wording', 'Median time', '95th percentile', 'Model memory', 'Tokens/s read / write', 'Pass rate', 'Budget'], er, 'wide'))
        # adaptation (RQ3): each condition next to the same model and role without adaptation
        ad = s[(s.profile == main_p) & (s.wording == 'template')]
        keys = set(map(tuple, ad[ad.adapt != 'none'][['model', 'role']].values))
        ar = [[e(r.model), f'<b>{e(r.role)}</b>', e(r.adapt), e(int(r.n)), bar(r.pass_rate, r.pass_lo, r.pass_hi), pct(r.pass_seen), pct(r.pass_held_out),
               f'{r.wall_s_median:.1f} s'] for r in ad.sort_values(['model', 'role', 'adapt']).itertuples() if (r.model, r.role) in keys]
        if ar:
            parts.append('<h2>Adaptation (RQ3)</h2><p class="muted">none: plain instruction; rules: step-by-step instruction; examples: two worked examples '
                         'retrieved from the Detroit training situations; lora: fine-tuned on the training situations. Template wording.</p>' +
                         table(['Model', 'Role', 'Adaptation', 'Answers', 'Pass rate', 'Pass, seen wish types', 'Pass, unseen wish types', 'Median time'], ar, 'wide'))
        stp = os.path.join(out, 'model_stats.csv')
        if os.path.exists(stp):
            t = pd.read_csv(stp)
            if len(t):
                tr = [[e(r.family), e(r.a), e(r.b), e(int(r.n)), pct(r.pass_a), pct(r.pass_b), f'{100 * r.diff:+.1f} [{100 * r.diff_lo:+.1f}, {100 * r.diff_hi:+.1f}]',
                       f'{r.only_a} / {r.only_b}', f'{r.p:.3g}', 'yes' if r.holm_significant else 'no'] for r in t.itertuples()]
                parts.append('<h2>Paired comparisons</h2><p class="muted">Same situations for both sides. Difference in pass rate (percentage points, A minus B) with a 95% interval; '
                             "McNemar's test on the situations where only one side passes; Holm's correction within each research question. Template wording, main profile.</p>" +
                             table(['RQ', 'A', 'B', 'Situations', 'Pass A', 'Pass B', 'Difference', 'Only A / only B', 'p', 'Significant after Holm'], tr, 'wide'))
    else:
        parts.append('<h2>5–6. Small language models</h2><p class="muted">Not run yet. Start Ollama, then run '
                     '<code>python evbench.py run --from models</code>.</p>')

    # ---- fingerprints
    rows = []
    for k, _, _ in STAGE_TEXT:
        for f, h in st.get(k, {}).get('files', {}).items(): rows.append([e(k), f'<code>{e(f)}</code>', f'<code>{e(h[:16])}…</code>'])
    mc = manifest.get('machine', {})
    parts.append('<h2>Fingerprints</h2><p>SHA-256 of every file each stage used or made. Running again on another computer should give the same '
                 'fingerprints for stages 1 to 4; model answers depend on the model build.</p>' + table(['Stage', 'File', 'SHA-256'], rows) +
                 f'<p class="muted">Pipeline machine: {e(mc.get("system", ""))}, Python {e(mc.get("python", ""))}.</p>')

    tp = os.path.join(here, 'ui', 'theme.css'); theme = open(tp).read().replace('{', '{{').replace('}', '}}') if os.path.exists(tp) else ''
    theme = theme.replace('{{', '{').replace('}}', '}')
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>EV charging benchmark report</title><style>
{theme}
:root{{--fg:var(--ink);--card:var(--surface);--acc:var(--accent);--ci:var(--muted);--todo:var(--road2)}}
body{{background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif;margin:0;padding:24px 16px}}
main{{max-width:1100px;margin:auto}} h1{{font-size:26px;margin:0 0 4px}} h2{{font-size:19px;margin:32px 0 8px;border-top:1px solid var(--line);padding-top:20px}}
.muted{{color:var(--muted)}} code,pre{{font:13px ui-monospace,Consolas,monospace}} pre{{background:var(--card);border:1px solid var(--line);padding:10px;overflow-x:auto;white-space:pre-wrap}}
.tw{{overflow-x:auto}} table{{border-collapse:collapse;width:100%;background:var(--card)}} th,td{{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}}
th{{font-weight:600;font-size:13px}} .wide td{{white-space:nowrap}} .wide td:nth-child(2){{white-space:normal;min-width:150px}}
.bar{{display:inline-block;position:relative;width:120px;height:10px;background:var(--line);vertical-align:middle;margin-right:6px}}
.fill{{position:absolute;left:0;top:0;bottom:0;background:var(--acc)}} .ci{{position:absolute;top:4px;height:2px;background:var(--ci)}}
.flow{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px}}
.step{{display:flex;gap:10px;background:var(--card);border:1px solid var(--line);border-left:4px solid var(--acc);padding:10px}} .step.todo{{border-left-color:var(--todo)}}
.step p{{margin:4px 0 0;font-size:13px}} .sn{{font-weight:700;color:var(--acc);font-size:18px}} .todo .sn{{color:var(--todo)}}
</style></head><body><main><h1>EV charging benchmark report</h1>
<p class="muted">Built {e(time.strftime('%Y-%m-%d %H:%M'))} by <code>evbench.py</code>. Every number on this page is read from the files listed under Fingerprints.</p>
{''.join(parts)}</main></body></html>"""
    p = os.path.join(out, 'report.html'); open(p, 'w', encoding='utf-8').write(page); return p
