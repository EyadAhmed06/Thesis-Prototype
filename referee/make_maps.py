"""Map data for the live dashboard and the demo: for every test situation, the routes SUMO drove (direct, to each
charger, from each charger to the destination) as longitude/latitude lines, plus a light background of the main roads.
Display only: nothing here is used for grading.
Usage: python make_maps.py NET_XML CASES_JSONL OUT_JSON"""
import sys, os, json; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from referee import Referee

def simplify(pts, tol):
    """Douglas-Peucker on lon/lat points."""
    if len(pts) < 3: return pts
    (x1, y1), (x2, y2) = pts[0], pts[-1]; dx, dy = x2 - x1, y2 - y1; L = (dx * dx + dy * dy) ** .5 or 1e-12
    d = [abs(dy * (x - x1) - dx * (y - y1)) / L for x, y in pts[1:-1]]; i = max(range(len(d)), key=d.__getitem__)
    if d[i] < tol: return [pts[0], pts[-1]]
    return simplify(pts[:i + 2], tol)[:-1] + simplify(pts[i + 1:], tol)

def main(net_path, cases_path, out):
    R = Referee(net_path); net = R.net
    def line(edges, tol=0.0004):
        if not edges: return []
        pts = []
        for eid in edges:
            for x, y in net.getEdge(eid).getShape():
                lon, lat = net.convertXY2LonLat(x, y); pts.append((round(lon, 5), round(lat, 5)))
        return [list(p) for p in simplify(pts, tol)]
    maps = {}
    cases = [json.loads(l) for l in open(cases_path, encoding='utf-8')]
    for n, c in enumerate(cases):
        legs = R.legs_for(c); m = {'direct': None, 'to': {}, 'from': {}}
        for g in legs:
            kind, _, cid = g['id'].partition('__')[2].partition('__')
            if kind == 'direct': m['direct'] = line(g['edges'])
            elif cid in c['letters']: m[kind][c['letters'][cid]] = line(g['edges'])
        ch = {}
        for cid, L in c['letters'].items():
            r = R.ch.loc[cid]; ch[L] = dict(lon=float(r.lon), lat=float(r.lat), name=str(r['name']), city=str(r.city), level=str(r.level),
                                            usable=not R.usable(cid), trap=', '.join(R.usable(cid)))
        m['chargers'] = ch; maps[c['id']] = m
        if n % 50 == 0: print(n, '/', len(cases), flush=True)
    # background: main roads inside the area the situations use
    xs = [p[0] for m in maps.values() for p in (m['direct'] or [])]; ys = [p[1] for m in maps.values() for p in (m['direct'] or [])]
    box = (min(xs) - .05, min(ys) - .05, max(xs) + .05, max(ys) + .05); bg = []
    for e in net.getEdges():
        t = e.getType() or ''
        if not any(k in t for k in ('motorway', 'trunk', 'primary')) or 'link' in t: continue
        pts = line([e.getID()], 0.001)
        if pts and box[0] < pts[0][0] < box[2] and box[1] < pts[0][1] < box[3]: bg.append(pts)
    json.dump({'box': box, 'roads': bg, 'situations': maps}, open(out, 'w'), separators=(',', ':'))
    print('situations', len(maps), 'background roads', len(bg), 'bytes', os.path.getsize(out))

if __name__ == '__main__':
    main(*sys.argv[1:4])
