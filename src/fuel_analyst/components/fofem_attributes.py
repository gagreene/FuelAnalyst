# -*- coding: utf-8 -*-
"""
Created on Wed June 4, 10:00:00 2025

@author: Gregory A. Greene
"""
__author__ = ['Gregory A. Greene']

import logging

import pandas as pd
import numpy as np

from . import fofem_mortality
from . import helper
from . import fofem_units

logger = logging.getLogger(__name__)

_CONSUMPTION_COLUMNS = [
    '#PlotId',
    'Litter',
    'wfl1Hour',
    'wfl10Hour',
    'wfl10HourMoisture',
    'wfl100Hour',
    'wfl3_6S',
    'wfl6_9S',
    'wfl9_20S',
    'wfl20plusS',
    'wfl3_6R',
    'wfl6_9R',
    'wfl9_20R',
    'wfl20plusR',
    'wfl1000HourMoisture',
    'Duff',
    'DuffMoisture',
    'DuffDepth',
    'Herbaceous',
    'Shrub',
    'CrownFoliage',
    'CrownBranch',
    'PercentCrownBurned',
    'Region',
    'CoverGroup',
    'Season',
    'FuelCategory',
    'SoilFamily',
    'SoilMoisture',
    'LitterLoad_ConsumEq1',
    'PctDuff_ConsumEq2',
    'DuffDepth_ConsumEq3',
    'MSE_ConsumEq4',
    'Herb_ConsumEq5',
    'Shrub_ConsumEq6',
    'remove_hereafter',
    'fuel_bed_depth_m',
]


def gen_fofem_gui_app_tree_df(df: pd.DataFrame, master_tree_df: pd.DataFrame) -> pd.DataFrame:
    """
    Generate a DataFrame formatted as a FOFEM 6.9.4 batch mortality (.tre) input file.

    FuelAnalyst does not run tree mortality through the official FOFEM application itself;
    this DataFrame is a hand-off point the analyst submits to their own FOFEM 6.9.4
    installation (GUI or runfofem.exe, run type 2). Column names/order match the real
    verified 6.9.4 .tre format exactly - notably 'PlotId' (no leading '#'), 'FlHt/ScHt', and
    'FS', not the '# PlotId'/'FlHt_ScHt'/'FL_SH_ID' names used elsewhere in FuelAnalyst for
    unrelated CSVs - confirmed by feeding this function's real output directly through the
    bundled runfofem.exe (src/fuel_analyst/supporting_data/fofem_694).

    All output values use US units as required by FOFEM:
      - TreeExpansionFactor: trees/acre (input: trees/ha)
      - Diameter: inches (input: cm)
      - TreeHeight, CrownBaseHeight: feet (input: m)
      - CrownRatio: percent (dimensionless ratio, no conversion needed)

    master_tree_df is filtered to live trees only via
    fofem_mortality.filter_live_trees() before building the output, since
    dead trees have no crown depth and modelling their mortality is
    meaningless - they are already dead.

    :param df: DataFrame with plot-level data (must include 'unique_id', 'treatment_type', 'year').
    :param master_tree_df: DataFrame with processed tree-level data.
    :return: DataFrame with FOFEM tree mortality variables, ready to export as a 6.9.4 .tre input.
    """
    master_tree_df = fofem_mortality.filter_live_trees(
        master_tree_df, logger, 'fofem_attributes_missing_status_column'
    )

    # Prepare lookup dictionaries
    treatment_dict = df.set_index('unique_id')['treatment_type'].to_dict()
    year_dict = df.set_index('unique_id')['year'].to_dict()

    # Build DataFrame
    fofem_tree_df = pd.DataFrame({
        'PlotId': master_tree_df['unique_id'],
        'MonStatus': master_tree_df['unique_id'].map(treatment_dict),
        'MonOrder': master_tree_df['unique_id'].map(year_dict),
        'TreeSpecies': master_tree_df['spp_fofem'],
        'TreeExpansionFactor': master_tree_df['dens_live_ha'] / 2.47105,  # ha to acre
        'Diameter': master_tree_df['dbh'] / 2.54,  # cm to inches
        'TreeHeight': master_tree_df['ht'] * 3.28084,  # m to feet
        'CrownBaseHeight': (master_tree_df['ht'] - master_tree_df['crown_depth']) * 3.28084,  # m to feet
        'TreeStatus': np.where(
            (master_tree_df['decay_cnfr'] == 1) | (master_tree_df['decay_brdlf'] == 1), 'H',
            np.where((master_tree_df['decay_cnfr'] == 2) | (master_tree_df['decay_brdlf'] == 2), 'U', 'L')
        ),
        'CrownClass': master_tree_df['crown_class'],
        'CrownRatio': 100 * master_tree_df['crown_depth'] / master_tree_df['ht'],
        'CharHeight': np.nan,
        'CrownScorchPercent': np.nan,
        'CrownScorchHeight': np.nan,
        'CKR': np.nan,
        'BeetleDamage': np.nan,
        'EquationType': 'CRNSCH',
        'FlHt/ScHt': np.nan,
        'FS': 'F',
        'Severity': np.nan
    })

    return fofem_tree_df


def gen_fofem_consumption_df(
        df: pd.DataFrame,
        fofem_consume_params: dict,
) -> pd.DataFrame:
    """
    Generate a DataFrame formatted for FOFEM consumption/emissions modeling.

    This function maps relevant columns from the plot-level DataFrame (already SI) to the
    FOFEM-required column names, moisture regime assignment, and categorical mappings. Column
    names and order are fixed and unsuffixed regardless of fofem_processing_units, since the
    legacy FOFEM GUI batch reader treats the header row as a comment and depends on field order,
    not field names; the unit system is instead communicated by the output filename (see
    fofem_units.consume_filename()). Fuel-load fields (kg/m2 or US short tons/acre) and
    DuffDepth (cm or inches) are the only fields affected by fofem_processing_units; region,
    cover group, season, fuel category, soil fields, moisture percentages, the six
    '_ConsumEq' equation overrides, 'remove_hereafter', and 'fuel_bed_depth_m' (always metres)
    are unit-agnostic or permanently fixed and are never converted. Fuel-load and DuffDepth
    values are returned at full float precision; rounding is left to the specific consumer
    (e.g. the fof_gui batch-file writer) that actually requires it.

    :param df: Plot data with collected Trees-parent and observation markers. Unknown
        tree observations are omitted; confirmed all-N absence retains surface fuels.
    :param fofem_consume_params: Dictionary of FOFEM consumption parameters, including region, season,
        moisture regime, soil heating options, and 'fofem_processing_units' ('SI' or 'Imperial';
        defaults to 'SI' when the key is absent).
    :return: DataFrame with FOFEM consumption variables.
    """
    # Apply the same known-tree/explicit-absence decision as the ConPyro input writer.
    df = helper.prepare_tree_model_inputs(df)

    # Extract FOFEM input parameters from the provided dictionary
    fofem_region = fofem_consume_params['region']
    fofem_season = fofem_consume_params['season']
    moist_regime = fofem_consume_params['moisture_regime']
    model_soil_heat = fofem_consume_params['soil_heating']['use_soil_heating']
    processing_units = fofem_units.validate_fofem_units(
        fofem_consume_params.get('fofem_processing_units', 'SI')
    )
    if df.empty:
        return pd.DataFrame(columns=_CONSUMPTION_COLUMNS, index=df.index)

    # Moisture regime lookup table: [Duff, 10hr, 1000hr, Soil]
    fofem_moist_regime_dict = {
        'Wet': [130, 22, 40, 25],
        'Moderate': [75, 16, 30, 15],
        'Dry': [40, 10, 15, 10],
        'Very Dry': [20, 6, 10, 5]
    }
    # Select moisture regime values, defaulting to 'Very Dry' if not found
    fofem_moist_regime = fofem_moist_regime_dict.get(moist_regime, fofem_moist_regime_dict['Very Dry'])

    # Assign CoverGroup based on dominant species and substrate codes
    fofem_cover_group = np.where(
        df.SPECIES_CD_1 == 'PY', 'Ponderosa',
        np.where(df['SPECIES_CD_1'].isin([
            'B', 'BA', 'BB', 'BG', 'BL', 'BN', 'S', 'SA', 'SB', 'SE', 'SR',
            'SS', 'SW', 'SXB', 'SXE', 'SXL', 'SXS', 'SXW', 'SXX'
        ]), 'BalBRWSpr',
        np.where(df['SPECIES_CD_1'].isin(['P', 'PJ', 'PL', 'PLC', 'PLI', 'PR']), 'RedJacPin',
        np.where(df['SPECIES_CD_1'].isin(['PW', 'PE', 'H', 'HW', 'HX', 'HXM']), 'WhiPinHem',
        np.where(df['dom_substrate'].isin(['SL', 'ST']), df['fofem_shrub_group'],
        np.where(df['dom_substrate'].isin(['HF', 'HG']), 'GrassGroup', '""')))))
    )

    # Assign FuelCategory based on treatment type
    fofem_fuel_category = np.where(
        df.treatment_type.isin(['untreated', 'burned']),
        'Natural',
        np.where(df.treatment_type == 'treated', 'Slash', 'Piles')
    )

    # Conversion factors from the SI source values (kg/m2, cm) to Imperial (US short tons/acre, in);
    # 1.0 leaves the SI source values unconverted when processing_units == 'SI'
    load_conv = fofem_units.LOAD_CONV_FACTOR if processing_units == 'Imperial' else 1.0
    depth_conv = fofem_units.DEPTH_CONV_FACTOR if processing_units == 'Imperial' else 1.0

    # Build the FOFEM consumption DataFrame with required variables and unit conversions.
    # Column names/order are fixed regardless of processing_units - see docstring.
    fofem_consume_df = pd.DataFrame({
        '#PlotId': df.unique_id,
        'Litter': (df['ffl_litter_kgpm2'] * load_conv).fillna(0),
        # A missing sound or rotten class means no pieces, so each is filled with 0 before the two are added;
        # filling after the addition would turn a class with only one of them into 0
        'wfl1Hour': ((df['woody_kgpm2_fofem_sound_0_635'].fillna(0) +
                      df['woody_kgpm2_fofem_rotten_0_635'].fillna(0)) * load_conv),
        'wfl10Hour': ((df['woody_kgpm2_fofem_sound_2_54'].fillna(0) +
                       df['woody_kgpm2_fofem_rotten_2_54'].fillna(0)) * load_conv),
        'wfl10HourMoisture': fofem_moist_regime[1],
        'wfl100Hour': ((df['woody_kgpm2_fofem_sound_7_62'].fillna(0) +
                        df['woody_kgpm2_fofem_rotten_7_62'].fillna(0)) * load_conv),
        'wfl3_6S': (df['woody_kgpm2_fofem_sound_15_24'] * load_conv).fillna(0),
        'wfl6_9S': (df['woody_kgpm2_fofem_sound_22_86'] * load_conv).fillna(0),
        'wfl9_20S': (df['woody_kgpm2_fofem_sound_50_8'] * load_conv).fillna(0),
        'wfl20plusS': (df['woody_kgpm2_fofem_sound_gt50_8'] * load_conv).fillna(0),
        'wfl3_6R': (df['woody_kgpm2_fofem_rotten_15_24'] * load_conv).fillna(0),
        'wfl6_9R': (df['woody_kgpm2_fofem_rotten_22_86'] * load_conv).fillna(0),
        'wfl9_20R': (df['woody_kgpm2_fofem_rotten_50_8'] * load_conv).fillna(0),
        'wfl20plusR': (df['woody_kgpm2_fofem_rotten_gt50_8'] * load_conv).fillna(0),
        'wfl1000HourMoisture': fofem_moist_regime[2],
        'Duff': (df['ffl_duff_kgpm2'] * load_conv).fillna(0),
        'DuffMoisture': fofem_moist_regime[0],
        'DuffDepth': (df['stand_duff_depth_cm'] * depth_conv).fillna(0),
        'Herbaceous': (df['herbs_kgpm2'] * load_conv).fillna(0),
        'Shrub': (df['shrubs_kgpm2'] * load_conv).fillna(0),
        'CrownFoliage': (df['stand_foliage_fofem_kgpm2_sum'] * load_conv).fillna(0),
        'CrownBranch': (df['stand_branches_fofem_kgpm2_sum'] * load_conv).fillna(0),
        'PercentCrownBurned': 0,
        'Region': fofem_region,
        'CoverGroup': fofem_cover_group,
        'Season': fofem_season,
        'FuelCategory': fofem_fuel_category,
        'SoilFamily': df['SoilFamily'] if model_soil_heat else 'NA',
        'SoilMoisture': fofem_moist_regime[3],
        'LitterLoad_ConsumEq1': -1,
        'PctDuff_ConsumEq2': -1,
        'DuffDepth_ConsumEq3': -1,
        'MSE_ConsumEq4': -1,
        'Herb_ConsumEq5': -1,
        'Shrub_ConsumEq6': -1,
        'remove_hereafter': np.nan,
        'fuel_bed_depth_m': (df['fuel_bed_depth_m']).round(2).fillna(0),
    })

    return fofem_consume_df
