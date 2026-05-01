# -*- coding: utf-8 -*-
"""
Created on Tue May 29, 8:30:00 2025

@author: Gregory A. Greene
"""
__author__ = ['Gregory A. Greene, map.n.trowel@gmail.com']

import os
import numpy as np
import pandas as pd
from dateutil import parser

import sys
pkg_dir = os.path.join(os.path.dirname(__file__), '..', '..')
if pkg_dir not in sys.path:
    sys.path.insert(0, pkg_dir)

from src.fuel_analyst.components import helper
from dependencies.BC_CFFBPS_FuelTyping_Tool import bcwft2018 as bcwft

def _calc_fbp_fuel_type(df: pd.DataFrame, season: str = 'Growing') -> pd.DataFrame:
    print('Calculating CFFBPS Fuel Types using BCWFT2018 fuel typing algorithm')
    bc_fuel_type = bcwft.FuelTyping()
    field_list = bc_fuel_type.fldList
    field_dtype = bc_fuel_type.fldDTypes
    field_dict = {field_list[i]: field_dtype[i] for i in range(len(field_list))}

    # Assign data types to columns
    fbp_df = df.copy()

    fbp_df['year'] = fbp_df['_date'].apply(lambda y: parser.parse(y).year)
    fbp_df['BCWFT_rowRef'] = 0
    fbp_df['FuelType'] = ''
    fbp_df['FT_Modifier'] = 0
    fbp_df['INVENTORY_STANDARD_CD'] = 'F'
    fbp_df['NON_PRODUCTIVE_CD'] = 64
    fbp_df['BCLCS_LEVEL_1'] = 'V'
    fbp_df['BCLCS_LEVEL_2'] = np.where(
        fbp_df.stand_dens_tpha_live_sum == 0,
        'N',
        np.where(fbp_df.cc < 10, 'N', 'T')
    )
    fbp_df['BCLCS_LEVEL_3'] = 'U'
    fbp_df['LAND_COVER_CLASS_CD_1'] = np.where(
        fbp_df.BCLCS_LEVEL_2 == 'T',
        np.where(fbp_df.stand_pct_cnfr_live > 75,
                 'TC',
                 np.where(fbp_df.stand_pct_brdlf_live > 75, 'TB', 'TM')),
        fbp_df.dom_substrate
    )
    fbp_df['BCLCS_LEVEL_4'] = fbp_df.LAND_COVER_CLASS_CD_1
    fbp_df['BCLCS_LEVEL_5'] = np.where(
        fbp_df.cc < 10,
        None,
        np.where(fbp_df.cc <= 25, 'SP', np.where(fbp_df.cc <= 60, 'OP', 'DE'))
    )
    if not 'EARLIEST_NONLOGGING_DIST_TYPE' in fbp_df.columns:
        fbp_df['EARLIEST_NONLOGGING_DIST_TYPE'] = np.where(
            fbp_df.treatment_type.str.contains('burn|fire', case=False),
            'B',
            ''
        )
    fbp_df['CROWN_CLOSURE'] = fbp_df.cc
    # Assign stand age to 0 if no live trees
    fbp_df['PROJ_AGE_1'] = np.where(fbp_df.stand_dens_tpha_live_sum == 0, 0, fbp_df.PROJ_AGE_1)
    fbp_df['VRI_LIVE_STEMS_PER_HA'] = fbp_df.stand_dens_tpha_live_sum
    fbp_df['VRI_DEAD_STEMS_PER_HA'] = fbp_df.stand_dens_tpha_dead_sum
    fbp_df['STAND_PERCENTAGE_DEAD'] = 100 * fbp_df.stand_ba_m2pha_dead_sum / fbp_df.stand_ba_m2pha_sum

    # Filter columns to only those needed for fuel typing
    fbp_df = fbp_df.reindex(columns=['unique_id'] + field_list)

    # Ensure correct data types
    fbp_df = fbp_df.astype(field_dict)

    # Convert dataframe to list containing only the rows needed for fbp fuel typing
    dfList = fbp_df.reindex(columns=['unique_id'] + field_list).values.tolist()

    for row in dfList:
        fuelData = bc_fuel_type.getFuelType(season, *row[4:])
        if fuelData is not None:
            # Get bcwft line reference number (row[0]), fuel type code (row[1]), and fuel type modifier (row[2])
            row[1], row[2], row[3] = fuelData
            # Remove dash from fuel type code
            row[2] = row[2].replace('-', '')
        else:
            row[1], row[2], row[3] = np.nan, 'NoMatchingFuelType_ERROR', np.nan

    ft_df = pd.DataFrame(dfList, columns=['unique_id'] + field_list)

    # Add new columns in ft_df to the original dataframe
    df = df.merge(ft_df[['unique_id', 'FuelType', 'FT_Modifier']], on='unique_id', how='left')
    df = df.rename(columns={'FuelType': 'fbp_fuel_type', 'FT_Modifier': 'fuel_type_modifier'})

    return df

def process_fbp_fuel_type(
        master_fuel_df_path: str,
        fbp_prep_df_path: str,
        conpyro_df_path: str,
        out_dir: str,
        season: str) -> None:
    """
    Calculate the FBP fuel type for each plot in the DataFrame using the BCWFT2018 fuel typing system.

    :param master_fuel_df_path: Path to the master fuel DataFrame CSV file.
    :param fbp_prep_df_path: Path to the FBP preparation DataFrame CSV file.
    :param conpyro_df_path: Path to the ConPyro DataFrame CSV file to be updated with FBP fuel types.
    :param out_dir: Directory to save the updated ConPyro DataFrame CSV file with FBP fuel types.
    :param season: Season for fuel typing ('Growing' or 'Dormant').
    :return: DataFrame with added columns for FBP fuel type and modifier.
    """
    # Columns to drop from the FBP preparation DataFrame
    fbp_drop_columns = [
        '_date',
        'treatment_area', 'treatment_unit', 'treatment_unit_other', 'treatment_type',
        'plot_id', 'SPECIES_CD_1'
    ]
    fbp_rename_columns = {
        'BEC_Zone': 'BEC_ZONE_CODE',
        'BEC_Subzone': 'BEC_SUBZONE',
        'SPECIES_CD_1_max_age': 'PROJ_AGE_1',
        'recent_clearcut_date_10_yrs': 'HARVEST_DATE',
        'recent_fire_date_11_yrs': 'EARLIEST_NONLOGGING_DIST_DATE',
    }

    # Load the master fuel DataFrame and the FBP preparation DataFrame
    master_fuel_df = pd.read_csv(master_fuel_df_path)
    fbp_prep_df = (pd.read_csv(fbp_prep_df_path)
                   .drop(columns=fbp_drop_columns)
                   .rename(columns=fbp_rename_columns))
    conpyro_df = pd.read_csv(conpyro_df_path)

    # Merge the two dataframes on 'unique_id' to get all necessary attributes
    fuel_type_df = master_fuel_df.merge(fbp_prep_df, on='unique_id', how='left')
    fuel_type_df['_date'] = fuel_type_df['_date'].astype(str)

    # Calculate FBP fuel type
    fuel_type_df = _calc_fbp_fuel_type(fuel_type_df, season)

    print('Assigning FBP fuel types to ConPyro DataFrame')
    # Assign FBP fuel types to conpyro_df based on unique_id
    conpyro_df = conpyro_df.merge(
        fuel_type_df[['unique_id', 'fbp_fuel_type']].rename(columns={'fbp_fuel_type': 'fbp_fuel_type_new'}),
        on='unique_id',
        how='left'
    )
    # Retain existing fbp_fuel_type values in conpyro_df if present (only replace empty values)
    conpyro_df['fbp_fuel_type'] = conpyro_df['fbp_fuel_type'].combine_first(conpyro_df['fbp_fuel_type_new'])
    conpyro_df = conpyro_df.drop(columns=['fbp_fuel_type_new'])

    # Replace conpyro_df with updated DataFrame
    print('Saving updated ConPyro DataFrame with FBP fuel types')
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, os.path.basename(conpyro_df_path).replace('.csv', '_fbp.csv'))
    helper.export_csv(conpyro_df, out_path)

    return


# Test routine for calculating FBP fuel types
if __name__ == '__main__':
    # Define the environment as "dockerized" or not 
    is_docker = os.path.exists('/.dockerenv')
    if is_docker:
        # Docker environment file paths 
        test_dir = os.getenv('DATA_BASE_DIR', '/app/input_data')
        _out_dir = os.path.join('app/output/')
          # Get stand fire and FOFEM consume csv paths (defined by the app)
        _master_fuel_df_path = os.path.join('BASE_FILES', '/app/test_data','fbp_fuel_typing', 'master_fuel_df.csv')
        _fbp_prep_df_path = os.path.join('BASE_FILES', '/app/test_data','fbp_fuel_typing', 'fbp_prep_df.csv')
        # Write out location to ingest in "fuel_analyst.py"
        _out_dir_conpyro = os.path.join('OUTPUT_FuelAnalyst', '/app/output/fuel_analyst')
        _conpyro_df_path = os.path.join(_out_dir_conpyro,'conpyro_df.csv')
    ## Non-Docker Environment
    else:
        # Local Windows development (follow the instructions)
        # Define input folder 
        test_dir = r'C:\Users\ssmithtr\Desktop\SiteModels\FuelAnalyst_test_data\test_data_LLCF-WBFN_2026-04-14'
        ## define output folder 
        _out_dir = os.path.join(test_dir, 'results', 'fbp_fuel_typing')
        _master_fuel_df_path = os.path.join(test_dir, 'results', 'fuel_analyst', 'master_fuel_df.csv')
        _fbp_prep_df_path = os.path.join(test_dir, 'test_data', 'fbp_fuel_typing', 'fbp_prep_df.csv')
        _conpyro_df_path = os.path.join(test_dir, 'results', 'fuel_analyst', 'conpyro_df.csv')
    
    # define growing season type
    _season = 'growing'  # Options: 'growing' or 'dormant'
  
    # Run FBP fuel type processing
    process_fbp_fuel_type(_master_fuel_df_path, _fbp_prep_df_path, _conpyro_df_path, _out_dir, _season)
