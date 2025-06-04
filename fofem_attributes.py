# -*- coding: utf-8 -*-
"""
Created on Wed June 4, 10:00:00 2025

@author: Gregory A. Greene
"""
__author__ = ['Gregory A. Greene, map.n.trowel@gmail.com']

import pandas as pd
import numpy as np


def _gen_fofem_tree_df(df: pd.DataFrame, master_tree_df: pd.DataFrame) -> pd.DataFrame:
    """
    Generate a DataFrame formatted for FOFEM tree mortality modeling.

    Maps and converts relevant columns from the master tree DataFrame and plot DataFrame
    to the FOFEM-required format, including unit conversions and status assignments.

    :param df: DataFrame with plot-level data (must include 'uniqueID', 'treatment_type', 'year').
    :param master_tree_df: DataFrame with processed tree-level data.
    :return: DataFrame with FOFEM tree mortality variables.
    """
    fofem_tree_df = pd.DataFrame()

    # Map plot and tree attributes to FOFEM columns
    fofem_tree_df['# PlotId'] = master_tree_df['unique_id']
    fofem_tree_df['MonStatus'] = fofem_tree_df['# PlotId'].map(
        df.set_index('unique_id')['treatment_type'].to_dict())
    fofem_tree_df['MonOrder'] = fofem_tree_df['# PlotId'].map(
        df.set_index('unique_id')['year'].to_dict())
    fofem_tree_df['TreeSpecies'] = master_tree_df['spp_fofem']
    fofem_tree_df['TreeExpansionFactor'] = master_tree_df['dens_live_ha'] / 2.47105  # ha to acre
    fofem_tree_df['Diameter'] = master_tree_df['dbh'] / 2.54  # cm to inches
    fofem_tree_df['TreeHeight'] = master_tree_df['ht'] / 3.28084  # m to feet
    fofem_tree_df['CrownBaseHeight'] = (master_tree_df['ht'] - master_tree_df['crown_depth']) / 3.28084  # m to feet

    # Assign tree status for FOFEM: H = healthy, U = unhealthy, L = other
    fofem_tree_df['TreeStatus'] = np.where(
        (master_tree_df['decay_cnfr'] == 1) | (master_tree_df['decay_brdlf'] == 1), 'H',
        np.where((master_tree_df['decay_cnfr'] == 2) | (master_tree_df['decay_brdlf'] == 2), 'U', 'L')
    )

    fofem_tree_df['CrownClass'] = master_tree_df['crown_class']
    fofem_tree_df['CrownRatio'] = 100 * master_tree_df['crown_depth'] / master_tree_df['ht']

    # Set FOFEM-specific columns to NaN or default values
    fofem_tree_df['CharHeight'] = np.nan
    fofem_tree_df['CrownScorchPercent'] = np.nan
    fofem_tree_df['CrownScorchHeight'] = np.nan
    fofem_tree_df['CKR'] = np.nan
    fofem_tree_df['BeetleDamage'] = np.nan
    fofem_tree_df['EquationType'] = 'CRNSCH'
    fofem_tree_df['FlHt_ScHt'] = np.nan
    fofem_tree_df['FL_SH_ID'] = 'F'
    fofem_tree_df['Severity'] = np.nan

    return fofem_tree_df


def _gen_fofem_consumption_df(df: pd.DataFrame, moisture_var: str = 'Very Dry') -> pd.DataFrame:
    """
    Generate a DataFrame formatted for FOFEM consumption/emissions modeling.

    Maps and converts relevant columns from the plot DataFrame to the FOFEM-required format,
    including unit conversions, moisture regime assignment, and categorical mappings.

    :param df: DataFrame with plot-level data.
    :param moisture_var: Moisture regime key ('Wet', 'Moderate', 'Dry', 'Very Dry').
    :return: DataFrame with FOFEM consumption variables.
    """
    # Moisture regime lookup: [Duff, 10hr, 1000hr, Soil]
    fofem_moist_regime_dict = {
        'Wet': [130, 22, 40, 25],
        'Moderate': [75, 16, 30, 15],
        'Dry': [40, 10, 15, 10],
        'Very Dry': [20, 6, 10, 5]
    }
    fofem_moist_regime = fofem_moist_regime_dict.get(moisture_var, fofem_moist_regime_dict['Very Dry'])

    # Conversion factor: kg/m2 to tons/acre
    conv = 4.46089561

    fofem_consume_df = pd.DataFrame({
        '# PlotId': df.uniqueID,
        'Litter': (df.ffl_litter_kgpm2 * conv).round(2),
        'wfl1 Hour': (df.wfl_1hr_measured_kgpm2 * conv).round(2),
        'wfl10 Hour': (df.wfl_10hr_measured_kgpm2 * conv).round(2),
        'wfl10 Hour Moisture': fofem_moist_regime[1],
        'wfl100 Hour': (df.wfl_100hr_measured_kgpm2 * conv).round(2),
        'wfl3-6S': (df.wsf_3to6in_kgpm2_sound * conv).round(2),
        'wfl6-9S': (df.wsf_6to9in_kgpm2_sound * conv).round(2),
        'wfl9-20S': (df.wsf_9to20in_kgpm2_sound * conv).round(2),
        'wfl20plusS': (df.wsf_gte20in_kgpm2_sound * conv).round(2),
        'wfl3-6R': (df.wsf_3to6in_kgpm2_rotten * conv).round(2),
        'wfl6-9R': (df.wsf_6to9in_kgpm2_rotten * conv).round(2),
        'wfl9-20R': (df.wsf_9to20in_kgpm2_rotten * conv).round(2),
        'wfl20plusR': (df.wsf_gte20in_kgpm2_rotten * conv).round(2),
        'wfl1000HourMoisture': fofem_moist_regime[2],
        'Duff': (df.ffl_duff_kgpm2 * conv).round(2),
        'DuffMoisture': fofem_moist_regime[0],
        'DuffDepth': (df.mean_duff_depth / 2.54).round(2),  # cm to inches
        'Herbaceous': (df.fuel_herbs_kgpm2 * conv).round(2),
        'Shrub': (df.fuel_shrubs_kgpm2 * conv).round(2),
        'CrownFoliage': (df.biomass_foliage_ung * conv).round(2),
        'CrownBranch': (df.biomass_branches_ung * conv).round(2),
        'PercentCrownBurned': 0,
        'Region': 'InteriorWest',
        'Season': 'Summer',
        'SoilFamily': df.SoilFamily,
        'SoilMoisture': fofem_moist_regime[3],
        'LitterLoad_ConsumEq1': -1,
        'PctDuff_ConsumEq2': -1,
        'DuffDepth_ConsumEq3': -1,
        'MSE_ConsumEq4': -1,
        'Herb_ConsumEq5': -1,
        'Shrub_ConsumEq6': -1
    })

    # Assign CoverGroup based on species and substrate
    fofem_consume_df['CoverGroup'] = np.where(
        df.SPECIES_CD_1 == 'PY', 'Ponderosa',
        np.where(df.SPECIES_CD_1.isin([
            'B', 'BA', 'BB', 'BG', 'BL', 'BN', 'S', 'SA', 'SB', 'SE', 'SR',
            'SS', 'SW', 'SXB', 'SXE', 'SXL', 'SXS', 'SXW', 'SXX'
        ]), 'BalBRWSpr',
        np.where(df.SPECIES_CD_1.isin(['P', 'PJ', 'PL', 'PLC', 'PLI', 'PR']), 'RedJacPin',
        np.where(df.SPECIES_CD_1.isin(['PW', 'PE', 'H', 'HW', 'HX', 'HXM']), 'WhiPinHem',
        np.where(df.domSubstrate.isin(['SL', 'ST']),
            np.where(df.fccs_spl_species.str.split(':').str[0].isin(['ARFR', 'ARTR']),
                     'Sagebrush', 'ShrubGroup'),
        np.where(df.domSubstrate.isin(['HF', 'HG']), 'GrassGroup', '""'))))))

    # Assign FuelCategory based on treatment_type
    fofem_consume_df['FuelCategory'] = np.where(
        df.treatment_type.isin(['Control', 'Control-Resample', 'Pre', 'PostBurn']),
        'Natural',
        np.where(df.treatment_type == 'Post', 'Slash', 'Piles')
    )

    return fofem_consume_df


def process_fofem_attributes(df: pd.DataFrame, master_tree_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Process FOFEM attributes for tree mortality and consumption modeling.

    This function generates DataFrames formatted for FOFEM tree mortality and consumption modeling.

    :param df: DataFrame with plot-level data (must include 'uniqueID', 'treatment_type', 'year').
    :param master_tree_df: DataFrame with processed tree-level data.
    :return: DataFrame with FOFEM tree mortality variables.
    """
    print('\nProcessing FOFEM Attributes')

    # Generate the FOFEM tree DataFrame
    fofem_tree_df = _gen_fofem_tree_df(df, master_tree_df)

    # Generate the FOFEM consumption DataFrame
    fofem_consume_df = _gen_fofem_consumption_df(df)

    return fofem_tree_df, fofem_consume_df
