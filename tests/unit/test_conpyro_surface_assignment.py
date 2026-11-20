"""Surface classification must distinguish observed zero live trees from missing inputs."""
import copy

import numpy as np
import pandas as pd
import pytest

from fuel_analyst.components import conpyro_attributes, trees
from fuel_analyst.components._default_configs import default_conpyro_dict


def test_fixed_live_density_includes_saplings_and_preserves_unknown_parents():
    parents = pd.DataFrame({'GlobalID': ['live', 'dead', 'absent', 'unknown'],
                            'tree_large_present': ['Y', 'Y', 'N', None],
                            'tree_small_present': ['N', 'N', 'N', None],
                            'sapling_present': ['Y', 'N', 'N', None]})
    records = pd.DataFrame({'ParentGlobalID': ['live', 'live', 'dead'],
                            'tree_dens_live_ha': [0., 200., 0.], 'tree_status': ['D', 'L', 'D'], 'tree_count': [1., 2., 1.], 'tree_density_radius_class': ['lgtree', 'sapling', 'lgtree']})
    result = trees._calc_conpyro_live_density(parents, records)
    assert result.conpyro_live_tree_density.iloc[:3].tolist() == [200., 0., 0.]
    assert pd.isna(result.conpyro_live_tree_density.iloc[3])


def test_generated_inputs_export_models_and_open_canopy_without_rescuing_exclusions():
    rows = []
    for uid, density, substrate, excluded in [('f', 5., 'HG', False), ('g', 0., 'HG', False),
                                               ('s', 0., 'ST', False), ('x', 0., 'HG', True)]:
        row = dict(unique_id=uid, plot_id=uid, _date='2025-06-01', treatment_area='a', treatment_unit='u',
                   treatment_type='untreated', conpyro_live_tree_density=density, dom_substrate=substrate,
                   _trees_excluded=excluded, SPECIES_PCT_1=100 if density else 0, cc=np.nan if not density else 50.)
        row.update({f'SPECIES_CD_{i}': 'FDI' if i == 1 and density else None for i in range(1, 7)})
        for field in ['x', 'y', 'plot_elevation', 'plot_slope_pct', 'plot_aspect', 'stand_pct_cnfr_live',
                      'conpyro_cfl_ovrstry', 'conpyro_cbd_ovrstry', 'conpyro_cfl_midstry', 'conpyro_cbd_midstry',
                      'conpyro_dead_branch_fl_midstry', 'conpyro_ht_ovrstry_live', 'conpyro_ht_midstry_live',
                      'conpyro_ht_midstry_dead', 'conpyro_cbh_ovrstry', 'conpyro_cbh_midstry', 'conpyro_fsg',
                      'ffl_duff_kgpm2', 'ffl_litter_kgpm2', 'woody_kgpm2_conpyro_lt7cm_7',
                      'grass_kgpm2', 'herb_forb_kgpm2', 'shrubs_kgpm2']:
            row[field] = 0.1
        rows.append(row)
    source = pd.DataFrame(rows)
    source['form_select'] = 'trees'
    source['_tree_parent_present'] = True
    source['conpyro_live_trees_present'] = [True, False, False, None]
    source['_trees_confirmed_absent'] = [False, True, True, False]
    result, _ = conpyro_attributes.gen_conpyro_df(source, copy.deepcopy(default_conpyro_dict))
    result = result.set_index('unique_id')
    assert result.loc[['f', 'g', 's'], 'sros_model'].tolist() == [13, 31, 31]
    assert result.loc[['g', 's'], 'stand_type'].eq(10).all()
    assert result.loc[['g', 's'], 'stand_density'].eq('L').all()
    assert result.loc[['g', 's'], ['canopy_cover', 'ht_ovrstry_live', 'fsg']].eq(0).all(axis=None)
    assert 'x' not in result.index
    assert source.loc[1, 'cc'] is np.nan or pd.isna(source.loc[1, 'cc'])


def test_live_presence_does_not_use_invalid_radius_zero_density():
    parents = pd.DataFrame({'GlobalID': ['live'], 'unique_id': ['live'], 'dom_substrate': ['HG']})
    records = pd.DataFrame({'ParentGlobalID': ['live'], 'tree_status': ['L'], 'tree_count': [1.],
                            'tree_dens_live_ha': [0.], 'tree_density_affected': [True]})
    result = trees._calc_conpyro_live_density(parents, records)
    assert result.conpyro_live_trees_present.iloc[0]
    assert pd.isna(result.conpyro_live_tree_density.iloc[0])
    assigned = conpyro_attributes._calc_surface_models(result, default_conpyro_dict['sros_model'])
    assert assigned.sros_model.iloc[0] == 13


def test_surface_assignment_uses_live_trees_before_substrate_and_preserves_missing(caplog):
    source = pd.DataFrame({
        'unique_id': ['live', 'grass', 'herbs', 'mixed', 'low', 'tall', 'bryoid', 'unknown', 'excluded'],
        'conpyro_live_tree_density': [1., 0., 0., 0., 0., 0., 0., np.nan, 0.],
        'dom_substrate': ['ST', 'HG', 'HF', 'HE', 'SL', 'ST', 'BY', 'HG', 'HG'],
        '_trees_excluded': [False] * 8 + [True],
    })
    result = conpyro_attributes._calc_surface_models(source, default_conpyro_dict['sros_model'])
    assert result.sros_model.iloc[:6].tolist() == [13, 31, 31, 31, 31, 31]
    assert result.surface_fuel_type.iloc[:6].tolist() == ['forest', 'grass_herbs', 'grass_herbs', 'grass_herbs', 'shrubs', 'shrubs']
    assert result.sros_model.iloc[6:].isna().all()
    assert {'bryoid', 'unknown'} <= {r.unique_id for r in caplog.records}
    assert 'excluded' not in {r.unique_id for r in caplog.records}
    assert 'sros_model' not in source


def test_surface_model_mapping_can_be_overridden():
    source = pd.DataFrame({'unique_id': ['f', 'g', 's'], 'conpyro_live_tree_density': [10., 0., 0.],
                           'dom_substrate': ['HG', 'HG', 'ST']})
    result = conpyro_attributes._calc_surface_models(source, {'forest': '9c', 'grass_herbs': 30, 'shrubs': 31})
    assert result.sros_model.tolist() == [9, 30, 31]


@pytest.mark.parametrize('value', [True, None, 13.5, 999, np.nan])
def test_surface_model_mapping_rejects_invalid_configuration(value):
    settings = copy.deepcopy({'forest': 13, 'grass_herbs': 31, 'shrubs': 31})
    settings['forest'] = value
    with pytest.raises(ValueError, match='sros_model'):
        conpyro_attributes._calc_surface_models(pd.DataFrame(), settings)


def test_unknown_live_sapling_count_does_not_prove_treeless():
    parents = pd.DataFrame({'GlobalID': ['dead'], 'unique_id': ['dead'], 'dom_substrate': ['HG']})
    records = pd.DataFrame({'ParentGlobalID': ['dead'], 'tree_status': ['D'], 'tree_count': [1.],
                            'tree_dens_live_ha': [0.]})
    saplings = pd.DataFrame({'ParentGlobalID': ['dead'], 'sapling_live_count': [np.nan]})
    result = trees._calc_conpyro_live_density(parents, records, saplings)
    assert pd.isna(result.conpyro_live_trees_present.iloc[0])
    assigned = conpyro_attributes._calc_surface_models(result, default_conpyro_dict['sros_model'])
    assert pd.isna(assigned.sros_model.iloc[0])


@pytest.mark.parametrize('large_present', ['Y', None])
def test_zero_saplings_do_not_establish_absent_direct_trees(large_present):
    parents = pd.DataFrame({'GlobalID': ['p'], 'unique_id': ['p'], 'dom_substrate': ['HG'],
                            'tree_large_present': [large_present], 'tree_small_present': ['N'], 'sapling_present': ['Y']})
    records = pd.DataFrame(columns=['ParentGlobalID', 'tree_status', 'tree_count', 'tree_dens_live_ha'])
    saplings = pd.DataFrame({'ParentGlobalID': ['p'], 'sapling_live_count': [0.]})
    result = trees._calc_conpyro_live_density(parents, records, saplings)
    assert pd.isna(result.conpyro_live_trees_present.iloc[0])
