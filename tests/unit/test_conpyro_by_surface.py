"""BY classification must preserve FBP codes and separate fuel from error fallbacks."""
import copy
import logging

import numpy as np
import pandas as pd
import pytest

from fuel_analyst.components import conpyro_attributes as ca
from fuel_analyst.components._default_configs import default_conpyro_dict


def _input_frame():
    rows = []
    for uid, present, flammable, excluded in [('fuel', False, 80., False), ('none', False, 0., False),
                                              ('unknown', None, np.nan, False), ('excluded', False, 50., True)]:
        row = dict(unique_id=uid, plot_id=uid, _date='2025-06-01', treatment_area='a', treatment_unit='u',
                   treatment_type='burned', conpyro_live_tree_density=0. if present is False else np.nan,
                   conpyro_live_trees_present=present, dom_substrate='BY', dom_sub='BY', pc_flammable=flammable,
                   _trees_excluded=excluded, SPECIES_PCT_1=0., cc=np.nan, woody_spp_comp='FDI:100')
        row.update({f'SPECIES_CD_{i}': None for i in range(1, 7)})
        for field in ['x', 'y', 'plot_elevation', 'plot_slope_pct', 'plot_aspect', 'stand_pct_cnfr_live',
                      'conpyro_cfl_ovrstry', 'conpyro_cbd_ovrstry', 'conpyro_cfl_midstry', 'conpyro_cbd_midstry',
                      'conpyro_dead_branch_fl_midstry', 'conpyro_ht_ovrstry_live', 'conpyro_ht_midstry_live',
                      'conpyro_ht_midstry_dead', 'conpyro_cbh_ovrstry', 'conpyro_cbh_midstry', 'conpyro_fsg',
                      'ffl_duff_kgpm2', 'ffl_litter_kgpm2', 'woody_kgpm2_conpyro_lt7cm_7',
                      'grass_kgpm2', 'herb_forb_kgpm2', 'shrubs_kgpm2']:
            row[field] = 0.2
        rows.append(row)
    result = pd.DataFrame(rows)
    result['form_select'] = 'trees'
    result['_tree_parent_present'] = True
    result['_trees_confirmed_absent'] = [True, True, False, False]
    return result


@pytest.mark.parametrize(('present', 'flammable', 'excluded', 'reason'), [
    (False, np.nan, False, 'pc_flammable is missing'),
    (None, 50., False, 'live-tree presence is unresolved'),
    (None, np.nan, False, 'pc_flammable is missing'),
    (False, 50., True, 'tree inputs were excluded'),
    (False, -1., False, 'pc_flammable'),
    (False, np.inf, False, 'pc_flammable'),
    (False, -np.inf, False, 'pc_flammable'),
    (False, 101., False, 'pc_flammable'),
    (False, 'invalid', False, 'pc_flammable'),
])
def test_by_bad_inputs_report_error_and_preserve_missing_model(caplog, present, flammable, excluded, reason):
    source = pd.DataFrame({'unique_id': ['bad'], 'conpyro_live_trees_present': [present],
                           'dom_substrate': ['BY'], 'pc_flammable': [flammable], '_trees_excluded': [excluded]})
    with caplog.at_level(logging.INFO, logger=ca.__name__):
        result = ca._calc_surface_models(source, default_conpyro_dict['sros_model'])
    if present is None or excluded:
        assert result.loc[0, 'surface_fuel_type'] == ''
        assert pd.isna(result.loc[0, 'sros_model'])
        if excluded:
            assert caplog.records == []  # Existing species/protocol errors identify the cause.
        else:
            assert len(caplog.records) == 1 and caplog.records[0].levelno == logging.ERROR
            assert caplog.records[0].issue_code == 'tree_model_inputs_unknown'
        return
    assert result.loc[0, 'surface_fuel_type'] == 'nonfuel_error'
    assert pd.isna(result.loc[0, 'sros_model'])
    assert len(caplog.records) == 1
    assert caplog.records[0].levelno == logging.ERROR
    assert caplog.records[0].unique_id == 'bad'
    assert reason in caplog.records[0].message
    assert 'stand_type=0' in caplog.records[0].message
    if present is None and pd.isna(flammable):
        assert 'live-tree presence is unresolved' in caplog.records[0].message


def test_by_does_not_require_species_composition():
    source = _input_frame().iloc[[0]].drop(columns='woody_spp_comp')
    result, _ = ca.gen_conpyro_df(source, copy.deepcopy(default_conpyro_dict))
    assert result.iloc[0].stand_type == 10
    assert result.iloc[0].sros_model == 1


def test_by_fuel_uses_model_one_without_changing_substrate(caplog):
    source = _input_frame().iloc[[0]].copy()
    with caplog.at_level(logging.INFO, logger=ca.__name__):
        result = ca._calc_surface_models(source, {'forest': 9, 'grass_herbs': 30, 'shrubs': 31})
    assert result.iloc[0].sros_model == 1
    assert result.iloc[0].surface_fuel_type == 'forest_floor'
    assert result.iloc[0].dom_substrate == result.iloc[0].dom_sub == 'BY'
    assert caplog.records == []


def test_by_generated_inputs_supply_surface_only_and_explicit_nonfuel_codes():
    source = _input_frame()
    before = source.copy(deep=True)
    result, _ = ca.gen_conpyro_df(source, copy.deepcopy(default_conpyro_dict))
    result = result.set_index('unique_id')
    assert result.loc['fuel', 'stand_type'] == 10
    assert result.loc['fuel', 'sros_model'] == 1
    assert result.index.tolist() == ['fuel', 'none']
    assert result['stand_density'].eq('L').all()
    assert result.loc[['none'], 'stand_type'].eq(0).all()
    assert result.loc[['none'], 'sros_model'].isna().all()
    zero = ['canopy_cover', 'cfl_ovrstry', 'cbd_ovrstry', 'cfl_midstry', 'cbd_midstry', 'dead_branch_fl_midstry',
            'ht_ovrstry_live', 'ht_midstry_live', 'ht_midstry_dead', 'cbh_ovrstry', 'cbh_midstry', 'fsg',
            'herbaceous_fuel_load', 'grass_fuel_load', 'shrub_fuel_load']
    assert result.loc['fuel', zero].eq(0).all()
    assert result.loc['fuel', ['duff_fuel_load', 'litter_fuel_load', 'woody_fuel_load']].eq(0.2).all()
    pd.testing.assert_frame_equal(source, before)


@pytest.mark.parametrize('index', [[20, 4, 18, 6], [3, 3, 8, 8]])
def test_by_masks_preserve_nondefault_input_index(index):
    source = _input_frame()
    source.index = index
    result, _ = ca.gen_conpyro_df(source, copy.deepcopy(default_conpyro_dict))
    assert result.index.tolist() == index[:2]
    assert result['unique_id'].tolist() == source['unique_id'].iloc[:2].tolist()
    assert result['surface_fuel_type'].tolist() == ['forest_floor', 'nonfuel']
    assert result['stand_type'].tolist() == [10, 0]


def test_by_no_flammable_substrate_is_informational_nonfuel(caplog):
    source = _input_frame().iloc[[1]].copy()
    with caplog.at_level(logging.INFO, logger=ca.__name__):
        result = ca._calc_surface_models(source, default_conpyro_dict['sros_model'])
    assert result.iloc[0].surface_fuel_type == 'nonfuel'
    assert pd.isna(result.iloc[0].sros_model)
    assert len(caplog.records) == 1
    assert caplog.records[0].levelno == logging.INFO
    assert 'No flammable substrate recorded (pc_flammable=0)' in caplog.records[0].message


def test_confirmed_absence_with_sampling_exclusion_reaches_by_model():
    source = _input_frame().iloc[[0]].copy()
    source['_trees_excluded'] = True
    source['_trees_species_excluded'] = False
    result, _ = ca.gen_conpyro_df(source, copy.deepcopy(default_conpyro_dict))
    assert len(result) == 1
    assert result.iloc[0].stand_type == 10
    assert result.iloc[0].sros_model == 1


def test_live_tree_priority_is_preserved_for_by():
    source = _input_frame().iloc[[0]].copy()
    source['conpyro_live_trees_present'] = True
    source['pc_flammable'] = 0.
    result = ca._calc_surface_models(source, default_conpyro_dict['sros_model'])
    assert result.iloc[0].surface_fuel_type == 'forest'
    assert result.iloc[0].sros_model == 13
