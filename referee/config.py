"""All referee assumptions in one place. Every number here is a declared assumption or a measured value (source noted)."""
CAR = dict(
    name='Nissan Leaf e+ 62 kWh',
    usable_kwh=59.0,            # 62 kWh gross; usable assumed 59 kWh
    plugs_ac={'J1772'},         # Level 2 plug
    plugs_dc={'CHADEMO'},       # fast-charge plug
    onboard_ac_kw=6.6,          # built-in AC charger limit
    max_dc_kw=50.0,             # assumed CHAdeMO station limit (AFDC lists no power)
)
RESERVE = 0.10                  # must never drop below 10% (hard rule)
STOP_OVERHEAD_MIN = 5.0         # parking + plugging in, per charging stop
# Heating/cooling load SUMO lacks, fitted on real Michigan VED trips (fit_temp.py, held-out total error ~1%)
HEAT = dict(T_heat=12.0, k_heat_W_per_C=226.0, T_cool=30.0, k_cool_W_per_C=303.0)
# Cold slows DC fast charging: factor 1.0 above 10 C, 0.6 at or below 0 C, linear between (assumption)
def dc_cold_factor(T):
    return 1.0 if T >= 10 else 0.6 if T <= 0 else 0.6 + 0.04 * T
TAPER_START = 0.80              # DC power falls linearly above 80% SoC ...
TAPER_END_FRACTION = 0.2        # ... to 20% of max at 100%
UNKNOWN_PRICE = {'L2': 0.25, 'DC': 0.49}   # $/kWh when AFDC lists no price (assumption; DC = typical listed MI price)
# Referee error band used for the robustness ("uncertain") check
ENERGY_ERROR = 0.10             # +/-10% energy (validated totals within ~6%)
HEAT_SCALE_ALT = 0.5            # heat pump case: half the fitted heating load

# a situation is a close call when the runner-up (another charger, or the other charge/no-charge choice) is within this
# margin of the best; set near the lower third of the runner-up gaps (fastest: 8 min, cheapest: $0.10)
CLOSE_MIN = 8.0; CLOSE_USD = 0.10
