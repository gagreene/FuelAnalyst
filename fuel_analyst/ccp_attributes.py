# -*- coding: utf-8 -*-
"""
Created on Tue Oct 21, 09:00:00 2025

@author: Gregory A. Greene
"""
__author__ = ['Gregory A. Greene, map.n.trowel@gmail.com']

import os
import pandas as pd
import numpy as np
from . import helper


def _calc_herbaceous_fuels(df: pd.DataFrame, fuel_fields: list) -> pd.DataFrame:
    """
    Calculate surface vegetation fuel loads based on CCP parameters.

    :param df: DataFrame containing plot-level data.
    :param ccp_params: Dictionary of CCP surface vegetation fuel load parameters.
    :return: DataFrame with an added 'surface_veg_fuel_load' column.
    """
    df['ccp_herbaceous_fuel_load'] = 0
    for field in fuel_fields:
        if field not in df.columns:
            df['ccp_herbaceous_fuel_load'] += df[f'{field}_kgpm2'].fillna(0)
    return df


def _calc_shrub_fuels(df: pd.DataFrame, fuel_fields: list) -> pd.DataFrame:
    """
    Calculate surface vegetation fuel loads based on CCP parameters.

    :param df: DataFrame containing plot-level data.

    :return: DataFrame with an added 'surface_veg_fuel_load' column.
    """
    df['ccp_shrub_fuel_load'] = 0
    for field in fuel_fields:
        if field not in df.columns:
            df['ccp_shrub_fuel_load'] += df[f'{field}_kgpm2'].fillna(0)
    return df


def _calc_stand_type(df: pd.DataFrame, tree_params_df: pd.DataFrame) -> pd.DataFrame:
    """
    Determine the stand type based on species composition.

    :param df: DataFrame containing species codes and percentages.
    :param tree_params_df: DataFrame containing tree parameters indexed by species code.
    :return: DataFrame with an added 'stand_type' column.
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
    Calculate stand density based on tree counts and plot area.

    # Estimate stand density class from canopy cover
        if 0 <= cc <= 45:
            density = 'L'  # low density
        elif cc <= 60:
            density = 'M'  # moderate density
        elif cc <= 100:
            density = 'H'  # high density

    :param df: DataFrame containing tree counts and plot area.
    :return: DataFrame with an added 'stand_density_tpha' column.
    """
    # Calculate stand density (trees per hectare)
    df['ccp_density_class'] = np.where(
        df[cc_field] <= 45,
        'L',
        np.where(df[cc_field] <= 60, 'M', 'H')
    )
    return df


def gen_ccp_df(df: pd.DataFrame, ccp_params: dict) -> pd.DataFrame:
    """
    Read CCP attributes from a CSV file into a pandas DataFrame.

    :param df: DataFrame containing plot-level data.
    :return: DataFrame containing the CCP attributes.
    """
    # Load tree parameters and set index
    tree_params_df = helper.get_df(
        os.path.join(os.path.dirname(__file__), 'supporting_data', 'tree_parameters.csv')
    ).set_index('Species')

    df = _calc_stand_type(df, tree_params_df)
    df = _calc_stand_density(df, ccp_params['canopy_cover_attribute'])
    df = _calc_shrub_fuels(df, ccp_params['vegetative_fuels']['shrub_fuel_load'])
    df = _calc_herbaceous_fuels(df, ccp_params['vegetative_fuels']['herbaceous_fuel_load'])

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
        'shrub_fuel_load': df['ccp_shrub_fuel_load'].fillna(0),
    })

    return ccp_df
