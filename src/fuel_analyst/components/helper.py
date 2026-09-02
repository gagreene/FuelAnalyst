# -*- coding: utf-8 -*-
"""
Created on Tue May 27, 9:25:00 2025

@author: Gregory A. Greene
"""
__author__ = ['Gregory A. Greene']

import csv as CSV
import os
import re
import shutil
import pandas as pd


def add_line_to_csv(file_path: str, add_list: list, position: int) -> None:
    """
    Add a line to a CSV file at a specified position.

    :param file_path: Path to the CSV file.
    :param add_list: List of values to add as a new line in the CSV.
    :param position: Line number (0-indexed) where the new line should be inserted.
    :return: None
    """
    with open(file_path, 'r') as in_file:
        reader = list(CSV.reader(in_file))
        reader.insert(position, add_list)

    with open(file_path, 'w', newline='') as out_file:
        writer = CSV.writer(out_file)
        for line in reader:
            writer.writerow(line)


def attach_columns(df: pd.DataFrame, columns: dict | pd.DataFrame) -> pd.DataFrame:
    """
    Attach calculated columns while replacing existing columns with the same names.

    :param df: DataFrame receiving the calculated columns.
    :param columns: Mapping (or DataFrame) of output column names to calculated Series.
    :return: DataFrame with calculated columns attached and existing output columns
        replaced in their original positions.
    """
    output_names = list(columns)
    column_order = list(df.columns)
    column_order.extend(name for name in output_names if name not in df.columns)

    base_df = df.drop(columns=output_names, errors='ignore')
    result = pd.concat([base_df, pd.DataFrame(columns, index=df.index)], axis=1)
    return result.loc[:, column_order]


def delete_files(src_dir: str) -> None:
    """
    Delete all files and folders in the specified source directory.

    :param src_dir: Path to the source directory where files and folders will be deleted.
    :return: None
    """

    # Delete folders and files in src_dir if they already exist
    for item in os.listdir(src_dir):
        item_path = os.path.join(src_dir, item)
        if os.path.isfile(item_path):
            os.remove(item_path)
        elif os.path.isdir(item_path):
            shutil.rmtree(item_path)


def export_csv(df: pd.DataFrame, csv_path: str) -> None:
    """
    Export a DataFrame to a CSV file, overwriting the file if it already exists.

    :param df: DataFrame to export.
    :param csv_path: Path to the output CSV file.
    :return: None
    """
    # Remove the file if it already exists to avoid appending or file corruption
    if os.path.exists(csv_path):
        os.remove(csv_path)
    # Write the DataFrame to CSV without the index
    df.to_csv(csv_path, sep=',', index=False)
    return


def file_exists(file_path: str) -> bool:
    """
    Check if a file exists at the given path.

    :param file_path: Path to the file.
    :return: True if the file exists, False otherwise.
    """
    return os.path.isfile(file_path)


def get_development_dir(start_dir: str) -> str:
    """
    Get the root-level development directory for experimental scripts.

    :param start_dir: Directory to start searching from.
    :return: Absolute path to the repository development directory.
    """
    return os.path.join(get_repo_root(start_dir), 'development')


def get_df(csv_path: str) -> pd.DataFrame:
    """
    Read a CSV file into a pandas DataFrame.

    :param csv_path: Path to the CSV file.
    :return: DataFrame containing the CSV data.
    """
    print(f'\tGetting DataFrame from CSV file at: {csv_path}')
    # Read the CSV file with header row and no index column
    return pd.read_csv(csv_path, header=0, index_col=False, low_memory=False)


def get_examples_dir(start_dir: str) -> str:
    """
    Get the root-level examples directory for sample inputs and outputs.

    :param start_dir: Directory to start searching from.
    :return: Absolute path to the repository examples directory.
    """
    return os.path.join(get_repo_root(start_dir), 'examples')


def get_missing_df_columns(df: pd.DataFrame, required_columns: list) -> list:
    """
    Get a list of missing columns from a DataFrame based on a list of required column names.

    :param df: DataFrame to check.
    :param required_columns: List of required column names.
    :return: List of missing required columns.
    """
    missing_columns = [col for col in required_columns if col not in df.columns]
    return missing_columns


def get_repo_root(start_dir: str) -> str:
    """
    Find the repository root by walking upward from a starting directory.

    :param start_dir: Directory to start searching from.
    :return: Absolute path to the repository root.
    """
    current_dir = os.path.abspath(start_dir)

    while True:
        if (
            os.path.isdir(os.path.join(current_dir, 'src', 'fuel_analyst'))
            and os.path.isfile(os.path.join(current_dir, 'requirements.txt'))
        ):
            return current_dir

        parent_dir = os.path.dirname(current_dir)
        if parent_dir == current_dir:
            raise FileNotFoundError(f'Could not locate the repository root from: {start_dir}')
        current_dir = parent_dir


def get_unique_id(df: pd.DataFrame) -> pd.DataFrame:
    """
    Build canonical plot identifiers and retain the latest duplicate survey record.

    :param df: Survey123 parent-form DataFrame containing identity and date fields.
    :return: DataFrame with survey years, canonical unique IDs, and all but the
        latest record for each duplicate ID removed.
    """
    # Parse _date to datetime; try both known formats
    parsed = pd.to_datetime(df['_date'], format='%m/%d/%Y %H:%M', errors='coerce')
    mask = parsed.isna()
    if mask.any():
        parsed = parsed.copy()
        parsed[mask] = pd.to_datetime(df.loc[mask, '_date'], format='%m/%d/%Y %I:%M:%S %p', errors='coerce')

    still_missing = parsed.isna()
    if still_missing.any():
        bad_samples = df.loc[still_missing, '_date'].head(3).tolist()
        raise ValueError(
            f"'_date' column contains {still_missing.sum()} unparseable value(s). "
            f"Expected '%m/%d/%Y %H:%M' or '%m/%d/%Y %I:%M:%S %p'. "
            f"Sample bad values: {bad_samples}"
        )

    df['year'] = parsed.dt.year
    df['unique_id'] = df[['treatment_area', 'treatment_unit', 'treatment_type', 'plot_id', 'year']].apply(
        lambda x: '_'.join(x.astype(str)), axis=1)

    # Sort by parsed datetime (not raw string) so keep='last' correctly retains most recent
    df = df.assign(_date_parsed=parsed).sort_values(by='_date_parsed').drop_duplicates(subset='unique_id', keep='last')
    df = df.drop(columns=['_date_parsed'])

    return df


def sort_list(lst: list) -> list:
    """
    Sort a list of strings in alphanumeric order, handling both numbers and text correctly.

    :param lst: List of strings to be sorted.
    :return: Sorted list in alphanumeric order.
    """
    def alphanum_key(key):
        """
        Split one string into lowercase text and integer sort components.

        :param key: String value to convert into a natural-sort key.
        :return: Text and integer components used for alphanumeric sorting.
        """
        return [int(text) if text.isdigit() else text.lower()
                for text in re.split(r'(\d+)', key)]

    return sorted(lst, key=alphanum_key)

