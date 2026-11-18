import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import time, sys, pandas as pd, numpy as np
t0=time.time()
from referee import Referee
R=Referee(sys.argv[1]); print('net loaded', round(time.time()-t0), 's')
route=open(sys.argv[2]).read().split()
o,d=route[0],route[-1]
# chargers within 2 km of the direct route, as candidates
xy=np.array([R.net.getEdge(e).getShape()[0] for e in route])
ch=R.ch.copy()
cx=np.array([R.net.convertLonLat2XY(lo,la) for lo,la in zip(ch.lon,ch.lat)])
dist=np.sqrt(((cx[:,None,:]-xy[None,:,:])**2).sum(-1)).min(1)
ch['d']=dist
cand=ch[ch.d<2000].sort_values('d')
print('chargers within 2 km of route', len(cand), cand.level.value_counts().to_dict())
pick=list(cand[cand.level=='DC'].index[:6])+list(cand[cand.level=='L2'].index[:6])
case=dict(id='sara', origin_edge=o, dest_edge=d, depart_min=13*60, soc0=0.25, temp_c=-3, goal='cheapest', deadline_min=14*60+30, candidates=pick)
t1=time.time(); legs=R.legs_for(case); dr=R.drive(legs); print('drove',len(dr),'legs in',round(time.time()-t1),'s')
print(dr[f'sara__direct'])
res=R.decide(case,dr)
op=res['options']; print(op[op.valid].head(8)[['charge','charger','target','arrive_min','cost','soc_end','charge_min']].round(2).to_string())
print('robust',res['robust'],'n_valid',res['n_valid'])
print(op[~op.valid].drop_duplicates('charger').head(8)[['charger','broken']].to_string())
for cid in pick: print(cid, R.ch.loc[cid,['name','level','plugs','working','price_text']].tolist())
