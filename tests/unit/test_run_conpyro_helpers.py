import importlib
import sys
import types

import numpy as np
import pandas as pd
import pytest


fake_conpyro_package = types.ModuleType('conpyro')
fake_conpyro_package.conpyro = types.SimpleNamespace()
sys.modules['conpyro'] = fake_conpyro_package

fake_flame = types.ModuleType('flame_components')
fake_flame.get_mid_flame_ws = lambda **kwargs: np.asarray(kwargs['wind_speed']) / 2
fake_flame.get_flame_length = lambda **kwargs: np.asarray(kwargs['fire_intensity']) / 100
fake_flame.get_flame_residence_time = lambda **kwargs: np.ones(len(kwargs['ros'])) * 2
fake_flame.get_flame_depth = lambda **kwargs: np.asarray(kwargs['ros']) * np.asarray(kwargs['res_time'])
fake_flame.get_flame_height = lambda **kwargs: np.asarray(kwargs['flame_length']) / 2
fake_flame.get_flame_tilt = lambda **kwargs: np.ones(len(next(iter(kwargs.values())))) * 45
sys.modules['flame_components'] = fake_flame

module = importlib.import_module('fuel_analyst.run_conpyro')


def test_calc_instand_wind_uses_only_complete_rows():
    df = pd.DataFrame({
        'ws': [10.0, 10.0], 'canopy_cover': [50.0, None],
        'ht_ovrstry_live': [20.0, 20.0], 'fsg': [5.0, 5.0],
    })
    result = module._calc_instand_ws(df)
    assert result.loc[0, 'instand_ws_mps'] == 5
    assert np.isnan(result.loc[1, 'instand_ws_mps'])


def test_calc_flame_length_selects_crown_and_surface_models():
    df = pd.DataFrame({'fire_type': [3, 1], 'hfi': [1000.0, 500.0], 'ht_ovrstry_live': [10.0, 10.0]})
    result = module._calc_flame_length_m(df)
    assert result['flame_length_model'].tolist() == ['Butler et al. (2004)', 'Byram (1959)']
    assert result['flame_length_m'].tolist() == [20.0, 5.0]


def test_flame_residence_time_and_depth_use_fuelanalyst_units():
    df = pd.DataFrame({'hros': [3.0], 'tfc': [1.0], 'instand_ws_mps': [2.0]})
    result = module._calc_flame_depth(module._calc_flame_res_time(df))
    assert result.loc[0, 'flame_res_time_min'] == 2
    assert result.loc[0, 'flame_res_time_sec'] == 120
    assert result.loc[0, 'flame_depth_m'] == 6


@pytest.mark.parametrize('function', [module._calc_instand_ws, module._calc_flame_length_m])
def test_flame_helpers_reject_missing_required_columns(function):
    with pytest.raises(ValueError, match='Required columns'):
        function(pd.DataFrame({'wrong': [1]}))
