"""The final form-select switch separates stand inventory from fire-model eligibility."""
from copy import deepcopy
import importlib
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from fuel_analyst.components import conpyro_attributes as ca, fofem_attributes as fa, helper, trees
from fuel_analyst.components._default_configs import default_conpyro_dict
from fuel_calculation_fixtures import _make_consumption_input_df


def _surface_frame(substrate='HG'):
    frame = _make_consumption_input_df()
    frame['form_select'] = 'plants cover woody'
    frame['_tree_parent_present'] = False
    frame['_trees_excluded'] = True  # Stale Trees attributes must be ignored when not selected.
    frame['conpyro_live_trees_present'] = True
    frame['dom_substrate'] = substrate
    frame['pc_flammable'] = 50.
    frame['cc'] = 70.
    frame['_date'] = '2025-01-01'
    frame['plot_id'] = 'one'
    frame['treatment_area'] = 'area'
    frame['treatment_unit'] = 'unit'
    for column in ['x', 'y', 'plot_elevation', 'plot_slope_pct', 'plot_aspect', 'herb_forb_kgpm2',
                   'woody_kgpm2_conpyro_lt7cm_7']:
        frame[column] = 0.5
    return frame


@pytest.mark.parametrize('live_count', [0., np.nan, -1., np.inf])
def test_dead_only_coverage_rejects_unknown_or_invalid_live_sapling_count(live_count):
    parents = pd.DataFrame({'GlobalID': ['p'], 'unique_id': ['plot'],
                            'tree_large_present': ['Y'], 'tree_small_present': ['N'], 'sapling_present': ['Y']})
    direct = pd.DataFrame({'ParentGlobalID': ['p'], 'tree_dens_live_ha': [0.], 'tree_count': [1.],
                           'tree_status': ['D'], 'tree_density_radius_class': ['lgtree']})
    saplings = pd.DataFrame({'ParentGlobalID': ['p'], 'sapling_live_count': [live_count]})
    result = trees._calc_conpyro_live_density(parents, direct, saplings)
    if live_count == 0:
        assert result.conpyro_live_trees_present.iloc[0] == False
    else:
        assert pd.isna(result.conpyro_live_trees_present.iloc[0])


@pytest.mark.parametrize('kind', ['empty', 'unmatched'])
def test_gui_only_missing_parents_are_reported(tmp_path, kind):
    api = importlib.import_module('fuel_analyst.fuel_analyst')
    source = tmp_path / 'in'
    plot = source / '1_Plot_Attributes'
    plot.mkdir(parents=True)
    frame = pd.DataFrame({'GlobalID': ['p'], 'ParentGlobalID': [None], 'treatment_area': ['A'],
                           'treatment_unit': ['U'], 'treatment_type': ['Pre'], 'plot_id': [1],
                           '_date': ['01/01/2025 10:00'], 'plot_slope_units': ['percent'], 'plot_slope': [0.],
                           'form_select': ['trees']})
    frame.to_csv(plot / 'survey_0.csv', index=False)
    folder = source / '3_Trees'
    folder.mkdir()
    if kind == 'empty':
        frame.iloc[:0].to_csv(folder / 'survey_0.csv', index=False)
    else:
        frame['plot_id'] = 99
        frame.to_csv(folder / 'survey_0.csv', index=False)
    out = tmp_path / 'out'
    api.fuel_analyst(str(source), str(out), 'Byram', gen_fofem_gui_app_tree_df=True)
    report = pd.read_csv(out / 'fuelanalyst_errors.csv')
    assert report['Trees'].str.contains('FOFEM GUI').any()
    assert report['Trees'].str.contains('parent').any()


def test_marker_attachment_uses_identity_after_frame_reordering():
    markers = pd.DataFrame({'unique_id': ['live', 'absent', 'unknown'],
                            '_tree_parent_present': [True, True, False],
                            '_trees_confirmed_absent': [False, True, False]}, index=[8, 3, 6])
    exported = pd.DataFrame({'unique_id': ['unknown', 'live', 'absent']})
    result = trees._attach_tree_observation_markers(exported, markers)
    assert result['_tree_parent_present'].tolist() == [False, True, True]
    assert result['_trees_confirmed_absent'].tolist() == [False, False, True]


def test_model_preparation_does_not_destroy_plain_stand_values():
    api = importlib.import_module('fuel_analyst.fuel_analyst')
    frame = pd.DataFrame({'unique_id': ['dead'], 'form_select': ['trees'],
                          '_tree_parent_present': [True], 'conpyro_live_trees_present': [None],
                          'stand_dens_tpha_dead_sum': [25.], 'stand_wood_kgpm2_dead_sum': [2.]})
    before = frame.copy(deep=True)
    result = api._prepare_tree_model_inputs(frame, ['stand_dens_tpha_dead_sum', 'stand_wood_kgpm2_dead_sum'])
    assert result.empty
    pd.testing.assert_frame_equal(frame, before)


def test_partial_by_weather_warning_counts_only_affected_scenarios(caplog):
    module = importlib.import_module('fuel_analyst.run_conpyro')
    frame = pd.DataFrame({'unique_id': ['plot'] * 3, 'surface_fuel_type': ['forest_floor'] * 3,
                          'duff_fuel_load': [1.] * 3, 'litter_fuel_load': [1.] * 3,
                          'woody_fuel_load': [0.1] * 3, 'bui': [20., np.nan, 30.]})
    with caplog.at_level(logging.WARNING):
        module._log_missing_by_surface_inputs(frame, 'unique_id')
    assert len(caplog.records) == 1
    assert caplog.records[0].levelno == logging.WARNING
    assert '1 of 3' in caplog.records[0].message


def test_plain_workflow_does_not_apply_model_eligibility(monkeypatch, tmp_path):
    api = importlib.import_module('fuel_analyst.fuel_analyst')
    source = Path(__file__).resolve().parents[2] / 'examples/data/Survey123_Data'
    uid = helper.get_unique_id(pd.read_csv(source / '3_Trees/survey_0.csv')).unique_id.iloc[0]
    plots = pd.DataFrame({'unique_id': [uid], 'form_select': ['trees']})
    inventory = pd.DataFrame({'unique_id': [uid], 'conpyro_live_trees_present': [None],
                              'stand_dens_tpha_dead_sum': [25.], 'stand_wood_kgpm2_dead_sum': [2.]})
    fields = ['conpyro_live_trees_present', 'stand_dens_tpha_dead_sum', 'stand_wood_kgpm2_dead_sum']
    monkeypatch.setattr(api.pa, 'process_plot_attributes', lambda *a, **k: (plots, []))
    monkeypatch.setattr(api.trees, 'process_trees', lambda *a, **k: (inventory, fields, pd.DataFrame()))
    def forbidden(*args, **kwargs):
        raise AssertionError('plain inventory must not enter model eligibility')
    monkeypatch.setattr(api, '_prepare_tree_model_inputs', forbidden)
    out = tmp_path / 'out'
    api.fuel_analyst(str(source), str(out), 'Byram')
    master = pd.read_csv(out / 'master_fuel_df.csv')
    assert master.stand_dens_tpha_dead_sum.iloc[0] == 25.
    assert master.stand_wood_kgpm2_dead_sum.iloc[0] == 2.


@pytest.mark.parametrize(('substrate', 'model'), [('HG', 31), ('HF', 31), ('SL', 31), ('BY', 1)])
def test_unchecked_trees_use_substrate_and_ignore_stale_tree_values(substrate, model):
    source = _surface_frame(substrate)
    before = source.copy(deep=True)
    result, _ = ca.gen_conpyro_df(source, deepcopy(default_conpyro_dict))
    assert len(result) == 1
    assert result.iloc[0].sros_model == model
    assert result.iloc[0].stand_type == 10
    assert result.iloc[0][['cfl_ovrstry', 'cbd_ovrstry', 'cfl_midstry', 'fsg']].eq(0).all()
    settings = {'region': 'West', 'season': 'Summer', 'moisture_regime': 'Dry',
                'soil_heating': {'use_soil_heating': False}}
    consume = fa.gen_fofem_consumption_df(source, settings)
    assert len(consume) == 1
    assert consume.iloc[0][['CrownFoliage', 'CrownBranch']].eq(0).all()
    pd.testing.assert_frame_equal(source, before)


def test_unchecked_unsupported_substrate_reports_surface_warning(caplog):
    with caplog.at_level(logging.WARNING):
        result, _ = ca.gen_conpyro_df(_surface_frame('unsupported'), deepcopy(default_conpyro_dict))
    assert len(result) == 1
    assert pd.isna(result.iloc[0].sros_model)
    assert any('Surface model not assigned' in record.message for record in caplog.records)
    assert not any('unknown tree' in record.message.lower() for record in caplog.records)


@pytest.mark.parametrize('model_outputs', [False, True])
def test_unknown_live_count_retains_measured_dead_inventory(tmp_path, model_outputs):
    from fuel_analyst.fuel_analyst import default_stand_summary_dict
    schema = Path(__file__).resolve().parents[2] / 'examples/data/Survey123_Data/3_Trees'
    parents = pd.read_csv(schema / 'survey_0.csv').iloc[[0]].copy()
    parents['GlobalID'] = 'parent'
    parents['tree_large_present'] = 'Y'
    parents['tree_small_present'] = 'N'
    parents['sapling_present'] = 'Y'
    dead = pd.read_csv(schema / 'tree_plot_2.csv').iloc[[0]].copy()
    dead['ParentGlobalID'] = 'parent'
    dead['tree_species'] = 'FDI'
    dead['tree_status'] = 'D'
    dead['tree_dbh'] = 20.
    dead['tree_ht'] = 10.
    sapling = pd.read_csv(schema / 'sapling_1.csv').iloc[[0]].copy()
    sapling['ParentGlobalID'] = 'parent'
    sapling['sapling_species'] = 'FDI'
    sapling['sapling_live_count'] = np.nan
    sapling['sapling_dead_count'] = 0.
    source = tmp_path / 'trees'
    source.mkdir()
    parents.to_csv(source / 'survey_0.csv', index=False)
    dead.to_csv(source / 'tree_plot_2.csv', index=False)
    sapling.to_csv(source / 'sapling_1.csv', index=False)
    result, _, _ = trees.process_trees(str(source), str(tmp_path / 'out'), 'Byram',
                                      deepcopy(default_stand_summary_dict), model_outputs)
    assert pd.isna(result.conpyro_live_trees_present.iloc[0])
    assert result['stand_dens_tpha_dead_sum'].iloc[0] > 0
    wood = [c for c in result if c.startswith('stand_wood_') and '_dead_' in c]
    assert wood and result[wood].iloc[0].gt(0).any()
