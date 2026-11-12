"""Regression coverage for PR 99 parent evidence and output compatibility."""
from copy import deepcopy
import logging
from pathlib import Path

import pandas as pd
import pytest

from fuel_analyst.components import table_reader, trees
from fuel_analyst.fuel_analyst import default_stand_summary_dict


def _write_tree_source(tmp_path, live_count=0.):
    schema = Path(__file__).resolve().parents[2] / 'examples/data/Survey123_Data/3_Trees'
    source = tmp_path / 'trees'
    source.mkdir()
    parents = pd.read_csv(schema / 'survey_0.csv').iloc[[0]].copy()
    parents['GlobalID'] = 'parent'
    parents['tree_large_present'] = 'Y'
    parents['tree_small_present'] = 'N'
    parents['sapling_present'] = 'Y'
    direct = pd.read_csv(schema / 'tree_plot_2.csv').iloc[[0]].copy()
    direct['ParentGlobalID'] = 'parent'
    direct['tree_species'] = 'FDI'
    direct['tree_status'] = 'D'
    direct['tree_dbh'] = 20.
    direct['tree_ht'] = 10.
    sapling = pd.read_csv(schema / 'sapling_1.csv').iloc[[0]].copy()
    sapling['ParentGlobalID'] = 'parent'
    sapling['sapling_species'] = 'FDI'
    sapling['sapling_live_count'] = live_count
    sapling['sapling_dead_count'] = 0.
    parents.to_csv(source / 'survey_0.csv', index=False)
    direct.to_csv(source / 'tree_plot_2.csv', index=False)
    sapling.to_csv(source / 'sapling_1.csv', index=False)
    return source, parents


def test_duplicate_marker_identity_is_unknown_without_selecting_first():
    exported = pd.DataFrame({'unique_id': ['same', 'safe']})
    markers = pd.DataFrame({'unique_id': ['same', 'same', 'safe'],
                            '_tree_parent_present': [True, True, True],
                            '_trees_confirmed_absent': [False, True, True],
                            '_tree_live_trees_present': [True, False, False],
                            '_tree_live_tree_density': [10., 0., 0.]})
    result = trees._attach_tree_observation_markers(exported, markers)
    assert not result.loc[0, '_tree_parent_present']
    assert not result.loc[0, '_trees_confirmed_absent']
    assert pd.isna(result.loc[0, '_tree_live_trees_present'])
    assert pd.isna(result.loc[0, '_tree_live_tree_density'])
    assert 'ambiguous' in result.loc[0, '_tree_model_unknown_reason']
    assert result.loc[1, '_trees_confirmed_absent']


def test_duplicate_parent_globalid_remains_unknown_end_to_end(tmp_path):
    source, parents = _write_tree_source(tmp_path)
    duplicate = pd.concat([parents, parents], ignore_index=True)
    duplicate['plot_id'] = [1, 2]
    duplicate.to_csv(source / 'survey_0.csv', index=False)
    result, _, _ = trees.process_trees(str(source), str(tmp_path / 'out'), 'Byram',
                                       deepcopy(default_stand_summary_dict), True)
    assert len(result) == 2
    assert result.conpyro_live_trees_present.isna().all()
    assert not result['_trees_confirmed_absent'].any()
    assert result['_tree_model_unknown_reason'].str.contains('ambiguous').all()


def test_fractional_direct_count_reports_sampling_class(caplog):
    parents = pd.DataFrame({'GlobalID': ['p'], 'unique_id': ['plot'],
                            'plot_lgtree_mult': [100.], 'plot_smtree_mult': [200.],
                            'plot_sapling_mult': [300.]})
    record = pd.DataFrame({'ParentGlobalID': ['p'], 'tree_dbh': [20.], 'tree_count': [0.5],
                           'tree_status': ['D'], 'tree_id': [1]})
    result = trees._calc_tree_density(parents, record)
    with caplog.at_level(logging.ERROR):
        trees._log_tree_density_issues(parents, pd.DataFrame(), result)
    records = [r for r in caplog.records if getattr(r, 'issue_code', '') == 'non_integer_tree_count']
    assert len(records) == 1
    assert 'lgtree' in records[0].message
    assert not result.tree_density_input_valid.iloc[0]


def test_fractional_sapling_count_is_unknown_and_logged(tmp_path, caplog):
    source, _ = _write_tree_source(tmp_path, live_count=0.5)
    with caplog.at_level(logging.ERROR):
        result, _, _ = trees.process_trees(str(source), str(tmp_path / 'out'), 'Byram',
                                           deepcopy(default_stand_summary_dict), True)
    records = [r for r in caplog.records if getattr(r, 'issue_code', '') == 'non_integer_sapling_count']
    assert len(records) == 1
    assert 'sapling' in records[0].message
    assert pd.isna(result.conpyro_live_trees_present.iloc[0])
    assert 'sapling' in result['_tree_model_unknown_reason'].iloc[0]


@pytest.mark.parametrize('export_conpyro', [False, True])
def test_live_evidence_is_private_unless_conpyro_requested(tmp_path, export_conpyro):
    source, _ = _write_tree_source(tmp_path)
    out = tmp_path / 'out'
    result, columns, _ = trees.process_trees(str(source), str(out), 'Byram',
                                            deepcopy(default_stand_summary_dict), export_conpyro)
    public = {'conpyro_live_tree_density', 'conpyro_live_trees_present'}
    assert public.issubset(columns) is export_conpyro
    assert public.issubset(result.columns) is export_conpyro
    assert public.issubset(pd.read_csv(out / 'survey_0.csv').columns) is export_conpyro
    assert result['_tree_live_trees_present'].iloc[0] == False
    assert result['_tree_live_tree_density'].iloc[0] == 0.


def test_supplied_parents_avoid_second_read_and_remain_unmodified(tmp_path, monkeypatch):
    source, parents = _write_tree_source(tmp_path)
    before = parents.copy(deep=True)
    (source / 'survey_0.csv').unlink()
    original = table_reader.read_table
    reads = []
    def read_repeat(form_source, stem, **kwargs):
        reads.append(stem)
        return original(form_source, stem, **kwargs)
    monkeypatch.setattr(table_reader, 'read_table', read_repeat)
    result, _, _ = trees.process_trees(str(source), str(tmp_path / 'out'), 'Byram',
                                       deepcopy(default_stand_summary_dict), True, parent_df=parents)
    assert len(result) == 1
    assert reads == ['tree_plot_2', 'sapling_1']
    pd.testing.assert_frame_equal(parents, before)


def test_unknown_evidence_names_each_uncovered_sampling_class():
    parents = pd.DataFrame({'GlobalID': ['p'], 'unique_id': ['plot']})
    records = pd.DataFrame(columns=['ParentGlobalID', 'tree_dens_live_ha', 'tree_count', 'tree_status'])
    result = trees._calc_conpyro_live_density(parents, records)
    reason = result['_tree_model_unknown_reason'].iloc[0]
    assert all(name in reason for name in ['lgtree', 'smtree', 'sapling'])
