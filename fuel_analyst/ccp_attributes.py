# -*- coding: utf-8 -*-
"""
Created on Tue Oct 21, 09:00:00 2025

@author: Gregory A. Greene
"""
__author__ = ['Gregory A. Greene, map.n.trowel@gmail.com']

import os
import pandas as pd
import numpy as np
import helper
from datetime import datetime as dt
# import bcwft


def _calc_fbp_fuel_type(df: pd.DataFrame) -> pd.DataFrame:
    print('Processing CFFBPS Fuel Type')
    bcFT = bcwft.BCFuelType()
    fldList = bcFT.fldList
    fldDType = bcFT.fldDTypes
    fldDict = {fldList[i]: fldDType[i] for i in range(len(fldList))}
    season = 'Growing'
    
    fbp_df = df.copy()
    
    fbp_df['_date'] = fbp_df['_date'].apply(lambda y: dt.strptime(y, '%m/%d/%Y %I:%M:%S %p').year)
    fbp_df['BCWFT_rowRef'] = 0
    fbp_df['FuelType'] = ''
    fbp_df['FT_Modifier'] = 0
    fbp_df['INVENTORY_STANDARD_CD'] = 'F'
    fbp_df['COAST_INTERIOR_CD'] = 'I'
    fbp_df['NON_PRODUCTIVE_CD'] = 64
    fbp_df['BCLCS_LEVEL_1'] = 'V'
    fbp_df['BCLCS_LEVEL_2'] = np.where(fbp_df.dens_live == 0, 'N', np.where(fbp_df.CC < 10, 'N', 'T'))
    fbp_df['BCLCS_LEVEL_3'] = 'U'
    fbp_df['LAND_COVER_CLASS_CD_1'] = np.where(fbp_df.BCLCS_LEVEL_2 == 'T',
                                           np.where(fbp_df.pc > 75,
                                                    'TC',
                                                    np.where(fbp_df.ph > 75, 'TB', 'TM')),
                                           fbp_df.domSubstrate)
    fbp_df['BCLCS_LEVEL_4'] = fbp_df.LAND_COVER_CLASS_CD_1
    fbp_df['BCLCS_LEVEL_5'] = np.where(fbp_df.CC < 10, np.nan, np.where(fbp_df.CC <= 25, 'SP', np.where(fbp_df.CC <= 60, 'OP', 'DE')))
    if not 'EARLIEST_NONLOGGING_DIST_TYPE' in fbp_df.columns:
        fbp_df['EARLIEST_NONLOGGING_DIST_TYPE'] = np.where(fbp_df.treatment_type.str.contains('burn|fire', case=False),
                                                       'B',
                                                       np.nan)
    if not 'EARLIEST_NONLOGGING_DIST_DATE' in fbp_df.columns:
        fbp_df['EARLIEST_NONLOGGING_DIST_DATE'] = np.nan
        fbp_df['EARLIEST_NONLOGGING_DIST_DATE'] = pd.to_datetime(fbp_df['EARLIEST_NONLOGGING_DIST_DATE'])
        fbp_df['_date'] = pd.to_datetime(fbp_df['_date'])
        # Rover added the above line to address the DType conflict in the np.where below
        fbp_df['EARLIEST_NONLOGGING_DIST_DATE'] = np.where(fbp_df.treatment_type.str.contains('burned', case=False),
                                                       fbp_df['_date'],
                                                       fbp_df.EARLIEST_NONLOGGING_DIST_DATE)
    # fbp_df['HARVEST_DATE'] = np.nan
    fbp_df['CROWN_CLOSURE'] = fbp_df.CC
    fbp_df['PROJ_AGE_1'] = np.where(fbp_df.dens_live == 0, 0, fbp_df.PROJ_AGE_1)  # Assign stand age to 0 if no live trees
    fbp_df['PROJ_HEIGHT_1'] = fbp_df.ht_ovrstry_live  # THIS SHOULD BE FOR LEADING SPECIES, NOT ALL LIVE
    fbp_df['VRI_LIVE_STEMS_PER_HA'] = fbp_df.dens_live
    fbp_df['VRI_DEAD_STEMS_PER_HA'] = fbp_df.dens_dead
    fbp_df['STAND_PERCENTAGE_DEAD'] = 100 * fbp_df.ba_dead / fbp_df.ba

    # Assign data types to columns
    fbp_df = fbp_df.astype(fldDict)

    # Convert dataframe to list containing only the rows needed for fbp fuel typing
    dfList = df.reindex(columns=fldList).values.tolist()

    for row in dfList:
        fuelData = bcFT.getFuelType(season, row)
        if fuelData is not None:
            # Get bcwft line reference number (row[0]), fuel type code (row[1]), and fuel type modifier (row[2])
            row[0], row[1], row[2] = fuelData
            # Remove dash from fuel type code
            row[1] = row[1].replace('-', '')
        else:
            row[0], row[1], row[2] = np.nan, 'NoMatchingFuelType_ERROR', np.nan

    ft_df = pd.DataFrame(dfList, columns=fldList)

    # Add new columns in ft_df to the original dataframe
    df = df.merge(ft_df[['unique_id', 'FuelType', 'FT_Modifier']], on='unique_id', how='left')
    df = df.rename(columns={'FuelType': 'fbp_fuel_type', 'FT_Modifier': 'fbp_ft_modifier'})

    return df


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


def gen_ccp_df(df: pd.DataFrame, ccp_params: dict) -> pd.DataFrame:
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
    # df = _calc_fbp_fuel_type(df)

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
        # 'fbp_fuel_type': df['fbp_fuel_type'].fillna(''),
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

    return ccp_df
