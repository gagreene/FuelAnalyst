# -*- coding: utf-8 -*-
"""
Created on Sun Feb 1, 16:30:00 2026

@author: Gregory A. Greene
"""
__author__ = ['Gregory A. Greene']

import logging
import os
import numpy as np
import pandas as pd
from typing import Union

from . import error_handling, helper

logger = logging.getLogger(__name__)

# Explicit rename map for process_mortality()'s FOFEM-generated final-result physical columns.
# Applied via DataFrame.rename(), which silently no-ops for keys absent from a given DataFrame
# (e.g. 'mortality_crnsch'/'prob_mortality_crnsch' exist only in merged_tree_df, not
# plot_fire_df). CRNSCH mortality probabilities aren't already self-evidently 0-1-scaled from
# their bare names, unlike 'prop_dead_ba_crnsch' (kept as-is - its own 'prop_' prefix already
# states the scale).
_FINAL_RESULT_RENAME_MAP = {
    'tree_dead_ba_crnsch': 'tree_dead_ba_crnsch_m2pha',
    'mortality_crnsch': 'mortality_crnsch_prop',
    'prob_mortality_crnsch': 'prob_mortality_crnsch_prop',
}


def _calc_plot_ba_killed(
        plot_fire_df: pd.DataFrame,
        plot_id_col_name: str,
        tree_df: pd.DataFrame,
        fofem_tree_id_col_name: str
) -> pd.DataFrame:
    """
    Calculate live stand basal area killed based on mortality probability.

    :param plot_fire_df: DataFrame containing stand fire data with plot_id_col_name column.
    :param plot_id_col_name: Name of the unique ID column in plot_fire_df (default 'unique_id').
    :param tree_df: DataFrame containing tree data with fofem_tree_id_col_name column.
    :param fofem_tree_id_col_name: Name of the unique ID column in tree_df (default 'unique_id').
    :return: DataFrame with added basal area killed columns ('total_live_ba_m2pha',
        'dead_ba_crnsch_m2pha', 'prop_dead_ba_crnsch').
    """
    plot_fire_df['total_live_ba_m2pha'] = plot_fire_df[plot_id_col_name].map(
        tree_df.groupby(fofem_tree_id_col_name)['ba_live_ha'].sum()
    )
    plot_fire_df['dead_ba_crnsch_m2pha'] = plot_fire_df[plot_id_col_name].map(
        tree_df.groupby(fofem_tree_id_col_name)['tree_dead_ba_crnsch'].sum()
    )
    plot_fire_df['prop_dead_ba_crnsch'] = (
        plot_fire_df['dead_ba_crnsch_m2pha'] / plot_fire_df['total_live_ba_m2pha']
    )

    return plot_fire_df


def _calc_severity_class(plot_fire_df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate stand-level fire severity based on proportion of basal area killed.
    0-20% = low, 20-70% = moderate, 70-100% = high (Agee, 1994).

    :param plot_fire_df: DataFrame containing stand fire data with 'prop_dead_ba_crnsch' column.
    :return: DataFrame with added 'fire_severity' column.
    """
    prop_dead_ba = plot_fire_df['prop_dead_ba_crnsch']
    mask_low = (0 <= prop_dead_ba) & (prop_dead_ba <= 0.2)
    mask_mod = (prop_dead_ba > 0.2) & (prop_dead_ba < 0.7)
    mask_high = prop_dead_ba >= 0.7

    plot_fire_df['fire_severity'] = None
    plot_fire_df.loc[mask_low, 'fire_severity'] = 'low'
    plot_fire_df.loc[mask_mod, 'fire_severity'] = 'mod'
    plot_fire_df.loc[mask_high, 'fire_severity'] = 'high'

    return plot_fire_df


def _log_and_drop_incomplete_rows(
        plot_fire_df: pd.DataFrame,
        filtered_required_cols: list,
        plot_id_col_name: str,
) -> pd.DataFrame:
    """
    Log a per-plot warning for any row with a NaN in a required column, then drop it.
    Logs a single run-level warning instead if no required columns exist in plot_fire_df.

    :param plot_fire_df: DataFrame to check and filter.
    :param filtered_required_cols: Required columns that exist in plot_fire_df.
    :param plot_id_col_name: Name of the unique ID column in plot_fire_df.
    :return: plot_fire_df with incomplete rows removed.
    """
    if not filtered_required_cols:
        logger.warning('None of the required columns were found in plot_fire_df. Skipping dropna.')
        return plot_fire_df

    incomplete_mask = plot_fire_df[filtered_required_cols].isna().any(axis=1)
    for _, row in plot_fire_df.loc[incomplete_mask].iterrows():
        missing_cols = [c for c in filtered_required_cols if pd.isna(row[c])]
        logger.warning(
            f'Plot dropped from FOFEM mortality processing; missing required column(s): '
            f'{", ".join(missing_cols)}.',
            extra={'unique_id': row.get(plot_id_col_name), 'issue_code': 'fofem_mortality_missing_required_column'},
        )
    return plot_fire_df.dropna(subset=filtered_required_cols)


def filter_live_trees(
        tree_df: pd.DataFrame,
        component_logger: logging.Logger,
        issue_code: str,
) -> pd.DataFrame:
    """
    Keep only live trees eligible for FOFEM mortality modelling or export.

    Dead trees have no crown depth (undefined by trees._calc_tree_crown_depth())
    and either produce meaningless mortality predictions or NaN downstream
    values (e.g. FOFEM GUI export's CrownBaseHeight/CrownRatio). Shared by
    process_mortality() and fofem_attributes.gen_fofem_gui_app_tree_df() so
    the filter predicate, fallback, and message text can't drift between the
    two call sites - only the logger and issue_code differ per caller, for
    correct attribution in the run's error report.

    Falls back to the pre-'status'-column filter (dens_live_ha > 0 alone) and
    logs a run-level error via component_logger if 'status' is missing from
    tree_df, since that matches the exact behavior of a legacy input
    predating this column.

    :param tree_df: DataFrame of tree records; expected to include a
        'status' column and 'dens_live_ha'.
    :param component_logger: Logger to attribute a missing-'status' issue to.
    :param issue_code: issue_code to log if 'status' is missing.
    :return: DataFrame filtered to live trees only.
    """
    if helper.get_missing_df_columns(tree_df, ['status']):
        component_logger.error(
            "Tree data has no 'status' column; cannot distinguish live from "
            'dead trees. Treating input as legacy (pre-status-column) data '
            'and filtering on dens_live_ha alone.',
            extra={'unique_id': error_handling.GENERAL_ERROR_ROW, 'issue_code': issue_code},
        )
        return tree_df.loc[tree_df['dens_live_ha'] > 0].reset_index(drop=True)
    return tree_df.loc[
        (tree_df['status'] == 'L') & (tree_df['dens_live_ha'] > 0)
    ].reset_index(drop=True)


def process_mortality(
        plot_wx_fire_csv_path: str,
        fofem_tree_csv_path: str,
        out_dir: str,
        aspen_sev: str = 'low',
        plot_id_col_name: str = 'unique_id',
        fofem_tree_id_col_name: str = 'unique_id',
        return_dfs: bool = False,
) -> Union[None, tuple[pd.DataFrame, pd.DataFrame]]:
    """
    Process mortality for a DataFrame of trees using the CRNSCH model.

    :param plot_wx_fire_csv_path: Path to CSV file containing plot weather and fire data.
    :param fofem_tree_csv_path: Path to CSV file containing tree data. May include dead
        trees; they are filtered out via filter_live_trees() before modelling.
    :param out_dir: Output directory to save results.
    :param aspen_sev: Aspen severity level ('low' or 'high') for mortality calculation.
    :param plot_id_col_name: Name of the unique ID column in plot_fire_df (default 'unique_id').
    :param fofem_tree_id_col_name: Name of the unique ID column in tree_df (default 'unique_id').
    :param return_dfs: Whether to return the merged tree-fire DataFrame and the stand-level
        fire severity DataFrame (default False).
    :return: None if return_dfs is False, otherwise a tuple of (merged_tree_df, plot_fire_df) DataFrames.
    """
    # Imported here, not at module level: pyfofem is an optional extra, and
    # fofem_attributes.py imports this module for filter_live_trees() alone -
    # eagerly importing pyfofem here would make it a hard dependency of the
    # base fuel_analyst() pipeline.
    from pyfofem import pyfofem as fofem

    # Load tree parameters and set index
    tree_params_df = helper.get_df(
        os.path.join(os.path.dirname(__file__), '..', 'supporting_data', 'tree_parameters.csv')
    ).set_index('Species')
    tree_code_dict = dict(zip(tree_params_df['sppNumCD'], tree_params_df['FOFEM_sppCD']))

    # Load stand fire and tree data
    plot_fire_df = helper.get_df(plot_wx_fire_csv_path)
    tree_df = helper.get_df(fofem_tree_csv_path)
    tree_df = filter_live_trees(tree_df, logger, 'fofem_mortality_missing_status_column')

    # Remove rows with missing required data
    required_cols = ['instand_ws_mps', 'canopy_cover', 'ht_ovrstry_live', 'fsg', 'ws', 'hfi', 'fire_type', 'temp']
    # Only keep columns that exist in plot_fire_df
    filtered_required_cols = [col for col in required_cols if col in plot_fire_df.columns]
    plot_fire_df = _log_and_drop_incomplete_rows(plot_fire_df, filtered_required_cols, plot_id_col_name)

    # Merge tree data with all fire weather scenarios for each unique_id
    merged_tree_df = pd.merge(
        plot_fire_df,
        tree_df,
        left_on=plot_id_col_name,
        right_on=fofem_tree_id_col_name,
        how='inner',
        suffixes=('', '_tree')
    )

    # Calculate mortality for each tree-fire scenario combination
    print('\tProcessing Post-Fire Tree Mortality (via FOFEM CRNSCH model)...')
    def get_col(col):
        """
        Return a merged-tree column as an array when it is available.

        :param col: Column name to retrieve.
        :return: Column values as a NumPy array, or None when the column is absent.
        """
        return merged_tree_df[col].to_numpy() if col in merged_tree_df.columns else None
    params = {
        'spp': get_col('spp'),
        'dbh': get_col('dbh'),
        'ht': get_col('ht'),
        'crown_depth': get_col('crown_depth'),
        'bark_thickness': get_col('bark_thick'),
        'fire_intensity': get_col('hfi'),
        'amb_t': get_col('temp'),
        'flame_length': get_col('flame_length'),
        'char_ht': get_col('char_height'),
        'scorch_ht': get_col('scorch_height'),
        'instand_ws': get_col('instand_ws_mps'),
        'aspen_sev': aspen_sev,
        'tree_code_dict': tree_code_dict
    }
    merged_tree_df['mortality_crnsch'] = fofem.run_fofem_mortality(
        mort_function='crnsch',
        params=params,
    )

    # Calculate tree-level mortality for each scenario
    merged_tree_df['prob_mortality_crnsch'] = merged_tree_df['mortality_crnsch']
    merged_tree_df['tree_dead_crnsch'] = np.where(merged_tree_df['prob_mortality_crnsch'] > 0.5, 1, 0)
    merged_tree_df['tree_dead_ba_crnsch'] = np.where(merged_tree_df['tree_dead_crnsch'] == 1,
                                                     merged_tree_df['ba_live_ha'],
                                                     0)

    # Calculate stand-level proportion of basal area killed by fire for each scenario
    agg_df = merged_tree_df.groupby([
        plot_id_col_name, 'wx_date', 'hfi', 'fire_type', 'temp', 'instand_ws_mps'
    ], as_index=False).agg({
        'ba_live_ha': 'sum',
        'tree_dead_ba_crnsch': 'sum'
    })
    agg_df['prop_dead_ba_crnsch'] = agg_df['tree_dead_ba_crnsch'] / agg_df['ba_live_ha']

    # Merge aggregated results back to original plot_fire_df to preserve all columns
    plot_fire_df = pd.merge(
        plot_fire_df,
        agg_df[[plot_id_col_name, 'wx_date', 'hfi', 'fire_type', 'temp',
                'instand_ws_mps', 'tree_dead_ba_crnsch', 'prop_dead_ba_crnsch']],
        on=[plot_id_col_name, 'wx_date', 'hfi', 'fire_type', 'temp', 'instand_ws_mps'],
        how='left'
    )

    # Calculate stand-level fire severity per Agee (1994)
    plot_fire_df = _calc_severity_class(plot_fire_df)

    # Sort DataFrames by plot_id_col_name and wx_date for easier comparison
    merged_tree_df = merged_tree_df.sort_values(by=[plot_id_col_name, 'wx_date']).reset_index(drop=True)
    plot_fire_df = plot_fire_df.sort_values(by=[plot_id_col_name, 'wx_date']).reset_index(drop=True)

    # Unit-qualify FOFEM-generated physical columns in both final DataFrames/CSVs. Applied here,
    # immediately before export/return, so both returned DataFrames and written CSVs expose the
    # same schema. 'tree_dead_crnsch' (binary indicator), 'prop_dead_ba_crnsch' (name already
    # states its 0-1 scale), and 'fire_severity' (category) are deliberately left unsuffixed.
    merged_tree_df = merged_tree_df.rename(columns=_FINAL_RESULT_RENAME_MAP)
    plot_fire_df = plot_fire_df.rename(columns=_FINAL_RESULT_RENAME_MAP)

    # Save results to output folder
    os.makedirs(out_dir, exist_ok=True)
    out_tree_csv_path = os.path.join(out_dir, 'fofem_tree_mortality_results.csv')
    out_severity_csv_path = os.path.join(out_dir, 'fofem_severity_results.csv')
    print(f'\tSaving tree mortality results to {out_tree_csv_path}...')
    helper.export_csv(merged_tree_df, out_tree_csv_path)
    print(f'\tSaving plot severity results to {out_severity_csv_path}...')
    helper.export_csv(plot_fire_df, out_severity_csv_path)

    if return_dfs:
        # Return the merged tree-fire DataFrame and the stand-level fire severity DataFrame
        return merged_tree_df, plot_fire_df

    return None


# Test routine for FOFEM mortality processing
if __name__ == '__main__':
    # Define input and output folders
    examples_dir = helper.get_examples_dir(os.path.dirname(__file__))
    _in_tree_data_dir = os.path.join(examples_dir, 'results', 'fuel_analyst')
    _in_fire_data_dir = os.path.join(examples_dir, 'results', 'conpyro')
    _out_dir = os.path.join(examples_dir, 'results', 'fofem_mortality')
    _aspen_sev = 'low'

    # Get stand fire and tree csv paths
    _plot_wx_fire_csv_path = os.path.join(_in_fire_data_dir, 'conpyro_df_results.csv')
    _fofem_tree_csv_path = os.path.join(_in_tree_data_dir, 'master_tree_df.csv')
    _plot_fire_id_col_name = _fofem_tree_id_col_name = 'unique_id'

    # Process mortality modelling
    process_mortality(
        plot_wx_fire_csv_path=_plot_wx_fire_csv_path,
        plot_id_col_name=_plot_fire_id_col_name,
        fofem_tree_csv_path=_fofem_tree_csv_path,
        fofem_tree_id_col_name=_fofem_tree_id_col_name,
        out_dir=_out_dir,
        aspen_sev=_aspen_sev,
    )
