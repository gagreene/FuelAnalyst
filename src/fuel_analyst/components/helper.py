# -*- coding: utf-8 -*-
"""
Created on Tue May 27, 9:25:00 2025

@author: Gregory A. Greene
"""
__author__ = ['Gregory A. Greene, map.n.trowel@gmail.com']

import os
import pandas as pd
from datetime import datetime as dt
import re


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


def get_df(csv_path):
    """
    Read a CSV file into a pandas DataFrame.

    :param csv_path: Path to the CSV file.
    :return: DataFrame containing the CSV data.
    """
    print(f'\tGetting DataFrame from CSV file at: {csv_path}')
    # Read the CSV file with header row and no index column
    return pd.read_csv(csv_path, header=0, index_col=False)


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

    # Drop duplicate rows based on 'unique_id', keeping the most recent entry based on _date column
    df = df.sort_values(by='_date').drop_duplicates(subset='unique_id', keep='last')

    return df

def sort_list(lst: list) -> list:
    """
    Sort a list of strings in alphanumeric order, handling both numbers and text correctly.

    :param lst: List of strings to be sorted.
    :return: Sorted list in alphanumeric order.
    """
    def alphanum_key(key):
        return [int(text) if text.isdigit() else text.lower()
                for text in re.split(r'(\d+)', key)]

    return sorted(lst, key=alphanum_key)

