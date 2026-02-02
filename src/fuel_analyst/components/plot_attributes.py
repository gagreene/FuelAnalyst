# -*- coding: utf-8 -*-
"""
Created on Tue May 27, 9:30:00 2025

@author: Gregory A. Greene
"""
__author__ = ['Gregory A. Greene, map.n.trowel@gmail.com']

import os
import pandas as pd
import numpy as np

try:
    # Relative import for module usage
    from . import helper
except ImportError:
    # Absolute import for script usage
    import helper


def process_plot_attributes(in_folder: str, out_folder: str) -> tuple[pd.DataFrame, list]:
    """
    Get the plot attributes from a CSV file and return as an updated DataFrame.

    :param in_folder: Path to the folder containing the input CSV files.
    :param out_folder: Path to the folder where output CSV files will be saved.
    :return: DataFrame with processed tree attributes.
    """
    print('\nProcessing Plot Attribute data')

    # ### PROCESS PLOT ATTRIBUTE DATA
    # Get plot attributes dataframe
    df = helper.get_df(os.path.join(in_folder, 'survey_0.csv'))
    # Generate a unique ID for each plot
    df = helper.get_unique_id(df)

    # Calculate slope as %
    df['plot_slope_pct'] = np.where(df['plot_slope_units'] == 'degrees',
                                      100 * np.tan(df['plot_slope'] * np.pi / 180),
                                      df['plot_slope'].astype(float)).round(1)

    # ### SAVE DATASETS TO OUTPUT FOLDER
    os.makedirs(out_folder, exist_ok=True)
    helper.export_csv(df, os.path.join(out_folder, 'survey_0.csv'))

    remove_columns = (
            ['ObjectID', 'GlobalID', 'unique_id', 'comments', 'plot_slope_units', 'plot_slope', 'year'] +
            [col for col in df.columns if 'select' in col] +
            [col for col in df.columns if col.startswith('witness_')] +
            [col for col in df.columns if col.startswith('photo_')] +
            [col for col in df.columns if col.startswith('Creat')] +
            [col for col in df.columns if col.startswith('Edit')]
    )
    keep_columns = [col for col in df.columns.tolist() if col not in remove_columns]

    return df, keep_columns
