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

logger = logging.getLogger(__name__)


def gen_fofem_gui_app_tree_df(df: pd.DataFrame, master_tree_df: pd.DataFrame) -> pd.DataFrame:
    """
    Generate a DataFrame formatted for FOFEM tree mortality modeling.

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
    :return: DataFrame with FOFEM tree mortality variables.
    """
    master_tree_df = fofem_mortality.filter_live_trees(
        master_tree_df, logger, 'fofem_attributes_missing_status_column'
    )

    # Prepare lookup dictionaries
    treatment_dict = df.set_index('unique_id')['treatment_type'].to_dict()
    year_dict = df.set_index('unique_id')['year'].to_dict()

    # Build DataFrame
    fofem_tree_df = pd.DataFrame({
        '# PlotId': master_tree_df['unique_id'],
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
        'FlHt_ScHt': np.nan,
        'FL_SH_ID': 'F',
        'Severity': np.nan
    })

    return fofem_tree_df


def gen_fofem_consumption_df(
        df: pd.DataFrame,
        fofem_consume_params: dict,
) -> pd.DataFrame:
    """
    Generate a DataFrame formatted for FOFEM consumption/emissions modeling.

    This function maps and converts relevant columns from the plot-level DataFrame to the FOFEM-required format,
    including unit conversions, moisture regime assignment, and categorical mappings.

    :param df: DataFrame with plot-level data.
    :param fofem_consume_params: Dictionary of FOFEM consumption parameters, including region, season,
        moisture regime, and soil heating options.
    :return: DataFrame with FOFEM consumption variables.
    """
    # Extract FOFEM input parameters from the provided dictionary
    fofem_region = fofem_consume_params['region']
    fofem_season = fofem_consume_params['season']
    moist_regime = fofem_consume_params['moisture_regime']
    model_soil_heat = fofem_consume_params['soil_heating']['use_soil_heating']

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

    # Conversion factor from kg/m^2 to tons/acre
    conv = 4.46089561

    # Build the FOFEM consumption DataFrame with required variables and unit conversions
    fofem_consume_df = pd.DataFrame({
        '#PlotId': df.unique_id,
        'Litter': (df['ffl_litter_kgpm2'] * conv).round(2).fillna(0),
        'wfl1Hour': ((df['woody_kgpm2_fofem_sound_0_635'] +
                       df['woody_kgpm2_fofem_rotten_0_635']) * conv).round(2).fillna(0),
        'wfl10Hour': ((df['woody_kgpm2_fofem_sound_2_54'] +
                        df['woody_kgpm2_fofem_rotten_2_54']) * conv).round(2).fillna(0),
        'wfl10HourMoisture': fofem_moist_regime[1],
        'wfl100Hour': ((df['woody_kgpm2_fofem_sound_7_62'] +
                         df['woody_kgpm2_fofem_rotten_7_62']) * conv).round(2).fillna(0),
        'wfl3_6S': (df['woody_kgpm2_fofem_sound_15_24'] * conv).round(2).fillna(0),
        'wfl6_9S': (df['woody_kgpm2_fofem_sound_22_86'] * conv).round(2).fillna(0),
        'wfl9_20S': (df['woody_kgpm2_fofem_sound_50_8'] * conv).round(2).fillna(0),
        'wfl20plusS': (df['woody_kgpm2_fofem_sound_gt50_8'] * conv).round(2).fillna(0),
        'wfl3_6R': (df['woody_kgpm2_fofem_rotten_15_24'] * conv).round(2).fillna(0),
        'wfl6_9R': (df['woody_kgpm2_fofem_rotten_22_86'] * conv).round(2).fillna(0),
        'wfl9_20R': (df['woody_kgpm2_fofem_rotten_50_8'] * conv).round(2).fillna(0),
        'wfl20plusR': (df['woody_kgpm2_fofem_rotten_gt50_8'] * conv).round(2).fillna(0),
        'wfl1000HourMoisture': fofem_moist_regime[2],
        'Duff': (df['ffl_duff_kgpm2'] * conv).round(2).fillna(0),
        'DuffMoisture': fofem_moist_regime[0],
        'DuffDepth': (df['stand_duff_depth_cm'] / 2.54).round(2).fillna(0),
        'Herbaceous': (df['herbs_kgpm2'] * conv).round(2).fillna(0),
        'Shrub': (df['shrubs_kgpm2'] * conv).round(2).fillna(0),
        'CrownFoliage': (df['stand_foliage_fofem_kgpm2_sum'] * conv).round(2).fillna(0),
        'CrownBranch': (df['stand_branches_fofem_kgpm2_sum'] * conv).round(2).fillna(0),
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
