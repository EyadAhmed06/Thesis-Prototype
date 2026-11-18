import osmium, csv, sys
rows=[]
class H(osmium.SimpleHandler):
    def add(self,o,lat,lon):
        t=dict(o.tags)
        if t.get('amenity')=='charging_station':
            rows.append(dict(id=o.id,lat=lat,lon=lon,name=t.get('name',''),operator=t.get('operator',''),
              capacity=t.get('capacity',''),sockets=';'.join(f'{k}={v}' for k,v in t.items() if k.startswith('socket')),
              output=t.get('charging_station:output',t.get('maxpower','')),motorcar=t.get('motorcar',''),fee=t.get('fee','')))
    def node(self,n): self.add(n,n.location.lat,n.location.lon)
    def area(self,a):
        try:
            c=[(n.lat,n.lon) for r in a.outer_rings() for n in r]
            self.add(a,sum(x for x,_ in c)/len(c),sum(y for _,y in c)/len(c))
        except Exception: pass
H().apply_file(sys.argv[1],locations=True)
with open(sys.argv[2],'w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0].keys()) if rows else ['id']); w.writeheader(); w.writerows(rows)
print(len(rows),'charging stations')
inbox=[r for r in rows if 31.2<=r['lon']<=32.45 and 29.55<=r['lat']<=30.15]
print(len(inbox),'in Cairo–Sokhna box;', sum(1 for r in rows if r['sockets']),'with socket tags;', sum(1 for r in rows if r['output']),'with power tags')
