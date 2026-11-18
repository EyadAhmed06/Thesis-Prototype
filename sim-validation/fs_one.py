import fastsim as fsim, json, numpy as np, pandas as pd, sys
base=fsim.Vehicle.from_resource('2016 Nissan Leaf 30 kWh thrml.yaml').to_yaml()
def run(tt,ss,tempC):
    n=len(tt); K=tempC+273.15
    cyc=dict(init_elev_meters=0.0,time_seconds=list(map(float,tt)),speed_meters_per_second=list(map(float,ss)),dist_meters=[0.0]*n,grade=[0.0]*n,elev_meters=[0.0]*n,
             pwr_max_chrg_watts=[0.0]*n,temp_amb_air_kelvin=[K]*n,pwr_solar_load_watts=[0.0]*n,grade_interp=0,elev_interp=0)
    c=fsim.Cycle.from_json(json.dumps(cyc),skip_init=False)
    v=fsim.Vehicle.from_yaml(base.replace('295.15',f'{K:.2f}'),skip_init=False)
    sd=fsim.SimDrive(v,c,None); sd.run()
    return sd
if __name__=='__main__':
    tt=np.arange(0,600.); ss=np.clip(np.sin(tt/60)*15+12,0,None)*np.minimum(1,tt/30)
    sd=run(tt,ss,20); df=sd.to_dataframe()
    cols=[c for c in df.columns if 'energy' in c and ('res' in c or 'hvac' in c)]
    print(cols[:40]); print(df[cols].iloc[-1].to_dict())
