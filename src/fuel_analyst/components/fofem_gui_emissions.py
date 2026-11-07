# -*- coding: utf-8 -*-
"""
Created on Sun Feb 1, 16:30:00 2026

@author: Gregory A. Greene
"""
__author__ = ['Gregory A. Greene']

import logging
import os
import re
import shutil
import subprocess
import sys
from typing import Union

import numpy as np
import pandas as pd
import tqdm
import concurrent.futures

from . import fofem_units
from . import fofem_moisture
from . import helper
from ._default_configs import default_season_start_dict
try:
    from tqdm.contrib.concurrent import process_map
    _TQDM_PROCESS_MAP_AVAILABLE = True
except ImportError:
    _TQDM_PROCESS_MAP_AVAILABLE = False

logger = logging.getLogger(__name__)

# Environment variable override for _get_fofem_dir(), for use when the bundled
# src/fuel_analyst/supporting_data/fofem_694 directory is not present (e.g. an alternate
# installation of the official FOFEM 6.9.4 batch runtime).
_FOFEM_DIR_ENV_VAR = 'FUEL_ANALYST_FOFEM_DIR'
_RUNFOFEM_EXE = 'runfofem.exe'
# Windows loader status code STATUS_DLL_NOT_FOUND (0xC0000135), the OS-level exit code
# runfofem.exe (or any Windows executable) produces when a required DLL - notably the
# Microsoft Visual C++ Redistributable's msvcp140.dll/vcruntime140.dll/vcruntime140_1.dll,
# a documented prerequisite this project deliberately does not bundle - cannot be located.
# subprocess.run() reports this as a large negative signed return code on Windows rather than
# raising OSError, since process creation itself succeeds; only the loader fails.
_STATUS_DLL_NOT_FOUND = 0xC0000135
# Files copied into each worker's own isolated directory (never the shared fofem_dir bundle
# itself) before it invokes runfofem.exe there. runfofem.exe writes at least one shared-state
# file (runfofem_plots.tmp) into FOFEM_DATA regardless of the subprocess's cwd - verified
# directly, not documented by FOFEM - so concurrent workers pointing FOFEM_DATA at the same
# shared directory race on that file. Giving every worker its own copy of the runtime, with
# FOFEM_DATA pointed at that worker's own copy, removes the shared directory from the picture
# entirely. No Microsoft Visual C++ runtime DLLs are copied here (or bundled anywhere in
# FuelAnalyst): the redistributable is a documented, separately-installed Windows prerequisite
# (see docs/CODEBASE.md), not an app-local file this codebase provides or manages.
_REQUIRED_FOFEM_RUNTIME_FILES = [_RUNFOFEM_EXE, 'Emission_Factors.csv', 'fof_spp.csv']

# Fixed 6.9.4 batch consumption/soil input field order, verified directly against runfofem.exe
# (tests/manual/fofem694_no_install_smoke.ps1). Field names, not incidental DataFrame column
# order, drive the writer: runfofem.exe's batch reader is purely positional (its header row is
# a comment, per gen_fofem_consumption_df()'s own docstring), so relying on a DataFrame's
# current column order would silently miswrite the file if that order ever changed upstream.
# Matches gen_fofem_consumption_df()'s own field set exactly, including the pre-existing
# 6.7-era quirk of using its static, config-supplied 'Season' value rather than
# _get_season()'s per-row wx_date-derived 'season' (used only by the separate pyfofem backend).
_CONSUMPTION_FIELD_ORDER = [
    '#PlotId', 'Litter', 'wfl1Hour', 'wfl10Hour', 'wfl10HourMoisture', 'wfl100Hour',
    'wfl3_6S', 'wfl6_9S', 'wfl9_20S', 'wfl20plusS',
    'wfl3_6R', 'wfl6_9R', 'wfl9_20R', 'wfl20plusR',
    'wfl1000HourMoisture', 'Duff', 'DuffMoisture', 'DuffDepth',
    'Herbaceous', 'Shrub', 'CrownFoliage', 'CrownBranch',
    'PercentCrownBurned', 'Region', 'CoverGroup', 'Season', 'FuelCategory',
]
# Soil-mode-only fields, inserted right after _CONSUMPTION_FIELD_ORDER and before the equation
# overrides. Ambient temperature (from the row's 'temp' weather field) comes last within this
# group - its new required position in the 6.9.4 input format, after SoilMoisture.
_SOIL_FIELD_ORDER = ['SoilFamily', 'SoilMoisture']
# Equation-override fields, in the fixed order the 6.9.4 batch input expects them, appended
# after every other field (including SoilFamily/SoilMoisture/AmbientTemp for soil runs).
_EQUATION_OVERRIDE_COLUMNS = [
    'LitterLoad_ConsumEq1', 'PctDuff_ConsumEq2', 'DuffDepth_ConsumEq3',
    'MSE_ConsumEq4', 'Herb_ConsumEq5', 'Shrub_ConsumEq6',
]

# Expanded Emission Factor group switches, REQUIRED by the runfofem.exe build verified
# 2026-09-29 (upstream ZIP, see the provenance record) - its own sample inputs
# (sampledata/ConE-In.txt, sampledata/Soil-In.txt) mark these as required switches, and their
# absence is exactly what produced "Input File has a missing or invalid Expanded Emission
# Factor switch(es)" against that build. A previously bundled runfofem.exe build accepted
# their absence; do not assume every future build will require them. Values match pyfofem's
# own run_fofem_emissions() defaults (ef_group=3, ef_smoldering_group=7, ef_duff_group=8) for
# consistency between backends. Per the upstream guide, CWDRSC and DuffRSC each have exactly
# one valid value (7 and 8); STFS accepts 1-6, but FuelAnalyst does not expose that as a
# user-configurable knob for either backend today, so it stays fixed at pyfofem's own default.
_EFG_STFS = 3
_EFG_CWDRSC = 7
_EFG_DUFFRSC = 8

# Verified 6.9.4 consumption/soil output column counts (header row) with equation results
# always enabled (#ConsumptionEquation is always written - see _write_consumption_input()).
# Confirmed directly against runfofem.exe: consumption=80, soil=86; see
# tests/manual/fofem694_no_install_smoke.ps1 and development/plans/2026-09-28-pyfofem-pypi-
# integration.md's "Verified command-line probes" section.
_EXPECTED_OUTPUT_COLUMN_COUNTS = {'C': 80, 'S': 86}

# Fixed-format 113-switch Burnup parameter file for FOFEM 6.9.4's runfofem.exe. The pyfofem
# package's own gen_burnup_in_file() only writes 17 switches and is rejected by 6.9.4
# ("switch not found #FM_Lit"); this template reproduces the verified, accepted 113-switch
# format from tests/test_data/fofem694/burnup_parameters_694.brn exactly, substituting only the
# five fire/weather-derived values FuelAnalyst computes per row. Every other switch is a fixed
# physical fuel-property constant, not user-configurable - confirmed by the same smoke test.
_BURNUP_PARAMS_694_TEMPLATE = """#MAX_TIMES 3000
#INTENSITY {intensity}
#IG_TIME {ig_time}
#WINDSPEED {windspeed}
#DEPTH {depth}
#AMBIENT_TEMP {ambient_temp}
#R0 1.83
#DR 0.4
#TIMESTEP 15
#HCon_Lit 18600.0
#HCon_DW1 18600.0
#HCon_DW10 18600.0
#HCon_DW100 18600.0
#HCon_DWk_Snd_3_6 18600.0
#HCon_DWk_Rot_3_6 18600.0
#HCon_DWk_Snd_6_9 18600.0
#HCon_DWk_Rot_6_9 18600.0
#HCon_DWk_Snd_9_20 18600.0
#HCon_DWk_Rot_9_20 18600.0
#HCon_DWk_Snd_20 18600.0
#HCon_DWk_Rot_20 18600.0
#FM_Lit 0.08
#FM_DW1 0.08
#FM_DW10 0.10
#FM_DW100 0.12
#FM_DWk_Snd_3_6 0.15
#FM_DWk_Rot_3_6 0.375
#FM_DWk_Snd_6_9 0.15
#FM_DWk_Rot_6_9 0.375
#FM_DWk_Snd_9_20 0.15
#FM_DWk_Rot_9_20 0.375
#FM_DWk_Snd_20 0.15
#FM_DWk_Rot_20 0.375
#Den_Lit 513
#Den_DW1 513
#Den_DW10 513
#Den_DW100 513
#Den_DWk_Snd_3_6 513
#Den_DWk_Rot_3_6 224
#Den_DWk_Snd_6_9 513
#Den_DWk_Rot_6_9 224
#Den_DWk_Snd_9_20 513
#Den_DWk_Rot_9_20 224
#Den_DWk_Snd_20 513
#Den_DWk_Rot_20 224
#SURat_Lit 8200.0
#SURat_DW1 1480.0
#SURat_DW10 394.0
#SURat_DW100 105.0
#SURat_DWk_3_6 39.4
#SURat_DWk_6_9 21.9
#SURat_DWk_9_20 12.7
#SURat_DWk_20 5.91
#HCap_Lit 2750
#HCap_DW1 2750
#HCap_DW10 2750
#HCap_DW100 2750
#HCap_DWk_Snd_3_6 2750
#HCap_DWk_Rot_3_6 2750
#HCap_DWk_Snd_6_9 2750
#HCap_DWk_Rot_6_9 2750
#HCap_DWk_Snd_9_20 2750
#HCap_DWk_Rot_9_20 2750
#HCap_DWk_Snd_20 2750
#HCap_DWk_Rot_20 2750
#TCon_Lit 0.133
#TCon_DW1 0.133
#TCon_DW10 0.133
#TCon_DW100 0.133
#TCon_DWk_Snd_3_6 0.133
#TCon_DWk_Rot_3_6 0.133
#TCon_DWk_Snd_6_9 0.133
#TCon_DWk_Rot_6_9 0.133
#TCon_DWk_Snd_9_20 0.133
#TCon_DWk_Rot_9_20 0.133
#TCon_DWk_Snd_20 0.133
#TCon_DWk_Rot_20 0.133
#IgTemp_Lit 327
#IgTemp_DW1 327
#IgTemp_DW10 327
#IgTemp_DW100 327
#IgTemp_DWk_Snd_3_6 327
#IgTemp_DWk_Rot_3_6 302
#IgTemp_DWk_Snd_6_9 327
#IgTemp_DWk_Rot_6_9 302
#IgTemp_DWk_Snd_9_20 327
#IgTemp_DWk_Rot_9_20 302
#IgTemp_DWk_Snd_20 327
#IgTemp_DWk_Rot_20 302
#ChTemp_Lit 377
#ChTemp_DW1 377
#ChTemp_DW10 377
#ChTemp_DW100 377
#ChTemp_DWk_Snd_3_6 377
#ChTemp_DWk_Rot_3_6 377
#ChTemp_DWk_Snd_6_9 377
#ChTemp_DWk_Rot_6_9 377
#ChTemp_DWk_Snd_9_20 377
#ChTemp_DWk_Rot_9_20 377
#ChTemp_DWk_Snd_20 377
#ChTemp_DWk_Rot_20 377
#MAF_Lit 0.05
#MAF_DW1 0.05
#MAF_DW10 0.05
#MAF_DW100 0.05
#MAF_DWk_Snd_3_6 0.05
#MAF_DWk_Rot_3_6 0.05
#MAF_DWk_Snd_6_9 0.05
#MAF_DWk_Rot_6_9 0.05
#MAF_DWk_Snd_9_20 0.05
#MAF_DWk_Rot_9_20 0.05
#MAF_DWk_Snd_20 0.05
#MAF_DWk_Rot_20 0.05
"""


def _calc_fuel_moisture_content(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate fuel moisture content columns and add them to the DataFrame.

    :param df: DataFrame with 'mc_sa', 'dmc', and 'dc' columns.
    :return: DataFrame with 'wfl10HourMoisture', 'DuffMoisture', and 'wfl1000HourMoisture' columns added.
    """
    return fofem_moisture.calc_fuel_moisture_content(df, logger)


def _convert_consume_row_to_imperial(row_consume_df: pd.DataFrame, emissions_units: str) -> pd.DataFrame:
    """
    Convert a single-row FOFEM consumption DataFrame to the Imperial units the FOFEM 6.9.4
    batch executable requires, rounded to its expected batch-file precision.

    The intermediate consumption CSV's column names and order are fixed and unsuffixed
    regardless of emissions_units (see fofem_units.py); only the load/depth values themselves
    differ. This keeps the exact existing column set and order - it never adds, removes, or
    duplicates a column.

    :param row_consume_df: Single-row consumption DataFrame with the fixed, unsuffixed FOFEM
        column names, holding values in the unit system given by emissions_units.
    :param emissions_units: Unit system of row_consume_df's values ('SI' or 'Imperial').
    :return: A new DataFrame with the same columns/order; load and DuffDepth values converted to
        Imperial (if emissions_units is 'SI') and rounded to 2 decimals; other columns unchanged.
    """
    row_consume_df = row_consume_df.copy()
    physical_cols = fofem_units.FOFEM_LOAD_COLUMNS + fofem_units.FOFEM_DEPTH_COLUMNS
    physical_cols = [c for c in physical_cols if c in row_consume_df.columns]
    if emissions_units == 'SI':
        load_cols = [c for c in fofem_units.FOFEM_LOAD_COLUMNS if c in row_consume_df.columns]
        depth_cols = [c for c in fofem_units.FOFEM_DEPTH_COLUMNS if c in row_consume_df.columns]
        row_consume_df[load_cols] = row_consume_df[load_cols] * fofem_units.LOAD_CONV_FACTOR
        row_consume_df[depth_cols] = row_consume_df[depth_cols] * fofem_units.DEPTH_CONV_FACTOR
    row_consume_df[physical_cols] = row_consume_df[physical_cols].round(2)
    return row_consume_df


def _ensure_worker_fofem_runtime(worker_dir: str, fofem_dir: str) -> str:
    """
    Copy the FOFEM 6.9.4 runtime files this worker needs into its own isolated directory,
    skipping any file already copied there (so a worker that reuses worker_dir across several
    rows only pays the copy cost once). Never writes into fofem_dir itself, which stays a
    read-only copy source shared across all workers.

    :param worker_dir: This worker's isolated directory (created under the caller's out_dir).
    :param fofem_dir: Absolute path to the shared FOFEM 6.9.4 batch runtime directory to copy from.
    :return: worker_dir, now containing its own copy of the runtime files.
    :raises FileNotFoundError: If a required runtime file is missing from fofem_dir.
    """
    for filename in _REQUIRED_FOFEM_RUNTIME_FILES:
        src = os.path.join(fofem_dir, filename)
        dst = os.path.join(worker_dir, filename)
        if not os.path.isfile(src):
            raise FileNotFoundError(f'Required FOFEM 6.9.4 runtime file not found: {src}')
        if not os.path.isfile(dst):
            shutil.copy(src, dst)
    return worker_dir


def _format_burnup_value(value: float) -> str:
    """
    Format one dynamic Burnup parameter value, rounded to 2 decimals, without a spurious
    trailing '.0' for whole numbers - matching the verified fixture's own convention
    (e.g. '500', '60', '2', not '500.0', '60.0', '2.0').

    :param value: Raw parameter value.
    :return: String representation, e.g. '500' or '0.3'.
    """
    rounded = round(float(value), 2)
    if rounded == int(rounded):
        return str(int(rounded))
    return str(rounded)


def _gen_plot_id(df: pd.DataFrame):
    """
    Replace spaces with underscores in the '#PlotId' column and return a mapping
    from underscored to original values.

    :param df: DataFrame with '#PlotId' column.
    :return: (DataFrame with updated '#PlotId', dict mapping underscored to original values)
    """
    plotid_map = dict(zip(df['#PlotId'].str.replace(' ', '_'), df['#PlotId']))
    df['#PlotId'] = df['#PlotId'].str.replace(' ', '_')
    return df, plotid_map


def _get_fofem_dir() -> str:
    """
    Resolve the FOFEM 6.9.4 batch runtime directory (runfofem.exe, Emission_Factors.csv, and
    fof_spp.csv; no Microsoft Visual C++ runtime DLLs - the redistributable is a documented,
    separately-installed Windows prerequisite, not a file this codebase bundles or manages).

    Checked eagerly at the top of process_emissions() rather than lazily per-row. Every
    candidate must contain the executable and both CSVs, so incomplete installations fail
    before any row is processed.

    Resolved in order:
      1. The FUEL_ANALYST_FOFEM_DIR environment variable, for an alternate/separately
         installed 6.9.4 runtime (or to cover a platform/environment the runtime wheel below
         doesn't reach).
      2. The installed fuel-analyst-fofem694-runtime package (Windows x64 only;
         packages/fofem694-runtime/), if it is installed - its own get_runtime_dir() resolves
         its installed location via importlib.resources, so this works regardless of the
         installing environment's own directory layout.
      3. The bundled src/fuel_analyst/supporting_data/fofem_694 directory shipped alongside
         this module in a Git source checkout - resolved relative to this file, not a
         source-checkout-relative repo root. A normal `pip install fuel-analyst` wheel does
         not include this directory's runfofem.exe (only its *.csv files, via MANIFEST.in's
         recursive-include pattern), so this step only succeeds from a source checkout; step 2
         is what provides the executable when installed from a wheel.

    :return: Absolute path to the FOFEM 6.9.4 batch runtime directory.
    :raises FileNotFoundError: If none of the three resolution steps yields a directory that
        contains runfofem.exe and both required CSVs.
    """
    override = os.environ.get(_FOFEM_DIR_ENV_VAR)
    if override:
        if not os.path.isdir(override):
            raise FileNotFoundError(
                f'{_FOFEM_DIR_ENV_VAR} is set to "{override}", but that directory does not exist.'
            )
        missing = [name for name in _REQUIRED_FOFEM_RUNTIME_FILES
                   if not os.path.isfile(os.path.join(override, name))]
        if missing:
            raise FileNotFoundError(
                f'{_FOFEM_DIR_ENV_VAR} is set to "{override}", but required FOFEM 6.9.4 '
                f'runtime files are missing there: {", ".join(missing)}.'
            )
        return override

    try:
        import fuel_analyst_fofem694_runtime
        runtime_dir = fuel_analyst_fofem694_runtime.get_runtime_dir()
        if all(os.path.isfile(os.path.join(runtime_dir, name))
               for name in _REQUIRED_FOFEM_RUNTIME_FILES):
            return runtime_dir
    except ImportError:
        pass

    bundled_dir = os.path.normpath(
        os.path.join(os.path.dirname(__file__), '..', 'supporting_data', 'fofem_694')
    )
    missing = [name for name in _REQUIRED_FOFEM_RUNTIME_FILES
               if not os.path.isfile(os.path.join(bundled_dir, name))]
    if missing:
        raise FileNotFoundError(
            f'Could not resolve the FOFEM 6.9.4 batch runtime directory: required files '
            f'{", ".join(missing)} are missing at {bundled_dir}, the '
            f'fuel-analyst-fofem694-runtime package is not '
            f'installed (or is installed but incomplete), and the {_FOFEM_DIR_ENV_VAR} '
            f'environment variable is not set. On Windows, install the '
            f'fuel-analyst-fofem694-runtime package for this backend, or set '
            f'{_FOFEM_DIR_ENV_VAR} to point at an equivalent FOFEM 6.9.4 installation '
            f'directory. A Git source checkout of fuel-analyst includes this directory '
            f'directly and does not need either.'
        )
    return bundled_dir


def _get_merged_consumption_df(
        plot_wx_fire_csv_path: str,
        plot_id_col_name: str,
        fofem_consume_csv_path: str,
        consume_model: str = 'C'
) -> pd.DataFrame:
    """
    Merge stand fire severity and FOFEM consumption dataframes.

    :param plot_wx_fire_csv_path: Path to stand weather and fire severity CSV file.
    :param plot_id_col_name: Name of the unique ID column in the stand fire severity CSV used for merging (e.g., 'unique_id').
    :param fofem_consume_csv_path: Path to FOFEM consumption CSV file.
    :param consume_model: FOFEM consumption model ('C' or 'S').
    :return: Merged DataFrame.
    """
    if not helper.file_exists(plot_wx_fire_csv_path):
        raise FileNotFoundError(f'Stand weather and fire behavior CSV file not found: {plot_wx_fire_csv_path}')
    if not helper.file_exists(fofem_consume_csv_path):
        raise FileNotFoundError(f'FOFEM consumption CSV file not found: {fofem_consume_csv_path}')

    plot_fire_df = helper.get_df(plot_wx_fire_csv_path)
    fofem_consume_df = helper.get_df(fofem_consume_csv_path)

    if consume_model == 'C':
        remove_cols = ['SoilFamily', 'SoilMoisture']
        soil_heating_cols = [col for col in fofem_consume_df.columns if col not in remove_cols]
        fofem_consume_df = fofem_consume_df[soil_heating_cols]
    else:  # if consume_model == 'S':
        fofem_consume_df['SoilFamily'] = fofem_consume_df['SoilFamily'].fillna('NA')

    required_cols = [
        plot_id_col_name, 'wx_date', 'hfi',
        'flame_res_time_sec', 'instand_ws_mps',
        'temp', 'mc_sa', 'mc_dmc', 'dc', 'cfb'
    ]

    missing_cols = helper.get_missing_df_columns(plot_fire_df, required_cols)
    if missing_cols:
        raise ValueError(
            f'Missing required column(s) in weather and fire behavior CSV: {required_cols}'
        )

    optional_cols = [column for column in ('surface_fuel_type', 'stand_type') if column in plot_fire_df]
    plot_fire_df = plot_fire_df[required_cols + optional_cols]

    merged_df = pd.merge(
        left=fofem_consume_df,
        right=plot_fire_df,
        left_on='#PlotId',
        right_on=plot_id_col_name,
        how='left',
        suffixes=('', '_plot')
    )
    merged_df = merged_df.drop(columns=[col for col in merged_df.columns if col.endswith('_plot')])
    merged_df = merged_df.dropna(subset=[plot_id_col_name])

    return merged_df


def _get_pct_crown_burned(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate percent crown burned and add to DataFrame.

    :param df: DataFrame with 'cfb' column.
    :return: DataFrame with 'PercentCrownBurned' column added.
    """
    df['PercentCrownBurned'] = 100 * df['cfb']

    return df


def _get_season(df: pd.DataFrame, season_start_dict: dict = None) -> pd.DataFrame:
    """
    Determine the season for each row in the DataFrame based on date and season start dates.

    :param df: DataFrame with 'wx_date' column.
    :param season_start_dict: Dictionary defining season start dates.
    :return: DataFrame with 'season' column added.
    """
    if season_start_dict is None:
        season_start_dict = default_season_start_dict

    required_cols = ['wx_date']
    missing_cols = helper.get_missing_df_columns(df, required_cols)
    if missing_cols:
        raise ValueError(
            f'Missing required column(s) in weather CSV: {required_cols}'
        )

    season_starts = {
        'Spring': int(season_start_dict['Spring']),
        'Summer': int(season_start_dict['Summer']),
        'Fall': int(season_start_dict['Fall']),
        'Winter': int(season_start_dict['Winter']),
    }

    def determine_season(row):
        """
        Determine the configured season for one weather-data row.

        :param row: Weather-data row containing a YYYYMMDD wx_date value.
        :return: Season name containing the weather date.
        """
        date_str = str(row['wx_date'])
        month_day = int(date_str[4:8])
        if season_starts['Spring'] <= month_day < season_starts['Summer']:
            return 'Spring'
        elif season_starts['Summer'] <= month_day < season_starts['Fall']:
            return 'Summer'
        elif season_starts['Fall'] <= month_day < season_starts['Winter']:
            return 'Fall'
        else:
            return 'Winter'

    df['season'] = df.apply(determine_season, axis=1)

    return df


def _log_emissions_failures(results: list, merged_df: pd.DataFrame, plotid_map: dict) -> None:
    """
    Log the runfofem.exe rows that failed, once per plot and cause, from the parent process.

    A logging call made inside a ProcessPoolExecutor worker never reaches error_handling's collecting handler in the
    parent process, but the return value of _model_emissions() always does. So each worker only returns
    {'fofem_gui_error': message} for a failed row, and this function reports those messages from the parent, which
    gives the same report for every worker count. A plot with several failed weather dates and the same cause is
    logged once, with the number of failed scenarios and the first weather date.

    :param results: One result dict per row of merged_df, in order; a failed row holds 'fofem_gui_error'.
    :param merged_df: Merged consumption and fire data, with the (underscored) '#PlotId' and 'wx_date' columns.
    :param plotid_map: Mapping from the underscored '#PlotId' values back to the original plot IDs.
    :return: None. Logs one error per plot and cause through error_handling.
    """
    prefix = re.compile(r'^runfofem\.exe failed for plot ".*?", wx_date .*?: ')
    plot_ids = merged_df['#PlotId'].tolist()
    wx_dates = merged_df['wx_date'].tolist() if 'wx_date' in merged_df.columns else [None] * len(plot_ids)
    totals = merged_df['#PlotId'].value_counts().to_dict()
    failures = {}
    for plot_id, wx_date, result in zip(plot_ids, wx_dates, results):
        message = result.get('fofem_gui_error') if isinstance(result, dict) else None
        if not isinstance(message, str):
            continue
        entry = failures.setdefault((plot_id, prefix.sub('', message)), [0, wx_date])
        entry[0] += 1
    for (plot_id, cause), (count, first_date) in failures.items():
        logger.error(
            f'runfofem.exe failed for {count} of {totals[plot_id]} weather scenarios of this plot '
            f'(first wx_date {first_date}): {cause}',
            extra={'unique_id': plotid_map.get(plot_id, plot_id), 'issue_code': 'fofem_gui_emissions_runfofem_failure'},
        )


def _model_emissions(row: dict, out_dir: str, consume_model: str, emissions_units: str, fofem_dir: str) -> dict:
    """
    Model emissions for one fire-behavior/weather row via a single isolated runfofem.exe call.

    :param row: Dict of merged DataFrame row containing fire behavior and weather data for a single plot.
    :param out_dir: Parent output directory; this row's isolated worker directory is created under it.
    :param consume_model: FOFEM consumption model ('C' or 'S').
    :param emissions_units: Unit system of row's FOFEM consumption values ('SI' or 'Imperial').
        runfofem.exe itself always requires Imperial input; SI values are converted immediately
        before being written to the batch input file (see _convert_consume_row_to_imperial()).
    :param fofem_dir: Absolute path to the shared FOFEM 6.9.4 batch runtime directory to copy
        this worker's own runtime from (see _get_fofem_dir()); never written to.
    :return: Dict of parsed runfofem.exe result fields for this row. On failure (e.g. a plot's
        windspeed genuinely exceeds Burnup's documented 0-5 m/s validity range - a real FOFEM
        model limit, not clipped or otherwise worked around here), returns
        {'fofem_gui_error': <message>} instead: the row's FOFEM result fields become NaN when
        later assembled into a DataFrame, and 'fofem_gui_error' names the real cause inline in
        the final CSV. The worker does not log it: process_emissions() reports the returned
        message from the parent process (see _log_emissions_failures()).
    """
    worker_dir = os.path.join(out_dir, f'FOFEM_Emissions_{os.getpid()}')
    os.makedirs(worker_dir, exist_ok=True)

    burnup_path = os.path.abspath(os.path.join(worker_dir, 'Burnup-In.brn'))
    input_path = os.path.abspath(os.path.join(worker_dir, 'fofem_input.txt'))
    output_path = os.path.abspath(os.path.join(worker_dir, 'fofem_output.csv'))
    error_path = os.path.abspath(os.path.join(worker_dir, 'fofem_error.txt'))
    try:
        # Inside the try block, not before it: _get_fofem_dir() already validated fofem_dir has
        # runfofem.exe and both required CSVs before any row was processed, so a failure here
        # means the runtime disappeared or was corrupted mid-batch (e.g. concurrent deletion,
        # antivirus quarantine) - this row degrades the same way any other per-row failure
        # does, rather than crashing the whole batch.
        _ensure_worker_fofem_runtime(worker_dir, fofem_dir)

        row_df = _convert_consume_row_to_imperial(pd.DataFrame([row]), emissions_units)
        row_series = row_df.iloc[0]

        _write_burnup_params_694(
            out_path=burnup_path,
            intensity=row['hfi'],
            ig_time=row['flame_res_time_sec'],
            windspeed=row['instand_ws_mps'],
            depth=row['fuel_bed_depth_m'],
            ambient_temp=row['temp'],
        )
        _write_consumption_input(
            input_path=input_path,
            row_series=row_series,
            consume_model=consume_model,
            burnup_path=burnup_path,
        )

        run_type = '1' if consume_model == 'S' else '0'
        # fofem_dir=worker_dir: this worker's own copy of the runtime, not the shared bundle -
        # keeps FOFEM_DATA (and the shared-state file runfofem.exe writes there regardless of
        # cwd) isolated per worker, never shared across concurrent workers.
        _run_runfofem(
            run_type=run_type,
            input_path=input_path,
            output_path=output_path,
            error_path=error_path,
            worker_dir=worker_dir,
            fofem_dir=worker_dir,
        )
        result_df = _parse_runfofem_output(
            output_path, expected_plot_ids=[row_series['#PlotId']], consume_model=consume_model
        )
        result = result_df.iloc[0].to_dict()
    except Exception as e:
        plot_id = row.get('#PlotId', 'N/A')
        wx_date = row.get('wx_date', 'N/A')
        message = (
            f'runfofem.exe failed for plot "{plot_id}", wx_date {wx_date}: {e}'
        )
        # Not logged here: a logging call inside a ProcessPoolExecutor/process_map worker never crosses back to the
        # parent process's error_handling handler. The returned 'fofem_gui_error' always does (multiprocessing
        # pickles it back whatever the worker count), and process_emissions() reports it from the parent through
        # _log_emissions_failures().
        result = {'fofem_gui_error': message}
    finally:
        # Only this row's own files - not the whole worker_dir, whose copied runtime files
        # (and any concurrently-written runfofem_plots.tmp) are reused across this worker's
        # subsequent rows and cleaned up once, after the whole batch, in process_emissions().
        for path in (burnup_path, input_path, output_path, error_path):
            if os.path.isfile(path):
                os.remove(path)

    return result


def _parse_runfofem_output(output_path: str, expected_plot_ids: list, consume_model: str) -> pd.DataFrame:
    """
    Parse a runfofem.exe consumption/soil output CSV using its own field-name header row.

    The output has a field-name header row, then a units row (shorter than the header when
    equation results are enabled, since equation-identifier fields have no physical unit), then
    one data row per plot. Reading with the header row and skipping only the units row lets
    pandas assign each column its own real FOFEM-reported name directly - no positional mapping
    to a hardcoded column-name list, which would otherwise have to reproduce FOFEM's own
    inconsistent naming (e.g. 'Shurb-Equ', not 'Shrub-Equ'). The plot-identity column ('Std')
    is validated against expected_plot_ids then dropped, since the caller's own merged_df
    already carries the authoritative '#PlotId' column - keeping both would collide.

    :param output_path: Path to the runfofem.exe output CSV.
    :param expected_plot_ids: Plot IDs expected, in the order submitted (one input row per
        weather scenario).
    :param consume_model: FOFEM consumption model ('C' or 'S'), selecting the expected header
        column count to validate against (80 or 86, with equation results always enabled).
    :return: DataFrame with runfofem.exe's own result field names as columns, plot identity
        validated and the raw 'Std' column dropped.
    :raises ValueError: If the header column count, row count, or plot identity does not match
        what was expected.
    """
    # cp1252, not utf-8: the soil-mode units row's temperature fields use a Windows-1252 degree
    # sign (0xB0), which is invalid utf-8 and would otherwise raise UnicodeDecodeError even
    # though that row is never used (only the header row and data rows are read).
    result_df = pd.read_csv(output_path, skiprows=[1], skipinitialspace=True, encoding='cp1252')

    expected_cols = _EXPECTED_OUTPUT_COLUMN_COUNTS[consume_model]
    if len(result_df.columns) != expected_cols:
        raise ValueError(
            f'Unexpected runfofem.exe output column count: got {len(result_df.columns)}, '
            f'expected {expected_cols} for consume_model={consume_model!r}. '
            f'Columns: {list(result_df.columns)}'
        )
    if len(result_df) != len(expected_plot_ids):
        raise ValueError(
            f'Unexpected runfofem.exe output row count: got {len(result_df)}, '
            f'expected {len(expected_plot_ids)}.'
        )
    actual_plot_ids = result_df['Std'].tolist()
    if actual_plot_ids != list(expected_plot_ids):
        raise ValueError(
            f'runfofem.exe output plot identity mismatch: got {actual_plot_ids}, '
            f'expected {expected_plot_ids}.'
        )
    return result_df.drop(columns=['Std'])


def _read_runfofem_error_file(error_path: str) -> str:
    """
    Read a runfofem.exe error file and return any real batch-error lines beyond its standard
    four-line preamble ("This file contains FOFEM batch errors.", the missing-values note, the
    input-file line, and a blank line) - matching the verified skip count in
    tests/manual/fofem694_no_install_smoke.ps1.

    :param error_path: Path to the runfofem.exe error file.
    :return: Joined non-blank error lines beyond the preamble, or an empty string if there were none.
    """
    if not helper.file_exists(error_path):
        return ''
    with open(error_path, 'r') as f:
        lines = f.readlines()
    real_errors = [line.strip() for line in lines[4:] if line.strip()]
    return ' | '.join(real_errors)


def _run_runfofem(
        run_type: str,
        input_path: str,
        output_path: str,
        error_path: str,
        worker_dir: str,
        fofem_dir: str,
        extra_args: list = None,
) -> None:
    """
    Invoke the bundled FOFEM 6.9.4 runfofem.exe for one isolated batch call.

    The input file path must be absolute: runfofem.exe resolves a batch input's own
    #BurnUpFile switch relative to the input file's directory, and does so incorrectly (a
    nonsensical concatenated path) when the input file argument itself is given as a relative
    path - verified directly against the bundled executable. FOFEM_DATA and PATH are both set
    to fofem_dir so runfofem.exe can find Emission_Factors.csv/fof_spp.csv regardless of the
    caller's own environment. On Linux, Wine must be on PATH and the Microsoft Visual
    C++ runtime must be provisioned in the selected Wine prefix. Linux calls explicitly
    invoke Wine rather than requiring a binfmt_misc handler or executable permission.

    :param run_type: '0' (consumption/emissions), '1' (consumption/emissions/soil), or '2'
        (mortality).
    :param input_path: Absolute path to the batch input file.
    :param output_path: Absolute path to the batch output CSV to be written.
    :param error_path: Absolute path to the batch error file to be written.
    :param worker_dir: Isolated working directory for this call (subprocess cwd).
    :param fofem_dir: Absolute path to the FOFEM 6.9.4 batch runtime directory.
    :param extra_args: Additional positional arguments appended after the four required ones
        (e.g. ['S', '10'] for mortality's required Scorch/Flame fallback arguments).
    :return: None. Raises if the executable exits non-zero or reports a real batch error.
    :raises FileNotFoundError: If runfofem.exe is not found in fofem_dir.
    :raises RuntimeError: If runfofem.exe exits non-zero or its error file reports a real
        (non-preamble) batch error. A STATUS_DLL_NOT_FOUND exit code (missing Microsoft Visual
        C++ Redistributable) raises with a specific, actionable message instead of the generic
        exit-code message.
    """
    exe_path = os.path.join(fofem_dir, _RUNFOFEM_EXE)
    if not os.path.isfile(exe_path):
        raise FileNotFoundError(
            f'{_RUNFOFEM_EXE} not found at {exe_path}. Set {_FOFEM_DIR_ENV_VAR} to the '
            f'directory containing the official FOFEM 6.9.4 batch runtime.'
        )

    args = [exe_path, str(run_type), os.path.abspath(input_path), os.path.abspath(output_path), os.path.abspath(error_path)]
    if sys.platform == 'linux':
        args.insert(0, 'wine')
    if extra_args:
        args.extend(str(a) for a in extra_args)

    env = os.environ.copy()
    env['FOFEM_DATA'] = fofem_dir
    env['PATH'] = fofem_dir + os.pathsep + env.get('PATH', '')

    result = subprocess.run(
        args,
        cwd=worker_dir,
        env=env,
        capture_output=True,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0,
    )

    real_errors = _read_runfofem_error_file(error_path)
    if result.returncode != 0:
        if (result.returncode & 0xFFFFFFFF) == _STATUS_DLL_NOT_FOUND:
            raise RuntimeError(
                f'{_RUNFOFEM_EXE} failed to start because a required DLL is missing '
                f'(Windows loader status STATUS_DLL_NOT_FOUND). Install the Microsoft Visual '
                f'C++ Redistributable (x64) - see docs/CODEBASE.md - then retry.'
            )
        raise RuntimeError(
            f'runfofem.exe exited with code {result.returncode}. '
            f'Errors: {real_errors or result.stderr.strip() or "(none reported)"}'
        )
    if real_errors:
        raise RuntimeError(f'runfofem.exe reported batch errors: {real_errors}')
    if not helper.file_exists(output_path):
        raise FileNotFoundError(f'runfofem.exe output file not found: {output_path}')


def _restore_plot_id(df: pd.DataFrame, plotid_map: dict) -> pd.DataFrame:
    """
    Restore the original '#PlotId' values using the mapping.

    :param df: DataFrame with underscored '#PlotId' column.
    :param plotid_map: Mapping from underscored to original '#PlotId' values.
    :return: DataFrame with '#PlotId' restored to original values.
    """
    df['#PlotId'] = df['#PlotId'].map(plotid_map).fillna(df['#PlotId'])
    return df


def _write_burnup_params_694(
        out_path: str,
        intensity: float,
        ig_time: float,
        windspeed: float,
        depth: float,
        ambient_temp: float,
) -> None:
    """
    Write a verified 113-switch FOFEM 6.9.4 Burnup parameter file.

    :param out_path: Output path for the Burnup parameter file.
    :param intensity: Heat per unit area (kJ/m^2).
    :param ig_time: Ignition (flame residence) time (seconds).
    :param windspeed: In-stand/mid-flame wind speed (m/s).
    :param depth: Flame depth (m).
    :param ambient_temp: Ambient temperature (degC).
    :return: None. Writes the parameter file to out_path.
    """
    content = _BURNUP_PARAMS_694_TEMPLATE.format(
        intensity=_format_burnup_value(intensity),
        ig_time=_format_burnup_value(ig_time),
        windspeed=_format_burnup_value(windspeed),
        depth=_format_burnup_value(depth),
        ambient_temp=_format_burnup_value(ambient_temp),
    )
    with open(out_path, 'w', newline='\r\n') as f:
        f.write(content)


def _write_consumption_input(
        input_path: str,
        row_series: pd.Series,
        consume_model: str,
        burnup_path: str,
) -> None:
    """
    Write one FOFEM 6.9.4 batch consumption/soil input file for a single plot row.

    Field order is looked up by name from _CONSUMPTION_FIELD_ORDER/_SOIL_FIELD_ORDER/
    _EQUATION_OVERRIDE_COLUMNS, not row_series's own column order, since runfofem.exe's batch
    reader is purely positional. Ambient temperature is read from row_series['temp'] (the
    weather-derived field already present on every merged row) and written only for soil runs,
    in its required position between SoilMoisture and the equation overrides. Also writes the
    three required Expanded Emission Factor group switches (_EFG_STFS/_EFG_CWDRSC/
    _EFG_DUFFRSC) for both consumption and soil modes, per the same fixed values in both
    upstream sample input files.

    :param input_path: Absolute output path for the batch input file.
    :param row_series: Single merged plot/weather row (Imperial units for physical loads/depth;
        must include every field named in _CONSUMPTION_FIELD_ORDER, 'temp', and
        _SOIL_FIELD_ORDER/'SoilFamily'/'SoilMoisture' when consume_model='S').
    :param consume_model: FOFEM consumption model ('C' or 'S').
    :param burnup_path: Absolute path to this row's Burnup parameter file.
    :return: None. Writes the batch input file to input_path.
    """
    field_order = list(_CONSUMPTION_FIELD_ORDER)
    if consume_model == 'S':
        field_order += _SOIL_FIELD_ORDER
    values = [row_series[c] for c in field_order]
    if consume_model == 'S':
        values.append(round(float(row_series['temp']), 2))
    values.extend(row_series[c] for c in _EQUATION_OVERRIDE_COLUMNS)

    def _format(value) -> str:
        """
        Format one batch-input field value as FOFEM expects it.

        :param value: Field value (numeric or categorical string).
        :return: String representation; NaN becomes '0' since FOFEM's parser expects a number.
        """
        if isinstance(value, float) and np.isnan(value):
            return '0'
        return str(value)

    data_line = ','.join(_format(v) for v in values)

    with open(input_path, 'w', newline='\r\n') as f:
        f.write('#1k-SizeClass\n')
        f.write('#ConsumptionEquation\n')
        f.write(f'#EFG-STFS {_EFG_STFS}\n')
        f.write(f'#EFG-CWDRSC {_EFG_CWDRSC}\n')
        f.write(f'#EFG-DuffRSC {_EFG_DUFFRSC}\n')
        f.write(f'#BurnUpFile {os.path.abspath(burnup_path)}\n')
        f.write('#PlotId,Litter\n')
        f.write(data_line + '\n')


def process_emissions(
        plot_wx_fire_csv_path: str,
        plot_id_col_name: str,
        fofem_consume_csv_path: str,
        out_dir: str,
        model_soil_heating: bool = False,
        emissions_units: str = 'SI',
        num_workers: int = 1,
        return_df: bool = False,
) -> Union[None, pd.DataFrame]:
    """
    Process emissions modelling with the official FOFEM 6.9.4 runfofem.exe batch executable.

    :param plot_wx_fire_csv_path: Path to CSV file containing plot weather and fire data.
    :param plot_id_col_name: Name of the unique ID column in the stand fire severity CSV used for merging
        (e.g., 'unique_id').
    :param fofem_consume_csv_path: Path to FOFEM consumption CSV file. Its filename must be one of
        the canonical, unit-bearing names from fofem_units.consume_filename() and must match
        emissions_units.
    :param out_dir: Output directory; each worker gets its own isolated directory under it (with
        its own copy of the FOFEM 6.9.4 runtime, reused across that worker's rows), removed once
        the whole batch completes.
    :param model_soil_heating: Whether to use FOFEM soil heating consumption model (True) or not (False).
    :param emissions_units: Unit system of the values in fofem_consume_csv_path ('SI' or
        'Imperial'). runfofem.exe itself always requires Imperial input and always returns
        Imperial output; SI is supported by converting values immediately before/after the
        executable runs (see _convert_consume_row_to_imperial()). Also determines the unit
        suffixes applied to physical result columns in the final analyst-facing DataFrame and CSV
        (see fofem_units.emissions_result_rename_map()), using the same map as the pyfofem
        backend so both backends expose the same final schema for a given unit system.
    :param num_workers: Number of workers for parallel processing.
    :param return_df: Whether to return the final DataFrame with emissions results (True) or not (False).
    :return: None if return_df is False, otherwise the DataFrame containing the merged input data and
        FOFEM emissions results. A row whose runfofem.exe call failed (e.g. a genuinely
        out-of-range input, such as windspeed exceeding Burnup's documented 0-5 m/s validity
        range) has NaN FOFEM result fields and a non-null 'fofem_gui_error' column naming the
        real cause; each failed plot is also logged once per cause through error_handling, whatever
        the worker count.
    """
    os.makedirs(out_dir, exist_ok=True)

    emissions_units = fofem_units.validate_fofem_units(emissions_units)
    fofem_units.validate_consume_units(fofem_consume_csv_path, emissions_units)

    fofem_dir = _get_fofem_dir()
    consume_model = 'S' if model_soil_heating else 'C'

    merged_df = _get_merged_consumption_df(
        plot_wx_fire_csv_path=plot_wx_fire_csv_path,
        plot_id_col_name=plot_id_col_name,
        fofem_consume_csv_path=fofem_consume_csv_path,
        consume_model=consume_model,
    )
    merged_df = _calc_fuel_moisture_content(merged_df)
    if merged_df.empty:
        helper.export_csv(merged_df, os.path.join(out_dir, 'fofem_emissions_results.csv'))
        return merged_df if return_df else None

    merged_df, plotid_map = _gen_plot_id(merged_df)
    merged_df = _get_pct_crown_burned(merged_df)
    merged_df = _get_season(merged_df)
    merged_df = merged_df.drop(columns=[plot_id_col_name, 'cfb'])

    if num_workers >= 4:
        print(f'\tProcessing Emissions (via official FOFEM 6.9.4 runfofem.exe) in parallel with {num_workers} workers...')
        records = merged_df.to_dict(orient='records')
        out_dirs = [out_dir] * len(merged_df)
        consume_models = [consume_model] * len(merged_df)
        emissions_units_list = [emissions_units] * len(merged_df)
        fofem_dirs = [fofem_dir] * len(merged_df)
        if _TQDM_PROCESS_MAP_AVAILABLE:
            results = process_map(
                _model_emissions,
                records,
                out_dirs,
                consume_models,
                emissions_units_list,
                fofem_dirs,
                max_workers=num_workers,
                desc='Emissions',
                chunksize=1,
            )
        else:
            with concurrent.futures.ProcessPoolExecutor(max_workers=num_workers) as executor:
                results = list(tqdm.tqdm(
                    executor.map(_model_emissions, records, out_dirs, consume_models, emissions_units_list, fofem_dirs),
                    total=len(records),
                    desc='Emissions',
                ))
    else:
        print('\tProcessing Emissions (via official FOFEM 6.9.4 runfofem.exe)...')
        results = [
            _model_emissions(row, out_dir, consume_model, emissions_units, fofem_dir)
            for row in tqdm.tqdm(merged_df.to_dict(orient='records'), desc='Emissions')
        ]

    _log_emissions_failures(results, merged_df, plotid_map)

    # Each worker's own runtime-file copy (_ensure_worker_fofem_runtime()) and directory persist
    # across that worker's rows for reuse, so clean them all up now that the whole batch is done.
    for entry in os.listdir(out_dir):
        if entry.startswith('FOFEM_Emissions_'):
            shutil.rmtree(os.path.join(out_dir, entry), ignore_errors=True)

    fofem_results_df = pd.DataFrame(results)
    helper.export_csv(fofem_results_df, os.path.join(out_dir, 'fofem_results_df_temp.csv'))

    merged_df = merged_df.drop(columns=['remove_hereafter'])
    helper.export_csv(merged_df, os.path.join(out_dir, 'merged_df_temp.csv'))

    final_df = pd.concat([merged_df.reset_index(drop=True), fofem_results_df.reset_index(drop=True)], axis=1)

    # runfofem.exe always returns Imperial-unit results; when SI is configured, convert the
    # analyst-facing result back to SI so both backends expose the same final unit system.
    load_result_cols = [c for c in fofem_units.EMISSIONS_LOAD_RESULT_FIELDS if c in final_df.columns]
    depth_result_cols = [c for c in fofem_units.EMISSIONS_DEPTH_RESULT_FIELDS if c in final_df.columns]
    gas_result_cols = [c for c in fofem_units.EMISSIONS_GAS_RESULT_FIELDS if c in final_df.columns]
    for col in load_result_cols + depth_result_cols + gas_result_cols:
        final_df[col] = pd.to_numeric(final_df[col], errors='coerce')
    if emissions_units == 'SI':
        final_df[load_result_cols] = final_df[load_result_cols] / fofem_units.LOAD_CONV_FACTOR
        final_df[depth_result_cols] = final_df[depth_result_cols] / fofem_units.DEPTH_CONV_FACTOR
        # Mirrors pyfofem's own SI/Imperial emissions_factor convention (emission_calcs.py's
        # unit_conv: SI 1.0, Imperial 2.0) applied to runfofem.exe's Imperial output, since the
        # official FOFEM application implements the same underlying emissions methodology
        # pyfofem reproduces. Not independently verified against runfofem.exe itself for gas
        # emissions; per the plan, the two backends' SI-vs-Imperial values are validated within
        # each backend, not required to numerically match each other.
        final_df[gas_result_cols] = final_df[gas_result_cols] / 2.0

    final_df = final_df.rename(columns=fofem_units.emissions_result_rename_map(emissions_units))
    final_df = _restore_plot_id(final_df, plotid_map)
    final_df = final_df.sort_values(by=['#PlotId', 'wx_date']).reset_index(drop=True)

    csv_out_path = os.path.join(out_dir, 'fofem_emissions_results.csv')
    helper.export_csv(final_df, csv_out_path)

    if return_df:
        return final_df

    return None


# Test routine for FOFEM emissions processing
if __name__ == '__main__':
    examples_dir = helper.get_examples_dir(os.path.dirname(__file__))
    _in_fofem_consume_dir = os.path.join(examples_dir, 'results', 'fuel_analyst')
    _in_fire_data_dir = os.path.join(examples_dir, 'results', 'fofem_mortality')
    _out_dir = os.path.join(examples_dir, 'results', 'fofem_emissions')

    _plot_wx_fire_csv_path = os.path.join(_in_fire_data_dir, 'fofem_severity_results.csv')
    _fofem_consume_csv_path = os.path.join(_in_fofem_consume_dir, fofem_units.consume_filename('SI'))
    _plot_id_col_name = 'unique_id'

    process_emissions(
        plot_wx_fire_csv_path=_plot_wx_fire_csv_path,
        plot_id_col_name=_plot_id_col_name,
        fofem_consume_csv_path=_fofem_consume_csv_path,
        out_dir=_out_dir,
        num_workers=os.cpu_count() - 1,
    )
