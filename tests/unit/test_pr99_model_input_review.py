"""Regression cases for the final PR #99 model-input review."""
from copy import deepcopy
import importlib
import logging
from pathlib import Path

import pandas as pd
import pytest

from fuel_analyst.components import conpyro_attributes as ca, fofem_attributes as fa, helper
from fuel_analyst.components._default_configs import default_conpyro_dict
from fuel_calculation_fixtures import _make_consumption_input_df


def _model_frame():
    frame = _make_consumption_input_df()
    frame['_date'] = '2025-06-17'
    frame['plot_id'] = 'one'
    frame['treatment_area'] = 'area'
    frame['treatment_unit'] = 'unit'
    frame['conpyro_live_tree_density'] = 100.
    frame['pc_flammable'] = 75.
    frame['cc'] = 70.
    frame['SPECIES_PCT_1'] = 100.
    for i in range(2, 7):
        frame[f'SPECIES_CD_{i}'] = None
    for field in ['x', 'y', 'plot_elevation', 'plot_slope_pct', 'plot_aspect', 'stand_pct_cnfr_live',
                  'conpyro_cfl_ovrstry', 'conpyro_cbd_ovrstry', 'conpyro_cfl_midstry', 'conpyro_cbd_midstry',
                  'conpyro_dead_branch_fl_midstry', 'conpyro_ht_ovrstry_live', 'conpyro_ht_midstry_live',
                  'conpyro_ht_midstry_dead', 'conpyro_cbh_ovrstry', 'conpyro_cbh_midstry', 'conpyro_fsg',
                  'herb_forb_kgpm2', 'woody_kgpm2_conpyro_lt7cm_7']:
        frame[field] = 0.5
    return frame


def test_absent_form_select_preserves_conpyro_canopy_and_warns(caplog):
    source = _model_frame()
    expected, _ = ca.gen_conpyro_df(source, deepcopy(default_conpyro_dict))
    legacy = source.drop(columns=['form_select', '_tree_parent_present'])
    with caplog.at_level(logging.WARNING):
        result, _ = ca.gen_conpyro_df(legacy, deepcopy(default_conpyro_dict))
    fields = ['canopy_cover', 'cfl_ovrstry', 'cbd_ovrstry', 'fsg', 'stand_type', 'sros_model']
    pd.testing.assert_frame_equal(result[fields], expected[fields])
    assert any(getattr(r, 'issue_code', '') == 'tree_model_inputs_form_select_missing' for r in caplog.records)


def test_absent_form_select_preserves_fofem_crown_inputs_and_warns(caplog):
    source = _make_consumption_input_df().drop(columns=['form_select', '_tree_parent_present'])
    settings = {'region': 'West', 'season': 'Summer', 'moisture_regime': 'Dry',
                'soil_heating': {'use_soil_heating': False}}
    with caplog.at_level(logging.WARNING):
        result = fa.gen_fofem_consumption_df(source, settings)
    assert result.iloc[0].CrownFoliage == 0.4
    assert result.iloc[0].CrownBranch == 0.5
    assert any(getattr(r, 'issue_code', '') == 'tree_model_inputs_form_select_missing' for r in caplog.records)


@pytest.mark.parametrize('output', ['conpyro', 'consume'])
def test_combined_gui_and_model_request_warns_for_missing_trees(monkeypatch, tmp_path, caplog, output):
    api = importlib.import_module('fuel_analyst.fuel_analyst')
    source = tmp_path / 'source'
    for directory in ['1_Plot_Attributes', '2_Plants_Regeneration', '4_Canopy_Cover', '5_Woody_Debris']:
        folder = source / directory
        folder.mkdir(parents=True)
        pd.DataFrame({'GlobalID': ['p']}).to_csv(folder / 'survey_0.csv', index=False)
    plots = pd.DataFrame({'unique_id': ['plot'], 'form_select': ['trees']})
    monkeypatch.setattr(api.pa, 'process_plot_attributes', lambda *a, **k: (plots.copy(), []))
    monkeypatch.setattr(api.conpyro_attributes, 'gen_conpyro_df', lambda *a, **k: (pd.DataFrame(), pd.DataFrame()))
    monkeypatch.setattr(api.fofem_attributes, 'gen_fofem_consumption_df', lambda *a, **k: pd.DataFrame())
    with caplog.at_level(logging.WARNING):
        api.fuel_analyst(str(source), str(tmp_path / 'out'), 'Byram', gen_fofem_gui_app_tree_df=True,
                         gen_conpyro_df=output == 'conpyro', gen_fofem_consume_df=output == 'consume')
    warnings = [r for r in caplog.records if getattr(r, 'issue_code', '') == 'fofem_gui_missing_tree_parent']
    assert len(warnings) == 1
    assert 'Trees' in warnings[0].message and 'missing' in warnings[0].message
    assert not (tmp_path / 'out/fofem_gui_app_tree_mortality_df.csv').exists()


def test_duplicate_index_is_reset_before_shared_model_preparation(monkeypatch):
    source = pd.concat([_model_frame(), _model_frame()], ignore_index=True)
    source['unique_id'] = ['forest', 'surface']
    source.index = [4, 4]
    original = helper.prepare_tree_model_inputs
    seen = []
    def checked(frame, *args, **kwargs):
        seen.append(frame.index.is_unique)
        return original(frame, *args, **kwargs)
    monkeypatch.setattr(helper, 'prepare_tree_model_inputs', checked)
    result, _ = ca.gen_conpyro_df(source, deepcopy(default_conpyro_dict))
    assert seen == [True]
    assert result.index.tolist() == [4, 4]
    assert result.unique_id.tolist() == ['forest', 'surface']


def test_fofem_consumption_uses_private_evidence_without_exported_conpyro_fields():
    source = _make_consumption_input_df().drop(columns='conpyro_live_trees_present')
    source['_tree_live_trees_present'] = True
    source['_tree_live_tree_density'] = 100.
    settings = {'region': 'West', 'season': 'Summer', 'moisture_regime': 'Dry',
                'soil_heating': {'use_soil_heating': False}}
    result = fa.gen_fofem_consumption_df(source, settings)
    assert len(result) == 1 and result.iloc[0].CrownFoliage == 0.4
    assert 'conpyro_live_trees_present' not in source


def test_legacy_density_remains_usable_without_form_select_or_presence_marker():
    source = _model_frame()
    expected, _ = ca.gen_conpyro_df(source, deepcopy(default_conpyro_dict))
    legacy = source.drop(columns=['form_select', '_tree_parent_present', 'conpyro_live_trees_present'])
    result, _ = ca.gen_conpyro_df(legacy, deepcopy(default_conpyro_dict))
    assert result.iloc[0].sros_model == expected.iloc[0].sros_model
    assert result.iloc[0].canopy_cover == expected.iloc[0].canopy_cover


def test_partial_tree_parent_coverage_keeps_gui_warning_with_model_outputs(monkeypatch, tmp_path, caplog):
    api = importlib.import_module('fuel_analyst.fuel_analyst')
    source = tmp_path / 'source'
    for directory in ['1_Plot_Attributes', '2_Plants_Regeneration', '3_Trees', '4_Canopy_Cover', '5_Woody_Debris']:
        folder = source / directory
        folder.mkdir(parents=True)
        pd.DataFrame({'GlobalID': ['p']}).to_csv(folder / 'survey_0.csv', index=False)
    schema = Path(__file__).resolve().parents[2] / 'examples/data/Survey123_Data/3_Trees/survey_0.csv'
    parent = pd.read_csv(schema).iloc[[0]].copy()
    parent.to_csv(source / '3_Trees/survey_0.csv', index=False)
    uid = helper.get_unique_id(parent).unique_id.iloc[0]
    plots = pd.DataFrame({'unique_id': [uid, 'missing'], 'form_select': ['trees', 'trees']})
    evidence = pd.DataFrame({'unique_id': [uid], '_tree_parent_present': [True],
                             'conpyro_live_trees_present': [True]})
    monkeypatch.setattr(api.pa, 'process_plot_attributes', lambda *a, **k: (plots.copy(), []))
    monkeypatch.setattr(api.trees, 'process_trees', lambda *a, **k: (evidence.copy(), ['conpyro_live_trees_present'], pd.DataFrame()))
    monkeypatch.setattr(api.conpyro_attributes, 'gen_conpyro_df', lambda *a, **k: (pd.DataFrame(), pd.DataFrame()))
    monkeypatch.setattr(api.fofem_attributes, 'gen_fofem_gui_app_tree_df', lambda *a, **k: pd.DataFrame())
    with caplog.at_level(logging.WARNING):
        api.fuel_analyst(str(source), str(tmp_path / 'out'), 'Byram', gen_conpyro_df=True,
                         gen_fofem_gui_app_tree_df=True)
    warnings = [r for r in caplog.records if getattr(r, 'issue_code', '') == 'fofem_gui_missing_tree_parent']
    assert len(warnings) == 1 and warnings[0].unique_id == 'missing'
    errors = [r for r in caplog.records if getattr(r, 'issue_code', '') == 'tree_model_inputs_unknown']
    assert len(errors) == 1 and errors[0].unique_id == 'missing'


def test_pre_read_parent_is_passed_once_with_literal_protocol(monkeypatch, tmp_path):
    import shutil
    api = importlib.import_module('fuel_analyst.fuel_analyst')
    source = tmp_path / 'source'
    tree_source = Path(__file__).resolve().parents[2] / 'examples/data/Survey123_Data/3_Trees'
    shutil.copytree(tree_source, source / '3_Trees')
    plot = source / '1_Plot_Attributes'
    plot.mkdir()
    pd.DataFrame({'GlobalID': ['placeholder']}).to_csv(plot / 'survey_0.csv', index=False)
    parents = pd.read_csv(source / '3_Trees/survey_0.csv')
    parents['sampling_protocol'] = '001'
    parents.to_csv(source / '3_Trees/survey_0.csv', index=False)
    uid = helper.get_unique_id(parents).unique_id.iloc[0]
    monkeypatch.setattr(api.pa, 'process_plot_attributes',
                        lambda *a, **k: (pd.DataFrame({'unique_id': [uid], 'form_select': ['trees']}), []))
    original = api.table_reader.read_table
    reads = []
    def counted(folder, table, *args, **kwargs):
        if table == 'survey_0' and Path(getattr(folder, 'path', folder)).name == '3_Trees':
            reads.append(kwargs.get('literal_text_columns'))
        return original(folder, table, *args, **kwargs)
    monkeypatch.setattr(api.table_reader, 'read_table', counted)
    config = {'protocol_column': 'sampling_protocol', 'protocol_overrides': {'001': {}}}
    api.fuel_analyst(str(source), str(tmp_path / 'out'), 'Byram', tree_sampling_params=config)
    assert reads == [('sampling_protocol',)]
    master = pd.read_csv(tmp_path / 'out/master_fuel_df.csv')
    assert not {'conpyro_live_trees_present', 'conpyro_live_tree_density'} & set(master.columns)
    assert master.filter(regex='stand_dens_').notna().any(axis=None)


def test_private_unknown_by_reports_tree_error_without_surface_warning(caplog):
    source = _model_frame()
    source['dom_substrate'] = 'BY'
    source['conpyro_live_trees_present'] = None
    with caplog.at_level(logging.INFO):
        ca._calc_surface_models(source, default_conpyro_dict['sros_model'])
    records = [r for r in caplog.records if getattr(r, 'issue_code', '') == 'tree_model_inputs_unknown']
    assert len(records) == 1 and records[0].levelno == logging.ERROR
    assert not any(getattr(r, 'issue_code', '') == 'conpyro_surface_model_unassigned' for r in caplog.records)


def test_tree_model_error_preserves_sampling_class_explanation(caplog):
    api = importlib.import_module('fuel_analyst.fuel_analyst')
    source = _model_frame()
    source['conpyro_live_trees_present'] = None
    source['_tree_model_unknown_reason'] = 'saplings (sapling): no absence or valid observation evidence'
    with caplog.at_level(logging.ERROR):
        result = api._prepare_tree_model_inputs(source, [])
    records = [r for r in caplog.records if getattr(r, 'issue_code', '') == 'tree_model_inputs_unknown']
    assert result.empty and len(records) == 1
    assert 'sapling' in records[0].message and 'no absence or valid observation evidence' in records[0].message


def test_unknown_by_uses_shared_tree_error_once(caplog):
    source = _model_frame()
    source['dom_substrate'] = 'BY'
    source['conpyro_live_trees_present'] = None
    with caplog.at_level(logging.INFO):
        result, _ = ca.gen_conpyro_df(source, deepcopy(default_conpyro_dict))
    assert result.empty
    errors = [r for r in caplog.records if getattr(r, 'issue_code', '') == 'tree_model_inputs_unknown']
    assert len(errors) == 1
    assert not any(getattr(r, 'issue_code', '') == 'conpyro_surface_model_unassigned' for r in caplog.records)
