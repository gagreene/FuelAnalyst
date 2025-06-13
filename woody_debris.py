# -*- coding: utf-8 -*-
"""
Created on Tue May 29, 8:30:00 2025

@author: Gregory A. Greene
"""
__author__ = ['Gregory A. Greene, map.n.trowel@gmail.com']

import os
import pandas as pd
import numpy as np
import fnmatch
from scipy.stats import linregress
import helper


bulk_density_map = [
    # (output bd column, tree params column, output biomass column)
    ('stand_duff_bd_kgpm3', 'Duff_BD', 'stand_duff_depth_m', 'ffl_duff_kgpm2'),
    ('stand_litter_bd_kgpm3', 'Litter_BD', 'stand_litter_depth_m', 'ffl_litter_kgpm2'),
]

specific_gravity_map = [
    # (output sg column, input sg column, tree parameters column, lower diam limit, upper diam limit)
    ('woody_sg_05cm', 'SG_0.5', 0, 0.5),
    ('woody_sg_1cm', 'SG_1', 0.5, 1),
    ('woody_sg_3cm', 'SG_3', 1, 3),
    ('woody_sg_5cm', 'SG_5', 3, 5),
    ('woody_sg_7cm', 'SG_7', 5, 7),
    ('woody_sg_gt7cm', 'SG_7+', 7, 9999),
    ('woody_sg_1hr', 'SG_0.635', 0, 0.635),
    ('woody_sg_10hr', 'SG_2.54', 0.635, 2.54),
    ('woody_sg_100hr', 'SG_7.62', 2.54, 7.62),
    ('woody_sg_gt100hr', 'SG_7.62+', 7.62, 9999),
]


def _get_van_wagner_qmd(inDF, extension, dClasses, tLengths, tsct):
    # Replace missing values with np.nan
    dcDF = inDF.copy().replace(r'^\s+$', np.nan, regex=True)

    # Average QMD values from Delisle and Woodard (1988)
    # Designed for typical Canadian fuel size classes
    # Polynomial Model Equation for Delisle and Woodard (1988) points
    # (only good between ~0.5cm and ~7cm):
    # QMD = 0.0537x^2 + 0.4583x + 0.0977 (R^2 = 0.9977)
    delisleDict = {
        '0.5': 0.3155,
        '0.635': 0.0537 * (0.635 ** 2) + 0.4583 * 0.635 + 0.0977,
        '1': 0.68975,
        '2': 0.0537 * (2 ** 2) + 0.4583 * 2 + 0.0977,
        '2.5': 0.0537 * (2.5 ** 2) + 0.4583 * 2.5 + 0.0977,
        '2.54': 0.0537 * (2.54 ** 2) + 0.4583 * 2.54 + 0.0977,
        '3': 1.80575,
        '5': 3.87075,
        '7': 5.8905,
        '7.5': 0.0537 * (7.5 ** 2) + 0.4583 * 7.5 + 0.0977,
        '7.62': 0.0537 * (7.62 ** 2) + 0.4583 * 7.62 + 0.0977
    }

    ## Count all diameter classes with empty tallies (empty = null or nan)
    dcDF['countEmpty'] = dcDF[[col for col in dcDF.columns if 'count' in col]].isnull().sum(axis=1)

    # Replace NAN values with 0
    dcDF = dcDF.replace(np.nan, 0)

    ## These calculations should only happen if counts are missing in only 3 or fewer classes
    for i, dc in enumerate(dClasses):
        if i == 0:
            dcDF[f'adjFreq{dc}'] = ((max(tLengths) *
                                     (dcDF[fnmatch.filter(list(dcDF.columns),
                                                          f't{tsct}_count{dc}{extension}')] / tLengths[i])) /
                                    dc)
            dcDF[f'midClass{dc}'] = dc / 2
        else:
            dcDF[f'adjFreq{dc}'] = ((max(tLengths) *
                                     (dcDF[fnmatch.filter(list(dcDF.columns),
                                                          f't{tsct}_count{dc}{extension}')] / tLengths[i])) /
                                    (dc - dClasses[i - 1]))
            dcDF[f'midClass{dc}'] = (dc + dClasses[i - 1]) / 2
        dcDF[f'adjFreq{dc}'] = dcDF[f'adjFreq{dc}'].replace(0, np.nan)  # Replace 0 values with np.nan
        dcDF[f'lnAdjFreq{dc}'] = np.log(dcDF[f'adjFreq{dc}'])
        dcDF[f'lnMidClass{dc}'] = np.log(dcDF[f'midClass{dc}'])

    # Get X and Y elements to enable slope (linear regression) calculation
    dcDF['slopeX'] = dcDF.apply(lambda x: x[[f'lnMidClass{dc}' for dc in dClasses]].values.tolist(), axis=1)
    dcDF['slopeY'] = dcDF.apply(lambda x: x[[f'lnAdjFreq{dc}' for dc in dClasses]].values.tolist(), axis=1)

    # Delete infinite or null elements from slopeX and slopeY columns, using slopeY as a reference to match indices
    # Must delete slopeX values first, otherwise you lose the reference for index matching
    dcDF['slopeY'] = dcDF.apply(lambda x: np.array(x.slopeY)[np.isfinite(x.slopeX)], axis=1)
    dcDF['slopeX'] = dcDF.apply(lambda x: np.array(x.slopeX)[np.isfinite(x.slopeX)], axis=1)
    dcDF['slopeX'] = dcDF.apply(lambda x: np.array(x.slopeX)[np.isfinite(x.slopeY)], axis=1)
    dcDF['slopeY'] = dcDF.apply(lambda x: np.array(x.slopeY)[np.isfinite(x.slopeY)], axis=1)

    # Calculate slope (b) by creating a regression against the points
    def getSlope(inX, inY):
        try:
            return linregress(inX, inY)[0]
        except RuntimeWarning:
            return np.nan

    dcDF['slopeB'] = dcDF.apply(lambda x: getSlope(x.slopeX, x.slopeY)
    if len(list(x.slopeY)) > 1
    else np.nan, axis=1)

    # Handle situation where slope (b) == -1 or -3
    dcDF['slopeB'] = np.where((dcDF.slopeB == -1) | (dcDF.slopeB == -3),
                              dcDF.slopeB + 0.01,
                              dcDF.slopeB)

    ## Calculate QMD for each size class
    ## Apply default plot-level QMD values if counts missing in at least four diameter classes
    for i, dc in enumerate(dClasses):
        try:
            if i == 0:
                dcDF[f'qmd{dc}'] = dcDF.apply(
                    lambda x: np.sqrt(((x.slopeB + 1) * (np.power(dc, x.slopeB + 3) - np.power(0.1, x.slopeB + 3))) /
                                      ((x.slopeB + 3) * (np.power(dc, x.slopeB + 1) - np.power(0.1, x.slopeB + 1))))
                    if (len(x.slopeY) > 1) &
                       (np.isfinite(x.slopeB))
                    else delisleDict.get(f'{dc}', np.nan), axis=1)
            else:
                dcDF[f'qmd{dc}'] = dcDF.apply(
                    lambda x: np.sqrt(
                        ((x.slopeB + 1) * (np.power(dc, x.slopeB + 3) -
                                           np.power(dClasses[i - 1], x.slopeB + 3))) /
                        ((x.slopeB + 3) * (np.power(dc, x.slopeB + 1) -
                                           np.power(dClasses[i - 1], x.slopeB + 1))))
                    if ((len(x.slopeY) > 1) & np.isfinite(x.slopeB) & np.isfinite(x[f'adjFreq{dc}']))
                    else delisleDict.get(f'{dc}', np.nan), axis=1)
        except RuntimeWarning:
            dcDF[f'qmd{dc}'] = delisleDict.get(f'{dc}', np.nan)
            pass

        # Replace qmd values with np.nan if no count exists for the class
        dcDF[f'qmd{dc}'] = np.where(dcDF[f't{tsct}_count{dc}{extension}'] == 0, np.nan, dcDF[f'qmd{dc}'])

    return dcDF[[f'qmd{dc}' for dc in dClasses]]


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


def _calc_plot_duff_litter_depths(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate average stand-level duff, litter, and fuel bed depths (in meters)
    for each plot by averaging measurements from two transects.

    :param df: DataFrame containing plot-level duff and litter measurements.
    :return: DataFrame with new columns for stand-level duff and litter depths in meters.
    """
    # Create boolean masks for plots with one or two transects
    one_transect_mask = df['num_transects'] == 1
    two_transects_mask = df['num_transects'] == 2

    # For plots with one transect, calculate average duff and litter depths (in meters)
    df.loc[one_transect_mask, ['stand_duff_depth_m', 'stand_litter_depth_m']] = (
        df.loc[one_transect_mask, ['t1_duff_75', 't1_duff_225', 't1_litter_75', 't1_litter_225']]
        .assign(
            # Average duff depth: sum of two measurements divided by 200 (to get average in m)
            stand_duff_depth_m=lambda x: (x['t1_duff_75'] + x['t1_duff_225']) / 200,
            # Average litter depth: sum of two measurements divided by 200 (to get average in m)
            stand_litter_depth_m=lambda x: (x['t1_litter_75'] + x['t1_litter_225']) / 200
        )[['stand_duff_depth_m', 'stand_litter_depth_m']]
    )

    # For plots with two transects, calculate average duff and litter depths (in meters)
    df.loc[two_transects_mask, ['stand_duff_depth_m', 'stand_litter_depth_m']] = (
        df.loc[two_transects_mask, ['t1_duff_75', 't1_duff_225', 't2_duff_75', 't2_duff_225',
                                    't1_litter_75', 't1_litter_225', 't2_litter_75', 't2_litter_225']]
        .assign(
            # Average duff depth: sum of four measurements divided by 400 (to get average in m)
            stand_duff_depth_m=lambda x: (x['t1_duff_75'] + x['t1_duff_225'] +
                                          x['t2_duff_75'] + x['t2_duff_225']) / 400,
            # Average litter depth: sum of four measurements divided by 400 (to get average in m)
            stand_litter_depth_m=lambda x: (x['t1_litter_75'] + x['t1_litter_225'] +
                                            x['t2_litter_75'] + x['t2_litter_225']) / 400
        )[['stand_duff_depth_m', 'stand_litter_depth_m']]
    )

    return df

def _calc_plot_tsct_slope_correction(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate the corrected transect lengths based on diameter class.

    :param df: DataFrame containing transect length and slope data.
    :return: Updated df with corrected transect lengths.
    """
    # TODO - Determine if a slope correction is needed for transects
    #  (should calculations be based on horizontal length or slope length?)

    # Calculate slope correction for each transect
    for tsct in [1, 2]:
        # Calculate slope percent
        df[f't{tsct}_slope_pct'] = np.where(df[f't{tsct}_slope_units'] == 'degrees',
                                            100 * np.tan(df[f't{tsct}_slope'] * np.pi / 180),
                                            df[f't{tsct}_slope'].astype(float))

        # Calculate slope radians
        df[f't{tsct}_slope_rad'] = np.arctan(df[f't{tsct}_slope_pct'].astype(float) / 100)

        # Calculate slope correction
        df[f't{tsct}_slope_cor'] = (1 + np.power(df[f't{tsct}_slope_rad'], 2)) ** 0.5

    return df


def _get_merged_woody_df(in_folder: str) -> pd.DataFrame:
    """
    Merge transect woody debris CSVs into a single DataFrame, removing transect prefixes from column names.
    Adds a 'transect_id' column to indicate the transect number (1 or 2).

    :param in_folder: Path to the folder containing transect CSV files.
    :return: Merged DataFrame with unified column names and transect_id.
    """
    # Define file paths for both transect CSVs
    woody_df1_path = os.path.join(in_folder, 't1_woody_2.csv')
    woody_df2_path = os.path.join(in_folder, 't2_woody_3.csv')

    # Load first transect and remove 't1_' prefix from columns
    woody_df1 = helper.get_df(woody_df1_path)
    woody_df1.columns = [col.replace('t1_', '') for col in woody_df1.columns]
    woody_df1['transect_id'] = 1

    # If second transect exists, load and remove 't2_' prefix, then concatenate
    if os.path.exists(woody_df2_path):
        woody_df2 = helper.get_df(woody_df2_path)
        woody_df2.columns = [col.replace('t2_', '') for col in woody_df2.columns]
        woody_df2['transect_id'] = 2
        woody_merged_df = pd.concat([woody_df1, woody_df2], ignore_index=True)
    else:
        woody_merged_df = woody_df1.copy()

    return woody_merged_df


def _calc_woody_diam_cm(woody_merged_df: pd.DataFrame) -> pd.DataFrame:
    """
    Convert woody fuel diameter from mm to cm and round to 2 decimal places.

    :param woody_merged_df: DataFrame containing woody fuel data.
    :return: DataFrame with a new column 'woody_diam_cm' containing diameters in cm.
    """
    # Convert diameter from mm to cm and round to 3 decimal places
    woody_merged_df['woody_diam_cm'] = round(pd.to_numeric(woody_merged_df['woody_diam']) / 10, 3)

    return woody_merged_df


def _calc_woody_corrected_tsct_lengths(df: pd.DataFrame, woody_merged_df: pd.DataFrame) -> pd.DataFrame:
    """
    Assigns corrected transect lengths to woody debris pieces based on their diameter class.

    Woody debris pieces are binned by diameter (in cm) into predefined classes,
    and each class is assigned a corresponding transect length (in meters).

    :param df: DataFrame containing plot-level data (not used in this function, but kept for interface consistency).
    :param woody_merged_df: DataFrame containing woody debris data with a 'woody_diam_cm' column.
    :return: DataFrame with a new 'tsct_lengths' column indicating transect length for each piece.
    """
    # Define bin edges for woody diameter classes (in cm)
    bins = [0, 0.5, 7, 30, float('inf')]

    # Define corresponding transect lengths (in meters) for each bin
    lengths = [4.0, 10.0, 20.0, 30.0]

    # Assign transect length to each woody debris piece based on its diameter class
    woody_merged_df['tsct_length'] = pd.cut(
        woody_merged_df['woody_diam_cm'],
        bins=bins,
        labels=lengths,
        right=True
    ).astype(float)

    # Calculate the corrected transect lengths based on the slope correction value in df
    for tsct in [1, 2]:
        # Create a mapping from (GlobalID, transect_id) to slope correction if the column exists
        if f't{tsct}_slope_cor' in df.columns:
            slope_cor_map = {(gid, tsct): val for gid, val in zip(df['GlobalID'], df[f't{tsct}_slope_cor'])}
        else:
            slope_cor_map = {}

        mask = woody_merged_df['transect_id'] == tsct
        # Map the slope correction to each woody debris piece, defaulting to 1.0 if not found
        woody_merged_df.loc[mask, 'tsct_slope_cor'] = woody_merged_df.loc[mask].apply(
            lambda x: slope_cor_map.get((x['ParentGlobalID'], x['transect_id']), 1.0), axis=1
        )

        # Apply the slope correction to the transect lengths
        woody_merged_df.loc[mask, 'tsct_length_cor'] = (woody_merged_df.loc[mask, 'tsct_length'] /
                                                        woody_merged_df.loc[mask, 'tsct_slope_cor'])

    return woody_merged_df


def _calc_woody_species(woody_merged_df: pd.DataFrame) -> pd.DataFrame:
    """
    Assign adjusted species codes for woody debris pieces based on decay class.

    If the decay class (_wsf_decay) is greater than 3, assigns 'DECAYED' to the
    'wsf_species_adj' column; otherwise, retains the original species code.

    :param woody_merged_df: DataFrame containing woody debris data with
        '_wsf_decay' and 'wsf_species' columns.
    :return: DataFrame with an added or updated 'wsf_species_adj' column.
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
        merged transect DataFrame, based on species and diameter class, normalized by the sum of
        diameters per plot and class.

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
                                          np.power(woody_merged_df[f'woody_diam_cm'], 2))

    return woody_merged_df


def _calc_woody_weight(woody_merged_df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate the weight (kg per m^2) of woody debris based on specific gravity and volume.
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


def _assign_spp_comp_id_col(df: pd.DataFrame, spp_comp_df: pd.DataFrame) -> pd.DataFrame:
    # Where ParentGlobalID in spp_comp_df matches GlobalID in df, assign unique_id from df to spp_comp_df
    spp_comp_df['unique_id'] = spp_comp_df['ParentGlobalID'].map(
        df.set_index('GlobalID')['unique_id'].to_dict()
    )

    return spp_comp_df



def _add_spp_comp_type(spp_comp_df: pd.DataFrame) -> pd.DataFrame:
    """
    Add a 'spp_comp_type' column to the species composition DataFrame, defaulting to 'manual_entry'.

    :param spp_comp_df: DataFrame containing species composition data.
    :return: Updated spp_comp_df with 'spp_comp_type' column.
    """
    # Initialize spp_comp_type column with default value
    spp_comp_df['spp_comp_type'] = 'manual_entry'

    return spp_comp_df


def _merge_spp_comp(plot_df: pd.DataFrame,
                    df: pd.DataFrame,
                    woody_merged_df: pd.DataFrame,
                    spp_comp_df: pd.DataFrame,) -> pd.DataFrame:
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
        # Split the string into tuples and create a DataFrame
        plot_spp_comp = (
            plot_df['stand_spp_comp_woody']
            .str.split(',', expand=True)
            .stack()
            .str.split(':', expand=True)
            .rename(columns={0: 'spp_comp_code', 1: 'spp_comp_percent'})
            .assign(unique_id=lambda x: x.index.get_level_values(0).map(plot_df['unique_id']))
            .reset_index(level=1, drop=True)
        )
        # Convert spp_comp_percent to numeric and fill NaN with 0
        plot_spp_comp['spp_comp_percent'] = pd.to_numeric(plot_spp_comp['spp_comp_percent'], errors='coerce').fillna(0)

        # Add spp_comp_type column
        plot_spp_comp['spp_comp_type'] = 'tree_data'

        # Concatenate with existing spp_comp_df
        spp_comp_df = pd.concat([spp_comp_df, plot_spp_comp], ignore_index=True)

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
        spp_comp_df = pd.concat([spp_comp_df, transect_spp_comp], ignore_index=True)

    return spp_comp_df


def _calc_spp_comp_duff_litter_bulk_density(df: pd.DataFrame,
                                        spp_comp_df: pd.DataFrame,
                                        tree_params: pd.DataFrame) -> pd.DataFrame:

    print('\tCalculating duff and litter bulk density for species composition')

    for out_col, param_col, _, _ in bulk_density_map:
        # Initialize bulk density column
        spp_comp_df[out_col] = np.nan

        # For each species in this plot
        for spp in spp_comp_df['spp_comp_code'].unique():
            # Generate a mask for the current species
            spp_mask = spp_comp_df['spp_comp_code'] == spp
            # Get bulk density for species
            spp_comp_df.loc[spp_mask, out_col] = (
                tree_params.loc[spp, param_col]
                if spp in tree_params.index
                else tree_params.loc['UNK', param_col]
            ) * spp_comp_df['spp_comp_percent'] / 100

    return spp_comp_df


def _calc_plot_duff_litter_biomass(plot_df: pd.DataFrame,
                                   df: pd.DataFrame,
                                   spp_comp_df: pd.DataFrame) -> tuple[pd.DataFrame, list]:
    """
    Calculate plot-level duff and litter biomass (kg/m^2) for each plot, using species composition
    and bulk density data. Biomass is scaled by the proportion of flammable ground cover.

    :param plot_df: DataFrame containing plot-level attributes, including 'pc_flammable'.
    :param df: DataFrame containing plot-level data with unique IDs and spp_comp_type.
    :param spp_comp_df: DataFrame containing species composition and calculated bulk densities.
    :return: Updated df with duff and litter biomass columns.
    """
    print('\tProcessing plot-level specific gravity')

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
                df.loc[plot_mask, out_col] = biomass * df.loc[plot_mask, depth_col]

    # Initialize list of columns to keep
    keep_columns = []

    # Scale biomass by percent flammable ground cover, if available
    if 'pc_flammable' in plot_df.columns:
        flammable_map = plot_df.set_index('unique_id')['pc_flammable'].to_dict()
        for _, _, _, out_col in bulk_density_map:
            if out_col in df.columns:
                df[out_col] = df[out_col] * df['unique_id'].map(flammable_map) / 100
                keep_columns.append(out_col)

    return df, keep_columns


def _calc_spp_comp_specific_gravity(spp_comp_df: pd.DataFrame,
                                    tree_params: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate specific gravity for each species in the spp_comp_df DataFrame.

    :param spp_comp_df: DataFrame containing species composition data.
    :param tree_params: DataFrame containing specific gravity parameters for each species.
    :return: DataFrame with specific gravity columns added for each species.
    """
    print('\tCalculating specific gravity for species composition')
    # Initialize specific gravity columns based on bulk density dictionary
    for out_col, param_col in bulk_density_map:
        spp_comp_df[out_col] = np.nan

    # Assign specific gravity values based on species
    for out_col, param_col, _, _ in bulk_density_map:
        # Map specific gravity values from tree_params to spp_comp_df based on species
        spp_comp_df[out_col] = (
                spp_comp_df['spp_comp_code'].map(
                    tree_params[param_col].to_dict()
                ).fillna(tree_params.loc['UNK', param_col]) * (spp_comp_df['spp_comp_percent'] / 100)
        )

        # Convert specific gravity to float
        spp_comp_df[out_col] = pd.to_numeric(spp_comp_df[out_col], errors='coerce')

    return spp_comp_df


def _calc_plot_specific_gravity(df: pd.DataFrame,
                                spp_comp_df: pd.DataFrame) -> tuple[pd.DataFrame, list]:

    print(f'\tProcessing plot-level specific gravity')

    # Initialize list of columns to keep
    keep_columns = []

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
        df.loc[plot_comp_type_mask, f'woody_sg_comment'] = sg_comment

        # If there are no rows for this type, skip to the next iteration
        if not df[plot_comp_type_mask].empty:
            # Process specific gravity for tree data
            for out_col, param_col, _, _ in specific_gravity_map:
                spp_comp_mask = spp_comp_df['spp_comp_type'] == spp_comp_type
                # Get the specific gravity for the "manual entry" approach
                df.loc[plot_comp_type_mask, out_col] = df['unique_id'].map(
                    spp_comp_df[spp_comp_mask].groupby('unique_id')[out_col].sum()
                )
                keep_columns.append(out_col)

    return df, keep_columns


def _calc_woody_debris(in_folder: str,
                       df: pd.DataFrame,
                       tree_params: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:

    for tsct in range(1, 3):
        print(f'\tProcessing Transect {tsct}')

        # Calculate slope percent
        df[f't{tsct}_slope_pct'] = np.where(df[f't{tsct}_slope_units'] == 'degrees',
                                            100 * np.tan(df[f't{tsct}_slope'] * np.pi / 180),
                                            df[f't{tsct}_slope'].astype(float))

        # Calculate slope degrees
        df[f't{tsct}_slope_deg'] = np.arctan(df[f't{tsct}_slope_pct'].astype(float) / 100) * 180 / np.pi

        # Calculate slope correction
        df[f't{tsct}_slope_cor'] = np.sqrt(1 + np.power(df[f't{tsct}_slope_pct'].astype(float) / 100, 2))

        # Assign transect data CSV to woody_df
        woody_df = helper.get_df(os.path.join(in_folder, f't{tsct}_woody_{tsct}.csv'))
        woody_df['group'] = woody_df['ParentGlobalID']

        # Assign NAN to woody fuel pieces at distance of 999 (i.e., no data for that transect)
        # No data occurs when the user enters transect data on separate surface fuel forms
        woody_df[f't{tsct}_woody_diam'] = np.where(woody_df[f't{tsct}_woody_dist'] == 999, np.nan,
                                                   woody_df[f't{tsct}_woody_diam'])
        woody_df[f't{tsct}_woody_dist'] = np.where(woody_df[f't{tsct}_woody_dist'] == 999, np.nan, woody_df[f't{tsct}_woody_dist'])

        # Convert woody fuel diameter from mm to cm
        woody_df[f't{tsct}_woody_diam_cm'] = round(pd.to_numeric(woody_df[f't{tsct}_woody_diam']) / 10, 2)

        #### TALLIED WOODY FUELS
        ## CALCULATE VAN WAGNER QMD FOR EACH DIAMETER CLASS
        # Create diameter class and transect length lists
        dClasses = [0.5, 1, 3, 5, 7]
        tLengths = [4, 10, 10, 10, 10, 20, 30]
        wlcfFR_dClasses = [0.635, 2.54, 7.62]
        wlcfFR_tLengths = [1, 2, 4, 15]



        # Get counts of woody fuel tallies (Tree-Ring Lab Plots)
        df[f't{tsct}_count0.635'] = df[f't{tsct}_woody_fine_0to2'] + df[f't{tsct}_woody_fine_28to30']
        df[f't{tsct}_count1'] = df.group.map(
            woody_df[(woody_df[f't{tsct}_woody_diam_cm'] < 1)].groupby('group')[f't{tsct}_woody_diam_cm'].count())
        df[f't{tsct}_count3'] = df.group.map(
            woody_df[(woody_df[f't{tsct}_woody_diam_cm'] > 1) &
                 (woody_df[f't{tsct}_woody_diam_cm'] <= 3)].groupby('group')[f't{tsct}_woody_diam_cm'].count())
        df[f't{tsct}_count5'] = df.group.map(
            woody_df[(woody_df[f't{tsct}_woody_diam_cm'] > 3) &
                 (woody_df[f't{tsct}_woody_diam_cm'] <= 5)].groupby('group')[f't{tsct}_woody_diam_cm'].count())
        df[f't{tsct}_count7'] = df.group.map(
            woody_df[(woody_df[f't{tsct}_woody_diam_cm'] > 5) &
                 (woody_df[f't{tsct}_woody_diam_cm'] <= 7)].groupby('group')[f't{tsct}_woody_diam_cm'].count())

        # Get Van Wagner QMD values (Tree-Ring Lab Plots)
        # Temporarily ignore invalid values & divide by zero warnings
        # with np.errstate(divide='ignore', invalid='ignore'):
        df[[f't{tsct}_woody_qmd{dc}' for dc in sorted(dClasses)]] = getVanWagnerQMD(
            df[[f't{tsct}_count0.635', f't{tsct}_count1', f't{tsct}_count3', f't{tsct}_count5',
                  f't{tsct}_count7']],
            dClasses, tLengths)

        if tsct == 1:
            # Get counts of woody fuel tallies (WLCF Consus Plots)
            df[f't{tsct}_count0.635'] = np.where(df.group.str.contains('|'.join(['WLCFFR', "ESK'ETEMCFTU"])),
                                                   df[f't{tsct}_woody_1hr_0to1'],
                                                   df[f't{tsct}_count0.635'])
            df[f't{tsct}_count2.54'] = df[f't{tsct}_woody_10hr_0to2']
            df[f't{tsct}_count7.62'] = df.group.map(
                woody_df[(woody_df.group.str.contains('|'.join(['WLCFFR', "ESK'ETEMCFTU"]))) &
                     (woody_df[f't{tsct}_woody_diam_cm'] > 2.54) &
                     (woody_df[f't{tsct}_woody_diam_cm'] <= 7.62)].groupby('group')[f't{tsct}_woody_diam_cm'].count())

            # Get Van Wagner QMD values (WLCF Consus Plots)
            # Temporarily ignore invalid values & divide by zero warnings
            # with np.errstate(divide='ignore', invalid='ignore'):
            df[[f't{tsct}_woody_qmd1hr', f't{tsct}_woody_qmd10hr', f't{tsct}_woody_qmd100hr']] = getVanWagnerQMD(
                df[[f't{tsct}_count0.635', f't{tsct}_count2.54', f't{tsct}_count7.62']],
                wlcfFR_dClasses, wlcfFR_tLengths)

        # CALCULATE BIOMASS FOR TALLIED WOODY FUELS
        # Calculate corrected transect lengths (Tree-Ring Lab Plots)
        df[f't{tsct}_woody_0635_tlength_cor'] = 4 / df[f't{tsct}_slope_cor']
        # Convert to volumes and biomass using Van Wagner QMD value (Tree-Ring Lab Plots)
        df[f't{tsct}_woody_volume_0635'] = 10000 * df[f't{tsct}_count0.635'] * \
                                           (0.1234 / df[f't{tsct}_woody_0635_tlength_cor']) * \
                                           np.power(df[f't{tsct}_woody_qmd0.635'] / 100, 2)
        df[f't{tsct}_0635_kgpm2'] = df[f't{tsct}_slope_cor'] * df.woody_sg_05cm * \
                                      df[f't{tsct}_woody_volume_0635']
        if tsct == 1:
            # Calculate corrected transect lengths (WLCF Consus & Esk'etemc Plots)
            df[f't{tsct}_woody_1hr_tlength_cor'] = np.where(
                df.group.str.contains('|'.join(['WLCFFR', "ESK'ETEMCFTU"]), case=True),
                1 / df[f't{tsct}_slope_cor'],
                np.nan)
            df[f't{tsct}_woody_10hr_tlength_cor'] = np.where(
                df.group.str.contains('|'.join(['WLCFFR', "ESK'ETEMCFTU"]), case=True),
                2 / df[f't{tsct}_slope_cor'],
                np.nan)
            # Convert to volumes and biomass using Van Wagner QMD values (WLCF Consus & Esk'etemc Plots)
            df[f't{tsct}_woody_volume_1hr'] = 10000 * df[f't{tsct}_count0.635'] * \
                                              (0.1234 / df[f't{tsct}_woody_1hr_tlength_cor']) * \
                                              np.power(df[f't{tsct}_woody_qmd1hr'] / 100, 2)
            df[f't{tsct}_1hr_kgpm2'] = df[f't{tsct}_slope_cor'] * df.woody_sg_1hr * \
                                         df[f't{tsct}_woody_volume_1hr']
            df[f't{tsct}_woody_volume_10hr'] = 10000 * df[f't{tsct}_count2.54'] * \
                                               (0.1234 / df[f't{tsct}_woody_10hr_tlength_cor']) * \
                                               np.power(df[f't{tsct}_woody_qmd10hr'] / 100, 2)
            df[f't{tsct}_10hr_kgpm2'] = df[f't{tsct}_slope_cor'] * df.woody_sg_10hr * \
                                          df[f't{tsct}_woody_volume_10hr']

        #### MEASURED WOODY FUELS
        # Join survey_0 dataframe to the transect dataframe and assign as dfT
        # This copies the plot-level data to each row of data in the transect dataframe
        dfT = pd.merge(woody_df, df.copy(), on='group', suffixes=('_DROP', ''))  # .filter(regex='^(?!.*_DROP)')

        # Adjust Species Codes
        # Change FD species to FDI
        dfT[f't{tsct}_woody_species'] = np.where(dfT[f't{tsct}_woody_species'] == 'FD', 'FDI', dfT[f't{tsct}_woody_species'])
        dfT[f't{tsct}_woody_species'] = np.where(dfT[f't{tsct}_woody_species'] == 'FDC', 'FDI', dfT[f't{tsct}_woody_species'])
        # Change PL and P species to PLI
        dfT[f't{tsct}_woody_species'] = np.where(dfT[f't{tsct}_woody_species'] == 'PL', 'PLI', dfT[f't{tsct}_woody_species'])
        dfT[f't{tsct}_woody_species'] = np.where(dfT[f't{tsct}_woody_species'] == 'P', 'PLI', dfT[f't{tsct}_woody_species'])
        # Change C species to CW
        dfT[f't{tsct}_woody_species'] = np.where(dfT[f't{tsct}_woody_species'] == 'C', 'CW', dfT[f't{tsct}_woody_species'])
        # Change UNK species to XC (UNKNOWN CONIFER)
        # dfT[f't{tsct}_woody_species'] = np.where(dfT[f't{tsct}_woody_species'] == 'UNK', 'XC', dfT[f't{tsct}_woody_species'])

        # Calculate horizontal transect length
        dfT[f't{tsct}_woody_tlength'] = np.nan
        dfT[f't{tsct}_woody_tlength'] = np.where(dfT.group.str.contains('|'.join(['WLCFFR', "ESK'ETEMCFTU"])),
                                               # WLCF Consus Plots
                                               np.where(dfT[f't{tsct}_woody_diam_cm'] <= 7.62,
                                                        4,
                                                        dfT[f't{tsct}_woody_tlength']),
                                               # Tree-Ring Lab Plots
                                               np.where(dfT[f't{tsct}_woody_diam_cm'] <= 7,
                                                        10,
                                                        dfT[f't{tsct}_woody_tlength']))
        dfT[f't{tsct}_woody_tlength'] = np.where(dfT.group.str.contains('|'.join(['WLCFFR', "ESK'ETEMCFTU"])),
                                               # WLCF Consus Plots
                                               np.where(dfT[f't{tsct}_woody_diam_cm'] > 7.62,
                                                        15,
                                                        dfT[f't{tsct}_woody_tlength']),
                                               # Tree-Ring Lab Plots
                                               np.where((dfT[f't{tsct}_woody_diam_cm'] > 7) &
                                                        (dfT[f't{tsct}_woody_diam_cm'] <= 30),
                                                        20,
                                                        dfT[f't{tsct}_woody_tlength']))
        dfT[f't{tsct}_woody_tlength'] = np.where(dfT.group.str.contains('|'.join(['WLCFFR', "ESK'ETEMCFTU"])),
                                               # WLCF Consus Plots
                                               dfT[f't{tsct}_woody_tlength'],
                                               # Tree-Ring Lab Plots
                                               np.where(dfT[f't{tsct}_woody_diam_cm'] > 30,
                                                        30,
                                                        dfT[f't{tsct}_woody_tlength']))

        # Calculate corrected transect length
        dfT[f't{tsct}_woody_tlength_cor'] = dfT[f't{tsct}_woody_tlength'] / dfT[f't{tsct}_slope_cor']

        # Change species code to DECAYED if decay class is > 3
        dfT[f't{tsct}_woody_species_adj'] = np.where(dfT[f't{tsct}_woody_decay'] > 3,
                                                   'DECAYED',
                                                   dfT[f't{tsct}_woody_species'])

        # Get relative density / specific gravity (sg) of woody fuel piece
        sppList = [n for n in dfT[f't{tsct}_woody_species_adj'].unique() if not pd.isnull(n)]
        dfT[f't{tsct}_woody_sg'] = np.nan
        for spp in sppList:
            sg1 = tree_params.loc[spp, 'SG_1']
            sg3 = tree_params.loc[spp, 'SG_3']
            sg5 = tree_params.loc[spp, 'SG_5']
            sg7 = tree_params.loc[spp, 'SG_7']
            sg7p = tree_params.loc[spp, 'SG_7+']
            dfT[f't{tsct}_woody_sg'] = np.where((dfT[f't{tsct}_woody_species_adj'] == spp) &
                                              (dfT[f't{tsct}_woody_diam_cm'] <= 1), sg1, dfT[f't{tsct}_woody_sg'])
            dfT[f't{tsct}_woody_sg'] = np.where((dfT[f't{tsct}_woody_species_adj'] == spp) &
                                              (dfT[f't{tsct}_woody_diam_cm'] > 1) &
                                              (dfT[f't{tsct}_woody_diam_cm'] <= 3), sg3, dfT[f't{tsct}_woody_sg'])
            dfT[f't{tsct}_woody_sg'] = np.where((dfT[f't{tsct}_woody_species_adj'] == spp) &
                                              (dfT[f't{tsct}_woody_diam_cm'] > 3) &
                                              (dfT[f't{tsct}_woody_diam_cm'] <= 5), sg5, dfT[f't{tsct}_woody_sg'])
            dfT[f't{tsct}_woody_sg'] = np.where((dfT[f't{tsct}_woody_species_adj'] == spp) &
                                              (dfT[f't{tsct}_woody_diam_cm'] > 5) &
                                              (dfT[f't{tsct}_woody_diam_cm'] <= 7), sg7, dfT[f't{tsct}_woody_sg'])
            dfT[f't{tsct}_woody_sg'] = np.where((dfT[f't{tsct}_woody_species_adj'] == spp) &
                                              (dfT[f't{tsct}_woody_diam_cm'] > 7), sg7p, dfT[f't{tsct}_woody_sg'])

        ## Calculate woody fuel volume
        dfT[f't{tsct}_woody_vol'] = (0.1234 / dfT[f't{tsct}_woody_tlength_cor']) * \
                                  np.power(dfT[f't{tsct}_woody_diam_cm'] / 100, 2) * 10000

        ## Calculate kilograms per m^2 (kgpm2) for all fuel pieces
        dfT[f't{tsct}_woody_mass_kgpm2'] = dfT[f't{tsct}_slope_cor'] * \
                                         dfT[f't{tsct}_woody_sg'] * \
                                         dfT[f't{tsct}_woody_vol']

        # Calculate kgpm2 for Canadian fuel size classes
        dfT[f't{tsct}_woody_mass_kgpm2_0635cm'] = np.where(dfT[f't{tsct}_woody_diam_cm'] <= 0.635,
                                                         dfT[f't{tsct}_woody_mass_kgpm2'], 0)
        dfT[f't{tsct}_woody_mass_kgpm2_1cm'] = np.where((dfT[f't{tsct}_woody_diam_cm'] > 0.635) &
                                                      (dfT[f't{tsct}_woody_diam_cm'] <= 1),
                                                      dfT[f't{tsct}_woody_mass_kgpm2'], 0)
        dfT[f't{tsct}_woody_mass_kgpm2_3cm'] = np.where((dfT[f't{tsct}_woody_diam_cm'] > 1) &
                                                      (dfT[f't{tsct}_woody_diam_cm'] <= 3),
                                                      dfT[f't{tsct}_woody_mass_kgpm2'], 0)
        dfT[f't{tsct}_woody_mass_kgpm2_5cm'] = np.where((dfT[f't{tsct}_woody_diam_cm'] > 3) &
                                                      (dfT[f't{tsct}_woody_diam_cm'] <= 5),
                                                      dfT[f't{tsct}_woody_mass_kgpm2'], 0)
        dfT[f't{tsct}_woody_mass_kgpm2_7cm'] = np.where((dfT[f't{tsct}_woody_diam_cm'] > 5) &
                                                      (dfT[f't{tsct}_woody_diam_cm'] <= 7),
                                                      dfT[f't{tsct}_woody_mass_kgpm2'], 0)
        dfT[f't{tsct}_woody_mass_kgpm2_lte3'] = np.where(dfT[f't{tsct}_woody_diam_cm'] <= 3,
                                                       dfT[f't{tsct}_woody_mass_kgpm2'], 0)
        dfT[f't{tsct}_woody_mass_kgpm2_lte7'] = np.where(dfT[f't{tsct}_woody_diam_cm'] <= 7,
                                                       dfT[f't{tsct}_woody_mass_kgpm2'], 0)
        dfT[f't{tsct}_woody_mass_kgpm2_7to20'] = np.where((dfT[f't{tsct}_woody_diam_cm'] > 7) &
                                                        (dfT[f't{tsct}_woody_diam_cm'] <= 20),
                                                        dfT[f't{tsct}_woody_mass_kgpm2'], 0)
        dfT[f't{tsct}_woody_mass_kgpm2_gt20'] = np.where((dfT[f't{tsct}_woody_diam_cm'] > 20),
                                                       dfT[f't{tsct}_woody_mass_kgpm2'], 0)

        # Calculate kgpm2 for U.S. fuel size classes
        # 1hr = 0-0.25", 10hr = 0.25-1", 100hr = 1-3", 1000hr = 3-8", gt1000hr = >8")
        if tsct == 1:
            if processBVRC:
                dfT[f't{tsct}_woody_mass_kgpm2_1hr'] = 0
                dfT[f't{tsct}_woody_mass_kgpm2_10hr'] = 0
            elif processRover:
                dfT[f't{tsct}_woody_mass_kgpm2_1hr'] = np.where(dfT[f't{tsct}_woody_diam_cm'] < 0.635,
                                                              dfT[f't{tsct}_woody_mass_kgpm2'],
                                                              0)
                dfT[f't{tsct}_woody_mass_kgpm2_10hr'] = np.where((dfT[f't{tsct}_woody_diam_cm'] >= 0.635) &
                                                               (dfT[f't{tsct}_woody_diam_cm'] < 2.54),
                                                               dfT[f't{tsct}_woody_mass_kgpm2'],
                                                               0)
            else:
                dfT[f't{tsct}_woody_mass_kgpm2_1hr'] = np.where(
                    dfT.group.str.contains('|'.join(['WLCFFR', "ESK'ETEMCFTU"]), case=True),
                    # WLCF Consus Plots
                    dfT[f't{tsct}_1hr_kgpm2'],
                    # Tree-Ring Lab Plots
                    np.where(dfT[f't{tsct}_woody_diam_cm'] < 0.635,
                             dfT[f't{tsct}_woody_mass_kgpm2'],
                             0))
                dfT[f't{tsct}_woody_mass_kgpm2_10hr'] = np.where(
                    dfT.group.str.contains('|'.join(['WLCFFR', "ESK'ETEMCFTU"]), case=True),
                    # Rover & WLCF Consus Plots
                    dfT[f't{tsct}_10hr_kgpm2'],
                    # Tree-Ring Lab Plots
                    np.where((dfT[f't{tsct}_woody_diam_cm'] >= 0.635) &
                             (dfT[f't{tsct}_woody_diam_cm'] < 2.54),
                             dfT[f't{tsct}_woody_mass_kgpm2'],
                             0))
        else:
            if processBVRC:
                dfT[f't{tsct}_woody_mass_kgpm2_1hr'] = 0
                dfT[f't{tsct}_woody_mass_kgpm2_10hr'] = 0
            else:
                dfT[f't{tsct}_woody_mass_kgpm2_1hr'] = np.where(dfT[f't{tsct}_woody_diam_cm'] < 0.635,
                                                              dfT[f't{tsct}_woody_mass_kgpm2'],
                                                              0)
                dfT[f't{tsct}_woody_mass_kgpm2_10hr'] = np.where((dfT[f't{tsct}_woody_diam_cm'] >= 0.635) &
                                                               (dfT[f't{tsct}_woody_diam_cm'] < 2.54),
                                                               dfT[f't{tsct}_woody_mass_kgpm2'],
                                                               0)

        dfT[f't{tsct}_woody_mass_kgpm2_100hr'] = np.where((dfT[f't{tsct}_woody_diam_cm'] >= 2.54) &
                                                        (dfT[f't{tsct}_woody_diam_cm'] < 7.62),
                                                        dfT[f't{tsct}_woody_mass_kgpm2'], 0)
        dfT[f't{tsct}_woody_mass_kgpm2_1000hr'] = np.where((dfT[f't{tsct}_woody_diam_cm'] >= 7.62) &
                                                         (dfT[f't{tsct}_woody_diam_cm'] < 22.86),
                                                         dfT[f't{tsct}_woody_mass_kgpm2'], 0)
        dfT[f't{tsct}_woody_mass_kgpm2_10000hr'] = np.where((dfT[f't{tsct}_woody_diam_cm'] >= 22.86) &
                                                          (dfT[f't{tsct}_woody_diam_cm'] < 50.8),
                                                          dfT[f't{tsct}_woody_mass_kgpm2'], 0)
        dfT[f't{tsct}_woody_mass_kgpm2_gt10000hr'] = np.where(dfT[f't{tsct}_woody_diam_cm'] >= 50.8,
                                                            dfT[f't{tsct}_woody_mass_kgpm2'], 0)
        # FCCS classifications for >=1000hr fuels: sound (decay class <=3) and rotten (decay class >3)
        dfT[f't{tsct}_woody_mass_kgpm2_1000hr_sound'] = np.where((dfT[f't{tsct}_woody_diam_cm'] >= 7.62) &
                                                               (dfT[f't{tsct}_woody_diam_cm'] < 22.86) &
                                                               (dfT[f't{tsct}_woody_decay'] <= 3),
                                                               dfT[f't{tsct}_woody_mass_kgpm2'], 0)
        dfT[f't{tsct}_woody_mass_kgpm2_1000hr_rotten'] = np.where((dfT[f't{tsct}_woody_diam_cm'] >= 7.62) &
                                                                (dfT[f't{tsct}_woody_diam_cm'] < 22.86) &
                                                                (dfT[f't{tsct}_woody_decay'] > 3),
                                                                dfT[f't{tsct}_woody_mass_kgpm2'], 0)
        dfT[f't{tsct}_woody_mass_kgpm2_10000hr_sound'] = np.where((dfT[f't{tsct}_woody_diam_cm'] >= 22.86) &
                                                                (dfT[f't{tsct}_woody_diam_cm'] < 50.8) &
                                                                (dfT[f't{tsct}_woody_decay'] <= 3),
                                                                dfT[f't{tsct}_woody_mass_kgpm2'], 0)
        dfT[f't{tsct}_woody_mass_kgpm2_10000hr_rotten'] = np.where((dfT[f't{tsct}_woody_diam_cm'] >= 22.86) &
                                                                 (dfT[f't{tsct}_woody_diam_cm'] < 50.8) &
                                                                 (dfT[f't{tsct}_woody_decay'] > 3),
                                                                 dfT[f't{tsct}_woody_mass_kgpm2'], 0)
        dfT[f't{tsct}_woody_mass_kgpm2_gt10000hr_sound'] = np.where((dfT[f't{tsct}_woody_diam_cm'] >= 50.8) &
                                                                  (dfT[f't{tsct}_woody_decay'] <= 3),
                                                                  dfT[f't{tsct}_woody_mass_kgpm2'], 0)
        dfT[f't{tsct}_woody_mass_kgpm2_gt10000hr_rotten'] = np.where((dfT[f't{tsct}_woody_diam_cm'] >= 50.8) &
                                                                   (dfT[f't{tsct}_woody_decay'] > 3),
                                                                   dfT[f't{tsct}_woody_mass_kgpm2'], 0)
        # FOFEM classification for > 10hr fuels: sound (decay class <=3) and rotten (decay class >3)
        dfT[f't{tsct}_woody_mass_kgpm2_fofem3to6_sound'] = np.where((dfT[f't{tsct}_woody_diam_cm'] >= 7.62) &
                                                                  (dfT[f't{tsct}_woody_diam_cm'] < 15.24) &
                                                                  (dfT[f't{tsct}_woody_decay'] <= 3),
                                                                  dfT[f't{tsct}_woody_mass_kgpm2'], 0)
        dfT[f't{tsct}_woody_mass_kgpm2_fofem3to6_rotten'] = np.where((dfT[f't{tsct}_woody_diam_cm'] >= 7.62) &
                                                                   (dfT[f't{tsct}_woody_diam_cm'] < 15.24) &
                                                                   (dfT[f't{tsct}_woody_decay'] > 3),
                                                                   dfT[f't{tsct}_woody_mass_kgpm2'], 0)
        dfT[f't{tsct}_woody_mass_kgpm2_fofem6to9_sound'] = np.where((dfT[f't{tsct}_woody_diam_cm'] >= 15.24) &
                                                                  (dfT[f't{tsct}_woody_diam_cm'] < 22.86) &
                                                                  (dfT[f't{tsct}_woody_decay'] <= 3),
                                                                  dfT[f't{tsct}_woody_mass_kgpm2'], 0)
        dfT[f't{tsct}_woody_mass_kgpm2_fofem6to9_rotten'] = np.where((dfT[f't{tsct}_woody_diam_cm'] >= 15.24) &
                                                                   (dfT[f't{tsct}_woody_diam_cm'] < 22.86) &
                                                                   (dfT[f't{tsct}_woody_decay'] > 3),
                                                                   dfT[f't{tsct}_woody_mass_kgpm2'], 0)
        dfT[f't{tsct}_woody_mass_kgpm2_fofem9to20_sound'] = np.where((dfT[f't{tsct}_woody_diam_cm'] >= 22.86) &
                                                                   (dfT[f't{tsct}_woody_diam_cm'] < 50.8) &
                                                                   (dfT[f't{tsct}_woody_decay'] <= 3),
                                                                   dfT[f't{tsct}_woody_mass_kgpm2'], 0)
        dfT[f't{tsct}_woody_mass_kgpm2_fofem9to20_rotten'] = np.where((dfT[f't{tsct}_woody_diam_cm'] >= 22.86) &
                                                                    (dfT[f't{tsct}_woody_diam_cm'] < 50.8) &
                                                                    (dfT[f't{tsct}_woody_decay'] > 3),
                                                                    dfT[f't{tsct}_woody_mass_kgpm2'], 0)
        dfT[f't{tsct}_woody_mass_kgpm2_fofem20plus_sound'] = np.where((dfT[f't{tsct}_woody_diam_cm'] > 50.8) &
                                                                    (dfT[f't{tsct}_woody_decay'] <= 3),
                                                                    dfT[f't{tsct}_woody_mass_kgpm2'], 0)
        dfT[f't{tsct}_woody_mass_kgpm2_fofem20plus_rotten'] = np.where((dfT[f't{tsct}_woody_diam_cm'] > 50.8) &
                                                                     (dfT[f't{tsct}_woody_decay'] > 3),
                                                                     dfT[f't{tsct}_woody_mass_kgpm2'], 0)

    return dfT


def process_woody_debris(in_folder: str,
                         out_folder: str,
                         plot_df: pd.DataFrame) -> tuple[pd.DataFrame, list]:
    """
    Process woody debris data from a CSV file and return an updated DataFrame.

    :param in_folder: Path to the folder containing the input CSV files.
    :param out_folder: Path to the folder where output CSV files will be saved.
    :param plot_df: DataFrame containing plot-level data.
    :return: DataFrame with processed woody debris attributes.
    """
    print('\nProcessing Woody Debris data')

    # Initialize list of columns to keep
    keep_columns = []

    # Load tree parameters and set index
    tree_params_df = helper.get_df(
        os.path.join(os.path.dirname(__file__), 'Supporting_Data\\tree_parameters.csv')
    ).set_index('Species')

    # ### PROCESS PLOT DATA
    # Get woody debris dataframe
    df = helper.get_df(os.path.join(in_folder, 'survey_0.csv'))
    # Generate a unique ID for each plot
    df = helper.get_unique_id(df)
    # Process plot attributes
    df = _calc_plot_t2_azimuth(df)
    df = _calc_plot_duff_litter_depths(df)
    df = _calc_plot_tsct_slope_correction(df)

    # ### PROCESS WOODY DATA
    # Get transect woody debris data
    woody_merged_df = _get_merged_woody_df(in_folder)
    # Process woody debris attributes
    woody_merged_df = _calc_woody_diam_cm(woody_merged_df)
    woody_merged_df = _calc_woody_corrected_tsct_lengths(df, woody_merged_df)
    woody_merged_df = _calc_woody_species(woody_merged_df)
    woody_merged_df = _calc_woody_specific_gravity(woody_merged_df, tree_params_df)
    woody_merged_df = _calc_woody_volume(woody_merged_df)
    woody_merged_df = _calc_woody_weight(woody_merged_df)

    # ### PROCESS SPECIES COMPOSITION DATA
    # Get manual species composition dataframe
    spp_comp_df = helper.get_df(os.path.join(in_folder, 'spp_comp_manual_1.csv'))
    # Process species composition attributes
    spp_comp_df = _assign_spp_comp_id_col(df, spp_comp_df)
    spp_comp_df = _add_spp_comp_type(spp_comp_df)
    spp_comp_df = _merge_spp_comp(plot_df, df, woody_merged_df, spp_comp_df)
    spp_comp_df = _calc_spp_comp_duff_litter_bulk_density(df, spp_comp_df, tree_params_df)
    spp_comp_df = _calc_spp_comp_specific_gravity(spp_comp_df, tree_params_df)

    # ### PROCESS PLOT DUFF AND LITTER BULK DENSITY DATA
    df, add_columns = _calc_plot_duff_litter_biomass(plot_df, df, spp_comp_df)
    keep_columns.extend(add_columns)

    # ### PROCESS PLOT SPECIFIC GRAVITY DATA
    # Generate plot-level specific gravity values
    df, add_columns = _calc_plot_specific_gravity(df, spp_comp_df)
    keep_columns.extend(add_columns)

    # ### CALCULATE WOODY DEBRIS ATTRIBUTES
    df, woody_merged_df = _calc_woody_debris(in_folder, plot_df, df, woody_merged_df, tree_params_df)


    # Save the processed DataFrame to the output folder
    os.makedirs(out_folder, exist_ok=True)
    helper.export_csv(df, os.path.join(out_folder, 'survey_0.csv'))
    helper.export_csv(spp_comp_df, os.path.join(out_folder, 'spp_comp_merged.csv'))
    helper.export_csv(woody_merged_df, os.path.join(out_folder, 't_woody_merged.csv'))

    return df, keep_columns
