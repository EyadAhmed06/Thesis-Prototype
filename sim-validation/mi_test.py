import sys; sys.path.insert(0,sys.argv[1]+'/sumo/lib/python3.13/site-packages/sumo/tools')
import sumolib, pandas as pd, warnings; warnings.filterwarnings('ignore')
n=sumolib.net.readNet('aa_det.net.xml')
def near(lon,lat,r=800,minspeed=0):
    x,y=n.convertLonLat2XY(lon,lat)
    c=[(d,e) for e,d in n.getNeighboringEdges(x,y,r) if e.allows('passenger') and e.getSpeed()>minspeed]
    return min(c,key=lambda t:t[0]) if c else (None,None)
a=near(-83.743,42.281,800,8)[1]; b=near(-83.045,42.331,800,8)[1]
p,_=n.getShortestPath(a,b,vClass='passenger')
print('edges',len(n.getEdges()),'| Ann Arbor->Detroit km',round(sum(e.getLength() for e in p)/1000,1),'freeflow min',round(sum(e.getLength()/e.getSpeed() for e in p)/60,1))
open('route_aa_det.txt','w').write(' '.join(e.getID() for e in p))
d=pd.read_csv(sys.argv[2],low_memory=False)
d=d[d.Longitude.between(-84.2,-82.9)&d.Latitude.between(42.0,42.7)].copy()
m=[near(lo,la,300)[0] for lo,la in zip(d.Longitude,d.Latitude)]
d['dist_to_road_m']=m; ok=d[d.dist_to_road_m.notna()]
print('stations in box',len(d),'| within 300 m of a main road',len(ok),'| DC fast',int((ok['EV DC Fast Count'].fillna(0)>0).sum()),'| CHAdeMO',int(ok['EV Connector Types'].fillna('').str.contains('CHADEMO').sum()),'| temporarily unavailable',int((ok['Status Code']=='T').sum()))
ok.to_csv('aa_det_stations.csv',index=False)
