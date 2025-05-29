# -*- coding: utf-8 -*-
"""
Created on Tue May 28, 15:00:00 2025

@author: Gregory A. Greene
"""
__author__ = ['Gregory A. Greene, map.n.trowel@gmail.com']

import os
import pandas as pd
import numpy as np
from datetime import datetime as dt
import helper
import plot_attributes as pa
import plants_regen as pr
import trees
import canopy_cover as cc
import woody_debris as wd


def main():
    """
    Main function to process the fuel attributes and save the results.
    """
    # Define input and output folders
    in_folder = r'E:\UBC_FuelAnalyst_Testing\Survey123_Data\Survey_Data'
    out_folder = r'E:\UBC_FuelAnalyst_Testing\Survey123_Data\_Results'

    # form_select_list = ['plants', 'trees', 'cover', 'woody']
    form_select_list = ['plants', 'trees']

    # Process plot attributes
    plot_df = pa.process_plot_attributes(in_folder, out_folder)

    # Process selected forms
    for form in form_select_list:
        mask = plot_df['form_select'].str.contains(form, na=False)
        id_list = plot_df.loc[mask, 'uniqueID'].tolist()
        if mask.any():
            if form == 'plants':
                form_df = pr.process_plants_regen(in_folder, out_folder)
            elif form == 'trees':
                form_df = trees.process_trees(in_folder, out_folder)
            elif form == 'cover':
                form_df = cc.process_canopy_cover(in_folder, out_folder)
            elif form == 'woody':
                form_df = wd.process_woody_debris(in_folder, out_folder)

        # Verify that all IDs in id_list are present in the form_df
        if not all(id in form_df['uniqueID'].values for id in id_list):
            missing_ids = [id for id in id_list if id not in form_df['uniqueID'].values]
            print(f'Warning: The following IDs are missing in {form} data: {missing_ids}')
            for missing_id in missing_ids:
                print(f'{missing_id}')
        else:
            print(f'All IDs from plot_df are present in {form} data. Merging data.')

        # Drop columns in form_df that are already in plot_df, except for uniqueID
        form_df = form_df.drop(columns=[col for col in form_df.columns if col in plot_df.columns and col != 'uniqueID'])

        # Merge the form_df with plot_df based on uniqueID
        plot_df = pd.merge(plot_df, form_df, on='uniqueID', how='left', suffixes=('', f'_{form}'))

    # Save the final merged DataFrame to the output folder
    os.makedirs(out_folder, exist_ok=True)
    helper.export_csv(plot_df, os.path.join(out_folder, 'master_fuel_df.csv'))


if __name__ == '__main__':
    main()
