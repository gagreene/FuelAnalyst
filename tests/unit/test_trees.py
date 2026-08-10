import numpy as np
import pandas as pd
import pytest

from fuel_analyst.components.trees import (
    _calc_plot_multipliers,
    _calc_sapling_dbh,
    _calc_sapling_density,
    _calc_sapling_tree_type,
    _calc_tree_basal_area,
    _calc_tree_cbh,
    _calc_tree_crown_depth,
    _calc_tree_crown_fuels,
    _calc_tree_dbh_classes,
    _calc_tree_decay_classes,
    _calc_tree_density,
    _calc_tree_fire_attributes,
    _calc_tree_fsg,
    _calc_tree_type,
    _get_temesgen_tree_height,
    _merge_saplings_to_trees,
    _round_plot_data,
    _round_tree_data,
)


def test_calc_plot_multipliers_handles_standard_custom_and_missing_radii():
    df = pd.DataFrame({
        'lgtree_plot_radius': [11.28, 20.0, np.nan],
        'smtree_plot_radius': [5.64, 10.0, np.nan],
        'sapling_plot_radius': [5.64, 10.0, np.nan],
    })
    result = _calc_plot_multipliers(df)
    assert result['plot_lgtree_mult'].tolist()[:2] == [25.0, 50.0]
    assert result['plot_smtree_mult'].tolist()[:2] == [100.0, 200.0]
    assert np.isnan(result.loc[2, 'plot_sapling_mult'])


def test_tree_and_sapling_type_mapping():
    params = pd.DataFrame({'TreeType': ['conifer', 'broadleaf']}, index=['FDI', 'ACT'])
    trees = _calc_tree_type(pd.DataFrame({'tree_species': ['FDI', 'ACT', 'UNK']}), params)
    saplings = _calc_sapling_tree_type(pd.DataFrame({'sapling_species': ['ACT']}), params)
    assert trees['tree_type'].iloc[:2].tolist() == ['conifer', 'broadleaf']
    assert pd.isna(trees.loc[2, 'tree_type'])
    assert saplings.loc[0, 'tree_type'] == 'broadleaf'


def test_calc_sapling_density_zeroes_no_saplings_rows():
    df = pd.DataFrame({
        'sapling_species': ['NO_SAPLINGS', 'FDI'],
        'sapling_live_count': [3, 2], 'sapling_dead_count': [4, 1],
    })
    result = _calc_sapling_density(df)
    assert result.loc[0, ['sapling_live_count', 'sapling_dead_count']].tolist() == [0, 0]
    assert result.loc[1, ['sapling_live_count', 'sapling_dead_count']].tolist() == [2, 1]


def test_calc_sapling_dbh_defaults_present_missing_values_and_clears_absent_values():
    df = pd.DataFrame({
        'sapling_live_count': [1, 0], 'sapling_live_dbh': [np.nan, 3.0],
        'sapling_dead_count': [1, 0], 'sapling_dead_dbh': [np.nan, 4.0],
    })
    result = _calc_sapling_dbh(df)
    assert result.loc[0, 'sapling_live_dbh'] == 2.5
    assert result.loc[0, 'sapling_dead_dbh'] == 2.5
    assert 'Live sapling DBH' in result.loc[0, 'sapling_dbh_comment']
    assert 'Dead sapling DBH' in result.loc[0, 'sapling_dbh_comment']
    assert np.isnan(result.loc[1, 'sapling_live_dbh'])


def test_calc_tree_basal_area_uses_density_weighting():
    result = _calc_tree_basal_area(pd.DataFrame({'tree_dbh': [20.0], 'tree_dens_ha': [100.0]}))
    expected = np.pi * 0.1 ** 2
    assert result.loc[0, 'tree_ba'] == pytest.approx(expected)
    assert result.loc[0, 'tree_ba_ha'] == pytest.approx(100 * expected)


def test_tree_classification_boundaries_and_decay_combination():
    df = pd.DataFrame({
        'tree_dbh': [30.0, 12.5, 7.5, 7.49],
        'tree_dcy_class_cnfr': [1, np.nan, 0, np.nan],
        'tree_dcy_class_brdlf': [np.nan, 2, 0, np.nan],
    })
    result = _calc_tree_decay_classes(_calc_tree_dbh_classes(df))
    assert result['tree_dbh_class_bc'].tolist() == ['1D', '1M', '2', '3']
    assert result['tree_dcy_class'].iloc[:2].tolist() == [1.0, 2.0]
    assert result['tree_dcy_class'].iloc[2:].isna().all()


def test_tree_density_selects_plot_multiplier_by_dbh_and_tree_count():
    plots = pd.DataFrame({
        'GlobalID': ['p1'], 'plot_lgtree_mult': [25],
        'plot_smtree_mult': [100], 'plot_sapling_mult': [200],
    })
    trees = pd.DataFrame({'ParentGlobalID': ['p1'] * 3, 'tree_dbh': [12.5, 5.0, 4.9], 'tree_count': [2, 2, 2]})
    assert _calc_tree_density(plots, trees)['tree_dens_ha'].tolist() == [50, 200, 400]


def test_tree_cbh_cleanup_crown_depth_and_crown_fuels():
    trees = pd.DataFrame({
        'tree_status': ['L', 'D'], 'tree_cbh': [99.0, 99.0], 'tree_ht': [10.0, 10.0],
        'tree_species': ['FDI', 'FDI'], 'tree_dbh': [20.0, 20.0],
        'tree_foliage_cnbe_ha': [4.0, 4.0],
    })
    cleaned = _calc_tree_cbh(trees)
    assert np.isnan(cleaned.loc[0, 'tree_cbh'])
    assert cleaned.loc[1, 'tree_cbh'] == 99
    cleaned.loc[0, 'tree_cbh'] = 6
    result = _calc_tree_crown_fuels(_calc_tree_crown_depth(cleaned), pd.DataFrame())
    assert result.loc[0, 'tree_crwn_dpth'] == 4
    assert result.loc[0, 'tree_cfl_cnbe_ha'] == 4
    assert result.loc[0, 'tree_cbd_cnbe_ha'] == 1
    assert result.loc[1, 'tree_cfl_cnbe_ha'] == 0


def test_calc_tree_fsg_handles_live_dead_and_overlapping_fuel_beds():
    df = pd.DataFrame({
        'tree_status': ['L', 'L', 'L', 'D'],
        'tree_cbh': [5.0, 8.0, 1.0, 5.0],
        'tree_dcbh': [8.0, 4.0, 3.0, 8.0],
        'tree_fuel_bed_ht': [2.0, 1.0, 2.0, 1.0],
    })
    result = _calc_tree_fsg(df)
    assert result['tree_fsg'].iloc[:3].tolist() == [3.0, 3.0, 0.0]
    assert np.isnan(result.loc[3, 'tree_fsg'])


def test_calc_tree_fire_attributes_uses_crown_sentinel_and_surface_model():
    df = pd.DataFrame({
        'tree_bark_char_high': [444.0, 2.0],
        'tree_ht': [10.0, 10.0],
    })
    result = _calc_tree_fire_attributes(df, 'Thomas')
    assert result.loc[0, 'tree_bark_char_high'] == 10.0
    assert result.loc[0, 'tree_fire_intensity'] == pytest.approx((18.0 / 0.0175) ** 1.5)
    assert result.loc[1, 'tree_fire_intensity'] == pytest.approx((3.6 / 0.0267) ** 1.5)


def test_temesgen_height_models_and_invalid_model():
    params = pd.DataFrame({
        'Temesgen_M2a': [20.0], 'Temesgen_M2b': [0.1], 'Temesgen_M2c': [1.0],
        'Temesgen_M7a1': [20.0], 'Temesgen_M7a2': [0.0], 'Temesgen_M7a3': [0.0],
        'Temesgen_M7a4': [0.0], 'Temesgen_M7a5': [1.0], 'Temesgen_M7a6': [0.0],
        'Temesgen_M7b': [0.1],
    }, index=['FDI'])
    expected = 1.3 + 20 * (1 - np.exp(-1))
    assert _get_temesgen_tree_height(2, params, 'FDI', 10) == pytest.approx(expected)
    assert _get_temesgen_tree_height(7, params, 'FDI', 10, 0, 0, 0) == pytest.approx(expected)
    assert np.isnan(_get_temesgen_tree_height(99, params, 'FDI', 10))


def test_merge_saplings_to_trees_creates_live_and_dead_rows():
    trees = pd.DataFrame({'tree_species': ['FDI']})
    saplings = pd.DataFrame({
        'sapling_species': ['ACT'], 'tree_type': ['broadleaf'],
        'sapling_live_count': [2], 'sapling_live_dbh': [0.0], 'sapling_live_ht': [1.5],
        'sapling_live_cbh': [0.5], 'sapling_dead_count': [1], 'sapling_dead_dbh': [2.0],
        'sapling_dead_ht': [1.0], 'ParentGlobalID': ['p1'],
    })
    result, normalized = _merge_saplings_to_trees(trees, saplings)
    assert len(result) == 3
    assert result.iloc[1:]['tree_status'].tolist() == ['L', 'D']
    assert normalized.loc[0, 'sapling_live_dbh'] == 0.1


def test_rounding_helpers_apply_documented_precision():
    plots = pd.DataFrame({'lgtree_plot_radius': [1.234], 'smtree_plot_radius': [2.345], 'sapling_plot_radius': [3.456]})
    assert _round_plot_data(plots).iloc[0].tolist() == [1.23, 2.35, 3.46]
    trees = pd.DataFrame({
        'tree_dbh': [1.25], 'tree_ht': [2.25], 'tree_cbh': [3.25], 'tree_dcbh': [4.25],
        'tree_bark_char_high': [1.234], 'tree_bark_char_low': [2.345], 'tree_bark_char_azim': [3.456],
    })
    result = _round_tree_data(trees)
    assert result.loc[0, 'tree_dbh'] == 1.2
    assert result.loc[0, 'tree_bark_char_high'] == 1.23
