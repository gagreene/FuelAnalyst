import numpy as np
import pandas as pd
import pytest

from fuel_analyst.components.plants_regen import (
    _calc_plants_fccs_fofem_attributes,
    _get_dom_substrate,
    _get_photoload_biomass,
    _process_regen,
)


def test_get_photoload_biomass_known_unknown_and_zero_codes():
    assert _get_photoload_biomass('MOSS', 50, 10) == 0
    assert _get_photoload_biomass('VAGL', 20, 35.56) == pytest.approx(0.104)
    assert np.isnan(_get_photoload_biomass('UNKNOWN', 20, 10))


@pytest.mark.parametrize(
    ('covers', 'height', 'expected'),
    [
        ([0, 0, 0, 60], 1.0, 'SL'),
        ([0, 0, 0, 60], 2.0, 'ST'),
        ([60, 0, 0, 0], 0.0, 'BY'),
        ([0, 60, 0, 0], 0.0, 'HG'),
        ([0, 0, 60, 0], 0.0, 'HF'),
        ([0, 30, 30, 0], 0.0, 'HE'),
    ],
)
def test_get_dom_substrate_rules(covers, height, expected):
    df = pd.DataFrame([dict(zip(
        ['bryoid_pct_total', 'grass_pct_total', 'herb_forb_pct_total', 'shrubs_pct_total'], covers
    )) | {'shrubs_ht_avg': height}])
    result, keep = _get_dom_substrate(df)
    assert result.loc[0, 'dom_substrate'] == expected
    assert keep == ['dom_substrate']


def test_calc_plants_fccs_fofem_attributes_aggregates_duplicate_shrubs():
    row = {'dom_substrate': 'SL'}
    for i in range(1, 6):
        row[f'pc_species_{i}_label'] = None
        row[f'pc_species_{i}_plCode'] = None
        row[f'pc_species_{i}_pct'] = 0
    row.update({
        'pc_species_1_label': 'Shrub', 'pc_species_1_plCode': 'ARTR', 'pc_species_1_pct': 60,
        'pc_species_2_label': 'Shrub', 'pc_species_2_plCode': 'ARTR', 'pc_species_2_pct': 20,
        'pc_species_3_label': 'Shrub', 'pc_species_3_plCode': 'VAGL', 'pc_species_3_pct': 20,
    })
    result, keep = _calc_plants_fccs_fofem_attributes(pd.DataFrame([row]))
    assert result.loc[0, 'fccs_shrub_species'] == 'ARTR:80.0 | VAGL:20.0'
    assert result.loc[0, 'fofem_shrub_group'] == 'Sagebrush'
    assert keep == ['fofem_shrub_group']


def test_process_regen_normalizes_sampled_proportion_and_maps_to_plot():
    plots = pd.DataFrame({'GlobalID': ['p1', 'p2']})
    regen = pd.DataFrame({
        'ParentGlobalID': ['p1', 'p1'],
        'rgn_live_small_cnt': [2.0, 1.0], 'rgn_small_plot_proportion': [0.5, 1.0],
        'rgn_live_tall_cnt': [1.0, 2.0], 'rgn_tall_plot_proportion': [1.0, 0.5],
    })
    result, _, keep = _process_regen(plots, regen)
    assert result['dens_regen_live_small_ha'].tolist() == [500.0, 0.0]
    assert result['dens_regen_live_tall_ha'].tolist() == [500.0, 0.0]
    assert keep == ['dens_regen_live_small_ha', 'dens_regen_live_tall_ha']
