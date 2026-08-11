import importlib
import sys
import types

import numpy as np
import pandas as pd
import pytest


fake_package = types.ModuleType('pyfofem')
fake_package.pyfofem = types.SimpleNamespace()
sys.modules['pyfofem'] = fake_package

emissions = importlib.import_module('fuel_analyst.components.fofem_emissions')
mortality = importlib.import_module('fuel_analyst.components.fofem_mortality')


def test_emissions_moisture_season_and_crown_transformations():
    df = pd.DataFrame({
        'mc_sa': [10.0], 'mc_dmc': [20.0], 'dc': [0.0], 'cfb': [0.25],
        'wx_date': [20250615],
    })
    result = emissions._get_pct_crown_burned(emissions._get_season(emissions._calc_fuel_moisture_content(df)))
    assert result.loc[0, 'wfl10HourMoisture'] == 10
    assert result.loc[0, 'wfl1000HourMoisture'] == pytest.approx(100)
    assert result.loc[0, 'PercentCrownBurned'] == 25
    assert result.loc[0, 'season'] == 'Summer'


def test_emissions_plot_ids_cover_groups_and_numeric_arrays():
    df = pd.DataFrame({'#PlotId': ['Plot One'], 'value': ['bad']})
    normalized, mapping = emissions._gen_plot_id(df)
    assert normalized.loc[0, '#PlotId'] == 'Plot_One'
    assert emissions._restore_plot_id(normalized, mapping).loc[0, '#PlotId'] == 'Plot One'
    assert emissions._to_float_arr(df, 'value', 4).tolist() == [4.0]
    assert emissions._sanitize_cover_group(pd.Series(['"Ponderosa"', None, 'NA'])).tolist() == [
        'Ponderosa', '', ''
    ]


def test_emissions_season_requires_weather_date():
    with pytest.raises(ValueError, match='wx_date'):
        emissions._get_season(pd.DataFrame({'other': [1]}))


def test_mortality_basal_area_and_severity_boundaries():
    plots = pd.DataFrame({'id': ['p1', 'p2', 'p3']})
    trees = pd.DataFrame({
        'tree_id': ['p1', 'p2', 'p3'], 'ba_live_ha': [10.0, 10.0, 10.0],
        'tree_dead_ba_crnsch': [2.0, 5.0, 7.0],
    })
    result = mortality._calc_severity_class(mortality._calc_plot_ba_killed(plots, 'id', trees, 'tree_id'))
    assert result['prop_dead_ba_crnsch'].tolist() == pytest.approx([0.2, 0.5, 0.7])
    assert result['fire_severity'].tolist() == ['low', 'mod', 'high']
