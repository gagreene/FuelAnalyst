from copy import deepcopy
import logging
from pathlib import Path
import shutil

import numpy as np
import pandas as pd
import pytest

from fuel_analyst.components import trees
from fuel_analyst.fuel_analyst import default_stand_summary_dict


def _form(tmp_path, flags=('N', 'N', 'N')):
    source = Path(__file__).resolve().parents[2] / 'examples/data/Survey123_Data/3_Trees'
    target = tmp_path / 'inputs'
    shutil.copytree(source, target)
    parents = pd.read_csv(target / 'survey_0.csv').iloc[:1].copy()
    for field, value in zip(('tree_large_present', 'tree_small_present', 'sapling_present'), flags):
        parents[field] = value
    parents.to_csv(target / 'survey_0.csv', index=False)
    for filename in ('tree_plot_2.csv', 'sapling_1.csv'):
        path = target / filename
        pd.read_csv(path).iloc[:0].to_csv(path, index=False)
    return target, parents


def _raw(flags=('N', 'N', 'N')):
    parents = pd.DataFrame({
        'GlobalID': ['p1'], 'unique_id': ['P1'],
        'tree_large_present': [flags[0]], 'tree_small_present': [flags[1]],
        'sapling_present': [flags[2]],
    })
    direct = pd.DataFrame({
        'GlobalID': ['large', 'small', 'invalid'], 'ParentGlobalID': ['p1'] * 3,
        'tree_id': [1, 2, 3], 'tree_dbh': [15., 10., np.nan],
        'tree_species': ['FDI', 'FDI', 'UNKNOWN'],
    })
    saplings = pd.DataFrame({
        'GlobalID': ['sapling'], 'ParentGlobalID': ['p1'],
        'sapling_species': ['FDI'], 'sapling_live_count': [3], 'sapling_dead_count': [0],
    })
    return parents, direct, saplings


def _run(source, output):
    return trees.process_trees(str(source), str(output), 'Byram', deepcopy(default_stand_summary_dict), True)


def test_absence_classification_matches_rounded_protocol_boundaries():
    parents, direct, saplings = _raw(('N', 'Y', 'Y'))
    parents['protocol'] = 'NFI'
    direct['tree_dbh'] = [8.94, 8.96, 9.0]
    settings = {'protocol_column': 'protocol', 'protocol_overrides': {'NFI': {'large_tree_min': 9}}}
    kept, _ = trees._filter_tree_presence(parents, direct, saplings, settings)
    assert kept.GlobalID.tolist() == ['large']


def test_absent_classes_filter_conflicting_records_before_species_validation(caplog):
    parents, direct, saplings = _raw()
    with caplog.at_level(logging.WARNING, logger='fuel_analyst.components.trees'):
        kept_trees, kept_saplings = trees._filter_tree_presence(parents, direct, saplings, None)
    assert kept_trees.empty and kept_saplings.empty
    assert len(direct) == 3 and len(saplings) == 1
    conflicts = [r for r in caplog.records if getattr(r, 'issue_code', '') == 'tree_presence_conflict']
    assert conflicts and all(r.unique_id == 'P1' for r in conflicts)


def test_absent_sapling_source_ignores_its_imputed_dbh():
    parents, direct, saplings = _raw(('Y', 'Y', 'N'))
    saplings['sapling_live_dbh'] = 15.
    kept, sapling_result = trees._filter_tree_presence(parents, direct, saplings, None)
    assert sapling_result.empty
    pd.testing.assert_frame_equal(kept, direct)


def test_absent_tables_can_be_omitted_without_missing_radius_warnings(tmp_path, caplog):
    source, parents = _form(tmp_path)
    for filename in ('tree_plot_2.csv', 'sapling_1.csv'):
        (source / filename).unlink()
    for field in ('lgtree_plot_radius', 'smtree_plot_radius', 'sapling_plot_radius'):
        parents[field] = np.nan
    parents.to_csv(source / 'survey_0.csv', index=False)
    with caplog.at_level(logging.WARNING, logger='fuel_analyst.components.trees'):
        result, _, master = _run(source, tmp_path / 'out')
    assert master.empty
    assert result['stand_dens_tpha_live_sum'].iloc[0] == 0
    assert not any('radius' in getattr(r, 'issue_code', '') for r in caplog.records)


@pytest.mark.parametrize('flag', ['', None, 'Y', 'unknown'])
def test_blank_missing_and_unrecognized_flags_do_not_drop_records(flag):
    parents, direct, saplings = _raw((flag, flag, flag))
    kept_trees, kept_saplings = trees._filter_tree_presence(parents, direct, saplings, None)
    pd.testing.assert_frame_equal(kept_trees, direct)
    pd.testing.assert_frame_equal(kept_saplings, saplings)


def test_confirmed_empty_plot_has_zero_sums_but_missing_heights(tmp_path):
    source, _ = _form(tmp_path)
    result, _, master = _run(source, tmp_path / 'out')
    assert master.empty
    for field in ('stand_dens_tpha_live_sum', 'stand_ba_m2pha_live_sum'):
        assert result[field].iloc[0] == 0
    assert result['stand_ht_m_live_mean'].isna().all()


def test_duplicate_ids_and_orphaned_records_are_not_silently_removed():
    parents, direct, saplings = _raw()
    parents = pd.concat([parents, parents], ignore_index=True)
    direct.loc[0, 'ParentGlobalID'] = 'orphan'
    direct.loc[1, 'ParentGlobalID'] = None
    kept, sapling_result = trees._filter_tree_presence(parents, direct, saplings, None)
    pd.testing.assert_frame_equal(kept, direct)
    pd.testing.assert_frame_equal(sapling_result, saplings)


def test_duplicate_parent_cannot_authorize_discarding_records():
    parents, direct, saplings = _raw()
    parents['_parent_id_ambiguous'] = True
    kept_trees, kept_saplings = trees._filter_tree_presence(parents, direct, saplings, None)
    pd.testing.assert_frame_equal(kept_trees, direct)
    pd.testing.assert_frame_equal(kept_saplings, saplings)


def test_empty_unconfirmed_plot_does_not_become_zero(tmp_path):
    source, _ = _form(tmp_path, ('', '', ''))
    result, _, _ = _run(source, tmp_path / 'out')
    assert result['stand_dens_tpha_live_sum'].isna().all()


def test_missing_required_repeat_still_raises(tmp_path):
    source, _ = _form(tmp_path, ('Y', 'N', 'N'))
    (source / 'tree_plot_2.csv').unlink()
    with pytest.raises(FileNotFoundError):
        _run(source, tmp_path / 'out')


def test_mixed_parents_filter_only_the_absent_plot():
    parents, direct, saplings = _raw()
    present = parents.copy()
    present['GlobalID'] = 'p2'
    present['unique_id'] = 'P2'
    present[['tree_large_present', 'tree_small_present', 'sapling_present']] = 'Y'
    parents = pd.concat([parents, present], ignore_index=True)
    direct.loc[0, 'ParentGlobalID'] = 'p2'
    kept, sapling_result = trees._filter_tree_presence(parents, direct, saplings, None)
    assert kept.GlobalID.tolist() == ['large']
    assert sapling_result.empty


def test_no_flags_preserves_legacy_records():
    parents, direct, saplings = _raw()
    parents = parents[['GlobalID', 'unique_id']]
    kept, sapling_result = trees._filter_tree_presence(parents, direct, saplings, None)
    pd.testing.assert_frame_equal(kept, direct)
    pd.testing.assert_frame_equal(sapling_result, saplings)


@pytest.mark.parametrize('count, conflict', [(0, False), (2, True), ('invalid', True)])
def test_no_saplings_placeholder_only_warns_if_it_has_conflicting_counts(caplog, count, conflict):
    parents, direct, saplings = _raw(('Y', 'Y', 'N'))
    saplings['sapling_species'] = 'NO_SAPLINGS'
    saplings['sapling_live_count'] = count
    with caplog.at_level(logging.WARNING, logger='fuel_analyst.components.trees'):
        _, result = trees._filter_tree_presence(parents, direct, saplings, None)
    assert result.empty
    warnings = [r for r in caplog.records if getattr(r, 'issue_code', '') == 'tree_presence_conflict']
    assert bool(warnings) == conflict


def test_partial_absence_does_not_resolve_unknown_protocol_by_guessing():
    parents, direct, saplings = _raw(('N', 'Y', 'Y'))
    parents['protocol'] = 'unknown'
    settings = {'protocol_column': 'protocol', 'protocol_overrides': {'NFI': {'large_tree_min': 9}}}
    kept, _ = trees._filter_tree_presence(parents, direct, saplings, settings)
    pd.testing.assert_frame_equal(kept, direct)


@pytest.mark.parametrize('large_min, expected', [(12.5, ['small', 'invalid']), (9., ['invalid'])])
def test_partial_absence_uses_configured_dbh_thresholds(large_min, expected):
    parents, direct, saplings = _raw(('N', 'Y', 'Y'))
    settings = {'dbh_thresholds_cm': {'large_tree_min': large_min}}
    kept_trees, kept_saplings = trees._filter_tree_presence(parents, direct, saplings, settings)
    assert kept_trees.GlobalID.tolist() == expected
    pd.testing.assert_frame_equal(kept_saplings, saplings)


def test_sapling_absence_does_not_drop_direct_trees():
    parents, direct, saplings = _raw(('Y', 'Y', 'N'))
    kept_trees, kept_saplings = trees._filter_tree_presence(parents, direct, saplings, None)
    pd.testing.assert_frame_equal(kept_trees, direct)
    assert kept_saplings.empty


def test_small_tree_absence_keeps_large_trees_and_saplings():
    parents, direct, saplings = _raw(('Y', 'N', 'Y'))
    kept, sapling_result = trees._filter_tree_presence(parents, direct, saplings, None)
    assert kept.GlobalID.tolist() == ['large', 'invalid']
    pd.testing.assert_frame_equal(sapling_result, saplings)


def test_trimmed_lowercase_no_is_recognized():
    parents, direct, saplings = _raw((' n ', 'n', 'N'))
    kept, sapling_result = trees._filter_tree_presence(parents, direct, saplings, None)
    assert kept.empty and sapling_result.empty
