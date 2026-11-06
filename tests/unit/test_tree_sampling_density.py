import numpy as np
import pandas as pd
import pytest

from fuel_analyst.components import trees


def _plots(ids=('p1',), small_radius=5.64):
    return trees._calc_plot_multipliers(pd.DataFrame({
        'GlobalID': list(ids), 'unique_id': [f'plot_{value}' for value in ids],
        'lgtree_plot_radius': [11.28] * len(ids),
        'smtree_plot_radius': [small_radius] * len(ids),
        'sapling_plot_radius': [3.99] * len(ids),
    }))


@pytest.mark.parametrize('cbh', [2., 99.])
def test_blank_tree_notes_accept_cbh_normalization(cbh):
    frame = pd.DataFrame({'tree_status': ['L'], 'tree_cbh': [cbh], 'tree_note': [np.nan]})
    result = trees._calc_tree_cbh(frame)
    if cbh == 99:
        assert pd.isna(result.loc[0, 'tree_cbh'])
        assert 'entered as 99' in result.loc[0, 'tree_note']
    else:
        assert result.loc[0, 'tree_cbh'] == cbh
        assert pd.isna(result.loc[0, 'tree_note'])


@pytest.mark.parametrize('small', [0.0, 2.0, 5.0])
def test_custom_cutoff_never_moves_aggregated_saplings(small):
    result = trees._calc_tree_density(_plots(), pd.DataFrame({
        'ParentGlobalID': ['p1'], 'tree_dbh': [2.5], 'tree_count': [3],
        'tree_density_source_table': ['sapling_1.csv'],
    }), {'dbh_thresholds_cm': {'small_tree_min': small, 'large_tree_min': 9}})
    assert result.tree_dens_ha.tolist() == [600]


def test_default_and_nfi_boundaries_and_rounding():
    frame = pd.DataFrame({'ParentGlobalID': ['p1'] * 5,
                          'tree_dbh': [4.9, 5.0, 8.9, 9.0, 12.4], 'tree_count': [1] * 5})
    result = trees._calc_tree_density(_plots(small_radius=3.99), frame,
                                     {'dbh_thresholds_cm': {'large_tree_min': 9}})
    assert result.tree_dens_ha.tolist() == [200, 200, 200, 25, 25]
    assert result.tree_density_radius_class.tolist() == ['sapling', 'smtree', 'smtree', 'lgtree', 'lgtree']
    frame = pd.DataFrame({'ParentGlobalID': ['p1'] * 3, 'tree_dbh': [8.96, 9.04, 9.06],
                          'tree_count': [1] * 3, 'tree_ht': [1.] * 3, 'tree_cbh': [0.] * 3,
                          'tree_dcbh': [0.] * 3, 'tree_bark_char_high': [0.] * 3,
                          'tree_bark_char_low': [0.] * 3, 'tree_bark_char_azim': [0.] * 3})
    frame = trees._round_tree_data(frame)
    result = trees._calc_tree_density(_plots(), frame, {'dbh_thresholds_cm': {'large_tree_min': 9.05}})
    assert result.tree_dens_ha.tolist() == [100, 100, 25]
    result = trees._calc_tree_density(_plots(), frame, {'dbh_thresholds_cm': {'large_tree_min': 9}})
    assert result.tree_dens_ha.tolist() == [25, 25, 25]


def test_empty_sapling_repeat_normalizes_without_integer_assignment_error():
    empty = pd.DataFrame(columns=['sapling_species', 'sapling_live_count', 'sapling_dead_count',
                                  'sapling_live_dbh', 'sapling_dead_dbh'])
    assert trees._normalize_sapling_inputs(empty).empty


def test_imputed_dbh_and_merged_sapling_counts_keep_source_area():
    saplings = pd.DataFrame({
        'ParentGlobalID': ['p1'], 'GlobalID': ['s1'], 'sapling_species': ['FDI'],
        'sapling_live_count': [3], 'sapling_dead_count': [2],
        'sapling_live_dbh': [np.nan], 'sapling_dead_dbh': [6.],
        'sapling_live_ht': [3.], 'sapling_dead_ht': [4.],
        'sapling_live_cbh': [1.], 'tree_type': ['conifer'],
    })
    saplings = trees._calc_sapling_dbh(saplings)
    assert saplings.sapling_live_dbh.tolist() == [2.5]
    merged, _ = trees._merge_saplings_to_trees(
        pd.DataFrame(columns=['GlobalID', 'ParentGlobalID', 'tree_dbh']), saplings
    )
    result = trees._calc_tree_density(_plots(), merged,
                                     {'dbh_thresholds_cm': {'small_tree_min': 2.0}})
    assert result.tree_status.tolist() == ['L', 'D']
    assert result.tree_dens_ha.tolist() == [600, 400]


def test_mixed_protocol_counts_and_row_order():
    plots = _plots(('nfi', 'cwc'))
    plots['protocol'] = ['NFI', 'CWC']
    settings = {'protocol_column': 'protocol', 'protocol_overrides': {'CWC': {}, 'NFI': {'large_tree_min': 9}}}
    frame = pd.DataFrame({'ParentGlobalID': ['cwc', 'nfi'], 'tree_dbh': [10., 10.], 'tree_count': [2, 2]})
    result = trees._calc_tree_density(plots.iloc[::-1], frame, settings)
    assert result.tree_dens_ha.tolist() == [200, 50]


@pytest.mark.parametrize('missing_column', [False, True])
def test_protocol_errors_are_missing_and_logged_once_per_eligible_parent(caplog, missing_column):
    plots = _plots(('good', 'bad', 'unused', 'duplicate', 'duplicate', 'marked', ''))
    if not missing_column:
        plots['protocol'] = ['CWC', 'typo', '', '', '', '', '']
    plots['_parent_id_ambiguous'] = [False] * 5 + [True, False]
    settings = {'protocol_column': 'protocol', 'protocol_overrides': {'CWC': {}}}
    frame = pd.DataFrame({
        'ParentGlobalID': ['good', 'bad', 'bad', 'duplicate', 'marked', '', 'orphan'],
        'tree_dbh': [10., 10., np.nan, 10., 10., 10., 10.], 'tree_count': [1] * 7,
    })
    result = trees._calc_tree_density(plots, frame, settings)
    assert result.loc[[1, 2], 'tree_dens_ha'].isna().all()
    assert result.loc[[1, 2], 'tree_density_multiplier'].isna().all()
    assert result.loc[3:, 'tree_dens_ha'].eq(0).all()
    assert result.loc[3:, '_tree_sampling_issue_code'].eq('').all()
    if missing_column:
        assert np.isnan(result.loc[0, 'tree_dens_ha'])
    else:
        assert result.loc[0, 'tree_dens_ha'] == 100
    with caplog.at_level('ERROR'):
        excluded = trees._log_tree_sampling_issues(plots, result)
        trees._log_tree_density_issues(plots, pd.DataFrame(), result)
    expected = {'plot_bad', 'plot_good'} if missing_column else {'plot_bad'}
    assert excluded == expected
    entries = [r for r in caplog.records if getattr(r, 'issue_code', '') == 'tree_sampling_invalid_protocol']
    assert len(entries) == len(expected)
    assert {r.unique_id for r in entries} == expected
    assert all('assigned zero' not in r.getMessage() for r in entries)
    bad_messages = [r.getMessage() for r in caplog.records if str(getattr(r, 'unique_id', None)) == 'plot_bad']
    assert all('assigned zero' not in message for message in bad_messages)


def test_protocol_missing_on_unused_parents_does_not_require_column():
    settings = {'protocol_column': 'protocol', 'protocol_overrides': {'CWC': {}}}
    result = trees._calc_tree_density(_plots(), pd.DataFrame({
        'ParentGlobalID': ['orphan'], 'tree_dbh': [10.], 'tree_count': [1],
    }), settings)
    assert result.tree_dens_ha.tolist() == [0]
    assert result['_tree_sampling_issue_code'].eq('').all()


@pytest.mark.parametrize('status', ['L', 'D'])
def test_sapling_source_keeps_counted_area_above_dbh_boundaries(status):
    frame = pd.DataFrame({
        'ParentGlobalID': ['p1'] * 6, 'tree_dbh': [2.5, 5.0, 13.0] * 2,
        'tree_count': [3] * 6, 'tree_status': [status] * 6,
        'tree_density_source_table': ['sapling_1.csv'] * 3 + ['tree_plot_2.csv'] * 3,
    })
    result = trees._calc_tree_density(_plots(), frame)
    assert result.tree_dens_ha.tolist() == [600, 600, 600, 600, 300, 75]
    assert result.tree_density_radius_class.tolist() == ['sapling'] * 4 + ['smtree', 'lgtree']


def test_sapling_source_preserves_invalid_dbh_and_zero_count_handling():
    frame = pd.DataFrame({
        'ParentGlobalID': ['p1'] * 2, 'tree_dbh': [np.nan, 5.0], 'tree_count': [3, 0],
        'tree_density_source_table': ['sapling_1.csv'] * 2,
    })
    result = trees._calc_tree_density(_plots(), frame)
    assert result.tree_dens_ha.tolist() == [0, 0]
    assert result.tree_density_input_valid.tolist() == [False, True]
    assert result.loc[1, 'tree_density_multiplier'] == 200