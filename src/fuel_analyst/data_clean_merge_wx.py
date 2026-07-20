# -*- coding: utf-8 -*-
"""
Created on Monday July 20th, 2026

@author: Sarah Smith-Tripp
"""
__author__ = ['Sarah Smith-Tripp, sarahsmith.tripp@gmail.com']

import os
from fuel_analyst.components import helper
import numpy as np
import pandas as pd
from typing import Union
from fuel_analyst.extract_BECType import create_joined_geopackage
from fuel_analyst.components import plot_attributes as pa
from fuel_analyst.extract_BECType import _load_plots, _extract_BECType  
# ── Environment detection ────────────────────────────────────────────────────
is_docker = os.path.exists('/.dockerenv')
# set folder structures 
dir_dict = {
    'plot': '1_Plot_Attributes',
    'plants': '2_Plants_Regeneration',
    'trees': '3_Trees',
    'cover': '4_Canopy_Cover',
    'woody': '5_Woody_Debris'
}
# ── 1. Set Sources ──────────────────────────────────────────────────────────
if is_docker:
    _in_dir  = os.getenv('DATA_BASE_DIR', '/app/input_data')
    _out_dir = os.getenv('OUTPUT_CHECK_DIR', '/app/output/data_check')
    os.makedirs(_out_dir, exist_ok=True)
else :
    raise ValueError('This script is intended to run in a Docker environment. Please set up the required environment variables and run within Docker.')
## Check that all of the directories are available and contain expected files
# Create the list of forms to process
# ── 1. Set Sources ──────────────────────────────────────────────────────────

## FOLDER CHECKING HERE 
def folder_check(in_dir: str, form_select_list: list,
                 dir_dict: dict) -> None:
    """Check that the required Survey123 form directories exist in the input directory. 
    Args:
        in_dir (str): The input directory containing the Survey123 form directories.
        form_select_list (list): A list of form names to check for existence.
        dir_dict (dict): A dictionary mapping form names to their respective directory names.   
    Raises:
        FileNotFoundError: If any of the required form directories are missing.
    """
    form_select_list = ['plants', 'trees', 'cover', 'woody']

    # Create a dictionary to map form names to their display names
    form_dict = {
        'plot': 'Plot Attributes',
        'plants': 'Plants and Regeneration',
        'trees': 'Trees',
        'cover': 'Canopy Cover',
        'woody': 'Woody Debris'
    }
    missing_forms = [
        form for form in form_select_list
        if not os.path.exists(os.path.join(in_dir, dir_dict.get(form)))
    ]
    if missing_forms:
        raise FileNotFoundError(
            f'Not all Survey123 form directories were found in the input directory: {in_dir}. '
            f'The following forms are missing:\n{missing_forms}.'
            )
    return f'All required Survey123 form directories were found in the input directory: {in_dir}.'

def plot_read(in_dir: str, out_dir: str, spatial = False) -> pd.DataFrame:
    plot_dir = os.path.join(in_dir, dir_dict.get('plot'))
    print(plot_dir)
    
    # List all survey CSVs in the plot directory
    plot_files = sorted(f for f in os.listdir(plot_dir)
                        if f.startswith('survey_0') and f.endswith('.csv'))
    print(plot_files)
    
    survey_file = os.path.join(plot_dir, plot_files[0]) if plot_files else None
    
    if not survey_file:
        raise FileNotFoundError(
            f'No survey_0*.csv file found in the Plot Attributes directory: {plot_dir}.'
        )
    
    # Load plots as geodataframe and check for missing lat/long values
    plot_gdf = _load_plots(survey_file, lat='y', lon='x')
    plot_df = helper.get_unique_id(plot_gdf)
    
    # Calculate slope as %
    plot_gdf['plot_slope_pct'] = np.where(plot_gdf['plot_slope_units'] == 'degrees',
                                          100 * np.tan(plot_gdf['plot_slope'] * np.pi / 180),
                                          plot_gdf['plot_slope'].astype(float)).round(1)
    
    # Save datasets
    os.makedirs(out_dir, exist_ok=True)
    helper.export_csv(plot_gdf, os.path.join(out_dir, 'survey_0.csv'))
    
    # Column management
    remove_columns = (
        ['ObjectID', 'GlobalID', 'unique_id', 'comments', 'plot_slope_units', 'plot_slope', 'year'] +
        [col for col in plot_gdf.columns if 'select' in col] +
        [col for col in plot_gdf.columns if col.startswith('witness_')] +
        [col for col in plot_gdf.columns if col.startswith('photo_')] +
        [col for col in plot_gdf.columns if col.startswith('Creat')] +
        [col for col in plot_gdf.columns if col.startswith('Edit')]
    )
    add_columns = [col for col in plot_gdf.columns.tolist() if col not in remove_columns]
    
    # Check for missing lat/long values
    missing_coords = plot_gdf[plot_gdf['y'].isna() | plot_gdf['x'].isna()]
    plot_gdf = plot_gdf.dropna(subset=['y', 'x'])
    
    if not missing_coords.empty:
        print(f'Warning: {len(missing_coords)} plots have missing lat/long values.')
    else:
        print('All plots have valid lat/long values.')
    
    return plot_gdf, add_columns, missing_coords
## using the plot_dt and unique ID column, create the next layer of data, the fpb_prep_csv 
def extract_BEC(plot_gdf: 'gpd.GeoDataFrame', 
                vri_polygon: str = None,
                write_sf: bool = False
                ) -> pd.DataFrame:
    """Extract BEC type information for each plot and save the updated DataFrame.
    Args:
        in_dir (str): The input directory containing the Survey123 form directories.
        out_dir (str): The output directory to save the updated DataFrame.
        plot_gdf (pd.DataFrame): A DataFrame containing the plot data.
        add_columns (list): A list of additional columns to include in the output DataFrame.
        bec_data (pd.DataFrame): A DataFrame containing BEC type information.
    Returns:
        pd.DataFrame: A DataFrame containing the updated plot data with BEC type information.   
    """
    bec_info_df = _extract_BECType(
            plots=plot_gdf,
            plot_id_col_name='unique_id',
            BEC_shp_dir=vri_polygon,
            BEC_layer='VEG_COMP_LYR_R1_POLY'
        )
    if write_sf:
            gpkg_out_path = os.path.join(_out_dir, 'plots.gpkg')
            create_joined_geopackage(
            plots=plot_gdf,
            bec_info_df=bec_info_df,
            plot_id_col='unique_id',
            output_path=gpkg_out_path
            )
    return bec_info_df

# Test routine for calculating FBP fuel types
if __name__ == '__main__':
        # Define input and output folders
    _in_dir  = os.getenv('DATA_BASE_DIR', '/app/input_data')
    _out_dir = os.getenv('OUTPUT_CHECK_DIR', '/app/output/data_check')
    _BEC_shp_dir = os.path.join(os.getenv('BEC_DATA_DIR', '/app/BEC_data'), 'VEG_COMP_LYR_R1_POLY_2025.gdb')
    print(_BEC_shp_dir)
    os.makedirs(_out_dir, exist_ok=True)
    ## run all of the functions 
    
    folder_check(_in_dir, ['plants', 'trees', 'cover', 'woody'], dir_dict)
    plots, cols, missing_coords = plot_read(_in_dir, _out_dir, spatial=True)
    
    ## extract BEC 
    bec_info_df = extract_BEC(plots, vri_polygon=_BEC_shp_dir, write_sf=True)
    ### write out plots with missing lat/long values to a separate CSV for review
    if not missing_coords.empty:
        missing_coords_path = os.path.join(_out_dir, 'missing_lat_long_plots.csv')
        helper.export_csv(missing_coords, missing_coords_path)
        print(f'Plots with missing lat/long values saved to: {missing_coords_path}')
    