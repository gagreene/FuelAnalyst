"""Grass duff moisture comes from weather DMC, never a static moisture regime."""
import importlib
import logging

import numpy as np
import pandas as pd
import pytest


@pytest.mark.parametrize('duff, accepted', [
    (9.99, False), (10., True), (197.19, True), (197.19998, True),
    (197.19999, False), (197.2, False), (197.21, False),
])
def test_duff_moisture_checks_burnup_float_boundary(caplog, duff, accepted):
    module = importlib.import_module('fuel_analyst.components.fofem_moisture')
    frame = pd.DataFrame({'#PlotId': ['forest'], 'mc_dmc': [duff], 'mc_sa': [10.], 'dc': [100.]})

    result = module.calc_fuel_moisture_content(frame, logging.getLogger(__name__))

    assert result['DuffMoisture'].tolist() == ([duff] if accepted else [])
    assert [r.issue_code for r in caplog.records] == ([] if accepted else ['fofem_duff_moisture_invalid'])


def test_grass_duff_moisture_uses_weather_dmc_and_preserves_existing_values():
    module = importlib.import_module('fuel_analyst.components.fofem_moisture')
    source = pd.DataFrame({'#PlotId': ['forest', 'grass', 'shrub', 'legacy'],
                           'surface_fuel_type': ['forest', 'grass_herbs', 'shrubs', 'grass_herbs'],
                           'stand_type': ['P', 10, 10, 10], 'dmc': [40., 40., 70., np.nan],
                           'mc_sa': [10.] * 4, 'mc_dmc': [150., np.nan, np.nan, 80.],
                           'dc': [100.] * 4, 'DuffMoisture': [20.] * 4})
    result = module.calc_fuel_moisture_content(source, logging.getLogger(__name__))
    expected = [150., 20 + np.exp((244.72 - 40) / 43.43), 20 + np.exp((244.72 - 70) / 43.43), 80.]
    assert result.mc_dmc.tolist() == pytest.approx(expected)
    assert result.DuffMoisture.tolist() == pytest.approx(expected)
    assert source.mc_dmc.isna().sum() == 2


@pytest.mark.parametrize('invalid', [np.nan, -1., np.inf, 'bad'])
def test_grass_missing_duff_moisture_is_not_replaced_by_regime(caplog, invalid):
    module = importlib.import_module('fuel_analyst.components.fofem_moisture')
    source = pd.DataFrame({'#PlotId': ['missing'], 'stand_type': [10], 'dmc': [invalid],
                           'mc_sa': [10.], 'mc_dmc': [np.nan], 'dc': [100.], 'DuffMoisture': [20.]})
    result = module.calc_fuel_moisture_content(source, logging.getLogger(__name__))
    assert result.empty
    assert {r.unique_id for r in caplog.records} == {'missing'}
    assert caplog.records[0].issue_code == 'fofem_duff_moisture_invalid'
    assert 'DMC' in caplog.records[0].getMessage()


def test_invalid_text_mc_dmc_is_rebuilt_from_weather():
    module = importlib.import_module('fuel_analyst.components.fofem_moisture')
    frame = pd.DataFrame({'stand_type': [10], 'mc_dmc': pd.Series(['bad'], dtype='string'), 'dmc': [40.]})
    result = module.derive_grass_duff_moisture(frame)
    assert result.mc_dmc.iloc[0] == pytest.approx(20 + np.exp((244.72 - 40) / 43.43))


@pytest.mark.parametrize('moisture, accepted', [(2.99, False), (3., True), (298., True), (298.01, False)])
def test_ten_hour_moisture_uses_unrounded_limits(caplog, moisture, accepted):
    module = importlib.import_module('fuel_analyst.components.fofem_moisture')
    frame = pd.DataFrame({'#PlotId': ['forest'], 'mc_dmc': [20.], 'mc_sa': [moisture], 'dc': [100.]})

    result = module.calc_fuel_moisture_content(frame, logging.getLogger(__name__))

    assert result['wfl10HourMoisture'].tolist() == ([moisture] if accepted else [])
    assert [r.issue_code for r in caplog.records] == ([] if accepted else ['fofem_10h_moisture_invalid'])


@pytest.mark.parametrize('moisture, accepted', [(0.99, False), (1., True), (300., True), (300.01, False)])
def test_thousand_hour_moisture_uses_unrounded_limits(caplog, monkeypatch, moisture, accepted):
    module = importlib.import_module('fuel_analyst.components.fofem_moisture')
    frame = pd.DataFrame({'#PlotId': ['forest'], 'mc_dmc': [20.], 'mc_sa': [10.], 'dc': [100.]})
    # A nonnegative weather DC cannot produce the upper boundary through the real conversion.
    monkeypatch.setattr(module.mc, 'dc_mc', lambda dc: np.full_like(dc, moisture))

    result = module.calc_fuel_moisture_content(frame, logging.getLogger(__name__))

    assert result['wfl1000HourMoisture'].tolist() == ([moisture] if accepted else [])
    assert [r.issue_code for r in caplog.records] == ([] if accepted else ['fofem_1000h_moisture_invalid'])


@pytest.mark.parametrize('field, issue_code', [
    ('mc_sa', 'fofem_10h_moisture_invalid'), ('mc_dmc', 'fofem_duff_moisture_invalid'),
    ('dc', 'fofem_1000h_moisture_invalid'),
])
@pytest.mark.parametrize('value', [None, np.inf, -np.inf, 'invalid'])
def test_unusable_required_moisture_skips_even_with_no_fuel(caplog, field, issue_code, value):
    module = importlib.import_module('fuel_analyst.components.fofem_moisture')
    frame = pd.DataFrame([{'#PlotId': 'forest', 'mc_dmc': 20., 'mc_sa': 10., 'dc': 100.,
                           'Duff': 0., 'wfl10Hour': 0., 'wfl20plusS': 0., field: value}])

    result = module.calc_fuel_moisture_content(frame, logging.getLogger(__name__))

    assert result.empty
    assert [(r.levelname, r.unique_id, r.issue_code) for r in caplog.records] == [('WARNING', 'forest', issue_code)]


def test_weather_dc_must_be_nonnegative_and_yield_valid_moisture(caplog):
    module = importlib.import_module('fuel_analyst.components.fofem_moisture')
    frame = pd.DataFrame({'#PlotId': ['negative', 'zero', 'too-dry'], 'mc_dmc': 20., 'mc_sa': 10.,
                          'dc': [-0.01, 0., 2000.]})

    result = module.calc_fuel_moisture_content(frame, logging.getLogger(__name__))

    assert result['#PlotId'].tolist() == ['zero']
    assert result['wfl1000HourMoisture'].tolist() == [100.]
    assert {(r.unique_id, r.issue_code) for r in caplog.records} == {
        ('negative', 'fofem_1000h_moisture_invalid'), ('too-dry', 'fofem_1000h_moisture_invalid'),
    }


def test_weather_dmc_reaches_both_emissions_moisture_helpers(tmp_path, monkeypatch):
    import sys
    import types

    package = types.ModuleType('pyfofem')
    package.pyfofem = types.SimpleNamespace()
    monkeypatch.setitem(sys.modules, 'pyfofem', package)
    fire_path = tmp_path / 'fire.csv'
    consume_path = tmp_path / 'consume.csv'
    pd.DataFrame({'unique_id': ['p'], 'wx_date': [20250615], 'hfi': [100.], 'flame_res_time_sec': [30.],
                  'flame_depth_m': [0.5],
                  'instand_ws_mps': [1.], 'temp': [20.], 'mc_sa': [10.], 'mc_dmc': [np.nan], 'dmc': [40.],
                  'dc': [100.], 'cfb': [0.], 'surface_fuel_type': ['shrubs'], 'stand_type': [10]}).to_csv(fire_path, index=False)
    pd.DataFrame({'#PlotId': ['p'], 'DuffMoisture': [90.]}).to_csv(consume_path, index=False)
    for name in ['fofem_emissions', 'fofem_gui_emissions']:
        module = importlib.import_module(f'fuel_analyst.components.{name}')
        kwargs = {'consume_model': 'C'} if name == 'fofem_gui_emissions' else {}
        merged = module._get_merged_consumption_df(str(fire_path), 'unique_id', str(consume_path), **kwargs)
        assert merged.dmc.tolist() == [40.]
        result = module._calc_fuel_moisture_content(merged)
        assert result.DuffMoisture.tolist() == pytest.approx([20 + np.exp((244.72 - 40) / 43.43)])


@pytest.mark.parametrize('stand_type', [
    10, 20, 21, 22, '10', '20', '21', '22', '20.0',
    'WHEAT_UNHARVESTED', 'WHEAT_HARVESTED', 'WHEAT_BALED',
    'wheat_unharvested', 'wheat_harvested', 'wheat_baled',
])
def test_wheat_and_grass_derive_only_unusable_duff_moisture(stand_type):
    module = importlib.import_module('fuel_analyst.components.fofem_moisture')
    frame = pd.DataFrame({'stand_type': stand_type, 'mc_dmc': [np.nan, 80., -1., 197.21],
                          'dmc': [28.493, np.nan, 28.493, 28.493]})

    result = module.derive_grass_duff_moisture(frame)

    assert result['mc_dmc'].tolist() == pytest.approx([165.292276, 80., -1., 197.21])
