# -*- coding: utf-8 -*-
"""
Created on Wed Feb 12, 15:00:00 2026

@author: Gregory A. Greene
"""
__author__ = ['Gregory A. Greene, map.n.trowel@gmail.com']

import os
import numpy as np
import pandas as pd
from typing import Union

import sys
pkg_dir = os.path.join(os.path.dirname(__file__), '..', '..')
if pkg_dir not in sys.path:
    sys.path.insert(0, pkg_dir)

from src.fuel_analyst.components import helper


def _add_season_column(
        merged_df: pd.DataFrame,
        Summer_start: int,
        fall_start: int
) -> pd.DataFrame:
    """
    Add a 'season' column to merged_df based on 'wx_date' and given seasonal boundaries.

    :param merged_df: DataFrame containing merged plot and weather data, with 'wx_date' column
    :param Summer_start: Integer representing the month and day (MMDD) when Summer starts (e.g., 615 for June 15)
    :param fall_start: Integer representing the month and day (MMDD) when fall starts (e.g., 915 for September 15)
    :return: DataFrame with added 'season' column
    """
    if 'wx_date' in merged_df.columns:
        merged_df['month_day'] = merged_df['wx_date'].astype(str).str[4:8].astype(int)
        conditions = [
            merged_df['month_day'] < Summer_start,
            (merged_df['month_day'] >= Summer_start) & (merged_df['month_day'] < fall_start),
            merged_df['month_day'] >= fall_start
        ]
        choices = ['Spring', 'Summer', 'Fall']
        merged_df['season'] = np.select(conditions, choices, default='fall')
        # Move 'season' column immediately after 'wx_date'
        cols = list(merged_df.columns)
        if 'wx_date' in cols and 'season' in cols:
            wx_idx = cols.index('wx_date')
            cols.insert(wx_idx + 1, cols.pop(cols.index('season')))
            merged_df = merged_df[cols]
        merged_df = merged_df.drop(columns=['month_day'])
    return merged_df


def _refine_fbp_fuel_types_by_season(merged_df: pd.DataFrame) -> pd.DataFrame:
    """
    Refine seasonal FBP fuel types based on user-defined season.
        - O1a/O1b codes changed to O1a in Spring, O1b otherwise.
        - M1/M2 codes changed to M2 in Summer, M1 otherwise.
        - M3/M4 codes changed to M4 in Summer, M3 otherwise.
        - D1/D2 codes changed to D2 in Summer, D1 otherwise.

    :param merged_df: DataFrame containing merged plot and weather data, with 'fbp_fuel_type' and 'season' columns
    :return: DataFrame with refined 'fbp_fuel_type' based on season
    """
    if 'fbp_fuel_type' in merged_df.columns and 'season' in merged_df.columns:
        # O1a/O1b
        merged_df.loc[merged_df['season'] == 'Spring', 'fbp_fuel_type'] = (
            merged_df.loc[merged_df['season'] == 'Spring', 'fbp_fuel_type'].str.replace('O1b', 'O1a')
        )
        merged_df.loc[merged_df['season'] != 'Spring', 'fbp_fuel_type'] = (
            merged_df.loc[merged_df['season'] != 'Spring', 'fbp_fuel_type'].str.replace('O1a', 'O1b')
        )
        # M1/M2
        merged_df.loc[merged_df['season'] == 'Summer', 'fbp_fuel_type'] = (
            merged_df.loc[merged_df['season'] == 'Summer', 'fbp_fuel_type'].str.replace('M1', 'M2')
        )
        merged_df.loc[merged_df['season'] != 'Summer', 'fbp_fuel_type'] = (
            merged_df.loc[merged_df['season'] != 'Summer', 'fbp_fuel_type'].str.replace('M2', 'M1')
        )
        # M3/M4
        merged_df.loc[merged_df['season'] == 'Summer', 'fbp_fuel_type'] = (
            merged_df.loc[merged_df['season'] == 'Summer', 'fbp_fuel_type'].str.replace('M3', 'M4')
        )
        merged_df.loc[merged_df['season'] != 'Summer', 'fbp_fuel_type'] = (
            merged_df.loc[merged_df['season'] != 'Summer', 'fbp_fuel_type'].str.replace('M4', 'M3')
        )
        # D1/D2
        merged_df.loc[merged_df['season'] == 'Summer', 'fbp_fuel_type'] = (
            merged_df.loc[merged_df['season'] == 'Summer', 'fbp_fuel_type'].str.replace('D1', 'D2')
        )
        merged_df.loc[merged_df['season'] != 'Summer', 'fbp_fuel_type'] = (
            merged_df.loc[merged_df['season'] != 'Summer', 'fbp_fuel_type'].str.replace('D2', 'D1')
        )
    return merged_df


def merge_weather_data(
        plot_data_path: str,
        plot_merge_col_name: str,
        wx_data_path: str,
        wx_merge_col_name: Union[str, None],
        wx_merge_vars: Union[list[str], None],
        out_path: str,
        add_season: bool = True,
        refine_fbp_seasonally: bool = True,
        summer_start: int = 615,
        fall_start: int = 915,
) -> None:
    """
    Merge extracted weather data with other plot-level data from a CSV.

    :param plot_data_path: Path to the CSV file containing plot-level data to merge
        (must include plot_merge_col_name)
    :param plot_merge_col_name: Name of the unique ID column in the plot data CSV used for merging
        (e.g., "unique_id")
    :param wx_data_path: Path to the CSV file containing extracted weather data to merge
        (must include wx_merge_col_name)
    :param wx_merge_col_name: Name of the unique ID column in the weather data CSV used for merging,
        or None to merge all weather data with each plot row
    :param wx_merge_vars: List of weather variable column names to include in the merge
    :param out_path: Path to save the merged CSV file
    :param add_season: Whether to add a 'season' column based on 'wx_date' (default: True)
    :param refine_fbp_seasonally: Whether to refine FBP fuel types based on season
        (e.g., convert 'D' to 'S' for Summer) if 'fbp_fuel_type' column is present (default: True)
    :param summer_start: Integer representing the month and day (MMDD) when Summer starts (default: 615 for June 15)
        Required if add_season or refine_fbp_seasonally is True
    :param fall_start: Integer representing the month and day (MMDD) when fall starts (default: 915 for September 15)
        Required if add_season or refine_fbp_seasonally is True
    :return: None
    """
    # Check if required parameters are provided when adding season or refining FBP fuel types
    if (add_season or refine_fbp_seasonally) and (summer_start is None or fall_start is None):
        raise ValueError('Summer_start and fall_start parameters must be provided when add_season or '
                         'refine_fbp_seasonally is True.')

    # Ensure output directory exists
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    print('Merging extracted weather data with other plot data...')
    plot_df = helper.get_df(plot_data_path)
    ## remove plots that had missing lat and long and were skipped in weather extracti on
    ## get plots with missing spatial data 
    missing_coords = plot_df[plot_df['lat'].isna() | plot_df['long'].isna()]
    missing_fbp = plot_df[plot_df['fbp_fuel_type'] == 'NoMatchingFuelType_ERROR']
    if len(missing_coords) > 0:
        print(f'Warning: {len(missing_coords)} plots have missing lat or long data and will be skipped in the merge:')
        print(missing_coords[plot_merge_col_name].to_list())
    if len(missing_fbp) > 0:
        print(f'Warning: {len(missing_fbp)} plots have missing FBP fuel type data and may not be merged with weather data:')
        print(missing_fbp[plot_merge_col_name].to_list())
    ## combine missing into one dataframe
    missing_data = pd.concat([missing_coords, missing_fbp]).drop_duplicates()
    ## subset missing data from plot_df to get the plots that will be merged with weather data  
    plot_df_sub = plot_df[~plot_df['unique_id'].isin(missing_data['unique_id'])]    
    wx_df = helper.get_df(wx_data_path)
    # Get weather variables to merge
    if wx_merge_vars is not None:
        wx_merge_vars = [var for var in wx_merge_vars if var in wx_df.columns]
    else:
        wx_merge_vars = [col for col in wx_df.columns if col != wx_merge_col_name]
    if plot_merge_col_name not in plot_df_sub.columns:
        raise ValueError(f'Plot ID column "{plot_merge_col_name}" not found in '
                         f'plot data columns: {list(plot_df_sub.columns)}')
    if wx_merge_col_name is not None:
        if wx_merge_col_name not in wx_df.columns:
            raise ValueError(f'Plot ID column "{wx_merge_col_name}" not found in '
                             f'weather data columns: {list(wx_df.columns)}')
        # Merge on the specified ID columns
        merged_df = plot_df_sub.merge(
            wx_df[[wx_merge_col_name] + wx_merge_vars],
            left_on=plot_merge_col_name,
            right_on=wx_merge_col_name,
            how='left'
        )
    else:
        # Remove plot_merge_col_name from wx_df if it exists to avoid duplication in the merge
        if plot_merge_col_name in wx_df.columns:
            wx_df = wx_df.drop(columns=[plot_merge_col_name])
        # Filter wx_df to only include the specified weather variables
        wx_df = wx_df[wx_merge_vars]
        # Cartesian product: merge all wx_df rows with each plot_df row
        plot_df_sub['_tmp_key'] = 1
        wx_df['_tmp_key'] = 1
        merged_df = plot_df_sub.merge(wx_df, on='_tmp_key').drop('_tmp_key', axis=1)

    # Change FBP fuel types to match season of weather data (if applicable)
    if 'fbp_fuel_type' in merged_df.columns:
        merged_df['month_day'] = pd.to_datetime(merged_df['wx_date']).dt.strftime('%m%d').astype(int)
        merged_df['season'] = merged_df['month_day'].apply(
            lambda x: 'Summer' if summer_start <= x < fall_start else 'Fall/Winter'
        )
        # Update FBP fuel types based on season
        merged_df['fbp_fuel_type'] = merged_df.apply(
            lambda row: row['fbp_fuel_type'].replace('D', 'S') if row['season'] == 'Summer' else row['fbp_fuel_type'],
            axis=1
        )
        merged_df = merged_df.drop(columns=['month_day', 'season'])

    # Add a 'season' column based on 'wx_date' and Summer/fall start dates if requested
    if add_season or refine_fbp_seasonally:
        merged_df = _add_season_column(merged_df, summer_start, fall_start)

    # Refine FBP fuel types based on season
    if refine_fbp_seasonally and ('fbp_fuel_type' in merged_df.columns):
        merged_df = _refine_fbp_fuel_types_by_season(merged_df)
        # Drop 'season' column if it was only added for refining FBP fuel types and not requested to be kept
        if not add_season:
            merged_df = merged_df.drop(columns=['season'], errors='ignore')

    merged_df.to_csv(out_path, index=False)
    missing_data.to_csv(os.path.splitext(out_path)[0] + '_missing_data.csv', index=False)   
    print('Saved merged data: ', out_path)
    print('Saved missing data (plots with missing lat/long or FBP fuel type): ', os.path.splitext(out_path)[0] + '_missing_data.csv')

    return


# Test routine for merging weather data with plot data
if __name__ == '__main__':
    # Define input and output directories
    examples_dir = helper.get_examples_dir(os.path.dirname(__file__))
    _wx_out_dir     = os.path.join(examples_dir, 'results', 'wx_extract')
    _fbp_out_dir = os.path.join(examples_dir, 'results', 'fbp_fuel_typing')
    _wx_data_path  = os.path.join(_wx_out_dir, 'wx_data.csv')
    _plot_data_path = os.path.join(_fbp_out_dir, 'conpyro_df_fbp.csv')
    _out_path      = os.path.join(_wx_out_dir, 'conpyro_df_wx.csv')
    _wx_data_path   = os.path.join(_wx_out_dir, 'wx_data.csv')
    _plot_data_path = os.path.join(examples_dir, 'results', 'fbp_fuel_typing', 'conpyro_df_fbp.csv')
    _plot_merge_col_name = 'unique_id'
    _wx_merge_col_name = 'unique_id'  # Assign as None to merge all weather data with each plot
    _wx_merge_vars = None
    _add_season = True
    _refine_fbp_seasonally = True
    _summer_start = 615
    _fall_start = 915

    merge_weather_data(
        plot_data_path=_plot_data_path,
        plot_merge_col_name=_plot_merge_col_name,
        wx_data_path=_wx_data_path,
        wx_merge_col_name=_wx_merge_col_name,
        wx_merge_vars=_wx_merge_vars,
        out_path=_out_path,
        add_season=_add_season,
        refine_fbp_seasonally=_refine_fbp_seasonally,
        summer_start=_summer_start,
        fall_start=_fall_start
    )
