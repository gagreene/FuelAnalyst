# -*- coding: utf-8 -*-
"""
Created on Tue Oct 21, 09:00:00 2025

@author: Gregory A. Greene
"""
__author__ = ['Gregory A. Greene']

import logging
import os
import numpy as np
import pandas as pd

from . import helper

logger = logging.getLogger(__name__)


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
    :return: DataFrame with an added 'conpyro_density_class' column; logs a warning
        per plot with missing source cover without changing the input values.
    """
    # Calculate stand density class from canopy cover
    mask_l = (df[cc_field] >= 0) & (df[cc_field] <= 45)
    mask_m = (df[cc_field] > 45) & (df[cc_field] <= 60)
    mask_h = (df[cc_field] > 60) & (df[cc_field] <= 100)

    density_class = pd.Series([None] * len(df), index=df.index, dtype=object)
    density_class.loc[mask_l] = 'L'
    density_class.loc[mask_m] = 'M'
    density_class.loc[mask_h] = 'H'

    # Report the source value before gen_conpyro_df separately fills exported cover with zero.
    missing_cover = df[cc_field].isna()
    plot_ids = df.get('unique_id', pd.Series(pd.NA, index=df.index))
    for unique_id in plot_ids.loc[missing_cover].drop_duplicates():
        logger.warning(
            f"Canopy cover in '{cc_field}' is missing; ConPyro stand_density cannot be assigned. "
            'stand_density is a canopy-cover class (L/M/H), not trees per hectare; '
            'live trees may still be present. Check canopy observations and plot links, then '
            'regenerate the ConPyro input CSV and weather merge. A zero-filled exported '
            'canopy_cover does not establish measured zero cover or supply a density class.',
            extra={'unique_id': unique_id, 'issue_code': 'conpyro_missing_canopy_cover'},
        )

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
    unknown_by_plot = {}
    for (row_label, _), code in unknown_codes.items():
        unknown_by_plot.setdefault(stand_type_df.loc[row_label, 'unique_id'], []).append(code)
    for unique_id, codes in unknown_by_plot.items():
        logger.error(
            f"Species code(s) {', '.join(repr(code) for code in dict.fromkeys(codes))} in SPECIES_CD_1 to SPECIES_CD_6 "
            f"are not in tree_parameters.csv; the stand type for this plot was left empty.",
            extra={'unique_id': unique_id, 'issue_code': 'stand_type_species_not_in_table'},
        )
    unknown_plot = stand_type_df['unique_id'].isin(unknown_by_plot)

    stand_type_df[spp_code_cols] = pd.DataFrame(
        {column: stand_type_df[column].map(tree_type_lookup) for column in spp_code_cols},
        index=stand_type_df.index,
    )
    stand_type_df['tree_type'] = _join_first_seen_unique_types(stand_type_df[spp_code_cols])
    stand_type_df.loc[unknown_plot, 'tree_type'] = ''
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

    # A plot with a species code that is not in the table gets no stand type, whatever its other codes give
    conpyro_stand_type.loc[df['unique_id'].isin(unknown_by_plot)] = ''

    stand_columns = {
        'tree_type': tree_type,
        'conpyro_stand_type': conpyro_stand_type,
    }
    return helper.attach_columns(df, stand_columns)


def _calc_surface_models(df: pd.DataFrame, model_settings: dict) -> pd.DataFrame:
    """
    Assign surface models from live-tree presence and observed dominant substrate.

    :param df: Plot attributes with live-tree presence/density, dom_substrate, and pc_flammable.
    :param model_settings: Forest, grass_herbs and shrubs surface-model selections.
    :return: Copy with surface_fuel_type and sros_model; log missing inputs and nonfuel decisions.
    """
    from .._vendor.conpyro.components.equations.conpyro_eqs import normalize_sros_model

    models = {}
    for category in ('forest', 'grass_herbs', 'shrubs'):
        value = model_settings.get(category) if isinstance(model_settings, dict) else None
        if isinstance(value, (bool, np.bool_)) or value is None or not np.isscalar(value):
            raise ValueError(f'sros_model.{category} must be a valid ConPyro surface model.')
        try:
            normalized = normalize_sros_model(value)
            if np.ma.getmaskarray(normalized).any():
                raise ValueError('Surface model cannot be missing')
            models[category] = int(normalized.item())
        except (TypeError, ValueError, OverflowError) as error:
            raise ValueError(f'Invalid sros_model.{category}: {value!r}') from error

    result = df.copy()
    density = result.get('conpyro_live_tree_density', pd.Series(np.nan, index=result.index))
    present = result.get('conpyro_live_trees_present', density.gt(0).astype('boolean').mask(density.isna()))
    substrate = result.get('dom_substrate', pd.Series('', index=result.index))
    excluded = helper.get_tree_excluded_plots(result)
    category = pd.Series('', index=result.index, dtype=object)
    category.loc[present.eq(True) & ~excluded] = 'forest'
    category.loc[present.eq(False) & substrate.isin(['HG', 'HF', 'HE']) & ~excluded] = 'grass_herbs'
    category.loc[present.eq(False) & substrate.isin(['SL', 'ST']) & ~excluded] = 'shrubs'
    flammable = pd.to_numeric(
        result.get('pc_flammable', pd.Series(np.nan, index=result.index)), errors='coerce')
    for idx in result.index[substrate.eq('BY') & category.eq('')]:
        reasons = []
        if excluded.loc[idx]:
            reasons.append('tree inputs were excluded')
        elif pd.isna(present.loc[idx]):
            reasons.append('live-tree presence is unresolved')
        value = flammable.loc[idx]
        if pd.isna(value):
            reasons.append('pc_flammable is missing or nonnumeric')
        elif not np.isfinite(value) or not 0 <= value <= 100:
            reasons.append(f'pc_flammable is outside 0-100: {value!r}')
        if reasons:
            category.loc[idx] = 'nonfuel_error'
            logger.error(
                'SROS model not assigned: %s. Set sros_model=None and stand_type=0 as a '
                'processing fallback. Non-burning outputs do not establish nonfuel conditions.',
                '; '.join(reasons),
                extra={'unique_id': result.at[idx, 'unique_id'],
                       'issue_code': 'conpyro_by_missing_inputs'},
            )
        elif value == 0:
            category.loc[idx] = 'nonfuel'
            logger.info(
                'No flammable substrate recorded (pc_flammable=0). Set sros_model=None and '
                'stand_type=0; plot treated as nonfuel.',
                extra={'unique_id': result.at[idx, 'unique_id'],
                       'issue_code': 'conpyro_by_nonflammable'},
            )
        else:
            category.loc[idx] = 'forest_floor'
    result['surface_fuel_type'] = category
    result['sros_model'] = category.map({**models, 'forest_floor': 1})
    for plot_id in result.loc[category.eq(''), 'unique_id'].drop_duplicates():
        logger.warning(
            'Surface model not assigned: live-tree observations are missing/excluded or the '
            'treeless plot has no supported grass/herb or shrub dominant substrate.',
            extra={'unique_id': plot_id, 'issue_code': 'conpyro_surface_model_unassigned'},
        )
    return result


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


def _join_first_seen_unique_types(columns: pd.DataFrame) -> pd.Series:
    """
    Join each row's unique values across ordered columns, preserving first-seen order.

    :param columns: DataFrame of per-row candidate values, in the column order that
        determines first-seen priority.
    :return: Series with each row's non-null unique values joined by a single space,
        in the order they first appear across the columns.
    """
    # Missing values are tracked with masks, not a placeholder value: Arrow-backed string columns (pandas 3 with pyarrow
    # installed) cannot be compared with an arbitrary object.
    present = columns.notna()
    column_names = list(columns.columns)
    joined = pd.Series('', index=columns.index)
    for position, column in enumerate(column_names):
        first_seen = present[column].astype(bool)
        for earlier_column in column_names[:position]:
            same_as_earlier = (columns[column] == columns[earlier_column]).fillna(False).astype(bool)
            first_seen &= ~same_as_earlier
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

    from ._default_configs import default_conpyro_dict

    df = _calc_surface_models(df, conpyro_params.get('sros_model', default_conpyro_dict['sros_model']))
    df = _calc_stand_type(df, tree_params_df)
    open_fuel = df['surface_fuel_type'].isin(['grass_herbs', 'shrubs'])
    by_surface = df['surface_fuel_type'].eq('forest_floor')
    nonfuel = df['surface_fuel_type'].isin(['nonfuel', 'nonfuel_error'])
    no_canopy = open_fuel | by_surface | nonfuel
    cover_column = conpyro_params['canopy_cover_attribute']
    df[cover_column] = df[cover_column].mask(no_canopy, 0.)
    df = _calc_stand_density(df, cover_column)
    df = _calc_veg_fuel_loads(df, conpyro_params['vegetative_fuel_loads'])
    fbp_prep_df = _prep_fbp_df(df)

    # A plot left out of the tree calculations has no canopy fuel values, and the fill with 0 below would model it with
    # canopy fuels that were never calculated. Its stand type and density stay empty instead, so run_conpyro() leaves
    # it out. BY error fallbacks below instead retain the plot with explicit stand code zero.
    tree_excluded = helper.get_tree_excluded_plots(df)

    # Build DataFrame
    conpyro_df = pd.DataFrame({
        'unique_id': df['unique_id'],
        'plot_id': df['plot_id'],
        'lat': df['y'],
        'long': df['x'],
        'elevation': df['plot_elevation'],
        'slope': df['plot_slope_pct'],
        'aspect': df['plot_aspect'],  # slope==0 -> 270 already forced upstream in plot_attributes.py
        'stand_density': df['conpyro_density_class'].mask(open_fuel, 'L').mask(tree_excluded),
        'stand_type': df['conpyro_stand_type'].astype(object).mask(open_fuel, 10).mask(tree_excluded, ''),
        'surface_fuel_type': df['surface_fuel_type'],
        'sros_model': df['sros_model'],
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

    # Confirmed treeless surface fuels have no live canopy geometry.
    conpyro_df.loc[open_fuel, ['canopy_cover', 'ht_ovrstry_live', 'cbh_ovrstry', 'fsg']] = 0.

    # Excluded tree inputs are unknown, not measured zero canopy fuel.
    tree_columns = [
        'pct_cnfr', 'cfl_ovrstry', 'cbd_ovrstry', 'cfl_midstry', 'cbd_midstry',
        'dead_branch_fl_midstry', 'ht_ovrstry_live', 'ht_midstry_live',
        'ht_midstry_dead', 'cbh_ovrstry', 'cbh_midstry', 'fsg',
    ]
    # BY forest-floor fuel and explicit nonfuel rows must reach the runner with
    # usable routing metadata. These canopy zeros are model inputs, not new observations.
    conpyro_df.loc[by_surface | nonfuel, tree_columns + ['canopy_cover']] = 0.
    conpyro_df.loc[by_surface | nonfuel, 'stand_density'] = 'L'
    conpyro_df.loc[by_surface, 'stand_type'] = 10
    conpyro_df.loc[nonfuel, 'stand_type'] = 0
    conpyro_df.loc[by_surface | nonfuel,
                   ['herbaceous_fuel_load', 'grass_fuel_load', 'shrub_fuel_load']] = 0.
    conpyro_df.loc[tree_excluded, tree_columns] = np.nan

    return conpyro_df, fbp_prep_df
