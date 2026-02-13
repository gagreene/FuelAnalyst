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

    # Remove rows with missing required data
    required_cols = ['instand_ws_kmph', 'canopy_cover', 'ht_ovrstry_live', 'fsg', 'ws', 'hfi', 'fire_type', 'temp']
    # Only keep columns that exist in stand_fire_df
    filtered_required_cols = [col for col in required_cols if col in stand_fire_df.columns]
    if filtered_required_cols:
        stand_fire_df = stand_fire_df.dropna(subset=filtered_required_cols)
    else:
        print('Warning: None of the required columns found in stand_fire_df. Skipping dropna.')

    # Identify scenario columns (all columns except unique_id and weather/fire variables)
    scenario_cols = [col for col in stand_fire_df.columns if col not in ['unique_id', 'instand_ws_kmph', 'hfi', 'fire_type', 'temp']]
    # Merge tree data with all fire weather scenarios for each unique_id
    merged_df = pd.merge(tree_df, stand_fire_df, on='unique_id', how='inner', suffixes=('', '_fire'))

    # Calculate mortality for each tree-fire scenario combination
    def get_col(col):
        return merged_df[col].to_numpy() if col in merged_df.columns else None

    merged_df['mortality_crnsch'] = fofem.mort_crnsch(
        spp=get_col('spp'),
        dbh=get_col('dbh'),
        ht=get_col('ht'),
        crown_depth=get_col('crown_depth'),
        bark_thickness=get_col('bark_thick'),
        fire_intensity=get_col('hfi'),
        amb_t=get_col('temp'),
        flame_length=get_col('flame_length'),
        char_ht=get_col('char_height'),
        scorch_ht=get_col('scorch_height'),
        instand_ws=get_col('instand_ws_kmph'),
        aspen_sev=aspen_sev,
        tree_code_dict=tree_code_dict
    )

    # Calculate tree-level mortality for each scenario
    merged_df['prob_mortality_crnsch'] = merged_df['mortality_crnsch']
    merged_df['tree_dead_crnsch'] = np.where(merged_df['prob_mortality_crnsch'] > 0.5, 1, 0)
    merged_df['tree_dead_ba_crnsch'] = np.where(merged_df['tree_dead_crnsch'] == 1, merged_df['ba_live_ha'], 0)

    # Calculate stand-level proportion of basal area killed by fire for each scenario
    agg_df = merged_df.groupby(['unique_id', 'hfi', 'fire_type', 'temp', 'instand_ws_kmph'], as_index=False).agg({
        'ba_live_ha': 'sum',
        'tree_dead_ba_crnsch': 'sum'
    })
    agg_df['prop_dead_ba_crnsch'] = agg_df['tree_dead_ba_crnsch'] / agg_df['ba_live_ha']

    # Merge aggregated results back to original stand_fire_df to preserve all columns
    stand_fire_df = pd.merge(
        stand_fire_df,
        agg_df[['unique_id', 'hfi', 'fire_type', 'temp', 'instand_ws_kmph', 'tree_dead_ba_crnsch', 'prop_dead_ba_crnsch']],
        on=['unique_id', 'hfi', 'fire_type', 'temp', 'instand_ws_kmph'],
        how='left'
    )

    # Calculate stand-level fire severity per Agee (1994)
    stand_fire_df = _calc_severity_class(stand_fire_df)

    # Save results to output folder
    os.makedirs(out_dir, exist_ok=True)
    helper.export_csv(merged_df, os.path.join(out_dir, 'fofem_tree_mortality_results.csv'))
    helper.export_csv(stand_fire_df, os.path.join(out_dir, 'fofem_severity_results.csv'))

    return


# Test routine for FOFEM mortality processing
if __name__ == '__main__':
    # Define input and output folders
    test_dir = os.path.join(os.path.dirname(__file__), 'tests')
    _in_tree_data_dir = os.path.join(test_dir, 'results', 'fuel_analyst')
    _in_fire_data_dir = os.path.join(test_dir, 'results', 'conpyro')
    _out_dir = os.path.join(test_dir, 'results', 'fofem_mortality')
    _aspen_sev = 'low'

    # Get stand fire and tree csv paths
    _stand_fire_csv_path = os.path.join(_in_fire_data_dir, 'ccp_df_results.csv')
    _tree_csv_path = os.path.join(_in_tree_data_dir, 'master_tree_df.csv')

    # Process mortality
    process_mortality(
        stand_fire_csv_path=_stand_fire_csv_path,
        tree_csv_path=_tree_csv_path,
        out_dir=_out_dir,
        aspen_sev=_aspen_sev,
    )
