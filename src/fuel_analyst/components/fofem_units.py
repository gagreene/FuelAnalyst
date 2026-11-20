# -*- coding: utf-8 -*-
"""
Created on Tue Sep 08, 17:00:00 2026

@author: Gregory A. Greene
"""
__author__ = ['Gregory A. Greene']

import logging
import os

import numpy as np
import pandas as pd

BURNUP_IGNITION_INTENSITY_COLUMN = 'burnup_ign_intensity_kWpm2'
FOFEM_SCENARIO_ID = '_fofem_scenario_id'
VALID_FOFEM_UNITS = ('SI', 'Imperial')

LOAD_CONV_FACTOR = 4.46089561  # kg/m2 -> US short tons/acre
DEPTH_CONV_FACTOR = 1 / 2.54   # cm -> inches

FOFEM_LOAD_COLUMNS = [
    'Litter', 'Duff', 'Herbaceous', 'Shrub', 'CrownFoliage', 'CrownBranch',
    'wfl1Hour', 'wfl10Hour', 'wfl100Hour',
    'wfl3_6S', 'wfl6_9S', 'wfl9_20S', 'wfl20plusS',
    'wfl3_6R', 'wfl6_9R', 'wfl9_20R', 'wfl20plusR',
]
FOFEM_DEPTH_COLUMNS = ['DuffDepth']

_SI_FILENAME = 'fofem_consume_si_df.csv'
_IMPERIAL_FILENAME = 'fofem_consume_imperial_df.csv'
_CONSUME_FILENAME_UNITS = {
    _SI_FILENAME: 'SI',
    _IMPERIAL_FILENAME: 'Imperial',
}

# Final emissions/consumption RESULT fields (pyfofem.run_fofem_emissions()'s return dict, per
# emission_pipeline.py's build_emissions_result()), grouped by actual output dimension. Verified
# directly against the pyfofem-fire-effects source, not the module's own (partially inaccurate, e.g.
# 'Shurb-Equ' vs the EQUATION_VARS constant's 'Shrub-Equ') exported name lists. Loads (kg/m2 or
# US short tons/acre):
EMISSIONS_LOAD_RESULT_FIELDS = [
    'LitPre', 'LitCon', 'LitPos',
    'DW1Pre', 'DW1Con', 'DW1Pos',
    'DW10Pre', 'DW10Con', 'DW10Pos',
    'DW100Pre', 'DW100Con', 'DW100Pos',
    'DW1kSndPre', 'DW1kSndCon', 'DW1kSndPos',
    'DW1kRotPre', 'DW1kRotCon', 'DW1kRotPos',
    'DufPre', 'DufCon', 'DufPos',
    'HerPre', 'HerCon', 'HerPos',
    'ShrPre', 'ShrCon', 'ShrPos',
    'FolPre', 'FolCon', 'FolPos',
    'BraPre', 'BraCon', 'BraPos',
    'FlaCon', 'SmoCon',  # total load consumed during the flaming/smoldering phase
]
# The official FOFEM 6.9.4 runfofem.exe backend (fofem_gui_emissions.py) reports coarse woody
# debris across eight sound/rotten size classes (3-6", 6-9", 9-20", 20"+) instead of pyfofem's
# single combined sound/rotten pair above (DW1kSndPre/DW1kRotPre) - a genuine, intentional schema
# difference between the two backends' emissions output, not a naming inconsistency to reconcile.
# Verified against real runfofem.exe output (src/fuel_analyst/supporting_data/fofem_694).
EMISSIONS_COARSE_WOODY_694_LOAD_RESULT_FIELDS = [
    f'{size}{phase}'
    for size in ('Snd3', 'Snd6', 'Snd9', 'Snd20', 'Rot3', 'Rot6', 'Rot9', 'Rot20')
    for phase in ('Pre', 'Con', 'Pos')
]
EMISSIONS_LOAD_RESULT_FIELDS = EMISSIONS_LOAD_RESULT_FIELDS + EMISSIONS_COARSE_WOODY_694_LOAD_RESULT_FIELDS
# Depths (cm or inches):
EMISSIONS_DEPTH_RESULT_FIELDS = ['DufDepPre', 'DufDepCon', 'DufDepPos']
# Durations (seconds, unit-system-independent):
EMISSIONS_DURATION_RESULT_FIELDS = ['FlaDur', 'SmoDur']
# Percentages on a 0-100 scale (unit-system-independent): MSE is mineral soil exposure (%), per
# consm_mineral_soil()'s own docstring.
EMISSIONS_PERCENT_RESULT_FIELDS = ['MSE']
# Temperatures (always degrees Celsius - pyfofem's soil-heating model compares against fixed
# 60/275 degC thresholds regardless of emissions_units; see components/pyfofem.py's soil-heating
# block):
EMISSIONS_TEMPERATURE_RESULT_FIELDS = ['Lay0', 'Lay2', 'Lay4', 'Lay6']
# Smoke-emission masses (g/m2 SI or lb/acre Imperial, per emission_calcs.calc_smoke_emissions()):
EMISSIONS_GAS_RESULT_FIELDS = [
    'PM10F', 'PM10S', 'PM25F', 'PM25S', 'CH4F', 'CH4S', 'COF', 'COS', 'CO2F', 'CO2S',
    'NOXF', 'NOXS', 'SO2F', 'SO2S',
    'PM10S_Duff', 'PM25S_Duff', 'CH4S_Duff', 'COS_Duff', 'CO2S_Duff', 'NOXS_Duff', 'SO2S_Duff',
]
# Deliberately left unsuffixed (not physical quantities): 'Lay60d'/'Lay275d' are layer-index
# codes (which depth layer first exceeded the 60/275 degC threshold, or -1), not depths, despite
# their names - verified against pyfofem.py's soil-heating block; the equation-identifier fields
# 'Lit-Equ', 'DufCon-Equ', 'DufRed-Equ', 'MSE-Equ', 'Herb-Equ', 'Shurb-Equ'; and the status/error
# codes 'BurnupLimitAdj', 'BurnupError'.


def add_burnup_ignition_intensity(df: pd.DataFrame) -> None:
    """
    Calculate Burnup ignition intensity and put it after the flame columns.

    :param df: Fire results with head fireline intensity and horizontal flame depth.
    :raises ValueError: If either required fire input column is missing.
    :return: None. Inserts or replaces the Burnup ignition intensity column in df.
    """
    missing = [column for column in ('hfi', 'flame_depth_m') if column not in df]
    if missing:
        raise ValueError(f'Missing required column(s) for Burnup ignition intensity: {missing}')

    hfi = pd.to_numeric(df['hfi'], errors='coerce').to_numpy(dtype=float, na_value=np.nan)
    depth = pd.to_numeric(df['flame_depth_m'], errors='coerce').to_numpy(dtype=float, na_value=np.nan)
    if BURNUP_IGNITION_INTENSITY_COLUMN in df:
        del df[BURNUP_IGNITION_INTENSITY_COLUMN]
    last_flame_column = max(index for index, name in enumerate(df.columns) if name.startswith('flame_'))
    df.insert(last_flame_column + 1, BURNUP_IGNITION_INTENSITY_COLUMN, calc_burnup_ignition_intensity(hfi, depth))


def calc_burnup_ignition_intensity(hfi: float | np.ndarray, flame_depth_m: float | np.ndarray) -> np.ndarray:
    """
    Convert head fireline intensity to Burnup ignition intensity.

    :param hfi: Head fireline intensity (kW/m), as a scalar or array.
    :param flame_depth_m: Horizontal flame depth (m), with the same shape as hfi.
    :return: Ignition intensity (kW/m²), with NaN for invalid inputs or a nonfinite result.
    """
    fireline_intensity = np.asarray(hfi, dtype=float)
    flame_depth = np.asarray(flame_depth_m, dtype=float)
    valid = np.isfinite(fireline_intensity) & (fireline_intensity >= 0) & np.isfinite(flame_depth) & (flame_depth > 0)
    intensity = np.full(fireline_intensity.shape, np.nan)
    with np.errstate(over='ignore'):
        np.divide(fireline_intensity, flame_depth, out=intensity, where=valid)
    return np.where(np.isfinite(intensity), intensity, np.nan)


def consume_filename(units: str) -> str:
    """
    Get the canonical, unit-bearing FOFEM consumption CSV filename for a unit system.

    :param units: FOFEM processing units ('SI' or 'Imperial').
    :return: 'fofem_consume_si_df.csv' for SI or 'fofem_consume_imperial_df.csv' for Imperial.
    """
    units = validate_fofem_units(units)
    return _SI_FILENAME if units == 'SI' else _IMPERIAL_FILENAME


def emissions_result_rename_map(units: str) -> dict:
    """
    Build the explicit rename map from pyFOFEM's raw result field names to unit-suffixed,
    analyst-facing column names, for a given processing-unit system.

    Shared by both emissions backends (fofem_emissions.py's pyfofem backend and
    fofem_gui_emissions.py's legacy fof_gui backend) so a given unit system always produces the
    same final result schema regardless of which backend produced it. Fields not covered by this
    map (equation identifiers, error/status codes, and the soil-heating layer-index codes
    'Lay60d'/'Lay275d') are deliberately left unsuffixed and are absent from the returned map;
    applying the map with DataFrame.rename() leaves those columns untouched.

    :param units: FOFEM processing units ('SI' or 'Imperial').
    :return: Dict mapping each known raw pyFOFEM result field name to its unit-suffixed name.
    """
    units = validate_fofem_units(units)
    load_suffix = '_kgpm2' if units == 'SI' else '_tpac'
    depth_suffix = '_cm' if units == 'SI' else '_in'
    emissions_suffix = '_gpm2' if units == 'SI' else '_lbpac'

    rename_map = {}
    for field in EMISSIONS_LOAD_RESULT_FIELDS:
        rename_map[field] = f'{field}{load_suffix}'
    for field in EMISSIONS_DEPTH_RESULT_FIELDS:
        rename_map[field] = f'{field}{depth_suffix}'
    for field in EMISSIONS_DURATION_RESULT_FIELDS:
        rename_map[field] = f'{field}_sec'
    for field in EMISSIONS_PERCENT_RESULT_FIELDS:
        rename_map[field] = f'{field}_pct'
    for field in EMISSIONS_TEMPERATURE_RESULT_FIELDS:
        rename_map[field] = f'{field}_degC'
    for field in EMISSIONS_GAS_RESULT_FIELDS:
        rename_map[field] = f'{field}{emissions_suffix}'
    return rename_map


def infer_consume_units(path: str) -> str:
    """
    Infer the unit system of a FOFEM consumption CSV from its canonical filename.

    :param path: Path to a FOFEM consumption CSV file.
    :return: 'SI' or 'Imperial', inferred strictly from the file's basename.
    :raises ValueError: If the basename is not one of the two canonical, unit-bearing filenames
        (this includes the old, unit-ambiguous 'fofem_consume_df.csv' name and any other renamed
        or user-supplied file), since units cannot be inferred from an unrecognized name.
    """
    basename = os.path.basename(path)
    if basename not in _CONSUME_FILENAME_UNITS:
        raise ValueError(
            f'Cannot infer FOFEM processing units from filename "{basename}". Expected one of '
            f'{sorted(_CONSUME_FILENAME_UNITS)}. Rename the file to a canonical unit-bearing '
            f'name (see fofem_units.consume_filename()) before processing it.'
        )
    return _CONSUME_FILENAME_UNITS[basename]


def prepare_burnup_ignition_inputs(df: pd.DataFrame, plot_id_col_name: str, logger: logging.Logger) -> pd.DataFrame:
    """
    Calculate ignition intensity and skip invalid scenarios before emissions dispatch.

    :param df: Merged consumption and fire rows. The ignition intensity column is added in place.
    :param plot_id_col_name: Column identifying the plot for each scenario.
    :param logger: Adapter logger used to report one warning per affected plot.
    :return: Copy of the rows with finite ignition intensity.
    """
    add_burnup_ignition_intensity(df)
    valid_ignition = df[BURNUP_IGNITION_INTENSITY_COLUMN].notna()
    for plot_id in df.loc[~valid_ignition, plot_id_col_name].drop_duplicates():
        logger.warning(
            'FOFEM emissions scenarios skipped: Burnup requires finite non-negative hfi and '
            'finite positive flame depth (flame_depth_m).',
            extra={'unique_id': plot_id, 'issue_code': 'fofem_burnup_ignition_invalid'},
        )
    return df.loc[valid_ignition].copy()


def validate_consume_plot_ids(plot_ids: pd.Series, fire_plot_ids: pd.Series) -> None:
    """
    Check that every plot has a single set of FOFEM consumption inputs.

    :param plot_ids: Consumption CSV plot IDs.
    :param fire_plot_ids: Plot IDs present in the fire input.
    :return: None. Raises ValueError if an input plot has repeated consumption rows.
    """
    matched = plot_ids.loc[plot_ids.isin(fire_plot_ids.dropna())]
    duplicates = matched.loc[matched.duplicated()].unique().tolist()
    if duplicates:
        raise ValueError(f'FOFEM consumption CSV contains duplicate #PlotId values: {duplicates}.')


def validate_consume_units(path: str, configured_units: str) -> None:
    """
    Validate that a FOFEM consumption CSV's filename matches the configured processing units.

    :param path: Path to a FOFEM consumption CSV file.
    :param configured_units: The processing units ('SI' or 'Imperial') the caller intends to use
        for this file.
    :return: None. Raises if the file and configured units disagree.
    :raises ValueError: If configured_units is invalid, if the filename is not one of the two
        canonical unit-bearing names, or if the inferred filename units do not match
        configured_units.
    """
    configured_units = validate_fofem_units(configured_units)
    inferred_units = infer_consume_units(path)
    if inferred_units != configured_units:
        raise ValueError(
            f'FOFEM consumption CSV "{os.path.basename(path)}" is in {inferred_units} units, '
            f'but processing is configured for {configured_units} units. Point to the matching '
            f'file (see fofem_units.consume_filename()) or correct the configured '
            f'"fofem_processing_units"/"emissions_units" setting.'
        )


def validate_fofem_scenario_ids(values: pd.Series) -> pd.Series:
    """
    Validate and normalize the private keys for FOFEM scenario joins.

    :param values: Scenario IDs from a fire input or a backend result.
    :return: Unique non-negative scenario IDs as signed 64-bit integers.
    """
    numeric = pd.to_numeric(values, errors='coerce')
    invalid = numeric.isna() | numeric.lt(0) | numeric.ge(2 ** 63) | numeric.mod(1).ne(0)
    if invalid.any() or not numeric.is_unique:
        raise ValueError('FOFEM scenario identifiers must be unique non-negative integers.')
    return numeric.astype('int64')


def validate_fofem_units(units: str) -> str:
    """
    Validate a FOFEM processing-units string.

    :param units: Candidate processing units string.
    :return: The validated units string, unchanged.
    :raises ValueError: If units is not exactly 'SI' or 'Imperial'.
    """
    if units not in VALID_FOFEM_UNITS:
        raise ValueError(
            f'Invalid FOFEM processing units "{units}". Valid options: {VALID_FOFEM_UNITS}'
        )
    return units
