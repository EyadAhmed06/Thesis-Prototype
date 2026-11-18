"""Turn the AFDC station list (already snapped to the SUMO network) into the referee's charger table."""
import pandas as pd, re, sys
def price(s, level):
    if not isinstance(s, str) or not s.strip():
        return dict(kind='kwh', value=None, fee=0.0, text='not listed')
    t = s.lower(); fee = 0.0
    m = re.search(r'\$([\d.]+)\s*(?:connection |session )?fee|\$([\d.]+)\s*per session', t)
    if m: fee = float(m.group(1) or m.group(2))
    if t.startswith('free') and 'parking' not in t and '$' not in t:
        return dict(kind='kwh', value=0.0, fee=0.0, text=s)
    m = re.search(r'\$([\d.]+)\s*(?:per|/)\s*kwh', t)
    if m: return dict(kind='kwh', value=float(m.group(1)), fee=fee, text=s)
    m = re.search(r'\$([\d.]+)\s*(?:per|/)\s*(?:hour|hr)', t)
    if m: return dict(kind='hour', value=float(m.group(1)), fee=fee, text=s)
    m = re.search(r'\$([\d.]+)\s*(?:per|/)\s*min', t)
    if m: return dict(kind='min', value=float(m.group(1)), fee=fee, text=s)
    return dict(kind='kwh', value=None, fee=fee, text=s)
def build(src, net_path, out):
    from referee import _sumolib; sumolib = _sumolib()
    net = sumolib.net.readNet(net_path)
    d = pd.read_csv(src, low_memory=False)
    rows = []
    for _, r in d.iterrows():
        x, y = net.convertLonLat2XY(r.Longitude, r.Latitude)
        c = [(dist, e) for e, dist in net.getNeighboringEdges(x, y, 300) if e.allows('passenger') and e.getLength() > 20]
        if not c: continue
        dist, e = min(c, key=lambda t: t[0])
        pos = min(max(sumolib.geomhelper.polygonOffsetWithMinimumDistanceToPoint((x, y), e.getShape()), 1.0), e.getLength() - 1.0)
        plugs = set(str(r['EV Connector Types']).split()) if isinstance(r['EV Connector Types'], str) else set()
        for level, n in [('DC', r['EV DC Fast Count']), ('L2', r['EV Level2 EVSE Num'])]:
            if pd.notna(n) and n > 0:
                p = price(r['EV Pricing'], level)
                rows.append(dict(id=f"{r.ID}_{level}", afdc_id=r.ID, name=r['Station Name'], city=r.City, lon=r.Longitude, lat=r.Latitude,
                                 edge=e.getID(), pos=round(pos, 1), dist_to_road_m=round(dist, 1), level=level,
                                 plugs=' '.join(sorted(plugs)), working=r['Status Code'] == 'E', public=r['Access Code'] == 'public' and not bool(r['Restricted Access']),
                                 price_kind=p['kind'], price_value=p['value'], price_fee=p['fee'], price_text=p['text'], network=r['EV Network']))
    pd.DataFrame(rows).to_csv(out, index=False)
    print(len(rows), 'charger entries written to', out)
if __name__ == '__main__':
    build(sys.argv[1], sys.argv[2], sys.argv[3])
