# -*- coding: utf-8 -*-
"""
Created on Sun Feb 1, 16:30:00 2026

@author: Gregory A. Greene
"""
__author__ = ['Gregory A. Greene, map.n.trowel@gmail.com']

import os
import numpy as np
import pandas as pd

import sys
pkg_dir = os.path.join(os.path.dirname(__file__), '..', '..')
if pkg_dir not in sys.path:
    sys.path.insert(0, pkg_dir)

from src.fuel_analyst.components import helper
from dependencies.flame_components import flame_components as fc
from dependencies.pyfofem.src.pyfofem import pyfofem as fofem


def _calc_stand_ba_killed(stand_fire_df: pd.DataFrame,
                          tree_df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate live stand basal area killed based on mortality probability.
    :param stand_fire_df: DataFrame containing stand fire data with 'unique_id' column.
    :return: DataFrame with added basal area killed columns.
    """
    # Calculate tree-level mortality
    stand_fire_df['total_live_ba'] = stand_fire_df['unique_id'].map(
        tree_df.groupby('unique_id')['ba_live_ha'].sum()
    )
    stand_fire_df['dead_ba_crnsch'] = stand_fire_df['unique_id'].map(
        tree_df.groupby('unique_id')['tree_dead_ba_crnsch'].sum()
    )
    stand_fire_df['prop_dead_ba_crnsch'] = stand_fire_df['dead_ba_crnsch'] / stand_fire_df['total_live_ba']

    return stand_fire_df


def _calc_severity_class(stand_fire_df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate stand-level fire severity based on proportion of basal area killed.
    0-20% = low, 20-70% = moderate, 70-100% = high (Agee, 1994).
    :param stand_fire_df: DataFrame containing stand fire data with 'prop_dead_ba_crnsch' column.
    :return: DataFrame with added 'fire_severity' column.
    """
    prop_dead_ba = stand_fire_df['prop_dead_ba_crnsch']
    mask_low = (0 <= prop_dead_ba) & (prop_dead_ba <= 0.2)
    mask_mod = (prop_dead_ba > 0.2) & (prop_dead_ba < 0.7)
    mask_high = prop_dead_ba >= 0.7

    stand_fire_df['fire_severity'] = None
    stand_fire_df.loc[mask_low, 'fire_severity'] = 'low'
    stand_fire_df.loc[mask_mod, 'fire_severity'] = 'mod'
    stand_fire_df.loc[mask_high, 'fire_severity'] = 'high'

    return stand_fire_df


def _calc_tree_mortality(merged_df: pd.DataFrame,
                         tree_df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate tree-level mortality using the CRNSCH model.
    :param merged_df: DataFrame containing merged stand fire and tree data with 'mortality_crnsch' column.
    :param tree_df: DataFrame containing tree data with required columns.
    :return: DataFrame with added mortality columns.
    """
    # Calculate tree-level mortality
    tree_df['prob_mortality_crnsch'] = merged_df['mortality_crnsch']
    tree_df['tree_dead_crnsch'] = np.where(tree_df['prob_mortality_crnsch'] > 0.5, 1, 0)
    tree_df['tree_dead_ba_crnsch'] = np.where(tree_df['tree_dead_crnsch'] == 1, tree_df['ba_live_ha'], 0)

    return tree_df


def process_mortality(
    stand_fire_csv_path: str,
    tree_csv_path: str,
    out_dir: str,
    aspen_sev: str = 'low',
) -> None:
    """
    Process mortality for a DataFrame of trees using the CRNSCH model.

    :param stand_fire_csv_path: Path to CSV file containing stand fire data.
    :param tree_csv_path: Path to CSV file containing tree data.
    :param out_dir: Output directory to save results.
    :param aspen_sev: Aspen severity level ('low' or 'high') for mortality calculation.
    :return: None
    """
    print('\nProcessing Post-Fire Tree Mortality (via FOFEM CRNSCH model)')

    # Load tree parameters and set index
    tree_params_df = helper.get_df(
        os.path.join(os.path.dirname(__file__), 'supporting_data', 'tree_parameters.csv')
    ).set_index('Species')
    tree_code_dict = dict(zip(tree_params_df['sppNumCD'], tree_params_df['FOFEM_sppCD']))

    # Load stand fire and tree data
    stand_fire_df = helper.get_df(stand_fire_csv_path)
    tree_df = helper.get_df(tree_csv_path)

    # Generate required columns list
    required_cols = ['ws', 'canopy_cover', 'ht_ovrstry_live', 'ccp_fsg', 'ws', 'hfi', 'fire_type', 'temp']
    # Remove rows with missing required data
    stand_fire_df = stand_fire_df.dropna(subset=required_cols)

    # Calculate in-stand wind speed
    stand_fire_df['instand_ws'] = fc.getMidFlameWS(
        wind_speed = stand_fire_df['ws'].to_numpy(),
        canopy_cover = stand_fire_df['canopy_cover'].to_numpy(),
        canopy_ht = stand_fire_df['ht_ovrstry_live'].to_numpy(),
        canopy_baseht = stand_fire_df['ccp_fsg'].to_numpy(),
        units = 'SI'
    )

    # Merge stand fire data into tree data
    merge_cols = ['unique_id', 'instand_ws', 'hfi', 'fire_type', 'temp']
    merged_df = tree_df.merge(stand_fire_df[merge_cols], on='unique_id', how='left')

    # Calculate mortality using CRNSCH model
    print('\tCalculating post-fire probability of mortality...')
    merged_df['mortality_crnsch'] = fofem.mort_crnsch(
        spp=merged_df['spp'].to_numpy(),
        dbh=merged_df['dbh'].to_numpy(),  # Convert m to cm
        ht=merged_df['ht'].to_numpy(),
        crown_depth=merged_df['crown_depth'].to_numpy(),
        bark_thickness=merged_df['bark_thick'].to_numpy() if 'bark_thick' in merged_df.columns else None,
        fire_intensity=merged_df['hfi'].to_numpy() if 'hfi' in merged_df.columns else None,
        amb_t=merged_df['temp'].to_numpy(),
        flame_length=merged_df['flame_length'].to_numpy() if 'flame_length' in merged_df.columns else None,
        char_ht=merged_df['char_height'].to_numpy() if 'char_height' in merged_df.columns else None,
        scorch_ht=merged_df['scorch_height'].to_numpy() if 'scorch_height' in merged_df.columns else None,
        instand_ws=merged_df['instand_ws'].to_numpy(),
        aspen_sev=aspen_sev,
        tree_code_dict=tree_code_dict
    )

    # Calculate tree-level mortality
    print('\tCalculating Post-Fire Tree Mortality')
    tree_df = _calc_tree_mortality(merged_df, tree_df)

    # Calculate stand-level proportion of basal area killed by fire
    print('\tCalculating proportion of stand basal area killed...')
    stand_fire_df = _calc_stand_ba_killed(stand_fire_df, tree_df)

    # Calculate stand-level fire severity per Agee (1994)
    print('\tCalculating stand-level fire severity...')
    stand_fire_df = _calc_severity_class(stand_fire_df)

    # Save results to output folder
    print('\tSaving results to output folder...')
    os.makedirs(out_dir, exist_ok=True)
    helper.export_csv(tree_df, os.path.join(out_dir, 'tree_mortality_results.csv'))
    helper.export_csv(stand_fire_df, os.path.join(out_dir, 'stand_severity_results.csv'))

    return


if __name__ == '__main__':
    # Define input and output folders
    test_dir = os.path.join(os.path.dirname(__file__), 'tests')
    _in_tree_data_dir = os.path.join(test_dir, 'results', 'fuel_analyst')
    _in_fire_data_dir = os.path.join(test_dir, 'results', 'conpyro')
    _out_dir = os.path.join(test_dir, 'results', 'fofem_mortality')
    _aspen_sev = 'low'

    # Get stand fire and tree csv paths
    _stand_fire_df_path = os.path.join(_in_fire_data_dir, 'ccp_df_results.csv')
    _tree_df_path = os.path.join(_in_tree_data_dir, 'master_tree_df.csv')

    # Process mortality
    process_mortality(
        stand_fire_csv_path=_stand_fire_df_path,
        tree_csv_path=_tree_df_path,
        out_dir=_out_dir,
        aspen_sev=_aspen_sev,
    )
