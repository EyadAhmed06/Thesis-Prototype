"""Builds the thesis diagrams as one editable draw.io file (one page per diagram) plus an SVG of each page.
Open thesis_diagrams.drawio in draw.io / diagrams.net to edit. Run: python make_diagrams.py"""
import html, os, textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
FILL = dict(data='#DCEAF7', ref='#DFF0D8', case='#FCEFD4', model='#EADCF5', base='#EEEEEE', score='#FBE0DC', note='#FFFFFF')
STROKE = dict(data='#3B6E9E', ref='#3C7A3C', case='#A8741A', model='#6E4A9E', base='#666666', score='#A8483A', note='#999999')
FONT = 'Helvetica'


class Page:
    def __init__(self, name, w, h, title):
        self.name, self.w, self.h, self.title = name, w, h, title
        self.nodes, self.edges = {}, []

    def box(self, id, x, y, w, h, text, kind='data', status='done', bold_first=True, size=13):
        self.nodes[id] = dict(x=x, y=y, w=w, h=h, text=text, kind=kind, status=status, bold=bold_first, size=size)

    def arrow(self, a, b, sa='r', sb='l', label='', dashed=False):
        self.edges.append(dict(a=a, b=b, sa=sa, sb=sb, label=label, dashed=dashed))

    # ---------- geometry ----------
    def anchor(self, id, side):
        n = self.nodes[id]
        return {'r': (n['x'] + n['w'], n['y'] + n['h'] / 2), 'l': (n['x'], n['y'] + n['h'] / 2),
                't': (n['x'] + n['w'] / 2, n['y']), 'b': (n['x'] + n['w'] / 2, n['y'] + n['h'])}[side]

    def path(self, e):
        (x1, y1), (x2, y2) = self.anchor(e['a'], e['sa']), self.anchor(e['b'], e['sb'])
        if e['sa'] == e['sb'] == 'b': yd = max(y1, y2) + 35; return [(x1, y1), (x1, yd), (x2, yd), (x2, y2)]
        if e['sa'] == e['sb'] == 't': yd = min(y1, y2) - 30; return [(x1, y1), (x1, yd), (x2, yd), (x2, y2)]
        if e['sa'] == e['sb'] == 'r': xd = max(x1, x2) + 15; return [(x1, y1), (xd, y1), (xd, y2), (x2, y2)]
        if abs(x1 - x2) < 1 or abs(y1 - y2) < 1: return [(x1, y1), (x2, y2)]
        if e['sa'] in 'rl' and e['sb'] in 'rl':
            xm = (x1 + x2) / 2; return [(x1, y1), (xm, y1), (xm, y2), (x2, y2)]
        if e['sa'] in 'tb' and e['sb'] in 'tb':
            ym = (y1 + y2) / 2; return [(x1, y1), (x1, ym), (x2, ym), (x2, y2)]
        if e['sa'] in 'rl': return [(x1, y1), (x2, y1), (x2, y2)]
        return [(x1, y1), (x1, y2), (x2, y2)]

    # ---------- draw.io ----------
    def drawio(self):
        out = [f'<diagram name="{html.escape(self.name)}" id="{self.name.replace(" ", "_")}"><mxGraphModel dx="1200" dy="800" grid="0" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="{self.w}" pageHeight="{self.h}" math="0" shadow="0"><root><mxCell id="0"/><mxCell id="1" parent="0"/>']
        out.append(f'<mxCell id="title" value="{html.escape("<b>" + self.title + "</b>")}" style="text;html=1;align=left;verticalAlign=middle;fontSize=18;fontFamily={FONT};" vertex="1" parent="1"><mxGeometry x="20" y="10" width="{self.w - 40}" height="34" as="geometry"/></mxCell>')
        for id, n in self.nodes.items():
            lines = n['text'].split('\n')
            lab = ('<b>' + html.escape(lines[0]) + '</b>' if n['bold'] else html.escape(lines[0])) + ''.join('<br>' + html.escape(l) for l in lines[1:])
            dash = 'dashed=1;dashPattern=6 4;' if n['status'] != 'done' else ''
            style = (f"rounded=1;whiteSpace=wrap;html=1;arcSize=8;fillColor={FILL[n['kind']]};strokeColor={STROKE[n['kind']]};"
                     f"strokeWidth=1.5;fontFamily={FONT};fontSize={n['size']};verticalAlign=middle;spacing=6;{dash}")
            out.append(f'<mxCell id="{id}" value="{html.escape(lab)}" style="{style}" vertex="1" parent="1"><mxGeometry x="{n["x"]}" y="{n["y"]}" width="{n["w"]}" height="{n["h"]}" as="geometry"/></mxCell>')
        side = {'r': (1, 0.5), 'l': (0, 0.5), 't': (0.5, 0), 'b': (0.5, 1)}
        for i, e in enumerate(self.edges):
            (ex, ey), (nx, ny) = side[e['sa']], side[e['sb']]
            dash = 'dashed=1;' if e['dashed'] else ''
            style = (f"edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;endArrow=block;endFill=1;strokeColor=#444444;strokeWidth=1.5;"
                     f"exitX={ex};exitY={ey};entryX={nx};entryY={ny};fontFamily={FONT};fontSize=11;labelBackgroundColor=#FFFFFF;{dash}")
            out.append(f'<mxCell id="e{i}" value="{html.escape(e["label"])}" style="{style}" edge="1" parent="1" source="{e["a"]}" target="{e["b"]}"><mxGeometry relative="1" as="geometry"/></mxCell>')
        out.append('</root></mxGraphModel></diagram>')
        return ''.join(out)

    # ---------- SVG ----------
    def svg(self):
        o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" viewBox="0 0 {self.w} {self.h}" font-family="{FONT}, Arial, sans-serif">',
             '<defs><marker id="ah" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto"><path d="M0,0 L10,4 L0,8 z" fill="#444"/></marker></defs>',
             f'<rect width="{self.w}" height="{self.h}" fill="#FFFFFF"/>',
             f'<text x="20" y="34" font-size="18" font-weight="bold" fill="#222">{html.escape(self.title)}</text>']
        for n in self.nodes.values():
            dash = ' stroke-dasharray="6 4"' if n['status'] != 'done' else ''
            o.append(f'<rect x="{n["x"]}" y="{n["y"]}" width="{n["w"]}" height="{n["h"]}" rx="7" fill="{FILL[n["kind"]]}" stroke="{STROKE[n["kind"]]}" stroke-width="1.5"{dash}/>')
            sz = n['size']; cw = sz * 0.53; maxc = max(8, int((n['w'] - 14) / cw)); lines = []
            for i, l in enumerate(n['text'].split('\n')):
                for j, piece in enumerate(textwrap.wrap(l, maxc) or ['']): lines.append((piece, i == 0 and n['bold']))
            lh = sz * 1.25; y0 = n['y'] + n['h'] / 2 - lh * (len(lines) - 1) / 2 + sz * 0.35
            for k, (t, b) in enumerate(lines):
                o.append(f'<text x="{n["x"] + n["w"] / 2}" y="{y0 + k * lh:.1f}" font-size="{sz}" text-anchor="middle" fill="#1A1A1A"{" font-weight=\"bold\"" if b else ""}>{html.escape(t)}</text>')
        for e in self.edges:
            p = self.path(e); d = 'M' + ' L'.join(f'{x:.1f},{y:.1f}' for x, y in p)
            dash = ' stroke-dasharray="5 4"' if e['dashed'] else ''
            o.append(f'<path d="{d}" fill="none" stroke="#444" stroke-width="1.5" marker-end="url(#ah)"{dash}/>')
            if e['label']:
                # label at the middle of the longest segment
                segs = list(zip(p, p[1:])); (ax, ay), (bx, by) = max(segs, key=lambda s: abs(s[0][0] - s[1][0]) + abs(s[0][1] - s[1][1]))
                mx, my = (ax + bx) / 2, (ay + by) / 2; tw = len(e['label']) * 5.9 + 8
                o.append(f'<rect x="{mx - tw / 2:.1f}" y="{my - 9:.1f}" width="{tw:.1f}" height="17" fill="#FFFFFF"/>')
                o.append(f'<text x="{mx:.1f}" y="{my + 4:.1f}" font-size="11" text-anchor="middle" fill="#333">{html.escape(e["label"])}</text>')
        o.append('</svg>')
        return '\n'.join(o)


def legend(p, x, y):
    p.box('lg1', x, y, 150, 30, 'Done and tested', 'note', 'done', False, 11)
    p.box('lg2', x + 160, y, 190, 30, 'Ready, not yet run / planned', 'note', 'todo', False, 11)


pages = []

# 1. The study at a glance
p = Page('1 Study overview', 1180, 640, 'The study at a glance')
p.box('osm', 20, 70, 230, 70, 'Road network\nMichigan, OpenStreetMap\n56,923 road segments', 'data')
p.box('afdc', 20, 160, 230, 70, 'Charging stations\nAFDC export, Nov 2026\n994 charger entries', 'data')
p.box('trips', 20, 300, 230, 90, 'Real trips (validation)\nDEVRT: Leaf e+, 2023\nVED: Michigan, incl. winter', 'data')
p.box('ref', 310, 110, 250, 120, 'Referee\nSUMO drives every option,\nadds heating/cooling,\ncharging time and price,\nchecks every rule', 'ref')
p.box('val', 310, 300, 250, 90, 'Validation\nDEVRT: +5.7% total energy\nVED held-out: 0.99 ratio\n(median trip error 15%)', 'ref')
p.box('cases', 620, 70, 250, 100, 'Test situations\n1,400 generated, 300 kept\nafter testability checks\n(Ann Arbor; Detroit = training)', 'case')
p.box('sheet', 620, 200, 250, 70, 'What the model reads\nfact sheet + the driver\'s sentence', 'case')
p.box('llm', 930, 180, 230, 110, 'Small language models\nQwen2.5 0.5B / 1.5B / 3B\n4-bit, on the laptop CPU\nroles R1, R2, R3', 'model', 'todo')
p.box('base', 620, 300, 250, 80, 'Baselines\ngoal-aware rule, nearest\nto 80%, random safe', 'base')
p.box('score', 930, 330, 230, 140, 'Scoring vs. the referee\ncharge? (F1)\nright charger (top-1)\ntarget error, rules kept\noptimality gap\ntime and memory', 'score')
p.box('lora', 930, 60, 230, 90, 'Adaptation\nprompting and LoRA on the\nDetroit training situations', 'model', 'todo')
p.box('phone', 620, 490, 250, 70, 'Deployment check\nlatency and memory on a phone', 'model', 'todo')
p.arrow('osm', 'ref', 'r', 'l'); p.arrow('afdc', 'ref', 'r', 'l'); p.arrow('trips', 'val', 'r', 'l')
p.arrow('val', 'ref', 't', 'b', 'calibrates')
p.arrow('ref', 'cases', 'r', 'l', 'labels'); p.arrow('cases', 'sheet', 'b', 't')
p.arrow('sheet', 'llm', 'r', 'l'); p.arrow('sheet', 'base', 'b', 't')
p.arrow('llm', 'score', 'b', 't'); p.arrow('base', 'score', 'r', 'l')
p.arrow('lora', 'llm', 'b', 't', dashed=True); p.arrow('phone', 'score', 'r', 'b', dashed=True)
legend(p, 20, 590)
pages.append(p)

# 2. How the referee judges one situation
p = Page('2 Referee', 1180, 560, 'How the referee finds the best answer for one situation')
p.box('sit', 20, 70, 260, 150, 'One situation\nstart, destination, time\nbattery %, outside temperature\ndriver\'s goal (fastest/cheapest)\noptional deadline, budget\n3 to 9 chargers near the route', 'case')
p.box('enum', 330, 70, 250, 100, '1. List every option\ndo not charge, or\ncharger × target 20-100%\n(steps of 5%)', 'ref')
p.box('sumo', 630, 70, 250, 100, '2. Drive each leg in SUMO\nstart → charger → destination\nLeaf e+ physics, real roads', 'ref')
p.box('heat', 930, 70, 230, 100, '3. Add heating/cooling\n226 W per °C below 12 °C\n303 W per °C above 30 °C', 'ref')
p.box('chg', 930, 210, 230, 120, '4. Charging time and cost\nLevel 2: 6.6 kW\nDC: 50 kW, slower in the cold\nand above 80%\nlisted or assumed price', 'ref')
p.box('rules', 630, 210, 250, 120, '5. Check every rule\nplug fits, working, public\nbattery never below 10%\narrive by the deadline\nstay within the budget', 'ref')
p.box('rank', 330, 210, 250, 120, '6. Rank the valid options\nfastest: earliest arrival\ncheapest: lowest cost\n→ best answer (and runner-up)', 'ref')
p.box('rob', 330, 380, 250, 120, '7. Robustness check\nrepeat with energy ±10%\nand half the heating;\nkeep only if the best\nanswer stays the same', 'ref')
p.box('keep', 20, 380, 200, 120, 'Graded situation\nanswer stored with the full\ntable of options, so any\ndecision can be judged\n(arrival, cost, rules broken)', 'case')
p.box('drop', 700, 400, 250, 80, 'Set aside as uncertain\nthe referee itself cannot be\nsure (about 1 in 3)', 'base')
p.arrow('sit', 'enum'); p.arrow('enum', 'sumo'); p.arrow('sumo', 'heat'); p.arrow('heat', 'chg', 'b', 't')
p.arrow('chg', 'rules', 'l', 'r'); p.arrow('rules', 'rank', 'l', 'r'); p.arrow('rank', 'rob', 'b', 't')
p.arrow('rob', 'keep', 'l', 'r', 'stable'); p.arrow('rob', 'drop', 'r', 'l', 'answer flips')
pages.append(p)

# 3. Roles of the model
p = Page('3 Roles', 1180, 600, 'Three ways to use the small model (research question 2)')
p.box('r1t', 20, 70, 160, 90, 'R1\nThe model\ndecides alone', 'note')
p.box('r1in', 200, 80, 220, 70, 'Fact sheet +\ndriver\'s sentence', 'case', bold_first=False)
p.box('r1m', 460, 80, 200, 70, 'Small model', 'model', 'todo')
p.box('r1d', 700, 80, 220, 70, 'Decision\ncharge? where? to what %?', 'score')
p.box('r2t', 20, 210, 160, 120, 'R2\nThe model decides,\na checker catches\nbroken rules', 'note')
p.box('r2in', 200, 235, 220, 70, 'Fact sheet +\ndriver\'s sentence', 'case', bold_first=False)
p.box('r2m', 460, 235, 200, 70, 'Small model', 'model', 'todo')
p.box('r2c', 700, 235, 220, 70, 'On-device check\nplug, status, battery', 'ref')
p.box('r2d', 960, 235, 200, 70, 'Decision', 'score')
p.box('r3t', 20, 400, 160, 120, 'R3 (comparison)\nThe model only\nreads the request', 'note')
p.box('r3in', 200, 425, 220, 70, 'Driver\'s sentence only', 'case', bold_first=False)
p.box('r3m', 460, 425, 200, 70, 'Small model', 'model', 'todo')
p.box('r3s', 700, 425, 220, 70, 'Settings\ngoal, deadline, budget', 'base')
p.box('r3p', 960, 425, 200, 70, 'Fixed planner\ndecides', 'base')
p.arrow('r1in', 'r1m'); p.arrow('r1m', 'r1d')
p.arrow('r2in', 'r2m'); p.arrow('r2m', 'r2c'); p.arrow('r2c', 'r2d', label='passes')
p.arrow('r2c', 'r2m', 'b', 'b', 'problem found: reason sent back, one retry', dashed=True)
p.arrow('r3in', 'r3m'); p.arrow('r3m', 'r3s'); p.arrow('r3s', 'r3p')
p.box('allref', 960, 70, 200, 90, 'Every decision is\njudged by the referee', 'ref')
p.arrow('r1d', 'allref')
legend(p, 20, 555)
pages.append(p)

# 4. The offline prototype
p = Page('4 Prototype', 1180, 470, 'The offline prototype on the laptop (no internet, no simulator)')
p.box('lap', 20, 60, 1140, 330, '', 'note', bold_first=False)
p.box('lapt', 760, 70, 380, 30, 'Laptop: i7-13700H, 24 GB, CPU only', 'note', size=13)
p.box('pick', 50, 130, 200, 90, 'Pick a situation\n(30 test situations)\nor type your own request', 'case')
p.box('oll', 300, 130, 220, 90, 'Ollama + Qwen2.5\n4-bit, runs locally\nreturns JSON decision', 'model', 'todo')
p.box('chk', 570, 130, 220, 90, 'On-device check\nplug, status, access,\nenough battery', 'ref')
p.box('ver', 840, 130, 290, 90, 'Referee verdict\nlooked up in the stored table:\narrival, cost, rules, best option', 'score')
p.box('json', 840, 270, 290, 90, 'demo_situations.json\nprecomputed in SUMO on the\nMichigan road network', 'data')
p.box('time', 300, 270, 220, 70, 'Shown on screen\ntime to decide, tokens', 'base')
p.arrow('pick', 'oll'); p.arrow('oll', 'chk'); p.arrow('chk', 'ver', label='passes')
p.arrow('chk', 'oll', 't', 't', 'reason, one retry', dashed=True)
p.arrow('json', 'ver', 't', 'b'); p.arrow('oll', 'time', 'b', 't')
legend(p, 20, 420)
pages.append(p)

with open(os.path.join(HERE, 'thesis_diagrams.drawio'), 'w', encoding='utf-8') as f:
    f.write('<mxfile host="app.diagrams.net" type="device">' + ''.join(pg.drawio() for pg in pages) + '</mxfile>')
os.makedirs(os.path.join(HERE, 'svg'), exist_ok=True)
for pg in pages:
    open(os.path.join(HERE, 'svg', pg.name.split(' ', 1)[0] + '_' + pg.name.split(' ', 1)[1].lower().replace(' ', '_') + '.svg'), 'w', encoding='utf-8').write(pg.svg())
print('ok', len(pages))
