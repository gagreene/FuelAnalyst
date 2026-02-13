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


# Define constants for ecodivision shapefile and BCWS fire season dates by ecodivision
ECODIVISION_PATH = os.path.join(
    os.path.dirname(__file__), 'supporting_data', 'WHSE_TERRESTRIAL_ECOLOGY_ERC_ECODIVISIONS_SP.json'
)
ECODIVISION_FIELD = 'ECODIVISION_NAME'
BCWS_FIRE_SEASON_DICT = {
    'SUB-ARCTIC HIGHLANDS': [601, 815, 'SAH'],
    'SUB-ARCTIC': [601, 815, 'SUA'],
    'BOREAL': [515, 831, 'BOL'],
    'HUMID CONTINENTAL HIGHLANDS': [515, 831, 'HCH'],
    'COOL HYPERMARITIME AND HIGHLANDS': [515, 831, 'CHH'],
    'SEMI-ARID STEPPE HIGHLANDS': [501, 915, 'SSH'],
    'NORTHEASTERN SUB-ARCTIC PACIFIC': [601, 815, 'NSP']
}


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
        if var not in df.columns:
            raise ValueError(f'Variable "{var}" not found in DataFrame columns: {list(df.columns)}')

        if os.cpu_count() >= 4:
            print(f'\tCalculating percentiles for variable {var} in parallel using {os.cpu_count() - 1} workers...')
            grouped = list(df.groupby(plot_id_col_name))
            num_workers = min(os.cpu_count() - 1, len(grouped))
            with concurrent.futures.ProcessPoolExecutor(max_workers=num_workers) as executor:
               results = list(executor.map(
                   _calc_percentile_worker,
                    [(plot_id, group, var) for plot_id, group in grouped]
               ))
            df = pd.concat(results, ignore_index=True)
        else:
            print(f'\tCalculating percentiles for variable: {var}')
            # Calculate percentiles for each variable within each plot using rank method
            df[f'{var}_prcnt'] = df.groupby(plot_id_col_name)[var].rank(pct=True) * 100

    return df


def _extract_weather(
        plots: gpd.GeoDataFrame,
        plot_id_col_name: str,
        wx_var_list: list[str],
        wx_directories: dict[str, str],
        start_year: int,
        end_year: int,
        use_bcws_dates: bool = False,
        start_month_day: Optional[int] = None,
        end_month_day: Optional[int] = None,
) -> pd.DataFrame:
    """
    Extract weather data from rasters for all variables and merge results.
    Each plot/date/variable combination is a row.

    :param plots: GeoDataFrame with plot locations (must include geometry and plot_id_col_name)
    :param plot_id_col_name: Name of the unique ID column in the plots GeoDataFrame (e.g. "unique_id")
    :param wx_var_list: List of weather variables to sample (e.g. ["fwi", "isi"])
    :param wx_directories: Dictionary mapping variable names to their corresponding dir paths
    :param start_year: First year to include (inclusive)
    :param end_year: Last year to include (inclusive)
    :param use_bcws_dates: Whether to determine in-season dates based on BCWS fire season dates and
        plot ecodivision (default False)
    :param start_month_day: Start month/day (MMDD as int) for filtering rasters (required if use_bcws_dates is False)
    :param end_month_day: End month/day (MMDD as int) for filtering rasters (required if use_bcws_dates is False)
    :return: DataFrame with sampled weather data for all variables and plots
    """
    wx_target_directories = _select_wx_directories(wx_var_list, wx_directories)
    dfs = []
    for var, dir in wx_target_directories.items():
        print(f'\tProcessing variable: {var}')
        if use_bcws_dates:
            # Extract ecodivision for this variable based on plot locations
            plot_ecodivisions = gpd.read_file(ECODIVISION_PATH)
            plot_ecodivisions = plot_ecodivisions.to_crs(plots.crs)
            joined = gpd.sjoin(plots, plot_ecodivisions, how='left', predicate='intersects')
            ecodivision_counts = joined[ECODIVISION_FIELD].value_counts()
            if ecodivision_counts.empty:
                raise ValueError('No ecodivision found for plot locations')

            # Assign start and end dates to new columns based on the ecodivision for each plot
            def _assign_dates(ecodivision):
                if pd.isna(ecodivision):
                    return (np.nan, np.nan)
                for eco, (start_md, end_md, code) in BCWS_FIRE_SEASON_DICT.items():
                    if eco in ecodivision:
                        return (start_md, end_md)
                return (np.nan, np.nan)
            plots[['start_month_day', 'end_month_day']] = joined[ECODIVISION_FIELD].apply(_assign_dates).tolist()

            # Check for any plots with missing dates and drop them with a warning
            missing_dates = plots[plots['start_month_day'].isna() | plots['end_month_day'].isna()]
            if not missing_dates.empty:
                print(f'Warning: {len(missing_dates)} plots have missing fire season dates due to missing or '
                      f'unrecognized ecodivision. These plots will be dropped from the analysis.')
                plots = plots.dropna(subset=['start_month_day', 'end_month_day'])
        else:
            plots['start_month_day'] = start_month_day
            plots['end_month_day'] = end_month_day

        print(f'\t\tGetting raster file paths for years {start_year}-{end_year} in directory: {dir}')
        raster_paths = _get_filtered_raster_paths(
            var=var,
            start_year=start_year,
            end_year=end_year,
            dir_map={var: dir},
        )

        # Build a mapping from raster date (YYYYMMDD) to raster path
        print(f'\t\tMapping raster dates to file paths for variable: {var}')
        raster_date_map = {}
        for rp in raster_paths:
            fname = os.path.basename(rp)
            date_str = fname[len(var):-4]  # YYYYMMDD
            raster_date_map[date_str] = rp

        # For each raster (date), find plots in-season for that date
        all_rows = []
        raster_date_items = list(raster_date_map.items())
        if os.cpu_count() >= 4:
            num_workers = os.cpu_count() - 1
        else:
            num_workers = 1
        if num_workers > 1:
            print(f'\t\tProcessing rasters for variable {var} in parallel using {num_workers} workers...')
            # Split raster_date_items into chunks for each worker
            chunk_size = (len(raster_date_items) + num_workers - 1) // num_workers
            chunks = [raster_date_items[i:i+chunk_size] for i in range(0, len(raster_date_items), chunk_size)]
            with concurrent.futures.ProcessPoolExecutor(max_workers=num_workers) as executor:
                futures = [executor.submit(_process_raster_date_chunk, chunk, plots, plot_id_col_name, var) for chunk in chunks]
                for future in concurrent.futures.as_completed(futures):
                    all_rows.extend(future.result())
        else:
            print(f'\t\tProcessing rasters for variable {var}...')
            all_rows = _process_raster_date_chunk(raster_date_items, plots, plot_id_col_name, var)

        # Combine all rows for this variable into a single DataFrame
        if all_rows:
            df_var = pd.concat(all_rows, ignore_index=True)
            df_var = df_var.dropna(subset=[var])
            dfs.append(df_var)
    if not dfs:
        return pd.DataFrame()

    # Merge all variable DataFrames on id and date
    df_merged = reduce(lambda left, right: pd.merge(left, right, on=[plot_id_col_name, 'wx_date']), dfs)
    return df_merged


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


def _process_raster_date_chunk(
        chunk: list[tuple[str, str]],
        plots: gpd.GeoDataFrame,
        plot_id_col_name: str,
        var: str,
) -> list[pd.DataFrame]:
    """
    Process a chunk of raster date items by sampling rasters for in-season plots and returning a list of DataFrames.

    :param chunk: List of tuples containing (date_str, raster_path) for a subset of rasters
    :param plots: GeoDataFrame of plot locations with start_month_day and end_month_day columns
    :param plot_id_col_name: Name of the unique ID column in the plots GeoDataFrame (e.g. "unique_id")
    :param var: Weather variable name corresponding to the rasters being processed (e.g. "fwi", "isi")
    :return: List of DataFrames with sampled weather data for the in-season plots for the rasters in this chunk
    """
    chunk_rows = []
    for date_str, rp in chunk:
        mmdd = int(date_str[4:])  # MMDD as int
        in_season_mask = (plots['start_month_day'] <= mmdd) & (plots['end_month_day'] >= mmdd)
        plots_in_season = plots[in_season_mask]
        if plots_in_season.empty:
            continue
        df_sample = _sample_raster(
            plots=plots_in_season,
            raster_paths=[rp],
            id_col=plot_id_col_name,
            var=var,
            value_col=var,
        )
        chunk_rows.append(df_sample)
    return chunk_rows


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
    Each raster is sampled for all provided plot coordinates in a single call.
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
        plot_pts_path: str,
        plot_id_col_name: str,
        lat_col_name: str,
        lon_col_name: str,
        wx_var_list: list[str],
        start_year: int,
        end_year: int,
        use_bcws_dates: bool = False,
        start_month_day: Optional[int] = None,
        end_month_day: Optional[int] = None,
        calculate_percentiles: bool = False,
        percentile_var_list: Optional[list[str]] = None,
) -> None:
    """
    Main function to extract weather data for specified variables and plots, and save results.

    :param wx_data_dir: Base path to weather data dir containing variable subdirectories
    :param out_dir: dir to save output files
    :param out_file_name: Base name for output files (without extension)
    :param plot_pts_path: Path to the plot locations CSV file (optional, if not using shapefile)
    :param plot_id_col_name: Name of the unique ID column in the plots file (default "unique_id")
    :param lat_col_name: Name of the latitude column in the CSV (required if using CSV)
    :param lon_col_name: Name of the longitude column in the CSV (required if using CSV)
    :param wx_var_list: List of weather variables to sample (e.g. ["fwi", "isi"])
    :param start_year: First year to include (inclusive)
    :param end_year: Last year to include (inclusive)
    :param use_bcws_dates: Whether to determine in-season dates based on BCWS fire season dates and
        plot ecodivision (default False)
    :param start_month_day: Start month/day (MMDD as int) for filtering rasters (required if use_bcws_dates is False)
    :param end_month_day: End month/day (MMDD as int) for filtering rasters (required if use_bcws_dates is False)
    :param calculate_percentiles: Whether to calculate percentiles for specified variables (default False)
    :param percentile_var_list: List of variables to calculate percentiles for
        (required if calculate_percentiles is True)
    :return: None
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
        end_year=end_year,
        use_bcws_dates=use_bcws_dates,
        start_month_day=start_month_day,
        end_month_day=end_month_day,
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


# Test routine for extracting weather data and saving results
if __name__ == '__main__':
    # Define input and output directories
    _wx_data_dir = r'I:/_Weather_Data/NRCAN_FWIS_Database'
    test_dir = os.path.join(os.path.dirname(__file__), 'tests')
    _out_dir = os.path.join(test_dir, 'results', 'wx_extract')
    _out_file_name = 'wx_data'
    _plot_pts_path = os.path.join(test_dir, 'test_data', 'wx_extract', 'ccp_df.csv')
    _plot_id_col_name = 'unique_id'
    _lat_col_name = 'lat'  # Always decimal degrees, WGS84 (EPSG:4326) for input CSV; will be reprojected to EPSG:3978
    _lon_col_name = 'long'  # Always decimal degrees, WGS84 (EPSG:4326) for input CSV; will be reprojected to EPSG:3978
    _wx_var_list = ['temp', 'rh', 'ws', 'wd', 'ffmc', 'dmc', 'dc', 'bui', 'isi', 'fwi']
    _start_year = 2007
    _end_year = 2024
    _use_bcws_dates = True  # If true, determine in-season dates based on BCWS fire season dates and plot ecodivision
    _start_month_day = None
    _end_month_day = None
    _calculate_percentiles = True
    _percentile_var_list = ['fwi']

    # Extract weather data and save results
    extract_weather_data(
        wx_data_dir=_wx_data_dir,
        out_dir=_out_dir,
        out_file_name=_out_file_name,
        plot_pts_path=_plot_pts_path,
        plot_id_col_name=_plot_id_col_name,
        lat_col_name=_lat_col_name,
        lon_col_name=_lon_col_name,
        wx_var_list=_wx_var_list,
        start_year=_start_year,
        end_year=_end_year,
        use_bcws_dates=_use_bcws_dates,
        start_month_day=_start_month_day,
        end_month_day=_end_month_day,
        calculate_percentiles=_calculate_percentiles,
        percentile_var_list=_percentile_var_list,
    )
