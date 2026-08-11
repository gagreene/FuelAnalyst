import numpy as np
import pandas as pd
import pytest

from fuel_analyst.components.fofem_attributes import gen_fofem_consumption_df, gen_fofem_tree_df


def test_gen_fofem_tree_df_converts_units_and_status():
    plots = pd.DataFrame({'unique_id': ['p1'], 'treatment_type': ['treated'], 'year': [2025]})
    trees = pd.DataFrame({
        'unique_id': ['p1', 'p1'], 'spp_fofem': ['DF', 'DF'], 'dens_live_ha': [2.47105, 4.9421],
        'dbh': [2.54, 5.08], 'ht': [10.0, 20.0], 'crown_depth': [4.0, 5.0],
        'decay_cnfr': [1, 2], 'decay_brdlf': [np.nan, np.nan], 'crown_class': ['D', 'C'],
    })
    result = gen_fofem_tree_df(plots, trees)
    assert result['TreeExpansionFactor'].tolist() == pytest.approx([1.0, 2.0])
    assert result['Diameter'].tolist() == pytest.approx([1.0, 2.0])
    assert result['TreeStatus'].tolist() == ['H', 'U']
    assert result['CrownRatio'].tolist() == pytest.approx([40.0, 25.0])
    assert (result['EquationType'] == 'CRNSCH').all()


def test_gen_fofem_consumption_df_assigns_categories_and_moisture_defaults():
    df = pd.DataFrame({
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
    params = {'region': 'West', 'season': 'Summer', 'moisture_regime': 'unknown',
              'soil_heating': {'use_soil_heating': False}}
    result = gen_fofem_consumption_df(df, params)
    assert result.loc[0, 'CoverGroup'] == 'Ponderosa'
    assert result.loc[0, 'FuelCategory'] == 'Natural'
    assert result.loc[0, 'DuffMoisture'] == 20
    assert result.loc[0, 'wfl10HourMoisture'] == 6
