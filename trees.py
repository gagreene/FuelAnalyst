# -*- coding: utf-8 -*-
"""
Created on Tue May 27, 15:30:00 2025

@author: Gregory A. Greene
"""
__author__ = ['Gregory A. Greene, map.n.trowel@gmail.com']

import os
import pandas as pd
import numpy as np
import itertools
import helper


# GENERAL LIST OF CONIFER SPECIES IN BC
conifer_list = [
    'B', 'BA', 'BB', 'BG', 'BL', 'BN',
    'C', 'CE', 'CH', 'CW',
    'F', 'FD', 'FDC', 'FDI',
    'H', 'HM', 'HW', 'HX', 'HXM',
    'J', 'JR',
    'L', 'LA', 'LS', 'LT', 'LW',
    'P', 'PA', 'PF', 'PJ', 'PL', 'PLC', 'PLI', 'PP', 'PR', 'PW', 'PX', 'PXJ', 'PY',
    'S', 'SA', 'SB', 'SE', 'SR', 'SS', 'SW', 'SX', 'SXB', 'SXE', 'SXL', 'SXS', 'SXW', 'SXX',
    'T', 'TW',
    'Y', 'YC',
    'UNK', 'XC', 'ZC'
]


# VARIABLES FOR BIOMASS MODELING
tree_component_list = ['wood', 'bark', 'branches', 'foliage']
tree_component_index_dict = {
    'wood': 0,
    'bark': 1,
    'branches': 2,
    'foliage': 3
}

tree_conifer_decay_class_dict = {
    1: [1, 1, 1, 1],
    2: [1, 1, 1, 1],
    3: [1, 1, 1, 0],
    4: [0.95, 0.75, 0.5, 0],
    5: [0.80, 0.5, 0, 0],
    6: [0.66, 0.25, 0, 0],
    7: [0.5, 0.1, 0, 0],
    8: [0.33, 0.05, 0, 0],
    9: [0.05, 0, 0, 0]
}

tree_broadleaf_decay_class_dict = {
    1: [1, 1, 1, 1],
    2: [1, 1, 1, 1],
    3: [1, 1, 1, 0],
    4: [0.95, 0.75, 0.5, 0],
    5: [0.66, 0.25, 0, 0],
    6: [0.05, 0, 0, 0]
}

attribute_weighting_dict = {
    'ht': 'ba',
    'cbh': 'ba',
    'dcbh': 'ba',
    'fsg': 'ba',
    'crwn_dpth': 'ba',
    'flame_length': 'ba',
    'fire_intensity': 'ba',
}


def _calc_plot_multipliers(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate multipliers for tree data based on plot radii.

    :param df: DataFrame containing plot attributes.
    :return: DataFrame with multipliers added.
    """
    print('\tCalculating plot multipliers')
    # Calculate plot-level multipliers for tree data
    def get_multiplier(radius, small, large):
        return np.where(radius == small, 100 if small == 5.64 else 25,
                        np.where(pd.isnull(radius), np.nan, large))

    df['plot_lgtree_mult'] = get_multiplier(df.lgtree_plot_radius, 11.28, 50)
    df['plot_smtree_mult'] = get_multiplier(df.smtree_plot_radius, 5.64, 200)
    df['plot_sapling_mult'] = get_multiplier(df.sapling_plot_radius, 5.64, 200)

    return df


def _calc_sapling_tree_type(sapling_df: pd.DataFrame, tree_params_df: pd.DataFrame) -> pd.DataFrame:
    """
    Assigns sapling tree type (e.g., conifer or broadleaf) to each tree in the DataFrame
    based on species codes and a parameter DataFrame.

    :param sapling_df: DataFrame containing individual tree data, including species codes.
    :param tree_params_df: DataFrame containing species parameters, including 'TreeType'.
    :return: Updated tree_df with a new 'tree_type' column.
    """
    print('\tCalculating sapling tree types')
    # Create a mapping from species code to tree type
    tree_type_map = tree_params_df['TreeType'].to_dict()
    # Map tree species to their type and assign to new column
    sapling_df['tree_type'] = sapling_df['sapling_species'].map(tree_type_map)

    return sapling_df


def _calc_sapling_density(sapling_df: pd.DataFrame) -> pd.DataFrame:
    """
    Sets sapling counts to 0 where species is 'NO_SAPLINGS'.

    :param sapling_df: DataFrame with sapling data, including species and count columns
    :return: Updated DataFrame with zeroed counts for 'NO_SAPLINGS'.
    """
    print('\tCalculating sapling density')
    # Set counts to 0 where sapling species is 'NO_SAPLINGS'
    mask = sapling_df['sapling_species'] == 'NO_SAPLINGS'
    sapling_df.loc[mask, ['sapling_live_count', 'sapling_dead_count']] = 0
    return sapling_df


def _calc_sapling_dbh(sapling_df: pd.DataFrame) -> pd.DataFrame:
    """
    Assigns DBH (diameter at breast height) values for live and dead saplings.

    If DBH is missing but saplings are present, assigns a default value of 2.5 cm (class midpoint).
    If no saplings are present (density is 0), sets DBH to NaN.

    :param sapling_df: DataFrame with sapling data, including density and DBH columns.
    :return: Updated DataFrame with filled DBH values for live and dead saplings.
    """
    print('\tCalculating sapling dbh')
    # Default DBH comment to empty string
    sapling_df['sapling_dbh_comment'] = ''

    # Set DBH to NaN where no live saplings are present
    sapling_df['sapling_live_dbh'] = np.where(
        sapling_df.sapling_live_count == 0, np.nan, sapling_df.sapling_live_dbh
    )
    # If DBH is missing but saplings are present, assign a default value of 2.5 cm
    live_dbh_calc_mask = (sapling_df.sapling_live_count > 0) & sapling_df.sapling_live_dbh.isnull()
    sapling_df['sapling_live_dbh'] = np.where(
        live_dbh_calc_mask,
        2.5,
        sapling_df.sapling_live_dbh
    )
    # Add a comment indicating the default value assignment
    sapling_df['sapling_dbh_comment'] = np.where(
        live_dbh_calc_mask,
        (sapling_df.get('sapling_dbh_comment', '').astype(str)
         if 'sapling_dbh_comment' in sapling_df else '') +
        'Live sapling DBH was missing, and defaulted to 2.5 cm (midpoint of size class); ',
        sapling_df.sapling_dbh_comment
    )

    # Set DBH to NaN where no dead saplings are present
    sapling_df['sapling_dead_dbh'] = np.where(
        sapling_df.sapling_dead_count == 0, np.nan, sapling_df.sapling_dead_dbh
    )
    # If DBH is missing but saplings are present, assign a default value of 2.5 cm
    dead_dbh_calc_mask = (sapling_df.sapling_dead_count > 0) & sapling_df.sapling_dead_dbh.isnull()
    sapling_df['sapling_dead_dbh'] = np.where(
        dead_dbh_calc_mask,
        2.5,
        sapling_df.sapling_dead_dbh
    )
    # Add a comment indicating the default value assignment
    sapling_df['sapling_dbh_comment'] = np.where(
        dead_dbh_calc_mask,
        (sapling_df.get('sapling_dbh_comment', '').astype(str)
         if 'sapling_dbh_comment' in sapling_df else '') +
        'Dead sapling DBH was missing, and defaulted to 2.5 cm (midpoint of size class); ',
        sapling_df.sapling_dbh_comment
    )

    return sapling_df


def _calc_sapling_ht(sapling_df: pd.DataFrame, tree_params_df: pd.DataFrame) -> pd.DataFrame:
    """
    Estimate missing sapling heights using the Temesgen Model 2 height equation.

    For each sapling species, if density is present and height is missing,
    height is estimated using the species-specific Temesgen model parameters
    and the sapling's DBH. Only saplings with density > 0 and missing height
    are updated.

    :param sapling_df: DataFrame with sapling data, including species, density, DBH, and height columns.
    :param tree_params_df: DataFrame with species-specific model parameters.
    :return: Updated DataFrame with estimated heights for live and dead saplings.
    """
    print('\tCalculating sapling ht')
    # Default DBH comment to empty string
    sapling_df['sapling_ht_comment'] = ''

    # Set DBH to NaN where no live saplings are present
    sapling_df['sapling_live_ht'] = np.where(
        sapling_df.sapling_live_count == 0, np.nan, sapling_df.sapling_live_ht
    )
    # Set DBH to NaN where no dead saplings are present
    sapling_df['sapling_dead_ht'] = np.where(
        sapling_df.sapling_dead_count == 0, np.nan, sapling_df.sapling_dead_ht
    )

    # Get list of sapling species, excluding 'NO_REGEN'
    spp_list = [spp for spp in sapling_df['sapling_species'].unique() if spp != 'NO_SAPLINGS']

    # For each species, estimate missing heights for live and dead saplings
    for spp in spp_list:
        # Estimate live sapling height where density > 0 and height is missing
        mask_live = (
            (sapling_df['sapling_species'] == spp) &
            (sapling_df['sapling_live_count'] > 0) &
            (sapling_df['sapling_live_ht'].isnull())
        )
        sapling_df.loc[mask_live, 'sapling_live_ht'] = sapling_df.loc[mask_live].apply(
            lambda row: _get_temesgen_tree_height(2, tree_params_df, spp, row['sapling_live_dbh']),
            axis=1
        )
        # Add a comment indicating the default value assignment
        sapling_df['sapling_ht_comment'] = np.where(
            mask_live,
            (sapling_df.get('sapling_ht_comment', '').astype(str)
             if 'sapling_ht_comment' in sapling_df else '') +
            'Live sapling DBH was missing and calculated using the Temesgen Model 2; ',
            sapling_df.sapling_ht_comment
        )

        # Estimate dead sapling height where density > 0 and height is missing
        mask_dead = (
            (sapling_df['sapling_species'] == spp) &
            (sapling_df['sapling_dead_count'] > 0) &
            (sapling_df['sapling_dead_ht'].isnull())
        )
        sapling_df.loc[mask_dead, 'sapling_dead_ht'] = sapling_df.loc[mask_dead].apply(
            lambda row: _get_temesgen_tree_height(2, tree_params_df, spp, row['sapling_dead_dbh']),
            axis=1
        )
        # Add a comment indicating the default value assignment
        sapling_df['sapling_ht_comment'] = np.where(
            mask_dead,
            (sapling_df.get('sapling_ht_comment', '').astype(str)
             if 'sapling_ht_comment' in sapling_df else '') +
            'Dead sapling height was missing and calculated using the Temesgen Model 2; ',
            sapling_df.sapling_ht_comment
        )

    return sapling_df


def _calc_stand_attributes(df: pd.DataFrame,
                           tree_df: pd.DataFrame,
                           stand_summary_params: dict) -> tuple[pd.DataFrame, list]:
        """
        Calculates stand-level attributes for requested parameters and attributes.
        Adds columns to the plot-level DataFrame for each attribute.

        :param df: DataFrame containing plot-level data.
        :param tree_df: DataFrame containing individual tree data.
        :param stand_summary_params: Dictionary containing stand summary parameters.
        :return: Updated plot-level DataFrame with stand density columns.
        """
        # Helper: get all permutations of summary types
        def get_permutations(_summary_list: list) -> list:
            """
            Generate all valid permutations of summary types based on rules:

            :param _summary_list: List of summary types to permute.
            :return: List of valid summary permutations.
            """
            priority_order = {val: i for i, val in enumerate(_summary_list)}

            # Initialize set to hold valid permutations
            valid_permutations = set()

            for r in range(1, 4):
                for combo in itertools.combinations(summary_list, r):
                    # Rule: total only allowed as a single-element
                    if 'total' in combo and len(combo) > 1:
                        continue
                    # Rule: must follow priority order
                    if list(combo) != sorted(combo, key=lambda x: priority_order[x]):
                        continue
                    # Rule: no live + dead
                    if 'live' in combo and 'dead' in combo:
                        continue
                    # Rule: no conifer + broadleaf
                    if 'conifer' in combo and 'broadleaf' in combo:
                        continue
                    # Passed all filters
                    valid_permutations.add('_'.join(combo))

            # Custom sort: by number of parts, then priority order
            def sort_key(_combo: str):
                parts = _combo.split('_')
                return (len(parts), [priority_order.get(p, len(priority_order)) for p in parts])

            # Sort using the sort key
            return sorted(valid_permutations, key=sort_key)

        def get_summary_mask(_tree_df: pd.DataFrame, _summary: str) -> pd.Series:
            """
            Return a boolean mask for the given summary string, which may include:
            - 'total' (alone)
            - 'live', 'dead'
            - 'conifer', 'broadleaf'
            - combinations like 'live_conifer', 'dead_broadleaf', etc.
            :param _tree_df: DataFrame containing tree data.
            :param _summary: Summary string to parse.
            :return: Boolean mask Series for the summary condition.
            """
            parts = _summary.split('_')

            # 'total' is only valid by itself
            if parts == ['total']:
                return pd.Series([True] * len(_tree_df), index=_tree_df.index)

            # Start with all True mask and apply each condition
            _mask = pd.Series([True] * len(_tree_df), index=_tree_df.index)

            for part in parts:
                if part == 'live':
                    _mask &= _tree_df['tree_status'] == 'L'
                elif part == 'dead':
                    _mask &= _tree_df['tree_status'] == 'D'
                elif part == 'conifer':
                    _mask &= _tree_df['tree_type'] == 'conifer'
                elif part == 'broadleaf':
                    _mask &= _tree_df['tree_type'] == 'broadleaf'
                else:
                    # Unknown part — return all False
                    return pd.Series([False] * len(_tree_df), index=_tree_df.index)

            return _mask

        # Helper: get mask for class range
        def get_class_mask(_tree_df, _class_var, _lower, _upper):
            """
            Returns a boolean mask for the given class variable and its range.

            :param _tree_df: DataFrame containing tree data.
            :param _class_var: Class variable to filter on (e.g., 'dbh', 'ht').
            :param _lower: Lower bound for the class range.
            :param _upper: Upper bound for the class range (None for open-ended).
            :return: Boolean mask Series for the class condition.
            """
            if _upper is None:
                return _tree_df[f'tree_{_class_var}'] >= _lower
            else:
                return (_tree_df[f'tree_{_class_var}'] >= _lower) & (_tree_df[f'tree_{_class_var}'] < _upper)

        def unweight_value(_att, _value, _tree_df) -> pd.Series:
            """
            Unweights the value based on the attribute type.

            :param _att: Attribute type (e.g., 'dens', 'ba', 'cfl', etc.).
            :param _value: Series of values to unweight.
            :param _tree_df: DataFrame containing tree data.
            :return: Unweighted Series of values.
            """
            if _att in attribute_weighting_dict.keys():
                field_name = f'tree_{attribute_weighting_dict.get(_att, 'dens')}_ha'
                denom = _tree_df.groupby('ParentGlobalID')[field_name].sum()
            elif _att == 'cbd':
                field_name = f'tree_{attribute_weighting_dict['crwn_dpth']}_ha'
                denom = (_tree_df.groupby('ParentGlobalID')['tree_crwn_dpth_wtd'].sum() /
                         _tree_df.groupby('ParentGlobalID')[field_name].sum())
            else:
                denom = 1
            return _value / denom

        # Initialize a list of keep columns for the final master DataFrame
        keep_columns = []

        for att, att_dict in stand_summary_params.items():
            summary_list = att_dict.get('summary', [])
            metrics = att_dict.get('metrics', [])
            units = att_dict.get('units', '')
            if units:
                units = f'_{units}'
            classes = att_dict.get('classes', {})

            # Get the column name extension based on the attribute type
            if att in ['dens', 'ba']:
                ext = '_ha'
            elif att in ['cfl', 'foliage', 'branches', 'wood', 'bark']:
                ext = '_cnbe_ha'
            elif att in attribute_weighting_dict.keys():
                ext = '_wtd'
            else:
                ext = ''

            new_columns = {}

            # Process all summary permutations
            summary_permutations = get_permutations(summary_list)
            for summary in summary_permutations:
                summary_mask = get_summary_mask(tree_df, summary)
                if att != 'cbd':
                    for metric in metrics:
                        unweight = False
                        if metric == 'sum':
                            value = tree_df[summary_mask].groupby('ParentGlobalID')[f'tree_{att}{ext}'].sum()
                        elif metric == 'min':
                            if att in attribute_weighting_dict.keys():
                                value = tree_df[summary_mask].groupby('ParentGlobalID')[f'tree_{att}'].min()
                            else:
                                value = tree_df[summary_mask].groupby('ParentGlobalID')[f'tree_{att}{ext}'].min()
                        elif metric == 'max':
                            if att in attribute_weighting_dict.keys():
                                value = tree_df[summary_mask].groupby('ParentGlobalID')[f'tree_{att}'].max()
                            else:
                                value = tree_df[summary_mask].groupby('ParentGlobalID')[f'tree_{att}{ext}'].max()
                        elif metric == 'mean':
                            value = tree_df[summary_mask].groupby('ParentGlobalID')[f'tree_{att}{ext}'].sum()
                            unweight = True
                        else:
                            continue

                        if unweight:
                            # Unweight values
                            value = unweight_value(att, value, tree_df[summary_mask])

                        # Assign data to new column
                        colname = f'stand_{att}{units}_{summary}_{metric}'.replace('_total', '')
                        new_columns[colname] = df.GlobalID.map(value)
                else:
                    value = (
                            tree_df[summary_mask].groupby('ParentGlobalID')[f'tree_cfl_cnbe_ha'].sum() /
                            tree_df[summary_mask].groupby('ParentGlobalID')[f'tree_crwn_dpth_wtd'].sum()
                    )
                    # Unweight values
                    value = unweight_value(att, value, tree_df[summary_mask])

                    # Assign data to new column
                    colname = f'stand_{att}{units}_{summary}'.replace('_total', '')
                    new_columns[colname] = df.GlobalID.map(value)

                # Process class cutoffs if present
                for class_var, cutoffs in classes.items():
                    # Bounds start at first value in cutoffs
                    bounds = cutoffs
                    for i in range(len(bounds)):
                        lower = bounds[i]
                        upper = bounds[i + 1] if i + 1 < len(bounds) else None
                        class_label = f'{class_var}{lower}plus' if upper is None else f'{class_var}{lower}-{upper}'
                        class_mask = get_class_mask(tree_df, class_var, lower, upper)
                        mask = summary_mask & class_mask
                        if att != 'cbd':
                            for metric in metrics:
                                unweight = False
                                if metric == 'sum':
                                    value = tree_df[mask].groupby('ParentGlobalID')[f'tree_{att}{ext}'].sum()
                                elif metric == 'min':
                                    if att in attribute_weighting_dict.keys():
                                        value = tree_df[mask].groupby('ParentGlobalID')[f'tree_{att}'].min()
                                    else:
                                        value = tree_df[mask].groupby('ParentGlobalID')[f'tree_{att}{ext}'].min()
                                elif metric == 'max':
                                    if att in attribute_weighting_dict.keys():
                                        value = tree_df[mask].groupby('ParentGlobalID')[f'tree_{att}'].max()
                                    else:
                                        value = tree_df[mask].groupby('ParentGlobalID')[f'tree_{att}{ext}'].max()
                                elif metric == 'mean':
                                    value = tree_df[mask].groupby('ParentGlobalID')[f'tree_{att}{ext}'].sum()
                                    unweight = True
                                else:
                                    continue

                                if unweight:
                                    # Unweight values
                                    value = unweight_value(att, value, tree_df[mask])

                                # Assign data to new column
                                colname = f'stand_{att}{units}_{summary}_{class_label}_{metric}'.replace('_total', '')
                                new_columns[colname] = df.GlobalID.map(value)
                        else:
                            value = (
                                    tree_df[mask].groupby('ParentGlobalID')[f'tree_cfl_cnbe_ha'].sum() /
                                    tree_df[mask].groupby('ParentGlobalID')[f'tree_crwn_dpth_wtd'].sum()
                            )
                            # Unweight values
                            value = unweight_value(att, value, tree_df[mask])

                            # Assign data to new column
                            colname = f'stand_{att}{units}_{summary}_{class_label}'.replace('_total', '')
                            new_columns[colname] = df.GlobalID.map(value)

            if new_columns:
                df = pd.concat([df, pd.DataFrame(new_columns, index=df.index)], axis=1)
                # Add the stand summary columns to the keep list
                keep_columns.extend(new_columns.keys())

        return df, keep_columns


def _calc_stand_composition(df: pd.DataFrame, tree_df: pd.DataFrame) -> tuple[pd.DataFrame, list]:
    """
    Calculates stand composition metrics for each plot based on tree basal area.

    For each plot, this function determines the top 6 species by their percentage of total basal area,
    both for live trees only and for all woody trees (live and dead). It adds columns to the plot-level
    DataFrame for the species codes and their corresponding basal area percentages, as well as a summary
    string for each stand. Returns the updated DataFrame and a list of new column names.

    :param df: DataFrame containing plot-level data, including 'GlobalID' and 'unique_id'.
    :param tree_df: DataFrame containing individual tree data, including 'tree_status', 'tree_ba_ha', and 'ParentGlobalID'.
    :return: Tuple of (updated plot-level DataFrame, list of new column names).
    """
    print('\tCalculating stand composition metrics')
    keep_columns = []

    # Map from GlobalID to unique_id for joining
    unique_id_map = df.set_index('GlobalID')['unique_id'].to_dict()

    # Calculate composition for live trees only, then for all woody trees (live + dead)
    for status in [['L'], ['L', 'D']]:
        # Mask for trees with the given status
        tree_mask = tree_df['tree_status'].isin(status)
        # Aggregate basal area by plot and species
        agg = (
            tree_df.loc[tree_mask]
            .groupby(['ParentGlobalID', 'tree_species'], as_index=False)['tree_ba_ha']
            .sum()
            .rename(columns={'tree_species': 'SPECIES_CD', 'tree_ba_ha': 'species_ba'})
        )
        # Remove zero-BA species
        agg = agg[agg['species_ba'] > 0]
        # Add unique_id for joining to plot-level data
        agg['unique_id'] = agg['ParentGlobalID'].map(unique_id_map)
        agg = agg.drop(columns=['ParentGlobalID'])

        # Sum species BA by unique_id and species (in case of duplicates)
        agg = (
            agg.groupby(['unique_id', 'SPECIES_CD'], as_index=False)['species_ba']
            .sum()
        )

        # Get total stand basal area for each plot
        stand_ba = (
            tree_df.loc[tree_mask]
            .groupby('ParentGlobalID')['tree_ba_ha']
            .sum()
            .rename(unique_id_map)
        )
        agg['stand_ba'] = agg['unique_id'].map(stand_ba)
        agg = agg[agg['stand_ba'] > 0]

        # Calculate percent of stand BA for each species
        agg['SPECIES_PCT'] = (100 * agg['species_ba'] / agg['stand_ba']).round(1)
        agg = agg[agg['species_ba'] > 0]

        # Keep only the top 6 species by BA percent per stand
        agg = (
            agg.sort_values(['unique_id', 'SPECIES_PCT'], ascending=[True, False])
            .groupby('unique_id')
            .head(6)
            .reset_index(drop=True)
        )
        # Assign rank and column names for pivoting
        agg['rank'] = agg.groupby('unique_id')['SPECIES_PCT'].rank('first', ascending=False).astype(int)
        agg['code'] = 'SPECIES_CD_' + agg['rank'].astype(str)
        agg['percent'] = 'SPECIES_PCT_' + agg['rank'].astype(str)

        # Pivot to wide format for species codes and percentages
        spp_code_df = agg.pivot(index='unique_id', columns='code', values='SPECIES_CD').reset_index()
        spp_pct_df = agg.pivot(index='unique_id', columns='percent', values='SPECIES_PCT').reset_index()

        spp_code_cols = [f'SPECIES_CD_{x}' for x in range(1, 7)]
        spp_pct_cols = [f'SPECIES_PCT_{x}' for x in range(1, 7)]

        # For live trees, add columns for top 6 species codes and percentages
        if status == ['L']:
            for col, df_src in [(spp_code_cols, spp_code_df), (spp_pct_cols, spp_pct_df)]:
                map_dict = df_src.set_index('unique_id').to_dict()
                for c in col:
                    if c in df_src.columns:
                        df[c] = df['unique_id'].map(map_dict[c])
                        if df_src is spp_pct_df:
                            df[c] = df[c].fillna(0)
                    else:
                        df[c] = 0 if df_src is spp_pct_df else np.nan
                    keep_columns.append(c)

        # Create a summary string column for each stand (live or woody)
        merged = pd.merge(spp_code_df, spp_pct_df, on='unique_id', how='outer')
        def spp_tuple_str(row):
            # Build a string like "SP1:40.0, SP2:30.0, ..."
            pairs = [
                f"{row.get(f'SPECIES_CD_{i}')}:{row.get(f'SPECIES_PCT_{i}')}"
                for i in range(1, 7)
                if pd.notnull(row.get(f'SPECIES_CD_{i}')) and pd.notnull(row.get(f'SPECIES_PCT_{i}')) and row.get(f'SPECIES_PCT_{i}') > 0
            ]
            return ', '.join(pairs) if pairs else None

        spp_comp_col_name = 'stand_spp_comp_live' if status == ['L'] else 'stand_spp_comp_woody'
        df[spp_comp_col_name] = df['unique_id'].map(
            merged.set_index('unique_id').apply(spp_tuple_str, axis=1)
        )
        keep_columns.append(spp_comp_col_name)

    return df, keep_columns


def _calc_tree_basal_area(tree_df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate the basal area and weighted basal area for each tree.

    :param tree_df: DataFrame containing individual tree data, including DBH and density.
    :return: DataFrame with 'tree_ba' (basal area in m^2) and 'tree_ba_ha' (density-weighted basal area) columns added.
    """
    print('\tCalculating tree basal area (m^2) and basal area per hectare (m^2/ha)')
    # Calculate basal area (m^2) for each tree: BA = π * (DBH/200)^2
    tree_df['tree_ba'] = np.pi * np.power(tree_df.tree_dbh / 200, 2)
    # Calculate weighted basal area: tree density * basal area
    tree_df['tree_ba_ha'] = tree_df['tree_dens_ha'] * tree_df['tree_ba']

    return tree_df


def _calc_tree_biomass(tree_df: pd.DataFrame, tree_params_df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculates tree component biomass (wood, bark, branches, foliage) per hectare using CNBE allometric equations,
    accounting for decay class and live/dead status.

    For each species and component, applies the appropriate decay reduction factor and allometric parameters.
    Uses measured height for live/less decayed trees, and modeled height for dead/more decayed trees.

    :param tree_df: DataFrame with tree attributes, including species, DBH, height, density, and decay class.
    :param tree_params_df: DataFrame with species-specific allometric parameters.
    :return: Updated tree_df with biomass columns for each component.
    """
    print('\tCalculating tree biomass (wood, bark, branches, foliage) using '
          'the Canadian National Biomass Equations (CNBE)')
    # Initialize biomass columns to zero
    for col in ['tree_wood_cnbe_ha', 'tree_bark_cnbe_ha', 'tree_branches_cnbe_ha', 'tree_foliage_cnbe_ha']:
        tree_df[col] = 0.0

    spp_list = [n for n in tree_df['tree_species'].unique() if not pd.isnull(n)]

    # Assign combined decay class (conifer or broadleaf) to each tree
    tree_df['tree_dcy_class'] = np.where(
        tree_df.tree_type == 'conifer',
        tree_df.tree_dcy_class_cnfr,
        np.where(tree_df.tree_type == 'broadleaf', tree_df.tree_dcy_class_brdlf, np.nan)
    )

    for spp in spp_list:
        # Select decay class dictionary based on species type
        decay_dict = tree_conifer_decay_class_dict if spp in conifer_list else tree_broadleaf_decay_class_dict
        for component in tree_component_list:
            comp_idx = tree_component_index_dict[component]
            param1 = tree_params_df.loc[spp, f'BIOMASS_CNBE_DBH-HT_B{component}1']
            param2 = tree_params_df.loc[spp, f'BIOMASS_CNBE_DBH-HT_B{component}2']
            param3 = tree_params_df.loc[spp, f'BIOMASS_CNBE_DBH-HT_B{component}3']

            # Masks for live/less decayed and dead/more decayed trees
            mask_live = (
                (tree_df.tree_species == spp) &
                (tree_df.tree_dcy_class > 0) &
                ((tree_df.tree_dcy_class_cnfr < 6) | (tree_df.tree_dcy_class_brdlf < 5)) &
                (tree_df.tree_dbh > 0) &
                (tree_df.tree_ht > 0)
            )
            mask_dead = (
                (tree_df.tree_species == spp) &
                (tree_df.tree_dcy_class > 0) &
                ((tree_df.tree_dcy_class_cnfr >= 6) | (tree_df.tree_dcy_class_brdlf >= 5)) &
                (tree_df.tree_dbh > 0) &
                (tree_df.tree_ht > 0)
            )

            # Calculate biomass for live/less decayed trees
            if mask_live.any():
                tree_df.loc[mask_live, f'tree_{component}_cnbe_ha'] = (
                    tree_df.loc[mask_live, 'tree_dens_ha'] *
                    tree_df.loc[mask_live, 'tree_dcy_class'].map(decay_dict).apply(lambda x: x[comp_idx]) *
                    param1 *
                    tree_df.loc[mask_live, 'tree_dbh'] ** param2 *
                    tree_df.loc[mask_live, 'tree_ht'] ** param3
                ) / 10000

            # Calculate biomass for dead/more decayed trees (using modeled height)
            if mask_dead.any():
                tree_df.loc[mask_dead, f'tree_{component}_cnbe_ha'] = (
                    tree_df.loc[mask_dead, 'tree_dens_ha'] *
                    tree_df.loc[mask_dead, 'tree_dcy_class'].map(decay_dict).apply(lambda x: x[comp_idx]) *
                    param1 *
                    tree_df.loc[mask_dead, 'tree_dbh'] ** param2 *
                    tree_df.loc[mask_dead, 'tree_ht_modeled'] ** param3
                ) / 10000

    return tree_df


def _calc_tree_cbh(tree_df: pd.DataFrame) -> pd.DataFrame:
    """
    Converts crown base height (CBH) to NaN for trees with CBH of 99.

    :param tree_df: DataFrame containing individual tree data.
    :return: Updated DataFrame with revised 'tree_cbh' column.
    """
    print('\tCleaning tree CBH values')
    mask = (tree_df['tree_cbh'] == 99) & (tree_df['tree_status'] == 'L')

    # Set CBH for live trees to NaN where CBH is 99
    tree_df.loc[mask, 'tree_cbh'] = np.nan

    # Append message to tree note if CBH was set to NaN
    if 'tree_note' not in tree_df.columns:
        tree_df['tree_note'] = ''
    tree_df.loc[mask, 'tree_note'] = (
        tree_df.loc[mask, 'tree_note'].astype(str) +
        ' [Fuel Analyst Note] Crown base height entered as 99. Value set to NaN; '
    )

    return tree_df


def _calc_tree_crown_depth(tree_df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculates the crown depth for each tree and adds it as a new column 'tree_crwn_dpth'.

    Crown depth is defined as the difference between tree height and crown base height (CBH)
    for live trees, where height exceeds CBH. For all other cases, the value is set to NaN.

    :param tree_df: DataFrame containing individual tree data, including 'tree_status', 'tree_ht', and 'tree_cbh'.
    :return: DataFrame with a new 'tree_crwn_dpth' column.
    """
    print('\tCalculating tree crown depths')
    # Calculate crown depth for live trees where height > CBH; otherwise, set as NaN
    tree_df['tree_crwn_dpth'] = np.where(
        (tree_df['tree_status'] == 'L') & (tree_df['tree_ht'] > tree_df['tree_cbh']),
        tree_df['tree_ht'] - tree_df['tree_cbh'],
        np.nan
    )
    return tree_df


def _calc_tree_crown_fuels(tree_df: pd.DataFrame, tree_params_df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculates canopy fuel load and bulk density for live conifer trees using allometric equations.

    For each conifer species present, computes:

    Crown fuel load (CFL) using Canadian National Biomass Equations (CNBE)
        - Equations per Ung et al. (2008) and Lambert et al. (2005), using DBH and height.

    Canopy bulk density (CBD), calculated as CFL divided by crown depth.

    Initializes output columns to zero and only processes live trees with valid DBH, height, and density.
    Results are stored in new columns for each tree.

    :param tree_df: DataFrame with individual tree data, including DBH, height, and status.
    :param tree_params_df: DataFrame with species-specific allometric parameters.
    :return: Updated tree_df with canopy fuel and bulk density columns.
    """
    print('\tCalculating tree crown fuels (CFL and CBD) using the Canadian National Biomass Equations (CNBE)')
    # Initialize columns
    for col in ['tree_cfl_cnbe_ha', 'tree_cbd_cnbe_ha']:
        tree_df[col] = 0.0

    # Process all species present in the DataFrame
    spp_set = set(tree_df['tree_species'].dropna())
    for spp in spp_set:
        # Mask for live trees of the current species with valid DBH and height
        spp_mask = (
                (tree_df['tree_species'] == spp) &
                (tree_df['tree_status'] == 'L') &
                (tree_df['tree_dbh'] > 0) &
                (tree_df['tree_ht'] > 0)
        )

        # Use existing foliage biomass as CFL
        tree_df.loc[spp_mask, 'tree_cfl_cnbe_ha'] = tree_df.loc[spp_mask, 'tree_foliage_cnbe_ha']

        # Calculate individual tree (per ha) CBD (CFL / crown depth)
        cbd_mask = spp_mask & (tree_df['tree_crwn_dpth'] > 0)
        tree_df.loc[cbd_mask, 'tree_cbd_cnbe_ha'] = (
                tree_df.loc[cbd_mask, 'tree_cfl_cnbe_ha'] / tree_df.loc[cbd_mask, 'tree_crwn_dpth']
        )

    return tree_df


def _calc_tree_dbh_classes(tree_df: pd.DataFrame) -> pd.DataFrame:
    """
    Assigns DBH (Diameter at Breast Height) class labels to each tree based on its DBH value.

    Classes:
        - '1D': DBH >= 30 cm
        - '1M': 12.5 cm <= DBH < 30 cm
        - '2' : 7.5 cm <= DBH < 12.5 cm
        - '3' : DBH < 7.5 cm

    :param tree_df: DataFrame containing individual tree data with a 'tree_dbh' column.
    :return: DataFrame with a new 'tree_dbh_class' column.
    """
    print('\tCalculating tree DBH classes')
    # Assign DBH class based on DBH value
    tree_df['tree_dbh_class_bc'] = np.select(
        condlist=[
            (tree_df.tree_dbh >= 30),
            ((tree_df.tree_dbh >= 12.5) & (tree_df.tree_dbh < 30)),
            ((tree_df.tree_dbh >= 7.5) & (tree_df.tree_dbh < 12.5)),
            (tree_df.tree_dbh < 7.5),
        ],
        choicelist=['1D', '1M', '2', '3'],
        default='')

    return tree_df


def _calc_tree_decay_classes(tree_df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate the combined decay class for each tree based on conifer and broadleaf decay classes.

    The function sums the values of 'tree_dcy_class_cnfr' and 'tree_dcy_class_brdlf' for each row.
    If the sum is 0, it is replaced with NaN, indicating no decay class is assigned.

    :param tree_df: DataFrame containing individual tree data with conifer and broadleaf decay class columns.
    :return: DataFrame with a new 'tree_dcy_class' column representing the combined decay class.
    """
    print('\tCalculating tree decay classes')
    # Calculate decay class for conifer and broadleaf trees by summing their respective columns
    # Replace 0 with NaN to indicate missing or unassigned decay class
    tree_df['tree_dcy_class'] = tree_df[
        ['tree_dcy_class_cnfr', 'tree_dcy_class_brdlf']
    ].sum(axis=1).replace(0, np.nan)

    return tree_df


def _calc_tree_density(df: pd.DataFrame, tree_df: pd.DataFrame) -> pd.DataFrame:
    """
    Assigns tree density multipliers to each tree based on its DBH class.

    For each tree:
    - If DBH >= 12.5 cm, use the large tree multiplier.
    - If 5 cm <= DBH < 12.5 cm, use the small tree multiplier.
    - If DBH < 5 cm, use the sapling multiplier.

    :param df: DataFrame containing plot-level multipliers.
    :param tree_df: DataFrame containing individual tree data, including DBH.
    :return: Updated tree_df with a new 'tree_dens' column for tree density multiplier.
    """
    print('\tCalculating tree density (per hectare)')
    # Assign density multiplier based on DBH class
    tree_df['tree_dens_ha'] = np.where(
        tree_df.tree_dbh >= 12.5,
        tree_df.ParentGlobalID.map(df.set_index('GlobalID')['plot_lgtree_mult'].to_dict()),
        np.where(
            (tree_df.tree_dbh >= 5) & (tree_df.tree_dbh < 12.5),
            tree_df.ParentGlobalID.map(df.set_index('GlobalID')['plot_smtree_mult'].to_dict()),
            tree_df.ParentGlobalID.map(df.set_index('GlobalID')['plot_sapling_mult'].to_dict()),
        )
    )

    # Multiply the density by the tree count to get total density per hectare
    tree_df['tree_dens_ha'] *= tree_df['tree_count']

    return tree_df


def _calc_tree_fire_attributes(tree_df: pd.DataFrame, surface_fire_intensity_model: str = 'Byram') -> pd.DataFrame:
    """
    Calculates fire-related attributes for each tree in the DataFrame.

    This function computes:
    - Flame length based on bark char height.
    - Fireline intensity (FLI) based on tree density and basal area.
        - Byram (1959) or Thomas (1963) model for surface fire intensity.
        - Butler's model for crown fire intensity.

    :param tree_df: DataFrame containing individual tree data, including density, basal area, crown base height,
                    dead crown base height, and fuel bed height.
    :param surface_fire_intensity_model: Model to use for calculating surface fireline intensity (default is 'Byram').
        Options: ['Byram', 'Thomas']
    :return: Updated DataFrame with new columns for FLI, CFP, and CBD.
    """
    print('\tCalculating fire metrics (Fireline Intensity, Flame Length)')

    # ### ESTIMATE FLAME LENGTH ###
    # Invert the FOFEM char height equation to solve for flame length
    tree_df['tree_flame_length'] = tree_df['tree_bark_char_high'] * 1.8

    # ### CALCULATE VARIOUS FIRELINE INTENSITY OPTIONS ###
    if surface_fire_intensity_model == 'Byram':
        # Use the Byram (1959) flame length model to estimate fireline intensity (kW/m)
        surface_model = (tree_df['tree_flame_length'] / 0.0775) ** (1 / 0.46)
    elif surface_fire_intensity_model == 'Thomas':
        # Use the Thomas (1963) flame length model to estimate fireline intensity (kW/m)
        surface_model = (tree_df['tree_flame_length'] / 0.026700) ** (3 / 2)
    else:
        print('Invalid surface fireline intensity model specified. Using Byram (1959) as default.')
        # Use the Byram (1959) flame length model to estimate fireline intensity (kW/m)
        surface_model = (tree_df['tree_flame_length'] / 0.0775) ** (1 / 0.46)

    # Use the Butler et al. (2004) crown fire flame length model to estimate crown fireline intensity
    # (must add value to average stand height)
    crown_model = (tree_df['tree_flame_length'] / 0.017500) ** (3 / 2)

    # ### ESTIMATE FIRELINE INTENSITY ###
    # Set bark char heights of 444 to the tree height
    full_ht_mask = tree_df['tree_bark_char_high'] == 444
    # Estimate fireline intensity based on the full_ht_mask
    tree_df['tree_fire_intensity'] = np.where(full_ht_mask, crown_model, surface_model)

    return tree_df


def _calc_tree_fofem_attributes(tree_df: pd.DataFrame, tree_params_df: pd.DataFrame) -> pd.DataFrame:
    """
    Assigns FOFEM species codes and calculates bark thickness for each tree,
    and assigns FOFEM foliage and branch biomass.

    - Maps each tree's species to its FOFEM code using the parameter DataFrame.
    - Calculates bark thickness as DBH multiplied by the species-specific bark thickness factor,
      only if tree density is non-negative.

    :param tree_df: DataFrame with individual tree data.
    :param tree_params_df: DataFrame with species parameters, including 'FOFEM_sppCD' and 'FOFEM_BrkThck_Vsp'.
    :return: Updated DataFrame with 'tree_species_fofem' and 'tree_bark_thick' columns.
    """
    # Create mapping dictionaries for FOFEM species code and bark thickness factor
    spp_map = tree_params_df['FOFEM_sppCD'].to_dict()
    bark_map = tree_params_df['FOFEM_BrkThck_Vsp'].to_dict()

    # Map FOFEM species code
    tree_df['tree_species_fofem'] = tree_df['tree_species'].map(spp_map)

    # Calculate bark thickness where tree density is valid, else NaN
    tree_df['tree_bark_thick'] = np.where(
        tree_df['tree_dens_ha'] >= 0,
        tree_df['tree_dbh'] * tree_df['tree_species'].map(bark_map),
        np.nan
    )

    # Create masks for foliage and branch biomass assignments
    # Foliage = live conifers only
    foliage_map = tree_df['tree_status'].eq('L') & tree_df['tree_type'].eq('conifer')
    # Branches = dead broadleaf and all conifers
    branch_map = (tree_df['tree_type'].eq('conifer') |
                  (tree_df['tree_status'].eq('D') & tree_df['tree_type'].eq('broadleaf')))

    # Assign foliage and branch biomass to FOFEM columns
    tree_df['tree_foliage_fofem'] = 0
    tree_df['tree_foliage_fofem'] = tree_df[foliage_map]['tree_foliage_cnbe_ha']
    tree_df['tree_branches_fofem'] = 0
    tree_df['tree_branches_fofem'] = tree_df[branch_map]['tree_branches_cnbe_ha']

    return tree_df


def _calc_tree_fsg(tree_df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculates the fuel strata gap (FSG) for each tree in the DataFrame.

    The FSG is the vertical distance between the top of the surface fuel bed and the base of the tree crown.
    The calculation depends on tree status (live or dead), crown base height (CBH), dead crown base height (DCBH),
    and the height of the fuel bed. The result is stored in the 'tree_fsg' column.

    Rules:
        - If the tree is dead or has no fuel bed height, FSG is NaN.
        - For live trees:
            - If CBH < DCBH and (CBH - fuel bed height) > 0, FSG = CBH - fuel bed height.
            - If DCBH < CBH and (DCBH - fuel bed height) > 0, FSG = DCBH - fuel bed height.
            - If the fuel bed is above either CBH or DCBH, FSG = 0.

    :param tree_df: DataFrame containing tree attributes, including status, CBH, DCBH, and fuel bed height.
    :return: Updated DataFrame with a new 'tree_fsg' column.
    """
    print('\tCalculating tree fuel strata gap (FSG)')
    # Mask for dead trees or missing fuel bed height
    is_dead_or_no_fuel_bed = (tree_df['tree_status'] == 'D') | (tree_df['tree_fuel_bed_ht'].isnull())

    # Mask for live trees where CBH < DCBH and CBH is above the fuel bed
    cbh_lt_dcbh = (
        (tree_df['tree_status'] == 'L') &
        (tree_df['tree_cbh'] < tree_df['tree_dcbh']) &
        ((tree_df['tree_cbh'] - tree_df['tree_fuel_bed_ht']) > 0)
    )

    # Mask for live trees where DCBH < CBH and DCBH is above the fuel bed
    dcbh_lt_cbh = (
        (tree_df['tree_status'] == 'L') &
        (tree_df['tree_dcbh'] < tree_df['tree_cbh']) &
        ((tree_df['tree_dcbh'] - tree_df['tree_fuel_bed_ht']) > 0)
    )

    # Mask for live trees where the fuel bed is above either CBH or DCBH
    fuel_bed_above_crown = (
        (tree_df['tree_status'] == 'L') &
        (
            (tree_df['tree_fuel_bed_ht'] > tree_df['tree_cbh']) |
            (tree_df['tree_fuel_bed_ht'] > tree_df['tree_dcbh'])
        )
    )

    # Assign FSG values based on the above conditions
    tree_df['tree_fsg'] = np.select(
        condlist=[is_dead_or_no_fuel_bed, cbh_lt_dcbh, dcbh_lt_cbh, fuel_bed_above_crown],
        choicelist=[
            np.nan,
            tree_df['tree_cbh'] - tree_df['tree_fuel_bed_ht'],
            tree_df['tree_dcbh'] - tree_df['tree_fuel_bed_ht'],
            0
        ]
    )
    return tree_df


def _calc_tree_missing_heights(tree_df: pd.DataFrame, tree_params_df: pd.DataFrame) -> pd.DataFrame:
    """
    Model and assign tree heights for trees in the DataFrame using the Temesgen height model.
    Heights are estimated for live trees missing height values and for all dead trees.

    :param tree_df: DataFrame containing individual tree data.
    :param tree_params_df: DataFrame containing tree species parameters for height modeling.
    :return: Updated DataFrame with modeled tree heights.
    """
    print('\tCalculating missing tree heignts')
    # Function to model height using Temesgen Model 2 for a given row
    def model_height(row):
        if row['tree_species'] in spp_set:
            return _get_temesgen_tree_height(2, tree_params_df, row['tree_species'], row['tree_dbh'])
        return np.nan

    # Set of valid species codes present in the data
    spp_set = set(tree_df['tree_species'].dropna())

    # Mask for trees missing heights (decay class conifer < 6 or broadleaf < 5, and valid DBH)
    mask_missing = (
        (tree_df['tree_dens_ha'] > 0) &
        (
            (tree_df['tree_dcy_class_cnfr'] < 6) |
            (tree_df['tree_dcy_class_brdlf'] < 5)
        ) &
        tree_df['tree_ht'].isnull() &
        tree_df['tree_dbh'].notnull()
    )
    # Assign modeled heights to trees missing height values
    tree_df.loc[mask_missing, 'tree_ht_modeled'] = tree_df[mask_missing].apply(model_height, axis=1)

    # Assign modeled heights to dead trees with missing height values
    tree_df.loc[mask_missing, 'tree_ht'] = tree_df.loc[mask_missing, 'tree_ht_modeled']

    # Mask for dead trees (decay class conifer >= 6 or broadleaf >= 5, and valid DBH)
    mask_dead = (
        (
            (tree_df['tree_dcy_class_cnfr'] >= 6) |
            (tree_df['tree_dcy_class_brdlf'] >= 5)
        ) &
        tree_df['tree_dbh'].notnull()
    )
    # Initialize modeled height column for dead trees
    tree_df['tree_ht_modeled'] = 0.0
    # Assign modeled heights to dead trees
    tree_df.loc[mask_dead, 'tree_ht_modeled'] = tree_df[mask_dead].apply(model_height, axis=1).astype(float)

    return tree_df


def _calc_tree_type(tree_df: pd.DataFrame, tree_params_df: pd.DataFrame) -> pd.DataFrame:
    """
    Assigns tree type (e.g., conifer or broadleaf) to each tree in the DataFrame
    based on species codes and a parameter DataFrame.

    :param tree_df: DataFrame containing individual tree data, including species codes.
    :param tree_params_df: DataFrame containing species parameters, including 'TreeType'.
    :return: Updated tree_df with a new 'tree_type' column.
    """
    print('\tCalculating tree types (conifer or broadleaf)')
    # Create a mapping from species code to tree type
    tree_type_map = tree_params_df['TreeType'].to_dict()
    # Map tree species to their type and assign to new column
    tree_df['tree_type'] = tree_df['tree_species'].map(tree_type_map)

    return tree_df


def _calc_tree_weighted_attributes(tree_df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate weighted attributes for each tree based on its density and basal area.

    This function computes the weighted DBH, height, crown base height (CBH), dead crown base height (DCBH),
    and fuel bed height for each tree, using the tree's density and basal area.

    :param tree_df: DataFrame containing individual tree data, including DBH, height, CBH, DCBH, and fuel bed height.
    :return: Updated DataFrame with new columns for weighted attributes.
    """
    print('\tCalculating tree weighted attributes')
    # Initialize weighted attribute columns
    attribute_list = list(attribute_weighting_dict.keys())

    for att in attribute_list:
        # Get the column names for the attribute and its weight multiplier
        att_col = f'tree_{att}'
        wtd_col = f'tree_{att}_wtd'
        att_wt_mult = attribute_weighting_dict.get(att, 'dens')

        # Calculate the weighted attribute
        tree_df[wtd_col] = tree_df[att_col] * tree_df[f'tree_{att_wt_mult}_ha']

    return tree_df


def _gen_master_tree_df(df: pd.DataFrame, tree_df: pd.DataFrame) -> pd.DataFrame:
    """
    Generate a master tree DataFrame with selected and renamed columns for export.

    - Maps group IDs to unique IDs.
    - Converts tree height class codes to descriptive labels.
    - Selects and renames relevant columns.
    - Filters out trees with non-positive live density.

    :param df: DataFrame containing plot-level data with 'group' and 'unique_id' columns.
    :param tree_df: DataFrame containing individual tree data.
    :return: Master tree DataFrame ready for export.
    """
    # Map group to unique_id
    tree_df['unique_id'] = tree_df['ParentGlobalID'].map(df.set_index('GlobalID')['unique_id'].to_dict())

    # Map tree height class codes to labels
    ht_class_dict = {1: 'D', 2: 'CD', 3: 'I', 4: 'S'}
    tree_df['tree_ht_class_cd'] = tree_df['tree_ht_class'].map(ht_class_dict)

    # Calculate live tree density per hectare
    live_mask = tree_df['tree_status'] == 'L'
    tree_df['tree_dens_live_ha'] = np.where(live_mask, tree_df['tree_dens_ha'], 0)

    # Calculate live basal area per hectare
    tree_df['tree_ba_live_ha'] = np.where(live_mask, tree_df['tree_ba_ha'], 0)

    # Columns to keep and their new names
    tree_cols = [
        'unique_id', 'tree_species', 'tree_species_fofem', 'tree_dcy_class_cnfr', 'tree_dcy_class_brdlf',
        'tree_ht_class_cd', 'tree_dens_live_ha', 'tree_dbh', 'tree_ba_live_ha',
        'tree_ht', 'tree_crwn_dpth', 'tree_bark_thick'
    ]
    tree_cols_dict = {
        'tree_species': 'spp',
        'tree_species_fofem': 'spp_fofem',
        'tree_dcy_class_cnfr': 'decay_cnfr',
        'tree_dcy_class_brdlf': 'decay_brdlf',
        'tree_ht_class_cd': 'crown_class',
        'tree_dens_live_ha': 'dens_live_ha',
        'tree_dbh': 'dbh',
        'tree_ba_live_ha': 'ba_live_ha',
        'tree_ht': 'ht',
        'tree_crwn_dpth': 'crown_depth',
        'tree_bark_thick': 'bark_thick'
    }

    # Select, filter, and rename columns
    temp_df = tree_df.loc[tree_df['tree_dens_live_ha'] > 0, tree_cols].rename(columns=tree_cols_dict)

    # Return the master DataFrame
    return temp_df.reset_index(drop=True)


def _get_temesgen_tree_height(model: int,
                              param_df: pd.DataFrame,
                              spp: str,
                              dbh: float,
                              bal: float = None,
                              sph=None,
                              ba=None):
    """
    Calculates tree height using the Temesgen height model (Model 2 or 7).

    :param model: Integer, 2 or 7, specifying which Temesgen model to use.
    :param param_df: DataFrame containing species-specific model parameters.
    :param spp: Species code (string) for the target ttree.
    :param dbh: Diameter at Breast Height of the target tree (cm).
    :param bal: Total basal area of trees larger than the target tree in stand (m^2/ha), required for Model 7.
    :param sph: Total number of trees per hectare in stand, required for Model 7.
    :param ba: Total basal area per hectare in stand (m^2/ha), required for Model 7.
    :return: Estimated tree height (m) or np.nan if 'model' is invalid.
    """
    if model == 2:
        # Temesgen Model 2: Height = 1.3 + a * (1 - exp(-b * dbh^c))
        return 1.3 + param_df.loc[spp, 'Temesgen_M2a'] * \
               (1 - np.exp(-param_df.loc[spp, 'Temesgen_M2b'] * np.power(dbh, param_df.loc[spp, 'Temesgen_M2c'])))
    elif model == 7:
        # Temesgen Model 7: Height = 1.3 + a * (1 - exp(-b * dbh^c))
        # a and c are functions of bal, sph, and ba
        a = param_df.loc[spp, 'Temesgen_M7a1'] + \
            param_df.loc[spp, 'Temesgen_M7a2'] * bal + \
            param_df.loc[spp, 'Temesgen_M7a3'] * sph + \
            param_df.loc[spp, 'Temesgen_M7a4'] * ba
        c = param_df.loc[spp, 'Temesgen_M7a5'] + \
            param_df.loc[spp, 'Temesgen_M7a6'] * bal
        return 1.3 + a * (1 - np.exp(-param_df.loc[spp, 'Temesgen_M7b'] * np.power(dbh, c)))
    else:
        # If incorrect model number entered, return np.nan
        return np.nan


def _merge_saplings_to_trees(tree_df: pd.DataFrame, sapling_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Calculate sapling density for each plot based on the number of saplings per hectare.

    :param tree_df: DataFrame containing individual tree data.
    :param sapling_df: DataFrame containing small sapling data.
    :return: Updated tree_df with a new 'tree_sapling_dens' column for sapling density.
    """
    print('\tMerging sapling data into tree DataFrame')
    # Assign a default value of 1 to all trees in the tree DataFrame
    tree_df['tree_count'] = 1

    # Ensure all DBH values are > 0
    sapling_df['sapling_live_dbh'] = sapling_df['sapling_live_dbh'].replace(0, 0.1)
    sapling_df['sapling_dead_dbh'] = sapling_df['sapling_dead_dbh'].replace(0, 0.1)

    # For each row in sapling_df, create new rows for live and dead saplings in tree_df
    sapling_rows = []
    for _, row in sapling_df.iterrows():
        # Live saplings
        if row['sapling_live_count'] > 0:
            sapling_rows.append({
                'tree_count': row['sapling_live_count'],
                'tree_species': row['sapling_species'],
                'tree_status': 'L',
                'tree_dbh': row['sapling_live_dbh'],
                'tree_ht': row['sapling_live_ht'],
                'tree_cbh': row['sapling_live_cbh'],
                'tree_dcy_class_cnfr': 1 if row['tree_type'] == 'conifer' else np.nan,
                'tree_dcy_class_brdlf': 1 if row['tree_type'] == 'broadleaf' else np.nan,
                'tree_note': '[Fuel Analyst Note] Tree merged from sapling data; ',
                'ParentGlobalID': row['ParentGlobalID'] if 'ParentGlobalID' in row else None,
                'CreationDate': row['CreationDate'] if 'CreationDate' in row else None,
                'Creator': row['Creator'] if 'Creator' in row else None,
                'EditDate': row['EditDate'] if 'EditDate' in row else None,
                'Editor': row['Editor'] if 'Editor' in row else None,
            })
        # Dead saplings
        if row['sapling_dead_count'] > 0:
            sapling_rows.append({
                'tree_count': row['sapling_dead_count'],
                'tree_species': row['sapling_species'],
                'tree_status': 'D',
                'tree_dbh': row['sapling_dead_dbh'],
                'tree_ht': row['sapling_dead_ht'],
                'tree_cbh': np.nan,
                'tree_dcy_class_cnfr': 3 if row['tree_type'] == 'conifer' else np.nan,
                'tree_dcy_class_brdlf': 3 if row['tree_type'] == 'broadleaf' else np.nan,
                'tree_note': '[Fuel Analyst Note] Tree merged from sapling data; ',
                'ParentGlobalID': row['ParentGlobalID'] if 'ParentGlobalID' in row else None,
                'CreationDate': row['CreationDate'] if 'CreationDate' in row else None,
                'Creator': row['Creator'] if 'Creator' in row else None,
                'EditDate': row['EditDate'] if 'EditDate' in row else None,
                'Editor': row['Editor'] if 'Editor' in row else None,
            })
    # Convert sapling_rows to DataFrame and append to tree_df
    if sapling_rows:
        sapling_tree_df = pd.DataFrame(sapling_rows)
        tree_df = pd.concat([tree_df, sapling_tree_df], ignore_index=True)


    return tree_df, sapling_df


def _round_plot_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    Rounds plot data columns to appropriate decimal places.

    :param df: DataFrame containing plot data.
    :return: Updated DataFrame with rounded values.
    """
    print('\tRounding plot variables')
    # Round DBH, height, cbh, and dcbh to 1 decimal place
    df['lgtree_plot_radius'] = df['lgtree_plot_radius'].round(2)
    df['smtree_plot_radius'] = df['smtree_plot_radius'].round(2)
    df['sapling_plot_radius'] = df['sapling_plot_radius'].round(2)

    return df


def _round_tree_data(tree_df: pd.DataFrame) -> pd.DataFrame:
    """
    Rounds tree data columns to appropriate decimal places.

    :param tree_df: DataFrame containing individual tree data.
    :return: Updated DataFrame with rounded values.
    """
    print('\tRounding tree variables')
    # Round DBH, height, cbh, and dcbh to 1 decimal place
    tree_df['tree_dbh'] = tree_df['tree_dbh'].round(1)
    tree_df['tree_ht'] = tree_df['tree_ht'].round(1)
    tree_df['tree_cbh'] = tree_df['tree_cbh'].round(1)
    tree_df['tree_dcbh'] = tree_df['tree_dcbh'].round(1)
    # Round bark char height to 2 decimal places
    tree_df['tree_bark_char_high'] = tree_df['tree_bark_char_high'].round(2)
    tree_df['tree_bark_char_low'] = tree_df['tree_bark_char_low'].round(2)
    tree_df['tree_bark_char_azim'] = tree_df['tree_bark_char_azim'].round(2)

    return tree_df


def process_trees(in_folder: str,
                  out_folder: str,
                  surface_fire_intensity_model: str,
                  stand_summary_params: dict) -> tuple[pd.DataFrame, list, pd.DataFrame]:
    """
    Get the tree data from CSV files.

    :param in_folder: Path to the folder containing the input CSV files.
    :param out_folder: Path to the folder where output CSV files will be saved.
    :param surface_fire_intensity_model: Model to use for calculating surface fireline intensity (default is 'Byram').
        Options: ['Byram', 'Thomas']
    :param stand_summary_params: Dictionary containing stand summary parameters.
    :return: Tuple containing:
        - Updated DataFrame with plot-level attributes.
        - List of columns to keep in the final DataFrame.
        - Master tree DataFrame with selected attributes for export.
    """
    print('\nProcessing Tree data')

    # Initialize list of columns to keep
    keep_columns = []

    # Load tree parameters and set index
    tree_params_df = helper.get_df(
        os.path.join(os.path.dirname(__file__), 'Supporting_Data\\tree_parameters.csv')
    ).set_index('Species')

    # ### PROCESS PLOT-LEVEL ATTRIBUTES
    # Get plot dataframe
    df = helper.get_df(os.path.join(in_folder, 'survey_0.csv'))
    # Generate a unique ID for each plot
    df = helper.get_unique_id(df)
    # Calculate plot attributes
    df = _round_plot_data(df)
    df = _calc_plot_multipliers(df)

    # ### PROCESS SAPLING ATTRIBUTES
    # Get sapling dataframe
    sapling_df = helper.get_df(os.path.join(in_folder, 'sapling_1.csv'))
    # Calculate sapling attributes
    sapling_df = _calc_sapling_tree_type(sapling_df, tree_params_df)
    sapling_df = _calc_sapling_density(sapling_df)
    sapling_df = _calc_sapling_dbh(sapling_df)
    sapling_df = _calc_sapling_ht(sapling_df, tree_params_df)

    # ### PROCESS INDIVIDUAL TREE ATTRIBUTES
    # Get tree dataframe
    tree_df = helper.get_df(os.path.join(in_folder, 'tree_plot_2.csv'))
    # Merge sapling attributes
    tree_df, sapling_df = _merge_saplings_to_trees(tree_df, sapling_df)
    # Round tree data to appropriate decimal places
    tree_df = _round_tree_data(tree_df)
    # Calculate tree attributes
    tree_df = _calc_tree_dbh_classes(tree_df)
    tree_df = _calc_tree_decay_classes(tree_df)
    tree_df = _calc_tree_type(tree_df, tree_params_df)
    tree_df = _calc_tree_density(df, tree_df)
    tree_df = _calc_tree_basal_area(tree_df)
    tree_df = _calc_tree_missing_heights(tree_df, tree_params_df)
    tree_df = _calc_tree_cbh(tree_df)
    tree_df = _calc_tree_fsg(tree_df)
    tree_df = _calc_tree_crown_depth(tree_df)
    tree_df = _calc_tree_biomass(tree_df, tree_params_df)
    tree_df = _calc_tree_crown_fuels(tree_df, tree_params_df)
    # Calculate FOFEM tree attributes
    tree_df = _calc_tree_fofem_attributes(tree_df, tree_params_df)
    # Calculate fire behavior attributes
    tree_df = _calc_tree_fire_attributes(tree_df, surface_fire_intensity_model)
    # Calculate weighted attributes
    tree_df = _calc_tree_weighted_attributes(tree_df)
    # Generate Master Tree DataFrame
    master_tree_df = _gen_master_tree_df(df, tree_df)

    # ### PROCESS STAND_LEVEL (PER HA) ATTRIBUTES
    df, add_columns = _calc_stand_composition(df, tree_df)
    keep_columns.extend(add_columns)
    df, add_columns = _calc_stand_attributes(df, tree_df, stand_summary_params)
    keep_columns.extend(add_columns)

    # ### SAVE DATASETS TO OUTPUT FOLDER
    os.makedirs(out_folder, exist_ok=True)
    helper.export_csv(df, os.path.join(out_folder, 'survey_0.csv'))
    helper.export_csv(sapling_df, os.path.join(out_folder, 'sapling_1.csv'))
    helper.export_csv(tree_df, os.path.join(out_folder, 'tree_plot_2.csv'))

    return df, helper.sort_list(keep_columns), master_tree_df
