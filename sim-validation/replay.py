import pandas as pd, numpy as np, subprocess, sys, re, os
from concurrent.futures import ThreadPoolExecutor
B=sys.argv[1]
d=pd.read_csv('ved_ev.csv',low_memory=False); r=pd.read_csv('ved_trips.csv')
r['kwh100']=-r.Wh/r.km/10; r=r[(r.km>=2)&(r.kwh100>0)&(r.kwh100<60)].copy()
G={k:g for k,g in d.groupby(['VehId','Trip'])}
def run(row):
    g=G[(row.veh,row.trip)].sort_values('Timestamp(ms)')
    t=g['Timestamp(ms)'].values/1000; t=t-t[0]; s=g['Vehicle Speed[km/h]'].values
    tt=np.arange(0,int(t[-1])+1); ss=np.interp(tt,t,s)
    f=f'cyc/{row.veh}_{row.trip}.csv'; open(f,'w').write('\n'.join(f'{a};{b:.2f}' for a,b in zip(tt,ss)))
    o=subprocess.run([B+'/emissionsDrivingCycle','-t',f,'--kmh','--compute-a','--additional-files','leaf.add.xml','--vtype','leaf','-o',f+'.out'],capture_output=True,text=True).stdout
    os.remove(f); os.remove(f+'.out')
    m=re.search(r'electricity:([\d.\-e]+)',o); return float(m.group(1)) if m else np.nan
with ThreadPoolExecutor(8) as ex: r['sumo_Wh']=list(ex.map(run,[x for _,x in r.iterrows()]))
r['meas_Wh']=-r.Wh; r['err']=(r.sumo_Wh-r.meas_Wh)/r.meas_Wh
r.to_csv('replay.csv',index=False)
def rep(x,lab):
    print(f"{lab}: n={len(x)} km={x.km.sum():.0f} measured {x.meas_Wh.sum()/x.km.sum()/10:.1f} vs SUMO {x.sumo_Wh.sum()/x.km.sum()/10:.1f} kWh/100km; total ratio {x.sumo_Wh.sum()/x.meas_Wh.sum():.2f}; median |err| {100*x.err.abs().median():.0f}%; corr {np.corrcoef(x.sumo_Wh,x.meas_Wh)[0,1]:.2f}")
rep(r,'all temps'); rep(r[(r.temp>=15)&(r.temp<=25)],'15-25C'); rep(r[r.temp<5],'below 5C'); rep(r[r.temp>28],'above 28C')
