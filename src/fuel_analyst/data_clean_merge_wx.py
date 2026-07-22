# -*- coding: utf-8 -*-
"""
Created on Monday July 20th, 2026

@author: Sarah Smith-Tripp
"""
__author__ = ['Sarah Smith-Tripp, sarahsmith.tripp@gmail.com']

import os
from fuel_analyst.components.trees import _calc_plot_multipliers
import numpy as np
import pandas as pd
from typing import Union
from fuel_analyst.extract_BECType import create_joined_geopackage
from fuel_analyst.components import plot_attributes as pa
from fuel_analyst.extract_BECType import _load_plots, _extract_BECType  
from fuel_analyst.components import helper
from fuel_analyst.components import trees
# ── Environment detection ────────────────────────────────────────────────────
is_docker = os.path.exists('/.dockerenv')
# set folder structures 
dir_dict = {
    'plot': '1_Plot_Attributes',
    'plants': '2_Plants_Regeneration',
    'trees': '3_Trees',
    'cover': '4_Canopy_Cover',
    'woody': '5_Woody_Debris'
}
## set default dictionary

default_stand_summary_dict = {
    'dens': {
        'att_source': 'dens',  # This could be user specified/adjusted
        'override_field_name': False, # This is fixed as False for stand summaries
        'summary': ['total', 'live', 'dead', 'conifer', 'broadleaf'],  # These are the only options
        'summary_permutation': 'all',  # This is the default (options: 'all', 'exact', 'combined')
        'metrics': ['sum'],  # These options are fixed
        'units': 'tpha',  # This option is fixed
        'classes': {
            'dbh': [0, 5, 7.5, 12.5, float('inf')]
        },
    },
    'ba': {
        'att_source': 'ba',  # This could be user specified/adjusted
        'override_field_name': False, # This is fixed as False for stand summaries
        'summary': ['total', 'live', 'dead', 'conifer', 'broadleaf'],  # These are the only options
        'summary_permutation': 'all',  # This is the default (options: 'all', 'exact', 'combined')
        'metrics': ['sum'],  # These options are fixed
        'units': 'm2pha',  # This option is fixed
        'classes': {
            'dbh': [0, 5, 7.5, 12.5, float('inf')]
        },
    },
    'ht': {
        'att_source': 'ht',  # This could be user specified/adjusted
        'override_field_name': False, # This is fixed as False for stand summaries
        'summary': ['total', 'live', 'dead', 'conifer', 'broadleaf'],  # These are the only options
        'summary_permutation': 'all',  # This is the default (options: 'all', 'exact', 'combined')
        'metrics': ['max', 'mean'],  # These are the only options
        'units': 'm',  # This option is fixed
        'classes': {
            'dbh': [0, 5, float('inf')]
        },
    },
    'cbh': {
        'att_source': 'cbh',  # This could be user specified/adjusted
        'override_field_name': False, # This is fixed as False for stand summaries
        'summary': ['total', 'live', 'conifer', 'broadleaf'],  # These are the only options
        'summary_permutation': 'all',  # This is the default (options: 'all', 'exact', 'combined')
        'metrics': ['min', 'max', 'mean'],  # These are the only options
        'units': 'm',  # This option is fixed
        'classes': {
            'dbh': [0, 5, float('inf')]
        },
    },
    'dcbh': {
        'att_source': 'dcbh',  # This could be user specified/adjusted
        'override_field_name': False, # This is fixed as False for stand summaries
        'summary': ['total', 'live', 'dead', 'conifer', 'broadleaf'],  # These are the only options
        'summary_permutation': 'all',  # This is the default (options: 'all', 'exact', 'combined')
        'metrics': ['min', 'max', 'mean'],  # These are the only options
        'units': 'm',  # This option is fixed
        'classes': {
            'dbh': [0, 5, float('inf')]
        },
    },
    'fsg': {
        'att_source': 'fsg',  # This could be user specified/adjusted
        'override_field_name': False, # This is fixed as False for stand summaries
        'summary': ['total', 'live', 'dead', 'conifer', 'broadleaf'],  # This is the default
        'summary_permutation': 'all',  # This is the default (options: 'all', 'exact', 'combined')
        'metrics': ['min', 'max', 'mean'],  # These are the only options
        'units': 'm',  # This option is fixed
        'classes': {
            'dbh': [0, 5, float('inf')]
        },
    },
    'cfl': {
        'att_source': 'cfl',  # This could be user specified/adjusted
        'override_field_name': False, # This is fixed as False for stand summaries
        'summary': ['live', 'conifer'],  # This is the default
        'summary_permutation': 'all',  # This is the default (options: 'all', 'exact', 'combined')
        'metrics': ['min', 'max', 'mean', 'sum'],  # These are the only options
        'units': 'kgpm2',  # This option is fixed
        'classes': {
            'dbh': [0, 5, float('inf')]
        },
    },
    'cbd': {
        'att_source': 'cbd',  # This could be user specified/adjusted
        'override_field_name': False, # This is fixed as False for stand summaries
        'summary': ['live', 'conifer'],  # This is the default
        'summary_permutation': 'all',  # This is the default (options: 'all', 'exact', 'combined')
        'metrics': [],  # This is fixed as empty (no user options)
        'units': 'kgpm3',  # This option is fixed
        'classes': {
            'dbh': [0, 5, float('inf')]
        },
    },
    'foliage': {
        'att_source': 'foliage',  # This could be user specified/adjusted
        'override_field_name': False, # This is fixed as False for stand summaries
        'summary': ['live', 'conifer', 'broadleaf'],  # These are all live trees
        'summary_permutation': 'all',  # This is the default (options: 'all', 'exact', 'combined')
        'metrics': ['sum'],  # This is the only option
        'units': 'kgpm2',  # This option is fixed
        'classes': {
            'dbh': [0, float('inf')]
        },
    },
    'branches': {
        'att_source': 'branches',  # This could be user specified/adjusted
        'override_field_name': False, # This is fixed as False for stand summaries
        'summary': ['live', 'dead', 'conifer', 'broadleaf'],  # These are the only options
        'summary_permutation': 'all',  # This is the default (options: 'all', 'exact', 'combined')
        'metrics': ['sum'],  # This is the only option
        'units': 'kgpm2',  # This option is fixed
        'classes': {
            'dbh': [0, float('inf')]
        },
    },
    'wood': {
        'att_source': 'wood',  # This could be user specified/adjusted
        'override_field_name': False, # This is fixed as False for stand summaries
        'summary': ['live', 'dead', 'conifer', 'broadleaf'],  # These are the only options
        'summary_permutation': 'all',  # This is the default (options: 'all', 'exact', 'combined')
        'metrics': ['sum'],  # This is the only option
        'units': 'kgpm2',  # This option is fixed
        'classes': {
            'dbh': [0, float('inf')]
        },
    },
    'bark': {
        'att_source': 'bark',  # This could be user specified/adjusted
        'override_field_name': False, # This is fixed as False for stand summaries
        'summary': ['live', 'dead', 'conifer', 'broadleaf'],  # These are the only options
        'summary_permutation': 'all',  # This is the default (options: 'all', 'exact', 'combined')
        'metrics': ['sum'],  # This is the only option
        'units': 'kgpm2',  # This option is fixed
        'classes': {
            'dbh': [0, float('inf')]
        },
    },
    'flame_length': {
        'att_source': 'flame_length',  # This could be user specified/adjusted
        'override_field_name': False, # This is fixed as False for stand summaries
        'summary': ['total'],  # This is fixed (no user options)
        'summary_permutation': 'exact',  # This is fixed (no user options)
        'metrics': ['min', 'max', 'mean'],  # These are the only options
        'units': 'm',  # This option is fixed
    },
    'fire_intensity': {
        'att_source': 'fire_intensity',  # This could be user specified/adjusted
        'override_field_name': False, # This is fixed as False for stand summaries
        'summary': ['total'],  # This is fixed (no user options)
        'summary_permutation': 'exact',  # This is fixed (no user options)
        'metrics': ['min', 'max', 'mean'],  # These are the only options
        'units': 'kWpm2',  # This option is fixed
    },
}

# ── 1. Set Sources ──────────────────────────────────────────────────────────
if not is_docker:
    raise ValueError('This script is intended to run in a Docker environment. Please set up the required environment variables and run within Docker.')
## Check that all of the directories are available and contain expected files
# Create the list of forms to process
# ────────────────────────────────────────────────────────────

def get_unique_id_strip(df: pd.DataFrame) -> pd.DataFrame:
    # Parse _date to datetime; try both known formats
    parsed = pd.to_datetime(df['_date'], format='%m/%d/%Y %H:%M', errors='coerce')
    mask = parsed.isna()
    if mask.any():
        parsed = parsed.copy()
        parsed[mask] = pd.to_datetime(df.loc[mask, '_date'], format='%m/%d/%Y %H:%M:%S %p', errors='coerce')

    still_missing = parsed.isna()
    if still_missing.any():
        bad_samples = df.loc[still_missing, '_date'].head(3).tolist()
        raise ValueError(
            f"'_date' column contains {still_missing.sum()} unparseable value(s). "
            f"Expected '%m/%d/%Y %H:%M' or '%m/%d/%Y %H:%M:%S %p'. "
            f"Sample bad values: {bad_samples}"
        )

    df['year'] = parsed.dt.year
    ## strip the spaces in these different columns 
    df['unique_id'] = df[['treatment_area', 'treatment_unit', 'treatment_type', 'plot_id', 'year']].apply(
         lambda x: '_'.join(x.astype(str).str.strip()), axis=1) 

    # Sort by parsed datetime (not raw string) so keep='last' correctly retains most recent
    df = df.assign(_date_parsed=parsed).sort_values(by='_date_parsed').drop_duplicates(subset='unique_id', keep='last')
    df = df.drop(columns=['_date_parsed'])

    return df

## FOLDER CHECKING HERE 
def folder_check(in_dir: str, form_select_list: list,
                 dir_dict: dict) -> None:
    """Check that the required Survey123 form directories exist in the input directory. 
    Args:
        in_dir (str): The input directory containing the Survey123 form directories.
        form_select_list (list): A list of form names to check for existence.
        dir_dict (dict): A dictionary mapping form names to their respective directory names.   
    Raises:
        FileNotFoundError: If any of the required form directories are missing.
    """
    form_select_list = ['plants', 'trees', 'cover', 'woody']

    # Create a dictionary to map form names to their display names
    form_dict = {
        'plot': 'Plot Attributes',
        'plants': 'Plants and Regeneration',
        'trees': 'Trees',
        'cover': 'Canopy Cover',
        'woody': 'Woody Debris'
    }
    missing_forms = [
        form for form in form_select_list
        if not os.path.exists(os.path.join(in_dir, dir_dict.get(form)))
    ]
    if missing_forms:
        raise FileNotFoundError(
            f'Not all Survey123 form directories were found in the input directory: {in_dir}. '
            f'The following forms are missing:\n{missing_forms}.'
            )
    return f'All required Survey123 form directories were found in the input directory: {in_dir}.'
def export_set(in_dir: str, out_dir: str, form_select_list: list,
               dir_dict: dict) -> dict:
    """Create an output folder per selected Survey123 form, mirroring the input structure.

    Validates that each selected form's directory exists under in_dir, then creates
    a folder of the same name under out_dir (so out_dir mirrors in_dir). Returns a
    dict mapping form -> output path for use as that form's output directory.
    """
    # Validate that each selected form's input directory exists
    missing = [
        form for form in form_select_list
        if form not in dir_dict
        or not os.path.isdir(os.path.join(in_dir, dir_dict[form]))
    ]
    if missing:
        raise FileNotFoundError(
            f'Not all Survey123 form directories were found in {in_dir}. '
            f'Missing forms: {missing}.'
        )

    # Mirror the input folder names (e.g. '3_Trees') under out_dir
    out_dirs = {}
    for form in form_select_list:
        path = os.path.join(out_dir, dir_dict[form])
        os.makedirs(path, exist_ok=True)
        out_dirs[form] = path
    
    return out_dirs
def plot_data_check(in_dir: str, dir_dict: dict, out_dir: str) -> pd.DataFrame:
    """Read the survey file(s) in each Survey123 form directory, generate a unique_id
    for each form's records, and compare which unique_ids are present across forms.

    Args:
        in_dir (str): The input directory containing the Survey123 form directories.
        dir_dict (dict): A dictionary mapping form names to their respective directory names.
        out_dir (str): The output directory to save the comparison report to.

    Returns:
        pd.DataFrame: A DataFrame indicating, for each unique_id, which forms it was found in.
    """
    form_ids = {}
    for form, dirname in dir_dict.items():
        form_dir = os.path.join(in_dir, dirname)
        survey_files = sorted(
            f for f in os.listdir(form_dir)
            if 'survey' in f.lower() and f.endswith('.csv')
        )
        if not survey_files:
            print(f"Warning: No survey file found for form '{form}' in directory: {form_dir}")
            continue

        form_df = pd.concat(
            [get_unique_id_strip(helper.get_df(os.path.join(form_dir, f))) for f in survey_files],
            ignore_index=True
        )
        form_ids[form] = set(form_df['unique_id'])

    if not form_ids:
        raise FileNotFoundError(f'No survey files were found in any form directory under: {in_dir}')

    # Build a membership table across all unique_ids found in any form
    all_ids = sorted(set().union(*form_ids.values()))
    membership = pd.DataFrame({'unique_id': all_ids})
    for form in form_ids:
        membership[form] = membership['unique_id'].isin(form_ids[form])

    # Flag unique_ids that are missing from at least one form
    membership['missing_from_forms'] = membership[list(form_ids.keys())].apply(
        lambda row: ', '.join(form for form in form_ids if not row[form]), axis=1
    )
    mismatches = membership[membership['missing_from_forms'] != '']
    # All error/flagged files go in one shared data_check folder under out_dir
    check_dir = os.path.join(out_dir, 'data_check')
    os.makedirs(check_dir, exist_ok=True)

    if not mismatches.empty:
        mismatch_path = os.path.join(check_dir, 'unique_id_mismatches.csv')
        helper.export_csv(mismatches, mismatch_path)
        print(f"Warning: {len(mismatches)} unique_id(s) are missing from at least one form. "
              f"Details saved to: {mismatch_path}")
    else:
        print('All unique_ids are present across all forms.')

    return membership
# ────────────────────────────────────────────────────────────
def plot_attributes_read(in_dir: str, out_dirs: dict, spatial: bool = False) -> pd.DataFrame:
    # Resolve this form's output folder from the export_set dict
    if 'plot' not in out_dirs:
        raise KeyError(
            "No 'plot' entry in out_dirs. Include 'plot' in the form_select_list "
            "passed to export_set so its output folder gets created."
        )
    out_dir = out_dirs['plot']

    plot_dir = os.path.join(in_dir, dir_dict.get('plot'))
    print(plot_dir)

    # List all survey CSVs in the plot directory
    plot_files = sorted(f for f in os.listdir(plot_dir)
                        if f.startswith('survey_0') and f.endswith('.csv'))
    print(plot_files)

    survey_file = os.path.join(plot_dir, plot_files[0]) if plot_files else None
    if not survey_file:
        raise FileNotFoundError(
            f'No survey_0*.csv file found in the Plot Attributes directory: {plot_dir}.'
        )

    # Load plots as geodataframe and check for missing lat/long values
    plot_gdf = _load_plots(survey_file, lat='y', lon='x')
    plot_gdf = get_unique_id_strip(plot_gdf)
# All error/flagged files go in one shared data_check folder under out_dir
    check_dir = os.path.join(out_dir, 'data_check')
    os.makedirs(check_dir, exist_ok=True)

    # Attribute range check: elevation, slope, aspect
    plot_gdf['flagged_attributes'] = (
        plot_gdf['plot_elevation'].lt(0) | plot_gdf['plot_elevation'].gt(3500) |
        plot_gdf['plot_slope'].lt(0)     | plot_gdf['plot_slope'].gt(90)       |
        plot_gdf['plot_aspect'].lt(0)    | plot_gdf['plot_aspect'].gt(360)
    )

    # Spatial check: True = coords present, False = missing (also flagged for export)
    plot_gdf['spatial'] = ~(plot_gdf['y'].isna() | plot_gdf['x'].isna())

    # Calculate slope as %
    plot_gdf['plot_slope_pct'] = np.where(
        plot_gdf['plot_slope_units'] == 'degrees',
        100 * np.tan(plot_gdf['plot_slope'] * np.pi / 180),
        plot_gdf['plot_slope'].astype(float)
    ).round(1)

    # Single flagged export: any attribute failure OR missing spatial
    flagged_mask = plot_gdf['flagged_attributes'] | ~plot_gdf['spatial']
    if flagged_mask.any():
        flagged_plots = plot_gdf.loc[flagged_mask, ['unique_id', 'flagged_attributes', 'spatial']]
        flagged_path = os.path.join(check_dir, 'flagged_plots.csv')
        helper.export_csv(flagged_plots, flagged_path)
        print(f'Warning: {len(flagged_plots)} plots flagged (attributes and/or missing spatial). '
              f'Details saved to: {flagged_path}')
    else:
        print('All plots passed attribute and spatial checks.')
    # Column management
    remove_columns = (
        ['ObjectID', 'GlobalID', 'unique_id', 'comments', 'plot_slope_units', 'plot_slope', 'year'] +
        [col for col in plot_gdf.columns if 'select' in col] +
        [col for col in plot_gdf.columns if col.startswith('witness_')] +
        [col for col in plot_gdf.columns if col.startswith('photo_')] +
        [col for col in plot_gdf.columns if col.startswith('Creat')] +
        [col for col in plot_gdf.columns if col.startswith('Edit')]
    )
    add_columns = [col for col in plot_gdf.columns.tolist() if col not in remove_columns]
   
    # Save datasets
    os.makedirs(out_dir, exist_ok=True)
    helper.export_csv(plot_gdf, os.path.join(out_dir, 'survey_0.csv'))
    if spatial:
        plot_gdf.to_file(os.path.join(out_dir, 'survey_0.gpkg'), driver='GPKG')

    return plot_gdf, add_columns
## using the plot_dt and unique ID column, create the next layer of data, the fpb_prep_csv 
def extract_BEC(plot_gdf: 'gpd.GeoDataFrame', 
                vri_polygon: str = None,
                write_sf: bool = False
                ) -> pd.DataFrame:
    """Extract BEC type information for each plot and save the updated DataFrame.
    Args:
        in_dir (str): The input directory containing the Survey123 form directories.
        out_dir (str): The output directory to save the updated DataFrame.
        plot_gdf (pd.DataFrame): A DataFrame containing the plot data.
        add_columns (list): A list of additional columns to include in the output DataFrame.
        bec_data (pd.DataFrame): A DataFrame containing BEC type information.
    Returns:
        pd.DataFrame: A DataFrame containing the updated plot data with BEC type information.   
    """
    bec_info_df = _extract_BECType(
            plots=plot_gdf,
            plot_id_col_name='unique_id',
            BEC_shp_dir=vri_polygon,
            BEC_layer='VEG_COMP_LYR_R1_POLY'
        )
    if write_sf:
            gpkg_out_path = os.path.join(_out_dir, 'plots.gpkg')
            create_joined_geopackage(
            plots=plot_gdf,
            bec_info_df=bec_info_df,
            plot_id_col='unique_id',
            output_path=gpkg_out_path
            )
    return bec_info_df

def subplot_data(in_dir: str, dir_dict: dict,
                 dir_get: str = None,
                 file_prefix: str = 'survey_0',
                 merge_plot: bool = False,
                 plot_df: pd.DataFrame = None,
                 out_dirs: dict = None) -> pd.DataFrame:
    """Read one subplot file from a Survey123 form directory and optionally merge with plot data.

    Args:
        in_dir (str): Input directory containing the Survey123 form directories.
        dir_dict (dict): Maps form names to their directory names.
        dir_get (str): Which form directory to read (e.g. 'trees', 'plants', 'cover', 'woody').
        file_prefix (str): Filename prefix to select within that directory (e.g.
            'survey_0', 'tree_plot', 'sapling'). The first matching '*.csv' is read.
        merge_plot (bool): Whether to merge plot data onto the subplot data. Defaults to False.
        plot_df (pd.DataFrame): Parent plot data to merge onto subplot data.
        out_dirs (dict): The {form: path} lookup from export_set. Flagged/error files
            go in a 'data_check' subfolder of this form's output dir.

    Returns:
        pd.DataFrame: The subplot data, merged with plot data when merge_plot is True.
    """
    if dir_get is None:
        raise ValueError('dir_get parameter is required')
    if out_dirs is None or dir_get not in out_dirs:
        raise KeyError(
            f"No '{dir_get}' entry in out_dirs. Include '{dir_get}' in the "
            "form_select_list passed to export_set so its output folder gets created."
        )

    check_dir = os.path.join(out_dirs[dir_get], 'data_check')
    os.makedirs(check_dir, exist_ok=True)

    print(f"Reading '{file_prefix}' data from '{dir_get}'")
    plot_dir = os.path.join(in_dir, dir_dict.get(dir_get))

    # Select the first CSV matching the requested prefix
    plot_files = sorted(f for f in os.listdir(plot_dir)
                        if f.startswith(file_prefix) and f.endswith('.csv'))
    survey_file = os.path.join(plot_dir, plot_files[0]) if plot_files else None
    if not survey_file:
        raise FileNotFoundError(f"No '{file_prefix}*.csv' file found in: {plot_dir}")

    # Generate the unique_id column and calculate attributes
    tree_df = helper.get_df(survey_file)
    tree_df = get_unique_id_strip(tree_df)
    tree_df = _calc_plot_multipliers(tree_df)

    if not merge_plot:
        return tree_df

    if plot_df is None:
        raise ValueError('Need parent plot data to merge on')

    sfx = f'_{dir_get}'   # suffix matches the form being read (e.g. '_trees', '_plants')
    out_df = pd.merge(plot_df, tree_df, on='unique_id', how='left', suffixes=('_plot', sfx))
    sfx = f'_{dir_get}'
    out_df = pd.merge(plot_df, tree_df, on='unique_id', how='left', suffixes=('_plot', sfx))

    # Coordinate mismatch check — only when both frames carried x/y (columns collided)
    x_sub, y_sub = f'x{sfx}', f'y{sfx}'
    coord_cols = {x_sub, y_sub, 'x_plot', 'y_plot'}
    if coord_cols.issubset(out_df.columns):
        coord_mismatch = (out_df[x_sub] != out_df['x_plot']) | (out_df[y_sub] != out_df['y_plot'])
        if coord_mismatch.any():
            mismatches = out_df[coord_mismatch]
            print(f"Warning: {len(mismatches)} rows have mismatched X or Y coordinates")
            mismatches[['unique_id', x_sub, 'x_plot', y_sub, 'y_plot']].to_csv(
                os.path.join(check_dir, 'coordinate_mismatches.csv'), index=False)
        out_df = out_df.drop(columns=[x_sub, y_sub])

    # Normalize plot coords to X/Y if present
    rename = {c: c.upper().replace('_PLOT', '') for c in ('x_plot', 'y_plot') if c in out_df.columns}
    return out_df.rename(columns=rename)
def tree_data_read(in_dir: str, out_dirs: dict, 
                   dir_dict: dict):
    """Read, validate, merge, and export individual-tree and sapling data.

    Reads the first 'tree_plot*.csv' and 'sapling*.csv' from the Trees form
    directory, validates each for reporting, merges saplings into the tree table
    (required for stand-level calculations), rounds the result, exports both raw
    tables, and returns the merged frame.

    Args:
        in_dir (str): Input directory of Survey123 form directories (Trees resolved
            via dir_dict['trees']).
        out_dir (dict): dictionary of outputs to tree data.

    Returns:
        pd.DataFrame: Merged tree + sapling table, rounded, ready for stand-level
        calculations.

    Raises:
        FileNotFoundError: If no 'tree_plot*.csv' or 'sapling*.csv' is found.

    Notes:
        tree_data_check returns only flagged rows, so its return is discarded here —
        reassigning from it would drop all valid data. The two checks write to
        separate subfolders because tree_data_check uses a fixed output filename.
    """
    # Create export folder locations 
    plot_dir = os.path.join(in_dir, dir_dict.get('trees'))
    out_dir = out_dirs['trees']                       # assign first
    check_dir = os.path.join(out_dir, 'data_check')   # then use it
    os.makedirs(check_dir, exist_ok=True)
    ## read necessary tree data 
    tree_params_df = helper.get_df(
        os.path.join(os.path.dirname(__file__), 'supporting_data', 'tree_parameters.csv')
    ).set_index('Species')

    # --- individual tree data ---
    tree_files = sorted(f for f in os.listdir(plot_dir)
                        if f.startswith('tree_plot') and f.endswith('.csv'))
    survey_file = os.path.join(plot_dir, tree_files[0]) if tree_files else None
    if not survey_file:
        raise FileNotFoundError(f'No individual tree data found in {plot_dir}')
    ind_tree_df = helper.get_df(survey_file)
    # Validate for reporting only — keep the full dataset
    tree_data_check(ind_tree_df, os.path.join(check_dir, 'trees'))

    # --- sapling data ---
    sapling_files = sorted(f for f in os.listdir(plot_dir)
                           if f.startswith('sapling') and f.endswith('.csv'))
    survey_file = os.path.join(plot_dir, sapling_files[0]) if sapling_files else None
    if not survey_file:
        raise FileNotFoundError(f'No sapling tree data found in {plot_dir}')
    sapling_df = helper.get_df(survey_file)
    # Calculate sapling attributes
    sapling_df = trees._calc_sapling_density(sapling_df)
    sapling_df = trees._calc_sapling_dbh(sapling_df)
    sapling_df = trees._calc_sapling_ht(sapling_df, tree_params_df)
    ## check for errors
    tree_data_check(sapling_df, os.path.join(check_dir, 'saplings'))

    # --- merge saplings into trees (needed for stand calculations), then round ---
    trees_df = trees._merge_saplings_to_trees(ind_tree_df, sapling_df)
    trees_df = trees._round_tree_data(trees_df)

    # --- export ---
    os.makedirs(out_dir, exist_ok=True)
    helper.export_csv(sapling_df,  os.path.join(out_dir, 'sapling_1.csv'))
    helper.export_csv(ind_tree_df, os.path.join(out_dir, 'tree_plot_2.csv'))

    return trees_df
def tree_data_check(in_df: pd.DataFrame, out_dir: str = '.') -> pd.DataFrame:
    """Flag tree/sapling records with out-of-range values or crown base height >= height.

    Columns are matched by measurement suffix (_dbh, _ht, _cbh), so any prefix
    works (tree_dbh, sapling_live_dbh, sapling_dead_cbh, ...). The cbh >= ht
    check pairs columns sharing a prefix (sapling_live_cbh vs sapling_live_ht).

    Returns flagged records (one row per tree, 'flags' lists every failed check),
    or an empty frame if all pass.
    """
    if in_df is None or in_df.empty:
        return in_df

    ranges = {'dbh': (0, 500), 'ht': (0, 120), 'cbh': (0, 120)}

    # Classify each column by its measurement suffix
    typed = {}
    for col in in_df.columns:
        for meas in ranges:
            if col == meas or col.endswith(f'_{meas}'):
                typed[col] = meas
                break

    num = {col: pd.to_numeric(in_df[col], errors='coerce') for col in typed}

    # Range checks
    masks = {}
    for col, meas in typed.items():
        lo, hi = ranges[meas]
        masks[f'{col}_range'] = num[col].lt(lo) | num[col].gt(hi)

    # Cross-field: cbh >= ht, paired by shared prefix
    def prefix(col, meas):
        return col[:-len(meas) - 1] if col.endswith(f'_{meas}') else ''
    ht_cols  = {prefix(c, 'ht'):  c for c, m in typed.items() if m == 'ht'}
    cbh_cols = {prefix(c, 'cbh'): c for c, m in typed.items() if m == 'cbh'}
    for pfx in ht_cols.keys() & cbh_cols.keys():
        ht, cbh = ht_cols[pfx], cbh_cols[pfx]
        masks[f'{cbh}>={ht}'] = num[cbh].ge(num[ht])   # swap .ge -> .lt for literal ht>cbh

    flags = pd.DataFrame(masks)
    invalid = flags.any(axis=1)
    if not invalid.any():
        print('All tree records passed the value checks.')
        return in_df.iloc[:0].copy()

    out = in_df.loc[invalid].copy()
    out['flags'] = flags.loc[invalid].apply(lambda r: ','.join(flags.columns[r]), axis=1)

    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, 'flagged_tree_data.csv')
    helper.export_csv(out, path)
    print(f'Warning: {len(out)} tree records flagged. Saved to: {path}')
    return out
def tree_calculations(in_df,
                      ind_tree_df,
                      out_dirs: dict, 
                      stand_summary_params: dict):
    out_dir = out_dirs['trees']
    keep_columns = []
    trees_params_df = helper.get_df(
        os.path.join(os.path.dirname(__file__), 'supporting_data', 'tree_parameters.csv')
    ).set_index('Species')

    df = trees._round_plot_data(in_df)
    df = trees._calc_plot_multipliers(df)                       # df, not in_df

    df, add_columns = trees._calc_stand_composition(df, ind_tree_df, gen_conpyro_df=True)
    keep_columns.extend(add_columns)
    df, add_columns = trees._calc_stand_attributes(df, ind_tree_df, stand_summary_params)
    keep_columns.extend(add_columns)

    os.makedirs(out_dir, exist_ok=True)
    helper.export_csv(df, os.path.join(out_dir, 'survey_0.csv'))  # out_dir, not out_dirs
    return df, helper.sort_list(keep_columns)
 
# Test routine for calculating FBP fuel types
if __name__ == '__main__':
    # Base paths from env
    _in_dir  = os.getenv('DATA_BASE_DIR', '/app/input_data')
    _out_dir = os.getenv('OUTPUT_DIR', '/app/output')   # form folders + data_check live under here
    _BEC_shp_dir = os.path.join(os.getenv('BEC_DATA_DIR', '/app/BEC_data'),
                                'VEG_COMP_LYR_R1_POLY_2025.gdb')
    os.makedirs(_out_dir, exist_ok=True)
    print(_BEC_shp_dir)

    form_select_list = ['plot', 'plants', 'trees', 'cover', 'woody']

    # 1. Validate input form dirs and create one output folder per form -> {form: path}
    out_dirs = export_set(_in_dir, _out_dir, form_select_list, dir_dict)
    print(out_dirs)
    # 2. Cross-form unique_id membership check
    print('Checking which plots/unique_ids are present across all forms...')
    plot_data_check(_in_dir, dir_dict, _out_dir)

    # 3. Plot attributes
    print('Reading plot level data and checking for outliers / missing values...')
    plots, cols = plot_attributes_read(_in_dir, out_dirs, spatial=False)

    # 4. Extract BEC type (writes plots.gpkg when write_sf=True)
    bec_info_df = extract_BEC(plots, vri_polygon=_BEC_shp_dir, write_sf=True)

    # 5. Subplot (tree) data merged onto the BEC-joined plot data
    print('Reading tree level data and checking for outliers / missing values...')
    tree_df = subplot_data(in_dir=_in_dir, dir_dict=dir_dict, dir_get='trees',
                       file_prefix='survey_0', merge_plot=True, plot_df=bec_info_df,
                       out_dirs=out_dirs)
    # 6. Individual-tree data -> Read 
    print('Reading individual tree data and calculating stand-level attributes...')
    ind_trees = tree_data_read(in_dir=_in_dir, out_dirs=out_dirs, dir_dict=dir_dict)
    # y. Individual-tree data -> Stand Level Attributes 
    out_trees = tree_calculations(in_df = tree_df, ind_tree_df = ind_trees, 
                                  out_dirs = out_dirs, 
                                  stand_summary_params= default_stand_summary_dict)
    