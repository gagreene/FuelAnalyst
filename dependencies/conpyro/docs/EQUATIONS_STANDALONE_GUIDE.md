# Using Conpyro Equations Independently

This guide demonstrates how to use the equation modules (`ladder_eqs.py` and `moisture_eqs.py`) in your own code without the class wrappers.

## Installation

```python
from conpyro.components.equations.ladder_eqs import (
    calc_dead_ladder_contributions,
    calc_fmc,
    calc_live_ladder_contributions,
    calc_min_ladder_fsg,
    calc_total_sfc,
)

from conpyro.components.equations.moisture_eqs import (
    calc_mc_ffmc,
    calc_mc_dmc,
    calc_mc_sa,
    calc_season,
    calc_stand_density,
    get_adjusted_mc_areas,
)
```

## Ladder Equations Examples

### Example 1: Dead Ladder Fuel Contributions

```python
import numpy as np
from conpyro.components.equations.ladder_eqs import calc_dead_ladder_contributions

# Parameters
ht_midstry_dead = 2.0  # meters
cbh_ovrstry = 4.0  # meters (crown base height)
dead_branch_fl = 0.2  # kg/m2
m = 4.2  # ladder fuel multiplier

# Calculate
fsg, sfc = calc_dead_ladder_contributions(
    ht_midstry_dead, cbh_ovrstry, dead_branch_fl, m
)

print(f"Dead ladder FSG: {float(fsg[0]):.4f} m")
print(f"Dead ladder SFC: {float(sfc[0]):.4f} kg/m2")
```

**Error Handling:**
```python
try:
    calc_dead_ladder_contributions(2.0, 4.0, 0.2, -1.0)  # Invalid m
except ValueError as e:
    print(f"Error: {e}")  # "m must be positive, got -1.0"
```

### Example 2: Foliar Moisture Content

```python
import numpy as np
from conpyro.components.equations.ladder_eqs import calc_fmc

# Parameters
lat = 50.5  # latitude (decimal degrees)
long = -120.5  # longitude (decimal degrees)
elevation = 1000.0  # meters
wx_date = 20230731  # YYYYMMDD format (July 31, 2023)

# Calculate
fmc, latn, d0, dj, nd = calc_fmc(lat, long, elevation, wx_date)

print(f"FMC: {float(fmc[0]):.2f}%")
print(f"Normalized latitude: {float(latn[0]):.2f}")
print(f"Julian day: {int(dj[0])}")
```

**With Custom D0/DJ:**
```python
# Provide your own date of minimum FMC
fmc, latn, d0, dj, nd = calc_fmc(
    lat=50.5,
    long=-120.5,
    elevation=1000.0,
    wx_date=20230731,
    d0=150,  # Your custom D0 value
    dj=212   # Your custom DJ value
)
```

### Example 3: Live Ladder Fuel Contributions

```python
import numpy as np
from conpyro.components.equations.ladder_eqs import calc_live_ladder_contributions

# Parameters
multiply_cfl = False  # Don't apply CFL multiplier
cfl_midstry = 0.5  # Canopy fuel load (kg/m2)
cbh_ovrstry = 4.0  # Crown base height (m)
cbh_midstry = 0.5  # Midstory CBH (m)
ht_midstry_live = 2.0  # Midstory height (m)
fmc = 90.0  # Foliar moisture content (%)
m = 4.2  # Multiplier
fsg = 2.0  # Base fuel strata gap (m)
sfc = 1.0  # Base surface fuel consumption (kg/m2)

# Calculate
adj_cfl, fsg_live, sfc_live = calc_live_ladder_contributions(
    multiply_cfl, cfl_midstry, cbh_ovrstry, cbh_midstry,
    ht_midstry_live, fmc, m, fsg, sfc
)

print(f"Adjusted CFL: {float(adj_cfl[0]):.4f} kg/m2")
print(f"Live ladder FSG: {float(fsg_live[0]):.4f} m")
print(f"Live ladder SFC: {float(sfc_live[0]):.4f} kg/m2")
```

**Validation - FMC Out of Range:**
```python
try:
    calc_live_ladder_contributions(False, 0.5, 4.0, 0.5, 2.0, 150.0, 4.2, 2.0, 1.0)
except ValueError as e:
    print(f"Error: {e}")  # "fmc must be between 0 and 100 percent"
```

### Example 4: Total Surface Fuel Consumption

```python
import numpy as np
from conpyro.components.equations.ladder_eqs import calc_total_sfc

# Parameters
sfc_base = 1.0  # Base SFC (kg/m2)
sfc_dead = 0.3  # Dead ladder contribution (kg/m2)
sfc_live = 0.5  # Live ladder contribution (kg/m2)

# Calculate
sfc_total = calc_total_sfc(sfc_base, sfc_dead, sfc_live)
print(f"Total SFC: {float(sfc_total[0]):.4f} kg/m2")
```

---

## Moisture Content Equations Examples

### Example 5: Moisture Content from FFMC

```python
import numpy as np
from conpyro.components.equations.moisture_eqs import calc_mc_ffmc

# Parameters
ref_array = np.array([0.0])  # Reference array for output shape
ffmc = 85.0  # Fine Fuel Moisture Code

# Calculate
mc_ffmc = calc_mc_ffmc(ref_array, ffmc)
print(f"MC from FFMC: {float(mc_ffmc[0]):.4f}%")
```

**Array Operations:**
```python
ffmc_array = np.array([70.0, 85.0, 95.0])
ref_array = np.zeros(3)
mc_ffmc = calc_mc_ffmc(ref_array, ffmc_array)
print(f"MC values: {mc_ffmc}")
```

### Example 6: Stand Density from Canopy Cover

```python
import numpy as np
from conpyro.components.equations.moisture_eqs import calc_stand_density

# Parameters
ref_array = np.array([0], dtype=np.int8)
cc = 75.0  # Canopy cover (%)

# Calculate
density = calc_stand_density(ref_array, cc)
print(f"Density: {int(density[0])} (1=Low, 2=Moderate, 3=High)")
```

**Validation - Invalid Range:**
```python
try:
    calc_stand_density(np.array([0]), 150.0)  # >100%
except ValueError as e:
    print(f"Error: {e}")  # "Canopy cover must be 0-100%"
```

### Example 7: Season from Date

```python
import numpy as np
from conpyro.components.equations.moisture_eqs import calc_season

# Parameters
ref_array = np.array([0], dtype=np.int8)
month_day = 531  # May 31 (MMDD format)
season_cutoff = {1: 531, 2: 615, 3: 901, 4: 1231}

# Calculate
season = calc_season(ref_array, month_day, season_cutoff)
print(f"Season: {int(season[0])} (1=Spring, 2=Trans, 3=Summer, 4=Fall)")
```

### Example 8: Stand-Adjusted Moisture Content

```python
import numpy as np
from conpyro.components.equations.moisture_eqs import calc_mc_sa
from conpyro.components.moisture_content import MoistureContent

# Get coefficient arrays from MoistureContent class
mc = MoistureContent()
coeff_a = mc.mc_sa_coeff_a
coeff_b = mc.mc_sa_coeff_b

# Parameters
ref_array = np.array([0.0])
season = np.array([3])  # Summer
density = np.array([2])  # Moderate
stand_type = np.array([4])  # Pine
ffmc = np.array([85.0])
mc_ffmc = np.array([16.31])
mc_dmc = np.array([108.55])
use_adjusted_mc = np.array([True])

# Calculate
mc_sa_result = calc_mc_sa(
    ref_array, season, density, stand_type,
    ffmc, mc_ffmc, mc_dmc, use_adjusted_mc,
    coeff_a, coeff_b, model_mcsa='corrected'
)

print(f"MCSA: {float(mc_sa_result[0]):.4f}%")
```

**Validation - Wrong Coefficient Shape:**
```python
bad_coeff = np.zeros((4, 3, 5))  # Wrong shape
try:
    calc_mc_sa(ref_array, season, density, stand_type,
               ffmc, mc_ffmc, mc_dmc, use_adjusted_mc,
               bad_coeff, bad_coeff)
except ValueError as e:
    print(f"Error: {e}")  # Shape error
```

---

## Complete Workflow Example

```python
import numpy as np
from conpyro.components.equations import ladder_eqs, moisture_eqs
from conpyro.components.moisture_content import MoistureContent

# Step 1: Calculate moisture content
mc = MoistureContent()
mc.initialize_mc(season=3, density=2, stand_type=4, ffmc=85.0, dmc=50.0, cc=60.0)
mc.run_mc()

# Step 2: Use moisture content in ladder fuels
fmc = mc.mc_sa[0]
ht_live = 2.0
ht_dead = 2.0
cbh = 4.0

# Calculate FMC (if not already done)
fmc_calc, _, _, _, _ = ladder_eqs.calc_fmc(
    lat=50.5, long=-120.5, elevation=1000.0, wx_date=20230731
)

# Calculate ladder contributions
fsg_d, sfc_d = ladder_eqs.calc_dead_ladder_contributions(ht_dead, cbh, 0.2, 4.2)
cfl_adj, fsg_l, sfc_l = ladder_eqs.calc_live_ladder_contributions(
    False, 0.5, cbh, 0.5, ht_live, fmc, 4.2, 2.0, 1.0
)
fsg_min = ladder_eqs.calc_min_ladder_fsg(2.0, fsg_l, fsg_d)
sfc_total = ladder_eqs.calc_total_sfc(1.0, sfc_d, sfc_l)

# Step 3: Output results
print(f"FMC: {float(fmc):.2f}%")
print(f"Dead Ladder SFC: {float(sfc_d[0]):.4f} kg/m2")
print(f"Live Ladder SFC: {float(sfc_l[0]):.4f} kg/m2")
print(f"Total SFC: {float(sfc_total[0]):.4f} kg/m2")
print(f"Min FSG: {float(fsg_min[0]):.4f} m")
```

---

## Error Handling Guide

All functions validate inputs and raise informative errors:

```python
# Type errors
try:
    calc_dead_ladder_contributions(2.0, 4.0, 0.2, "invalid")
except TypeError as e:
    print(f"Type Error: {e}")

# Value errors
try:
    calc_stand_density(np.array([0]), 150.0)
except ValueError as e:
    print(f"Value Error: {e}")

# Shape errors
try:
    calc_mc_ffmc(np.array([0, 0]), np.array([85.0]))  # Incompatible shapes
except ValueError as e:
    print(f"Shape Error: {e}")
```

---

## Notes for External Users

1. **Input Validation**: All functions validate inputs and raise exceptions with descriptive messages. Catching `TypeError` and `ValueError` is recommended.

2. **Array Handling**: Functions accept scalars (int, float) or numpy arrays. Scalars are automatically converted to 1D arrays.

3. **Masked Arrays**: While functions work with regular numpy arrays, they're designed to work seamlessly with `numpy.ma.MaskedArray` objects for handling missing/invalid data.

4. **Reference Arrays**: Functions like `calc_mc_ffmc`, `calc_mc_dmc`, `calc_season`, and `calc_stand_density` require a `ref_array` parameter. This defines the output shape. Pass an array of the same shape as your main input data.

5. **Coefficient Arrays**: The `calc_mc_sa` function requires coefficient arrays (`mc_sa_coeff_a`, `mc_sa_coeff_b`) of specific shape (5, 4, 6). These are available from the `MoistureContent` class attributes.

6. **Units**: Pay attention to parameter units (meters, percentages, kg/m2, etc.) as documented in each function's docstring.

