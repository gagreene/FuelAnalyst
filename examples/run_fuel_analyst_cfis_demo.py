# -*- coding: utf-8 -*-
"""
Standalone fuel_analyst() -> FBP fuel typing -> run_conpyro() (CFIS) demonstration.

Companion to ``examples/run_fuel_analyst_conpyro_demo.py``, which exercises ConPyro's
default fire-behavior model (``cfo_model=5``). This script instead exercises the CFIS
(Crown Fire Initiation and Spread) model (``cfo_model=10``), which - unlike the default
model - requires a real CFFBPS fuel type: ``src/fuel_analyst/_vendor/conpyro/conpyro.py``
documents ``fuel_type``/``pct_cnfr`` as "SFC (CFIS only) - set to None if not using CFIS",
and ``_single_run_fire_behavior()`` only passes a real fuel-type array through when every
plot in a weather-date batch has one (any missing value drops the whole batch to
``fuel_type=None``, and ``run_conpyro()`` logs each affected plot in the ConPyro Fire Behavior
column of ``run_conpyro_errors.csv``).

Runs against committed data alone: ``examples/data/Survey123_Data`` (raw plot data),
``examples/data/fbp_fuel_typing/fbp_prep_df.csv`` (user-filled BEC/VRI fields feeding
BCWFT2018 fuel typing), and ``examples/data/weather/conpyro_df_wx.csv`` (real 2005-2024
NRCAN weather). No NRCAN weather archive access, no rasterio, and no environment-split
concerns are needed - just an environment with FuelAnalyst and its optional ``fofem`` extra
(pyfofem) installed.

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
#: dataset's 20 plots). Its plot columns are stale (its fbp_fuel_type is unpopulated and it
#: has no sros_model or surface_fuel_type), so step 3 below replaces them with the fresh
#: FBP-typed ConPyro table and keeps only its weather columns.
#: Regenerate via examples/weather_pipeline/run_weather_conpyro_pipeline.py's `--stage
#: weather --stage merge` and copy the resulting output here.
WEATHER_MERGED_PATH = os.path.join(EXAMPLES_DIR, 'data', 'weather', 'conpyro_df_wx.csv')

#: CFIS-only requirement (see module docstring): a literal time of day of the weather
# observations. The weather data are representative of 12 noon LST.
#: 1200 (12pm)
CFIS_TIME_HHMM = 1200


def _refresh_weather_inputs(weather_path: str, fuel_path: str, output_path: str) -> None:
    """
    Attach current plot attributes, model assignments, and FBP fuel types to committed example weather.

    The committed weather file predates automatic surface-model assignment, so its plot columns are replaced
    with those of the freshly typed ConPyro table. The refresh carries sros_model, which run_conpyro() requires
    under its default sros_model='use_csv', and surface_fuel_type, which it reads when present to apply the
    category-specific calculations (forest-floor BY consumption and the shrub contribution to the grass fuel load).

    :param weather_path: Existing weather-merged example CSV.
    :param fuel_path: Fresh FBP-typed ConPyro table (conpyro_df_fbp.csv) generated from the example data.
    :param output_path: Destination CSV used by the fire-model stage.
    :return: None. Writes refreshed plot/weather rows to output_path without modifying either input file.
    """
    weather = pd.read_csv(weather_path, low_memory=False)
    fuels = pd.read_csv(fuel_path, low_memory=False)
    missing = set(weather['unique_id']) - set(fuels['unique_id'])
    if missing:
        raise ValueError(f'Weather rows have no current fuel inputs for plots: {sorted(missing)}')
    weather = weather.drop(columns=[column for column in fuels if column != 'unique_id' and column in weather])
    merged = weather.merge(fuels, on='unique_id', how='left', validate='many_to_one')
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    merged.to_csv(output_path, index=False)


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

    print('\n=== Step 3: attach current plot inputs and FBP fuel types to the committed weather ===')
    cfis_input_path = os.path.join(CONPYRO_DIR, 'conpyro_df_wx_fbp.csv')
    _refresh_weather_inputs(
        WEATHER_MERGED_PATH, os.path.join(FBP_FUEL_TYPING_DIR, 'conpyro_df_fbp.csv'), cfis_input_path
    )

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
