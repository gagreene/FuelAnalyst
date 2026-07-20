# Plan: Make FuelAnalyst pip-installable (G6)

## Context

Every top-level module injects `sys.path.insert(0, ...)` to reach both internal modules (`from src.fuel_analyst...`) and 4 git submodule dependencies (`from dependencies...`). This blocks `pip install` and forces running from the repo root. The goal is a standard pip-installable package with proper imports.

---

## Dependency Strategy: Hybrid

| Dependency | Strategy | Rationale |
|-----------|----------|-----------|
| **conpyro** | pip-installable (add pyproject.toml) | Substantial package, src/conpyro/ layout already correct |
| **pyfofem** | pip-installable (already has pyproject.toml) | No changes needed |
| **flame_components** | Vendor into `_vendor/` | Single .py file (779 lines), pure numpy functions, no data files |
| **bcwft2018** | Vendor into `_vendor/` | Single .py file (1983 lines), no runtime data references |

For development: `pip install -e dependencies/conpyro` and `pip install -e dependencies/pyfofem`.
For PyPI publishing (future): publish conpyro and pyfofem to PyPI first, then declare as normal deps.

---

## Implementation Steps

### Step 1: Add pyproject.toml to conpyro submodule

Create `dependencies/conpyro/pyproject.toml` modeled on pyfofem's. Already has `src/conpyro/` layout with `__init__.py`. Declare deps: numpy, pandas. Include `supporting_data/*` as package-data.

### Step 2: Create FuelAnalyst pyproject.toml

```
FuelAnalyst/pyproject.toml
```

- Build system: setuptools
- `[tool.setuptools.packages.find] where = ["src"]`
- Package-data: `supporting_data/*.csv`, `supporting_data/*.json`
- Core deps (audited from requirements.txt): numpy, pandas, scipy, scikit-learn, matplotlib, geopandas, rasterio, pyproj, shapely, python-dateutil, tqdm, joblib
- Optional deps groups: `conpyro` (conpyro, via git URL), `fofem` (pyfofem, via git URL), `all`
- Drop from requirements.txt: shiny, uvicorn, starlette, websockets, h11, h2, hpack, hyperframe, asgiref, htmltools, watchfiles, python-multipart (Shiny web app deps), pip, setuptools, wheel (build tools)

### Step 3: Delete `src/__init__.py`

Makes `src` itself a package → conflicts with src-layout. Must be removed so setuptools finds `fuel_analyst` not `src`.

### Step 4: Vendor flame_components and bcwft2018

- Create `src/fuel_analyst/_vendor/__init__.py`
- Copy `dependencies/flame_components/flame_components.py` → `src/fuel_analyst/_vendor/flame_components.py`
- Copy `dependencies/BC_CFFBPS_FuelTyping_Tool/bcwft2018.py` → `src/fuel_analyst/_vendor/bcwft2018.py`
- Add origin comment header to each vendored file
- Neither file references `__file__` or data dirs — pure computation, safe to vendor

### Step 5: Remove sys.path injection (8 files)

Delete the `import sys` / `pkg_dir` / `sys.path.insert` block from:

| File | Lines |
|------|-------|
| `fuel_analyst.py` | 13-16 |
| `run_conpyro.py` | 14-17 |
| `extract_nrcan_wx.py` | 19-22 |
| `fbp_fuel_type.py` | 14-17 |
| `merge_wx_data.py` | 14-17 |
| `components/fofem_emissions.py` | 14-17 |
| `components/fofem_mortality.py` | 14-17 |
| `components/fofem_gui_emissions.py` | 18-21 |

Also remove `import sys` if unused elsewhere in each file.

### Step 6: Rewrite internal imports (7 files)

All `from src.fuel_analyst.X import Y` → relative imports:

| File | Old | New |
|------|-----|-----|
| fuel_analyst.py | `from src.fuel_analyst.components import helper` | `from .components import helper` |
| fuel_analyst.py | `from src.fuel_analyst.components import plot_attributes as pa` | `from .components import plot_attributes as pa` |
| fuel_analyst.py | (same pattern for trees, cc, wd, conpyro_attributes, fofem_attributes, plants_regen) | (same pattern) |
| run_conpyro.py | `from src.fuel_analyst.components import helper` | `from .components import helper` |
| run_conpyro.py | `from src.fuel_analyst.components import fofem_emissions as fe` (line 502) | `from .components import fofem_emissions as fe` |
| run_conpyro.py | `from src.fuel_analyst.components import fofem_gui_emissions as fe` (line 515) | `from .components import fofem_gui_emissions as fe` |
| run_conpyro.py | `from src.fuel_analyst.components import fofem_mortality as fm` (line 570) | `from .components import fofem_mortality as fm` |
| extract_nrcan_wx.py | `from src.fuel_analyst.components import helper` | `from .components import helper` |
| fbp_fuel_type.py | `from src.fuel_analyst.components import helper` | `from .components import helper` |
| merge_wx_data.py | `from src.fuel_analyst.components import helper` | `from .components import helper` |
| fofem_gui_emissions.py | `from fuel_analyst.components import helper` | `from . import helper` |
| fofem_gui_emissions.py | `from fuel_analyst.components import fwis_moisture_content as mc` | `from . import fwis_moisture_content as mc` |

### Step 7: Rewrite dependency imports (5 files)

| File | Old | New |
|------|-----|-----|
| run_conpyro.py | `from dependencies.conpyro.src.conpyro import conpyro` | `from conpyro import conpyro` |
| run_conpyro.py | `from dependencies.flame_components import flame_components as fc` | `from fuel_analyst._vendor import flame_components as fc` |
| fbp_fuel_type.py | `from dependencies.BC_CFFBPS_FuelTyping_Tool import bcwft2018 as bcwft` | `from fuel_analyst._vendor import bcwft2018 as bcwft` |
| fofem_emissions.py | `from dependencies.pyfofem.src.pyfofem import pyfofem as fofem` | `from pyfofem import pyfofem as fofem` |
| fofem_mortality.py | `from dependencies.pyfofem.src.pyfofem import pyfofem as fofem` | `from pyfofem import pyfofem as fofem` |
| fofem_gui_emissions.py | `from dependencies.pyfofem.src.pyfofem import pyfofem as fofem, TOTAL_DURATION_CONSUMED_VARS, ...` | `from pyfofem import pyfofem as fofem, TOTAL_DURATION_CONSUMED_VARS, EQUATION_VARS, SOIL_HEAT_VARS, DEFAULT_CONSUMPTION_VARS` (pyfofem's `__init__.py` re-exports all 4 constants) |

### Step 8: Clean up try/except fallback imports (6 files)

Replace in canopy_cover.py, conpyro_attributes.py, plants_regen.py, plot_attributes.py, trees.py, woody_debris.py:

```python
# Old:
try:
    from . import helper
except ImportError:
    import helper

# New:
from . import helper
```

### Step 9: Create MANIFEST.in

```
recursive-include src/fuel_analyst/supporting_data *.csv *.json
```

### Step 10: Update helper.get_examples_dir()

The `if __name__ == '__main__'` blocks use `helper.get_examples_dir(os.path.dirname(__file__))` to locate example data. This function likely navigates up from `__file__`. Verify it still works after packaging — `__file__` will still be valid for editable installs but may differ for wheel installs. The examples dir is for development only, so this is acceptable to leave as-is.

---

## Verification

1. `pip install -e dependencies/conpyro && pip install -e dependencies/pyfofem` — deps install
2. `pip install -e ".[all]"` — FuelAnalyst installs
3. `python -c "from fuel_analyst import fuel_analyst; print('OK')"` — import works
4. `python -c "from fuel_analyst.components import helper, trees; print('OK')"` — components work
5. `python -c "from fuel_analyst._vendor import flame_components, bcwft2018; print('OK')"` — vendored work
6. `grep -r "sys.path.insert" src/` — returns nothing
7. `grep -r "from src.fuel_analyst" src/` — returns nothing
8. `grep -r "from dependencies" src/` — returns nothing
9. `python -m build` — builds .whl and .tar.gz

---

## Data File Access (verify at implementation time)

- `extract_nrcan_wx.py` loads `supporting_data/WHSE_...json` via `os.path.dirname(__file__)` — works in editable + wheel installs as long as package-data is declared (covered by pyproject.toml + MANIFEST.in)
- `trees.py:1475` loads `../supporting_data/tree_parameters.csv` via `__file__` — same, works because `__file__` resolves inside site-packages
- `plants_regen.py:204` loads `../supporting_data/plant_photoload.csv` — same

All three are covered by the `supporting_data/*.csv` + `*.json` package-data declaration. Verify after `python -m build` that these files appear in the .whl.

## What NOT to Change

- `if __name__ == '__main__'` blocks — keep for developer convenience
- No CLI entry points — current `__main__` blocks are test routines, not real CLIs
- `dependencies/` submodules — keep conpyro and pyfofem submodules for development (they're also pip deps now). Remove flame_components and BC_CFFBPS submodules only after vendoring is verified.
- Lazy-loading `__init__.py` files — already well-structured, no changes needed

## Commit Strategy

Single atomic commit for Steps 3-9 (all import changes must land together or nothing works). Steps 1-2 can be separate prior commits.
