# -*- coding: utf-8 -*-
"""
Standalone fuel_analyst() -> FBP fuel typing -> run_conpyro() (CFIS) demonstration.

Companion to ``examples/run_fuel_analyst_conpyro_demo.py``, which exercises ConPyro's
default fire-behavior model (``cfo_model=5``). This script instead exercises the CFIS
(Crown Fire Initiation and Spread) model (``cfo_model=10``), which - unlike the default
model - requires a real CFFBPS fuel type: ``dependencies/conpyro/src/conpyro/conpyro.py``
documents ``fuel_type``/``pct_cnfr`` as "SFC (CFIS only) - set to None if not using CFIS",
and ``_single_run_fire_behavior()`` only passes a real fuel-type array through when every
plot in a weather-date batch has one (any missing value silently drops the whole batch to
``fuel_type=None``).

Runs against committed data alone: ``examples/data/Survey123_Data`` (raw plot data),
``examples/data/fbp_fuel_typing/fbp_prep_df.csv`` (user-filled BEC/VRI fields feeding
BCWFT2018 fuel typing), and ``examples/data/weather/conpyro_df_wx.csv`` (real 2005-2024
NRCAN weather). No NRCAN weather archive access, no rasterio, and no environment-split
concerns are needed - just an environment with ``fuel_analyst``'s ``conpyro`` and ``fofem``
optional dependencies installed.

CFIS also requires a literal ``time`` (HHMM) for its Rothermel dead-fuel-moisture
calculation, unlike the default model - the committed weather dataset has no per-scenario
time-of-day value, so a fixed representative time is used here instead (see
:data:`CFIS_TIME_HHMM`). Every other CFIS-specific input (``cc``, ``temp``, ``rh``,
``site_elev``/``stn_elev``, ``slope``, ``aspect``) is already present in the committed
weather-merged dataset.
"""
import copy
import os
import sys

# fuel_analyst isn't pip-installed in every environment this script needs to run
# in. Bootstrap src/ onto sys.path so a plain `python
# examples/run_fuel_analyst_cfis_demo.py` works from any interpreter, regardless
# of PYTHONPATH or how it's invoked.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC_DIR = os.path.join(_REPO_ROOT, 'src')
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

import pandas as pd

EXAMPLES_DIR = os.path.dirname(os.path.abspath(__file__))
IN_DIR = os.path.join(EXAMPLES_DIR, 'data', 'Survey123_Data')
FUEL_ANALYST_RESULTS_DIR = os.path.join(EXAMPLES_DIR, 'results', 'fuel_analyst')
FBP_FUEL_TYPING_DIR = os.path.join(EXAMPLES_DIR, 'results', 'fbp_fuel_typing')
CONPYRO_DIR = os.path.join(EXAMPLES_DIR, 'results', 'conpyro_cfis')

#: User-filled BEC/VRI fields BCWFT2018 fuel typing requires; see docs/CODEBASE.md's
#: Survey123 input-names/identities section and _validate_user_supplied_fbp_fields().
FBP_PREP_DF_PATH = os.path.join(EXAMPLES_DIR, 'data', 'fbp_fuel_typing', 'fbp_prep_df.csv')

#: Checked-in, already weather-merged demo input (real 2005-2024 NRCAN weather for this
#: dataset's 20 plots). Its own fbp_fuel_type column is unpopulated (FBP typing wasn't
#: part of the pipeline that produced it) - overwritten with real values in step 3 below.
#: Regenerate via examples/weather_pipeline/run_weather_conpyro_pipeline.py's `--stage
#: weather --stage merge` and copy the resulting output here.
WEATHER_MERGED_PATH = os.path.join(EXAMPLES_DIR, 'data', 'weather', 'conpyro_df_wx.csv')

#: CFIS-only requirement (see module docstring): a literal time of day, since the
#: committed weather dataset has no per-scenario time-of-day value to pull from CSV.
#: 1400 (2pm) is a representative peak-burn-period time, not survey- or plot-specific.
CFIS_TIME_HHMM = 1400


def main() -> None:
    """
    Run fuel_analyst(), FBP fuel typing, then run_conpyro() with CFIS (cfo_model=10)
    against the committed Survey123 and weather-merged datasets.

    :return: None. Writes fuel_analyst outputs under :data:`FUEL_ANALYST_RESULTS_DIR`,
        FBP fuel typing outputs under :data:`FBP_FUEL_TYPING_DIR`, and ConPyro/FOFEM
        outputs under :data:`CONPYRO_DIR`.
    """
    from fuel_analyst.fuel_analyst import fuel_analyst
    from fuel_analyst.tools.fbp_fuel_type import process_fbp_fuel_type
    from fuel_analyst.run_conpyro import run_conpyro, default_fire_modelling_dict
    from fuel_analyst.components import fofem_units

    print('=== Step 1: fuel_analyst() ===')
    fuel_analyst(
        in_dir=IN_DIR,
        out_dir=FUEL_ANALYST_RESULTS_DIR,
        surface_fire_intensity_model='Byram',
        gen_conpyro_df=True,
        gen_fofem_gui_app_tree_df=False,
        gen_fofem_consume_df=True,
    )

    print('\n=== Step 2: process_fbp_fuel_type() ===')
    process_fbp_fuel_type(
        master_fuel_df_path=os.path.join(FUEL_ANALYST_RESULTS_DIR, 'master_fuel_df.csv'),
        fbp_prep_df_path=FBP_PREP_DF_PATH,
        conpyro_df_path=os.path.join(FUEL_ANALYST_RESULTS_DIR, 'conpyro_df.csv'),
        out_dir=FBP_FUEL_TYPING_DIR,
        season='growing',
    )

    print('\n=== Step 3: apply real FBP fuel types to the committed weather-merged dataset ===')
    fbp_typed_df = pd.read_csv(os.path.join(FBP_FUEL_TYPING_DIR, 'conpyro_df_fbp.csv'))
    fuel_type_by_plot = fbp_typed_df.set_index('unique_id')['fbp_fuel_type'].to_dict()

    weather_df = pd.read_csv(WEATHER_MERGED_PATH, low_memory=False)
    weather_df['fbp_fuel_type'] = weather_df['unique_id'].map(fuel_type_by_plot)

    os.makedirs(CONPYRO_DIR, exist_ok=True)
    cfis_input_path = os.path.join(CONPYRO_DIR, 'conpyro_df_wx_fbp.csv')
    weather_df.to_csv(cfis_input_path, index=False)

    print('\n=== Step 4: run_conpyro() with CFIS (cfo_model=10) ===')
    fire_modelling_params = copy.deepcopy(default_fire_modelling_dict)
    fire_modelling_params['conpyro']['input_params']['cfo_model'] = 10
    fire_modelling_params['conpyro']['input_params']['time'] = CFIS_TIME_HHMM

    run_conpyro(
        out_dir=CONPYRO_DIR,
        in_conpyro_csv_path=cfis_input_path,
        in_tree_csv_path=os.path.join(FUEL_ANALYST_RESULTS_DIR, 'master_tree_df.csv'),
        # fire_modelling_params above still uses default_fire_modelling_dict's
        # fofem_emissions.emissions_units='SI' - must match this filename.
        in_fofem_consume_csv_path=os.path.join(
            FUEL_ANALYST_RESULTS_DIR, fofem_units.consume_filename('SI')
        ),
        fire_modelling_params=fire_modelling_params,
    )


if __name__ == '__main__':
    main()
