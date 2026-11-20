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


@pytest.mark.parametrize('sapling_flag', ['Y', '', None])
@pytest.mark.parametrize('small_min, expected', [(5., ['sapling', 'invalid']), (2., ['invalid'])])
def test_direct_saplings_follow_presence_flags_and_protocol_thresholds(
        caplog,
        sapling_flag,
        small_min,
        expected
):
    parents, direct, saplings = _raw(('N', 'N', sapling_flag))
    parents['protocol'] = 'custom'
    direct = pd.concat([direct, direct.iloc[[2]]], ignore_index=True)
    direct['GlobalID'] = ['large', 'small', 'sapling', 'invalid']
    direct['tree_dbh'] = [15., 10., 2.5, np.nan]
    settings = {'protocol_column': 'protocol',
                'protocol_overrides': {'custom': {'small_tree_min': small_min}}}
    before = direct.copy(deep=True)
    with caplog.at_level(logging.WARNING, logger='fuel_analyst.components.trees'):
        kept, kept_saplings = trees._filter_tree_presence(parents, direct, saplings, settings)
    assert kept.GlobalID.tolist() == expected
    pd.testing.assert_frame_equal(direct, before)
    pd.testing.assert_frame_equal(kept_saplings, saplings)
    conflicts = [r for r in caplog.records if getattr(r, 'issue_code', '') == 'tree_presence_conflict']
    assert len(conflicts) == 1 and conflicts[0].unique_id == 'P1'
    assert 'invalid' not in conflicts[0].getMessage()
    if small_min == 5.:
        assert 'sapling' not in conflicts[0].getMessage()


def test_direct_saplings_reach_density_and_live_presence(tmp_path):
    source, parents = _form(tmp_path, ('N', 'N', 'Y'))
    parents['sapling_plot_radius'] = 3.99
    parents.to_csv(source / 'survey_0.csv', index=False)
    original = pd.read_csv(Path(__file__).resolve().parents[2] /
                           'examples/data/Survey123_Data/3_Trees/tree_plot_2.csv')
    row = original.loc[original.tree_status.eq('L') & original.tree_dbh.notna()].iloc[[0]].copy()
    row['GlobalID'] = 'direct-sapling'
    row['ParentGlobalID'] = parents.GlobalID.iloc[0]
    row['tree_species'] = 'FDI'
    row['tree_dbh'] = 2.5
    row['tree_ht'] = 3.
    row['tree_cbh'] = 1.
    row['tree_dcbh'] = 0.5
    row['tree_dcy_class_cnfr'] = 1
    row.to_csv(source / 'tree_plot_2.csv', index=False)
    result, _, master = _run(source, tmp_path / 'out')
    # A 3.99 m radius is the rounded 50 m2 plot: one live stem expands to 200 stems/ha.
    assert len(master) == 1
    assert master.dens_ha.iloc[0] == pytest.approx(200.)
    assert result.stand_dens_tpha_live_sum.iloc[0] == pytest.approx(200.)
    assert result.conpyro_live_tree_density.iloc[0] == pytest.approx(200.)
    assert bool(result.conpyro_live_trees_present.iloc[0])


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


@pytest.mark.parametrize('missing_repeat', ['tree_plot_2.csv', 'sapling_1.csv'])
def test_empty_parent_table_cannot_authorize_omitted_repeats(tmp_path, missing_repeat):
    source, parents = _form(tmp_path)
    (source / missing_repeat).unlink()
    resolved = trees.table_reader.ensure_form_source(str(source))
    with pytest.raises(ValueError, match='survey_0.*no plot records'):
        trees._read_tree_repeats(resolved, parents.iloc[:0])


def test_empty_parent_table_has_clear_error(tmp_path):
    source, parents = _form(tmp_path)
    parents.iloc[:0].to_csv(source / 'survey_0.csv', index=False)
    output = tmp_path / 'out'
    with pytest.raises(ValueError, match='survey_0.*no plot records'):
        _run(source, output)
    assert not output.exists()


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
