import sys; sys.path.insert(0, sys.argv[1])
import fastsim as fsim, json, numpy as np, pandas as pd
from concurrent.futures import ProcessPoolExecutor
from fs_one import base
sp=fsim.SimParams.default().to_yaml().replace('trace_miss_opts: Error','trace_miss_opts: Allow')
def run(args):
    tt,ss,tempC=args
    try:
        n=len(tt); K=tempC+273.15
        cyc=dict(init_elev_meters=0.0,time_seconds=list(map(float,tt)),speed_meters_per_second=list(map(float,ss)),dist_meters=[0.0]*n,grade=[0.0]*n,elev_meters=[0.0]*n,
                 pwr_max_chrg_watts=[0.0]*n,temp_amb_air_kelvin=[K]*n,pwr_solar_load_watts=[0.0]*n,grade_interp=0,elev_interp=0)
        c=fsim.Cycle.from_json(json.dumps(cyc),skip_init=False)
        v=fsim.Vehicle.from_yaml(base.replace('295.15',f'{K:.2f}'),skip_init=False)
        sd=fsim.SimDrive(v,c,fsim.SimParams.from_yaml(sp,skip_init=False)); sd.run()
        df=sd.to_dataframe()
        return df['veh.pt_type.BEV.res.history.energy_out_electrical_joules'].iloc[-1]/3600
    except Exception as e:
        return np.nan
if __name__=='__main__':
    d=pd.read_csv('ved_ev.csv',low_memory=False); r=pd.read_csv('replay.csv')
    G={k:g for k,g in d.groupby(['VehId','Trip'])}; jobs=[]
    for _,row in r.iterrows():
        g=G[(row.veh,row.trip)].sort_values('Timestamp(ms)')
        t=g['Timestamp(ms)'].values/1000; t=t-t[0]; s=g['Vehicle Speed[km/h]'].values/3.6
        tt=np.arange(0,int(t[-1])+1.); ss=np.interp(tt,t,s)
        if ss[0]>0: ramp=np.arange(0,ss[0],2.0); ss=np.r_[ramp,ss]; tt=np.arange(len(ss),dtype=float)
        ss[-1]=0.0
        jobs.append((tt,ss,row.temp))
    with ProcessPoolExecutor(8) as ex: r['fast_Wh']=list(ex.map(run,jobs,chunksize=4))
    r.to_csv('replay2.csv',index=False)
    ok=r.dropna(subset=['fast_Wh'])
    print('ran',len(ok),'of',len(r))
    def rep(x,lab):
        print(f"{lab}: n={len(x)} measured {x.meas_Wh.sum()/x.km.sum()/10:.1f} | SUMO {x.sumo_Wh.sum()/x.km.sum()/10:.1f} (ratio {x.sumo_Wh.sum()/x.meas_Wh.sum():.2f}, med|err| {100*((x.sumo_Wh-x.meas_Wh)/x.meas_Wh).abs().median():.0f}%) | FASTSim {x.fast_Wh.sum()/x.km.sum()/10:.1f} (ratio {x.fast_Wh.sum()/x.meas_Wh.sum():.2f}, med|err| {100*((x.fast_Wh-x.meas_Wh)/x.meas_Wh).abs().median():.0f}%)")
    rep(ok,'all'); rep(ok[(ok.temp>=15)&(ok.temp<=25)],'15-25C'); rep(ok[ok.temp<5],'<5C'); rep(ok[(ok.temp>=5)&(ok.temp<15)],'5-15C'); rep(ok[ok.temp>28],'>28C')
