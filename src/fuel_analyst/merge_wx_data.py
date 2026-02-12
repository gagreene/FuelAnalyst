# -*- coding: utf-8 -*-
"""
Created on Wed Feb 12, 15:00:00 2026

@author: Gregory A. Greene
"""
__author__ = ['Gregory A. Greene, map.n.trowel@gmail.com']

import os
import sys
pkg_dir = os.path.join(os.path.dirname(__file__), '..', '..')
if pkg_dir not in sys.path:
    sys.path.insert(0, pkg_dir)

from src.fuel_analyst.components import helper


def merge_weather_data(
        plot_data_path: str,
        plot_merge_col_name: str,
        wx_data_path: str,
        wx_merge_col_name: str,
        wx_merge_vars: list[str],
        out_path: str,
) -> None:
    """
    Merge extracted weather data with other plot-level data from a CSV.

    :param plot_data_path: Path to the CSV file containing plot-level data to merge
        (must include plot_merge_col_name)
    :param plot_merge_col_name: Name of the unique ID column in the plot data CSV used for merging
        (e.g., "unique_id")
    :param wx_data_path: Path to the CSV file containing extracted weather data to merge
        (must include wx_merge_col_name)
    :param wx_merge_col_name: Name of the unique ID column in the weather data CSV used for merging
        (e.g., "unique_id")
    :param wx_merge_vars: List of weather variable column names to include in the merge
    :param out_path: Path to save the merged CSV file
    :return: None
    """
    # Create output directory if it doesn't exist
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    print('Merging extracted weather data with other plot data...')
    plot_df = helper.get_df(plot_data_path)
    wx_df = helper.get_df(wx_data_path)
    if plot_merge_col_name not in plot_df.columns:
        raise ValueError(f'Plot ID column "{plot_merge_col_name}" not found in plot data columns: {list(plot_df.columns)}')
    if wx_merge_col_name not in wx_df.columns:
        raise ValueError(f'Plot ID column "{wx_merge_col_name}" not found in weather data columns: {list(wx_df.columns)}')
    merged_df = wx_df.merge(plot_df, left_on=wx_merge_col_name, right_on=plot_merge_col_name, how='left')
    merged_df.to_csv(out_path, index=False)
    print('Saved merged data: ', out_path)

    return


if __name__ == '__main__':
    # Example usage
    # Define input and output directories
    _wx_data_dir = r'I:/_Weather_Data/NRCAN_FWIS_Database'
    test_dir = os.path.join(os.path.dirname(__file__), 'tests')
    _out_dir = os.path.join(test_dir, 'results', 'wx_extract')
    _out_file_name = 'wx_data'
    _plot_data_path = os.path.join(test_dir, 'test_data', 'fuel_analyst', 'ccp_df.csv')
    _plot_merge_col_name = 'unique_id'
    _wx_data_path = os.path.join(_out_dir, f'{_out_file_name}.csv')
    _wx_merge_col_name = 'unique_id'
    _wx_merge_vars = ['wx_date', 'temp', 'rh', 'ws', 'wd', 'ffmc', 'dmc', 'dc', 'bui', 'isi', 'fwi']
    _out_path = os.path.join(_out_dir, f'ccp_df_wx.csv')

    merge_weather_data(
        plot_data_path=_plot_data_path,
        plot_merge_col_name=_plot_merge_col_name,
        wx_data_path=_wx_data_path,
        wx_merge_col_name=_wx_merge_col_name,
        wx_merge_vars=_wx_merge_vars,
        out_path=_out_path,
    )
