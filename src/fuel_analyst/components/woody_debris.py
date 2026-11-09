# -*- coding: utf-8 -*-
"""
Created on Tue May 29, 8:30:00 2025

@author: Gregory A. Greene
"""
__author__ = ['Gregory A. Greene']

import logging
import os
import warnings
import pandas as pd
import numpy as np
import fnmatch
from scipy.stats import linregress
import operator

from . import helper, table_reader

logger = logging.getLogger(__name__)

bulk_density_map = [
    # (output bd column, tree params column, duff/litter depth columm, output biomass column)
    ('stand_duff_bd_kgpm3', 'Duff_BD', 'stand_duff_depth_cm', 'ffl_duff_kgpm2'),
    ('stand_litter_bd_kgpm3', 'Litter_BD', 'stand_litter_depth_cm', 'ffl_litter_kgpm2'),
]

woody_tally_map = [
    # (output tally column,
    # transect 1 tally 0-2m column, transect 1 tally 28-30m column,
    # transect 2 tally 0-2m column, transect 2 tally 28-30m column)
    ('woody_tally_count',
     't1_woody_tally_0to2', 't1_woody_tally_28to30',
     't2_woody_tally_0to2', 't2_woody_tally_28to30')
]

# Specific gravity columns are breakpoints along one size trend. A piece or tally class takes the first column whose
# breakpoint is at or above its diameter, so each column covers diameters greater than the previous breakpoint and up to
# (and including) its own, and the last column covers everything thicker than the final breakpoint.
specific_gravity_map = [
    # (plot-level output column, tree parameters column, lower diameter limit (cm, excluded),
    # upper diameter limit (cm, included))
    ('woody_sg_0_5cm', 'SG_0.5', 0, 0.5),
    ('woody_sg_0_635cm', 'SG_0.635', 0.5, 0.635),    # 1hr woody fuels (US protocol)
    ('woody_sg_1cm', 'SG_1', 0.635, 1),
    ('woody_sg_2cm', 'SG_2', 1, 2),
    ('woody_sg_2_54cm', 'SG_2.54', 2, 2.54),         # 10hr woody fuels (US protocol)
    ('woody_sg_3cm', 'SG_3', 2.54, 3),
    ('woody_sg_4cm', 'SG_4', 3, 4),
    ('woody_sg_5cm', 'SG_5', 4, 5),
    ('woody_sg_6cm', 'SG_6', 5, 6),
    ('woody_sg_7cm', 'SG_7', 6, 7),
    ('woody_sg_7_62cm', 'SG_7.62', 7, 7.62),         # 100hr woody fuels (US protocol)
    ('woody_sg_gt7_62cm', 'SG_7.62+', 7.62, np.inf),  # 1000hr woody fuels (US protocol)
]


def _add_spp_comp_type(spp_comp_df: pd.DataFrame) -> pd.DataFrame:
    """
    Add a 'spp_comp_type' column to the species composition DataFrame, defaulting to 'manual_entry'.

    :param spp_comp_df: DataFrame containing species composition data.
    :return: Updated spp_comp_df with 'spp_comp_type' column.
    """
    # Initialize spp_comp_type column with default value
    spp_comp_df['spp_comp_type'] = 'manual_entry'

    return spp_comp_df


def _assign_spp_comp_id_col(df: pd.DataFrame, spp_comp_df: pd.DataFrame) -> pd.DataFrame:
    """
    Assigns the `unique_id` from `df` to `spp_comp_df` where `ParentGlobalID` in `spp_comp_df`
    matches `GlobalID` in `df`.

    :param df: DataFrame containing plot-level data with `GlobalID` and `unique_id` columns.
    :param spp_comp_df: DataFrame containing species composition data with `ParentGlobalID`.
    :return: Updated `spp_comp_df` with a new `unique_id` column mapped from `df`.
    """
    # Map unique_id from df to spp_comp_df based on matching ParentGlobalID and GlobalID
    spp_comp_df['unique_id'] = spp_comp_df['ParentGlobalID'].map(
        df.set_index('GlobalID')['unique_id'].to_dict()
    )

    return spp_comp_df


def _calc_plot_duff_litter_biomass(
        plot_df: pd.DataFrame,
        df: pd.DataFrame,
        spp_comp_df: pd.DataFrame
) -> tuple[pd.DataFrame, list]:
    """
    Calculate plot-level duff and litter biomass (kg/m^2) for each plot, using species composition
    and bulk density data. Biomass is scaled by the proportion of flammable ground cover.

    :param plot_df: DataFrame containing plot-level attributes, including 'pc_flammable' if the
        Plants and Regeneration form was processed.
    :param df: DataFrame containing plot-level data with unique IDs and spp_comp_type.
    :param spp_comp_df: DataFrame containing species composition and calculated bulk densities.
    :return: Updated df with duff and litter biomass columns.
    """
    print('\tProcessing plot-level duff and litter biomass')

    # Loop through each species composition type
    for spp_comp_type in ['tree_data', 'transect_data', 'manual_entry']:
        plot_mask = df['spp_comp_type'] == spp_comp_type

        # Set comment for biomass calculation source
        if spp_comp_type == 'tree_data':
            sg_comment = 'Duff/Litter biomass values derived using live and dead tree species composition data.'
        elif spp_comp_type == 'transect_data':
            sg_comment = ('Duff/Litter biomass values derived using measured woody debris species composition '
                          'along transect(s).')
        else:
            sg_comment = 'Duff/Litter biomass values derived using manual species composition entry.'
        df.loc[plot_mask, 'woody_sg_comment'] = sg_comment

        # Only process if there are rows for this type
        if not df[plot_mask].empty:
            for bd_col, _, depth_col, out_col in bulk_density_map:
                spp_mask = spp_comp_df['spp_comp_type'] == spp_comp_type
                # Map summed bulk density to plot, then multiply by depth
                biomass = df['unique_id'].map(
                    spp_comp_df[spp_mask].groupby('unique_id')[bd_col].sum()
                )
                df.loc[plot_mask, out_col] = biomass * df.loc[plot_mask, depth_col] / 100  # Convert depth from cm to m

    # Initialize list of columns to keep
    keep_columns = []

    # Scale biomass by percent flammable ground cover. Plots missing a pc_flammable value
    # (e.g., the Plants and Regeneration form was not processed for any plot) default to fully
    # flammable (100) rather than dropping the computed duff/litter values.
    if 'pc_flammable' in plot_df.columns:
        flammable_map = plot_df.set_index('unique_id')['pc_flammable'].to_dict()
    else:
        flammable_map = {}

    for _, _, _, out_col in bulk_density_map:
        if out_col in df.columns:
            flammable_pct = df['unique_id'].map(flammable_map).fillna(100)
            df[out_col] = df[out_col] * flammable_pct / 100
            keep_columns.append(out_col)

    return df, keep_columns


def _calc_plot_duff_litter_depths(df: pd.DataFrame) -> tuple[pd.DataFrame, list]:
    """
    Calculate average stand-level duff and litter depths (in centimeters) for each plot
    by averaging all available *_duff_75, *_duff_225, *_litter_75, *_litter_225 columns.

    :param df: DataFrame containing plot-level duff and litter measurements.
    :return: DataFrame with new columns for stand-level duff and litter depths in meters.
    """
    # Find all columns for duff and litter measurements
    duff_cols = [col for col in df.columns if '_duff_75' in col or '_duff_225' in col]
    litter_cols = [col for col in df.columns if '_litter_75' in col or '_litter_225' in col]

    # Calculate average depths and convert to meters
    df['stand_duff_depth_cm'] = df[duff_cols].apply(pd.to_numeric, errors='coerce').mean(axis=1)
    df['stand_litter_depth_cm'] = df[litter_cols].apply(pd.to_numeric, errors='coerce').mean(axis=1)

    return df, ['stand_duff_depth_cm', 'stand_litter_depth_cm']


def _calc_plot_specific_gravity(
        df: pd.DataFrame,
        spp_comp_df: pd.DataFrame
) -> tuple[pd.DataFrame, list]:
    """
    Calculate plot-level specific gravity values for woody debris fuel size classes.

    For each plot, this function aggregates specific gravity values from the species composition
    DataFrame (`spp_comp_df`) by `unique_id` and species composition type, and assigns the
    summed values to the corresponding rows in the plot DataFrame (`df`). It also adds a comment
    describing the source of the specific gravity values for each plot.

    :param df: DataFrame containing plot-level data, including `unique_id` and `spp_comp_type`.
    :param spp_comp_df: DataFrame containing species composition data and specific gravity columns.
    :return: Tuple of the updated plot DataFrame and a sorted list of specific gravity columns added.
    """
    print(f'\tProcessing plot-level specific gravity')

    # Initialize list of columns to keep
    keep_columns = []

    # Loop through each species composition type
    for spp_comp_type in ['tree_data', 'transect_data', 'manual_entry']:
        # Filter the DataFrame for the current species composition type
        plot_comp_type_mask = df['spp_comp_type'] == spp_comp_type

        # Add specific gravity source comment
        if spp_comp_type == 'tree_data':
            sg_comment = 'Specific gravity values derived using live and dead tree species composition data.'
        elif spp_comp_type == 'transect_data':
            sg_comment = ('Specific gravity values derived using measured woody debris species composition '
                          'along transect(s).')
        else:
            sg_comment = 'Specific gravity values derived using manual species composition entry.'
        df.loc[plot_comp_type_mask, 'woody_sg_comment'] = sg_comment

        # Only process if there are rows for this type
        if not df[plot_comp_type_mask].empty:
            # For each specific gravity output column, aggregate and assign values
            for out_col, param_col, _, _ in specific_gravity_map:
                spp_comp_mask = spp_comp_df['spp_comp_type'] == spp_comp_type
                # Map summed specific gravity from spp_comp_df to df by unique_id
                df.loc[plot_comp_type_mask, out_col] = df['unique_id'].map(
                    spp_comp_df[spp_comp_mask].groupby('unique_id')[out_col].sum()
                )
                keep_columns.append(out_col)

    # Remove duplicate columns in keep_columns
    keep_columns = list(set(keep_columns))

    return df, helper.sort_list(keep_columns)


def _calc_plot_t2_azimuth(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate the azimuth for transect 2 by adding 90 degrees to transect 1's azimuth.
    If the result exceeds 360, subtract 270 to keep within compass bounds.

    :param df: DataFrame with a 't1_azimuth' column.
    :return: DataFrame with a new 't2_azimuth' column.
    """
    # Add 90 degrees to t1_azimuth; if result > 360, wrap around
    df['t2_azimuth'] = (df['t1_azimuth'] + 90) % 360

    return df


def _calc_plot_tsct_slope_correction(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate the exact horizontal-projection correction for each transect.

    For slope percent s, the factor is sqrt(1 + (s / 100)^2). Degrees are
    converted to percent first; the radians column remains diagnostic.

    :param df: DataFrame containing transect length and slope data.
    :return: Updated DataFrame with slope percent, radians, and correction factors.
    """

    # Calculate slope correction for each transect
    for tsct in [1, 2]:
        # Calculate slope percent
        df[f't{tsct}_slope_pct'] = np.where(df[f't{tsct}_slope_units'] == 'degrees',
                                            100 * np.tan(df[f't{tsct}_slope'] * np.pi / 180),
                                            df[f't{tsct}_slope'].astype(float))

        # Calculate slope radians
        df[f't{tsct}_slope_rad'] = np.arctan(df[f't{tsct}_slope_pct'].astype(float) / 100)

        # Calculate slope correction
        df[f't{tsct}_slope_cor'] = np.sqrt(1 + np.power(df[f't{tsct}_slope_pct'] / 100, 2))

    return df


def _calc_plot_tsct_total_slope_correction(df: pd.DataFrame, woody_debris_params: dict) -> pd.DataFrame:
    """
    Calculate the total slope-corrected transect lengths for each plot and diameter class.

    For each transect length defined in the protocol parameters, this function computes the slope-corrected
    length for both transects (t1 and t2) and sums them to get the total corrected transect length per plot.
    It also calculates an overall slope correction factor for each plot.

    :param df: DataFrame containing plot-level data, including slope correction factors for each transect.
    :param woody_debris_params: Dictionary containing protocol transect parameters, including transect lengths.
    :return: Updated DataFrame with new columns for corrected transect lengths and total slope correction.
    """
    # Get the list of transect lengths (in meters) for each diameter class
    lengths = woody_debris_params['protocol_transect_params']['transect_lengths']

    for lngth in lengths:
        for tsct in [1, 2]:
            # Calculate the corrected transect length for each transect and diameter class
            df[f't{tsct}_length_{lngth}m_cor'] = lngth / df[f't{tsct}_slope_cor']

        # Sum the corrected transect lengths for both transects to get the total corrected length
        df[f'tsct_length_{lngth}m_cor'] = (
            df[f't1_length_{lngth}m_cor'].replace(np.nan, 0) +
            df[f't2_length_{lngth}m_cor'].replace(np.nan, 0)
        )

    # Calculate the total (overall) slope correction factor for the plot
    # (uses the first transect length as representative)
    df[f'tsct_slope_cor'] = (
        (df['num_transects'] * lengths[0]) / df[f'tsct_length_{lengths[0]}m_cor']
    )

    return df


def _calc_plot_woody_debris(
        df: pd.DataFrame,
        woody_merged_df: pd.DataFrame,
        woody_debris_params: dict
) -> tuple[pd.DataFrame, list]:
    """
    Calculate plot-level woody debris biomass (kg/m^2) for each requested output class.

    For each woody debris class defined in the protocol parameters, this function:
    - Applies user-defined filters to the merged woody debris DataFrame to select pieces in each output class.
    - Sums the measured woody debris biomass for each plot and output class.
    - Incorporates tallied woody fuel biomass into every output class that holds the tallied size class
      (for a request filtered on a field the tally lacks, only into the first request).
    - Adds the resulting columns to a list of columns to keep.

    :param df: DataFrame containing plot-level data (with GlobalID).
    :param woody_merged_df: DataFrame with merged woody debris transect data, including diameter and biomass.
    :param woody_debris_params: Dictionary with woody debris class definitions and output requests.
    :return: Tuple of the updated plot DataFrame and a sorted list of new output columns.
    """
    print('\tProcessing final woody debris calculations')

    # Initialize list of columns to keep
    keep_columns = []
    output_columns = {}

    # Loop through each woody debris class defined in parameters
    for woody_class, woody_class_dict in woody_debris_params['woody_debris_classes'].items():
        print(f'\t\tProcessing {woody_class.upper()} class')

        if woody_class_dict['process_classes']:
            # Get the class extension, diameter cutoffs, and output requests
            woody_class_ext = woody_class_dict['class_extension']
            diameter_cutoffs = woody_class_dict['diameter_cutoffs']
            output_requests = woody_class_dict['output_request']

            # Loop through each output request for this woody debris class
            for i, (req_ext, req_filter, req_cutoffs) in enumerate(output_requests):
                prior_out_dc = req_cutoffs[0]
                for out_dc in req_cutoffs[1:]:
                    out_dc_str = str(out_dc).replace('.', '_')
                    if out_dc_str == 'inf':
                        prior_out_dc_str = str(prior_out_dc).replace('.', '_')
                        out_dc_str = f'gt{prior_out_dc_str}'

                    # Create a mask for the merged woody DataFrame (default to all True)
                    mask = np.ones(len(woody_merged_df), dtype=bool)

                    # Apply user-defined filters to the merged woody DataFrame
                    for col, cond in req_filter.items():
                        ops = {
                            '<=': operator.le,
                            '>=': operator.ge,
                            '<': operator.lt,
                            '>': operator.gt,
                            '==': operator.eq,
                            '!=': operator.ne,
                        }
                        for op_str, op_func in ops.items():
                            if cond.startswith(op_str):
                                val = float(cond[len(op_str):])
                                mask &= op_func(woody_merged_df[col], val)
                                break
                        else:
                            raise ValueError(f'Unsupported condition: {cond}')

                    output_col = f'woody_kgpm2_{woody_class_ext}_{req_ext}_{out_dc_str}'

                    # Sum measured woody debris biomass for each plot and output class
                    output_columns[output_col] = df.GlobalID.map(
                        woody_merged_df[
                            (woody_merged_df['woody_diam_cm'] > prior_out_dc) &
                            (woody_merged_df['woody_diam_cm'] <= out_dc) &
                            mask
                        ].groupby('ParentGlobalID')['woody_mass_kgpm2'].sum()
                    )

                    # Incorporate tallied woody fuels into every output class that holds the tallied size class,
                    # whatever the position of its request. A request filtered on a field the tally lacks (such as
                    # decay class) only gets the tally when it is the first request, so FOFEM's sound and rotten
                    # classes do not both count the same tally
                    if i == 0 or not req_filter:
                        dc = diameter_cutoffs[0]
                        dc_str = str(dc).replace('.', '_')
                        if dc == out_dc:
                            # If the tallied diameter class matches the output diameter class,
                            # copy the tallied woody value
                            output_columns[output_col] = df[f'woody_kgpm2_{woody_class_ext}_{dc_str}']
                        elif prior_out_dc < dc < out_dc:
                            # Add the tallied fuel mass to the class if the tallied diameter class is between
                            # the prior and current output diameter classes. A plot with only one of the measured
                            # and tallied masses keeps it (a missing part is no pieces, not a missing total)
                            output_columns[output_col] = output_columns[output_col].add(
                                df[f'woody_kgpm2_{woody_class_ext}_{dc_str}'], fill_value=0
                            )
                        else:
                            pass

                    # Add the output column to the keep_columns list
                    keep_columns.append(f'woody_kgpm2_{woody_class_ext}_{req_ext}_{out_dc_str}')

                    # Assign the previous diameter class to the current one
                    prior_out_dc = out_dc

    df = helper.attach_columns(df, output_columns)

    return df, helper.sort_list(keep_columns)


def _calc_spp_comp_duff_litter_bulk_density(
        spp_comp_df: pd.DataFrame,
        tree_params: pd.DataFrame
) -> pd.DataFrame:
    """
    Calculate duff and litter bulk density for each species in the species composition DataFrame.

    For each output column defined in `bulk_density_map`, this function assigns a bulk density value
    to each species based on the corresponding parameter in `tree_params`, weighted by the species
    composition percent. If a species is not found in `tree_params`, the value for 'UNK' is used.

    :param spp_comp_df: DataFrame containing species composition data.
    :param tree_params: DataFrame containing bulk density parameters for each species.
    :return: Updated spp_comp_df with calculated bulk density columns.
    """
    print('\tCalculating duff and litter bulk density for species composition')

    for out_col, param_col, _, _ in bulk_density_map:
        # Initialize bulk density column with NaN
        spp_comp_df[out_col] = np.nan

        # Assign bulk density for each species in spp_comp_df
        for spp in spp_comp_df['spp_comp_code'].unique():
            # Mask for current species
            spp_mask = spp_comp_df['spp_comp_code'] == spp
            # Get bulk density value from tree_params, fallback to 'UNK' if not found
            spp_comp_df.loc[spp_mask, out_col] = (
                tree_params.loc[spp, param_col]
                if spp in tree_params.index
                else tree_params.loc['UNK', param_col]
            ) * spp_comp_df['spp_comp_percent'] / 100  # Weight by species percent

    return spp_comp_df


def _calc_spp_comp_specific_gravity(
        spp_comp_df: pd.DataFrame,
        tree_params: pd.DataFrame
) -> pd.DataFrame:
    """
    Calculate specific gravity for each species in the spp_comp_df DataFrame.

    :param spp_comp_df: DataFrame containing species composition data.
    :param tree_params: DataFrame containing specific gravity parameters for each species.
    :return: DataFrame with specific gravity columns added for each species.
    """
    print('\tCalculating specific gravity for species composition')
    # Assign specific gravity values based on species
    for out_col, param_col, _, _ in specific_gravity_map:
        # Initialize specific gravity columns based on bulk density dictionary
        spp_comp_df[out_col] = np.nan
        # Map specific gravity values from tree_params to spp_comp_df based on species
        spp_comp_df[out_col] = (
                spp_comp_df['spp_comp_code'].map(
                    tree_params[param_col].to_dict()
                ).fillna(tree_params.loc['UNK', param_col]) * (spp_comp_df['spp_comp_percent'] / 100)
        )

        # Convert specific gravity to float
        spp_comp_df[out_col] = pd.to_numeric(spp_comp_df[out_col], errors='coerce')

    return spp_comp_df


def _calc_tallied_woody_biomass(
        df: pd.DataFrame,
        woody_merged_df: pd.DataFrame,
        woody_debris_params: dict
) -> tuple[pd.DataFrame, list]:
    """
    Calculate plot-level tallied woody debris biomass (kg/m^2) for each woody debris class.

    This function processes tallied woody fuel data for each plot and woody debris class,
    calculates counts, theoretical and actual QMD (quadratic mean diameter), and computes
    biomass using the Van Wagner approach and measured values if requested.
    Volume already uses slope-corrected transect length. All biomass paths convert
    that volume with specific gravity / 10, without a second slope correction.

    :param df: DataFrame containing plot-level data.
    :param woody_merged_df: DataFrame containing merged woody debris transect data.
    :param woody_debris_params: Dictionary containing parameters for woody debris processing.
    :return: Tuple of updated DataFrame and list of columns to keep.
    """
    print(f'\tProcessing tallied woody fuels')

    # Initialize list of columns to keep
    keep_columns = []

    # Check if QMD comparison between measured and tallied is enabled
    measure_tally_qmd_compare = woody_debris_params['measure_vs_tally_qmd_comparison']

    # Loop through each woody debris class defined in parameters
    for woody_class, woody_class_dict in woody_debris_params['woody_debris_classes'].items():
        print(f'\t\tProcessing {woody_class.upper()} class')

        if woody_class_dict['process_classes']:
            # Get the class extension, diameter cutoffs, and transect lengths
            woody_class_ext = woody_class_dict['class_extension']
            diameter_cutoffs = woody_class_dict['diameter_cutoffs']
            transect_lengths = woody_class_dict['transect_lengths']

            # Calculate total and max transect lengths for each plot
            length_columns = {}
            for lngth in np.unique(transect_lengths):
                length_columns[f'tsct_length_total_{woody_class_ext}_{lngth}'] = (
                    df['num_transects'] * lngth
                )
            length_columns[f'tsct_length_max_{woody_class_ext}'] = (
                df['num_transects'] * max(transect_lengths)
            )

            # Calculate corrected slope lengths for each transect and sum for each plot
            for lngth in np.unique(transect_lengths):
                for tsct in [1, 2]:
                    length_columns[f't{tsct}_length_cor_{woody_class_ext}_{lngth}'] = (
                        lngth / df[f't{tsct}_slope_cor']
                    )
                length_columns[f'tsct_length_cor_{woody_class_ext}_{lngth}'] = (
                    length_columns[f't1_length_cor_{woody_class_ext}_{lngth}'].replace(np.nan, 0) +
                    length_columns[f't2_length_cor_{woody_class_ext}_{lngth}'].replace(np.nan, 0)
                )
            df = helper.attach_columns(df, length_columns)

            # Get counts of woody fuel tallies for each diameter class
            count_columns = {}
            prior_dc = 0
            for i, dc in enumerate(diameter_cutoffs):
                dc_str = str(dc).replace('.', '_')
                count_col = f'woody_count_{woody_class_ext}_{dc_str}'
                # Count the number of measured woody fuels within each diameter class
                count_columns[count_col] = df.GlobalID.map(
                    woody_merged_df[
                        (woody_merged_df['woody_diam_cm'] > prior_dc) &
                        (woody_merged_df['woody_diam_cm'] <= dc)
                    ].groupby('ParentGlobalID')['woody_diam_cm'].count()
                )
                # For the first diameter class, add the tallied woody fuel count to the measured woody fuel count
                if i == 0:
                    # The measured woody fuel count should be 0 for Canadian and modified fuel classes,
                    # assuming the tallied woody fuel count encompasses the upper limit of the first diameter class.
                    count_columns[count_col] = (
                        count_columns[count_col].replace(np.nan, 0) +
                        df['woody_tally_count'].replace(np.nan, 0)
                    )
                # Assign prior diameter cutoff for next iteration
                prior_dc = dc
            del prior_dc
            df = helper.attach_columns(df, count_columns)

            # Calculate theoretical QMD of woody fuel tallies using Van Wagner approach
            df = helper.attach_columns(
                df,
                _get_van_wagner_qmd(
                    df[[col for col in ['unique_id'] if col in df] +
                       [f'tsct_length_max_{woody_class_ext}'] +
                       [f'tsct_length_total_{woody_class_ext}_{lngth}'
                        for lngth in sorted(np.unique(transect_lengths))] +
                       [f'woody_count_{woody_class_ext}_{str(dc).replace(".", "_")}'
                        for dc in sorted(diameter_cutoffs)]],
                    woody_class_ext,
                    diameter_cutoffs,
                    transect_lengths
                ).set_axis(
                    [f'woody_qmd_vanwagner_{woody_class_ext}_{str(dc).replace(".", "_")}'
                     for dc in sorted(diameter_cutoffs)],
                    axis=1)
            )

            # Calculate actual QMD of woody fuel tallies (if comparing measure vs tally)
            if measure_tally_qmd_compare and (woody_class_ext != 'fofem'):
                comparison_columns = {}
                prior_dc = diameter_cutoffs[0]
                for dc in diameter_cutoffs[1:]:
                    dc_str = str(dc).replace('.', '_')
                    diam_squared_col = f'compare_woody_diamSquared_sum_{woody_class_ext}_{dc_str}'
                    count_col = f'woody_count_{woody_class_ext}_{dc_str}'
                    # Sum of squared diameters for each class
                    comparison_columns[diam_squared_col] = df.GlobalID.map(
                        woody_merged_df[
                            (woody_merged_df['woody_diam_cm'] > prior_dc) &
                            (woody_merged_df['woody_diam_cm'] <= dc)
                        ].groupby('ParentGlobalID')['woody_diamSquared'].sum()
                    )
                    # Calculate QMD for each class
                    comparison_columns[f'compare_woody_qmd_calculated_{woody_class_ext}_{dc_str}'] = np.where(
                        df[count_col] > 0,
                        np.sqrt(comparison_columns[diam_squared_col] / df[count_col]),
                        np.nan
                    )
                    # Assign prior diameter cutoff for next iteration
                    prior_dc = dc
                del prior_dc
                df = helper.attach_columns(df, comparison_columns)

            # Calculate tallied woody fuel biomass for each diameter class
            biomass_columns = {}
            for i, dc in enumerate(diameter_cutoffs):
                dc_str = str(dc).replace('.', '_')
                sg_col = _get_sg_output_column(dc)

                # Convert to volumes and biomass
                if i == 0:
                    volume_col = f'woody_volume_{woody_class_ext}_{dc_str}'
                    # Calculate volume using Van Wagner QMD for smallest size class
                    biomass_columns[volume_col] = (
                        10000 * df[f'woody_count_{woody_class_ext}_{dc_str}'] *
                        ((np.pi**2 / 8) / df[f'tsct_length_cor_{woody_class_ext}_{transect_lengths[i]}']) *
                        np.power(df[f'woody_qmd_vanwagner_{woody_class_ext}_{dc_str}'] / 100, 2)
                    )
                    # Calculate biomass
                    biomass_columns[f'woody_kgpm2_{woody_class_ext}_{dc_str}'] = (
                        df[sg_col] *
                        biomass_columns[volume_col] /
                        10
                    )
                    # Add to keep columns
                    keep_columns.append(f'woody_kgpm2_{woody_class_ext}_{dc_str}')

                elif measure_tally_qmd_compare and (woody_class_ext != 'fofem'):
                    van_wagner_volume_col = f'compare_woody_volume_vanwagner_{woody_class_ext}_{dc_str}'
                    calculated_volume_col = f'compare_woody_volume_calculated_{woody_class_ext}_{dc_str}'
                    # Calculate volumes and biomass using Van Wagner QMD
                    biomass_columns[van_wagner_volume_col] = (
                        10000 * df[f'woody_count_{woody_class_ext}_{dc_str}'] *
                        ((np.pi**2 / 8) / df[f'tsct_length_cor_{woody_class_ext}_{transect_lengths[i]}']) *
                        np.power(df[f'woody_qmd_vanwagner_{woody_class_ext}_{dc_str}'] / 100, 2)
                    )
                    biomass_columns[f'compare_woody_kgpm2_vanwagner_{woody_class_ext}_{dc_str}'] = (
                        df[sg_col] *
                        biomass_columns[van_wagner_volume_col] /
                        10
                    )
                    # Calculate volumes and biomass using calculated QMD
                    biomass_columns[calculated_volume_col] = (
                        10000 * df[f'woody_count_{woody_class_ext}_{dc_str}'] *
                        ((np.pi**2 / 8) / df[f'tsct_length_cor_{woody_class_ext}_{transect_lengths[i]}']) *
                        np.power(df[f'compare_woody_qmd_calculated_{woody_class_ext}_{dc_str}'] / 100, 2)
                    )
                    biomass_columns[f'compare_woody_kgpm2_calculated_{woody_class_ext}_{dc_str}'] = (
                        df[sg_col] *
                        biomass_columns[calculated_volume_col] /
                        10
                    )
                else:
                    break
            df = helper.attach_columns(df, biomass_columns)

    # Reconcile comparison columns for output; also cleans up any stale
    # comparison output left over from a prior run if comparison is
    # disabled this run.
    df = _prefix_compare_columns(df, measure_tally_qmd_compare)
    keep_columns.extend([col for col in df if col.startswith(_COMPARE_COLUMN_PREFIXES)])

    return df, keep_columns


def _calc_tallied_woody_counts(df: pd.DataFrame) -> pd.DataFrame:
    """
    Sum woody debris tallies from transects 1 and 2.

    :param df: DataFrame containing tallies from both transects.
    :return: Updated DataFrame with summed tallies.
    """

    for out_col, t1_meas1_col, t1_meas2_col, t2_meas1_col, t2_meas2_col in woody_tally_map:
        # Calculate total tallies across both transects
        df[out_col] = df[t1_meas1_col] + df[t1_meas2_col] + df[t2_meas1_col] + df[t2_meas2_col]

    return df


def _calc_woody_corrected_tsct_lengths(
        df: pd.DataFrame,
        woody_merged_df: pd.DataFrame,
        woody_debris_params: dict
) -> pd.DataFrame:
    """
    Assigns corrected transect lengths to woody debris pieces based on their diameter class.

    Woody debris pieces are binned by diameter (in cm) into predefined classes,
    and each class is assigned a corresponding transect length (in meters).

    :param df: DataFrame containing plot-level data (not used in this function, but kept for interface consistency).
    :param woody_merged_df: DataFrame containing woody debris data with a 'woody_diam_cm' column.
    :param woody_debris_params: Dictionary containing parameters for woody debris processing.
    :return: DataFrame with a new 'tsct_lengths' column indicating transect length for each piece.
    """
    # Define bin edges for woody diameter classes (in cm)
    bins = [0] + woody_debris_params['protocol_transect_params']['size_classes']

    # Define corresponding transect lengths (in meters) for each bin
    lengths = woody_debris_params['protocol_transect_params']['transect_lengths']

    # Assign number of transects from df to woody_merged_df for each plot
    woody_merged_df['num_transects'] = df.set_index('GlobalID')['num_transects'].reindex(
        woody_merged_df['ParentGlobalID']
    ).values

    # Assign total transect length to each woody debris piece based on its diameter class
    woody_merged_df['tsct_length'] = pd.cut(
        woody_merged_df['woody_diam_cm'],
        bins=bins,
        labels=lengths,
        right=True
    ).astype(float) * woody_merged_df['num_transects']

    # Assign total slope correction from df to woody_merged_df for each plot
    woody_merged_df['tsct_slope_cor'] = df.set_index('GlobalID')['tsct_slope_cor'].reindex(
        woody_merged_df['ParentGlobalID']
    ).values

    # Calculate the corrected transect lengths based on the slope correction value in df
    woody_merged_df['tsct_length_cor'] = woody_merged_df['tsct_length'] / woody_merged_df['tsct_slope_cor']

    return woody_merged_df


def _calc_woody_diam_cm(woody_merged_df: pd.DataFrame) -> pd.DataFrame:
    """
    Convert woody fuel diameter from mm to cm and round to 2 decimal places.

    :param woody_merged_df: DataFrame containing woody fuel data.
    :return: DataFrame with a new column 'woody_diam_cm' containing diameters in cm.
    """
    # Convert diameter from mm to cm and round to 3 decimal places
    woody_merged_df['woody_diam_cm'] = round(pd.to_numeric(woody_merged_df['woody_diam']) / 10, 3)
    # Calculate squared diameter in cm^2
    woody_merged_df['woody_diamSquared'] = woody_merged_df['woody_diam_cm'] ** 2

    return woody_merged_df


def _calc_woody_species(woody_merged_df: pd.DataFrame) -> pd.DataFrame:
    """
    Assign adjusted species codes for woody debris pieces based on decay class.

    If the decay class (_woody_decay) is greater than 3, assigns 'DECAYED' to the
    'woody_species_adj' column; otherwise, retains the original species code.

    :param woody_merged_df: DataFrame containing woody debris data with
        '_woody_decay' and 'woody_species' columns.
    :return: DataFrame with an added or updated 'woody_species_adj' column.
    """
    # Assign 'DECAYED' if decay class > 3, else keep original species code
    woody_merged_df['woody_species_adj'] = np.where(
        woody_merged_df['woody_decay'] > 3,
        'DECAYED',
        woody_merged_df['woody_species']
    )
    return woody_merged_df


def _calc_woody_specific_gravity(woody_merged_df: pd.DataFrame, tree_params: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate and assign specific gravity values for each woody debris piece in the
    merged transect DataFrame, based on species and diameter, normalized by the sum of
    diameters per plot and class. Each piece takes the column whose size range holds its
    diameter (greater than the previous breakpoint and up to its own; see specific_gravity_map).

    :param woody_merged_df: DataFrame with merged woody debris transect data.
    :param tree_params: DataFrame with specific gravity parameters for each species.
    :return: Updated woody_merged_df
    """
    for _, param_col, low_lim, up_lim in specific_gravity_map:
        # Mask for diameter class (low_lim < diam <= up_lim)
        diam_mask = woody_merged_df['woody_diam_cm'].between(low_lim, up_lim, inclusive='right')
        # For each plot in this diameter class
        for plot in woody_merged_df['ParentGlobalID'].unique():
            plot_mask = woody_merged_df['ParentGlobalID'] == plot
            diam_sum = woody_merged_df.loc[plot_mask, 'woody_diam_cm'].sum()
            # Calculate sum of diameters for normalization
            woody_merged_df.loc[plot_mask, f'woody_diam_sum'] = diam_sum
            # For each species in this plot and diameter class
            for spp in woody_merged_df.loc[plot_mask, 'woody_species_adj'].unique():
                spp_mask = woody_merged_df['woody_species_adj'] == spp
                # Get specific gravity for species
                # Fallback to 'UNK' if spp not in tree_params
                woody_merged_df.loc[diam_mask & plot_mask & spp_mask, 'woody_sg'] = (
                    tree_params.loc[spp, param_col]
                    if spp in tree_params.index
                    else tree_params.loc['UNK', param_col]
                )
                # Calculate species percentage of total diameter for normalization
                woody_merged_df.loc[diam_mask & plot_mask & spp_mask, 'woody_spp_percent_wtd'] = (
                    100 * woody_merged_df['woody_diam_cm'] / diam_sum if diam_sum else 0
                )
                # Assign normalized specific gravity
                woody_merged_df.loc[diam_mask & plot_mask & spp_mask, f'woody_sg_wtd'] = (
                        woody_merged_df['woody_sg'] * woody_merged_df['woody_spp_percent_wtd'] / 100
                )

    return woody_merged_df


def _calc_woody_volume(woody_merged_df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate the volume (m^3 per ha) of woody debris based on specific gravity and diameter.
    Equations per Van Wagner (1968, 1982).

    :param woody_merged_df: DataFrame containing woody debris data with 'woody_sg_wtd' and 'woody_diam_cm'.
    :return: Updated woody_merged_df with a new 'woody_volume_m3' column.
    """
    # Calculate constant k for volume calculation
    # k represents a probability factor (pi/2) and a factor (pi/4) needed to convert d^2 into a circular area
    k = (np.pi ** 2) / 8

    # Calculate volume in cubic meters: V = (k/L) * d^2
    woody_merged_df['woody_volume_m3pha'] = ((k / woody_merged_df['tsct_length_cor']) *
                                             np.power(woody_merged_df['woody_diam_cm'], 2))

    return woody_merged_df


def _calc_woody_weight(woody_merged_df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate the weight (kg per m^2) of woody debris based on specific gravity and volume.
    Divide by 10 to convert from t/ha to kg/m^2.
    Equations per Van Wagner (1968, 1982).

    :param woody_merged_df: DataFrame containing woody debris data with 'woody_sg_wtd' and 'woody_volume_m3'.
    :return: Updated woody_merged_df with a new 'woody_biomass_kg' column.
    """
    # Calculate weight of fuel (W) in kilograms per m^2: W = sg * volume / 10
    woody_merged_df['woody_mass_kgpm2'] = (
            woody_merged_df['woody_sg'] * woody_merged_df['woody_volume_m3pha'] /
            10  # Convert from t/ha to kg/m^2
    )

    return woody_merged_df


def _concat_spp_comp_frames(*frames: pd.DataFrame) -> pd.DataFrame:
    """
    Concatenate species-composition frames without all-NA dtype inference.

    :param frames: Species-composition DataFrames to concatenate.
    :return: Combined DataFrame retaining schema-only columns and stable dtypes.
    """
    all_columns = pd.Index([])
    populated_frames = []

    for frame in frames:
        all_columns = all_columns.union(frame.columns, sort=False)
        if not frame.empty:
            # An all-NA column contributes no data, but including it in concat
            # makes its placeholder dtype affect pandas' result dtype.
            populated_frames.append(frame.dropna(axis=1, how='all'))

    if not populated_frames:
        return frames[0].copy().reset_index(drop=True)

    result = pd.concat(populated_frames, ignore_index=True)

    # Keep schema-only columns from empty inputs without involving them in
    # concat's dtype inference.
    for column in all_columns.difference(result.columns, sort=False):
        source_dtype = next(frame[column].dtype for frame in frames if column in frame.columns)
        result[column] = pd.Series(index=result.index, dtype=source_dtype)

    return result.reindex(columns=all_columns)


def _get_merged_woody_df(in_folder: 'str | table_reader.FormSource') -> pd.DataFrame:
    """
    Merge transect woody debris CSVs into a single DataFrame, removing transect prefixes from column names.
    Adds a 'transect_id' column to indicate the transect number (1 or 2).

    :param in_folder: Path to the form folder of transect tables, or a resolved FormSource.
    :return: Merged DataFrame with unified column names and transect_id.
    """
    in_folder = table_reader.ensure_form_source(in_folder)

    # Load first transect and remove 't1_' prefix from columns
    woody_df1 = table_reader.read_table(in_folder, 't1_woody_2')
    woody_df1.columns = [col.replace('t1_', '') for col in woody_df1.columns]
    woody_df1['transect_id'] = 1

    # If second transect exists, load and remove 't2_' prefix, then concatenate
    if table_reader.has_table(in_folder, 't2_woody_3'):
        woody_df2 = table_reader.read_table(in_folder, 't2_woody_3')
        woody_df2.columns = [col.replace('t2_', '') for col in woody_df2.columns]
        woody_df2['transect_id'] = 2
        woody_merged_df = pd.concat([woody_df1, woody_df2], ignore_index=True)
    else:
        woody_merged_df = woody_df1.copy()

    return woody_merged_df


def _get_sg_output_column(diameter_cm: float) -> str:
    """
    Find the plot-level specific gravity column for a diameter.

    The column is the first breakpoint at or above the diameter: greater than the previous breakpoint and up to
    and including its own, so 0.45 cm uses the 0.5 column, 4.8 cm uses the 5 column, and 20 cm uses the last column.

    :param diameter_cm: Diameter of a woody debris piece or the upper cutoff of a tally class (cm).
    :return: Name of the plot-level specific gravity column.
    """
    if not diameter_cm > 0:
        raise ValueError(f'No specific gravity column for a diameter of {diameter_cm} cm')
    for out_col, _, lower, upper in specific_gravity_map:
        if lower < diameter_cm <= upper:
            return out_col
    raise ValueError(f'No specific gravity column for a diameter of {diameter_cm} cm')


def _get_van_wagner_qmd(
        df: pd.DataFrame,
        extension: str,
        diam_classes: list[float],
        trans_lengths: list[float]
) -> pd.DataFrame:
    """
    Calculate the quadratic mean diameter (QMD) for woody debris fuel size classes using the Van Wagner method.

    This function estimates QMD for each diameter class in a plot, based on tally counts and transect lengths.
    It uses a regression approach (log-log of adjusted frequency vs. mid-class diameter) to estimate the slope,
    then applies the Van Wagner equations to compute QMD. If insufficient data exists, it falls back to
    default QMD values from Delisle and Woodard (1988).

    :param df: DataFrame containing tally counts and transect length columns for each plot.
        An optional unique_id column identifies plots in regression-failure warnings; absent count
        columns are excluded from fitting and retain missing QMD.
    :param extension: String extension for column names (e.g., 'can', 'mod').
    :param diam_classes: List of diameter class upper bounds (in cm).
    :param trans_lengths: List of transect lengths (in meters) for each class.
    :return: DataFrame with QMD columns for each diameter class; zero plot rows return
        an empty floating-point frame with the input index preserved. Failed regressions use the
        existing fallback values and log a warning; zero or missing tallies produce no warning.
    """
    if df.index.empty:
        return pd.DataFrame(index=df.index, columns=[f'qmd{dc}' for dc in diam_classes], dtype=float)

    # Replace missing values and zeros with np.nan for proper calculations
    dc_df = df.copy().replace(r'^\s+$', np.nan, regex=True).replace(0, np.nan)

    # Average QMD values from Delisle and Woodard (1988), designed for typical Canadian fuel size classes
    # Polynomial Model Equation for Delisle and Woodard (1988) points (best between ~0.5cm and ~7cm):
    # QMD = 0.0537x^2 + 0.4583x + 0.0977 (R^2 = 0.9977)
    delisle_dict = {
        '0.5': 0.3155,
        '0.635': 0.0537 * (0.635 ** 2) + 0.4583 * 0.635 + 0.0977,
        '1': 0.68975,
        '2': 0.0537 * (2 ** 2) + 0.4583 * 2 + 0.0977,
        '2.5': 0.0537 * (2.5 ** 2) + 0.4583 * 2.5 + 0.0977,
        '2.54': 0.0537 * (2.54 ** 2) + 0.4583 * 2.54 + 0.0977,
        '3': 1.80575,
        '4': 0.0537 * (4 ** 2) + 0.4583 * 4 + 0.0977,
        '5': 3.87075,
        '6': 0.0537 * (6 ** 2) + 0.4583 * 6 + 0.0977,
        '7': 5.8905,
        '7.5': 0.0537 * (7.5 ** 2) + 0.4583 * 7.5 + 0.0977,
        '7.62': 0.0537 * (7.62 ** 2) + 0.4583 * 7.62 + 0.0977
    }

    # Replace np.nan values with 0 for further calculations
    dc_df = dc_df.replace(np.nan, 0)

    # Calculate adjusted frequency and mid-class diameter for each diameter class
    for i, dc in enumerate(diam_classes):
        dc_str = str(dc).replace('.', '_')  # Remove decimal point for column names
        count_col = fnmatch.filter(list(dc_df.columns), f'woody_count_{extension}_{dc_str}')
        if count_col:
            count_series = dc_df[count_col[0]]
        else:
            count_series = 0
        if i == 0:
            # For the first class, use the class upper bound as denominator
            dc_df[f'adjFreq{dc}'] = (dc_df[f'tsct_length_max_{extension}'] * (
                    count_series / dc_df[f'tsct_length_total_{extension}_{trans_lengths[i]}']
            )) / dc
            dc_df[f'midClass{dc}'] = dc / 2
        else:
            # For subsequent classes, use the width of the class
            dc_df[f'adjFreq{dc}'] = (dc_df[f'tsct_length_max_{extension}'] * (
                    count_series / dc_df[f'tsct_length_total_{extension}_{trans_lengths[i]}']
            )) / (dc - diam_classes[i - 1])
            dc_df[f'midClass{dc}'] = (dc + diam_classes[i - 1]) / 2
        # Replace zero adjusted frequencies with np.nan to avoid log(0)
        dc_df[f'adjFreq{dc}'] = dc_df[f'adjFreq{dc}'].replace(0, np.nan)
        dc_df[f'lnAdjFreq{dc}'] = np.log(dc_df[f'adjFreq{dc}'])
        dc_df[f'lnMidClass{dc}'] = np.log(dc_df[f'midClass{dc}'])

    # Prepare X (lnMidClass) and Y (lnAdjFreq) for regression
    slope_x = dc_df[[f'lnMidClass{dc}' for dc in diam_classes]].to_numpy(dtype=float)
    slope_y = dc_df[[f'lnAdjFreq{dc}' for dc in diam_classes]].to_numpy(dtype=float)

    # Remove infinite or null values from slope_x and slope_y for regression. A plot with no usable point keeps empty
    # arrays (it falls back to the Delisle and Woodard values below) instead of failing the whole run.
    finite_mask = np.isfinite(slope_x) & np.isfinite(slope_y)
    plot_ids = df['unique_id'] if 'unique_id' in df else [None] * len(df)

    def getSlope(inX, inY, plot_id):
        """
        Calculate the slope (b) of the linear regression line for the given X and Y values.

        Uses scipy.stats.linregress to compute the slope (first return value).
        Runtime warnings (escalated to errors by the caller) and ValueError failures return np.nan for the
        existing QMD fallback.

        :param inX: Array of finite X values (lnMidClass for diameter classes).
        :param inY: Array of finite Y values (lnAdjFreq for diameter classes).
        :param plot_id: Plot unique_id for error reporting, or None when unavailable.
        :return: Slope of the regression line, or np.nan after logging a failed regression.
        """
        try:
            # linregress returns (slope, intercept, rvalue, pvalue, stderr)
            return linregress(inX, inY)[0]
        except (RuntimeWarning, ValueError) as error:
            logger.warning(
                'Van Wagner QMD regression failed for %s classes: %s. Using Delisle and Woodard fallback values.',
                extension,
                error,
                extra={'unique_id': plot_id, 'issue_code': 'woody_qmd_regression_failed'},
            )
            # Return NaN if regression cannot be performed
            return np.nan

    # Escalate RuntimeWarning once for the whole loop (not once per plot) so getSlope can fall back for that plot;
    # the previous filters are restored when the block ends.
    with warnings.catch_warnings():
        warnings.simplefilter('error', RuntimeWarning)
        dc_df['slopeB'] = [
            getSlope(xs[valid], ys[valid], plot_id) if np.count_nonzero(valid) > 1 else np.nan
            for plot_id, xs, ys, valid in zip(plot_ids, slope_x, slope_y, finite_mask)
        ]

    # Adjust slope if it is exactly -1 or -3 to avoid division by zero in QMD formula
    dc_df['slopeB'] = np.where((dc_df.slopeB == -1) | (dc_df.slopeB == -3),
                              dc_df.slopeB + 0.01,
                              dc_df.slopeB)

    # Calculate QMD for each size class using Van Wagner equations or fallback values
    for i, dc in enumerate(diam_classes):
        dc_str = str(dc).replace('.', '_')  # Remove decimal point for column names
        try:
            if i == 0:
                # First class: lower bound is 0.1 cm
                dc_df[f'qmd{dc}'] = dc_df.apply(
                    lambda x: np.sqrt(((x.slopeB + 1) * (np.power(dc, x.slopeB + 3) - np.power(0.1, x.slopeB + 3))) /
                                      ((x.slopeB + 3) * (np.power(dc, x.slopeB + 1) - np.power(0.1, x.slopeB + 1))))
                    if np.isfinite(x.slopeB)
                    else delisle_dict.get(f'{dc}', np.nan), axis=1)
            else:
                # Subsequent classes: lower bound is previous class upper bound
                dc_df[f'qmd{dc}'] = dc_df.apply(
                    lambda x: np.sqrt(
                        ((x.slopeB + 1) * (np.power(dc, x.slopeB + 3) -
                                           np.power(diam_classes[i - 1], x.slopeB + 3))) /
                        ((x.slopeB + 3) * (np.power(dc, x.slopeB + 1) -
                                           np.power(diam_classes[i - 1], x.slopeB + 1))))
                    if np.isfinite(x.slopeB) & np.isfinite(x[f'adjFreq{dc}'])
                    else delisle_dict.get(f'{dc}', np.nan), axis=1)
        except RuntimeWarning:
            dc_df[f'qmd{dc}'] = delisle_dict.get(f'{dc}', np.nan)
            pass

        # Set QMD to np.nan if no tally count exists for the class
        dc_df[f'qmd{dc}'] = np.where(dc_df.get(f'woody_count_{extension}_{dc_str}', 0) == 0,
                                   np.nan, dc_df[f'qmd{dc}'])

    # Return DataFrame with QMD columns for each diameter class
    return dc_df[[f'qmd{dc}' for dc in diam_classes]]


def _load_manual_spp_comp(in_folder: 'str | table_reader.FormSource') -> pd.DataFrame:
    """Load optional manual species composition records.

    :param in_folder: Woody Debris Survey123 form folder, or a resolved FormSource.
    :return: Manual composition rows, or an empty table with the required
        columns when Survey123 omitted the unused repeat table.
    """
    in_folder = table_reader.ensure_form_source(in_folder)
    if table_reader.has_table(in_folder, 'spp_comp_manual_1'):
        return table_reader.read_table(in_folder, 'spp_comp_manual_1')
    return pd.DataFrame(columns=['ParentGlobalID', 'spp_comp_code', 'spp_comp_percent'])


def _merge_spp_comp(
        plot_df: pd.DataFrame,
        df: pd.DataFrame,
        woody_merged_df: pd.DataFrame,
        spp_comp_df: pd.DataFrame
) -> pd.DataFrame:
    """
    Ensure all plots and species in woody_merged_df are represented in spp_comp_df.
    For any (plot, species) pair missing from spp_comp_df, add a row with the summed
    woody_spp_percent_wtd from woody_merged_df.

    :param plot_df: DataFrame containing plot-level tree attributes.
    :param df: DataFrame containing plot-level data with unique IDs.
    :param woody_merged_df: DataFrame containing merged transect woody debris data.
    :param spp_comp_df: DataFrame containing existing species composition data.
    :return: Updated spp_comp_df with all (plot, species) pairs represented.
    """
    print('\tMerging species composition data')
    # ### PROCESS TREE SPECIES COMPOSITION DATA
    # Get species composition from plot_df['stand_spp_comp_woody']
    # Unpack species composition data from strings in tuples, formatted as
    # (spp_comp_code:spp_comp_percent, spp_comp_code:spp_comp_percent, etc)
    if 'stand_spp_comp_woody' in plot_df.columns:
        # Check if the column has any valid (non-null) data
        valid_data = plot_df['stand_spp_comp_woody'].notna()
        
        if valid_data.any():
            print(f'\t\tFound {valid_data.sum()} plots with tree species composition data')
            print(f'\t\tSample data: {plot_df.loc[valid_data, "stand_spp_comp_woody"].iloc[0]}')
            
            # Filter to only rows with valid data before processing
            valid_rows = plot_df[valid_data].copy()

            for _, missing_row in plot_df.loc[~valid_data].iterrows():
                logger.info(
                    'No tree-derived species composition for this plot; falling back to '
                    'another spp_comp_type source.',
                    extra={
                        'unique_id': missing_row.get('unique_id'),
                        'issue_code': 'stand_spp_comp_woody_missing_for_plot',
                    },
                )

            # Split the string into tuples and create a DataFrame
            plot_spp_comp = (
                valid_rows['stand_spp_comp_woody']
                .str.split(',', expand=True)
                .stack()
                .str.split(':', expand=True)
                .rename(columns={0: 'spp_comp_code', 1: 'spp_comp_percent'})
                .assign(unique_id=lambda x: x.index.get_level_values(0).map(valid_rows['unique_id']))
                .reset_index(level=1, drop=True)
            )
            
            print(f'\t\tParsed {len(plot_spp_comp)} species entries from tree data')

            # Convert spp_comp_percent to numeric and fill NaN with 0
            plot_spp_comp['spp_comp_percent'] = pd.to_numeric(plot_spp_comp['spp_comp_percent'], errors='coerce').fillna(0)

            # Add spp_comp_type column
            plot_spp_comp['spp_comp_type'] = 'tree_data'

            # Concatenate with existing spp_comp_df
            spp_comp_df = _concat_spp_comp_frames(spp_comp_df, plot_spp_comp)
        else:
            logger.warning(
                'stand_spp_comp_woody column exists but contains no valid data for any plot.'
            )
            print('\t\tThis is normal if trees were not processed or plots have no trees')
    else:
        logger.warning('stand_spp_comp_woody column not found (trees may not have been processed).')

    # ### PROCESS TRANSECT SPECIES COMPOSITION DATA
    # All (plot, species) pairs in woody_merged_df with their summed percent
    transect_spp_comp = (
        woody_merged_df.groupby(['ParentGlobalID', 'woody_species'], as_index=False)['woody_spp_percent_wtd']
        .sum()
        .rename(columns={'woody_species': 'spp_comp_code', 'woody_spp_percent_wtd': 'spp_comp_percent'})
    )
    transect_spp_comp['spp_comp_type'] = 'transect_data'
    transect_spp_comp['unique_id'] = transect_spp_comp['ParentGlobalID'].map(
        df.set_index('GlobalID')['unique_id'].to_dict()
    )

    # ### MERGE RESULTS
    if not transect_spp_comp.empty:
        spp_comp_df = _concat_spp_comp_frames(spp_comp_df, transect_spp_comp)
    
    return spp_comp_df


_COMPARE_COLUMN_PREFIXES = ('compare_woody_count', 'compare_woody_qmd', 'compare_woody_kgpm2')


def _prefix_compare_columns(df: pd.DataFrame, enabled: bool) -> pd.DataFrame:
    """
    Reconcile woody-count and QMD comparison columns for output.

    When measured-vs-tally comparison is enabled, renames fresh woody-count
    and Van Wagner QMD columns to their 'compare_' form in place, so exported
    column order matches the source column's own position rather than
    wherever a stale same-named column happened to sit. Columns already
    carrying the 'compare_' prefix are left alone, and any pre-existing
    column already using a computed target name is dropped first so renaming
    never creates a duplicate label.

    When disabled, drops every existing column carrying a known comparison
    prefix, so toggling comparison off always removes stale comparison
    output regardless of what a prior run left behind.

    Reprocessing safety does not extend across a change in
    `woody_debris_params` between calls on the same DataFrame while
    comparison stays enabled: columns left over from a diameter-cutoff or
    woody-class configuration that is no longer active are not detected or
    removed, since `woody_debris_params` is a single static configuration in
    production and never varies between calls on the same table.

    :param df: DataFrame containing tallied woody-debris count and QMD columns.
    :param enabled: Whether measured-vs-tally comparison output is enabled.
    :return: DataFrame with comparison columns reconciled for this run.
    """
    if not enabled:
        stale_columns = [
            col_name for col_name in df
            if col_name.startswith(_COMPARE_COLUMN_PREFIXES)
        ]
        return df.drop(columns=stale_columns)

    rename_map = {
        col_name: f'compare_{col_name}'
        for col_name in df
        if not col_name.startswith('compare_')
        and ('woody_count_' in col_name or 'qmd_vanwagner' in col_name)
    }
    if not rename_map:
        return df

    stale_targets = [target for target in rename_map.values() if target in df.columns]
    return df.drop(columns=stale_targets).rename(columns=rename_map)


def _resolve_spp_comp_type(df: pd.DataFrame, spp_comp_df: pd.DataFrame) -> tuple[pd.DataFrame, list]:
    """
    Resolve the species composition source actually usable for each plot, falling back to
    another available source when the declared 'spp_comp_type' has no matching rows in
    spp_comp_df (e.g., a plot declares 'tree_data' but the Trees form was not processed).

    :param df: DataFrame containing plot-level data with 'unique_id' and declared 'spp_comp_type'.
    :param spp_comp_df: DataFrame containing merged species composition data with 'unique_id'
        and 'spp_comp_type'.
    :return: Updated df with 'spp_comp_type' overwritten to the resolved source and a new
        'spp_comp_type_declared' column preserving the original value, plus a list of columns
        to keep.
    """
    print('\tResolving species composition source availability')

    priority = ['tree_data', 'transect_data', 'manual_entry']
    available = {
        spp_comp_type: set(sub['unique_id'])
        for spp_comp_type, sub in spp_comp_df.groupby('spp_comp_type')
    }

    def _resolve(row):
        """
        Resolve the best available species-composition source for one plot.

        :param row: Plot row containing unique_id and declared spp_comp_type.
        :return: Declared source when available, otherwise the first usable fallback source.
        """
        declared = row['spp_comp_type']
        if row['unique_id'] in available.get(declared, set()):
            return declared
        for fallback in priority:
            if fallback != declared and row['unique_id'] in available.get(fallback, set()):
                logger.info(
                    f"Declared spp_comp_type '{declared}' had no matching species composition "
                    f"data; used '{fallback}' instead.",
                    extra={'unique_id': row['unique_id'], 'issue_code': 'spp_comp_type_fallback'},
                )
                return fallback
        return declared

    df['spp_comp_type_declared'] = df['spp_comp_type']
    df['spp_comp_type'] = df.apply(_resolve, axis=1)

    return df, ['spp_comp_type_declared']


def process_woody_debris(
        in_folder: 'str | table_reader.FormSource',
        out_folder: str,
        plot_df: pd.DataFrame,
        woody_debris_params: dict
) -> tuple[pd.DataFrame, list]:
    """
    Process woody debris data from a CSV file and return an updated DataFrame.

    :param in_folder: Path to the form folder of input tables, or a resolved FormSource.
    :param out_folder: Path to the folder where output CSV files will be saved.
    :param plot_df: DataFrame containing plot-level data.
    :param woody_debris_params: Dictionary containing parameters for processing woody debris.
    :return: DataFrame with processed woody debris attributes.
    """
    print('\nProcessing Woody Debris data')
    in_folder = table_reader.ensure_form_source(in_folder)

    # Initialize list of columns to keep
    keep_columns = []

    # Load tree parameters and set index
    tree_params_df = helper.get_df(
        os.path.join(os.path.dirname(__file__), '..', 'supporting_data', 'tree_parameters.csv')
    ).set_index('Species')

    # ### PROCESS PLOT DATA
    # Get woody debris dataframe
    df = table_reader.read_table(in_folder, 'survey_0')
    # Generate a unique ID for each plot
    df = helper.get_unique_id(df)
    # Process plot attributes
    df = _calc_plot_t2_azimuth(df)
    df, add_columns = _calc_plot_duff_litter_depths(df)
    keep_columns.extend(add_columns)
    df = _calc_plot_tsct_slope_correction(df)
    df = _calc_plot_tsct_total_slope_correction(df, woody_debris_params)

    # ### PROCESS WOODY DATA
    # Get transect woody debris data
    woody_merged_df = _get_merged_woody_df(in_folder)
    # Process woody debris attributes
    woody_merged_df = _calc_woody_diam_cm(woody_merged_df)
    woody_merged_df = _calc_woody_corrected_tsct_lengths(df, woody_merged_df, woody_debris_params)
    woody_merged_df = _calc_woody_species(woody_merged_df)
    woody_merged_df = _calc_woody_specific_gravity(woody_merged_df, tree_params_df)
    woody_merged_df = _calc_woody_volume(woody_merged_df)
    woody_merged_df = _calc_woody_weight(woody_merged_df)

    # ### PROCESS SPECIES COMPOSITION DATA
    # Get manual entry species composition dataframe
    spp_comp_df = _load_manual_spp_comp(in_folder)
    # Process species composition attributes
    spp_comp_df = _assign_spp_comp_id_col(df, spp_comp_df)
    spp_comp_df = _add_spp_comp_type(spp_comp_df)
    spp_comp_df = _merge_spp_comp(plot_df, df, woody_merged_df, spp_comp_df)
    df, add_columns = _resolve_spp_comp_type(df, spp_comp_df)
    keep_columns.extend(add_columns)
    spp_comp_df = _calc_spp_comp_duff_litter_bulk_density(spp_comp_df, tree_params_df)
    spp_comp_df = _calc_spp_comp_specific_gravity(spp_comp_df, tree_params_df)

    # ### PROCESS PLOT DUFF AND LITTER BULK DENSITY DATA
    df, add_columns = _calc_plot_duff_litter_biomass(plot_df, df, spp_comp_df)
    keep_columns.extend(add_columns)

    # ### PROCESS PLOT SPECIFIC GRAVITY DATA
    # Generate plot-level specific gravity values
    df, add_columns = _calc_plot_specific_gravity(df, spp_comp_df)
    # keep_columns.extend(add_columns)

    # ### PROCESS TALLIED WOODY DATA
    df = _calc_tallied_woody_counts(df)
    df, add_columns = _calc_tallied_woody_biomass(df, woody_merged_df, woody_debris_params)
    keep_columns.extend(add_columns)

    # ### PROCESS PLOT-LEVEL WOODY DEBRIS ATTRIBUTES
    df, add_columns = _calc_plot_woody_debris(df, woody_merged_df, woody_debris_params)
    keep_columns.extend(add_columns)

    # Save the processed DataFrame to the output folder
    os.makedirs(out_folder, exist_ok=True)
    helper.export_csv(df, os.path.join(out_folder, 'survey_0.csv'))
    helper.export_csv(spp_comp_df, os.path.join(out_folder, 'spp_comp_merged.csv'))
    helper.export_csv(woody_merged_df, os.path.join(out_folder, 't_woody_merged.csv'))

    return df, keep_columns
