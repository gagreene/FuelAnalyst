"""Synthetic observed-live, explicit-absence, and unknown-tree routing."""
import importlib
import logging

import numpy as np
import pandas as pd
import pytest

from fuel_analyst.components import helper, trees
from fuel_analyst.components.fofem_attributes import gen_fofem_consumption_df
from fuel_calculation_fixtures import _make_consumption_input_df


def test_ambiguous_all_no_parents_are_unknown():
    parents = pd.DataFrame({'GlobalID': ['same', 'same'], 'unique_id': ['one', 'two'],
                            'tree_large_present': ['N', 'N'], 'tree_small_present': ['N', 'N'],
                            'sapling_present': ['N', 'N']})
    records = pd.DataFrame(columns=['ParentGlobalID', 'tree_dens_live_ha', 'tree_count', 'tree_status'])
    result = trees._calc_conpyro_live_density(parents, records)
    assert result.conpyro_live_trees_present.isna().all()
    assert not trees._get_tree_absence(parents).any(axis=None)


@pytest.mark.parametrize('identity', ['', '   '])
def test_blank_live_parent_is_unknown(identity):
    parents = pd.DataFrame({'GlobalID': [identity], 'unique_id': ['plot']})
    records = pd.DataFrame({'ParentGlobalID': [identity], 'tree_dens_live_ha': [np.nan],
                            'tree_status': ['L'], 'tree_count': [1.]})
    result = trees._calc_conpyro_live_density(parents, records)
    assert pd.isna(result.conpyro_live_trees_present.iloc[0])


@pytest.mark.parametrize(('selected', 'parent', 'present', 'absent', 'excluded', 'species', 'expected'), [
    ('trees', True, True, False, False, False, True),
    ('trees', True, False, True, False, False, True),
    ('trees', True, False, True, True, False, True),
    ('trees', True, True, False, True, False, False),
    ('trees', True, True, False, True, True, False),
    ('trees', True, False, True, True, True, False),
    ('plants woody', True, True, False, False, False, True),
    ('trees', False, True, False, False, False, False),
    ('trees', True, None, False, False, False, False),
    ('trees', True, False, False, False, False, True),
])
def test_eligibility_requires_observed_live_or_explicit_absence(
        selected,
        parent,
        present,
        absent,
        excluded,
        species,
        expected
):
    frame = pd.DataFrame({'form_select': [selected], '_tree_parent_present': [parent],
                          'conpyro_live_trees_present': [present], '_trees_confirmed_absent': [absent],
                          '_trees_excluded': [excluded], '_trees_species_excluded': [species]})
    eligible, reasons = helper.get_tree_model_eligibility(frame)
    assert bool(eligible.iloc[0]) is expected
    assert bool(reasons.iloc[0]) is not expected


def test_empty_unflagged_trees_are_unknown():
    parents = pd.DataFrame({'GlobalID': ['p'], 'unique_id': ['plot']})
    records = pd.DataFrame(columns=['ParentGlobalID', 'tree_dens_live_ha', 'tree_count', 'tree_status'])
    result = trees._calc_conpyro_live_density(parents, records)
    assert pd.isna(result.conpyro_live_trees_present.iloc[0])
    assert pd.isna(result.conpyro_live_tree_density.iloc[0])


def test_fofem_drops_unknown_but_keeps_confirmed_absence_with_sampling_issue():
    frame = pd.concat([_make_consumption_input_df()] * 3, ignore_index=True)
    frame['unique_id'] = ['live', 'absent', 'unknown']
    frame['form_select'] = 'trees'
    frame['_tree_parent_present'] = True
    frame['conpyro_live_trees_present'] = [True, False, None]
    frame['_trees_confirmed_absent'] = [False, True, False]
    frame['_trees_excluded'] = [False, True, True]
    frame['_trees_species_excluded'] = False
    frame.loc[1, ['stand_foliage_fofem_kgpm2_sum', 'stand_branches_fofem_kgpm2_sum']] = 0.
    settings = {'region': 'West', 'season': 'Summer', 'moisture_regime': 'Dry',
                'soil_heating': {'use_soil_heating': False}}
    result = gen_fofem_consumption_df(frame, settings)
    assert result['#PlotId'].tolist() == ['live', 'absent']
    assert result.iloc[1][['CrownFoliage', 'CrownBranch']].eq(0).all()


@pytest.mark.parametrize('flags', [('N', 'N', 'N'), ('Y', 'N', 'N')])
def test_sampling_exclusion_respects_explicit_absence(flags):
    parents = pd.DataFrame({'GlobalID': ['p'], 'unique_id': ['plot'],
                            'tree_large_present': [flags[0]], 'tree_small_present': [flags[1]],
                            'sapling_present': [flags[2]]})
    records = pd.DataFrame({'ParentGlobalID': ['p'], '_tree_sampling_issue_code': ['tree_sampling_invalid_protocol'],
                            '_tree_sampling_protocol_column': ['sampling_protocol']})
    excluded = trees._log_tree_sampling_issues(parents, records)
    assert excluded == (set() if flags[0] == 'N' else {'plot'})


@pytest.mark.parametrize('uncollected_record', [False, True])
@pytest.mark.parametrize('export_conpyro', [False, True])
def test_tree_processor_preserves_absence_with_invalid_protocol_and_masks_unknown(
        tmp_path,
        caplog,
        export_conpyro,
        uncollected_record
):
    from copy import deepcopy
    from pathlib import Path
    from fuel_analyst.fuel_analyst import default_stand_summary_dict
    schema = Path(__file__).resolve().parents[2] / 'examples/data/Survey123_Data/3_Trees'
    parents = pd.concat([pd.read_csv(schema / 'survey_0.csv').iloc[[0]]] * 3, ignore_index=True)
    parents['GlobalID'] = ['live', 'absent', 'unknown']
    parents['plot_id'] = [1, 2, 3]
    parents['form_select'] = 'trees'
    parents['sampling_protocol'] = ['CWC', 'invalid', 'invalid']
    parents['tree_large_present'] = ['Y', 'N', 'Y']
    parents['tree_small_present'] = 'N'
    parents['sapling_present'] = 'N'
    direct = pd.concat([pd.read_csv(schema / 'tree_plot_2.csv').iloc[[0]]] * 2, ignore_index=True)
    direct['GlobalID'] = ['r1', 'r2']
    direct['ParentGlobalID'] = ['live', 'unknown']
    direct['tree_species'] = 'FDI'
    direct['tree_status'] = 'L'
    direct['tree_dbh'] = 20.
    direct['tree_ht'] = 10.
    direct['tree_cbh'] = 2.
    source = tmp_path / 'trees'
    source.mkdir()
    parents.to_csv(source / 'survey_0.csv', index=False)
    direct.to_csv(source / 'tree_plot_2.csv', index=False)
    pd.read_csv(schema / 'sapling_1.csv').iloc[:0].to_csv(source / 'sapling_1.csv', index=False)
    settings = {'protocol_column': 'sampling_protocol', 'protocol_overrides': {'CWC': {}}}
    selected_ids = set(helper.get_unique_id(parents.copy()).unique_id.iloc[:2]) if uncollected_record else None
    with caplog.at_level(logging.ERROR):
        result, columns, _ = trees.process_trees(str(source), str(tmp_path / 'out'), 'Byram',
                                                 deepcopy(default_stand_summary_dict), export_conpyro, settings, selected_plot_ids=selected_ids)
    result = result.set_index('plot_id')
    presence_column = 'conpyro_live_trees_present' if export_conpyro else '_tree_live_trees_present'
    assert bool(result.loc[1, presence_column])
    assert result.loc[2, presence_column] == False
    assert result.loc[2, '_trees_confirmed_absent']
    assert pd.isna(result.loc[3, presence_column])
    assert result.loc[3, [c for c in columns if c in result]].isna().all()
    eligible, _ = helper.get_tree_model_eligibility(result)
    assert eligible.tolist() == [True, True, False]
    issues = [r for r in caplog.records if getattr(r, 'issue_code', '') == 'tree_sampling_invalid_protocol']
    assert len(issues) == (0 if uncollected_record else 1)


def test_unknown_plot_stand_fields_are_missing_and_logged_once(caplog):
    module = importlib.import_module('fuel_analyst.fuel_analyst')
    frame = pd.DataFrame({'unique_id': ['live', 'absent', 'unknown'], 'form_select': ['trees'] * 3,
                          '_tree_parent_present': [True] * 3, 'conpyro_live_trees_present': [True, False, None],
                          '_trees_confirmed_absent': [False, True, False],
                          'stand_dens_live_ha_sum': [100., 0., 123.], 'conpyro_cfl_ovrstry': [1., 0., 4.]})
    with caplog.at_level(logging.ERROR):
        result = module._prepare_tree_model_inputs(frame, ['stand_dens_live_ha_sum', 'conpyro_cfl_ovrstry'])
    assert 'unknown' not in set(result['unique_id'])
    assert frame.loc[2, 'stand_dens_live_ha_sum'] == 123.
    records = [r for r in caplog.records if getattr(r, 'issue_code', '') == 'tree_model_inputs_unknown']
    assert len(records) == 1 and records[0].unique_id == 'unknown'


@pytest.mark.parametrize('scenario', ['missing_folder', 'empty_parents', 'missing_parent_table', 'unmatched_parent'])
def test_workflow_drops_unknown_trees_once_and_writes_empty_models(tmp_path, scenario):
    module = importlib.import_module('fuel_analyst.fuel_analyst')
    source = tmp_path / 'in'
    plot = source / '1_Plot_Attributes'
    plot.mkdir(parents=True)
    pd.DataFrame({'GlobalID': ['g'], 'ParentGlobalID': [None], 'treatment_area': ['A'],
                  'treatment_unit': ['U'], 'treatment_type': ['Pre'], 'plot_id': [1],
                  '_date': ['01/01/2025 10:00'], 'plot_slope_units': ['percent'], 'plot_slope': [0.],
                  'form_select': ['none' if scenario == 'not_selected' else 'trees']}).to_csv(plot / 'survey_0.csv',
                                                                                              index=False)
    for folder in ['2_Plants_Regeneration', '4_Canopy_Cover', '5_Woody_Debris']:
        (source / folder).mkdir()
    if scenario in ['empty_parents', 'missing_parent_table', 'unmatched_parent']:
        folder = source / '3_Trees'
        folder.mkdir()
        if scenario == 'empty_parents':
            pd.DataFrame(columns=['GlobalID', '_date']).to_csv(folder / 'survey_0.csv', index=False)
        elif scenario == 'missing_parent_table':
            pd.DataFrame(columns=['ParentGlobalID']).to_csv(folder / 'tree_plot_2.csv', index=False)
        else:
            unrelated = pd.read_csv(plot / 'survey_0.csv')
            unrelated['GlobalID'] = 'unrelated'
            unrelated['plot_id'] = 999
            unrelated.to_csv(folder / 'survey_0.csv', index=False)
    output = tmp_path / 'out'
    module.fuel_analyst(str(source), str(output), 'Byram', gen_conpyro_df=True, gen_fofem_consume_df=True)
    assert pd.read_csv(output / 'conpyro_df.csv').empty
    assert pd.read_csv(output / 'fofem_consume_si_df.csv').empty
    errors = pd.read_csv(output / 'fuelanalyst_errors.csv')
    plot_errors = errors.loc[errors['unique_id'] != 'General Error']
    assert len(plot_errors) == 1
    assert plot_errors.iloc[0]['Trees'].count('Plot omitted from ConPyro and FOFEM consumption') == 1
    master = pd.read_csv(output / 'master_fuel_df.csv')
    stand = [c for c in master if c.startswith(('stand_', 'conpyro_'))]
    assert master[stand].isna().all(axis=None)
    general = errors.loc[errors['unique_id'] == 'General Error']
    assert len(general) == 1 and general.iloc[0]['Trees'].count('No plots are eligible') == 1
