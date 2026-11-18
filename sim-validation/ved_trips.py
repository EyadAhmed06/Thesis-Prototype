import pandas as pd, numpy as np, sys
d=pd.read_csv(sys.argv[1],low_memory=False)
d.columns=[c.strip() for c in d.columns]
I='HV Battery Current[A]'; V='HV Battery Voltage[V]'; SP='Vehicle Speed[km/h]'; T='OAT[DegC]'
print({c:d[c].notna().mean().round(2) for c in [I,V,SP,T,'HV Battery SOC[%]']})
print(d[I].describe().round(1).to_dict())
rows=[]
for (v,t),g in d.groupby(['VehId','Trip']):
    g=g.sort_values('Timestamp(ms)')
    ts=g['Timestamp(ms)'].values/1000; dt=np.diff(ts,append=ts[-1]); dt=np.clip(dt,0,5)
    sp=g[SP].interpolate(limit_direction='both').values/3.6
    km=(sp*dt).sum()/1000
    gi=g[[I,V]].interpolate(limit_direction='both')
    if gi[I].isna().all() or gi[V].isna().all(): continue
    p=(gi[I]*gi[V]).values  # W
    cov=g[I].notna().mean()
    rows.append(dict(veh=v,trip=t,km=km,dur_min=(ts[-1]-ts[0])/60,Wh=(p*dt).sum()/3600,temp=g[T].mean(),vmean=km/max((ts[-1]-ts[0])/3600,1e-6),cov=cov,
                     soc0=g['HV Battery SOC[%]'].dropna().iloc[0] if g['HV Battery SOC[%]'].notna().any() else np.nan,
                     soc1=g['HV Battery SOC[%]'].dropna().iloc[-1] if g['HV Battery SOC[%]'].notna().any() else np.nan))
r=pd.DataFrame(rows); r.to_csv(sys.argv[2],index=False)
print(len(r),'trips with battery data'); print(r.describe().round(2).to_string())
