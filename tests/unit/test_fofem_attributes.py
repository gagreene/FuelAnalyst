import logging

import numpy as np
import pandas as pd
import pytest

from fuel_analyst.components import fofem_units
from fuel_analyst.components.fofem_attributes import gen_fofem_consumption_df, gen_fofem_gui_app_tree_df

_CONSUME_LOAD_AND_DEPTH_COLS = fofem_units.FOFEM_LOAD_COLUMNS + fofem_units.FOFEM_DEPTH_COLUMNS


def _make_consumption_input_df():
    """
    Build a minimal plot-level DataFrame with all columns gen_fofem_consumption_df() requires.

    :return: DataFrame with one row of SI-unit source values.
    """
    return pd.DataFrame({
        'unique_id': ['p1'], 'SPECIES_CD_1': ['PY'], 'dom_substrate': ['HG'],
        'fofem_shrub_group': [''], 'treatment_type': ['untreated'],
        'ffl_litter_kgpm2': [1.0], 'ffl_duff_kgpm2': [2.0], 'stand_duff_depth_cm': [3.0],
        'woody_kgpm2_fofem_sound_0_635': [0.1], 'woody_kgpm2_fofem_sound_2_54': [0.2],
        'woody_kgpm2_fofem_sound_7_62': [0.3], 'woody_kgpm2_fofem_sound_15_24': [0.4],
        'woody_kgpm2_fofem_sound_22_86': [0.5], 'woody_kgpm2_fofem_sound_50_8': [0.6],
        'woody_kgpm2_fofem_sound_gt50_8': [0.7],
        'woody_kgpm2_fofem_rotten_0_635': [0.1], 'woody_kgpm2_fofem_rotten_2_54': [0.2],
        'woody_kgpm2_fofem_rotten_7_62': [0.8],
        'woody_kgpm2_fofem_rotten_15_24': [0.9], 'woody_kgpm2_fofem_rotten_22_86': [1.0],
        'woody_kgpm2_fofem_rotten_50_8': [1.1], 'woody_kgpm2_fofem_rotten_gt50_8': [1.2],
        'grass_kgpm2': [0.3], 'herbs_kgpm2': [0.5], 'shrubs_kgpm2': [0.1],
        'fuel_bed_depth_m': [0.25],
        'stand_foliage_fofem_kgpm2_sum': [0.4], 'stand_branches_fofem_kgpm2_sum': [0.5],
    })


def test_gen_fofem_gui_app_tree_df_converts_units_and_status():
    plots = pd.DataFrame({'unique_id': ['p1'], 'treatment_type': ['treated'], 'year': [2025]})
    trees = pd.DataFrame({
        'unique_id': ['p1', 'p1'], 'status': ['L', 'L'],
        'spp_fofem': ['DF', 'DF'], 'dens_live_ha': [2.47105, 4.9421],
        'dbh': [2.54, 5.08], 'ht': [10.0, 20.0], 'crown_depth': [4.0, 5.0],
        'decay_cnfr': [1, 2], 'decay_brdlf': [np.nan, np.nan], 'crown_class': ['D', 'C'],
    })
    result = gen_fofem_gui_app_tree_df(plots, trees)
    assert result['TreeExpansionFactor'].tolist() == pytest.approx([1.0, 2.0])
    assert result['Diameter'].tolist() == pytest.approx([1.0, 2.0])
    assert result['TreeStatus'].tolist() == ['H', 'U']
    assert result['CrownRatio'].tolist() == pytest.approx([40.0, 25.0])
    assert (result['EquationType'] == 'CRNSCH').all()


def test_gen_fofem_gui_app_tree_df_filters_out_dead_trees():
    plots = pd.DataFrame({'unique_id': ['p1'], 'treatment_type': ['treated'], 'year': [2025]})
    trees = pd.DataFrame({
        'unique_id': ['p1', 'p1'], 'status': ['L', 'D'],
        'spp_fofem': ['DF', 'DF'], 'dens_live_ha': [2.47105, 0.0],
        'dbh': [2.54, 2.54], 'ht': [10.0, 10.0], 'crown_depth': [4.0, np.nan],
        'decay_cnfr': [1, 3], 'decay_brdlf': [np.nan, np.nan], 'crown_class': ['D', 'D'],
    })
    result = gen_fofem_gui_app_tree_df(plots, trees)
    assert len(result) == 1
    assert not result['CrownRatio'].isna().any()


def test_gen_fofem_gui_app_tree_df_missing_status_logs_and_falls_back(caplog):
    plots = pd.DataFrame({'unique_id': ['p1'], 'treatment_type': ['treated'], 'year': [2025]})
    trees = pd.DataFrame({
        'unique_id': ['p1', 'p1'],
        'spp_fofem': ['DF', 'DF'], 'dens_live_ha': [2.47105, 0.0],
        'dbh': [2.54, 2.54], 'ht': [10.0, 10.0], 'crown_depth': [4.0, np.nan],
        'decay_cnfr': [1, 3], 'decay_brdlf': [np.nan, np.nan], 'crown_class': ['D', 'D'],
    })
    with caplog.at_level(logging.ERROR, logger='fuel_analyst.components.fofem_attributes'):
        result = gen_fofem_gui_app_tree_df(plots, trees)

    assert len(result) == 1
    matching = [r for r in caplog.records if getattr(r, 'issue_code', None) ==
                'fofem_attributes_missing_status_column']
    assert len(matching) == 1


def test_gen_fofem_consumption_df_assigns_categories_and_moisture_defaults():
    df = _make_consumption_input_df()
    params = {'region': 'West', 'season': 'Summer', 'moisture_regime': 'unknown',
              'soil_heating': {'use_soil_heating': False}}
    result = gen_fofem_consumption_df(df, params)
    assert result.loc[0, 'CoverGroup'] == 'Ponderosa'
    assert result.loc[0, 'FuelCategory'] == 'Natural'
    assert result.loc[0, 'DuffMoisture'] == 20
    assert result.loc[0, 'wfl10HourMoisture'] == 6


def test_gen_fofem_consumption_df_defaults_to_si_when_key_absent():
    """A legacy fofem_consume_params dict predating fofem_processing_units must still work."""
    df = _make_consumption_input_df()
    params = {'region': 'West', 'season': 'Summer', 'moisture_regime': 'unknown',
              'soil_heating': {'use_soil_heating': False}}
    result = gen_fofem_consumption_df(df, params)
    # SI: no conversion applied to the SI source values
    assert result.loc[0, 'Litter'] == pytest.approx(1.0)
    assert result.loc[0, 'DuffDepth'] == pytest.approx(3.0)


def test_gen_fofem_consumption_df_si_is_unconverted_full_precision():
    df = _make_consumption_input_df()
    df.loc[0, 'ffl_litter_kgpm2'] = 1.23456789
    params = {'region': 'West', 'season': 'Summer', 'moisture_regime': 'unknown',
              'soil_heating': {'use_soil_heating': False}, 'fofem_processing_units': 'SI'}
    result = gen_fofem_consumption_df(df, params)
    assert result.loc[0, 'Litter'] == pytest.approx(1.23456789, abs=1e-9)
    assert result.loc[0, 'DuffDepth'] == pytest.approx(3.0)


def test_gen_fofem_consumption_df_imperial_converts_loads_and_depth():
    df = _make_consumption_input_df()
    params = {'region': 'West', 'season': 'Summer', 'moisture_regime': 'unknown',
              'soil_heating': {'use_soil_heating': False}, 'fofem_processing_units': 'Imperial'}
    result = gen_fofem_consumption_df(df, params)
    assert result.loc[0, 'Litter'] == pytest.approx(1.0 * fofem_units.LOAD_CONV_FACTOR, abs=1e-9)
    assert result.loc[0, 'DuffDepth'] == pytest.approx(3.0 * fofem_units.DEPTH_CONV_FACTOR, abs=1e-9)


def test_gen_fofem_consumption_df_rejects_invalid_units():
    df = _make_consumption_input_df()
    params = {'region': 'West', 'season': 'Summer', 'moisture_regime': 'unknown',
              'soil_heating': {'use_soil_heating': False}, 'fofem_processing_units': 'metric'}
    with pytest.raises(ValueError, match='Invalid FOFEM processing units'):
        gen_fofem_consumption_df(df, params)


def test_gen_fofem_consumption_df_column_names_and_order_unchanged_by_units():
    df = _make_consumption_input_df()
    base_params = {'region': 'West', 'season': 'Summer', 'moisture_regime': 'unknown',
                   'soil_heating': {'use_soil_heating': False}}
    si_result = gen_fofem_consumption_df(df, {**base_params, 'fofem_processing_units': 'SI'})
    imperial_result = gen_fofem_consumption_df(df, {**base_params, 'fofem_processing_units': 'Imperial'})
    assert si_result.columns.tolist() == imperial_result.columns.tolist()
