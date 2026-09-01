# -*- coding: utf-8 -*-
"""
Created on Tue Oct 21, 09:00:00 2025

@author: Gregory A. Greene
"""
__author__ = ['Gregory A. Greene']

import os
import numpy as np
import pandas as pd

from . import helper


def _calc_stand_density(df: pd.DataFrame, cc_field: str) -> pd.DataFrame:
    """
    Calculate stand density based on canopy cover.
        if 0 <= cc <= 45:
            density = 'L'  # low density
        elif cc <= 60:
            density = 'M'  # moderate density
        elif cc <= 100:
            density = 'H'  # high density

    :param df: DataFrame containing the canopy-cover field.
    :param cc_field: Name of the canopy-cover field used to classify stand density.
    :return: DataFrame with an added 'conpyro_density_class' column.
    """
    # Calculate stand density class from canopy cover
    mask_l = (df[cc_field] >= 0) & (df[cc_field] <= 45)
    mask_m = (df[cc_field] > 45) & (df[cc_field] <= 60)
    mask_h = (df[cc_field] > 60) & (df[cc_field] <= 100)

    density_class = pd.Series([None] * len(df), index=df.index, dtype=object)
    density_class.loc[mask_l] = 'L'
    density_class.loc[mask_m] = 'M'
    density_class.loc[mask_h] = 'H'

    return helper.attach_columns(df, {'conpyro_density_class': density_class})


def _calc_stand_type(df: pd.DataFrame, tree_params_df: pd.DataFrame) -> pd.DataFrame:
    """
    Determine the stand type based on species composition.

    :param df: DataFrame containing species codes and percentages.
    :param tree_params_df: DataFrame containing tree parameters indexed by species code.
    :return: DataFrame with added tree-type and ConPyro stand-type columns.
    """
    spp_code_cols = [f'SPECIES_CD_{x}' for x in range(1, 7)]
    tree_type_lookup = tree_params_df['TreeType']

    # Map species codes to tree types via direct hash-based lookup
    stand_type_df = df[['unique_id'] + spp_code_cols].copy()
    present_codes = stand_type_df[spp_code_cols].stack()
    present_codes = present_codes[present_codes.notna()]
    unknown_codes = present_codes[~present_codes.isin(tree_type_lookup.index)]
    if not unknown_codes.empty:
        raise KeyError(unknown_codes.iloc[0])

    stand_type_df[spp_code_cols] = pd.DataFrame(
        {column: stand_type_df[column].map(tree_type_lookup) for column in spp_code_cols},
        index=stand_type_df.index,
    )
    stand_type_df['tree_type'] = _join_first_seen_unique_types(stand_type_df[spp_code_cols])
    tree_type = df['unique_id'].map(stand_type_df.set_index('unique_id')['tree_type'])

    # Create masks for each condition
    mw_mask = tree_type.str.contains('conifer') & tree_type.str.contains('broadleaf')
    pct80_mask = (df['SPECIES_PCT_1'] >= 80) & pd.notnull(df['SPECIES_CD_1'])
    cd1_mask = pd.notnull(df['SPECIES_CD_1'])

    # Default empty string
    conpyro_stand_type = pd.Series('', index=df.index)

    # Apply MW mask
    conpyro_stand_type.loc[mw_mask] = 'MW'

    # Apply pct80_mask where MW is not already set
    conpyro_stand_type.loc[pct80_mask & ~mw_mask] = df.loc[
        pct80_mask & ~mw_mask, 'SPECIES_CD_1'
    ].map(tree_params_df['ConPyro_StandType'])

    # Apply cd1_mask where neither MW nor pct80_mask is set
    conpyro_stand_type.loc[cd1_mask & ~mw_mask & ~pct80_mask] = df.loc[
        cd1_mask & ~mw_mask & ~pct80_mask, 'SPECIES_CD_1'
    ].map(tree_params_df['ConPyro_StandType'])

    stand_columns = {
        'tree_type': tree_type,
        'conpyro_stand_type': conpyro_stand_type,
    }
    return helper.attach_columns(df, stand_columns)


def _calc_veg_fuel_loads(df: pd.DataFrame, veg_fuel_dict: dict) -> pd.DataFrame:
    """
    Calculate surface vegetation fuel loads based on ConPyro parameters.

    :param df: DataFrame containing plot-level data.
    :param veg_fuel_dict: Mapping of output fuel attributes to source fuel fields.
    :return: DataFrame with the configured ConPyro vegetation fuel-load columns.
    """
    fuel_load_columns = {}
    for fuel_att, fuel_fields in veg_fuel_dict.items():
        fuel_load = pd.Series(0, index=df.index)
        for fuel_field in fuel_fields:
            fuel_load = fuel_load + df[f'{fuel_field}_kgpm2'].fillna(0)
        fuel_load_columns[f'conpyro_{fuel_att}_fuel_load'] = fuel_load

    return helper.attach_columns(df, fuel_load_columns)


_MISSING_TYPE_SENTINEL = object()


def _join_first_seen_unique_types(columns: pd.DataFrame) -> pd.Series:
    """
    Join each row's unique values across ordered columns, preserving first-seen order.

    :param columns: DataFrame of per-row candidate values, in the column order that
        determines first-seen priority.
    :return: Series with each row's non-null unique values joined by a single space,
        in the order they first appear across the columns.
    """
    filled = columns.fillna(_MISSING_TYPE_SENTINEL)
    column_names = list(columns.columns)
    joined = pd.Series('', index=columns.index)
    for position, column in enumerate(column_names):
        first_seen = filled[column] != _MISSING_TYPE_SENTINEL
        for earlier_column in column_names[:position]:
            first_seen &= filled[column] != filled[earlier_column]
        display = pd.Series(np.where(first_seen, columns[column], ''), index=columns.index)
        both_present = (joined != '') & (display != '')
        only_joined = (joined != '') & (display == '')
        only_display = (joined == '') & (display != '')
        joined = pd.Series(np.select(
            [both_present, only_joined, only_display],
            [joined + ' ' + display, joined, display],
            default='',
        ), index=columns.index)
    return joined


def _prep_fbp_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Prepare a DataFrame for CFFBPS fuel type assignment.

    :param df: DataFrame containing plot-level data.
    :return: DataFrame formatted for CFFBPS fuel type assignment.
    """
    print('Generating CFFBPS Fuel Type Prep DataFrame')

    keep_columns = [
        'unique_id', '_date',
        'treatment_area', 'treatment_unit', 'treatment_type',
        'plot_id', 'COAST_INTERIOR_CD', 'BEC_Zone', 'BEC_Subzone', 'SPECIES_CD_1', 'SPECIES_CD_1_max_age',
        'recent_clearcut_date_10_yrs', 'recent_fire_date_11_yrs'
    ]

    fbp_prep_df = df.copy()
    fbp_prep_df['COAST_INTERIOR_CD'] = pd.NA
    fbp_prep_df['BEC_Zone'] = pd.NA
    fbp_prep_df['BEC_Subzone'] = pd.NA
    fbp_prep_df['SPECIES_CD_1_max_age'] = pd.NA
    fbp_prep_df['clearcut_date'] = pd.NaT
    fbp_prep_df['last_fire_date'] = pd.NaT
    fbp_prep_df['recent_clearcut_date_10_yrs'] = pd.NA
    fbp_prep_df['recent_fire_date_11_yrs'] = pd.NA
    fbp_prep_df = fbp_prep_df[keep_columns]

    return fbp_prep_df


def gen_conpyro_df(df: pd.DataFrame, conpyro_params: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Read ConPyro attributes from a CSV file into a pandas DataFrame.

    :param df: DataFrame containing plot-level data.
    :param conpyro_params: Dictionary of ConPyro parameters.
    :return: DataFrame containing the ConPyro attributes.
    """
    # Load tree parameters and set index
    tree_params_df = helper.get_df(
        os.path.join(os.path.dirname(__file__), '..', 'supporting_data', 'tree_parameters.csv')
    ).set_index('Species')

    df = _calc_stand_type(df, tree_params_df)
    df = _calc_stand_density(df, conpyro_params['canopy_cover_attribute'])
    df = _calc_veg_fuel_loads(df, conpyro_params['vegetative_fuel_loads'])
    fbp_prep_df = _prep_fbp_df(df)

    # Build DataFrame
    conpyro_df = pd.DataFrame({
        'unique_id': df['unique_id'],
        'plot_id': df['plot_id'],
        'lat': df['y'],
        'long': df['x'],
        'elevation': df['plot_elevation'],
        'slope': df['plot_slope_pct'],
        'aspect': df['plot_aspect'],  # slope==0 -> 270 already forced upstream in plot_attributes.py
        'stand_density': df['conpyro_density_class'],
        'stand_type': df['conpyro_stand_type'],
        'fbp_fuel_type': '',
        'pct_cnfr': df['stand_pct_cnfr_live'].fillna(0),
        'canopy_cover': df[conpyro_params['canopy_cover_attribute']].fillna(0),
        'cfl_ovrstry': df['conpyro_cfl_ovrstry'].fillna(0),
        'cbd_ovrstry': df['conpyro_cbd_ovrstry'].fillna(0),
        'cfl_midstry': df['conpyro_cfl_midstry'].fillna(0),
        'cbd_midstry': df['conpyro_cbd_midstry'].fillna(0),
        'dead_branch_fl_midstry': df['conpyro_dead_branch_fl_midstry'].fillna(0),
        'ht_ovrstry_live': df['conpyro_ht_ovrstry_live'],
        'ht_midstry_live': df['conpyro_ht_midstry_live'],
        'ht_midstry_dead': df['conpyro_ht_midstry_dead'],
        'cbh_ovrstry': df['conpyro_cbh_ovrstry'],
        'cbh_midstry': df['conpyro_cbh_midstry'],
        'fsg': df['conpyro_fsg'],
        'duff_fuel_load': df['ffl_duff_kgpm2'].fillna(0),
        'litter_fuel_load': df['ffl_litter_kgpm2'].fillna(0),
        'woody_fuel_load': df['woody_kgpm2_conpyro_lt7cm_7'].fillna(0),
        'herbaceous_fuel_load': df['conpyro_herbaceous_fuel_load'].fillna(0),
        'grass_fuel_load': df['conpyro_grass_fuel_load'].fillna(0),
        'shrub_fuel_load': df['conpyro_shrub_fuel_load'].fillna(0),
    })

    return conpyro_df, fbp_prep_df
