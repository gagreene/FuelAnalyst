# -*- coding: utf-8 -*-
"""
Standalone fuel_analyst() -> run_conpyro() demonstration.

Runs the complete FuelAnalyst -> ConPyro -> FOFEM workflow against committed
data alone: ``examples/data/Survey123_Data`` (raw plot data) and
``examples/data/weather/conpyro_df_wx.csv`` (real 2005-2024 NRCAN weather,
already extracted and merged). Plot attributes and surface-model assignments are
refreshed from the current fuel_analyst outputs before modelling. No NRCAN weather archive access, no rasterio,
and no environment-split concerns are needed - just an environment with
FuelAnalyst and its optional ``fofem`` extra (pyfofem) installed.

This intentionally excludes FBP fuel typing and weather extraction/merge
(``src/fuel_analyst/tools/``) - see ``examples/weather_pipeline/
run_weather_conpyro_pipeline.py`` for those, and for regenerating the
committed weather-merged dataset this script reads against fresh/real NRCAN
weather. For a fuller, narrated walkthrough of the coding steps rather than
a runnable demo, see ``examples/tutorial/FuelAnalyst_Tutorial.ipynb``.

Runs ConPyro fire behavior and flame components, FOFEM mortality, and FOFEM
emissions (via pyfofem) - the full default feature set from
``run_conpyro.default_fire_modelling_dict``.
"""
import os
import sys

# fuel_analyst isn't pip-installed in every environment this script needs to run
# in. Bootstrap src/ onto sys.path so a plain `python
# examples/run_fuel_analyst_conpyro_demo.py` works from any interpreter,
# regardless of PYTHONPATH or how it's invoked.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC_DIR = os.path.join(_REPO_ROOT, 'src')
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

EXAMPLES_DIR = os.path.dirname(os.path.abspath(__file__))
IN_DIR = os.path.join(EXAMPLES_DIR, 'data', 'Survey123_Data')
FUEL_ANALYST_RESULTS_DIR = os.path.join(EXAMPLES_DIR, 'results', 'fuel_analyst')
CONPYRO_DIR = os.path.join(EXAMPLES_DIR, 'results', 'conpyro')

#: Checked-in, already weather-merged demo input (real 2005-2024 NRCAN weather for
#: this dataset's 20 plots). Regenerate via examples/weather_pipeline/
#: run_weather_conpyro_pipeline.py's `--stage weather --stage merge` (requires real
#: NRCAN archive access) and copy the resulting output here.
WEATHER_MERGED_PATH = os.path.join(EXAMPLES_DIR, 'data', 'weather', 'conpyro_df_wx.csv')


def _refresh_weather_inputs(weather_path: str, fuel_path: str, output_path: str) -> None:
    """
    Attach current plot attributes and model assignments to committed example weather.

    :param weather_path: Existing weather-merged example CSV.
    :param fuel_path: Fresh conpyro_df.csv generated from the example field observations.
    :param output_path: Destination CSV used by the fire-model stage.
    :return: Write refreshed plot/weather rows without modifying either input file.
    """
    import pandas as pd

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
    Run fuel_analyst() on the committed Survey123 dataset, then run_conpyro()
    against committed weather with freshly generated plot attributes.

    :return: None. Writes fuel_analyst outputs under :data:`FUEL_ANALYST_RESULTS_DIR`
        and ConPyro/FOFEM outputs under :data:`CONPYRO_DIR`.
    """
    from fuel_analyst.fuel_analyst import fuel_analyst
    from fuel_analyst.run_conpyro import run_conpyro
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

    refreshed_weather_path = os.path.join(CONPYRO_DIR, 'conpyro_df_wx_current.csv')
    _refresh_weather_inputs(
        WEATHER_MERGED_PATH, os.path.join(FUEL_ANALYST_RESULTS_DIR, 'conpyro_df.csv'), refreshed_weather_path
    )

    print('\n=== Step 2: run_conpyro() ===')
    run_conpyro(
        out_dir=CONPYRO_DIR,
        in_conpyro_csv_path=refreshed_weather_path,
        in_tree_csv_path=os.path.join(FUEL_ANALYST_RESULTS_DIR, 'master_tree_df.csv'),
        # fire_modelling_params=None below uses default_fire_modelling_dict, whose
        # fofem_emissions.emissions_units defaults to 'SI' - must match this filename.
        in_fofem_consume_csv_path=os.path.join(
            FUEL_ANALYST_RESULTS_DIR, fofem_units.consume_filename('SI')
        ),
        fire_modelling_params=None,
    )


if __name__ == '__main__':
    main()
