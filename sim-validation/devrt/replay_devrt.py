import pandas as pd, numpy as np, subprocess, sys, re, glob, os
B, D = sys.argv[1], sys.argv[2]
out=[]
for f in sorted(glob.glob(D+'/NISSAN LEAF/*.csv')):
    d=pd.read_csv(f)
    # time from GPS mm:ss.s plus data minute; build monotonic seconds
    ts=pd.to_datetime(d['timestamp_data_utc'],format='%d/%m/%Y %H:%M')
    def tosec(x):
        x=str(x)
        if '/' in x:
            q=pd.to_datetime(x,dayfirst=True); return q.minute*60+q.second+q.microsecond/1e6
        m,s_=x.split(':')[-2:]; return float(m)*60+float(s_)
    sec=d['timestamp_gps_utc'].map(tosec); t=np.unwrap(sec.values,period=3600); t=t-t[0]
    km=d['cumul_dist'].max(); dsoc=d['soc'].iloc[0]-d['soc'].iloc[-1]
    if km<10 or np.any(np.diff(t)<0): continue
    tt=np.arange(0,int(t[-1])+1); v=np.interp(tt,t,d['speed'].values)/3.6
    a=np.gradient(v)
    x=np.interp(tt,t,d['cumul_dist'].values*1000); z=np.interp(tt,t,d['elv_spy'].rolling(5,center=True,min_periods=1).mean().values)
    dx=np.gradient(x); dz=np.gradient(z); sl=np.degrees(np.arctan2(dz,np.maximum(dx,0.5))); sl[dx<0.5]=0; sl=np.clip(sl,-12,12)
    res={}
    for tag,s in [('flat',np.zeros_like(sl)),('slope',sl)]:
        p=f'/tmp/dv_{os.getpid()}.csv'; open(p,'w').write('\n'.join(f'{i};{vv*3.6:.2f};{aa:.3f};{ss:.3f}' for i,vv,aa,ss in zip(tt,v,a,s)))
        o=subprocess.run([B,'-t',p,'--kmh','--have-slope','--additional-files','leafplus.add.xml','--vtype','leafplus','-o',p+'.out'],capture_output=True,text=True)
        m=re.search(r'electricity:([\d.\-e]+)',o.stdout); res[tag]=float(m.group(1)) if m else np.nan
    out.append(dict(trip=os.path.basename(f)[9:-4],km=km,T=d['amb_temp'].mean(),meas_Wh=dsoc/100*62000,sim_flat=res['flat'],sim_slope=res['slope'],dur_min=t[-1]/60))
r=pd.DataFrame(out); r.to_csv('devrt_replay.csv',index=False)
print(r.round(1).to_string())
for c in ['sim_flat','sim_slope']:
    e=(r[c]-r.meas_Wh)/r.meas_Wh
    print(c,'n',len(r),'km',round(r.km.sum()),'meas',round(r.meas_Wh.sum()/r.km.sum()/10,1),'sim',round(r[c].sum()/r.km.sum()/10,1),'kWh/100km; total ratio',round(r[c].sum()/r.meas_Wh.sum(),3),'median|err|',round(100*e.abs().median()))
