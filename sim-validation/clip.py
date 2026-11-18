import shapefile, sys, collections
D=sys.argv[1]; OUT=sys.argv[2]
W,E,Sb,N=31.20,32.45,29.55,30.15
keep={'motorway','motorway_link','trunk','trunk_link','primary','primary_link','secondary','secondary_link','tertiary','tertiary_link'}
r=shapefile.Reader(D+'/gis_osm_roads_free_1')
f=[x[0] for x in r.fields[1:]]; print(f)
nodes={}; ways=[]; cnt=collections.Counter()
for sr in r.iterShapeRecords():
    rec=dict(zip(f,sr.record))
    if rec['fclass'] not in keep: continue
    bx=sr.shape.bbox
    if bx[2]<W or bx[0]>E or bx[3]<Sb or bx[1]>N: continue
    ids=[]
    for lon,lat in sr.shape.points:
        k=(round(lon,7),round(lat,7))
        if k not in nodes: nodes[k]=len(nodes)+1
        ids.append(nodes[k])
    ways.append((rec,ids)); cnt[rec['fclass']]+=1
print(len(ways),'ways',len(nodes),'nodes',dict(cnt))
with open(OUT,'w') as o:
    o.write('<?xml version="1.0" encoding="UTF-8"?>\n<osm version="0.6">\n')
    for (lon,lat),i in nodes.items(): o.write(f'<node id="{i}" lat="{lat}" lon="{lon}"/>\n')
    for rec,ids in ways:
        o.write(f'<way id="{rec["osm_id"]}">'+''.join(f'<nd ref="{i}"/>' for i in ids))
        o.write(f'<tag k="highway" v="{rec["fclass"]}"/>')
        if rec['oneway']=='F': o.write('<tag k="oneway" v="yes"/>')
        elif rec['oneway']=='T': o.write('<tag k="oneway" v="-1"/>')
        if rec['maxspeed']: o.write(f'<tag k="maxspeed" v="{rec["maxspeed"]}"/>')
        nm=str(rec.get('ref') or '').replace('&','and').replace('"','').replace('<','')
        if nm: o.write(f'<tag k="ref" v="{nm}"/>')
        o.write('</way>\n')
    o.write('</osm>\n')
p=shapefile.Reader(D+'/gis_osm_pois_free_1'); pf=[x[0] for x in p.fields[1:]]
c=collections.Counter(dict(zip(pf,rr))['fclass'] for rr in p.iterRecords())
print([k for k in c if 'charg' in k or 'fuel' in k], c.get('fuel'))
