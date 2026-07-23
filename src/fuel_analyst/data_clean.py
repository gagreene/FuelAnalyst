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

# ── Single export path for every table written by this script ───────────────
# Driver lookup for the spatial formats write_df knows how to emit.
_SPATIAL_DRIVERS = {
    '.gpkg': 'GPKG',
    '.geojson': 'GeoJSON',
    '.shp': 'ESRI Shapefile',
}


def write_df(df, out_path: str, index: bool = False, layer: str = None,
             label: str = None, quiet: bool = False) -> bool:
    """Write a (Geo)DataFrame to disk, skipping frames with a zero-length dimension.

    Args:
        df: The frame to write. None, zero rows, or zero columns are all treated
            as "nothing to write" and no file is created.
        out_path: Full path of the file to write. Parent dirs are created.
        index: Whether to write the index (csv/parquet/excel only).
        layer: Optional layer name for .gpkg output.
        label: Friendly name used in messages; defaults to the file name.
        quiet: Suppress the "nothing to write" message. Use this for the
            data-check exports, where an empty frame is the expected, good case
            and the caller reports on the return value instead.

    Returns:
        bool: True if a file was written, False if the frame was empty/None.

    Raises:
        TypeError: A spatial format was requested for a non-spatial frame.
        ValueError: The extension has no registered writer.
    """
    name = label or os.path.basename(out_path)

    # Dimension check: never emit a zero-row or zero-column file.
    if df is None or getattr(df, 'ndim', 0) != 2 or df.shape[0] == 0 or df.shape[1] == 0:
        if not quiet:
            shape = 'None' if df is None else f'{df.shape[0]} rows x {df.shape[1]} cols'
            print(f'Warning: nothing written to {name} ({shape}).')
        return False

    parent = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(parent, exist_ok=True)

    ext = os.path.splitext(out_path)[1].lower()
    if ext in ('.csv', '.txt'):
        df.to_csv(out_path, index=index)
    elif ext in _SPATIAL_DRIVERS:
        if not hasattr(df, 'to_file'):
            raise TypeError(
                f'{name}: {ext} output requires a GeoDataFrame, got {type(df).__name__}.'
            )
        kwargs = {'driver': _SPATIAL_DRIVERS[ext]}
        if layer and ext == '.gpkg':
            kwargs['layer'] = layer
        df.to_file(out_path, **kwargs)
    elif ext == '.parquet':
        df.to_parquet(out_path, index=index)
    elif ext in ('.xlsx', '.xls'):
        df.to_excel(out_path, index=index)
    else:
        raise ValueError(f'No writer registered for extension {ext!r} ({out_path}).')

    return True


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
def plot_data_check(in_dir: str, dir_dict: dict, check_dir = str) -> pd.DataFrame:
    """Read the survey file(s) in each Survey123 form directory, generate a unique_id
    for each form's records, and compare which unique_ids are present across forms.

    Args:
        in_dir (str): The input directory containing the Survey123 form directories.
        dir_dict (dict): A dictionary mapping form names to their respective directory names.
        check_dir (str): The directory to save the comparison report to.

    Returns:
        pd.DataFrame: A DataFrame indicating, for each unique_id, which forms it was found in.
    """
    form_ids = {}
    missing_surveys = []
    for form, dirname in dir_dict.items():
        form_dir = os.path.join(in_dir, dirname)
        survey_files = sorted(
            f for f in os.listdir(form_dir)
            if 'survey' in f.lower() and f.endswith('.csv')
        )
        if not survey_files:
            missing_surveys.append(form)
            continue

        form_df = pd.concat(
            [get_unique_id_strip(helper.get_df(os.path.join(form_dir, f))) for f in survey_files],
            ignore_index=True
        )
        form_ids[form] = set(form_df['unique_id'])

    if missing_surveys:
        print(f'Warning: no survey file found for form(s): {missing_surveys}')

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
    # All error/flagged files go in one shared data_check folder under out_dir.
    # write_df skips the export when nothing is flagged, so no guard is needed here.
    mismatch_path = os.path.join(check_dir, 'unique_id_mismatches.csv')
    if write_df(mismatches, mismatch_path, quiet=True):
        print(f'Warning: {len(mismatches)} unique_id(s) missing from at least one form -> {mismatch_path}')

    return membership
# ────────────────────────────────────────────────────────────
def plot_attributes_read(in_dir: str, out_dirs: dict, check_dir,
                         spatial: bool = False) -> pd.DataFrame:
    # Resolve this form's output folder from the export_set dict
    if 'plot' not in out_dirs:
        raise KeyError(
            "No 'plot' entry in out_dirs. Include 'plot' in the form_select_list "
            "passed to export_set so its output folder gets created."
        )
    outputs = out_dirs['plot']
    plot_dir = os.path.join(in_dir, dir_dict.get('plot'))
    # List all survey CSVs in the plot directory
    plot_files = sorted(f for f in os.listdir(plot_dir)
                        if f.startswith('survey_0') and f.endswith('.csv'))

    survey_file = os.path.join(plot_dir, plot_files[0]) if plot_files else None
    if not survey_file:
        raise FileNotFoundError(
            f'No survey_0*.csv file found in the Plot Attributes directory: {plot_dir}.'
        )

    # Load plots as geodataframe and check for missing lat/long values
    plot_gdf = _load_plots(survey_file, lat='y', lon='x')
    plot_gdf = get_unique_id_strip(plot_gdf)
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
    flagged_path = os.path.join(check_dir, 'flagged_plots.csv')
    if write_df(plot_gdf.loc[flagged_mask, ['unique_id', 'flagged_attributes', 'spatial']],
                flagged_path, quiet=True):
        print(f'Warning: {int(flagged_mask.sum())} plots flagged (attributes and/or missing '
              f'spatial) -> {flagged_path}')

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
    write_df(plot_gdf, os.path.join(outputs, 'survey_0.csv'), label='plot attributes (csv)')
    if spatial:
        write_df(plot_gdf, os.path.join(outputs, 'survey_0.gpkg'), label='plot attributes (gpkg)')

    return plot_gdf, add_columns
## using the plot_dt and unique ID column, create the next layer of data, the fpb_prep_csv 
def extract_BEC(plot_gdf: 'gpd.GeoDataFrame',
                out_dir: str = None,
                vri_polygon: str = None,
                write_sf: bool = False
                ) -> pd.DataFrame:
    """Extract BEC type information for each plot and save the updated DataFrame.
    Args:
        plot_gdf (gpd.GeoDataFrame): A GeoDataFrame containing the plot data.
        out_dir (str): Directory the joined geopackage is written to when write_sf=True.
        vri_polygon (str): Path to the VRI/BEC geodatabase.
        write_sf (bool): Write plots.gpkg with the BEC attributes joined on.
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
            if out_dir is None:
                raise ValueError('out_dir is required when write_sf=True.')
            os.makedirs(out_dir, exist_ok=True)
            gpkg_out_path = os.path.join(out_dir, 'plots.gpkg')
            # create_joined_geopackage writes the file itself, so the dimension
            # check is done here rather than through write_df.
            if bec_info_df is None or bec_info_df.shape[0] == 0 or bec_info_df.shape[1] == 0:
                print(f'Warning: nothing written to plots.gpkg (no BEC records returned).')
            else:
                create_joined_geopackage(
                    plots=plot_gdf,
                    bec_info_df=bec_info_df,
                    plot_id_col='unique_id',
                    output_path=gpkg_out_path
                )
    return bec_info_df
def subplot_data(in_dir: str, form: str, check_dir: str,
                 file_prefix: str = 'survey_0',
                 plot_df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Read one subplot CSV from a Survey123 form directory, optionally merged onto plot data.

    Args:
        in_dir: Directory containing the Survey123 form directories.
        form: Which form to read — a key of the module-level dir_dict
            (e.g. 'trees', 'plants', 'cover', 'woody').
        check_dir: Where flagged/mismatch CSVs are written.
        file_prefix: Filename prefix within that directory. First match wins.
        plot_df: Parent plot data. When given, subplot rows are merged onto it;
            when None, the subplot table is returned as read.
    """
    if form not in dir_dict:
        raise KeyError(f"Unknown form {form!r}. Expected one of: {sorted(dir_dict)}")

    plot_dir = os.path.join(in_dir, dir_dict[form])

    plot_files = sorted(f for f in os.listdir(plot_dir)
                        if f.startswith(file_prefix) and f.endswith('.csv'))
    if not plot_files:
        raise FileNotFoundError(f"No '{file_prefix}*.csv' file found in: {plot_dir}")

    tree_df = _calc_plot_multipliers(get_unique_id_strip(helper.get_df(
        os.path.join(plot_dir, plot_files[0]))))

    if plot_df is None:
        return tree_df

    sfx = f'_{form}'
    out_df = pd.merge(plot_df, tree_df, on='unique_id', how='left', suffixes=('_plot', sfx))

    x_sub, y_sub = f'x{sfx}', f'y{sfx}'
    if {x_sub, y_sub, 'x_plot', 'y_plot'}.issubset(out_df.columns):
        mismatch = (out_df[x_sub] != out_df['x_plot']) | (out_df[y_sub] != out_df['y_plot'])
        mismatch_path = os.path.join(check_dir, 'coordinate_mismatches.csv')
        if write_df(out_df.loc[mismatch, ['unique_id', x_sub, 'x_plot', y_sub, 'y_plot']],
                    mismatch_path, quiet=True):
            print(f'Warning: {int(mismatch.sum())} rows have mismatched X or Y coordinates '
                  f'-> {mismatch_path}')
        out_df = out_df.drop(columns=[x_sub, y_sub])

    rename = {c: c.upper().replace('_PLOT', '') for c in ('x_plot', 'y_plot') if c in out_df.columns}
    return out_df.rename(columns=rename)
def tree_data_read(in_dir: str, out_dirs: dict, 
                   dir_dict: dict, check_dir = str):
    """Read, validate, merge, and export individual-tree and sapling data.

    Reads the first 'tree_plot*.csv' and 'sapling*.csv' from the Trees form
    directory, validates each for reporting, merges saplings into the tree table
    (required for stand-level calculations), rounds the result, exports both raw
    tables, and returns the merged frame.

    Args:
        in_dir (str): Input directory of Survey123 form directories (Trees resolved
            via dir_dict['trees']).
        out_dirs (dict): dictionary of output folders keyed by form.

    Returns:
        pd.DataFrame: Merged tree + sapling table, rounded, ready for stand-level
        calculations.

    Raises:
        FileNotFoundError: If no 'tree_plot*.csv' or 'sapling*.csv' is found.

    Notes:
        tree_data_check returns only flagged rows, so its return is discarded here —
        reassigning from it would drop all valid data. The two checks write to
        separate files because tree_data_check names its output by label.
    """
    # Create export folder locations 
    plot_dir = os.path.join(in_dir, dir_dict.get('trees'))
    out_dir = out_dirs['trees']                       # assign first
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
    tree_data_check(ind_tree_df, check_dir = check_dir, label = 'tree')
    # --- sapling data ---
    sapling_files = sorted(f for f in os.listdir(plot_dir)
                           if f.startswith('sapling') and f.endswith('.csv'))
    survey_file = os.path.join(plot_dir, sapling_files[0]) if sapling_files else None
    if not survey_file:
        raise FileNotFoundError(f'No sapling tree data found in {plot_dir}')
    sapling_df_raw = helper.get_df(survey_file)
    ## check for errors
    sapling_df = tree_data_check(sapling_df_raw, check_dir=check_dir, label='sapling')
    sapling_df = trees._calc_sapling_tree_type(sapling_df, 
                                               tree_params_df = tree_params_df)
    sapling_df = trees._calc_sapling_density(sapling_df)
    sapling_df = trees._calc_sapling_dbh(sapling_df)
    sapling_df = trees._calc_sapling_ht(sapling_df, tree_params_df)
    # --- export raw tables before any derived calculation can fail ---
    write_df(sapling_df, os.path.join(out_dir, 'sapling_1.csv'), index=True, label='sapling_1.csv')
    write_df(ind_tree_df, os.path.join(out_dir, 'tree_plot_2.csv'), index=True, label='tree_plot_2.csv')

    # --- merge saplings into trees (needed for stand calculations), then round ---
    trees_df = trees._merge_saplings_to_trees(ind_tree_df, sapling_df)
    trees_df = trees._round_tree_data(trees_df)
    return trees_df
    # # Calculate sapling attributes

    # ## check for errors
    # tree_data_check(sapling_df, check_dir=check_dir, label = 'sapling')
    # # --- merge saplings into trees (needed for stand calculations), then round ---
    # trees_df = trees._merge_saplings_to_trees(ind_tree_df, sapling_df)
    # trees_df = trees._round_tree_data(trees_df)
    # # --- export ---
    # write_df(sapling_df, os.path.join(out_dir, 'sapling_1.csv'), index=True, label='sapling_1.csv')
    # write_df(ind_tree_df, os.path.join(out_dir, 'tree_plot_2.csv'), index=True, label='tree_plot_2.csv')
    # return trees_df
def tree_data_check(in_df: pd.DataFrame, check_dir: str, label: str = 'tree') -> pd.DataFrame:
    """Flag tree/sapling records with out-of-range values or crown base height >= height.

    Columns are matched by measurement suffix (_dbh, _ht, _cbh), so any prefix
    works (tree_dbh, sapling_live_dbh, sapling_dead_cbh, ...). The cbh >= ht
    check pairs columns sharing a prefix (sapling_live_cbh vs sapling_live_ht).

    Writes only the flagged records to check_dir/flagged_{label}_data.csv; nothing
    is written when every record passes. Returns the flagged records ('flags'
    lists every failed check), or an empty frame if all pass.
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

    flags = pd.DataFrame(masks, index=in_df.index)
    invalid = flags.any(axis=1)

    if not invalid.any():
        return in_df.iloc[:0].copy()

    out = in_df.loc[invalid].copy()
    out['flags'] = flags.loc[invalid].apply(lambda r: ','.join(flags.columns[r]), axis=1)

    path = os.path.join(check_dir, f'flagged_{label}_data.csv')
    if write_df(out, path, quiet=True):
        print(f'Warning: {invalid.sum()} of {len(in_df)} {label} records flagged -> {path}')

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
    df = trees._calc_plot_multipliers(df)           

    df, add_columns = trees._calc_stand_composition(df, ind_tree_df, gen_conpyro_df=True)
    keep_columns.extend(add_columns)
    df, add_columns = trees._calc_stand_attributes(df, ind_tree_df, stand_summary_params)
    keep_columns.extend(add_columns)

    write_df(df, os.path.join(out_dir, 'survey_0.csv'), index=True, label='stand attributes')
    return df, helper.sort_list(keep_columns)
 
# Test routine for calculating FBP fuel types
if __name__ == '__main__':
    # Base paths from env
    _in_dir  = os.getenv('DATA_BASE_DIR', '/app/input_data')
    _out_dir = os.getenv('OUTPUT_DIR', '/app/output')   # form folders + data_check live under here
    _check_dir = _out_dir + '/data_check'
    os.makedirs(_check_dir, exist_ok=True)
    _BEC_shp_dir = os.path.join(os.getenv('BEC_DATA_DIR', '/app/BEC_data'),
                                'VEG_COMP_LYR_R1_POLY_2025.gdb')
    os.makedirs(_out_dir, exist_ok=True)
    form_select_list = ['plot', 'plants', 'trees', 'cover', 'woody']
    # 1. Validate input form dirs and create one output folder per form -> {form: path}
    out_dirs = export_set(_in_dir, _out_dir, form_select_list, dir_dict)
    # 2. Cross-form unique_id membership check
    plot_data_check(_in_dir, dir_dict, _check_dir)
    # 3. Plot attributes
    plots, cols = plot_attributes_read(_in_dir, out_dirs, _check_dir, spatial=False)
    # 4. Extract BEC type (writes plots.gpkg when write_sf=True)
    bec_info_df = extract_BEC(plots, out_dir=_out_dir, vri_polygon=_BEC_shp_dir, write_sf=True)
    # 5. Subplot (tree) data merged onto the BEC-joined plot data
    tree_df = subplot_data(_in_dir, 'trees', _check_dir, plot_df=bec_info_df)
    
    
    
    # 6. Individual-tree data -> Read 
    print(f'step5 tree_df: {getattr(tree_df, "shape", None)}')
    print(f'bec_info_df:   {getattr(bec_info_df, "shape", None)}')
    print(f'trees out_dir: {out_dirs["trees"]} exists={os.path.isdir(out_dirs["trees"])}')
    ind_trees = tree_data_read(in_dir=_in_dir, out_dirs=out_dirs, dir_dict=dir_dict, check_dir=_check_dir)
    # 7. Individual-tree data -> Stand Level Attributes 
    out_trees = tree_calculations(in_df = tree_df, ind_tree_df = ind_trees, 
                                  out_dirs = out_dirs, 
                                  stand_summary_params= default_stand_summary_dict)

    print(f'Processing complete: {len(out_trees[0])} plots written to {_out_dir} '
          f'(data checks in {_check_dir}).')