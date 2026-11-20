from copy import deepcopy
import logging
from pathlib import Path
import shutil

import numpy as np
import pandas as pd
import pytest

from fuel_analyst.components import helper, table_reader, trees
from fuel_analyst.fuel_analyst import (
    default_conpyro_dict, default_fofem_consume_dict, default_stand_summary_dict,
    default_tree_sampling_dict, default_woody_debris_dict, fuel_analyst,
)


SETTINGS = {
    'protocol_column': 'sampling_protocol',
    'protocol_overrides': {'CWC': {}, 'NFI': {'large_tree_min': 9}},
}


def _dead_tree_inputs(tmp_path):
    source, parents = _inputs(tmp_path)
    parent_path = source / '3_Trees/survey_0.csv'
    parents = parents.iloc[:2].copy()
    parents.loc[0, ['tree_large_present', 'tree_small_present', 'sapling_present']] = ['Y', 'N', 'N']
    parents.to_csv(parent_path, index=False)
    tree_path = source / '3_Trees/tree_plot_2.csv'
    records = pd.read_csv(tree_path)
    records.loc[0, ['tree_status', 'tree_dbh', 'tree_dcy_class_cnfr']] = ['D', 20., 3.]
    records.to_csv(tree_path, index=False)
    plot_path = source / '1_Plot_Attributes/survey_0.csv'
    plots = pd.read_csv(plot_path)
    plots.loc[plots.GlobalID.isin(parents.GlobalID)].to_csv(plot_path, index=False)
    plot_ids = helper.get_unique_id(parents.copy()).set_index('GlobalID').loc[parents.GlobalID, 'unique_id'].tolist()
    return source, parents, records, plot_ids


def _identifier_inputs(tmp_path, collision=False):
    source, parents = _inputs(tmp_path)
    for path in source.glob('*/survey_0.csv'):
        frame = pd.read_csv(path)
        frame['treatment_unit'] = '001'
        frame.to_csv(path, index=False)
    parents['treatment_unit'] = '001'
    if collision:
        other = parents.iloc[[0]].assign(
            GlobalID='alternate-parent', treatment_unit='1', _date='11/01/2021 12:00',
        )
        parents = pd.concat([parents, other], ignore_index=True)
        parents.to_csv(source / '3_Trees/survey_0.csv', index=False)
        path = source / '3_Trees/tree_plot_2.csv'
        frame = pd.read_csv(path)
        child = frame.iloc[[0]].assign(GlobalID='alternate-tree', ParentGlobalID='alternate-parent')
        pd.concat([frame, child], ignore_index=True).to_csv(path, index=False)
    plot_source = source / '1_Plot_Attributes'
    ordinary = helper.get_unique_id(table_reader.read_table(str(plot_source), 'survey_0'))
    plot_ids = ordinary.set_index('GlobalID').loc[parents.GlobalID.iloc[:2], 'unique_id'].tolist()
    return source, parents, plot_ids


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
    # Synthetic 10 cm trees are present even where the copied survey marked small trees absent.
    parents.loc[parents.index[:2], 'tree_small_present'] = 'Y'
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
    assert bad_id not in conpyro.index
    assert bad_id not in set(result['fofem_gui_app_tree_mortality_df'].PlotId)
    assert result['fofem_consume_si_df'].iloc[:, 0].astype(str).str.contains(bad_id, regex=False).sum() == 0
    assert bad_id not in set(result['fbp_prep_df']['unique_id'])
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
def test_dead_tree_and_empty_observations_export_distinct_inventory(tmp_path, caplog):
    source, parents, records, (dead_id, live_id) = _dead_tree_inputs(tmp_path)
    parent_path = source / '3_Trees/survey_0.csv'
    tree_path = source / '3_Trees/tree_plot_2.csv'
    ordinary = _run(source, tmp_path / 'ordinary', SETTINGS)
    parents.loc[0, 'tree_large_present'] = 'N'
    parents.to_csv(parent_path, index=False)
    discarded = records.iloc[[1]].assign(ParentGlobalID=parents.GlobalID.iloc[0], GlobalID='ignored-live')
    unknown_status = discarded.assign(GlobalID='ignored-status', tree_status='?')
    malformed = discarded.assign(GlobalID='ignored-malformed', tree_status='D', tree_dbh=0.01)
    pd.concat([records, discarded, unknown_status, malformed], ignore_index=True).to_csv(tree_path, index=False)
    retained = _run(source, tmp_path / 'retained', SETTINGS)
    records.iloc[1:].to_csv(tree_path, index=False)
    empty = _run(source, tmp_path / 'empty', SETTINGS)

    ordinary_stand = ordinary['master_fuel_df'].set_index('unique_id').loc[dead_id]
    retained_stand = retained['master_fuel_df'].set_index('unique_id').loc[dead_id]
    empty_stand = empty['master_fuel_df'].set_index('unique_id').loc[dead_id]
    branch = 'stand_branches_fofem_kgpm2_sum'
    foliage = 'stand_foliage_fofem_kgpm2_sum'
    assert ordinary_stand[branch] == pytest.approx(0.07249, abs=0.00001)
    live_branch = ordinary['fofem_consume_si_df'].set_index('#PlotId').loc[live_id, 'CrownBranch']
    assert live_branch > 0
    surface_model = empty['conpyro_df'].set_index('unique_id').loc[dead_id, 'sros_model']
    assert pd.notna(surface_model)
    for result, stand in [(ordinary, ordinary_stand), (retained, retained_stand), (empty, empty_stand)]:
        consume = result['fofem_consume_si_df'].set_index('#PlotId')
        assert consume.loc[dead_id, 'CrownBranch'] == pytest.approx(stand[branch])
        assert consume.loc[dead_id, 'CrownFoliage'] == pytest.approx(stand[foliage])
        assert consume.loc[live_id, 'CrownBranch'] == live_branch
        assert stand[['stand_dens_tpha_live_sum', 'stand_ba_m2pha_live_sum']].eq(0).all()
        inputs = result['conpyro_df'].set_index('unique_id').loc[dead_id]
        assert inputs[['cfl_ovrstry', 'cfl_midstry']].eq(0).all()
        assert inputs['sros_model'] == surface_model
        assert dead_id not in set(result['fofem_gui_app_tree_mortality_df'].PlotId)
    for name in (branch, foliage, 'stand_dens_tpha_dead_sum', 'stand_ba_m2pha_dead_sum',
                 'stand_wood_kgpm2_dead_sum', 'stand_bark_kgpm2_dead_sum',
                 'stand_dens_tpha_dead_dbh12.5plus_sum', 'stand_branches_kgpm2_dead_dbh0plus_sum'):
        assert retained_stand[name] == pytest.approx(ordinary_stand[name])
        assert empty_stand[name] == 0
    assert pd.isna(empty_stand['stand_ht_m_dead_mean'])
    control_tree = ordinary['master_tree_df'].set_index('unique_id').loc[dead_id]
    pd.testing.assert_series_equal(retained['master_tree_df'].set_index('unique_id').loc[dead_id], control_tree)
    assert control_tree.status == 'D' and control_tree.dens_ha == 25
    assert control_tree.ba_ha == pytest.approx(25 * np.pi * (20 / 200) ** 2)
    assert dead_id not in set(empty['master_tree_df'].unique_id)
    conflicts = [r for r in caplog.records if getattr(r, 'issue_code', '') == 'tree_presence_conflict'
                 and r.unique_id == dead_id]
    assert len(conflicts) == 1 and conflicts[0].levelno == logging.WARNING
    message = conflicts[0].message
    assert 'Retained dead record IDs: sampling-tree-0' in message
    assert 'Skipped record IDs: ignored-live, ignored-status, ignored-malformed' in message


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
    assert excluded_id not in conpyro.index
    master = result['master_fuel_df'].set_index('unique_id')
    stand = [c for c in master if c.startswith(('stand_', 'conpyro_'))
             and 'duff' not in c and 'litter' not in c]
    assert master.loc[excluded_id, stand].isna().all()
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
@pytest.mark.parametrize('direct', [False, True])
@pytest.mark.parametrize('file_format', ['csv', 'excel', 'excel_mixed'])
def test_literal_identifier_protocol_preserves_canonical_plot_join(tmp_path, direct, file_format):
    source, parents, (expected, _) = _identifier_inputs(tmp_path)
    tree_source = source / '3_Trees'
    if file_format.startswith('excel'):
        pytest.importorskip('openpyxl')
        if file_format == 'excel_mixed':
            # Ordinary workbook inference maps the numeric text and Boolean to 1.
            # The text pass must still provide "001" to the sampling protocol lookup.
            parents['treatment_unit'] = parents['treatment_unit'].astype(object)
            parents.loc[parents.index[1], 'treatment_unit'] = True
        with pd.ExcelWriter(tree_source / 'trees.xlsx', engine='openpyxl') as writer:
            for path in tree_source.glob('*.csv'):
                frame = parents if path.stem == 'survey_0' else pd.read_csv(path)
                frame.to_excel(writer, sheet_name=path.stem, index=False)
                path.unlink()
    settings = {'protocol_column': 'treatment_unit', 'protocol_overrides': {'001': {'large_tree_min': 9}}}
    output = tmp_path / 'out'
    if direct:
        _, _, master = trees.process_trees(
            str(tree_source), str(output), 'Byram', deepcopy(default_stand_summary_dict), False,
            tree_sampling_params=settings,
        )
    else:
        master = _run(source, output, settings)['master_tree_df']
    tree = master.set_index('unique_id').loc[expected]
    assert tree.dens_ha == 25
    assert tree.ba_ha == pytest.approx(25 * np.pi * (10 / 200) ** 2)


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
    assert ids.isdisjoint(set(result['conpyro_df']['unique_id']))


@pytest.mark.integration
@pytest.mark.parametrize('direct', [False, True])
def test_parent_identifier_collision_excludes_both_records(tmp_path, caplog, direct):
    source, parents, (ambiguous, good) = _identifier_inputs(tmp_path, collision=True)
    settings = {'protocol_column': 'treatment_unit', 'protocol_overrides': {'001': {}, '1': {}}}
    output = tmp_path / 'out'
    if direct:
        _, _, master = trees.process_trees(
            str(source / '3_Trees'), str(output / '3_Trees'), 'Byram',
            deepcopy(default_stand_summary_dict), False, tree_sampling_params=settings,
        )
    else:
        result = _run(source, output, settings)
        master = result['master_tree_df']
        assert ambiguous not in set(result['conpyro_df']['unique_id'])
        assert ambiguous not in set(result['fofem_consume_si_df']['#PlotId'])
        assert good in set(result['conpyro_df']['unique_id'])
        assert good in set(result['fofem_consume_si_df']['#PlotId'])
    issues = [r for r in caplog.records if getattr(r, 'issue_code', '') == 'tree_parent_id_collision']
    assert len(issues) == 1
    issue = issues[0]
    assert issue.unique_id == ambiguous and issue.levelno == logging.ERROR
    assert all(value in issue.message for value in ("'001'", "'1'", parents.GlobalID.iloc[0], 'alternate-parent'))
    exported = pd.read_csv(output / '3_Trees/survey_0.csv')
    assert ambiguous not in set(exported['unique_id'])
    assert master['unique_id'].tolist() == [good]
    assert master['dens_ha'].tolist() == [200]


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
@pytest.mark.parametrize(('failure', 'code'), [
    ('radius', 'missing_plot_radius'),
    ('protocol', 'tree_sampling_invalid_protocol'),
    ('decay_class', 'tree_retained_dead_biomass_unavailable'),
    ('nonnumeric_decay', 'tree_retained_dead_biomass_unavailable'),
])
def test_retained_dead_stem_with_unknown_fuel_is_omitted_from_models(tmp_path, caplog, failure, code):
    source, parents, records, (bad_id, good_id) = _dead_tree_inputs(tmp_path)
    parents.loc[0, 'tree_large_present'] = 'N'
    # The unused radii remain exempt and do not produce a second diagnostic.
    parents.loc[0, ['smtree_plot_radius', 'sapling_plot_radius']] = np.nan
    if failure == 'radius':
        parents.loc[0, 'lgtree_plot_radius'] = np.nan
    elif failure == 'protocol':
        parents.loc[0, 'sampling_protocol'] = 'unknown'
    elif failure == 'decay_class':
        records.loc[0, 'tree_dcy_class_cnfr'] = np.nan
    else:
        records['tree_dcy_class_cnfr'] = records['tree_dcy_class_cnfr'].astype(str)
        records.loc[0, 'tree_dcy_class_cnfr'] = 'invalid'
    parents.to_csv(source / '3_Trees/survey_0.csv', index=False)
    records.to_csv(source / '3_Trees/tree_plot_2.csv', index=False)
    output = tmp_path / 'out'
    result = _run(source, output, SETTINGS)
    errors = [r for r in caplog.records if getattr(r, 'unique_id', None) == bad_id and r.levelno >= logging.ERROR]
    assert [r.issue_code for r in errors] == [code]
    assert 'left missing' in errors[0].message and 'omitted from ConPyro and FOFEM consumption' in errors[0].message
    assert 'assigned zero' not in errors[0].message
    tree = result['master_tree_df'].set_index('unique_id').loc[bad_id]
    assert tree.status == 'D' and tree.dbh == 20 and tree.ht == 10
    stand = result['master_fuel_df'].set_index('unique_id').loc[bad_id]
    assert stand[['stand_branches_fofem_kgpm2_sum', 'stand_wood_kgpm2_dead_sum', 'stand_bark_kgpm2_dead_sum']].isna().all()
    assert stand[['stand_dens_tpha_live_sum', 'stand_ba_m2pha_live_sum']].eq(0).all()
    diagnostic = pd.read_csv(output / '3_Trees/tree_plot_2.csv').set_index('GlobalID').loc['sampling-tree-0']
    assert diagnostic[['tree_branches_cnbe_ha', 'tree_wood_cnbe_ha', 'tree_bark_cnbe_ha', 'tree_branches_fofem']].isna().all()
    if failure in {'decay_class', 'nonnumeric_decay'}:
        assert tree.dens_ha == 25 and tree.ba_ha == pytest.approx(25 * np.pi * (20 / 200) ** 2)
    else:
        assert tree[['dens_ha', 'ba_ha']].isna().all()
    assert result['master_tree_df'].set_index('unique_id').loc[good_id, 'dens_ha'] == 200
    for name, column in [('conpyro_df', 'unique_id'), ('fofem_consume_si_df', '#PlotId')]:
        assert bad_id not in set(result[name][column])
        assert good_id in set(result[name][column])


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
