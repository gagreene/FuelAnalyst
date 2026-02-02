# -*- coding: utf-8 -*-
"""
Created on Tue Oct 21, 09:00:00 2025

@author: Gregory A. Greene
"""
__author__ = ['Gregory A. Greene, map.n.trowel@gmail.com']

import os
import pandas as pd

try:
    # Relative import for module usage
    from . import helper
except ImportError:
    # Absolute import for script usage
    import helper


def _calc_veg_fuel_loads(df: pd.DataFrame, veg_fuel_dict: dict) -> pd.DataFrame:
    """
    Calculate surface vegetation fuel loads based on CCP parameters.

    :param df: DataFrame containing plot-level data.

    :return: DataFrame with an added 'ccp_shrub_fuel_load' column.
    """
    for fuel_att, fuel_fields in veg_fuel_dict.items():
        field_name = f'ccp_{fuel_att}_fuel_load'
        df[field_name] = 0
        for fuel_field in fuel_fields:
            df[field_name] += df[f'{fuel_field}_kgpm2'].fillna(0)
    return df


def _calc_stand_type(df: pd.DataFrame, tree_params_df: pd.DataFrame) -> pd.DataFrame:
    """
    Determine the stand type based on species composition.

    :param df: DataFrame containing species codes and percentages.
    :param tree_params_df: DataFrame containing tree parameters indexed by species code.
    :return: DataFrame with an added 'ccp_stand_type' column.
    """
    spp_code_cols = [f'SPECIES_CD_{x}' for x in range(1, 7)]

    # Map species codes to tree types
    stand_type_df = df[['unique_id'] + spp_code_cols].copy()
    stand_type_df[spp_code_cols] = stand_type_df[spp_code_cols].map(
        lambda x: tree_params_df.loc[x, 'TreeType'] if pd.notnull(x) else None
    )
    stand_type_df['tree_type'] = stand_type_df[spp_code_cols].apply(
        lambda row: ' '.join(pd.Series([val for val in row if pd.notnull(val)]).unique()), axis=1
    )
    df['tree_type'] = df['unique_id'].map(stand_type_df.set_index('unique_id')['tree_type'])

    # Create masks for each condition
    mw_mask = df['tree_type'].str.contains('conifer') & df['tree_type'].str.contains('broadleaf')
    pct80_mask = (df['SPECIES_PCT_1'] >= 80) & pd.notnull(df['SPECIES_CD_1'])
    cd1_mask = pd.notnull(df['SPECIES_CD_1'])

    # Default empty string
    df['ccp_stand_type'] = ''

    # Apply MW mask
    df.loc[mw_mask, 'ccp_stand_type'] = 'MW'

    # Apply pct80_mask where MW is not already set
    df.loc[pct80_mask & ~mw_mask, 'ccp_stand_type'] = df.loc[
        pct80_mask & ~mw_mask, 'SPECIES_CD_1'
    ].map(tree_params_df['CCP_StandType'])

    # Apply cd1_mask where neither MW nor pct80_mask is set
    df.loc[cd1_mask & ~mw_mask & ~pct80_mask, 'ccp_stand_type'] = df.loc[
        cd1_mask & ~mw_mask & ~pct80_mask, 'SPECIES_CD_1'
    ].map(tree_params_df['CCP_StandType'])
    return df


def _calc_stand_density(df: pd.DataFrame, cc_field: str) -> pd.DataFrame:
    """
    Calculate stand density based on canopy cover.
        if 0 <= cc <= 45:
            density = 'L'  # low density
        elif cc <= 60:
            density = 'M'  # moderate density
        elif cc <= 100:
            density = 'H'  # high density

    :param df: DataFrame containing tree counts and plot area.
    :return: DataFrame with an added 'ccp_density_class' column.
    """
    # Calculate stand density class from canopy cover
    mask_l = (df[cc_field] >= 0) & (df[cc_field] <= 45)
    mask_m = (df[cc_field] > 45) & (df[cc_field] <= 60)
    mask_h = (df[cc_field] > 60) & (df[cc_field] <= 100)

    df['ccp_density_class'] = None
    df.loc[mask_l, 'ccp_density_class'] = 'L'
    df.loc[mask_m, 'ccp_density_class'] = 'M'
    df.loc[mask_h, 'ccp_density_class'] = 'H'
    return df


def _prep_fbp_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Prepare a DataFrame for CFFBPS fuel type assignment.

    :param df: DataFrame containing plot-level data.
    :return: DataFrame formatted for CFFBPS fuel type assignment.
    """
    print('Generating CFFBPS Fuel Type Prep DataFrame')

    keep_columns = [
        'unique_id', '_date',
        'treatment_area', 'treatment_unit', 'treatment_unit_other', 'treatment_type',
        'plot_id', 'COAST_INTERIOR_CD', 'BEC_Zone', 'BEC_Subzone', 'SPECIES_CD_1', 'SPECIES_CD_1_max_age',
        'recent_clearcut_date_10_yrs', 'recent_fire_date_11_yrs'
    ]

    fbp_prep_df = df.copy()
    fbp_prep_df['COAST_INTERIOR_CD'] = pd.NA
    fbp_prep_df['BEC_Zone'] = pd.NA
    fbp_prep_df['BEC_Subzone'] = pd.NA
    fbp_prep_df['SPECIES_CD_1_max_age'] = pd.NA
    fbp_prep_df['clearcut_date'] = pd.NaT
    fbp_prep_df['last_fire_date'] = pd.NaT
    fbp_prep_df['recent_clearcut_date_10_yrs'] = pd.NA
    fbp_prep_df['recent_fire_date_11_yrs'] = pd.NA
    fbp_prep_df = fbp_prep_df[keep_columns]

    return fbp_prep_df


def gen_ccp_df(df: pd.DataFrame, ccp_params: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Read CCP attributes from a CSV file into a pandas DataFrame.

    :param df: DataFrame containing plot-level data.
    :param ccp_params: Dictionary of CCP parameters.
    :return: DataFrame containing the CCP attributes.
    """
    # Load tree parameters and set index
    tree_params_df = helper.get_df(
        os.path.join(os.path.dirname(__file__), 'supporting_data', 'tree_parameters.csv')
    ).set_index('Species')

    df = _calc_stand_type(df, tree_params_df)
    df = _calc_stand_density(df, ccp_params['canopy_cover_attribute'])
    df = _calc_veg_fuel_loads(df, ccp_params['vegetative_fuel_loads'])
    fbp_prep_df = _prep_fbp_df(df)

    # Build DataFrame
    ccp_df = pd.DataFrame({
        'unique_id': df['unique_id'],
        'plot_id': df['plot_id'],
        'lat': df['y'],
        'long': df['x'],
        'elevation': df['plot_elevation'],
        'slope': df['plot_slope_pct'],
        'aspect': df['plot_aspect'],
        'stand_density': df['ccp_density_class'],
        'stand_type': df['ccp_stand_type'],
        'fbp_fuel_type': '',
        'pct_cnfr': df['stand_pct_cnfr_live'].fillna(0),
        'canopy_cover': df[ccp_params['canopy_cover_attribute']].fillna(0),
        'cfl_ovrstry': df['ccp_cfl_ovrstry'].fillna(0),
        'cbd_ovrstry': df['ccp_cbd_ovrstry'].fillna(0),
        'cfl_midstry': df['ccp_cfl_midstry'].fillna(0),
        'cbd_midstry': df['ccp_cbd_midstry'].fillna(0),
        'dead_branch_fl': df['ccp_dead_branch_fl'].fillna(0),
        'ht_ovrstry_live': df['ccp_ht_ovrstry_live'],
        'ht_midstry_live': df['ccp_ht_midstry_live'],
        'ht_midstry_dead': df['ccp_ht_midstry_dead'],
        'cbh_ovrstry': df['ccp_cbh_ovrstry'],
        'cbh_midstry': df['ccp_cbh_midstry'],
        'fsg': df['ccp_fsg'],
        'duff_fuel_load': df['ffl_duff_kgpm2'].fillna(0),
        'litter_fuel_load': df['ffl_litter_kgpm2'].fillna(0),
        'woody_fuel_load': df['woody_kgpm2_ccp_lt7cm_7'].fillna(0),
        'herbaceous_fuel_load': df['ccp_herbaceous_fuel_load'].fillna(0),
        'grass_fuel_load': df['ccp_grass_fuel_load'].fillna(0),
        'shrub_fuel_load': df['ccp_shrub_fuel_load'].fillna(0),
    })

    return ccp_df, fbp_prep_df
