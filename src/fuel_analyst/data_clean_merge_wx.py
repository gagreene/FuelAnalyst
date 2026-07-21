# -*- coding: utf-8 -*-
"""
Created on Monday July 20th, 2026

@author: Sarah Smith-Tripp
"""
__author__ = ['Sarah Smith-Tripp, sarahsmith.tripp@gmail.com']

import os
from fuel_analyst.components import helper
from fuel_analyst.components.trees import _calc_plot_multipliers
import numpy as np
import pandas as pd
from typing import Union
from fuel_analyst.extract_BECType import create_joined_geopackage
from fuel_analyst.components import plot_attributes as pa
from fuel_analyst.extract_BECType import _load_plots, _extract_BECType  
from fuel_analyst.components import helper
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
# ────────────────────────────────────────────────────────────
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
# ────────────────────────────────────────────────────────────
def plot_attributes_read(in_dir: str, out_dir: str, spatial = False) -> pd.DataFrame:
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
    plot_gdf = helper.get_unique_id(plot_gdf)
    ## Data checks for the following columns: elevation, plot_slope, plot_aspect
    # Check for invalid attribute values
    plot_gdf['flagged'] = np.where(
        (plot_gdf['plot_elevation'] < 0) |
        (plot_gdf['plot_elevation'] > 3500) |
        (plot_gdf['plot_slope'] < 0) |
        (plot_gdf['plot_slope'] > 90) |
        (plot_gdf['plot_aspect'] < 0) |
        (plot_gdf['plot_aspect'] > 360), 1, 0
        )
    if plot_gdf['flagged'].sum() > 0:
        flagged_plots = plot_gdf[plot_gdf['flagged'] == 1]
        flagged_path = os.path.join(out_dir, 'flagged_plots.csv')
        helper.export_csv(flagged_plots, flagged_path)
        print(f'Warning: {len(flagged_plots)} plots have flagged values for elevation, slope, or aspect. '
              f'Details saved to: {flagged_path}')
    # Calculate slope as %
    plot_gdf['plot_slope_pct'] = np.where(plot_gdf['plot_slope_units'] == 'degrees',
                                          100 * np.tan(plot_gdf['plot_slope'] * np.pi / 180),
                                          plot_gdf['plot_slope'].astype(float)).round(1)
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
     # Save datasets
    os.makedirs(out_dir, exist_ok=True)
    helper.export_csv(plot_gdf, os.path.join(out_dir, 'survey_0.csv'))
    if spatial:
        plot_gdf.to_file(os.path.join(out_dir, 'survey_0.gpkg'), driver='GPKG')
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
def subplot_data(in_dir: str, dir_dict: dict, 
                 dir_get: str = None,
                 merge_plot: bool = False, 
                 plot_df: pd.DataFrame = None,
                 out_dir: str = '.') -> pd.DataFrame:
    """Extract subplot data from the Survey123 form directories and merge with plot data.
    
    Args:
        in_dir (str): The input directory containing the Survey123 form directories.
        dir_dict (dict): A dictionary mapping form names to their respective directory names.
        dir_get (str): A key to get from the dictionary (e.g., 'subplots').
        merge_plot (bool): Whether to merge plot data onto subplot data. Defaults to False.
        plot_df (pd.DataFrame): Optional plot data to merge onto subplot data.
        out_dir (str): The output directory to save flagged files to.
    
    Returns:
        pd.DataFrame: A DataFrame containing the updated subplot data.
    """ 
    if dir_get is None:
        raise ValueError('dir_get parameter is required')
    
    print(f'Reading and merging plot level data for {dir_get}')
    plot_dir = os.path.join(in_dir, dir_dict.get(dir_get))
    
    # Get parent survey data for the tree data
    plot_files = sorted(f for f in os.listdir(plot_dir)
                        if f.startswith('survey_0') and f.endswith('.csv'))
    
    survey_file = os.path.join(plot_dir, plot_files[0]) if plot_files else None
    if not survey_file:
        raise FileNotFoundError(f'No survey_0*.csv file found in: {plot_dir}')
    
    # Generate the unique_id column and calculate attributes
    tree_df = helper.get_df(survey_file)
    tree_df = helper.get_unique_id(tree_df)
    tree_df = _calc_plot_multipliers(tree_df)
    
    if not merge_plot:
        return tree_df
    
    if plot_df is None:
        raise ValueError('Need parent plot data to merge on')
    
    out_df = pd.merge(plot_df, tree_df, on='unique_id', how='left', suffixes=('_plot', '_tree'))
    
    # Flag plots with missing tree data
    missing_tree_data = out_df[out_df['x_tree'].isna()]
    if not missing_tree_data.empty:
        print(f"Warning: {len(missing_tree_data)} plots have no associated tree data")
        missing_tree_data.to_csv(os.path.join(out_dir, 'plots_missing_tree_data.csv'), index=False)
    
    # Flag mismatched coordinates
    coord_mismatch = (out_df['x_tree'] != out_df['x_plot']) | (out_df['y_tree'] != out_df['y_plot'])
    if coord_mismatch.any():
        mismatches = out_df[coord_mismatch]
        print(f"Warning: {len(mismatches)} rows have mismatched X or Y coordinates")
        mismatches[['unique_id', 'x_tree', 'x_plot', 'x_tree', 'x_plot']].to_csv(
            os.path.join(out_dir, 'coordinate_mismatches.csv'), index=False)
    
    # Keep plot coordinates
    return out_df.drop(columns=['x_tree', 'y_tree']).rename(columns={'x_plot': 'X', 'y_plot': 'Y'})
      
# Test routine for calculating FBP fuel types
if __name__ == '__main__':
        # Define input and output folders
    _in_dir  = os.getenv('DATA_BASE_DIR', '/app/input_data')
    _out_dir = os.getenv('OUTPUT_CHECK_DIR', '/app/output/data_check')
    _BEC_shp_dir = os.path.join(os.getenv('BEC_DATA_DIR', '/app/BEC_data'), 'VEG_COMP_LYR_R1_POLY_2025.gdb')
    print(_BEC_shp_dir)
    os.makedirs(_out_dir, exist_ok=True)
    ## run all of the functions 
    print('Reading plot level data and checking for missing values or outlier values...')
    folder_check(_in_dir, ['plants', 'trees', 'cover', 'woody'], dir_dict)
    plots, cols, missing_coords = plot_attributes_read(_in_dir, _out_dir, spatial=False)
    ## extract BEC 
    bec_info_df = extract_BEC(plots, vri_polygon=_BEC_shp_dir, write_sf=True)
    print('Reading tree level data and checking for missing values or outliers')
    tree_df  = subplot_data(in_dir = _in_dir, 
                         dir_dict=dir_dict, 
                         dir_get ='trees',
                         merge_plot=True, 
                         plot_df=plots, 
                         out_dir = _out_dir)
  
                         
    
    