import osmium, sys
W,E,Sb,N=-84.2,-82.9,42.0,42.7
keep={'motorway','motorway_link','trunk','trunk_link','primary','primary_link','secondary','secondary_link','tertiary','tertiary_link'}
nodes={}; ways=[]
class H(osmium.SimpleHandler):
    def way(self,w):
        hw=w.tags.get('highway')
        if hw not in keep: return
        pts=[]
        try:
            for n in w.nodes: pts.append((n.ref,n.lon,n.lat))
        except osmium.InvalidLocationError: return
        if not any(W<=x<=E and Sb<=y<=N for _,x,y in pts): return
        for r,x,y in pts: nodes[r]=(x,y)
        ways.append((w.id,[r for r,_,_ in pts],{k:w.tags.get(k) for k in ('highway','oneway','maxspeed','lanes','junction') if w.tags.get(k)}))
H().apply_file(sys.argv[1],locations=True)
esc=lambda s:str(s).replace('&','and').replace('"','').replace('<','')
with open(sys.argv[2],'w') as o:
    o.write('<?xml version="1.0" encoding="UTF-8"?>\n<osm version="0.6">\n')
    for r,(x,y) in nodes.items(): o.write(f'<node id="{r}" lat="{y}" lon="{x}"/>\n')
    for i,nds,t in ways:
        o.write(f'<way id="{i}">'+''.join(f'<nd ref="{r}"/>' for r in nds)+''.join(f'<tag k="{k}" v="{esc(v)}"/>' for k,v in t.items())+'</way>\n')
    o.write('</osm>\n')
print(len(ways),'ways',len(nodes),'nodes')
