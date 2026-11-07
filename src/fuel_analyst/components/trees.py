# -*- coding: utf-8 -*-
"""
Created on Tue May 27, 15:30:00 2025

@author: Gregory A. Greene
"""
__author__ = ['Gregory A. Greene']

import logging
import os
import pandas as pd
import numpy as np
import itertools

from . import error_handling, helper, table_reader, tree_sampling


# VARIABLES FOR BIOMASS MODELING
tree_component_list = ['wood', 'bark', 'branches', 'foliage']
tree_component_index_dict = {
    'wood': 0,
    'bark': 1,
    'branches': 2,
    'foliage': 3
}

# Decay class thresholds for "dead/more decayed" classification
# Conifer: classes 1-9; class >=6 treated as dead (use modeled height, degraded biomass)
# Broadleaf: classes 1-6; class >=5 treated as dead
_DEAD_DECAY_THRESHOLD_CONIFER = 6
_DEAD_DECAY_THRESHOLD_BROADLEAF = 5

# Sentinel value entered in the field to indicate bark char reached full tree height.
# Replaced with actual tree height before flame length is calculated.
_CROWN_FIRE_CHAR_SENTINEL = 444

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

_PLOT_RADIUS_FIELDS = {
    'lgtree': 'lgtree_plot_radius',
    'smtree': 'smtree_plot_radius',
    'sapling': 'sapling_plot_radius',
}

logger = logging.getLogger(__name__)


def _calc_conpyro_live_density(
        df: pd.DataFrame,
        tree_df: pd.DataFrame,
        sapling_df: pd.DataFrame | None = None
) -> pd.DataFrame:
    """
    Summarize live-tree density and presence without treating invalid density as absence.

    :param df: Tree parent records, including presence flags and GlobalID.
    :param tree_df: Processed trees and counted saplings with status, counts and density.
    :param sapling_df: Normalized saplings, including counts that could not form tree rows.
    :return: Parent table with fixed live density and nullable live-tree presence for ConPyro.
    """
    density = tree_df.groupby('ParentGlobalID')['tree_dens_live_ha'].sum(min_count=1)
    values = df['GlobalID'].map(density)
    count = tree_df['tree_count']
    live = tree_df['tree_status'].eq('L') & count.gt(0)
    known_live = set(tree_df.loc[live, 'ParentGlobalID'])
    invalid = count.isna() | ~tree_df['tree_status'].isin(['L', 'D'])
    uncertain = set(tree_df.loc[invalid, 'ParentGlobalID'])
    density_invalid = tree_df.get('tree_density_affected', pd.Series(False, index=tree_df.index)).fillna(True)
    invalid_density = set(tree_df.loc[density_invalid, 'ParentGlobalID'])
    absence = _get_tree_absence(df)
    covered = absence.copy()
    radius_class = tree_df.get('tree_density_radius_class', pd.Series('', index=tree_df.index))
    for name in ('lgtree', 'smtree', 'sapling'):
        recorded = set(tree_df.loc[radius_class.eq(name), 'ParentGlobalID'])
        covered[name] |= df['GlobalID'].isin(recorded)
    if sapling_df is not None:
        covered['sapling'] |= df['GlobalID'].isin(sapling_df['ParentGlobalID'])
        known_live.update(sapling_df.loc[sapling_df['sapling_live_count'].gt(0), 'ParentGlobalID'])
        uncertain.update(sapling_df.loc[sapling_df['sapling_live_count'].isna(), 'ParentGlobalID'])
    present = pd.Series(pd.NA, index=df.index, dtype='boolean')
    present.loc[covered.all(axis=1) & ~df['GlobalID'].isin(uncertain)] = False
    present.loc[df['GlobalID'].isin(known_live)] = True
    absent = absence.all(axis=1)
    present.loc[absent] = False
    values = values.mask(df['GlobalID'].isin(invalid_density | uncertain)).mask(absent, 0.)
    ambiguous = df.get('_parent_id_ambiguous', pd.Series(False, index=df.index)).fillna(False)
    ambiguous = ambiguous | df['GlobalID'].isna() | df['GlobalID'].duplicated(keep=False)
    present = present.mask(ambiguous)
    values = values.mask(ambiguous | present.isna()).mask(present.eq(False).fillna(False), 0.)
    return helper.attach_columns(df, {
        'conpyro_live_tree_density': values,
        'conpyro_live_trees_present': present,
    })


def _calc_plot_multipliers(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate per-hectare expansion factors from circular plot radii.

    Plot radii are recorded to two decimal places in the field, so calculated
    areas are rounded to the nearest square metre before expansion. Missing or
    non-positive radii produce missing multipliers.

    :param df: DataFrame containing plot attributes.
    :return: DataFrame with multipliers added.
    """
    print('\tCalculating plot multipliers')

    for radius_class, radius_field in _PLOT_RADIUS_FIELDS.items():
        raw_radius = df[radius_field].copy()
        radius = pd.to_numeric(raw_radius, errors='coerce').round(2)
        radius_issue = _classify_numeric_input(
            raw_radius, radius, 'plot_radius', allow_zero=False
        )
        area_m2 = (np.pi * radius.pow(2)).round(0)
        finite_area = pd.Series(np.isfinite(area_m2), index=df.index).fillna(False)
        invalid_area = radius_issue.eq('') & (
            area_m2.isna() | ~finite_area | area_m2.le(0)
        )
        radius_issue.loc[invalid_area] = 'invalid_plot_area'
        valid = radius_issue.eq('')

        df[f'_{radius_field}_raw'] = raw_radius
        df[f'_plot_{radius_class}_radius_issue'] = radius_issue
        df[radius_field] = radius.where(valid)
        df[f'plot_{radius_class}_mult'] = (10000 / area_m2).where(valid)

    return df


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
    live_dbh_issue = sapling_df.get(
        '_sapling_live_dbh_issue', pd.Series('', index=sapling_df.index)
    )
    dead_dbh_issue = sapling_df.get(
        '_sapling_dead_dbh_issue', pd.Series('', index=sapling_df.index)
    )

    # Set DBH to NaN where no live saplings are present
    sapling_df['sapling_live_dbh'] = np.where(
        sapling_df.sapling_live_count == 0, np.nan, sapling_df.sapling_live_dbh
    )
    # If DBH is missing but saplings are present, assign a default value of 2.5 cm
    live_dbh_calc_mask = (
        (sapling_df.sapling_live_count > 0)
        & sapling_df.sapling_live_dbh.isnull()
        & live_dbh_issue.eq('')
    )
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
    dead_dbh_calc_mask = (
        (sapling_df.sapling_dead_count > 0)
        & sapling_df.sapling_dead_dbh.isnull()
        & dead_dbh_issue.eq('')
    )
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
    live_dbh_issue = sapling_df.get(
        '_sapling_live_dbh_issue', pd.Series('', index=sapling_df.index)
    )
    dead_dbh_issue = sapling_df.get(
        '_sapling_dead_dbh_issue', pd.Series('', index=sapling_df.index)
    )

    # Set DBH to NaN where no live saplings are present
    sapling_df['sapling_live_ht'] = np.where(
        sapling_df.sapling_live_count == 0, np.nan, sapling_df.sapling_live_ht
    )
    # Set DBH to NaN where no dead saplings are present
    sapling_df['sapling_dead_ht'] = np.where(
        sapling_df.sapling_dead_count == 0, np.nan, sapling_df.sapling_dead_ht
    )

    # Get list of sapling species, excluding 'NO_SAPLINGS'
    spp_list = [spp for spp in sapling_df['sapling_species'].unique() if spp != 'NO_SAPLINGS']

    # For each species, estimate missing heights for live and dead saplings
    for spp in spp_list:
        # Estimate live sapling height where density > 0 and height is missing
        mask_live = (
            (sapling_df['sapling_species'] == spp) &
            (sapling_df['sapling_live_count'] > 0) &
            live_dbh_issue.eq('') &
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
            dead_dbh_issue.eq('') &
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


def _calc_stand_attributes(
        df: pd.DataFrame,
        tree_df: pd.DataFrame,
        stand_summary_params: dict
) -> tuple[pd.DataFrame, list]:
    """
    Calculates stand-level attributes for requested parameters and attributes.
    Adds columns to the plot-level DataFrame for each attribute.

    :param df: DataFrame containing plot-level data.
    :param tree_df: DataFrame containing individual tree data.
    :param stand_summary_params: Dictionary containing stand summary parameters.
    :return: Tuple containing the updated plot-level DataFrame and the names of
        its generated stand-summary columns.
    """
    # Helper: get all permutations of summary types
    def get_permutations(_summary_list: list, _summary_permutation: str) -> list:
        """
        Generate valid permutations of summary types based on rules and permutation mode.

        :param _summary_list: List of summary types to permute.
        :param _summary_permutation: 'all', 'exact', or 'combined'.
        :return: List of valid summary permutations.
        """
        priority_order = {val: i for i, val in enumerate(_summary_list)}

        if _summary_permutation == 'exact':
            # Only return the exact order as a single permutation
            return _summary_list
        elif _summary_permutation == 'combined':
            # Total means all trees and cannot constrain a combined filter.
            combined_parts = list(dict.fromkeys(
                part for part in _summary_list if part != 'total'
            ))
            if not combined_parts:
                message = (
                    "summary_permutation='combined' requires at least one summary "
                    "other than 'total'."
                )
                logger.error(message, extra={'issue_code': 'combined_summary_total_only'})
                raise ValueError(message)
            both_statuses = {'live', 'dead'} <= set(combined_parts)
            both_types = {'conifer', 'broadleaf'} <= set(combined_parts)
            effective_parts = [
                part for part in combined_parts
                if not (both_statuses and part in {'live', 'dead'})
                and not (both_types and part in {'conifer', 'broadleaf'})
            ]
            return ['_'.join(effective_parts) if effective_parts else 'total']
        else:
            # Default: all valid permutations as before
            valid_permutations = set()
            for r in range(1, 4):
                for combo in itertools.combinations(_summary_list, r):
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

            def sort_key(_combo: str):
                """
                Build the priority key for one summary permutation.

                :param _combo: Underscore-delimited summary permutation.
                :return: Component count and configured component priorities.
                """
                parts = _combo.split('_')
                return (len(parts), [priority_order.get(p, len(priority_order)) for p in parts])

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
            return pd.Series(True, index=_tree_df.index, dtype=bool)

        # Start with all True mask and apply each condition
        _mask = pd.Series(True, index=_tree_df.index, dtype=bool)

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
            field_name = f"tree_{attribute_weighting_dict.get(_att, 'dens')}_ha"
            # Only trees that have a value carry weight; a plot where none do gets a missing mean, not 0
            valued_trees = _tree_df[_tree_df[f'tree_{_att}'].notna()]
            denom = valued_trees.groupby('ParentGlobalID')[field_name].sum()
            denom = denom.where(denom > 0)
        elif _att == 'cbd':
            field_name = f'tree_{attribute_weighting_dict["crwn_dpth"]}_ha'
            denom = (_tree_df.groupby('ParentGlobalID')['tree_crwn_dpth_wtd'].sum() /
                     _tree_df.groupby('ParentGlobalID')[field_name].sum())
        else:
            denom = 1
        return _value / denom

    # Initialize a list of keep columns for the final master DataFrame
    keep_columns = []
    confirmed_absence = _get_tree_absence(df).all(axis=1)

    for att_name, att_dict in stand_summary_params.items():
        att = att_dict.get('att_source', att_name)
        override_field_name = att_dict.get('override_field_name', False)
        summary_list = att_dict.get('summary', [])
        summary_permutation = att_dict.get('summary_permutation', 'all')
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
        summary_permutations = get_permutations(summary_list, summary_permutation)
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
                    if override_field_name:
                        colname = att_name
                    else:
                        colname = f'stand_{att_name}{units}_{summary}_{metric}'.replace('_total', '')
                    new_columns[colname] = df.GlobalID.map(value)
                    if metric == 'sum' and att in ['dens', 'ba', 'cfl', 'foliage', 'branches', 'wood', 'bark']:
                        new_columns[colname] = new_columns[colname].mask(confirmed_absence, 0.)
            else:
                # Get sum of cfl values by plot
                value = tree_df[summary_mask].groupby('ParentGlobalID')[f'tree_cfl_cnbe_ha'].sum()

                # Unweight values
                value = unweight_value(att, value, tree_df[summary_mask])

                # Assign data to new column
                if override_field_name:
                    colname = att_name
                else:
                    colname = f'stand_{att_name}{units}_{summary}'.replace('_total', '')
                new_columns[colname] = df.GlobalID.map(value)

            # Process class cutoffs if present
            for class_var, cutoffs in classes.items():
                # Bounds start at first value in cutoffs
                bounds = cutoffs
                for i in range(len(bounds)):
                    lower = bounds[i]
                    upper = bounds[i + 1] if i + 1 < len(bounds) else None
                    if upper is None:
                        break
                    class_label = f'{class_var}{lower}plus' if np.isinf(upper) else f'{class_var}{lower}-{upper}'
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
                            if override_field_name:
                                colname = att_name
                            else:
                                colname = f'stand_{att_name}{units}_{summary}_{class_label}_{metric}'.replace('_total', '')
                            new_columns[colname] = df.GlobalID.map(value)
                            if metric == 'sum' and att in ['dens', 'ba', 'cfl', 'foliage', 'branches', 'wood', 'bark']:
                                new_columns[colname] = new_columns[colname].mask(confirmed_absence, 0.)
                    else:
                        value = tree_df[mask].groupby('ParentGlobalID')[f'tree_cfl_cnbe_ha'].sum()
                        # Unweight values
                        value = unweight_value(att, value, tree_df[mask])

                        # Assign data to new column
                        if override_field_name:
                            colname = att_name
                        else:
                            colname = f'stand_{att_name}{units}_{summary}_{class_label}'.replace('_total', '')
                        new_columns[colname] = df.GlobalID.map(value)

        if new_columns:
            df = pd.concat([df, pd.DataFrame(new_columns, index=df.index)], axis=1)
            # Add the stand summary columns to the keep list
            keep_columns.extend(new_columns.keys())

    return df, keep_columns


def _calc_stand_composition(
        df: pd.DataFrame,
        tree_df: pd.DataFrame,
        gen_conpyro_df: bool,
) -> tuple[pd.DataFrame, list]:
    """
    Calculates stand composition metrics for each plot based on tree basal area.

    For each plot, this function determines the top 6 species by their percentage of total basal area,
    both for live trees only and for all woody trees (live and dead). It adds columns to the plot-level
    DataFrame for the species codes, their corresponding basal area percentages, and mean heights (if requested),
    as well as a summary string for each stand. Returns the updated DataFrame and a list of new column names.

    :param df: DataFrame containing plot-level data, including 'GlobalID' and 'unique_id'.
    :param tree_df: DataFrame containing individual tree data, including 'tree_status', 'tree_ba_ha', and 'ParentGlobalID'.
    :param gen_conpyro_df: Whether to include ConPyro-specific composition fields.
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

        # If requested, calculate max height for each species in each plot
        if gen_conpyro_df:
            # Get max height by plot and species
            ht_agg = (
                tree_df.loc[tree_mask]
                .groupby(['ParentGlobalID', 'tree_species'], as_index=False)['tree_ht']
                .max()
                .rename(columns={'tree_species': 'SPECIES_CD', 'tree_ht': 'species_ht'})
            )
            ht_agg['unique_id'] = ht_agg['ParentGlobalID'].map(unique_id_map)
            ht_agg = ht_agg.drop(columns=['ParentGlobalID'])
            # Merge max height into agg
            agg = pd.merge(agg, ht_agg, on=['unique_id', 'SPECIES_CD'], how='left')

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
        if gen_conpyro_df:
            agg['height'] = 'PROJ_HEIGHT_' + agg['rank'].astype(str)

        # Pivot to wide format for species codes, percentages, and heights
        spp_code_df = agg.pivot(index='unique_id', columns='code', values='SPECIES_CD').reset_index()
        spp_pct_df = agg.pivot(index='unique_id', columns='percent', values='SPECIES_PCT').reset_index()
        if gen_conpyro_df:
            spp_ht_df = agg.pivot(index='unique_id', columns='height', values='species_ht').reset_index()

        spp_code_cols = [f'SPECIES_CD_{x}' for x in range(1, 7)]
        spp_pct_cols = [f'SPECIES_PCT_{x}' for x in range(1, 7)]
        if gen_conpyro_df:
            spp_ht_code_cols = [f'PROJ_HEIGHT_{x}' for x in range(1, 7)]

        # For live trees, add columns for top 6 species codes, percentages, and heights
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
            if gen_conpyro_df:
                map_dict = spp_ht_df.set_index('unique_id').to_dict()
                for c in spp_ht_code_cols:
                    if c in spp_ht_df.columns:
                        df[c] = df['unique_id'].map(map_dict[c])
                    else:
                        df[c] = np.nan
                    keep_columns.append(c)

        # Create a summary string column for each stand (live or woody)
        merged = pd.merge(spp_code_df, spp_pct_df, on='unique_id', how='outer')
        def spp_tuple_str(row):
            """
            Format one row of species codes and percentages.

            :param row: Stand-composition row containing species code and percentage fields.
            :return: Comma-delimited species composition, or None when no species are present.
            """
            # Build a string like "SP1:40.0, SP2:30.0, ..."
            pairs = [
                f"{row.get(f'SPECIES_CD_{i}')}:{row.get(f'SPECIES_PCT_{i}')}"
                for i in range(1, 7)
                if (pd.notnull(row.get(f'SPECIES_CD_{i}')) and
                    pd.notnull(row.get(f'SPECIES_PCT_{i}')) and
                    row.get(f'SPECIES_PCT_{i}') > 0)
            ]
            return ', '.join(pairs) if pairs else None

        spp_comp_col_name = 'stand_spp_comp_live' if status == ['L'] else 'stand_spp_comp_woody'
        df[spp_comp_col_name] = df['unique_id'].map(
            merged.set_index('unique_id').apply(spp_tuple_str, axis=1)
        )
        keep_columns.append(spp_comp_col_name)

        # Add percent conifer and broadleaf columns for live trees
        if status == ['L']:
            total_ba = (
                tree_df.loc[tree_mask]
                .groupby('ParentGlobalID')['tree_ba_ha']
                .sum()
                .rename(unique_id_map)
            )
            conifer_ba = (
                tree_df.loc[tree_mask & (tree_df['tree_type'] == 'conifer')]
                .groupby('ParentGlobalID')['tree_ba_ha']
                .sum()
                .rename(unique_id_map)
            )
            broadleaf_ba = (
                tree_df.loc[tree_mask & (tree_df['tree_type'] == 'broadleaf')]
                .groupby('ParentGlobalID')['tree_ba_ha']
                .sum()
                .rename(unique_id_map)
            )

            df['stand_pct_cnfr_live'] = (
                    100 * df['unique_id'].map(conifer_ba) / df['unique_id'].map(total_ba)
            ).fillna(0).round(1)
            df['stand_pct_brdlf_live'] = (
                    100 * df['unique_id'].map(broadleaf_ba) / df['unique_id'].map(total_ba)
            ).fillna(0).round(1)
            keep_columns.extend(['stand_pct_cnfr_live', 'stand_pct_brdlf_live'])

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
    A tree missing DBH or the applicable height (measured for live/less decayed, modeled for
    dead/more decayed) is excluded entirely and contributes zero biomass for every component.

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

    # Conifer species come from each tree's tree_type, which _calc_tree_type() reads from the TreeType column of
    # tree_parameters.csv, so that file is the only place that records whether a species is a conifer.
    conifer_species = set(tree_df.loc[tree_df['tree_type'] == 'conifer', 'tree_species'].dropna().unique())

    for spp in spp_list:
        # Select decay class dictionary based on species type
        decay_dict = tree_conifer_decay_class_dict if spp in conifer_species else tree_broadleaf_decay_class_dict
        for component in tree_component_list:
            comp_idx = tree_component_index_dict[component]
            param1 = tree_params_df.loc[spp, f'BIOMASS_CNBE_DBH-HT_B{component}1']
            param2 = tree_params_df.loc[spp, f'BIOMASS_CNBE_DBH-HT_B{component}2']
            param3 = tree_params_df.loc[spp, f'BIOMASS_CNBE_DBH-HT_B{component}3']

            # Masks for live/less decayed (measured height) and dead/more decayed (modeled
            # height) trees. mask_live includes all live trees, and less decayed dead trees.
            # mask_dead includes more decayed dead trees, and checks tree_ht_modeled, not raw tree_ht,
            # to match the height actually used in its biomass formula below - tree_ht_modeled is
            # guaranteed whenever tree_dbh is present (_calc_tree_missing_heights() models it
            # unconditionally for this same decay/DBH-filtered population), so this never excludes
            # a tree the DBH check alone wouldn't already exclude.
            mask_live = (
                (tree_df.tree_species == spp) &
                (tree_df.tree_dcy_class > 0) &
                ((tree_df.tree_dcy_class_cnfr < _DEAD_DECAY_THRESHOLD_CONIFER) |
                 (tree_df.tree_dcy_class_brdlf < _DEAD_DECAY_THRESHOLD_BROADLEAF)) &
                (tree_df.tree_dbh > 0) &
                (tree_df.tree_ht > 0)
            )
            mask_dead = (
                (tree_df.tree_species == spp) &
                (tree_df.tree_dcy_class > 0) &
                ((tree_df.tree_dcy_class_cnfr >= _DEAD_DECAY_THRESHOLD_CONIFER) |
                 (tree_df.tree_dcy_class_brdlf >= _DEAD_DECAY_THRESHOLD_BROADLEAF)) &
                (tree_df.tree_dbh > 0) &
                (tree_df.tree_ht_modeled > 0)
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
    tree_df['tree_note'] = tree_df['tree_note'].astype(object)
    tree_df.loc[mask, 'tree_note'] = (
        tree_df.loc[mask, 'tree_note'].fillna('').astype(str) +
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


def _calc_tree_density(
        df: pd.DataFrame,
        tree_df: pd.DataFrame,
        tree_sampling_params: dict | None = None
) -> pd.DataFrame:
    """
    Select sampling areas by source for saplings and by DBH for measured trees.

    For each tree:
    - Measured trees use configured DBH cutoffs (defaults: 5 and 12.5 cm).
    - Sapling-table records always use the sapling sampling area.
    - Missing protocol labels leave affected densities missing and do not raise.

    :param df: DataFrame containing plot-level multipliers.
    :param tree_df: DataFrame containing individual tree data, including DBH.
    :param tree_sampling_params: Global DBH thresholds and optional parent protocol overrides.
    :return: Updated tree_df with tree_dens_ha, sampling-area selection and validation diagnostics.
    """
    settings = tree_sampling.normalize_tree_sampling_params(tree_sampling_params)
    print('\tCalculating tree density (per hectare)')
    tree_df = tree_df.copy()

    parent_id = tree_df['ParentGlobalID']
    plot_ids = df['GlobalID']
    ambiguous_marker = df.get(
        '_parent_id_ambiguous', pd.Series(False, index=df.index)
    ).fillna(False).astype(bool)
    duplicate_ids = set(plot_ids[plot_ids.notna() & plot_ids.duplicated(keep=False)])
    duplicate_ids.update(df.loc[ambiguous_marker, 'GlobalID'].dropna())
    valid_plots = df.loc[~df['GlobalID'].isin(duplicate_ids) & df['GlobalID'].notna()]
    valid_plots = valid_plots.drop_duplicates('GlobalID').set_index('GlobalID')

    parent_issue = pd.Series('', index=tree_df.index, dtype='object')
    parent_missing = parent_id.isna() | parent_id.astype('string').str.strip().eq('').fillna(True)
    parent_issue.loc[parent_missing] = 'missing_parent_id'
    parent_issue.loc[~parent_missing & parent_id.isin(duplicate_ids)] = 'ambiguous_parent_id'
    parent_issue.loc[
        ~parent_missing & ~parent_id.isin(duplicate_ids) & ~parent_id.isin(set(plot_ids.dropna()))
    ] = 'orphan_tree_record'

    required = tree_df.get(
        'tree_density_required', pd.Series(True, index=tree_df.index)
    ).fillna(True).astype(bool)
    eligible_ids = parent_id.loc[required & parent_issue.eq('')]
    eligible = valid_plots.loc[valid_plots.index.isin(eligible_ids)]
    resolution = tree_sampling.resolve_tree_sampling_thresholds(eligible, settings)
    sampling_issue = parent_id.map(resolution['sampling_issue_code']).fillna('')
    small_min = parent_id.map(resolution['small_tree_min']).where(
        required, settings['dbh_thresholds_cm']['small_tree_min']
    )
    large_min = parent_id.map(resolution['large_tree_min']).where(
        required, settings['dbh_thresholds_cm']['large_tree_min']
    )
    sampling_valid = sampling_issue.eq('')
    raw_dbh = tree_df.get('_tree_dbh_raw', tree_df['tree_dbh']).copy()
    dbh = pd.to_numeric(tree_df['tree_dbh'], errors='coerce')
    if '_tree_dbh_issue' in tree_df.columns:
        dbh_issue = tree_df['_tree_dbh_issue'].fillna('').copy()
    else:
        dbh_issue = _classify_numeric_input(
            raw_dbh, dbh, 'tree_dbh', allow_zero=False
        )
    dbh_finite = pd.Series(np.isfinite(dbh), index=tree_df.index).fillna(False)
    normalized_dbh_issue = _classify_numeric_input(
        tree_df['tree_dbh'], dbh, 'tree_dbh', allow_zero=False
    )
    invalid_normalized_dbh = dbh_issue.eq('') & normalized_dbh_issue.ne('')
    dbh_issue.loc[invalid_normalized_dbh] = normalized_dbh_issue.loc[invalid_normalized_dbh]
    valid_dbh = dbh_issue.eq('') & dbh_finite & dbh.gt(0)

    raw_count = tree_df['tree_count'].copy()
    count = pd.to_numeric(raw_count, errors='coerce')
    count_issue = _classify_numeric_input(raw_count, count, 'tree_count', allow_zero=True)
    valid_count = count_issue.eq('')

    radius_class = pd.Series(pd.NA, index=tree_df.index, dtype='object')
    radius_class.loc[valid_dbh & sampling_valid & dbh.ge(large_min)] = 'lgtree'
    radius_class.loc[valid_dbh & sampling_valid & dbh.ge(small_min) & dbh.lt(large_min)] = 'smtree'
    radius_class.loc[valid_dbh & sampling_valid & dbh.lt(small_min)] = 'sapling'
    # Aggregated saplings were counted in the sapling plot, even when DBH is imputed.
    source = tree_df.get('tree_density_source_table', pd.Series('', index=tree_df.index))
    radius_class.loc[valid_dbh & sampling_valid & source.eq('sapling_1.csv')] = 'sapling'
    radius_field = radius_class.map(_PLOT_RADIUS_FIELDS)

    selected_multiplier = pd.Series(np.nan, index=tree_df.index, dtype='float64')
    selected_radius_issue = pd.Series('', index=tree_df.index, dtype='object')
    for plot_class in _PLOT_RADIUS_FIELDS:
        class_mask = radius_class.eq(plot_class) & parent_issue.eq('')
        multiplier_map = valid_plots.get(
            f'plot_{plot_class}_mult', pd.Series(dtype='float64')
        ).to_dict()
        selected_multiplier.loc[class_mask] = parent_id.loc[class_mask].map(multiplier_map)
        issue_map = valid_plots.get(
            f'_plot_{plot_class}_radius_issue', pd.Series('', index=valid_plots.index)
        ).to_dict()
        selected_radius_issue.loc[class_mask] = parent_id.loc[class_mask].map(issue_map).fillna('')

    missing_multiplier = (
        valid_dbh & sampling_valid & parent_issue.eq('') & selected_multiplier.isna()
        & selected_radius_issue.eq('')
    )
    selected_radius_issue.loc[missing_multiplier] = 'invalid_plot_radius'

    warnings = tree_df.get(
        '_tree_dbh_warning', pd.Series('', index=tree_df.index)
    ).fillna('')
    required = tree_df.get(
        'tree_density_required', pd.Series(True, index=tree_df.index)
    ).fillna(True).astype(bool)

    all_codes = []
    primary_codes = []
    input_valid = []
    for idx in tree_df.index:
        error_codes = []
        for code in (
            parent_issue.loc[idx], dbh_issue.loc[idx], count_issue.loc[idx],
            selected_radius_issue.loc[idx], sampling_issue.loc[idx],
        ):
            if code and code not in error_codes:
                error_codes.append(code)
        warning_codes = [warnings.loc[idx]] if warnings.loc[idx] else []
        codes = error_codes + [code for code in warning_codes if code not in error_codes]
        all_codes.append('|'.join(codes))
        primary_codes.append(error_codes[0] if error_codes else '')
        input_valid.append(not error_codes)

    input_valid = pd.Series(input_valid, index=tree_df.index, dtype=bool)
    calculated_density = selected_multiplier * count
    finite_density = pd.Series(np.isfinite(calculated_density), index=tree_df.index).fillna(False)
    invalid_calculated = input_valid & (~finite_density | calculated_density.lt(0))
    if invalid_calculated.any():
        for idx in tree_df.index[invalid_calculated]:
            codes = [c for c in all_codes[tree_df.index.get_loc(idx)].split('|') if c]
            if 'non_finite_tree_density' not in codes:
                codes.append('non_finite_tree_density')
            all_codes[tree_df.index.get_loc(idx)] = '|'.join(codes)
            primary_codes[tree_df.index.get_loc(idx)] = 'non_finite_tree_density'
        input_valid.loc[invalid_calculated] = False

    tree_df['tree_dbh'] = dbh
    tree_df['tree_count'] = count
    tree_df['tree_density_radius_class'] = radius_class
    tree_df['tree_density_radius_field'] = radius_field
    tree_df['tree_density_multiplier'] = selected_multiplier
    tree_df['tree_density_input_valid'] = input_valid
    tree_df['tree_density_required'] = required
    tree_df['tree_density_affected'] = required & ~input_valid
    tree_df['tree_density_primary_issue_code'] = primary_codes
    tree_df['tree_density_issue_codes'] = all_codes
    tree_df['tree_density_issue'] = [
        '; '.join(code.replace('_', ' ') for code in codes.split('|') if code)
        for codes in all_codes
    ]
    tree_df['tree_dens_ha'] = calculated_density.where(input_valid, 0.0).fillna(0.0).mask(~sampling_valid)
    tree_df['_tree_sampling_issue_code'] = sampling_issue
    tree_df['_tree_sampling_protocol_column'] = settings['protocol_column'] or ''

    return tree_df


def _calc_tree_fire_attributes(
        tree_df: pd.DataFrame,
        surface_fire_intensity_model: str = 'Byram',
        burned_plot_ids: set | None = None,
) -> pd.DataFrame:
    """
    Calculates fire-related attributes for each tree in the DataFrame.

    This function computes:
    - Flame length based on bark char height.
    - Fireline intensity (FLI) based on tree density and basal area.
        - Byram (1959) or Thomas (1963) model for surface fire intensity.
        - Butler's model for crown fire intensity.

    When burned_plot_ids is given, only the trees of those plots are part of the calculation: trees of
    unburned plots are left missing, and a valid tree (one with a basal area) of a burned plot without a bark
    char height is recorded as 0.

    :param tree_df: DataFrame containing individual tree data, including density, basal area, crown base height,
                    dead crown base height, and fuel bed height.
    :param surface_fire_intensity_model: Model to use for calculating surface fireline intensity (default is 'Byram').
        Options: ['Byram', 'Thomas']
    :param burned_plot_ids: GlobalID values of the burned plots, matched to the ParentGlobalID of each tree. None
        applies no plot restriction.
    :return: Updated DataFrame with new columns for FLI, CFP, and CBD.
    """
    print('\tCalculating fire metrics (Fireline Intensity, Flame Length)')

    # ### RESOLVE SENTINEL BARK CHAR HEIGHT ###
    # Per field protocol, a bark char height reaching the full tree height (crown fire)
    # is recorded either as _CROWN_FIRE_CHAR_SENTINEL or as the tree's own measured
    # height entered directly -- both indicate the same condition. Replace the sentinel
    # with actual tree height before calculating flame length (already-equal rows are a no-op).
    full_ht_mask = (
        (tree_df['tree_bark_char_high'] == _CROWN_FIRE_CHAR_SENTINEL) |
        (tree_df['tree_bark_char_high'] == tree_df['tree_ht'])
    )
    tree_df.loc[full_ht_mask, 'tree_bark_char_high'] = tree_df.loc[full_ht_mask, 'tree_ht']

    # ### ESTIMATE FLAME LENGTH ###
    # Invert the FOFEM char height equation to solve for flame length
    tree_df['tree_flame_length'] = tree_df['tree_bark_char_high'] * 1.8

    # ### CALCULATE VARIOUS FIRELINE INTENSITY OPTIONS ###
    if surface_fire_intensity_model == 'Thomas':
        # Use the Thomas (1963) flame length model to estimate fireline intensity (kW/m)
        surface_model = (tree_df['tree_flame_length'] / 0.026700) ** (3 / 2)
    else:
        if surface_fire_intensity_model != 'Byram':
            logger.warning(
                'Invalid surface fireline intensity model specified. Using Byram (1959) as default.'
            )
        # Use the Byram (1959) flame length model to estimate fireline intensity (kW/m)
        surface_model = (tree_df['tree_flame_length'] / 0.0775) ** (1 / 0.46)

    # Use the Butler et al. (2004) crown fire flame length model to estimate crown fireline intensity
    # (must add value to average stand height)
    crown_model = (tree_df['tree_flame_length'] / 0.017500) ** (3 / 2)

    # ### ESTIMATE FIRELINE INTENSITY ###
    # Use crown fire model where bark char reached full tree height, surface model otherwise
    tree_df['tree_fire_intensity'] = np.where(full_ht_mask, crown_model, surface_model)

    # ### LIMIT TO BURNED PLOTS ###
    # Flame length and fire intensity describe a fire that occurred, so unburned plots are left missing. A tree of a
    # burned plot with no bark char height is recorded as 0 (this should not happen, but can in a poorly filled form)
    if burned_plot_ids is not None:
        burned = tree_df['ParentGlobalID'].isin(burned_plot_ids)
        fire_columns = ['tree_flame_length', 'tree_fire_intensity']
        tree_df.loc[~burned, fire_columns] = np.nan
        # A record without a basal area (for example, a missing DBH) is not a valid tree, so it stays missing
        valid_tree = tree_df['tree_ba_ha'].notna() if 'tree_ba_ha' in tree_df.columns else True
        fill_zero = burned & valid_tree
        tree_df.loc[fill_zero, fire_columns] = tree_df.loc[fill_zero, fire_columns].fillna(0.0)

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
    # PLACEHOLDER CODE FOR ALTERNATE BARK THICKNESS CALCULATION APPROACH (INCOMPLETE)
    # def _get_bark_thick():
    #     bark_model_map = tree_params_df['BrkThck_Model'].to_dict()
    #     bc_mat_immat_bark_dbh_thresh = tree_params_df['BC_BrkThck_MI_DBH'].to_dict()
    #     bc_coast_mat_bark_k = tree_params_df['BC_BrkThck_K_C_M'].to_dict()
    #     bc_coast_immat_bark_k = tree_params_df['BC_BrkThck_K_C_I'].to_dict()
    #     bc_southint_bark_k = tree_params_df['BC_BrkThck_K_SI'].to_dict()
    #     bc_northint_bark_k = tree_params_df['BC_BrkThck_K_NI'].to_dict()
    #     fofem_bark_map = tree_params_df['FOFEM_BrkThck_Vsp'].to_dict()
    #
    #     temp_bark_cols = {
    #         'bark_thick_model': bark_model_map,
    #         'bc_bark_dbh_thresh': bc_mat_immat_dbh_thresh,
    #         'bc_bark_k_coast_mat': bc_coast_mat_bark_k,
    #         'bc_bark_k_coast_immat': bc_coast_immat_bark_k,
    #         'bc_bark_k_southint': bc_southint_bark_k,
    #         'bc_bark_k_northint': bc_northint_bark_k,
    #     }
    #
    #     for col in temp_bark_cols.keys():
    #         new_col = col.replace('_k', '_vsp')
    #         tree_df[new_col] = tree_df['tree_species'].map(temp_bark_cols[col])
    #         if '_vsp' in new_col:
    #             np.where(pd.isnull(tree_df[new_col]), np.nan, (1 - tree_df[new_col]) / 2)
    #
    #     # Apply Kozak/BC bark thickness models based on DBH thresholds and region (coast or south/north interior)
    #     #
    #
    #     # Calculate bark thickness where tree density is valid, else NaN
    #     tree_df['tree_bark_thick'] = np.where(
    #         (tree_df ['bark_thick_model'] == 'FOFEM') & (tree_df['tree_dens_ha'] >= 0),
    #         tree_df['tree_dbh'] * tree_df['tree_species'].map(bark_map),
    #         tree_df['tree_bark_thick']
    #     )

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
        """
        Model tree height for one record when species parameters are available.

        :param row: Tree record containing species and DBH values.
        :return: Modeled tree height in metres, or NaN for an unsupported species.
        """
        if row['tree_species'] in spp_set:
            return _get_temesgen_tree_height(2, tree_params_df, row['tree_species'], row['tree_dbh'])
        return np.nan

    # Set of valid species codes present in the data
    spp_set = set(tree_df['tree_species'].dropna())

    # Mask for trees missing heights (less-decayed, and valid DBH)
    mask_missing = (
        (tree_df['tree_dens_ha'] > 0) &
        (
            (tree_df['tree_dcy_class_cnfr'] < _DEAD_DECAY_THRESHOLD_CONIFER) |
            (tree_df['tree_dcy_class_brdlf'] < _DEAD_DECAY_THRESHOLD_BROADLEAF)
        ) &
        tree_df['tree_ht'].isnull() &
        tree_df['tree_dbh'].notnull()
    )
    # Assign modeled heights to trees missing height values
    tree_df.loc[mask_missing, 'tree_ht_modeled'] = tree_df[mask_missing].apply(model_height, axis=1)

    # Assign modeled heights to dead trees with missing height values
    tree_df.loc[mask_missing, 'tree_ht'] = tree_df.loc[mask_missing, 'tree_ht_modeled']

    # Mask for dead/more-decayed trees (use modeled height, and valid DBH)
    mask_dead = (
        (
            (tree_df['tree_dcy_class_cnfr'] >= _DEAD_DECAY_THRESHOLD_CONIFER) |
            (tree_df['tree_dcy_class_brdlf'] >= _DEAD_DECAY_THRESHOLD_BROADLEAF)
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

    This function computes the weighted height, crown base height (CBH), dead crown base height (DCBH),
    fuel strata gap, crown depth, flame length, and fire intensity for each tree,
    using the tree's density or basal area as weighting factors.

    :param tree_df: DataFrame containing weighted values.
    :return: Updated DataFrame with new columns for weighted attributes.
    """
    attribute_weighting_dict = {
        'ht': 'ba',
        'cbh': 'ba',
        'dcbh': 'ba',
        'fsg': 'ba',
        'crwn_dpth': 'ba',
        'flame_length': 'ba',
        'fire_intensity': 'ba',
    }
    print('\tCalculating tree weighted attributes')
    for att, att_wt_mult in attribute_weighting_dict.items():
        # Get the column names for the attribute and its weight multiplier
        att_col = f'tree_{att}'
        wtd_col = f'tree_{att}_wtd'

        # Calculate the weighted attribute
        tree_df[wtd_col] = tree_df[att_col] * tree_df[f'tree_{att_wt_mult}_ha']

    return tree_df


def _classify_numeric_input(raw: pd.Series, numeric: pd.Series, prefix: str, allow_zero: bool) -> pd.Series:
    """
    Return a stable validation code for each numeric source value.

    :param raw: Original uncoerced values.
    :param numeric: Values after numeric coercion.
    :param prefix: Field-specific suffix used in validation issue codes.
    :param allow_zero: Whether zero is accepted as a valid numeric value.
    :return: Validation issue code for each input row, or an empty string when valid.
    """
    raw_text = raw.astype('string').str.strip()
    missing = raw.isna() | raw_text.eq('').fillna(True)
    issue = pd.Series('', index=raw.index, dtype='object')
    issue.loc[missing] = f'missing_{prefix}'
    issue.loc[~missing & numeric.isna()] = f'non_numeric_{prefix}'
    finite = pd.Series(np.isfinite(numeric), index=raw.index).fillna(False)
    issue.loc[numeric.notna() & ~finite] = f'non_finite_{prefix}'
    if allow_zero:
        issue.loc[finite & numeric.lt(0)] = f'negative_{prefix}'
    else:
        issue.loc[finite & numeric.le(0)] = f'non_positive_{prefix}'
    return issue


def _exclude_unlisted_species(
        df: pd.DataFrame,
        tree_df: pd.DataFrame,
        sapling_df: pd.DataFrame,
        tree_params_df: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, list]:
    """
    Log each tree or sapling species that is missing from tree_parameters.csv and leave the affected plots out.

    The tree and sapling calculations look each species up in the table for its height, biomass, and fuel parameters,
    so an unlisted species cannot be calculated. Each affected plot is logged through error_handling (a record whose
    plot cannot be resolved goes to the General Error row). Every tree and sapling record of an affected plot is then
    removed, so that no plot is summarized from only some of its trees, and the run continues with the other plots.
    The caller sets the tree results of the returned plots to missing. Empty species entries are ignored. Sapling
    records count only when a live or dead count is above zero, and the form value for no saplings ('NO_SAPLINGS')
    never counts.

    :param df: Plot-level DataFrame with GlobalID and unique_id columns.
    :param tree_df: Raw tree table, with ParentGlobalID and tree_species columns.
    :param sapling_df: Raw sapling table, with ParentGlobalID, sapling_species, sapling_live_count, and
        sapling_dead_count columns.
    :param tree_params_df: Species parameter table indexed by species code.
    :return: Tuple of the tree table and the sapling table without the records of the affected plots (and without
        unlisted-species records whose plot cannot be resolved), and the list of affected plot unique IDs.
    """
    known = set(tree_params_df.index)

    unlisted_trees = tree_df[tree_df['tree_species'].notna() & ~tree_df['tree_species'].isin(known)]
    live = pd.to_numeric(sapling_df['sapling_live_count'], errors='coerce').fillna(0)
    dead = pd.to_numeric(sapling_df['sapling_dead_count'], errors='coerce').fillna(0)
    recorded = (
        sapling_df['sapling_species'].notna() & ((live > 0) | (dead > 0)) &
        sapling_df['sapling_species'].ne('NO_SAPLINGS')
    )
    unlisted_saplings = sapling_df[recorded & ~sapling_df['sapling_species'].isin(known)]

    affected = set()
    for label, records, species_col in (('tree', unlisted_trees, 'tree_species'),
                                        ('sapling', unlisted_saplings, 'sapling_species')):
        if records.empty:
            continue
        plots = _resolve_parent_unique_ids(df, records['ParentGlobalID'])
        affected.update(plots.dropna())
        for (species, unique_id), count in (
                records.assign(_plot=plots.values).groupby([species_col, '_plot'], dropna=False).size().items()
        ):
            outcome = ("the tree results for this plot were left empty" if pd.notna(unique_id)
                       else "the records were left out of the tree calculations")
            logger.error(
                f"Species '{species}' ({count} {'record' if count == 1 else 'records'} in the {label} table) is not in "
                f"tree_parameters.csv; {outcome}.",
                extra={'unique_id': unique_id, 'issue_code': 'tree_species_not_in_table'},
            )

    if unlisted_trees.empty and unlisted_saplings.empty:
        return tree_df, sapling_df, []

    def _remaining(records: pd.DataFrame, unlisted: pd.DataFrame) -> pd.DataFrame:
        """
        Drop the records of the affected plots and the unlisted records.

        :param records: Raw tree or sapling table.
        :param unlisted: The unlisted-species records of that table.
        :return: The table without those records, with a fresh index.
        """
        in_affected_plot = _resolve_parent_unique_ids(df, records['ParentGlobalID']).isin(affected)
        return records.loc[~(in_affected_plot | records.index.isin(unlisted.index))].reset_index(drop=True)

    return _remaining(tree_df, unlisted_trees), _remaining(sapling_df, unlisted_saplings), sorted(affected)


def _filter_tree_presence(
        df: pd.DataFrame,
        tree_df: pd.DataFrame,
        sapling_df: pd.DataFrame,
        tree_sampling_params: dict | None
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Skip records belonging to sampling classes explicitly marked absent.

    :param df: Plot parents with optional Survey123 presence flags.
    :param tree_df: Direct tree records before species or measurement validation.
    :param sapling_df: Aggregated sapling records before validation.
    :param tree_sampling_params: DBH thresholds and optional protocol overrides.
    :return: Copies without absent-class records; logs conflicting records in Trees.
    """
    absence = _get_tree_absence(df)
    if not absence.any(axis=None):
        return tree_df.copy(), sapling_df.copy()
    flags = absence.set_axis(df['GlobalID']).to_dict()
    direct_flags = pd.DataFrame(
        {name: tree_df['ParentGlobalID'].map(values).fillna(False).astype(bool)
         for name, values in flags.items()}, index=tree_df.index,
    )
    # Both direct classes absent disables the repeat even when DBH or protocol is missing.
    skip_tree = direct_flags['lgtree'] & direct_flags['smtree']
    eligible = df.loc[
        df['GlobalID'].notna() & ~df['GlobalID'].duplicated(keep=False)
        & ~df.get('_parent_id_ambiguous', pd.Series(False, index=df.index)).fillna(False).astype(bool)
        & df['GlobalID'].isin(tree_df.loc[~skip_tree, 'ParentGlobalID'])
    ]
    thresholds = tree_sampling.resolve_tree_sampling_thresholds(eligible, tree_sampling_params)
    thresholds.index = eligible['GlobalID']
    dbh = pd.to_numeric(tree_df['tree_dbh'], errors='coerce').round(1)
    small = tree_df['ParentGlobalID'].map(thresholds['small_tree_min'])
    large = tree_df['ParentGlobalID'].map(thresholds['large_tree_min'])
    valid = dbh.gt(0) & np.isfinite(dbh) & small.notna() & large.notna()
    skip_tree |= valid & (
        (dbh.ge(large) & direct_flags['lgtree'])
        | (dbh.ge(small) & dbh.lt(large) & direct_flags['smtree'])
        | (dbh.lt(small) & direct_flags['sapling'])
    )
    skip_sapling = sapling_df['ParentGlobalID'].map(flags['sapling']).fillna(False).astype(bool)
    for label, records, mask in (
            ('tree_plot_2', tree_df, skip_tree), ('sapling_1', sapling_df, skip_sapling)
    ):
        skipped = records.loc[mask]
        if label == 'sapling_1':
            # A valid no-saplings placeholder agrees with absence; it is not a conflict.
            placeholder = skipped['sapling_species'].eq('NO_SAPLINGS')
            for field in ('sapling_live_count', 'sapling_dead_count'):
                raw = skipped[field]
                missing = raw.isna() | raw.astype('string').str.strip().eq('').fillna(False)
                placeholder &= missing | pd.to_numeric(raw, errors='coerce').eq(0)
            skipped = skipped.loc[~placeholder]
        plot_ids = _resolve_parent_unique_ids(df, skipped['ParentGlobalID'])
        for unique_id, group in skipped.assign(_plot=plot_ids.values).groupby('_plot', dropna=False):
            ids = group.get('GlobalID', pd.Series(dtype='object')).dropna().astype(str).tolist()
            logger.warning(
                f'{len(group)} record(s) in {label} were skipped because their sampling class '
                f'is marked absent (presence flag N); record IDs: {", ".join(ids)}.',
                extra={'unique_id': unique_id, 'issue_code': 'tree_presence_conflict'},
            )
    return tree_df.loc[~skip_tree].copy(), sapling_df.loc[~skip_sapling].copy()


def _gen_master_tree_df(df: pd.DataFrame, tree_df: pd.DataFrame) -> pd.DataFrame:
    """
    Generate a master tree DataFrame with selected and renamed columns for export.

    - Maps group IDs to unique IDs.
    - Converts tree height class codes to descriptive labels.
    - Selects and renames relevant columns.
    - Retains all trees, live and dead. 'dens_live_ha'/'ba_live_ha' are 0 for
      dead trees by design; 'dens_ha'/'ba_ha' hold real totals for every tree.
      The 'status' column distinguishes live ('L') from dead ('D') trees.

    :param df: DataFrame containing plot-level data with 'GlobalID' and 'unique_id' columns.
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
        'unique_id', 'tree_status', 'tree_species', 'tree_species_fofem', 'tree_dcy_class_cnfr',
        'tree_dcy_class_brdlf', 'tree_ht_class_cd', 'tree_dens_live_ha', 'tree_dens_ha', 'tree_dbh',
        'tree_ba_live_ha', 'tree_ba_ha', 'tree_ht', 'tree_crwn_dpth', 'tree_bark_thick'
    ]
    tree_cols_dict = {
        'tree_status': 'status',
        'tree_species': 'spp',
        'tree_species_fofem': 'spp_fofem',
        'tree_dcy_class_cnfr': 'decay_cnfr',
        'tree_dcy_class_brdlf': 'decay_brdlf',
        'tree_ht_class_cd': 'crown_class',
        'tree_dens_live_ha': 'dens_live_ha',
        'tree_dens_ha': 'dens_ha',
        'tree_dbh': 'dbh',
        'tree_ba_live_ha': 'ba_live_ha',
        'tree_ba_ha': 'ba_ha',
        'tree_ht': 'ht',
        'tree_crwn_dpth': 'crown_depth',
        'tree_bark_thick': 'bark_thick'
    }

    # Select and rename columns; retain all trees, live and dead
    temp_df = tree_df.loc[:, tree_cols].rename(columns=tree_cols_dict)

    # Return the master DataFrame
    return temp_df.reset_index(drop=True)


def _get_burned_plot_ids(df: pd.DataFrame) -> set | None:
    """
    Identify the plots that burned from their treatment type.

    A plot burned when its treatment_type is 'burned', ignoring case and surrounding spaces.

    :param df: Plot-level DataFrame with 'GlobalID' and 'treatment_type'.
    :return: Set of GlobalID values of the burned plots, or None when the table has no treatment_type column.
    """
    if 'treatment_type' not in df.columns:
        return None
    treatment = df['treatment_type'].astype('string').str.strip().str.lower()
    return set(df.loc[treatment.eq('burned').fillna(False), 'GlobalID'].dropna())


def _get_temesgen_tree_height(
        model: int,
        param_df: pd.DataFrame,
        spp: str,
        dbh: float,
        bal: float = None,
        sph=None,
        ba=None
):
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


def _get_tree_absence(df: pd.DataFrame) -> pd.DataFrame:
    """
    Identify explicit absence only for uniquely identified plot parents.

    :param df: Plot parents, optionally carrying presence flags and ambiguity markers.
    :return: Boolean lgtree, smtree and sapling columns aligned with the parent index.
    """
    valid = (
        df['GlobalID'].notna() & df['GlobalID'].astype('string').str.strip().ne('').fillna(False)
        & ~df['GlobalID'].duplicated(keep=False)
        & ~df.get('_parent_id_ambiguous', pd.Series(False, index=df.index)).fillna(False).astype(bool)
    )
    return pd.DataFrame({
        name: df.get(field, pd.Series('', index=df.index)).astype('string').str.strip().str.upper()
        .eq('N').fillna(False) & valid
        for name, field in [('lgtree', 'tree_large_present'), ('smtree', 'tree_small_present'),
                            ('sapling', 'sapling_present')]
    }, index=df.index)


def _log_char_on_unburned_plots(df: pd.DataFrame, tree_df: pd.DataFrame, burned_plot_ids: set) -> None:
    """
    Report bark char heights that were recorded on plots whose treatment type is not burned.

    Those heights are not used for flame length or fire intensity, so the report keeps the data from being
    dropped silently when a burned plot carries a different treatment type label.

    :param df: Plot-level DataFrame with 'GlobalID' and 'unique_id'.
    :param tree_df: Tree records with 'ParentGlobalID' and 'tree_bark_char_high'.
    :param burned_plot_ids: GlobalID values of the burned plots.
    :return: None.
    """
    unique_id_by_parent = df.drop_duplicates('GlobalID').set_index('GlobalID')['unique_id']
    recorded = (tree_df['tree_bark_char_high'] > 0) & ~tree_df['ParentGlobalID'].isin(burned_plot_ids)
    for parent_id in tree_df.loc[recorded, 'ParentGlobalID'].dropna().unique():
        logger.warning(
            'Bark char height was recorded on a plot whose treatment type is not burned; '
            'it is not used for flame length or fire intensity',
            extra={
                'unique_id': unique_id_by_parent.get(parent_id, pd.NA),
                'issue_code': 'char_height_on_unburned_plot',
            },
        )


def _log_decayed_tree_height_issues(df: pd.DataFrame, tree_df: pd.DataFrame) -> None:
    """
    Report highly decayed trees that have no measured height or no DBH.

    A highly decayed tree (decay class at or above the dead threshold) takes its biomass height from the Temesgen
    model, which needs only its DBH, so a missing measured height is modelled and reported as a warning. A tree with
    no DBH contributes no biomass, which is reported as an error: when it also has no height, the height cannot be
    modelled either. Each plot is logged once per issue, with the tree_id of every affected tree. Only trees with a
    density above zero are reported, because the others contribute nothing in any case.

    :param df: Plot-level DataFrame with 'GlobalID' and 'unique_id'.
    :param tree_df: Tree records with 'ParentGlobalID', decay classes, 'tree_dens_ha', 'tree_dbh', and 'tree_ht'.
    :return: None. Logs warnings and errors through error_handling.
    """
    decayed = (
        (tree_df['tree_dens_ha'] > 0) &
        ((tree_df['tree_dcy_class_cnfr'] >= _DEAD_DECAY_THRESHOLD_CONIFER) |
         (tree_df['tree_dcy_class_brdlf'] >= _DEAD_DECAY_THRESHOLD_BROADLEAF))
    )
    no_height = tree_df['tree_ht'].isna()
    no_dbh = ~(tree_df['tree_dbh'] > 0)
    unique_ids = _resolve_parent_unique_ids(df, tree_df['ParentGlobalID'])
    issues = (
        (decayed & no_height & ~no_dbh, logger.warning, 'decayed_tree_height_modeled',
         'no measured height, so the height was modelled from the DBH'),
        (decayed & no_height & no_dbh, logger.error, 'decayed_tree_not_modellable',
         'neither a height nor a DBH, so the height cannot be modelled and no biomass is calculated'),
        (decayed & ~no_height & no_dbh, logger.error, 'decayed_tree_dbh_missing',
         'no DBH, so no biomass is calculated'),
    )
    for mask, log, code, text in issues:
        for unique_id, trees in tree_df[mask].groupby(unique_ids[mask], dropna=False, sort=False):
            tree_ids = []
            if 'tree_id' in trees.columns:
                tree_ids = [str(int(i)) if isinstance(i, float) and i.is_integer() else str(i)
                            for i in trees['tree_id'].dropna()]
            detail = f' (tree_id {", ".join(tree_ids)})' if tree_ids else ''
            count = len(trees)
            subject = '1 highly decayed tree has' if count == 1 else f'{count} highly decayed trees have'
            log(f'{subject} {text}{detail}', extra={'unique_id': unique_id, 'issue_code': code})


def _log_tree_density_issues(
        df: pd.DataFrame,
        sapling_df: pd.DataFrame,
        tree_df: pd.DataFrame,
) -> list[tuple]:
    """
    Report tree-density input failures through the centralized error_handling logger.

    Every tree- or sapling-specific message names the individual record (tree_id,
    or sapling species) so a plot with multiple issues can be traced back to
    which record needs fixing, not just which plot.

    :param df: Plot-level DataFrame containing plot identity and radius validation fields.
    :param sapling_df: Sapling records containing parent identity and count validation fields.
    :param tree_df: Tree records containing parent identity and density validation fields.
    :return: List of (unique_id, message) pairs for every issue logged at ERROR
        severity (results_partial=True), for the caller's console summary.
    """
    ambiguous_marker = df.get(
        '_parent_id_ambiguous', pd.Series(False, index=df.index)
    ).fillna(False).astype(bool)
    duplicate_ids = set(df.loc[df['GlobalID'].duplicated(keep=False), 'GlobalID'].dropna())
    duplicate_ids.update(df.loc[ambiguous_marker, 'GlobalID'].dropna())
    valid_parents = df.loc[~df['GlobalID'].isin(duplicate_ids)].drop_duplicates('GlobalID')
    parent_by_id = valid_parents.set_index('GlobalID')

    partial_log = []

    def resolve_unique_id(parent_id):
        """
        Resolve an unambiguous plot identifier from a parent record ID.

        :param parent_id: Survey123 parent record identifier.
        :return: Plot unique ID, or pd.NA when the parent cannot be resolved safely.
        """
        if pd.isna(parent_id) or parent_id in duplicate_ids or parent_id not in parent_by_id.index:
            return pd.NA
        return parent_by_id.loc[parent_id].get('unique_id')

    def log_issue(
            parent_id,
            issue_code,
            results_partial,
            detail=None,
            density_missing=False
    ):
        """
        Log one tree-density issue and retain partial-result errors for the summary.

        :param parent_id: Survey123 parent record identifier.
        :param issue_code: Stable machine-readable issue code.
        :param results_partial: Whether the issue caused density to be assigned zero.
        :param detail: Optional human-readable issue detail.
        :param density_missing: Whether protocol failure kept the density missing instead of zero.
        :return: None.
        """
        unique_id = resolve_unique_id(parent_id)
        message = issue_code.replace('_', ' ')
        if detail:
            message = f'{message} ({detail})'
        extra = {'unique_id': unique_id, 'issue_code': issue_code}
        if results_partial:
            outcome = 'left missing' if density_missing else 'assigned zero'
            full_message = f'{message}; affected density {outcome}'
            logger.error(full_message, extra=extra)
            partial_log.append((unique_id, full_message))
        else:
            logger.warning(message, extra=extra)

    # Explicitly absent classes do not require a sampling radius.
    absence = _get_tree_absence(df).set_axis(df['GlobalID']).to_dict()
    # Parent-level radius issues are reported even when no tree used the radius.
    for _, plot in df.iterrows():
        for radius_class in _PLOT_RADIUS_FIELDS:
            if pd.notna(plot.get('GlobalID')) and absence[radius_class].get(plot['GlobalID'], False):
                continue
            issue_code = plot.get(f'_plot_{radius_class}_radius_issue', '')
            if not issue_code:
                continue
            affected_count = len(tree_df[
                tree_df['ParentGlobalID'].eq(plot.get('GlobalID'))
                & tree_df['tree_density_radius_class'].eq(radius_class)
                & tree_df['tree_density_affected']
            ])
            log_issue(plot.get('GlobalID'), issue_code, results_partial=affected_count > 0,
                      detail=radius_class)

    radius_issue_codes = {
        'missing_plot_radius', 'non_numeric_plot_radius',
        'non_positive_plot_radius', 'non_finite_plot_radius',
        'invalid_plot_area', 'invalid_plot_radius',
    }
    # Row-level issues include every independent cause except radius causes,
    # which are represented by their parent survey source above. Each message
    # names the specific tree record so a plot with multiple issues can be
    # traced back to the individual tree: tree_id (the field crew's own tag
    # number) for direct tree_plot_2.csv records, or the sapling-merged
    # record's source table/id when tree_id isn't applicable (saplings are
    # tallied by species, not individually tagged).
    for _, tree in tree_df.iterrows():
        codes = [code for code in str(tree.get('tree_density_issue_codes', '')).split('|') if code]
        if not codes:
            continue
        tree_id = tree.get('tree_id')
        if pd.notna(tree_id):
            if isinstance(tree_id, float) and tree_id.is_integer():
                tree_id = int(tree_id)
            tree_detail = f'tree_id {tree_id}'
        else:
            tree_detail = (
                f"{tree.get('tree_density_source_table', 'unknown source')} "
                f"record {tree.get('tree_density_source_record_id', 'unknown')}"
            )
        for code in codes:
            if code in radius_issue_codes or code == 'tree_sampling_invalid_protocol':
                continue
            is_warning = code == 'sapling_dbh_zero_normalized'
            partial = bool(tree.get('tree_density_affected', False)) and not is_warning
            log_issue(
                tree.get('ParentGlobalID'), code, results_partial=partial, detail=tree_detail,
                density_missing=bool(tree.get('_tree_sampling_issue_code', '')),
            )

    # Invalid sapling counts cannot be synthesized into tree rows, so report
    # them directly from their source table. Parent linkage is also checked at
    # source level so simultaneous causes are not lost.
    known_parent_ids = set(df['GlobalID'].dropna())
    for _, sapling in sapling_df.iterrows():
        # Saplings are tallied by species per plot, not individually tagged like
        # trees, so species is the most specific identifier available for these.
        sapling_detail = f"sapling species {sapling.get('sapling_species')}"
        parent_id = sapling.get('ParentGlobalID')
        parent_code = ''
        if pd.isna(parent_id) or not str(parent_id).strip():
            parent_code = 'missing_parent_id'
        elif parent_id in duplicate_ids:
            parent_code = 'ambiguous_parent_id'
        elif parent_id not in known_parent_ids:
            parent_code = 'orphan_tree_record'
        if parent_code:
            log_issue(
                parent_id, parent_code,
                results_partial=sapling.get('sapling_species') != 'NO_SAPLINGS',
                detail=sapling_detail,
            )

        if sapling.get('sapling_species') == 'NO_SAPLINGS':
            continue
        for status in ('live', 'dead'):
            count_col = f'sapling_{status}_count'
            issue_code = sapling.get(f'_{count_col}_issue', '')
            if issue_code:
                log_issue(parent_id, issue_code, results_partial=True, detail=sapling_detail)

    return partial_log


def _log_tree_sampling_issues(df: pd.DataFrame, tree_df: pd.DataFrame) -> set[str]:
    """
    Report protocol data errors once per affected plot and return its exclusion ID.

    :param df: Parent records with canonical plot identities.
    :param tree_df: Processed tree records carrying sampling issue codes.
    :return: Canonical IDs whose tree-derived results must remain missing.
    """
    issue = tree_df.get('_tree_sampling_issue_code', pd.Series('', index=tree_df.index))
    affected = tree_df.loc[issue.eq('tree_sampling_invalid_protocol')]
    excluded = set()
    for parent_id, records in affected.groupby('ParentGlobalID'):
        parent = df.loc[df['GlobalID'].eq(parent_id)]
        if len(parent) != 1:
            continue
        unique_id = parent.iloc[0]['unique_id']
        column = records['_tree_sampling_protocol_column'].iloc[0]
        logger.error(
            f"Invalid or missing tree sampling protocol in column '{column}' for parent {parent_id}; "
            'tree-derived results left missing for this plot.',
            extra={'unique_id': unique_id, 'issue_code': 'tree_sampling_invalid_protocol'},
        )
        excluded.add(unique_id)
    return excluded


def _merge_saplings_to_trees(tree_df: pd.DataFrame, sapling_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Calculate sapling density for each plot based on the number of saplings per hectare.

    :param tree_df: DataFrame containing individual tree data.
    :param sapling_df: DataFrame containing small sapling data.
    :return: Updated tree_df with a new 'tree_sapling_dens' column for sapling density.
    """
    print('\tMerging sapling data into tree DataFrame')
    # Assign source metadata and a default count to direct tree records.
    tree_df['tree_count'] = 1.0
    if 'tree_density_source_table' not in tree_df.columns:
        tree_df['tree_density_source_table'] = 'tree_plot_2.csv'
    if 'tree_density_source_record_id' not in tree_df.columns:
        tree_df['tree_density_source_record_id'] = tree_df.get(
            'GlobalID', pd.Series(index=tree_df.index, dtype='object')
        )
    if 'tree_density_required' not in tree_df.columns:
        tree_df['tree_density_required'] = True
    if '_tree_dbh_issue' not in tree_df.columns:
        tree_df['_tree_dbh_issue'] = ''
    if '_tree_dbh_warning' not in tree_df.columns:
        tree_df['_tree_dbh_warning'] = ''

    # Retain the legacy zero-to-0.1 sapling normalization for direct helper use.
    # The normal pipeline applies this before height modelling.
    sapling_df['sapling_live_dbh'] = sapling_df['sapling_live_dbh'].replace(0, 0.1)
    sapling_df['sapling_dead_dbh'] = sapling_df['sapling_dead_dbh'].replace(0, 0.1)

    # For each row in sapling_df, create new rows for live and dead saplings in tree_df
    sapling_rows = []
    for _, row in sapling_df.iterrows():
        # Live saplings
        if row['sapling_live_count'] > 0:
            sapling_rows.append({
                'tree_count': row['sapling_live_count'],
                'tree_density_source_table': 'sapling_1.csv',
                'tree_density_source_record_id': row.get('GlobalID'),
                'tree_density_required': True,
                'tree_species': row['sapling_species'],
                'tree_status': 'L',
                'tree_dbh': row['sapling_live_dbh'],
                'tree_ht': row['sapling_live_ht'],
                'tree_cbh': row['sapling_live_cbh'],
                'tree_dcy_class_cnfr': 1 if row['tree_type'] == 'conifer' else np.nan,
                'tree_dcy_class_brdlf': 1 if row['tree_type'] == 'broadleaf' else np.nan,
                'tree_note': '[Fuel Analyst Note] Tree merged from sapling data; ',
                '_tree_dbh_raw': row.get('_sapling_live_dbh_raw', row['sapling_live_dbh']),
                '_tree_dbh_issue': row.get('_sapling_live_dbh_issue', ''),
                '_tree_dbh_warning': row.get('_sapling_live_dbh_warning', ''),
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
                'tree_density_source_table': 'sapling_1.csv',
                'tree_density_source_record_id': row.get('GlobalID'),
                'tree_density_required': True,
                'tree_species': row['sapling_species'],
                'tree_status': 'D',
                'tree_dbh': row['sapling_dead_dbh'],
                'tree_ht': row['sapling_dead_ht'],
                'tree_cbh': np.nan,
                'tree_dcy_class_cnfr': 3 if row['tree_type'] == 'conifer' else np.nan,
                'tree_dcy_class_brdlf': 3 if row['tree_type'] == 'broadleaf' else np.nan,
                'tree_note': '[Fuel Analyst Note] Tree merged from sapling data; ',
                '_tree_dbh_raw': row.get('_sapling_dead_dbh_raw', row['sapling_dead_dbh']),
                '_tree_dbh_issue': row.get('_sapling_dead_dbh_issue', ''),
                '_tree_dbh_warning': row.get('_sapling_dead_dbh_warning', ''),
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


def _normalize_sapling_inputs(sapling_df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize sapling counts and DBH before comparisons or height modelling.

    :param sapling_df: Raw sapling records.
    :return: Sapling records with normalized numeric values and validation fields.
    """
    sapling_df = sapling_df.copy()
    no_saplings = sapling_df['sapling_species'].eq('NO_SAPLINGS')

    for status in ('live', 'dead'):
        count_col = f'sapling_{status}_count'
        dbh_col = f'sapling_{status}_dbh'

        raw_count = sapling_df[count_col].copy()
        count = pd.to_numeric(raw_count, errors='coerce')
        count_issue = _classify_numeric_input(raw_count, count, 'sapling_count', allow_zero=True)
        count_issue.loc[no_saplings] = ''
        count.loc[no_saplings] = 0
        count.loc[count_issue.ne('')] = np.nan
        sapling_df[f'_{count_col}_raw'] = raw_count
        sapling_df[f'_{count_col}_issue'] = count_issue
        sapling_df[count_col] = count

        raw_dbh = sapling_df[dbh_col].copy()
        dbh = pd.to_numeric(raw_dbh, errors='coerce').astype(float)
        dbh_issue = _classify_numeric_input(raw_dbh, dbh, 'sapling_dbh', allow_zero=True)
        positive_count = count.gt(0)
        # Missing DBH for observed saplings follows the existing 2.5 cm
        # imputation path; zero follows the existing 0.1 cm normalization.
        dbh_issue.loc[positive_count & dbh_issue.eq('missing_sapling_dbh')] = ''
        zero_normalized = positive_count & dbh.eq(0) & dbh_issue.eq('')
        dbh.loc[zero_normalized] = 0.1
        invalid_dbh = positive_count & dbh_issue.ne('')
        dbh.loc[invalid_dbh] = np.nan
        dbh.loc[count.eq(0)] = np.nan
        sapling_df[f'_{dbh_col}_raw'] = raw_dbh
        sapling_df[f'_{dbh_col}_issue'] = dbh_issue.where(positive_count, '')
        sapling_df[f'_{dbh_col}_warning'] = np.where(
            zero_normalized, 'sapling_dbh_zero_normalized', ''
        )
        sapling_df[dbh_col] = dbh

    return sapling_df


def _normalize_tree_inputs(tree_df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize direct-tree DBH before rounding and density classification.

    :param tree_df: Raw direct-tree records.
    :return: Tree records with normalized DBH values and validation fields.
    """
    tree_df = tree_df.copy()
    raw_dbh = tree_df['tree_dbh'].copy()
    dbh = pd.to_numeric(raw_dbh, errors='coerce')
    issue = _classify_numeric_input(raw_dbh, dbh, 'tree_dbh', allow_zero=False)
    dbh.loc[issue.ne('')] = np.nan
    tree_df['_tree_dbh_raw'] = raw_dbh
    tree_df['_tree_dbh_issue'] = issue
    tree_df['_tree_dbh_warning'] = ''
    tree_df['tree_dbh'] = dbh
    tree_df['tree_density_source_table'] = 'tree_plot_2.csv'
    tree_df['tree_density_source_record_id'] = tree_df.get('GlobalID', pd.Series(index=tree_df.index, dtype='object'))
    tree_df['tree_density_required'] = True
    tree_df['tree_count'] = 1.0
    return tree_df


def _print_tree_density_summary(partial_log: list[tuple]) -> None:
    """
    Print partial-density results with unresolved IDs labelled consistently.

    :param partial_log: Plot identifiers and messages for density results assigned zero.
    :return: None.
    """
    if not partial_log:
        return

    by_plot = {}
    for unique_id, message in partial_log:
        row_key = error_handling.normalize_unique_id(unique_id)
        by_plot.setdefault(row_key, []).append(message)

    resolved_plot_count = len(by_plot) - int(error_handling.GENERAL_ERROR_ROW in by_plot)
    if resolved_plot_count:
        print(f'\tWARNING: Tree-density results are partial for {resolved_plot_count} plot(s).')
    if error_handling.GENERAL_ERROR_ROW in by_plot:
        print('\tWARNING: Tree-density results are partial for records with unresolved plot IDs.')
    for plot_label, messages in by_plot.items():
        print(f'\t  {plot_label}: {"; ".join(messages)}')
    print('\tSee the run-level error report (fuelanalyst_errors.csv) for full details.')


def _read_tree_repeats(source: table_reader.FormSource, df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Read tree repeats, allowing omitted tables only for explicitly absent classes.

    :param source: Resolved Trees form source.
    :param df: Retained plot parents with optional presence flags.
    :return: Direct-tree and sapling frames, including typed empty repeat schemas
        when absence permits an omitted table. Required missing tables still raise.
    """
    absence = _get_tree_absence(df)
    # These are the fields consumed by the calculation pipeline for an empty repeat.
    tree_columns = (
        'ObjectID GlobalID tree_id tree_species tree_type tree_status tree_dbh tree_ht '
        'tree_cbh tree_dcbh tree_dcy_class_cnfr tree_dcy_class_brdlf tree_ht_class '
        'tree_crwn_broken_top tree_fuel_bed_ht tree_bark_char_high tree_bark_char_low '
        'tree_bark_char_azim tree_crwn_discolor_prcnt tree_crwn_discolor tree_crwn_consumed '
        'tree_basal_char tree_basal_depth_of_burn tree_note ParentGlobalID '
        'CreationDate Creator EditDate Editor'
    ).split()
    sapling_columns = (
        'ObjectID GlobalID sapling_species sapling_live_count sapling_live_dbh '
        'sapling_live_ht sapling_live_cbh sapling_dead_count sapling_dead_dbh '
        'sapling_dead_ht ParentGlobalID CreationDate Creator EditDate Editor'
    ).split()
    frames = []
    for stem, allowed, columns in (
            ('tree_plot_2', (absence['lgtree'] & absence['smtree']).all(), tree_columns),
            ('sapling_1', absence['sapling'].all(), sapling_columns)
    ):
        frame = table_reader.read_table(source, stem, required=not bool(allowed))
        if frame is None:
            frame = pd.DataFrame({column: pd.Series(dtype='object') for column in columns})
        frames.append(frame)
    return frames[0], frames[1]


def _resolve_parent_unique_ids(df: pd.DataFrame, parent_ids: pd.Series) -> pd.Series:
    """
    Map Survey123 parent record IDs to plot unique IDs, leaving ambiguous or unknown parents missing.

    A parent is ambiguous when its GlobalID repeats in the plot table or the plot table marks it ambiguous. This is the
    same rule _log_tree_density_issues() applies to its records.

    :param df: Plot-level DataFrame with GlobalID and unique_id columns, and optionally _parent_id_ambiguous.
    :param parent_ids: Parent record IDs of the tree or sapling records.
    :return: Series of plot unique IDs aligned with parent_ids, missing where the parent cannot be resolved safely.
        A plot with a missing GlobalID never resolves a parent, so a record with no parent is not attributed to it.
    """
    ambiguous = df.get('_parent_id_ambiguous', pd.Series(False, index=df.index)).fillna(False).astype(bool)
    duplicate_ids = set(df.loc[df['GlobalID'].duplicated(keep=False), 'GlobalID'].dropna())
    duplicate_ids.update(df.loc[ambiguous, 'GlobalID'].dropna())
    valid_plots = df.loc[~df['GlobalID'].isin(duplicate_ids) & df['GlobalID'].notna()]
    valid = valid_plots.drop_duplicates('GlobalID').set_index('GlobalID')['unique_id']
    return parent_ids.map(valid)


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


def process_trees(
        in_folder: 'str | table_reader.FormSource',
        out_folder: str,
        surface_fire_intensity_model: str,
        stand_summary_params: dict,
        gen_conpyro_df: bool,
        tree_sampling_params: dict | None = None
) -> tuple[pd.DataFrame, list, pd.DataFrame]:
    """
    Get the tree data from CSV files.

    :param in_folder: Path to the form folder of input tables, or a resolved FormSource.
    :param out_folder: Path to the folder where output CSV files will be saved.
    :param surface_fire_intensity_model: Model to use for calculating surface fireline intensity (default is 'Byram').
        Options: ['Byram', 'Thomas']
    :param stand_summary_params: Dictionary containing stand summary parameters.
    :param gen_conpyro_df: Boolean indicating whether to generate ConPyro DataFrame.
    :param tree_sampling_params: Sampling thresholds and optional parent protocol overrides.
    :return: Tuple containing:
        - Updated DataFrame with plot-level attributes.
        - List of columns to keep in the final DataFrame.
        - Master tree DataFrame with selected attributes for export.
    """
    tree_sampling_params = tree_sampling.normalize_tree_sampling_params(tree_sampling_params)
    print('\nProcessing Tree data')
    in_folder = table_reader.ensure_form_source(in_folder)

    # Initialize list of columns to keep
    keep_columns = []

    # Load tree parameters and set index
    tree_params_df = helper.get_df(
        os.path.join(os.path.dirname(__file__), '../supporting_data', 'tree_parameters.csv')
    ).set_index('Species')

    # ### PROCESS PLOT-LEVEL ATTRIBUTES
    # Get plot dataframe and retain ambiguous parent IDs before survey
    # deduplication selects the latest record.
    protocol_column = tree_sampling_params['protocol_column']
    literal_columns = (protocol_column,) if protocol_column is not None else ()
    df = table_reader.read_table(in_folder, 'survey_0', literal_text_columns=literal_columns)
    ambiguous_parent_ids = set(
        df.loc[df['GlobalID'].notna() & df['GlobalID'].duplicated(keep=False), 'GlobalID']
    )
    # Generate a unique ID for each plot
    df = helper.get_unique_id(df)
    df['_parent_id_ambiguous'] = df['GlobalID'].isin(ambiguous_parent_ids)
    # Calculate plot attributes
    df = _calc_plot_multipliers(df)
    df = _round_plot_data(df)

    # Read the sapling and tree tables, and leave out the plots that record a species that is not in
    # tree_parameters.csv (each is logged), so that the other plots are still calculated
    tree_df, sapling_df = _read_tree_repeats(in_folder, df)
    tree_df, sapling_df = _filter_tree_presence(df, tree_df, sapling_df, tree_sampling_params)
    tree_df, sapling_df, excluded_plot_ids = _exclude_unlisted_species(df, tree_df, sapling_df, tree_params_df)

    # ### PROCESS SAPLING ATTRIBUTES
    # Normalize the sapling dataframe read above
    sapling_df = _normalize_sapling_inputs(sapling_df)
    # Calculate sapling attributes
    sapling_df = _calc_sapling_tree_type(sapling_df, tree_params_df)
    sapling_df = _calc_sapling_density(sapling_df)
    sapling_df = _calc_sapling_dbh(sapling_df)
    sapling_df = _calc_sapling_ht(sapling_df, tree_params_df)

    # ### PROCESS INDIVIDUAL TREE ATTRIBUTES
    # Normalize the tree dataframe read above
    tree_df = _normalize_tree_inputs(tree_df)
    # Merge sapling attributes
    tree_df, sapling_df = _merge_saplings_to_trees(tree_df, sapling_df)
    # Round tree data to appropriate decimal places
    tree_df = _round_tree_data(tree_df)
    # Calculate tree attributes
    tree_df = _calc_tree_dbh_classes(tree_df)
    tree_df = _calc_tree_decay_classes(tree_df)
    tree_df = _calc_tree_type(tree_df, tree_params_df)
    tree_df = _calc_tree_density(df, tree_df, tree_sampling_params=tree_sampling_params)
    sampling_excluded = _log_tree_sampling_issues(df, tree_df)
    excluded_plot_ids = set(excluded_plot_ids) | sampling_excluded
    partial_log = _log_tree_density_issues(df, sapling_df, tree_df)
    tree_df = _calc_tree_basal_area(tree_df)
    tree_df = _calc_tree_missing_heights(tree_df, tree_params_df)
    _log_decayed_tree_height_issues(df, tree_df)
    tree_df = _calc_tree_cbh(tree_df)
    tree_df = _calc_tree_fsg(tree_df)
    tree_df = _calc_tree_crown_depth(tree_df)
    tree_df = _calc_tree_biomass(tree_df, tree_params_df)
    tree_df = _calc_tree_crown_fuels(tree_df, tree_params_df)
    # Calculate FOFEM tree attributes
    tree_df = _calc_tree_fofem_attributes(tree_df, tree_params_df)
    # Calculate fire behavior attributes
    burned_plot_ids = _get_burned_plot_ids(df)
    tree_df = _calc_tree_fire_attributes(tree_df, surface_fire_intensity_model, burned_plot_ids)
    if burned_plot_ids is not None:
        _log_char_on_unburned_plots(df, tree_df, burned_plot_ids)
    # Calculate weighted attributes
    tree_df = _calc_tree_weighted_attributes(tree_df)
    # Master generation also adds live density/BA columns to the diagnostic tree frame.
    master_tree_df = _gen_master_tree_df(df, tree_df)
    # Mask afterwards so dead trees cannot turn unknown live-area values into zero.
    sampling_invalid = tree_df['_tree_sampling_issue_code'].ne('')
    area_columns = [column for column in tree_df if column.endswith('_ha')]
    tree_df.loc[sampling_invalid, area_columns] = np.nan
    master_tree_df.loc[
        master_tree_df['unique_id'].isin(sampling_excluded),
        ['dens_live_ha', 'dens_ha', 'ba_live_ha', 'ba_ha'],
    ] = np.nan

    # ### PROCESS STAND_LEVEL (PER HA) ATTRIBUTES
    if gen_conpyro_df:
        df = _calc_conpyro_live_density(df, tree_df, sapling_df)
        keep_columns.extend(['conpyro_live_tree_density', 'conpyro_live_trees_present'])
    df, add_columns = _calc_stand_composition(df, tree_df, gen_conpyro_df)
    keep_columns.extend(add_columns)
    df, add_columns = _calc_stand_attributes(df, tree_df, stand_summary_params)
    keep_columns.extend(add_columns)
    # A plot left out for an unlisted species has no trees to summarize, so its tree results are missing, not zero
    if excluded_plot_ids:
        tree_columns = [column for column in keep_columns if column in df.columns]
        df[tree_columns] = df[tree_columns].mask(df['unique_id'].isin(excluded_plot_ids))

    # ### SAVE DATASETS TO OUTPUT FOLDER
    os.makedirs(out_folder, exist_ok=True)
    export_df = df.drop(columns=[c for c in df.columns if c.startswith('_')])
    export_sapling_df = sapling_df.drop(
        columns=[c for c in sapling_df.columns if c.startswith('_')]
    )
    export_tree_df = tree_df.drop(
        columns=[c for c in tree_df.columns if c.startswith('_')]
    )
    helper.export_csv(export_df, os.path.join(out_folder, 'survey_0.csv'))
    helper.export_csv(export_sapling_df, os.path.join(out_folder, 'sapling_1.csv'))
    helper.export_csv(export_tree_df, os.path.join(out_folder, 'tree_plot_2.csv'))

    _print_tree_density_summary(partial_log)

    # Mark the plots left out for an unlisted species, so that the model inputs leave them out too; the marker
    # is in the returned table only, never in an output file
    df = helper.attach_columns(export_df, {helper.TREES_EXCLUDED_COLUMN: df['unique_id'].isin(excluded_plot_ids)})

    return df, helper.sort_list(keep_columns), master_tree_df
