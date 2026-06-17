# -*- coding: utf-8 -*-
"""
Created on Tues Feb 11, 13:25:00 2026

@author: Florencia Tiribelli,
"""
__author__ = ['Florencia Tiribelli, ftiribelli@forsite.ca']

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
) -> pd.DataFrame:
    """
    Extract BEC type information for each plot from a BEC shapefile.

    :param plots: GeoDataFrame with plot locations (must include geometry and plot_id_col_name)
    :param plot_id_col_name: Name of the unique ID column in the plots GeoDataFrame (e.g. "unique_id")
    :param BEC_shp_dir: Path to the BEC shapefile (.shp)
    :return: DataFrame with BEC_Zone and BEC_Subzone columns added for each plot
    """
    bec = gpd.read_file(BEC_shp_dir)

    # Align CRS to plots
    if bec.crs != plots.crs:
        bec = bec.to_crs(plots.crs)

    # Spatial join — each plot gets the BEC polygon it falls within
    joined = gpd.sjoin(plots[[plot_id_col_name, 'geometry']], bec[['ZONE', 'SUBZONE', 'geometry']],
                       how='left', predicate='within')

    # Return only the columns we care about
    result = joined[[plot_id_col_name, 'ZONE', 'SUBZONE']].copy()
    result = result.rename(columns={
        'ZONE': 'BEC_Zone',
        'SUBZONE': 'BEC_Subzone',
    })

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
    _BEC_shp_dir = os.path.join(_BEC_shp_loc, 'BEC_POLY_polygon.shp')  # Full path to the BEC shapefile
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
        BEC_shp_dir=_BEC_shp_dir
    )
    
    ## join bec info back to fbp_prep_df
    fbp_prep_df = pd.read_csv(_fbp_prep_path) 
    ##  replace the BEC_Zone and BEC_Subzone columns in fbp_prep_df with the extracted values from bec_info_df based on unique_id   
    fbp_prep_df_updated = fbp_prep_df.drop(columns=['BEC_Zone', 'BEC_Subzone'], errors='ignore').merge(
        bec_info_df.rename(columns={'unique_id': _plot_id_col_name}),
        on=_plot_id_col_name,
        how='left'
    )
    fbp_prep_df_updated.to_csv(_fbp_out_path, index=False)
    print(f'BEC type extraction complete. Results saved to {_fbp_out_path}')   