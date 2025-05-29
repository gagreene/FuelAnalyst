# -*- coding: utf-8 -*-
"""
Created on Tue May 27, 9:30:00 2025

@author: Gregory A. Greene
"""
__author__ = ['Gregory A. Greene, map.n.trowel@gmail.com']

import os
import pandas as pd
import numpy as np
from datetime import datetime as dt
import helper


def process_plot_attributes(in_folder: str, out_folder: str) -> pd.DataFrame:
    """
    Get the plot attributes from a CSV file and return as an updated DataFrame.

    :param in_folder: Path to the folder containing the input CSV files.
    :param out_folder: Path to the folder where output CSV files will be saved.
    :return: DataFrame with processed tree attributes.
    """
    print('Processing Plot Attribute data')

    # ### PROCESS PLOT ATTRIBUTE DATA
    # Get plot attributes dataframe
    df = helper.get_df(os.path.join(in_folder, 'survey_0.csv'))
    # Generate a unique ID for each plot
    df['year'] = df['_date'].apply(lambda y: dt.strptime(y, '%m/%d/%Y %I:%M:%S %p').year)
    df['uniqueID'] = df[
        ['treatment_area', 'treatment_unit', 'treatment_unit_other', 'plot_id', 'treatment_type', 'year']
    ].apply(lambda x: ''.join(x.astype(str)), axis=1)

    # Calculate slope as %
    df['plot_slope_pct'] = np.where(df['plot_slope_units'] == 'degrees',
                                      100 * np.tan(df['plot_slope'] * np.pi / 180),
                                      df['plot_slope'].astype(float)).round(1)

    # ### SAVE DATASETS TO OUTPUT FOLDER
    os.makedirs(out_folder, exist_ok=True)
    helper.export_csv(df, os.path.join(out_folder, 'survey_0.csv'))

    return df
