"""Grass emissions retain explicit consumption-file duff moisture for both backends."""
import importlib
import logging

import numpy as np
import pandas as pd
import pytest


@pytest.mark.parametrize('invalid', [np.nan, -1., np.inf, 'bad'])
def test_grass_duff_moisture_uses_configured_value_and_skips_missing_fallback(caplog, invalid):
    module = importlib.import_module('fuel_analyst.components.fofem_moisture')
    source = pd.DataFrame({'#PlotId': ['forest', 'grass', 'shrub', 'missing', 'numeric'],
                           'surface_fuel_type': ['forest', 'grass_herbs', 'shrubs', 'grass_herbs', ''],
                           'stand_type': ['P', 10, 10, 10, 10],
                           'mc_sa': [10.] * 5, 'mc_dmc': [150., np.nan, np.nan, np.nan, np.nan],
                           'dc': [100.] * 5, 'DuffMoisture': [80., 80., 100., invalid, 90.]})
    result = module.calc_fuel_moisture_content(source, logging.getLogger('fuel_analyst.components.fofem_emissions'))
    assert result['#PlotId'].tolist() == ['forest', 'grass', 'shrub', 'numeric']
    assert result.DuffMoisture.tolist() == [150., 80., 100., 90.]
    assert {r.unique_id for r in caplog.records} == {'grass', 'shrub', 'missing', 'numeric'}
    assert source.mc_dmc.isna().sum() == 4


def test_grass_metadata_reaches_both_emissions_moisture_helpers(tmp_path, monkeypatch):
    import sys
    import types

    package = types.ModuleType('pyfofem')
    package.pyfofem = types.SimpleNamespace()
    monkeypatch.setitem(sys.modules, 'pyfofem', package)
    fire_path = tmp_path / 'fire.csv'
    consume_path = tmp_path / 'consume.csv'
    pd.DataFrame({'unique_id': ['p'], 'wx_date': [20250615], 'hfi': [100.], 'flame_res_time_sec': [30.],
                  'instand_ws_mps': [1.], 'temp': [20.], 'mc_sa': [10.], 'mc_dmc': [np.nan],
                  'dc': [100.], 'cfb': [0.], 'surface_fuel_type': ['shrubs'], 'stand_type': [10]}).to_csv(fire_path, index=False)
    pd.DataFrame({'#PlotId': ['p'], 'DuffMoisture': [90.]}).to_csv(consume_path, index=False)
    for name in ['fofem_emissions', 'fofem_gui_emissions']:
        module = importlib.import_module(f'fuel_analyst.components.{name}')
        kwargs = {'consume_model': 'C'} if name == 'fofem_gui_emissions' else {}
        merged = module._get_merged_consumption_df(str(fire_path), 'unique_id', str(consume_path), **kwargs)
        assert merged.surface_fuel_type.tolist() == ['shrubs']
        result = module._calc_fuel_moisture_content(merged)
        assert result.DuffMoisture.tolist() == [90.]
