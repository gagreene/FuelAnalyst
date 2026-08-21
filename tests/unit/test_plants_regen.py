import numpy as np
import pandas as pd
import pytest

from fuel_analyst.components.plants_regen import (
    _calc_pc_flammable,
    _calc_plants_fccs_fofem_attributes,
    _get_dom_substrate,
    _get_photoload_biomass,
    _process_regen,
)


def test_calc_pc_flammable_computes_survey123_formula():
    df = pd.DataFrame({'pc_rock': [10.0], 'pc_mineral_soil': [20.0]})
    result, keep = _calc_pc_flammable(df)
    assert result.loc[0, 'pc_nonflammable'] == 30.0
    assert result.loc[0, 'pc_flammable'] == 70.0
    assert result.loc[0, 'pc_flammable_note'] == ''
    assert keep == ['pc_nonflammable', 'pc_flammable', 'pc_flammable_note']


def test_calc_pc_flammable_treats_one_missing_value_as_zero():
    df = pd.DataFrame({'pc_rock': [5.0], 'pc_mineral_soil': [np.nan]})
    result, _ = _calc_pc_flammable(df)
    assert result.loc[0, 'pc_nonflammable'] == 5.0
    assert result.loc[0, 'pc_flammable'] == 95.0
    assert result.loc[0, 'pc_flammable_note'] == ''


def test_calc_pc_flammable_defaults_to_fully_flammable_when_no_data_provided():
    df = pd.DataFrame({'pc_rock': [np.nan], 'pc_mineral_soil': [np.nan]})
    result, _ = _calc_pc_flammable(df)
    assert result.loc[0, 'pc_nonflammable'] == 0.0
    assert result.loc[0, 'pc_flammable'] == 100.0
    assert 'No pc_rock or pc_mineral_soil cover provided' in result.loc[0, 'pc_flammable_note']


def test_calc_pc_flammable_defaults_to_fully_flammable_when_columns_are_missing():
    df = pd.DataFrame({'other_col': [1]})
    result, _ = _calc_pc_flammable(df)
    assert result.loc[0, 'pc_nonflammable'] == 0.0
    assert result.loc[0, 'pc_flammable'] == 100.0
    assert 'No pc_rock or pc_mineral_soil cover provided' in result.loc[0, 'pc_flammable_note']


def test_calc_pc_flammable_defaults_to_fully_flammable_when_result_out_of_range():
    df = pd.DataFrame({'pc_rock': [60.0], 'pc_mineral_soil': [60.0]})
    result, _ = _calc_pc_flammable(df)
    assert result.loc[0, 'pc_nonflammable'] == 0.0
    assert result.loc[0, 'pc_flammable'] == 100.0
    assert 'outside the valid 0-100 range' in result.loc[0, 'pc_flammable_note']


@pytest.mark.parametrize(
    ('code', 'reference_height', 'expected'),
    [
        ('AMAL', 35.56, 0.0690181 * (np.exp(0.0240242 * 50) - 1)),
        ('ARLA', 30.48, 0.0005745 * np.power(50, 1.16228)),
        ('CARU', 20.30, 0.0117766 * (np.exp(0.0379728 * 50) - 1)),
        ('FESC', 30.5, 0.0161917 * (np.exp(0.0330081 * 50) - 1)),
        ('MARE', 10.16, 0.000733871 * np.power(50, 1.16779)),
        ('SYAL', 35.56, 0.00119555 * 50 + 0.0000169686 * np.power(50, 2)),
        ('VAGL', 35.56, 0.398329 * (np.exp(0.0109776 * 50) - 1)),
        ('VASC', 17.78, 0.0025455 * 50),
        ('XETE', 25.4, 0.00366616 * 50),
    ],
)
def test_get_photoload_biomass_uses_final_models(code, reference_height, expected):
    assert _get_photoload_biomass(code, 50, reference_height) == pytest.approx(expected)


@pytest.mark.parametrize(
    'code',
    ['AMAL', 'ARLA', 'CARU', 'FESC', 'MARE', 'SYAL', 'VAGL', 'VASC', 'XETE'],
)
def test_get_photoload_biomass_models_pass_through_origin(code):
    assert _get_photoload_biomass(code, 0, 20) == pytest.approx(0)


def test_get_photoload_biomass_scales_with_height_and_handles_special_codes():
    reference_biomass = _get_photoload_biomass('VAGL', 20, 35.56)
    assert _get_photoload_biomass('VAGL', 20, 71.12) == pytest.approx(2 * reference_biomass)
    assert _get_photoload_biomass('MOSS', 50, 10) == 0
    assert _get_photoload_biomass('TREE', 50, 10) == 0
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
