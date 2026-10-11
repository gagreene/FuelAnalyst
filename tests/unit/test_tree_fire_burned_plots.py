"""Flame length and fire intensity are calculated only for burned plots, and stand means use only valued trees."""

import logging

import numpy as np
import pandas as pd
import pytest

from fuel_analyst.components.trees import (
    _calc_stand_attributes,
    _calc_tree_fire_attributes,
    _calc_tree_weighted_attributes,
    _get_burned_plot_ids,
    _log_char_on_unburned_plots,
)
from fuel_analyst.fuel_analyst import default_stand_summary_dict


def _plots(treatment_types: list) -> pd.DataFrame:
    return pd.DataFrame({
        'GlobalID': [f'plot-{i}' for i in range(len(treatment_types))],
        'unique_id': [f'P{i}' for i in range(len(treatment_types))],
        'treatment_type': treatment_types,
    })


def test_burned_plot_ids_match_burned_treatment_type_ignoring_case_and_spaces() -> None:
    plots = _plots(['burned', ' Burned ', 'untreated', 'treated', np.nan])

    assert _get_burned_plot_ids(plots) == {'plot-0', 'plot-1'}


def test_burned_plot_ids_are_none_without_a_treatment_type_column() -> None:
    assert _get_burned_plot_ids(pd.DataFrame({'GlobalID': ['plot-0']})) is None


def test_fire_attributes_skip_unburned_plots_and_set_missing_burned_values_to_zero() -> None:
    tree_df = pd.DataFrame({
        'ParentGlobalID': ['burned', 'burned', 'unburned', 'unburned'],
        'tree_bark_char_high': [1.0, np.nan, np.nan, 2.0],
        'tree_ht': [10.0, 10.0, 10.0, 10.0],
    })

    result = _calc_tree_fire_attributes(tree_df, 'Byram', burned_plot_ids={'burned'})

    assert result['tree_flame_length'].iloc[0] == pytest.approx(1.8)
    assert result['tree_fire_intensity'].iloc[0] > 0
    # A burned tree without a char height is recorded as 0, not as missing
    assert result['tree_flame_length'].iloc[1] == 0.0
    assert result['tree_fire_intensity'].iloc[1] == 0.0
    # Unburned plots are left out, even where a char height was recorded
    assert result['tree_flame_length'].iloc[2:].isna().all()
    assert result['tree_fire_intensity'].iloc[2:].isna().all()


def test_fire_attributes_keep_invalid_trees_of_burned_plots_missing() -> None:
    """A record with no basal area (such as a missing DBH) is not a tree, so it must not become a zero value."""
    tree_df = pd.DataFrame({
        'ParentGlobalID': ['burned', 'burned'],
        'tree_bark_char_high': [np.nan, np.nan],
        'tree_ht': [10.0, 10.0],
        'tree_ba_ha': [5.0, np.nan],
    })

    result = _calc_tree_fire_attributes(tree_df, 'Byram', burned_plot_ids={'burned'})

    assert result['tree_flame_length'].tolist()[0] == 0.0
    assert np.isnan(result['tree_flame_length'].iloc[1])
    assert np.isnan(result['tree_fire_intensity'].iloc[1])


def test_fire_attributes_without_burned_plot_ids_keep_missing_values_missing() -> None:
    tree_df = pd.DataFrame({
        'ParentGlobalID': ['p', 'p'], 'tree_bark_char_high': [1.0, np.nan], 'tree_ht': [10.0, 10.0],
    })

    result = _calc_tree_fire_attributes(tree_df, 'Byram')

    assert result['tree_flame_length'].iloc[0] == pytest.approx(1.8)
    assert np.isnan(result['tree_flame_length'].iloc[1])


def test_char_height_on_an_unburned_plot_is_reported(caplog) -> None:
    plots = _plots(['burned', 'untreated', 'untreated'])
    tree_df = pd.DataFrame({
        'ParentGlobalID': ['plot-0', 'plot-1', 'plot-2'],
        'tree_bark_char_high': [1.0, 2.0, np.nan],
    })

    with caplog.at_level(logging.WARNING, logger='fuel_analyst.components.trees'):
        _log_char_on_unburned_plots(plots, tree_df, {'plot-0'})

    records = [r for r in caplog.records if getattr(r, 'issue_code', None) == 'char_height_on_unburned_plot']
    assert [r.unique_id for r in records] == ['P1']


def _stand_means(tree_df: pd.DataFrame, plot_ids: list, att: str) -> pd.DataFrame:
    tree_df = _calc_tree_weighted_attributes(tree_df)
    plot_df = pd.DataFrame({'GlobalID': plot_ids})
    params = {att: default_stand_summary_dict[att]}
    result, _ = _calc_stand_attributes(plot_df, tree_df, params)
    return result.set_index('GlobalID')


def _fire_tree_df(rows: list) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=['ParentGlobalID', 'tree_flame_length', 'tree_ba_ha'])
    for att in ('ht', 'cbh', 'dcbh', 'fsg', 'crwn_dpth', 'fire_intensity'):
        df[f'tree_{att}'] = np.nan
    df['tree_status'] = 'L'
    df['tree_type'] = 'conifer'
    df['tree_dbh'] = 20.0
    df['tree_dens_ha'] = 1.0
    return df


def test_stand_flame_length_is_missing_for_unburned_plots_and_includes_zero_valued_burned_trees() -> None:
    tree_df = _fire_tree_df([
        ('burned', 1.8, 10.0), ('burned', 0.0, 10.0),
        ('unburned', np.nan, 10.0), ('unburned', np.nan, 5.0),
    ])

    result = _stand_means(tree_df, ['burned', 'unburned'], 'flame_length')

    assert result.loc['burned', 'stand_flame_length_m_mean'] == pytest.approx(0.9)
    assert np.isnan(result.loc['unburned', 'stand_flame_length_m_mean'])
    assert np.isnan(result.loc['unburned', 'stand_flame_length_m_min'])
    assert np.isnan(result.loc['unburned', 'stand_flame_length_m_max'])


def _cbh_tree_df(rows: list) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=['ParentGlobalID', 'tree_status', 'tree_cbh', 'tree_ba_ha'])
    for att in ('ht', 'dcbh', 'fsg', 'crwn_dpth', 'flame_length', 'fire_intensity'):
        df[f'tree_{att}'] = np.nan
    df['tree_type'] = 'conifer'
    df['tree_dbh'] = 20.0
    df['tree_dens_ha'] = 1.0
    return df


def test_stand_mean_ignores_the_basal_area_of_trees_without_a_value() -> None:
    """A dead tree with no crown base height must not pull the mean of the trees that have one toward zero."""
    tree_df = _cbh_tree_df([('p', 'L', 4.0, 10.0), ('p', 'D', np.nan, 10.0)])

    result = _stand_means(tree_df, ['p'], 'cbh')

    assert result.loc['p', 'stand_cbh_m_mean'] == pytest.approx(4.0)


def test_stand_mean_is_missing_when_no_tree_has_a_value() -> None:
    tree_df = _cbh_tree_df([('p', 'D', np.nan, 10.0), ('p', 'D', np.nan, 5.0)])

    result = _stand_means(tree_df, ['p'], 'cbh')

    assert np.isnan(result.loc['p', 'stand_cbh_m_mean'])


def test_stand_mean_is_unchanged_when_every_tree_has_a_value() -> None:
    tree_df = _cbh_tree_df([('p', 'L', 4.0, 10.0), ('p', 'L', 2.0, 5.0)])

    result = _stand_means(tree_df, ['p'], 'cbh')

    assert result.loc['p', 'stand_cbh_m_mean'] == pytest.approx((4.0 * 10 + 2.0 * 5) / 15)
