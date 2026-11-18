"""Fit SUMO's missing heating/cooling load on real Michigan VED trips.
Extra power (W) = k_heat*max(0, T_heat - T) + k_cool*max(0, T - T_cool), applied for the trip duration.
Model: measured = a*SUMO + extra. Fit on a random half of trips (seed 0), report error on the held-out half."""
import pandas as pd, numpy as np, sys
r = pd.read_csv(sys.argv[1] if len(sys.argv) > 1 else '../sim-validation/replay.csv')
rng = np.random.default_rng(0); test = rng.random(len(r)) < 0.5
h = r.dur_min / 60
def design(d, Th, Tc):
    return np.c_[d.sumo_Wh, (d.dur_min/60) * np.maximum(0, Th - d.temp), (d.dur_min/60) * np.maximum(0, d.temp - Tc)]
best = None
for Th in range(0, 21):
    for Tc in range(22, 31, 2):
        X = design(r[~test], Th, Tc); y = r.meas_Wh[~test]
        k, *_ = np.linalg.lstsq(X, y, rcond=None); k = np.maximum(k, 0)
        sse = ((X @ k - y) ** 2).sum()
        if best is None or sse < best[0]: best = (sse, Th, Tc, k)
_, Th, Tc, k = best
pred = design(r, Th, Tc) @ k
def rep(m, lab):
    d = r[m]; p = pred[m]
    print(f"{lab}: n={m.sum()} km={d.km.sum():.0f} total ratio raw {d.sumo_Wh.sum()/d.meas_Wh.sum():.3f} corrected {p.sum()/d.meas_Wh.sum():.3f}; median |err| raw {100*((d.sumo_Wh-d.meas_Wh)/d.meas_Wh).abs().median():.0f}% corrected {100*((p-d.meas_Wh)/d.meas_Wh).abs().median():.0f}%")
print(f"scale a={k[0]:.3f}, T_heat={Th} C, k_heat={k[1]:.0f} W per degree, T_cool={Tc} C, k_cool={k[2]:.0f} W per degree")
rep(test.values if hasattr(test,'values') else test, 'held-out')
for lab, m in [('held-out below 5C', test & (r.temp < 5)), ('held-out 15-25C', test & r.temp.between(15, 25)), ('held-out above 28C', test & (r.temp > 28))]:
    rep(np.asarray(m), lab)
pd.Series({'scale_2013_leaf': k[0], 'T_heat': Th, 'k_heat_W_per_C': k[1], 'T_cool': Tc, 'k_cool_W_per_C': k[2]}).to_json('temp_correction.json')
