# -*- coding: utf-8 -*-
"""
Standalone fuel_analyst() -> run_conpyro() demonstration.

Runs the complete FuelAnalyst -> ConPyro -> FOFEM workflow against committed
data alone: ``examples/data/Survey123_Data`` (raw plot data) and
``examples/data/weather/conpyro_df_wx.csv`` (real 2005-2024 NRCAN weather,
already extracted and merged). No NRCAN weather archive access, no rasterio,
and no environment-split concerns are needed - just an environment with
``fuel_analyst``'s ``conpyro`` and ``fofem`` optional dependencies installed.

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


def main() -> None:
    """
    Run fuel_analyst() on the committed Survey123 dataset, then run_conpyro()
    against the committed weather-merged dataset.

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

    print('\n=== Step 2: run_conpyro() ===')
    run_conpyro(
        out_dir=CONPYRO_DIR,
        in_conpyro_csv_path=WEATHER_MERGED_PATH,
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
