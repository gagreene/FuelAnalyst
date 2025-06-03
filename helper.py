# -*- coding: utf-8 -*-
"""
Created on Tue May 27, 9:25:00 2025

@author: Gregory A. Greene
"""
__author__ = ['Gregory A. Greene, map.n.trowel@gmail.com']

import os
import pandas as pd
from datetime import datetime as dt


def get_df(csv_path):
    """
    Read a CSV file into a pandas DataFrame.

    :param csv_path: Path to the CSV file.
    :return: DataFrame containing the CSV data.
    """
    # Read the CSV file with header row and no index column
    return pd.read_csv(csv_path, header=0, index_col=False)


def export_csv(df: pd.DataFrame, csv_path: str) -> None:
    """
    Export a DataFrame to a CSV file, overwriting the file if it already exists.

    :param df: DataFrame to export.
    :param csv_path: Path to the output CSV file.
    """
    # Remove the file if it already exists to avoid appending or file corruption
    if os.path.exists(csv_path):
        os.remove(csv_path)
    # Write the DataFrame to CSV without the index
    df.to_csv(csv_path, sep=',', index=False)
    return

def get_unique_id(df: pd.DataFrame) -> pd.DataFrame:
    try:
        df['year'] = df['_date'].apply(lambda y: dt.strptime(y, '%m/%d/%Y %H:%M').year)
    except ValueError:
        try:
            df['year'] = df['_date'].apply(lambda y: dt.strptime(y, '%m/%d/%Y %H:%M:%S %p').year)
        except ValueError:
            print("Date format in '_date' column is not recognized. Please check the date format.")
    df['unique_id'] = df[['treatment_area', 'treatment_unit', 'treatment_type', 'plot_id', 'year']].apply(
        lambda x: '_'.join(x.astype(str)), axis=1)

    return df

