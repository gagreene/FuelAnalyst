# -*- coding: utf-8 -*-
"""
Created on Tue Sep 08, 17:00:00 2026

@author: Gregory A. Greene
"""
__author__ = ['Gregory A. Greene']

import os

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
# directly against dependencies/pyfofem source, not the module's own (partially inaccurate, e.g.
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
