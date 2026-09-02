# ConPyro — Components Parameter Combinations

This document identifies all required parameters and alternate parameter combinations
for each component of the ConPyro system. When a primary parameter can be supplied as
`None`, the alternate parameters that must be provided in its place are listed.

> **Data types** — Unless noted otherwise, every numeric parameter accepts
> `int`, `float`, or `numpy.ndarray`. All array inputs must share the same shape.

---

## Table of Contents

1. [Moisture Content (`MoistureContent`)](#1-moisture-content)
2. [Rothermel Moisture Content (`RothMC`)](#2-rothermel-moisture-content)
3. [Surface Fuel Consumption (`SFC`)](#3-surface-fuel-consumption)
4. [Ladder Fuels (`LadderFuels`)](#4-ladder-fuels)
5. [ConPyro (Main Module)](#5-conpyro-main-module)

---

## 1. Moisture Content

**Component class:** `MoistureContent`  
**Initializer:** `initialize_mc()`  
**Runner:** `run_mc()`

### Always Required

| Parameter     | Type                           | Description                                       |
|---------------|--------------------------------|---------------------------------------------------|
| `stand_type`  | `int`, `str`, or `np.ndarray`  | Stand type code or string (`D`, `DF`, `MW`, `P`, `S` or 1–5) |
| `ffmc`        | numeric                        | CFFWIS Fine Fuel Moisture Code (clipped to 80–97) |
| `dmc`         | numeric                        | CFFWIS Duff Moisture Code (clipped to 10–200)     |

### Conditional Parameters

#### Season (`season`)
Determines the seasonal coefficient set for the stand-adjusted moisture content model.

| Combination | Parameters Required | Notes |
|-------------|---------------------|-------|
| **A — Provide `season` directly** | `season` (`int`, `str`, or `np.ndarray`) | Valid codes: 1–4 or `'Sp'`, `'Sp-Su'`/`'T'`, `'Su'`, `'F'` |
| **B — Derive from date** | `wx_date` (`int` or `str`, format `YYYYMMDD`) | Season is calculated from the month/day portion of `wx_date` using built-in cutoff dates |

> If both `season` and `wx_date` are `None`, a `ValueError` is raised.

#### Density (`density`)
Stand density class used in the moisture content model.

| Combination | Parameters Required | Notes |
|-------------|---------------------|-------|
| **A — Provide `density` directly** | `density` (`int`, `str`, or `np.ndarray`) | Valid codes: 1–3 or `'L'`, `'M'`, `'H'` |
| **B — Derive from canopy cover** | `cc` (numeric, 0–100) | Density is binned from canopy cover percentage |

> If both `density` and `cc` are `None`, a `ValueError` is raised.

### Optional

| Parameter    | Type  | Default        | Description |
|--------------|-------|----------------|-------------|
| `model_mcsa` | `str` | `'corrected'`  | Moisture content model variant (`'corrected'` or `'original'`) |

### Summary — Minimum Required Combinations

```
# Combination 1: season + density supplied directly
stand_type, ffmc, dmc, season, density

# Combination 2: season supplied, density derived from cc
stand_type, ffmc, dmc, season, cc

# Combination 3: season derived from wx_date, density supplied
stand_type, ffmc, dmc, wx_date, density

# Combination 4: both season and density derived
stand_type, ffmc, dmc, wx_date, cc
```

---

## 2. Rothermel Moisture Content

**Component class:** `RothMC`  
**Initializer:** `initialize_roth()`  
**Runner:** `get_roth_mc()`

This component is only invoked when `cfo_model = 10` (CFIS model) in ConPyro.

### Always Required

All parameters below are mandatory — there are no conditional alternates.

| Parameter   | Type                           | Description                                               |
|-------------|--------------------------------|-----------------------------------------------------------|
| `wx_date`   | `int` or `str`                 | Weather observation date (`YYYYMMDD` or `YYYY-MM-DD`)     |
| `time`      | `int`                          | Time of observation in HHMM format (0–2400)               |
| `temp`      | numeric                        | Air temperature (°C)                                      |
| `rh`        | numeric                        | Relative humidity (%, clipped to 0–100)                   |
| `aspect`    | numeric                        | Slope aspect in degrees (0–360)                           |
| `slope`     | numeric                        | Slope steepness (%)                                       |
| `cc`        | numeric                        | Canopy cover (%, clipped to 0–100)                        |
| `site_elev` | numeric                        | Elevation of the site (m)                                 |
| `stn_elev`  | numeric                        | Elevation of the weather station (m)                      |

### Summary — Minimum Required Combination

```
wx_date, time, temp, rh, aspect, slope, cc, site_elev, stn_elev
```

---

## 3. Surface Fuel Consumption

**Component class:** `SFC`  
**Initializer:** `initialize_sfc()`  
**Runner:** `run_sfc(cfo_model)`

### Always Required

| Parameter  | Type                           | Description                                                |
|------------|--------------------------------|------------------------------------------------------------|
| `ffmc`     | numeric                        | Fine Fuel Moisture Code                                    |
| `bui`      | numeric                        | Buildup Index (clipped to 15–90)                           |
| `ffl`      | numeric                        | Forest floor fuel load (kg/m², clipped to 1–5)             |
| `wfl`      | numeric                        | Woody fuel load (kg/m², clipped to 1–5)                    |
| `gfl`      | numeric                        | Grass fuel load (kg/m²)                                    |
| `pct_cnfr` | numeric                        | Percent conifer (%, 0–100; defaults to 50 if `NaN`/`None`) |

### Conditional Parameters

#### Fuel Type (`fuel_type`)
Required only when the CFIS model (`cfo_model = 10`) is in use. Used to compute
FBP-based surface fuel consumption. When not using CFIS, `fuel_type` may be set to `None`
(internally replaced by the reference integer array).

| Combination | Parameters Required | Notes |
|-------------|---------------------|-------|
| **A — CFIS active (`cfo_model = 10`)** | `fuel_type` (`int`, `str`, or `np.ndarray`) | CFFBPS alphanumeric fuel type code (e.g. `'C1'`–`'S3'`, `'NF'`, `'WA'`, or numeric 1–20) |
| **B — Non-CFIS models** | `fuel_type = None` | No FBP SFC is calculated; De Groot FFC is used instead |

### Summary — Minimum Required Combinations

```
# Standard (non-CFIS)
ffmc, bui, ffl, wfl, gfl, pct_cnfr
# fuel_type may be None

# CFIS (cfo_model = 10)
fuel_type, ffmc, bui, ffl, wfl, gfl, pct_cnfr
```

---

## 4. Ladder Fuels

**Component class:** `LadderFuels`  
**Initializer:** `initialize_ladder_fuels()`  
**Runner:** `run_ladder_fuels()`

Ladder fuel processing is skipped entirely if **any** of the core ladder fuel
parameters below are `None`.

### Always Required (Core Ladder Parameters)

| Parameter         | Type    | Description                                                      |
|-------------------|---------|------------------------------------------------------------------|
| `sfc`             | numeric | Estimated surface fuel consumption (kg/m²)                       |
| `ht_midstry_live` | numeric | Mean height of live midstory trees / saplings (m)                |
| `ht_midstry_dead` | numeric | Mean height of dead midstory trees / saplings (m)                |
| `cbh_ovrstry`     | numeric | Live overstory canopy base height (m, clipped minimum 0.5)       |
| `cbh_midstry`     | numeric | Mean live canopy base height of midstory trees (m)               |
| `cfl_midstry`     | numeric | Midstory canopy fuel load (kg/m²)                                |
| `dead_branch_fl`  | numeric | Estimated biomass of dead branches ≤ 1 cm diameter (kg/m²)       |

### Conditional Parameters

#### Foliar Moisture Content (`fmc`)
Controls how the foliar moisture content of live midstory trees is determined.

| Combination | Parameters Required | Notes |
|-------------|---------------------|-------|
| **A — Provide `fmc` directly** | `fmc` (numeric, 0–100) | Used as-is; no geographic inputs needed |
| **B — Derive from date + geography** | `wx_date` + `lat` + `long` + `elevation` | `wx_date` (`int`, `YYYYMMDD`). `d0` and `dj` are calculated internally from `wx_date` and geographic position |
| **C — Derive from d0/dj + geography** | `d0` + `dj` + `lat` + `long` + `elevation` | Provide pre-computed `d0` (date of minimum FMC) and `dj` (Julian date) directly. `lat`, `long`, and `elevation` are still needed for normalized-latitude calculations. `wx_date` is not required |

> If `fmc` is `None` **and** both `wx_date` and `d0`/`dj` are `None`, a `ValueError` is raised.
>
> When `fmc` is `None`, `lat`, `long`, and `elevation` are always required regardless
> of whether `wx_date` or `d0`/`dj` is used.

### Summary — Minimum Required Combinations

```
# Combination 1: fmc provided directly
sfc, ht_midstry_live, ht_midstry_dead, cbh_ovrstry, cbh_midstry,
cfl_midstry, dead_branch_fl, fmc

# Combination 2: fmc derived from wx_date + geography
sfc, ht_midstry_live, ht_midstry_dead, cbh_ovrstry, cbh_midstry,
cfl_midstry, dead_branch_fl, wx_date, lat, long, elevation

# Combination 3: fmc derived from d0/dj + geography
sfc, ht_midstry_live, ht_midstry_dead, cbh_ovrstry, cbh_midstry,
cfl_midstry, dead_branch_fl, d0, dj, lat, long, elevation
```

---

## 5. ConPyro (Main Module)

**Component class:** `ConPyro` (inherits `MoistureContent`, `RothMC`, `SFC`, `LadderFuels`)  
**Initializer:** `initialize()`  
**Runner:** `run_conpyro()`

ConPyro orchestrates all component modules in a fixed processing pipeline:

1. `process_mc_sa()` → Moisture Content
2. `process_roth_mc()` → Rothermel MC *(only when `cfo_model = 10`)*
3. `process_sfc()` → Surface Fuel Consumption *(skipped if `sfc` override supplied)*
4. `process_ladder_fuels()` → Ladder Fuels *(skipped if any core ladder param is `None`)*
5. `process_cfo()` → Crown Fire Occurrence
6. `process_ros()` → Rate of Spread
7. `process_fire_metrics()` → Fire Metrics (fire type, CFB, CFL, CFC, TFC)
8. `process_intensity()` → Fire Intensity (SFI, CFI, HFI)

### Always Required

| Parameter                          | Type                           | Description                                              |
|------------------------------------|--------------------------------|----------------------------------------------------------|
| `cfo_model`                        | `int` or `np.ndarray`          | Crown Fire Occurrence model (1, 2, 3, 4, 5, or 10)      |
| `sros_model`                       | `int` or `np.ndarray`          | Surface ROS model (1, 2, 3, 4, 12, 13, or 20)           |
| `cros_model`                       | `int` or `np.ndarray`          | Crown ROS model (1 or 2)                                 |
| `smooth_ros`                       | `bool`                         | Whether to apply ROS smoothing                           |
| `model_terrain_effects_on_wind`    | `bool`                         | Whether to model terrain effects on wind                 |
| `model_terrain_effects_on_ffmc`    | `bool`                         | Whether to apply terrain-adjusted FFMC                   |
| `stand_type`                       | `int`, `str`, or `np.ndarray`  | Stand type code (`D`, `DF`, `MW`, `P`, `S` or 1–5)      |
| `cbd`                              | numeric                        | Canopy Bulk Density (kg/m³)                              |
| `cfl_ovrstry`                      | numeric                        | Overstory Canopy Fuel Load (kg/m²)                       |
| `fsg`                              | numeric                        | Fuel Strata Gap (m)                                      |
| `ffl`                              | numeric                        | Forest floor fuel load (kg/m²)                           |
| `wfl`                              | numeric                        | Woody fuel load (kg/m²)                                  |
| `gfl`                              | numeric                        | Grass fuel load (kg/m²)                                  |
| `ws`                               | numeric                        | Wind speed (km/h)                                        |
| `wd`                               | numeric                        | Wind direction (degrees)                                 |
| `wx_date`                          | `int` or `str`                 | Weather observation date (`YYYYMMDD`)                    |
| `ffmc`                             | numeric                        | Fine Fuel Moisture Code                                  |
| `dmc`                              | numeric                        | Duff Moisture Code                                       |
| `bui`                              | numeric                        | Buildup Index                                            |

### Conditional Parameters

#### Season (`season`)
*(Passed to Moisture Content component)*

| Combination | Parameters Required | Notes |
|-------------|---------------------|-------|
| **A** | `season` (1–4 or `'Sp'`, `'T'`, `'Su'`, `'F'`) | Provided directly |
| **B** | `wx_date` | Season derived from date; `wx_date` is already always required at the ConPyro level |

#### Density (`density`)
*(Passed to Moisture Content component)*

| Combination | Parameters Required | Notes |
|-------------|---------------------|-------|
| **A** | `density` (1–3 or `'L'`, `'M'`, `'H'`) | Provided directly |
| **B** | `cc` (numeric, 0–100) | Density derived from canopy cover |

> If both `density` and `cc` are `None`, a `ValueError` is raised.

#### Slope & Aspect (`slope`, `aspect`)
Required when **either** terrain effect flag is `True`.

| Condition | Parameters Required |
|-----------|---------------------|
| `model_terrain_effects_on_wind = True` | `slope`, `aspect` |
| `model_terrain_effects_on_ffmc = True` | `slope`, `aspect` |
| Both flags `False` | `slope` and `aspect` may be `None` (but see CFIS below) |

> When `model_terrain_effects_on_wind = True`, ConPyro computes slope factor, ISZ, ISF,
> and effective wind speed/direction (WSV/RAZ). When `False`, `ws` and `wd` are used directly.

#### CFIS Model Parameters (`cfo_model = 10`)
When any element of `cfo_model` equals 10 (CFIS), the following **additional** parameters
are required. These feed the Rothermel MC component and the CFIS logit.

| Parameter   | Type              | Description                                |
|-------------|-------------------|--------------------------------------------|
| `time`      | `int`             | Time of observation (HHMM, 0–2400)         |
| `temp`      | numeric           | Air temperature (°C)                       |
| `rh`        | numeric           | Relative humidity (%)                      |
| `cc`        | numeric           | Canopy cover (%)                           |
| `site_elev` | numeric           | Site elevation (m)                         |
| `stn_elev`  | numeric           | Weather station elevation (m)              |

> `slope` and `aspect` are also required by the Rothermel MC component when `cfo_model = 10`.
> If any of `cc`, `time`, `temp`, `rh`, `stn_elev`, `site_elev` are `None` when CFIS is
> active, a `ValueError` is raised.

#### SFC Override (`sfc`)
An optional pre-computed surface fuel consumption value.

| Combination | Parameters Required | Notes |
|-------------|---------------------|-------|
| **A — Override** | `sfc` (numeric) | Skips internal SFC computation; value used directly |
| **B — Compute internally** | `sfc = None` | SFC is calculated from `ffmc`, `bui`, `ffl`, `wfl`, `gfl`, and optionally `fuel_type`/`pct_cnfr` |

#### SFC Sub-Parameters (`fuel_type`, `pct_cnfr`)
*(Passed to SFC component)*

| Combination | Parameters Required | Notes |
|-------------|---------------------|-------|
| **A — Non-CFIS** | `fuel_type = None`, `pct_cnfr = None` | Safe to omit; De Groot FFC method is used |
| **B — CFIS active** | `fuel_type`, `pct_cnfr` | Required for FBP SFC calculation when `cfo_model = 10` |

#### Ladder Fuel Parameters
*(Passed to Ladder Fuels component)*

All six core ladder parameters must be provided for ladder fuel processing to occur.
If **any** is `None`, the entire ladder fuel step is skipped.

| Parameter         | Type              | Description                                            |
|-------------------|-------------------|--------------------------------------------------------|
| `ht_midstry_live` | numeric or `None` | Mean height of live midstory trees (m)                 |
| `ht_midstry_dead` | numeric or `None` | Mean height of dead midstory trees (m)                 |
| `cbh_ovrstry`     | numeric or `None` | Overstory canopy base height (m)                       |
| `cbh_midstry`     | numeric or `None` | Midstory canopy base height (m)                        |
| `cfl_midstry`     | numeric or `None` | Midstory canopy fuel load (kg/m²)                      |
| `dead_branch_fl`  | numeric or `None` | Dead branch biomass ≤ 1 cm diameter (kg/m²)            |

When ladder fuels are active, **foliar moisture content** (`fmc`) follows the same
conditional logic as the standalone Ladder Fuels component:

| Combination | Parameters Required | Notes |
|-------------|---------------------|-------|
| **A** | `fmc` (numeric, 0–100) | Provided directly |
| **B** | `wx_date` + `lat` + `long` + `elevation` | FMC derived from date and geography |
| **C** | `d0` + `dj` + `lat` + `long` + `elevation` | Pre-computed d0/dj with geography; `wx_date` is not required |

> If `fmc` is `None` and insufficient geographic/date parameters are provided, a
> `ValueError` is raised.

### Summary — Minimum Required Combinations for `ConPyro.initialize()`

#### Minimal (no terrain effects, no CFIS, no ladder fuels, no SFC override)

```python
ConPyro.initialize(
    cfo_model=1,              # Non-CFIS model
    sros_model=1,
    cros_model=1,
    smooth_ros=False,
    model_terrain_effects_on_wind=False,
    model_terrain_effects_on_ffmc=False,
    season=3,                 # or None if wx_date is used
    density=2,                # or None if cc is used
    stand_type='S',
    cbd=0.15,
    cfl_ovrstry=1.0,
    fsg=5.0,
    ffl=2.0, wfl=1.5, gfl=0.5,
    ws=15, wd=270,
    slope=None, aspect=None,  # Not needed when terrain flags are False
    wx_date=20250715,
    ffmc=90, dmc=40, bui=60,
    fuel_type=None, pct_cnfr=None,
    ht_midstry_live=None, ht_midstry_dead=None,
    cbh_ovrstry=None, cbh_midstry=None,
    cfl_midstry=None, dead_branch_fl=None,
    fmc=None,
    sfc=None,                 # Computed internally
)
```

#### With terrain effects enabled

```python
# Add slope and aspect; set one or both terrain flags to True
slope=25, aspect=180,
model_terrain_effects_on_wind=True,
model_terrain_effects_on_ffmc=True,
```

#### With CFIS model (cfo_model = 10)

```python
# Additional required parameters:
cfo_model=10,
time=1400,
temp=25.0,
rh=35.0,
cc=60.0,
site_elev=800,
stn_elev=600,
slope=25, aspect=180,        # Also required by Rothermel MC
fuel_type='C2',              # Required for FBP SFC
pct_cnfr=80,                 # Required for FBP SFC
```

#### With ladder fuels and FMC from geography

```python
# Core ladder parameters (all must be non-None):
ht_midstry_live=4.0,
ht_midstry_dead=3.0,
cbh_ovrstry=8.0,
cbh_midstry=2.0,
cfl_midstry=0.3,
dead_branch_fl=0.1,

# FMC option B — derived from geography:
fmc=None,
lat=52.0, long=-120.0, elevation=900,
wx_date=20250715,            # Already required at ConPyro level
# (d0 and dj are optional overrides)
```

#### With ladder fuels and FMC provided directly

```python
ht_midstry_live=4.0,
ht_midstry_dead=3.0,
cbh_ovrstry=8.0,
cbh_midstry=2.0,
cfl_midstry=0.3,
dead_branch_fl=0.1,
fmc=95.0,                    # Provided directly — no lat/long/elevation needed
```

---

## Quick Reference — All Parameters by Component

| Parameter | ConPyro | Moisture Content | Rothermel MC | SFC | Ladder |
|-----------|:-------:|:----------------:|:------------:|:---:|:------:|
| `cfo_model` | ● | | | | |
| `sros_model` | ● | | | | |
| `cros_model` | ● | | | | |
| `smooth_ros` | ● | | | | |
| `model_terrain_effects_on_wind` | ● | | | | |
| `model_terrain_effects_on_ffmc` | ● | | | | |
| `season` | ● | ◐ | | | |
| `density` | ● | ◐ | | | |
| `stand_type` | ● | ● | | | |
| `ffmc` | ● | ● | | ● | |
| `dmc` | ● | ● | | | |
| `bui` | ● | | | ● | |
| `wx_date` | ● | ◐ | ◑ | | ◐ |
| `cc` | ◐ | ◐ | ◑ | | |
| `model_mcsa` | | ○ | | | |
| `ws` | ● | | | | |
| `wd` | ● | | | | |
| `slope` | ◐ | | ◑ | | |
| `aspect` | ◐ | | ◑ | | |
| `cbd` | ● | | | | |
| `cfl_ovrstry` | ● | | | | |
| `fsg` | ● | | | | |
| `ffl` | ● | | | ● | |
| `wfl` | ● | | | ● | |
| `gfl` | ● | | | ● | |
| `fuel_type` | ◐ | | | ◐ | |
| `pct_cnfr` | ◐ | | | ● | |
| `time` | ◑ | | ● | | |
| `temp` | ◑ | | ● | | |
| `rh` | ◑ | | ● | | |
| `site_elev` | ◑ | | ● | | |
| `stn_elev` | ◑ | | ● | | |
| `sfc` | ○ | | | | ● |
| `ht_midstry_live` | ◐ | | | | ● |
| `ht_midstry_dead` | ◐ | | | | ● |
| `cbh_ovrstry` | ◐ | | | | ● |
| `cbh_midstry` | ◐ | | | | ● |
| `cfl_midstry` | ◐ | | | | ● |
| `dead_branch_fl` | ◐ | | | | ● |
| `fmc` | ◐ | | | | ◐ |
| `lat` | ◐ | | | | ◐ |
| `long` | ◐ | | | | ◐ |
| `elevation` | ◐ | | | | ◐ |
| `d0` | ○ | | | | ○ |
| `dj` | ○ | | | | ○ |

**Legend:**
- ● = Always required
- ◐ = Conditionally required (depends on other parameter values)
- ◑ = Required only when `cfo_model = 10` (CFIS)
- ○ = Optional (has default or can be derived)





