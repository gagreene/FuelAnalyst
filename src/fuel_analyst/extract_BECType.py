# -*- coding: utf-8 -*-
"""
Created on Wed June 12, 2024
Extracts information on BEC from existing and recent VRI Rank 1 data.  This allows students to directly input data.
This does not overwrite existing information in the fbp_prep_df, but rather updates the BEC_Zone and BEC_Subzone columns with the extracted values based on unique_id.

@author: Sarah Smith-Tripp
"""
__author__ = ['Sarah Smith-Tripp, sarah.smithtripp@ubc.ca']

import os
import numpy as np
import rasterio as rio
import pandas as pd
import geopandas as gpd
import concurrent.futures
from pyproj import CRS
from datetime import datetime
from typing import Optional
from functools import reduce
import sys
pkg_dir = os.path.join(os.path.dirname(__file__), '..', '..')
if pkg_dir not in sys.path:
    sys.path.insert(0, pkg_dir)
def _extract_BECType(
        plots: gpd.GeoDataFrame,
        plot_id_col_name: str,
        BEC_shp_dir: str,
        BEC_layer: str,
) -> gpd.GeoDataFrame:
    ## CRS set is constant
    crs = CRS.from_epsg(3005)  # Always use BC Albers (EPSG:3005) for spatial operations
    # Read only the BEC polygons that overlap the plot bounding box
    bbox = tuple(plots.to_crs(epsg=3005).total_bounds)  # xmin, ymin, xmax, ymax
    bec = gpd.read_file(
        BEC_shp_dir,
        layer=BEC_layer,
        bbox=bbox,          # spatial pre-filter — skips features outside the bbox
        engine='pyogrio',   # much faster than fiona for large files (pip install pyogrio)
    )

    # Align CRS for plots and BEC polygons  
    if bec.crs != plots.crs:
        plots = plots.to_crs(bec.crs)

    # Keep only the columns you need before the join (saves memory)
    bec_cols = ['COAST_INTERIOR_CD', 'BEC_ZONE_CODE', 'BEC_SUBZONE', 'SPECIES_CD_1',
                'PROJ_AGE_1', 'HARVEST_DATE', 'EARLIEST_NONLOGGING_DIST_TYPE',
                'EARLIEST_NONLOGGING_DIST_DATE', 'geometry']
    for col in bec_cols:
        if col not in bec.columns:
            raise ValueError(f'Expected column "{col}" not found in BEC shapefile layer. Available columns: {bec.columns.tolist()}')
    available_cols = [c for c in bec_cols if c in bec.columns]
    bec = bec[available_cols]
    joined = gpd.sjoin(
        plots[[plot_id_col_name, 'geometry']],
        bec,
        how='left',
        predicate='within'
    )
    ## if the type is fire than we want the date, else return na for earliest non-logging disturbance date
    joined['recent_fire_date_11_yrs'] = np.where(
        joined['EARLIEST_NONLOGGING_DIST_TYPE'] == 'fire',
        joined['EARLIEST_NONLOGGING_DIST_DATE'],
        np.nan
    )
    ## select and rename columns to match the expected format for fbp_prep_df  
    result = joined[[plot_id_col_name] + [c for c in available_cols if c != 'geometry'] + ['recent_fire_date_11_yrs']].copy()
    result = result.rename(columns={
        'COAST_INTERIOR_CD': 'COAST_INTERIOR_CD',
        'BEC_ZONE_CODE': 'BEC_Zone',
        'BEC_SUBZONE': 'BEC_Subzone',
        'PROJ_AGE_1': 'SPECIES_CD_1_max_age',
        'HARVEST_DATE': 'recent_clearcut_date_10_yrs',
        'recent_fire_date_11_yrs': 'recent_fire_date_11_yrs'
    })
    ## drop columns that are in FBP Fuel typing 
    result = result.drop(columns=['EARLIEST_NONLOGGING_DIST_TYPE', 'EARLIEST_NONLOGGING_DIST_DATE',
                                  'PROJ_AGE_1', 'BEC_ZONE_CODE', 'BEC_SUBZONE'], errors='ignore')
    ## Turn these columns into strings to match the expected format in fbp_prep_df (and to avoid issues with NaNs)
    for col in ['COAST_INTERIOR_CD', 'BEC_Zone', 'BEC_Subzone']:
        if col in result.columns:
            result[col] = result[col].astype(str).replace('nan', '')   

    return result



def _load_plots(
        plot_pts_path: str,
        lat: str,
        lon: str
) -> gpd.GeoDataFrame:
    """
    Load plot locations from a CSV or shapefile and return a GeoDataFrame.

    :param plot_pts_path: Path to the plot locations file (CSV or shapefile)
    :param lat: Name of the latitude column in the CSV (only needed if CSV)
    :param lon: Name of the longitude column in the CSV (only needed if CSV)
    :return: GeoDataFrame with plot locations and geometry
    """
    if plot_pts_path.lower().endswith('.csv'):
        df = pd.read_csv(plot_pts_path)
        plots = gpd.GeoDataFrame(
            df,
            geometry=gpd.points_from_xy(df[lon], df[lat]),
            crs=f'EPSG:4326'
        )
    else:
        plots = gpd.read_file(plot_pts_path)

    # Reproject plots to EPSG:3978 if not already in that CRS
    if plots.crs is None:
        raise ValueError('Plots CRS undefined')
    if plots.crs.to_epsg() != 3978:
        plots = plots.to_crs(epsg=3978)

    return plots

     

# Test routine for extracting weather data and saving results
if __name__ == '__main__':
        # Define the environment as "dockerized" or not 
    is_docker = os.path.exists('/.dockerenv')
    if is_docker:
        # Docker environment file paths 
        _BEC_shp_loc = os.getenv('BEC_DATA_DIR', '/app/BEC_data')  # Path to BEC shapefile directory (mounted in Docker)
        test_dir = os.getenv('DATA_BASE_DIR', '/app/input_data')
        _out_dir =  os.getenv('OUTPUT_FBP', 'app/output/fuel_analyst')
        _plot_pts_path = os.path.join('OUTPUT_FuelAnalyst', '/app/output/fuel_analyst', 'conpyro_df.csv')
        _fbp_prep_path = os.path.join('OUTPUT_FuelAnalyst', '/app/output/fuel_analyst', 'fbp_prep_df.csv')
        _fbp_out_path = os.path.join('OUTPUT_FBP', '/app/output/fuel_analyst/fbp_prep_df_BEC.csv')   
    ## Non-Docker Environment
    else:
        # Local Windows development (follow the instructions)
          # Define input and output directories
        _BEC_shp_dir = r'I:/_Weather_Data/NRCAN_FWIS_Database'  # Parent directory containing NRCAN gridded weather data
        test_dir = os.path.join(os.path.dirname(__file__), 'tests')
        _out_dir = os.path.join(test_dir, 'results', 'fuel_analyst')
        _plot_pts_path = os.path.join(test_dir, 'results', 'fuel_analyst', 'conpyro_df.csv')
        _fbp_prep_path = os.path.join(test_dir, 'results', 'fuel_analyst', 'fbp_prep_df.csv')
  
    _out_file_name = f'fbp_prep_df.csv'
    _BEC_shp_dir = os.path.join(_BEC_shp_loc, 'VEG_COMP_LYR_R1_POLY_2025.gdb')  # Full path to the BEC shapefile
    _BEC_layer   = 'VEG_COMP_LYR_R1_POLY'
    _plot_id_col_name = 'unique_id'
    _lat_col_name = 'lat'  # Always decimal degrees, WGS84 (EPSG:4326) for input CSV; will be reprojected to EPSG:3978
    _lon_col_name = 'long'  # Always decimal degrees, WGS84 (EPSG:4326) for input CSV; will be reprojected to EPSG:3978
    
    ## load plots 
    plots_gdf = _load_plots(
        plot_pts_path=_plot_pts_path,
        lat=_lat_col_name,
        lon=_lon_col_name
    )
    ##  extract BEC type for each plot
    bec_info_df = _extract_BECType(
        plots=plots_gdf,
        plot_id_col_name=_plot_id_col_name,
        BEC_shp_dir=_BEC_shp_dir,
        BEC_layer=_BEC_layer
    )
    bec_cols = [c for c in bec_info_df.columns if c in bec_info_df.columns]
    
    ## join bec info back to fbp_prep_df
    fbp_prep_df = pd.read_csv(_fbp_prep_path)
    ## infill BEC_Zone and BEC_Subzone only when the existing values are empty
    fbp_prep_df_updated = fbp_prep_df.merge(
        bec_info_df,
        on=_plot_id_col_name,
        how='left',
        suffixes=('', '_VRI')
    )
    for col in ['COAST_INTERIOR_CD', 'BEC_Zone', 'BEC_Subzone',
                'SPECIES_CD_1_max_age', 'recent_clearcut_date_10_yrs', 'recent_fire_date_11_yrs']:
        new_col = f'{col}_VRI'
        if col not in fbp_prep_df_updated.columns:
            fbp_prep_df_updated[col] = fbp_prep_df_updated[new_col]
        else:
            fbp_prep_df_updated[col] = fbp_prep_df_updated[col].replace('', np.nan).fillna(fbp_prep_df_updated[new_col])
    fbp_prep_df_updated.to_csv(_fbp_out_path, index=False)
    print(f'BEC type extraction complete. Results saved to {_fbp_out_path}')   