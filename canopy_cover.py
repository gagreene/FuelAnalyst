# -*- coding: utf-8 -*-
"""
Created on Tue May 29, 8:30:00 2025

@author: Gregory A. Greene
"""
__author__ = ['Gregory A. Greene, map.n.trowel@gmail.com']

import os
import pandas as pd
import numpy as np
from datetime import datetime as dt
import helper

def process_canopy_cover(in_folder: str, out_folder: str) -> pd.DataFrame:
    """
    Process canopy cover data from a CSV file and return an updated DataFrame.

    :param in_folder: Path to the folder containing the input CSV files.
    :param out_folder: Path to the folder where output CSV files will be saved.
    :return: DataFrame with processed canopy cover attributes.
    """
    print('Processing Canopy Cover data')

    # Get canopy cover dataframe
    df = helper.get_df(os.path.join(in_folder, 'canopy_cover.csv'))

    # Generate a unique ID for each plot
    df['year'] = df['_date'].apply(lambda y: dt.strptime(y, '%m/%d/%Y %I:%M:%S %p').year)
    df['uniqueID'] = df[['treatment_area', 'treatment_unit', 'treatment_unit_other', 'plot_id', 'year']].apply(
        lambda x: ''.join(x.astype(str)), axis=1)

    # Save the processed DataFrame to the output folder
    os.makedirs(out_folder, exist_ok=True)
    helper.export_csv(df, os.path.join(out_folder, 'canopy_cover.csv'))

    return df
