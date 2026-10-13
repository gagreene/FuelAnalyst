# -*- coding: utf-8 -*-
"""
Created on Tue May 27, 9:30:00 2025

@author: Gregory A. Greene
"""
__author__ = ['Gregory A. Greene']

import os
import pandas as pd
import numpy as np

from . import helper, table_reader


def process_plot_attributes(in_folder: 'str | table_reader.FormSource', out_folder: str) -> tuple[pd.DataFrame, list]:
    """
    Get the plot attributes from a CSV file and return as an updated DataFrame.

    :param in_folder: Path to the form folder of input tables, or a resolved FormSource.
    :param out_folder: Path to the folder where output CSV files will be saved.
    :return: DataFrame with processed tree attributes.
    """
    print('\nProcessing Plot Attribute data')
    in_folder = table_reader.ensure_form_source(in_folder)

    # ### PROCESS PLOT ATTRIBUTE DATA
    # Get plot attributes dataframe
    df = table_reader.read_table(in_folder, 'survey_0')
    # Generate a unique ID for each plot
    df = helper.get_unique_id(df)

    # Calculate slope as % -- keep the unrounded value for the exact-zero check
    # below so a tiny nonzero slope that would round to display 0.0 isn't
    # misclassified as flat.
    _slope_pct_unrounded = np.where(df['plot_slope_units'] == 'degrees',
                                      100 * np.tan(df['plot_slope'] * np.pi / 180),
                                      df['plot_slope'].astype(float))
    df['plot_slope_pct'] = np.round(_slope_pct_unrounded, 1)

    # Aspect may be undefined on flat ground (slope == 0). Force it to 270 for
    # downstream consumers, but only when the source data provides an aspect
    # column at all -- some inputs (and test fixtures) omit it entirely.
    if 'plot_aspect' in df.columns:
        df['plot_aspect'] = df['plot_aspect'].where(_slope_pct_unrounded != 0, 270)

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
