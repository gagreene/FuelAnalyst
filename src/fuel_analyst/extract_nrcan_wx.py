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


def _attach_geometry(
    df: pd.DataFrame,
    plots: gpd.GeoDataFrame,
    id_col: str,
    crs: Optional[CRS] = None
) -> gpd.GeoDataFrame:
    """
    Attach geometry to a DataFrame by merging with the original plots GeoDataFrame.

    :param df: DataFrame with sampled weather data (must include id_col)
    :param plots: Original GeoDataFrame with geometry (must include id_col and geometry)
    :param id_col: Name of the unique ID column used for merging (e.g., "UniqueID")
    :param crs: Coordinate reference system for the output GeoDataFrame (optional, defaults to plots CRS)
    :return: GeoDataFrame with geometry attached
    """
    geom_df = plots[[id_col, 'geometry']].copy()
    out = df.merge(geom_df, on=id_col, how='left')
    gdf = gpd.GeoDataFrame(out, geometry='geometry', crs=crs or plots.crs)
    return gdf


def _calc_percentile_worker(args) -> pd.DataFrame:
    """
    Worker function to calculate percentiles for a single variable within a single plot group.

    :param args: Tuple containing (plot_id, group DataFrame, variable name)
    :return: DataFrame with an additional column containing percentiles for the specified variable
    """
    plot_id, group, var = args
    group[f'{var}_prcnt'] = group[var].rank(pct=True) * 100
    return group


def _calc_percentiles(
        df: pd.DataFrame,
        plot_id_col_name: str,
        var_list: list,
) -> pd.DataFrame:
    """
    Calculate percentiles for a specified variable within each plot.

    :param df: DataFrame with sampled weather data (must include id_col and var columns)
    :param plot_id_col_name: Name of the unique ID column in df (e.g., "unique_id")
    :param var_list: List of the variables calculate percentiles for (e.g. ["fwi"])
    :return: DataFrame with an additional column containing percentiles for the specified variable
    """
    for var in var_list:
        print(f'\tCalculating percentiles for variable: {var}')
        if var not in df.columns:
            raise ValueError(f'Variable "{var}" not found in DataFrame columns: {list(df.columns)}')

        if os.cpu_count() >= 4:
            grouped = list(df.groupby(plot_id_col_name))
            with concurrent.futures.ProcessPoolExecutor(max_workers=os.cpu_count() - 1) as executor:
               results = list(executor.map(
                   _calc_percentile_worker,
                    [(plot_id, group, var) for plot_id, group in grouped]
               ))
            df = pd.concat(results, ignore_index=True)
        else:
            # Calculate percentiles for each variable within each plot using rank method
            df[f'{var}_prcnt'] = df.groupby(plot_id_col_name)[var].rank(pct=True) * 100

    return df


def _get_filtered_raster_paths(
    var: str,
    start_year: int,
    end_year: int,
    dir_map: dict[str, str],
) -> list[str]:
    """
    Filter and sort raster file paths for a given variable based on a specified year range.
    Assumes filenames look like: {var}YYYYMMDD.tif so it works for nrcan data.

    :param var: Variable name (e.g. "fwi", "isi")
    :param start_year: First year to include (inclusive)
    :param end_year: Last year to include (inclusive)
    :param dir_map: Dictionary mapping variable names to their corresponding dir paths
    :return: List of file paths to rasters for the specified variable and year range
    """
    dir = dir_map[var]
    paths = []
    for root, dirs, files in os.walk(dir):
        for fn in files:
            if not fn.lower().endswith('.tif'):
                continue
            date_str = fn[len(var):-4]  # YYYYMMDD
            year = int(date_str[:4])
            if start_year <= year <= end_year:
                paths.append(os.path.join(root, fn))
    paths.sort(key=lambda p: os.path.basename(p)[len(var):-4])
    return paths


def _get_wx_directories(wx_data_dir: str) -> dict[str, str]:
    """
    Return a dictionary mapping weather variable names to their dir paths.

    :param wx_data_dir: Base path to weather data directories
    :return: Dictionary of variable names to dir paths
    """
    return {
        'temp': f'{wx_data_dir}/temp',
        'rh':   f'{wx_data_dir}/rh',
        'pcp':  f'{wx_data_dir}/pcp',
        'ws':   f'{wx_data_dir}/ws',
        'wd':   f'{wx_data_dir}/wd',
        'ffmc': f'{wx_data_dir}/ffmc',
        'dmc':  f'{wx_data_dir}/dmc',
        'dc':   f'{wx_data_dir}/dc',
        'isi':  f'{wx_data_dir}/isi',
        'bui':  f'{wx_data_dir}/bui',
        'fwi':  f'{wx_data_dir}/fwi',
    }


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


def _sample_raster(
    plots: gpd.GeoDataFrame,
    raster_paths: list[str],
    id_col: str,
    var: str,
    value_col: str = "value",
    date_col: str = "wx_date",
) -> pd.DataFrame:
    """
    Sample a list of rasters at plot locations and return a long-format table.

    :param plots: GeoDataFrame with plot locations (must include geometry and id_col)
    :param raster_paths: List of file paths to rasters to sample (must be in same CRS as plots or reprojectable)
    :param id_col: Name of the unique ID column in plots (e.g., "UniqueID")
    :param var: Variable name to extract from raster file names (e.g. "fwi", "isi")
    :param value_col: Name of the column to store sampled values (default "value")
    :param date_col: Name of the column to store raster observation dates (default "wx_date")
    :return: DataFrame with columns [id_col, date_col, value_col] containing sampled
        raster values for each plot and date
    """
    if id_col not in plots.columns:
        raise ValueError(f'ID column "{id_col}" not found in plots columns: {list(plots.columns)}')
    with rio.open(raster_paths[0]) as src0:
        target_crs = src0.crs
    if plots.crs != target_crs:
        if plots.crs is None:
            raise ValueError('Plots CRS undefined')
        plots_proj = plots.to_crs(target_crs)
    else:
        plots_proj = plots
    coords = [(geom.x, geom.y) for geom in plots_proj.geometry]
    ids = plots_proj[id_col].to_list()
    rows = []
    for rp in raster_paths:
        data_name = os.path.basename(rp)
        date_str = data_name[len(var):-4]
        d = int(datetime.strptime(date_str, '%Y%m%d').strftime('%Y%m%d'))
        with rio.open(rp) as src:
            nodata = src.nodata
            vals = [v[0] for v in src.sample(coords)]
        if nodata is not None:
            vals = [np.nan if (x == nodata) else round(float(x), 3) for x in vals]
        else:
            vals = [round(float(x), 3) for x in vals]
        rows.extend(
            {id_col: uid, date_col: d, value_col: val}
            for uid, val in zip(ids, vals)
        )
    df = pd.DataFrame(rows)
    return df


def _extract_weather(
    plots: gpd.GeoDataFrame,
    plot_id_col_name: str,
    wx_var_list: list[str],
    wx_directories: dict[str, str],
    start_year: int,
    end_year: int
) -> pd.DataFrame:
    """
    Extract weather data from rasters for all variables and merge results.

    :param plots: GeoDataFrame with plot locations (must include geometry and id_col)
    :param plot_id_col_name: Name of the unique ID column in plots (e.g., "unique_id")
    :param wx_var_list: List of weather variables to sample (e.g. ["fwi", "isi"])
    :param wx_directories: Dictionary mapping variable names to their corresponding dir paths
    :param start_year: First year to include (inclusive)
    :param end_year: Last year to include (inclusive)
    :return: DataFrame with columns [id_col, date_col, var1, var2, ...] containing
        sampled values for each plot and date
    """
    wx_target_directories = _select_wx_directories(wx_var_list, wx_directories)
    dfs = []
    for var, dir in wx_target_directories.items():
        print(f'\tProcessing variable: {var}')
        print(f'\t\tGetting raster file paths for years {start_year}-{end_year} in directory: {dir}')
        raster_paths = _get_filtered_raster_paths(
            var=var,
            start_year=start_year,
            end_year=end_year,
            dir_map={var: dir},
        )
        if os.cpu_count() >= 4:
            print(f'\t\tExtracting data from rasters in parallel using {os.cpu_count() - 1} workers...')
            with concurrent.futures.ProcessPoolExecutor(max_workers=os.cpu_count() - 1) as executor:
                futures = [
                    executor.submit(
                        _sample_raster,
                        plots,
                        [rp],
                        plot_id_col_name,
                        var,
                        var,
                    )
                    for rp in raster_paths
                ]
                results = [f.result() for f in concurrent.futures.as_completed(futures)]
                df_var = pd.concat(results, ignore_index=True)
        else:
            print(f'\t\tExtracting data from rasters sequentially...')
            df_var = _sample_raster(
                plots=plots,
                raster_paths=raster_paths,
                id_col=plot_id_col_name,
                var=var,
                value_col=var,
            )
        # Remove rows with missing data
        df_var = df_var.dropna(subset=[var])
        dfs.append(df_var)
    if not dfs:
        return pd.DataFrame()
    # Merge all variable DataFrames on id and date
    df_merged = reduce(lambda left, right: pd.merge(left, right, on=[plot_id_col_name, 'wx_date']), dfs)
    return df_merged


def _select_wx_directories(
    wx_var_list: list[str],
    dir_map: dict[str, str],
) -> dict[str, str]:
    """
    Select directories for specified weather variables and check availability.

    :param wx_var_list: List of weather variables to select (e.g. ["fwi", "isi"])
    :param dir_map: Dictionary mapping variable names to their corresponding dir paths
    :return: Dictionary of selected variables and their dir paths
    """
    missing = [v for v in wx_var_list if v not in dir_map]
    if missing:
        raise ValueError(f'Not available: {missing}')
    return {v: dir_map[v] for v in wx_var_list}


def extract_weather_data(
        wx_data_dir: str,
        out_dir: str,
        out_file_name: str,
        start_year: int,
        end_year: int,
        wx_var_list: list[str],
        plot_pts_path: str,
        plot_id_col_name: str,
        lat_col_name: str,
        lon_col_name: str,
        calculate_percentiles: bool = False,
        percentile_var_list: Optional[list[str]] = None
) -> None:
    """
    Main function to extract weather data for specified variables and plots, and save results.

    :param wx_data_dir: Base path to weather data dir containing variable subdirectories
    :param out_dir: dir to save output files
    :param out_file_name: Base name for output files (without extension)
    :param start_year: First year to include (inclusive)
    :param end_year: Last year to include (inclusive)
    :param wx_var_list: List of weather variables to sample (e.g. ["fwi", "isi"])
    :param plot_pts_path: Path to the plot locations CSV file (optional, if not using shapefile)
    :param plot_id_col_name: Name of the unique ID column in the plots file (default "unique_id")
    :param lat_col_name: Name of the latitude column in the CSV (required if using CSV)
    :param lon_col_name: Name of the longitude column in the CSV (required if using CSV)
    :param calculate_percentiles: Whether to calculate percentiles for specified variables (default False)
    :param percentile_var_list: List of variables to calculate percentiles for (required if calculate_percentiles is True)
    :return: None (saves output files to disk)
    """
    # Create output directory if it doesn't exist
    os.makedirs(_out_dir, exist_ok=True)

    # Get weather variable directories
    wx_directories = _get_wx_directories(wx_data_dir)

    # Load plot locations
    print('Loading plot location data...')
    plots = _load_plots(plot_pts_path, lat_col_name, lon_col_name)

    # Sample weather data for all variables and merge results
    print('Sampling weather data for variables: ', wx_var_list)
    df_all = _extract_weather(
        plots=plots,
        plot_id_col_name=plot_id_col_name,
        wx_var_list=wx_var_list,
        wx_directories=wx_directories,
        start_year=start_year,
        end_year=end_year
    )

    # Calculate percentiles if requested
    if calculate_percentiles:
        print('Calculating percentiles...')
        df_all = _calc_percentiles(df_all, plot_id_col_name, percentile_var_list)

    # Sort data by plot ID and date
    df_all = df_all.sort_values(by=[plot_id_col_name, 'wx_date']).reset_index(drop=True)

    # Save results to CSV
    print('Saving results to csv...')
    out_csv = os.path.join(out_dir, f'{out_file_name}.csv')
    df_all.to_csv(out_csv, index=False)
    print('Saved: ', out_csv)

    # Save results to shapefile with geometry attached
    print('Saving results to shapefile...')
    gdf_all = _attach_geometry(
        df=df_all,
        plots=plots,
        id_col=plot_id_col_name,
        crs=plots.crs
    )
    out_shp  = os.path.join(out_dir, f'{out_file_name}.shp')
    gdf_all.to_file(out_shp, driver='ESRI Shapefile')

    return


if __name__ == '__main__':
    # Example usage
    # Define input and output directories
    _wx_data_dir = r'I:/_Weather_Data/NRCAN_FWIS_Database'
    test_dir = os.path.join(os.path.dirname(__file__), 'tests')
    _out_dir = os.path.join(test_dir, 'results', 'wx_extract')  # r'C:/Users/ftiribelli/PycharmProjects/sample_weather/test_data/'
    _out_file_name = 'wx_data'
    _start_year = 2023
    _end_year = 2024
    _wx_var_list = ['temp', 'rh', 'ws', 'wd', 'ffmc', 'dmc', 'dc', 'bui', 'isi', 'fwi']
    _plot_pts_path = os.path.join(test_dir, 'test_data', 'wx_extract', 'UBC_FuelPlots_small_xy.csv') #  r'C:/Users/ftiribelli/PycharmProjects/sample_weather/test_data/UBC_FuelPlots_small_xy.csv'
    _plot_id_col_name = 'unique_id'
    _lat_col_name = 'Y'  # Always decimal degrees, WGS84 (EPSG:4326) for input CSV; will be reprojected to EPSG:3978
    _lon_col_name = 'X'  # Always decimal degrees, WGS84 (EPSG:4326) for input CSV; will be reprojected to EPSG:3978
    _calculate_percentiles = True
    _percentile_var_list = ['fwi']

    extract_weather_data(
        wx_data_dir=_wx_data_dir,
        out_dir=_out_dir,
        out_file_name=_out_file_name,
        start_year=_start_year,
        end_year=_end_year,
        wx_var_list=_wx_var_list,
        plot_pts_path=_plot_pts_path,
        plot_id_col_name=_plot_id_col_name,
        lat_col_name=_lat_col_name,
        lon_col_name=_lon_col_name,
        calculate_percentiles=_calculate_percentiles,
        percentile_var_list=_percentile_var_list,
    )
