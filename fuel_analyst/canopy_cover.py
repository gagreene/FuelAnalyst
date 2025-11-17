# -*- coding: utf-8 -*-
"""
Created on Tue May 29, 8:30:00 2025

@author: Gregory A. Greene
"""
__author__ = ['Gregory A. Greene, map.n.trowel@gmail.com']

import os
import pandas as pd
import numpy as np
from . import helper


def _process_transect_data(transect_df: pd.DataFrame) -> pd.DataFrame:
    """
    Processes canopy cover transect data to calculate total, conifer, and broadleaf canopy cover percentages,
    accounting for excluded points, and assigns these values for each transect.

    :param transect_df: DataFrame containing canopy cover transect data.
    :return: Updated DataFrame with calculated canopy cover columns.
    """
    # List of canopy cover columns (every 2 meters from 2 to 30)
    cc_cols = [f'cc_{i}' for i in range(2, 32, 2)]
    # Count the number of excluded points per row
    exclude_count = transect_df[cc_cols].apply(lambda x: x.isin(['exclude']).sum(), axis=1)
    # Calculate denominator for percent cover (total points minus excluded)
    denom = 15 - exclude_count

    # Calculate total, conifer, and broadleaf canopy cover percentages
    transect_df['cc'] = 100 * transect_df[cc_cols].isin(['cnfr', 'brdlf', 'cnfr_brdlf']).sum(axis=1) / denom
    transect_df['cc_cnfr'] = 100 * transect_df[cc_cols].isin(['cnfr', 'cnfr_brdlf']).sum(axis=1) / denom
    transect_df['cc_brdlf'] = 100 * transect_df[cc_cols].isin(['brdlf', 'cnfr_brdlf']).sum(axis=1) / denom

    # Assign canopy cover values for each transect (1 and 2)
    for suffix in ['', '_cnfr', '_brdlf']:
        for t in [1, 2]:
            col = f'CC{suffix}_t{t}'
            base = f'cc{suffix}' if suffix else 'cc'
            transect_df[col] = np.where(transect_df['cc_transect'] == t, transect_df[base], 0)

    return transect_df


def _process_cc_data(df: pd.DataFrame, transect_df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregates canopy cover data from transect-level to group-level and assigns
    the results to the main DataFrame. Computes average canopy cover metrics.

    :param df: DataFrame containing plot-level data with a 'group' column.
    :param transect_df: DataFrame containing transect-level canopy cover data with a 'group' column.
    :return: Updated DataFrame with group-level canopy cover columns.
    """
    # Columns to aggregate from transect data
    cc_cols = ['CC_t1', 'CC_cnfr_t1', 'CC_brdlf_t1', 'CC_brdlf_t2', 'CC_cnfr_t2', 'CC_t2']

    # Sum canopy cover columns by ParentGlobalID
    group_sums = transect_df.groupby('ParentGlobalID')[cc_cols].sum()

    # Map plot-level sums back to the main DataFrame using GlobalID
    for col in cc_cols:
        df[col] = df['GlobalID'].map(group_sums[col])

    # Calculate average canopy cover metrics
    df['cc'] = (df['CC_t1'] + df['CC_t2']) / 2
    df['cc_cnfr'] = (df['CC_cnfr_t1'] + df['CC_cnfr_t2']) / 2
    df['cc_brdlf'] = (df['CC_brdlf_t1'] + df['CC_brdlf_t2']) / 2

    return df


def process_canopy_cover(in_folder: str, out_folder: str) -> tuple[pd.DataFrame, list]:
    """
    Process canopy cover data from a CSV file and return an updated DataFrame.

    :param in_folder: Path to the folder containing the input CSV files.
    :param out_folder: Path to the folder where output CSV files will be saved.
    :return: DataFrame with processed canopy cover attributes.
    """
    print('\nProcessing Canopy Cover data')

    keep_columns = []

    # ### PROCESS PLOT DATA
    # Get canopy cover dataframe
    df = helper.get_df(os.path.join(in_folder, 'survey_0.csv'))
    # Generate a unique ID for each plot
    df = helper.get_unique_id(df)

    # ### PROCESS CANOPY COVER DATA
    # Get canopy cover transect dataframe
    transect_df = helper.get_df(os.path.join(in_folder, 'canopy_cover_1.csv'))
    # Process transect data
    transect_df = _process_transect_data(transect_df)

    # ### MERGE TRANSECT AND PLOT DATASETS
    df = _process_cc_data(df, transect_df)

    # Save the processed DataFrame to the output folder
    os.makedirs(out_folder, exist_ok=True)
    helper.export_csv(df, os.path.join(out_folder, 'survey_0.csv'))
    helper.export_csv(transect_df, os.path.join(out_folder, 'canopy_cover_1.csv'))

    return df, ['cc', 'cc_cnfr', 'cc_brdlf']
