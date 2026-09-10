# -*- coding: utf-8 -*-
"""
Weather extraction, merge, and ConPyro/FOFEM pipeline (advanced/regeneration script).

For a quick, standalone demonstration of the fuel_analyst() -> run_conpyro()
workflow against committed data alone, see ``examples/run_fuel_analyst_conpyro_demo.py``
instead - it needs no NRCAN weather archive access and no environment-split concerns.

This script is for the narrower, more advanced case of regenerating that demo's
checked-in weather-merged dataset (``examples/data/weather/conpyro_df_wx.csv``)
against fresh/real NRCAN weather, or for exercising the weather extraction and
merge steps (``src/fuel_analyst/tools/``) on their own. Runs the documented but
previously separately-invoked chain (README.md "Weather extraction" / "Merge
weather with plot data" / "Run ConPyro and FOFEM" sections) as one script
against the current ``examples/data/Survey123_Data`` dataset. This is Phase 2
deliverable 1 of
``development/plans/2026-08-31-demo-dataset-replacement-and-section3.md``
(weather/ConPyro/FOFEM demonstration) — it does not include FBP fuel typing,
which is deliverable 2, blocked on Open Question #2 (a new FBP-prep dataset).

``--stage conpyro`` prefers a freshly-regenerated ``<WEATHER_DIR>/conpyro_df_wx.csv``
when one already exists on disk (from an earlier ``--stage merge`` run, in this
process or an earlier one), and otherwise falls back to the checked-in
``examples/data/weather/conpyro_df_wx.csv`` - so it never silently discards a
user's own regenerated weather in favor of the demo default, regardless of
whether ``merge`` happened to run in the same invocation.

Known environment split on this machine (documented, not a code issue):
the project's ``FuelAnalyst`` conda env has a broken ``rasterio`` install
(DLL load failures, likely a PATH conflict with ArcGIS Pro's ``bin``
directory shadowing GDAL/Python DLLs) so ``--stage weather`` cannot run
there; the ``ProcessGeospatial`` conda env has working ``rasterio`` but
lacks ``conpyro``/``pyfofem``, so ``--stage merge``/``--stage conpyro``
cannot run there. Run ``--stage weather`` in an environment with a
working geospatial stack, then ``--stage merge --stage conpyro`` in the
environment with ``conpyro``/``pyfofem`` installed, to regenerate the
committed weather-merged file end to end. ``--stage all`` is equivalent
to ``--stage weather --stage merge --stage conpyro`` in one process, so
it only works in an environment where every stage's dependencies are
satisfied at once; it is **not** a substitute for ``--stage merge
--stage conpyro`` in the split-environment workflow above, since it
would still try (and fail) to re-run the weather stage.

Requires ``examples/results/fuel_analyst/`` to already exist (run
``fuel_analyst.fuel_analyst`` first): ``--stage conpyro`` still needs
its ``master_tree_df.csv``/``fofem_consume_si_df.csv`` for FOFEM
mortality/emissions, even when it sources fire-behavior weather input
from the checked-in file rather than ``--stage merge``.
"""
import argparse
import os
import sys
from typing import Optional

# fuel_analyst isn't pip-installed in every environment this script needs to
# run in (confirmed: neither the FuelAnalyst nor ProcessGeospatial conda envs
# have it installed; only PyCharm's own Sources Root marking resolves it
# automatically). Bootstrap src/ onto sys.path so a plain `python
# examples/weather_pipeline/run_weather_conpyro_pipeline.py` works from any
# interpreter, regardless of PYTHONPATH or how it's invoked. This script lives
# one directory deeper than examples/run_fuel_analyst_conpyro_demo.py, hence
# the extra dirname() hop versus that script's bootstrap.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SRC_DIR = os.path.join(_REPO_ROOT, 'src')
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

# Each stage's fuel_analyst import is deferred into its own function below,
# not done here at module level. extract_nrcan_wx pulls in rasterio (broken
# in the FuelAnalyst conda env on this machine) and run_conpyro pulls in
# conpyro/pyfofem (not installed in the ProcessGeospatial conda env); an
# eager top-of-file import of all three would fail in EITHER environment
# regardless of which --stage was actually requested. merge_wx_data only
# needs pandas/numpy, so it has no environment restriction.

# EXAMPLES_DIR is the repo's examples/ directory - one level up from this script's
# own (nested) location, unlike examples/run_fuel_analyst_conpyro_demo.py which lives
# directly in examples/.
EXAMPLES_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FUEL_ANALYST_RESULTS_DIR = os.path.join(EXAMPLES_DIR, 'results', 'fuel_analyst')
WX_EXTRACT_DIR = os.path.join(EXAMPLES_DIR, 'results', 'wx_extract')
WEATHER_DIR = os.path.join(EXAMPLES_DIR, 'results', 'weather')
CONPYRO_DIR = os.path.join(EXAMPLES_DIR, 'results', 'conpyro')

#: Checked-in, already weather-merged demo input (real 2005-2024 NRCAN weather for
#: examples/data/Survey123_Data's 20 plots, merged via `--stage merge`). `--stage
#: conpyro` falls back to this only when no freshly-regenerated WEATHER_DIR output
#: exists yet. Regenerate by running `--stage weather --stage merge` (requires real
#: NRCAN archive access) and copying the resulting WEATHER_DIR output here.
COMMITTED_WEATHER_MERGED_PATH = os.path.join(EXAMPLES_DIR, 'data', 'weather', 'conpyro_df_wx.csv')

#: Base path to NRCAN gridded weather data (variable subdirectories + dated rasters).
#: Override with the NRCAN_DATA_DIR environment variable (same variable name
#: extract_nrcan_wx.py's own __main__ block uses for its Docker case) since this
#: default is specific to the machine this script was developed on.
WX_DATA_DIR = os.getenv('NRCAN_DATA_DIR', r'I:\_Weather_Data\NRCAN_FWIS_Database')

#: Weather variables to sample; matches run_conpyro()'s required/optional fields.
WX_VAR_LIST = ['temp', 'pcp', 'rh', 'ws', 'wd', 'ffmc', 'dmc', 'dc', 'bui', 'isi', 'fwi']

#: Historical range matching prior production convention (extract_nrcan_wx.py's
#: own __main__ defaults). Not survey-date-matched: ConPyro/FBP consume a
#: seasonal range of weather scenarios, not one literal field-survey date.
START_YEAR = 2005
END_YEAR = 2024
START_MONTH_DAY = 501
END_MONTH_DAY = 930


def _run_conpyro_stage(in_conpyro_csv_path: Optional[str] = None) -> None:
    """
    Run ConPyro, FOFEM mortality, and FOFEM emissions against a weather-merged table.

    Imports ``run_conpyro`` here, not at module level, since it requires
    ``conpyro``/``pyfofem`` — not installed in every environment this
    script runs in.

    :param in_conpyro_csv_path: Path to the weather-merged ConPyro input table.
        If not given (the default), resolved at call time: a freshly-regenerated
        ``<WEATHER_DIR>/conpyro_df_wx.csv`` is preferred if it already exists on
        disk (from an earlier ``--stage merge`` run, in this process or an
        earlier one), otherwise the checked-in :data:`COMMITTED_WEATHER_MERGED_PATH`
        is used. Resolving by disk state rather than "did 'merge' run in this
        same invocation" means a user's own regenerated weather is never
        silently discarded just because ``--stage merge`` and ``--stage conpyro``
        happened to run as two separate script invocations.
    :return: None. Writes ConPyro/FOFEM outputs and ``run_conpyro_errors.csv``
        under :data:`CONPYRO_DIR`.
    """
    from fuel_analyst.run_conpyro import run_conpyro
    from fuel_analyst.components import fofem_units

    if in_conpyro_csv_path is None:
        fresh_path = os.path.join(WEATHER_DIR, 'conpyro_df_wx.csv')
        in_conpyro_csv_path = fresh_path if os.path.exists(fresh_path) else COMMITTED_WEATHER_MERGED_PATH

    run_conpyro(
        out_dir=CONPYRO_DIR,
        in_conpyro_csv_path=in_conpyro_csv_path,
        in_tree_csv_path=os.path.join(FUEL_ANALYST_RESULTS_DIR, 'master_tree_df.csv'),
        # fire_modelling_params=None below uses default_fire_modelling_dict, whose
        # fofem_emissions.emissions_units defaults to 'SI' - must match this filename.
        in_fofem_consume_csv_path=os.path.join(
            FUEL_ANALYST_RESULTS_DIR, fofem_units.consume_filename('SI')
        ),
        fire_modelling_params=None,
    )


def _run_merge_stage() -> None:
    """
    Merge extracted weather data with ``conpyro_df.csv``.

    No ``fbp_fuel_type`` column is present (FBP typing is deliverable 2,
    tabled pending Open Question #2), so seasonal FBP refinement is
    disabled explicitly rather than left to silently no-op.

    :return: None. Writes the merged table to
        ``<WEATHER_DIR>/conpyro_df_wx.csv``.
    """
    from fuel_analyst.tools.merge_wx_data import merge_weather_data

    merge_weather_data(
        plot_data_path=os.path.join(FUEL_ANALYST_RESULTS_DIR, 'conpyro_df.csv'),
        plot_merge_col_name='unique_id',
        wx_data_path=os.path.join(WX_EXTRACT_DIR, 'wx_data.csv'),
        wx_merge_col_name='unique_id',
        wx_merge_vars=None,
        out_path=os.path.join(WEATHER_DIR, 'conpyro_df_wx.csv'),
        add_season=True,
        refine_fbp_seasonally=False,
        summer_start=615,
        fall_start=915,
    )


def _run_weather_stage() -> None:
    """
    Extract NRCAN gridded weather data for the current dataset's plot locations.

    Imports ``extract_weather_data`` here, not at module level, since it
    requires ``rasterio`` — not working in every environment this script
    runs in.

    :return: None. Writes ``wx_data.csv``, ``wx_data.shp``, and
        ``wx_data_errors.csv`` under :data:`WX_EXTRACT_DIR`.
    """
    from fuel_analyst.tools.extract_nrcan_wx import extract_weather_data

    extract_weather_data(
        wx_data_dir=WX_DATA_DIR,
        out_dir=WX_EXTRACT_DIR,
        out_file_name='wx_data',
        plot_pts_path=os.path.join(FUEL_ANALYST_RESULTS_DIR, 'conpyro_df.csv'),
        plot_id_col_name='unique_id',
        lat_col_name='lat',
        lon_col_name='long',
        wx_var_list=WX_VAR_LIST,
        start_year=START_YEAR,
        end_year=END_YEAR,
        use_bcws_dates=False,
        start_month_day=START_MONTH_DAY,
        end_month_day=END_MONTH_DAY,
        calculate_percentiles=True,
        percentile_var_list=['fwi'],
    )


def main() -> None:
    """
    Parse CLI arguments and run the requested pipeline stage(s) in order.

    :return: None.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--stage',
        choices=('weather', 'merge', 'conpyro', 'all'),
        action='append',
        required=True,
        help='Stage(s) to run; repeat --stage to run more than one in this process.',
    )
    args = parser.parse_args()
    stages = set(args.stage)
    if 'all' in stages:
        stages = {'weather', 'merge', 'conpyro'}

    if 'weather' in stages:
        print('=== Stage: weather extraction ===')
        _run_weather_stage()
    if 'merge' in stages:
        print('=== Stage: merge weather with plot data ===')
        _run_merge_stage()
    if 'conpyro' in stages:
        print('=== Stage: run ConPyro/FOFEM ===')
        # _run_conpyro_stage() resolves its own input path by disk state (prefers a
        # freshly-regenerated WEATHER_DIR output over the checked-in demo file), so
        # it works correctly whether 'merge' ran in this same invocation or an
        # earlier, separate one.
        _run_conpyro_stage()


if __name__ == '__main__':
    main()
