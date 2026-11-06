from copy import deepcopy
from pathlib import Path
import shutil

import numpy as np
import pandas as pd
import pytest

from fuel_analyst.fuel_analyst import (
    default_conpyro_dict, default_fofem_consume_dict, default_stand_summary_dict,
    default_tree_sampling_dict, default_woody_debris_dict, fuel_analyst,
)


SETTINGS = {
    'protocol_column': 'sampling_protocol',
    'protocol_overrides': {'CWC': {}, 'NFI': {'large_tree_min': 9}},
}


def _inputs(tmp_path, ranking=False):
    source = Path(__file__).resolve().parents[2] / 'examples/data/Survey123_Data'
    target = tmp_path / 'inputs'
    shutil.copytree(source, target)
    parent_path = target / '3_Trees/survey_0.csv'
    parents = pd.read_csv(parent_path)
    parents['sampling_protocol'] = 'CWC'
    parents.loc[0, 'sampling_protocol'] = 'NFI'
    parents['lgtree_plot_radius'] = 11.28
    parents['smtree_plot_radius'] = 3.99
    parents['sapling_plot_radius'] = 3.99
    parents.to_csv(parent_path, index=False)
    tree_path = target / '3_Trees/tree_plot_2.csv'
    original = pd.read_csv(tree_path)
    template = original.loc[original.tree_status.eq('L') & original.tree_dbh.notna()].iloc[0].copy()
    rows = []
    for number, parent in enumerate(parents.GlobalID.iloc[:2]):
        row = template.copy()
        row['GlobalID'] = f'sampling-tree-{number}'
        row['ParentGlobalID'] = parent
        row['tree_species'] = 'FDI'
        row['tree_status'] = 'L'
        row['tree_dbh'] = 10.
        row['tree_ht'] = 10.
        row['tree_cbh'] = 2.
        row['tree_dcbh'] = 1.
        row['tree_dcy_class_cnfr'] = 1
        row['tree_dcy_class_brdlf'] = np.nan
        row['tree_ht_class'] = 2
        rows.append(row)
    if ranking:
        row = rows[0].copy()
        row['GlobalID'] = 'ranking-tree'
        row['tree_species'] = 'PL'
        row['tree_dbh'] = 20.
        row['tree_ht'] = 18.
        rows.append(row)
    pd.DataFrame(rows).to_csv(tree_path, index=False)
    sapling_path = target / '3_Trees/sapling_1.csv'
    pd.read_csv(sapling_path).iloc[:0].to_csv(sapling_path, index=False)
    return target, parents


def _run(source, output, settings=None, summary=None):
    conpyro = deepcopy(default_conpyro_dict)
    fofem = deepcopy(default_fofem_consume_dict)
    woody = deepcopy(default_woody_debris_dict)
    summary = deepcopy(default_stand_summary_dict if summary is None else summary)
    snapshots = deepcopy((conpyro, fofem, settings, summary))
    fuel_analyst(
        str(source), str(output), 'Byram', stand_summary_params=summary,
        woody_debris_params=woody, conpyro_params=conpyro, fofem_consume_params=fofem,
        gen_conpyro_df=True, gen_fofem_gui_app_tree_df=True, gen_fofem_consume_df=True,
        tree_sampling_params=settings,
    )
    assert (conpyro, fofem, settings, summary) == snapshots
    names = ['master_fuel_df', 'master_tree_df', 'conpyro_df', 'fbp_prep_df',
             'fofem_gui_app_tree_mortality_df', 'fofem_consume_si_df', 'fuelanalyst_errors']
    return {name: pd.read_csv(output / f'{name}.csv', low_memory=False) for name in names}


@pytest.mark.integration
def test_bad_labels_blank_only_affected_plot_and_preserve_other_form_results(tmp_path):
    source, parents = _inputs(tmp_path)
    parents.loc[0, 'sampling_protocol'] = 'misspelled'
    parents.to_csv(source/'3_Trees/survey_0.csv', index=False)
    result = _run(source, tmp_path/'bad', SETTINGS)
    exported = pd.read_csv(tmp_path/'bad/3_Trees/survey_0.csv')
    bad_id, good_id = exported.set_index('GlobalID').loc[parents.GlobalID.iloc[:2], 'unique_id']
    master = result['master_fuel_df'].set_index('unique_id')
    trees = result['master_tree_df'].set_index('unique_id')
    assert trees.loc[bad_id, ['dens_ha', 'dens_live_ha', 'ba_ha', 'ba_live_ha']].isna().all()
    assert trees.loc[good_id, 'dens_ha'] == 200
    tree_stand_fields = [column for column in exported if column.startswith('stand_')]
    assert master.loc[bad_id, tree_stand_fields].isna().all()
    conpyro = result['conpyro_df'].set_index('unique_id')
    assert pd.isna(conpyro.loc[bad_id, 'stand_type'])
    assert pd.isna(conpyro.loc[bad_id, 'stand_density'])
    assert conpyro.loc[bad_id, ['cfl_ovrstry', 'cbd_ovrstry', 'pct_cnfr', 'fsg']].isna().all()
    assert bad_id not in set(result['fofem_gui_app_tree_mortality_df'].PlotId)
    assert result['fofem_consume_si_df'].iloc[:, 0].astype(str).str.contains(bad_id, regex=False).sum() == 0
    assert pd.isna(result['fbp_prep_df'].set_index('unique_id').loc[bad_id, 'SPECIES_CD_1'])
    report = result['fuelanalyst_errors'].set_index('unique_id')
    assert report.loc[bad_id, 'Trees'].count('sampling protocol') == 1
    assert 'assigned zero' not in report.loc[bad_id, 'Trees']
    assert pd.notna(report.loc[bad_id, 'plot_id'])
    parents['sampling_protocol'] = 'CWC'
    parents.to_csv(source/'3_Trees/survey_0.csv', index=False)
    valid = _run(source, tmp_path/'valid', SETTINGS)
    pd.testing.assert_series_equal(master.loc[good_id], valid['master_fuel_df'].set_index('unique_id').loc[good_id])
    for field in ['grass_kgpm2', 'herb_forb_kgpm2', 'shrubs_kgpm2', 'cc']:
        assert master.loc[bad_id, field] == valid['master_fuel_df'].set_index('unique_id').loc[bad_id, field]
    assert not valid['fuelanalyst_errors'].get('Trees', pd.Series(dtype=str)).fillna('').str.contains('sampling protocol').any()


@pytest.mark.integration
def test_excluded_species_parent_does_not_also_require_protocol(tmp_path):
    source, parents = _inputs(tmp_path)
    parents.loc[0, 'sampling_protocol'] = 'unknown'
    parents.to_csv(source/'3_Trees/survey_0.csv', index=False)
    path = source/'3_Trees/tree_plot_2.csv'
    frame = pd.read_csv(path)
    frame.loc[0, 'tree_species'] = 'UNLISTED_TEST_SPECIES'
    frame.to_csv(path, index=False)
    result = _run(source, tmp_path/'excluded', SETTINGS)
    messages = result['fuelanalyst_errors']['Trees'].fillna('')
    assert messages.str.contains('UNLISTED_TEST_SPECIES').any()
    assert not messages.str.contains('sampling protocol').any()
    assert result['master_tree_df'].dens_ha.tolist() == [200]
    exported = pd.read_csv(tmp_path/'excluded/3_Trees/survey_0.csv').set_index('GlobalID')
    excluded_id = exported.loc[parents.GlobalID.iloc[0], 'unique_id']
    valid_id = exported.loc[parents.GlobalID.iloc[1], 'unique_id']
    conpyro = result['conpyro_df'].set_index('unique_id')
    tree_columns = [
        'pct_cnfr', 'cfl_ovrstry', 'cbd_ovrstry', 'cfl_midstry', 'cbd_midstry',
        'dead_branch_fl_midstry', 'ht_ovrstry_live', 'ht_midstry_live',
        'ht_midstry_dead', 'cbh_ovrstry', 'cbh_midstry', 'fsg',
    ]
    assert conpyro.loc[excluded_id, tree_columns].isna().all()
    assert conpyro.loc[excluded_id, ['stand_type', 'stand_density']].isna().all()
    assert conpyro.loc[valid_id, 'cfl_ovrstry'] > 0


@pytest.mark.integration
def test_fbp_species_ranking_uses_corrected_expansion(tmp_path):
    source, parents = _inputs(tmp_path, ranking=True)
    base = _run(source, tmp_path/'base')
    nfi = _run(source, tmp_path/'nfi', SETTINGS)
    parent = pd.read_csv(tmp_path/'nfi/3_Trees/survey_0.csv').set_index('GlobalID').loc[parents.GlobalID.iloc[0], 'unique_id']
    assert 200 * np.pi * (10/200)**2 > 25 * np.pi * (20/200)**2
    assert 25 * np.pi * (10/200)**2 < 25 * np.pi * (20/200)**2
    for name in ['master_fuel_df', 'fbp_prep_df']:
        assert base[name].set_index('unique_id').loc[parent, 'SPECIES_CD_1'] == 'FDI'
        assert nfi[name].set_index('unique_id').loc[parent, 'SPECIES_CD_1'] == 'PL'


@pytest.mark.integration
@pytest.mark.parametrize('missing_column', [False, True])
def test_missing_or_unknown_protocol_for_all_eligible_plots_completes(tmp_path, missing_column):
    source, parents = _inputs(tmp_path)
    if missing_column:
        parents = parents.drop(columns='sampling_protocol')
    else:
        parents['sampling_protocol'] = 'unknown'
    parents.to_csv(source/'3_Trees/survey_0.csv', index=False)
    result = _run(source, tmp_path/'out', SETTINGS)
    assert result['master_tree_df'].dens_ha.isna().all()
    assert result['fofem_gui_app_tree_mortality_df'].empty
    errors = result['fuelanalyst_errors']['Trees'].fillna('')
    assert errors.str.contains('sampling protocol').sum() == 2
    ids = set(result['master_tree_df'].unique_id)
    assert result['conpyro_df'].set_index('unique_id').loc[list(ids), 'cfl_ovrstry'].isna().all()


@pytest.mark.integration
def test_protocol_invalid_dead_tree_exports_keep_per_area_values_missing(tmp_path):
    source, parents = _inputs(tmp_path)
    parents.loc[0, 'sampling_protocol'] = 'unknown'
    parents.to_csv(source/'3_Trees/survey_0.csv', index=False)
    path = source/'3_Trees/tree_plot_2.csv'
    frame = pd.read_csv(path)
    frame.loc[0, 'tree_status'] = 'D'
    frame.loc[0, 'tree_dcy_class_cnfr'] = 3
    frame.to_csv(path, index=False)
    result = _run(source, tmp_path/'out', SETTINGS)
    diagnostic = pd.read_csv(tmp_path/'out/3_Trees/tree_plot_2.csv')
    dead = diagnostic.loc[diagnostic.tree_status.eq('D')].iloc[0]
    assert dead[[column for column in diagnostic if column.endswith('_ha')]].isna().all()
    master_dead = result['master_tree_df'].loc[result['master_tree_df'].status.eq('D')].iloc[0]
    assert master_dead[['dens_ha', 'dens_live_ha', 'ba_ha', 'ba_live_ha']].isna().all()


@pytest.mark.integration
def test_sampling_settings_reach_model_inputs_without_changing_defaults(tmp_path):
    source, parents = _inputs(tmp_path)
    defaults_before = deepcopy(default_tree_sampling_dict)
    baseline = _run(source, tmp_path/'base')
    configured = _run(source, tmp_path/'configured', SETTINGS)
    repeat = _run(source, tmp_path/'repeat')
    for name in baseline:
        pd.testing.assert_frame_equal(baseline[name], repeat[name])
    assert default_tree_sampling_dict == defaults_before
    parent = pd.read_csv(tmp_path/'configured/3_Trees/survey_0.csv').set_index('GlobalID').loc[parents.GlobalID.iloc[0], 'unique_id']
    baseline_tree = baseline['master_tree_df'].set_index('unique_id').loc[parent]
    nfi_tree = configured['master_tree_df'].set_index('unique_id').loc[parent]
    assert baseline_tree.dens_ha == 200
    assert nfi_tree.dens_ha == 25
    assert nfi_tree.ba_ha == pytest.approx(25*np.pi*(10/200)**2)
    for column in ['cfl_ovrstry', 'cbd_ovrstry']:
        before = baseline['conpyro_df'].set_index('unique_id').loc[parent, column]
        after = configured['conpyro_df'].set_index('unique_id').loc[parent, column]
        assert before > 0 and after == pytest.approx(before/8, abs=1e-6)
    for column in ['CrownFoliage', 'CrownBranch']:
        # Join by identity because survey date sorting can reorder exported rows.
        before = baseline['fofem_consume_si_df'].set_index('#PlotId').loc[parent, column]
        after = configured['fofem_consume_si_df'].set_index('#PlotId').loc[parent, column]
        assert before > 0 and after == pytest.approx(before/8, abs=0.02)
    mortality = configured['fofem_gui_app_tree_mortality_df'].set_index('PlotId')
    assert mortality.loc[parent, 'TreeExpansionFactor'] == pytest.approx(25/2.47105)
    summary = deepcopy(default_stand_summary_dict)
    summary['dens']['classes']['dbh'] = [0, 11, float('inf')]
    grouped = _run(source, tmp_path/'grouped', SETTINGS, summary=summary)
    pd.testing.assert_frame_equal(configured['master_tree_df'], grouped['master_tree_df'])