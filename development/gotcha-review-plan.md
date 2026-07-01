# Gotcha Review Plan

Systematic review of known codebase gotchas from `docs/CODEBASE.md`.

**Excluded (confirmed non-issues):**
- Input folder/file naming — hardcoded by Survey123 convention, intentional
- Basal-area weighted means — correct scientific approach, not a bug

---

## Gotchas to Review

### G1 — `_date` parsing silently produces no `unique_id`

**Location:** `helper.get_unique_id()` (and wherever `_date` is parsed)

**Issue:** If `_date` doesn't match `'%m/%d/%Y %H:%M'` or `'%m/%d/%Y %H:%M:%S %p'`, the function silently returns no ID and no error is raised. Downstream deduplication then operates on blank or missing IDs.

**Review steps:**
- [x] Read `helper.py` — find `get_unique_id()` and all `_date` parse calls
- [x] Check what happens downstream when `unique_id` is blank/missing
- [x] Determine: is a warning/error appropriate on parse failure?
- [x] Fix or document as acceptable

**Resolution:** Two bugs fixed in `helper.py:get_unique_id()`:
1. `sort_values(by='_date')` sorted lexicographically (month-first strings ≠ chronological) → now sorts by parsed datetime so `keep='last'` correctly retains the most recent resurvey entry.
2. Failed parse silently printed a message then crashed with `KeyError: 'year'` → now raises `ValueError` with sample bad values.
Unused `datetime` import also removed.

---

### G2 — `unique_id` deduplication is per-form, not cross-form

**Location:** `helper.get_unique_id()`, called independently per form

**Issue:** If the same plot is re-surveyed in the same year, only the most recent entry is kept per form. But there's no check that the same record was kept across all forms — one form might retain rev-1, another retains rev-2.

**Review steps:**
- [x] Trace how `unique_id` dedup is applied across all five form CSVs
- [x] Check whether the "keep last by `_date`" logic is identical in each form's processing
- [x] Determine: is cross-form consistency enforced at merge time?
- [x] Fix or document expected behaviour

**Resolution:** No code bug. All five `survey_0.csv` forms call the same `helper.get_unique_id()` — dedup logic is identical across forms. `sapling_1.csv` and `tree_plot_2.csv` are child repeat records that don't need independent dedup; they're linked to the already-deduped parent plot via `_calc_tree_density(df, tree_df)`. Residual risk: a partial resurvey (crew resubmits only one form) produces cross-form inconsistency, but this is a field data issue not addressable in code.

---

### G3 — Form processing silently skips missing folders

**Location:** `fuel_analyst.py` — form loop with `if not os.path.exists(in_path): continue`

**Issue:** If a form folder doesn't exist, the form is silently skipped — even if `form_select` indicates it should be processed. No warning is raised; output columns are simply absent from `master_fuel_df.csv`.

**Review steps:**
- [x] Read the form-loop section of `fuel_analyst.py`
- [x] Check if `form_select` check and folder existence check are consistent
- [x] Determine: should a warning be raised when a selected form's folder is missing?
- [x] Fix or document as acceptable

**Resolution:** Logic was sound but warning quality was poor. Moved `form_select` mask computation before the folder existence check so the warning can name affected plots. Missing folder + plots selected → warning with plot IDs. Missing folder + no plots selected → silent skip. No spurious warnings for unused forms.

---

### G4 — `keep_columns` is additive and order-dependent

**Location:** `fuel_analyst.py` — `keep_columns` list built across component calls

**Issue:** Components append to `keep_columns` in order. Skipped components leave gaps. ConPyro/FOFEM stand attributes are injected into `stand_summary_params` via `dict.update()` **before** tree processing, so those columns are computed inside `trees.py` regardless of whether ConPyro/FOFEM output is requested.

**Review steps:**
- [x] Trace `keep_columns` construction in `fuel_analyst.py` from start to end
- [x] Identify which columns are always present vs conditionally present
- [x] Check whether ConPyro/FOFEM attrs computed in `trees.py` are always calculated even when not needed
- [x] Determine: is unnecessary computation a problem? Should `keep_columns` be validated at end?
- [x] Fix or document

**Resolution:** Real bug found — `stand_summary_params.update()` and `woody_debris_params['woody_debris_classes'].update()` mutated the module-level default dicts in-place. A second call with `gen_conpyro_df=False` would still compute ConPyro attributes because the defaults were permanently polluted. Fixed by shallow-copying defaults before mutation (including the nested `woody_debris_classes` dict). `keep_columns` being additive with no warning is an acceptable design choice — not changed.

---

### G5 — ConPyro hard-requires all four form folders

**Location:** `fuel_analyst.py` — `gen_conpyro_df=True` path

**Issue:** When `gen_conpyro_df=True`, code raises `FileNotFoundError` if any of the four form folders are missing. This is the only hard failure in the pipeline. The error message may not clearly identify which folder is missing or why it's required.

**Review steps:**
- [x] Read the ConPyro folder-check block in `fuel_analyst.py`
- [x] Check the error message quality — does it name the missing folder?
- [x] Determine: is this the right failure mode, or should it fall back gracefully per-plot?
- [x] Fix or document

**Resolution:** Two bugs found. (1) List comprehension used `form` as its own variable, shadowing the outer loop variable — `in_path` was fixed to one folder and checked against all form names, so missing_forms was always either empty or all-four. (2) The outer `for` loop was redundant. Fixed by removing the loop and building `missing_forms` correctly with per-form paths in a single comprehension. Hard-fail on missing forms is the right behaviour for ConPyro.

---

### G6 — `sys.path` injection blocks pip installability

**Location:** Every top-level module (`fuel_analyst.py`, `run_conpyro.py`, `extract_nrcan_wx.py`, etc.)

**Issue:** Each module injects `../../` into `sys.path` at import time to enable absolute imports. This works only when executed from the repo root. The package cannot be installed via pip.

**Review steps:**
- [x] List all modules that perform `sys.path` injection
- [x] Check if a `pyproject.toml` or `setup.py` exists
- [x] Determine scope of fix: add `pyproject.toml` + remove injections, or document as known limitation
- [x] Note: fixing this likely requires testing that all imports still resolve correctly

**Resolution:** Full packaging refactor completed. 8 files had sys.path injection — all removed. `src/fuel_analyst/` is now a proper src-layout package. `pyproject.toml` created at repo root (setuptools, src layout, deps audited from requirements.txt). `conpyro` submodule got its own `pyproject.toml` for pip-installability. `flame_components` and `bcwft2018` vendored into `src/fuel_analyst/_vendor/` (single-file, pure computation, no data deps). All `from src.fuel_analyst...` imports converted to relative. All `try/except ImportError: import helper` fallbacks cleaned to plain `from . import helper`. `MANIFEST.in` created for package data. See `docs/pypi-packaging-plan.md` for full plan and verification steps.

---

### G7 — `cbd` special-case branching is pervasive

**Location:** `trees._calc_stand_attributes()` and anywhere that iterates over tree attributes

**Issue:** CBD has no simple `_ha` column — it's derived from `cfl_cnbe_ha / crown_depth`. Every attribute loop has a parallel `att != 'cbd'` branch that recalculates it. Adding new CBD handling in any location requires updating both branches.

**Review steps:**
- [x] Find all `att != 'cbd'` (or equivalent) branches in `trees.py`
- [x] Verify each branch computes CBD correctly and consistently
- [x] Check if the CBD formula is the same in all branches
- [x] Determine: can this be refactored into a helper function to reduce duplication?
- [x] Fix or document

**Resolution:** No bug. Three CBD special-case locations found (`unweight_value()`, summary-level branch, class-level branch). Both `att != 'cbd'` branches are identical: sum `tree_cfl_cnbe_ha`, call `unweight_value` to divide by mean crown depth, assign with no metric suffix. Formula is consistent. Optional refactor: extract the CBD branch into a helper to reduce ~14 duplicated lines, but not required for correctness.

---

### G8 — Decay class asymmetry in three locations

**Location:** `trees._calc_tree_missing_heights()`, `trees._calc_tree_biomass()`, mask in `trees._calc_tree_fofem_attributes()`

**Issue:** Conifer "dead" threshold = decay class ≥6 (out of 9); broadleaf "dead" threshold = decay class ≥5 (out of 6). This appears in three separate places and must stay in sync. No shared constant or helper enforces the thresholds.

**Review steps:**
- [x] Find all three locations in `trees.py`
- [x] Verify all three use the same threshold values (conifer ≥6, broadleaf ≥5)
- [x] Determine: should thresholds be defined as module-level constants to enforce sync?
- [x] Fix or document

**Resolution:** Only two threshold locations exist (not three — `_calc_tree_fofem_attributes` uses `tree_status` L/D, not decay thresholds; CODEBASE.md was inaccurate). Both locations were consistent. Promoted thresholds to module-level constants `_DEAD_DECAY_THRESHOLD_CONIFER = 6` and `_DEAD_DECAY_THRESHOLD_BROADLEAF = 5` in `trees.py`, replacing all four hardcoded values. Single source of truth now enforces sync.

---

### G9 — FOFEM outputs in US units, everything else SI

**Location:** `components/fofem_attributes.py`

**Issue:** `fofem_tree_df` uses acres, inches, feet; `fofem_consumption_df` uses tons/acre. These are the only unit conversions in the codebase. Column names don't indicate units; downstream users relying on consistent SI units will get incorrect values.

**Review steps:**
- [x] Read `fofem_attributes.py` — verify all US unit conversions are correct
- [x] Check if output column names document their units (e.g. `_ac`, `_in`, `_ft`, `_ton_ac`)
- [x] Determine: should column names or a header comment flag the unit system?
- [x] Fix or document

**Resolution:** Two correctness bugs found in `gen_fofem_tree_df`. `TreeHeight` and `CrownBaseHeight` used `/ 3.28084` (feet→m) instead of `* 3.28084` (m→feet) — heights were off by a factor of ~10.76. All other conversions correct (`/ 2.54` cm→in, `/ 2.47105` ha→acre, `* 4.46089561` kg/m²→ton/ac, `/ 2.54` cm→in for DuffDepth). Column names are FOFEM-mandated so no unit suffixes possible; added explicit US unit documentation to `gen_fofem_tree_df` docstring.

---

### G10 — Dead saplings have `tree_cbh = NaN`

**Location:** `trees.py` ~line 1378 — sapling merge block

**Issue:** Dead saplings merged from `sapling_df` into `tree_df` have `tree_cbh = np.nan` because only live saplings carry `sapling_live_cbh`. CBH-dependent calculations (FSG, crown depth) on dead saplings will always produce NaN, which propagates silently.

**Review steps:**
- [x] Read the sapling merge block in `trees.py`
- [x] Trace which downstream calculations use `tree_cbh` for sapling records
- [x] Determine: should dead saplings be excluded from CBH-dependent calcs explicitly, or assigned a default CBH?
- [x] Check whether NaN propagation affects stand-level aggregations
- [x] Fix or document

**Resolution:** No bug. NaN is correct for dead sapling CBH. `_calc_tree_crown_depth` guards with `tree_status == 'L'` so dead trees always get NaN crown depth regardless. Stand-level CBH/FSG/crown depth aggregations filter to live-only subsets, so dead sapling NaNs never contaminate live-tree means. The gotcha documentation was overcautious.

---

### G11 — Bark char height `444` sentinel is undocumented in code

**Location:** `trees._calc_tree_fire_attributes()` — bark char height conditional

**Issue:** `tree_bark_char_high == 444` triggers the Butler crown fire intensity model instead of the surface fire model. This sentinel is not documented in comments beyond a single inline note. Any post-processing of fire intensity columns must know about this to avoid treating 444 as a real height measurement.

**Review steps:**
- [x] Find the sentinel check in `trees.py`
- [x] Verify the sentinel value is only set by intentional survey data entry (not a calculation artifact)
- [x] Check if output DataFrames expose the raw `444` values in any column
- [x] Determine: should the sentinel be defined as a named constant? Should a separate flag column be added?
- [x] Fix or document

**Resolution:** Two fixes applied. (1) Promoted `444` to module-level constant `_CROWN_FIRE_CHAR_SENTINEL`. (2) Logic bug corrected: sentinel was checked *after* `flame_length = bark_char_high * 1.8`, producing `flame_length = 799.2 m` and astronomical crown fire intensities. Now sentinel is resolved *first* — `bark_char_high` is replaced with `tree_ht` before flame length is calculated — so the crown fire model receives a physically meaningful input.

---

### G12 — `run_conpyro` expects pre-merged weather, no ordering enforced

**Location:** `run_conpyro.py` — input DataFrame columns assumed present

**Issue:** Weather columns must be added by `extract_nrcan_wx` → `merge_wx_data` before calling `run_conpyro`. No code enforces this ordering; if weather columns are absent, `run_conpyro` fails at runtime with a column-not-found error rather than a clear dependency error.

**Review steps:**
- [x] Read `run_conpyro.py` — identify all weather columns it reads
- [x] Check if any validation of required columns happens at entry
- [x] Determine: should `run_conpyro` validate required columns at start and raise a clear error?
- [x] Fix or document

**Resolution:** Always-required weather columns: `ws`, `wd`, `ffmc`, `dmc`, `bui` (from `extract_nrcan_wx` → `merge_wx_data`). `temp` and `rh` are `Optional` in ConPyro's `initialize()` and only required when `cfo_model == 10` (CFIS). Conditionally required: any `input_params` key set to `'use_csv'` (`wx_date`, `season`, `time`, `fmc`, `cfo_model`, `sros_model`, `cros_model`) maps to a same-named column in the CSV. Added dynamic validation after reading the CSV: builds the required column list from always-needed wx columns, CFIS-conditional columns, and any `'use_csv'` params, then raises a clear `ValueError` naming the missing columns and the required pipeline step.

---

## Status Summary

| # | Gotcha | Status |
|---|--------|--------|
| G1 | `_date` parsing silently produces no `unique_id` | Done |
| G2 | `unique_id` dedup is per-form, not cross-form | No issue |
| G3 | Form processing silently skips missing folders | Done |
| G4 | `keep_columns` is additive and order-dependent | Done |
| G5 | ConPyro hard-requires all four form folders | Done |
| G6 | `sys.path` injection blocks pip installability | Done |
| G7 | `cbd` special-case branching is pervasive | No issue |
| G8 | Decay class asymmetry in three locations | Done |
| G9 | FOFEM outputs in US units | Done |
| G10 | Dead saplings have `tree_cbh = NaN` | No issue |
| G11 | Bark char height `444` sentinel undocumented | Done |
| G12 | `run_conpyro` expects pre-merged weather | Done |
