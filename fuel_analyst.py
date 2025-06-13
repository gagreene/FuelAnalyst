# -*- coding: utf-8 -*-
"""
Created on Tue May 28, 15:00:00 2025

@author: Gregory A. Greene
"""
__author__ = ['Gregory A. Greene, map.n.trowel@gmail.com']

import os
import pandas as pd
import helper
import plot_attributes as pa
import plants_regen as pr
import trees
import canopy_cover as cc
import woody_debris as wd
import fofem_attributes
from typing import Optional

default_stand_summary_dict = {
    'dens': {
        'summary': ['total', 'live', 'dead', 'conifer', 'broadleaf'],  # These are the only options
        'metrics': ['sum'],  # These options are fixed
        'classes': {
            'dbh': [5, 7.5, 12.5]
        },
    },
    'ba': {
        'summary': ['total', 'live', 'dead', 'conifer', 'broadleaf'],  # These are the only options
        'metrics': ['sum'],  # These options are fixed
        'classes': {
            'dbh': [5, 7.5, 12.5]
        },
    },
    'ht': {
        'summary': ['total', 'live', 'dead', 'conifer', 'broadleaf'],  # These are the only options
        'metrics': ['max', 'mean'],  # These are the only options
        'classes': {
            'dbh': [5]
        },
    },
    'cbh': {
        'summary': ['total', 'live', 'conifer', 'broadleaf'],  # These are the only options
        'metrics': ['min', 'max', 'mean'],  # These are the only options
        'classes': {
            'dbh': [5]
        },
    },
    'dcbh': {
        'summary': ['total', 'live', 'dead', 'conifer', 'broadleaf'],  # These are the only options
        'metrics': ['min', 'max', 'mean'],  # These are the only options
        'classes': {
            'dbh': [5]
        },
    },
    'fsg': {
        'summary': ['total', 'live', 'dead', 'conifer', 'broadleaf'],  # These are the only options
        'metrics': ['min', 'max', 'mean'],  # These are the only options
        'classes': {
            'dbh': [5]
        },
    },
    'cfl': {
        'summary': ['total', 'conifer', 'broadleaf'],  # These are all live trees
        'metrics': ['min', 'max', 'mean', 'sum'],  # These are the only options
        'classes': {
            'dbh': [5]
        },
    },
    'cbd': {
        'summary': ['total', 'conifer', 'broadleaf'],  # These are all live trees
        'metrics': [],  # This is fixed as empty (no user options)
        'classes': {
            'dbh': [5]
        },
    },
    'flame_length': {
        'summary': ['total'],  # This is fixed (no user options)
        'metrics': ['min', 'max', 'mean'],  # These are the only options
    },
    'fire_intensity': {
        'summary': ['total'],  # This is fixed (no user options)
        'metrics': ['min', 'max', 'mean'],  # These are the only options
    },
}


def fuel_analyst(in_folder: str,
                 out_folder: str,
                 surface_fire_intensity_model: str,
                 stand_summary: Optional[dict] = None,
                 gen_fofem_tree_df: bool = False,
                 gen_fofem_consume_df: bool = False,
                 fofem_consume_moisture_var: str = 'Dry') -> None:
    """
    Main Fuel Analyst function to process the fuel attributes and save the results.

    :param in_folder: Path to the input folder containing the survey data.
    :param out_folder: Path to the output folder where results will be saved.
    :param surface_fire_intensity_model: Model to use for surface fire intensity calculations.
    :param stand_summary: List containing stand summary parameters.
    :param gen_fofem_tree_df: Boolean indicating whether to generate the FOFEM tree DataFrame.
    :param gen_fofem_consume_df: Boolean indicating whether to generate the FOFEM consumption DataFrame.
    :param fofem_consume_moisture_var: Moisture regime for FOFEM consumption (default is 'Dry').
    :return: None
    """
    # Create a dictionary to map form names to their respective folder names
    folder_dict = {
        'plot': '1_Plot_Attributes',
        'plants': '2_Plants_Regeneration',
        'trees': '3_Trees',
        'cover': '4_Canopy_Cover',
        'woody': '5_Woody_Debris'
    }

    # Create a dictionary to map form names to their display names
    form_dict = {
        'plot': 'Plot Attributes',
        'plants': 'Plants and Regeneration',
        'trees': 'Trees',
        'cover': 'Canopy Cover',
        'woody': 'Woody Debris'
    }

    if stand_summary is None:
        stand_summary = default_stand_summary_dict

    # Create the list of forms to process
    form_select_list = ['plants', 'trees', 'cover', 'woody']

    # Generate a list of columns to keep, using all columns in plot_df to begin with
    keep_columns = ['unique_id']
    form_df = None
    master_tree_df = None
    fofem_tree_df = None
    fofem_consume_df = None

    # Process plot attributes
    plot_df, add_columns = pa.process_plot_attributes(os.path.join(in_folder, folder_dict.get('plot')),
                                                      os.path.join(out_folder, folder_dict.get('plot')))
    keep_columns.extend(add_columns)

    # Process selected forms
    for form in form_select_list:
        # Get the input and output paths for the current form
        in_path = os.path.join(in_folder, folder_dict.get(form))
        out_path = os.path.join(out_folder, folder_dict.get(form))

        # Check if the input path exists
        if not os.path.exists(in_path):
            print(f'Warning: Input folder for {form} does not exist: {in_path}')
            continue

        # Filter the plot_df for the current form
        mask = plot_df['form_select'].str.contains(form, na=False)

        # Get the unique IDs for the current form
        id_list = plot_df.loc[mask, 'unique_id'].tolist()

        # Only process the form if there are IDs to process
        if mask.any():
            if form == 'plants':
                form_df, add_columns = pr.process_plants_regen(in_path, out_path)
            elif form == 'trees':
                (form_df, add_columns,
                 master_tree_df) = trees.process_trees(in_path,
                                                       out_path,
                                                       surface_fire_intensity_model,
                                                       stand_summary)
            elif form == 'cover':
                form_df, add_columns = cc.process_canopy_cover(in_path, out_path)
            elif form == 'woody':
                form_df, add_columns = wd.process_woody_debris(in_path, out_path, plot_df[mask])

            # Add the new columns to the keep_columns list
            keep_columns.extend(add_columns)

            # Verify that all IDs in id_list are present in the form_df
            if not all(id in form_df['unique_id'].values for id in id_list):
                missing_ids = [id for id in id_list if id not in form_df['unique_id'].values]
                print(f'\tWarning:')
                print(f'\t\tThe following plots are missing data in the {form_dict[form]} data: {missing_ids}')
                missing_ids = [id for id in form_df['unique_id'].values if id not in id_list]
                print(f'\t\tThe following IDs are in the {form_dict[form]} data, '
                      f'but not in Plot Attributes: {missing_ids}')
            else:
                print(f'\tAll IDs from plot_df are present in {form} data. Merging data.')

            # Drop columns in form_df that are already in plot_df, except for unique_id
            form_df = form_df.drop(
                columns=[col for col in form_df.columns if col in plot_df.columns and col != 'unique_id']
            )

            # Merge the form_df with plot_df based on unique_id
            plot_df = pd.merge(plot_df, form_df, on='unique_id', how='left')

    # ### PROCESS FOFEM DATA
    if gen_fofem_tree_df:
        fofem_tree_df = fofem_attributes.gen_fofem_tree_df(plot_df, master_tree_df)
    if gen_fofem_consume_df:
        fofem_consume_df = fofem_attributes.gen_fofem_consumption_df(plot_df, fofem_consume_moisture_var)

    # ### PROCESS OUTPUTS
    # Make the out_folder if it does not exist
    os.makedirs(out_folder, exist_ok=True)

    # Save the Master Fuel DataFrame to the output folder if it exists
    if plot_df is not None:
        master_df_path = os.path.join(out_folder, 'master_fuel_df.csv')
        print(f'Saving the Master Fuel DataFrame to: {master_df_path}')
        plot_df = plot_df[keep_columns]  # Keep only the specified columns
        helper.export_csv(plot_df, master_df_path)

    # Save the Master Tree DataFrame to the output folder if it exists
    if master_tree_df is not None:
        master_tree_df_path = os.path.join(out_folder, 'master_tree_df.csv')
        print(f'Saving the Master Tree DataFrame to: {master_tree_df_path}')
        helper.export_csv(master_tree_df, master_tree_df_path)

    # Save the FOFEM Tree DataFrame to the output folder if it exists
    if fofem_tree_df is not None:
        fofem_tree_df_path = os.path.join(out_folder, 'fofem_tree_df.csv')
        print(f'Saving the FOFEM Tree DataFrame to: {fofem_tree_df_path}')
        helper.export_csv(fofem_tree_df, fofem_tree_df_path)

    # Save the FOFEM Consumption DataFrame to the output folder if it exists
    if fofem_consume_df is not None:
        fofem_consume_df_path = os.path.join(out_folder, 'fofem_consume_df.csv')
        print(f'Saving the FOFEM Consumption DataFrame to: {fofem_consume_df_path}')
        helper.export_csv(fofem_consume_df, fofem_consume_df_path)

    return


if __name__ == '__main__':
    # Define input and output folders
    _in_folder = r'E:\UBC_FuelAnalyst_Testing\Survey123_Data\Survey_Data'
    _out_folder = r'E:\UBC_FuelAnalyst_Testing\Survey123_Data\_Results'
    _surface_fire_intensity_model = 'Byram'
    _stand_summary_dict = None
    _gen_fofem_tree_df = True  # Whether to generate the FOFEM tree DataFrame
    _gen_fofem_consume_df = False  # Whether to generate the FOFEM consumption DataFrame
    _fofem_consume_moisture_var = 'Very Dry'  # Moisture regime setting for FOFEM consumption

    # Run the main fuel_analyst function
    fuel_analyst(in_folder=_in_folder,
                 out_folder=_out_folder,
                 surface_fire_intensity_model=_surface_fire_intensity_model,
                 stand_summary=_stand_summary_dict,
                 gen_fofem_tree_df=_gen_fofem_tree_df,
                 gen_fofem_consume_df=_gen_fofem_consume_df)
