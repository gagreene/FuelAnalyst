import importlib
import logging
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
    assert result['total_live_ba_m2pha'].tolist() == pytest.approx([10.0, 10.0, 10.0])
    assert result['dead_ba_crnsch_m2pha'].tolist() == pytest.approx([2.0, 5.0, 7.0])
    assert 'total_live_ba' not in result.columns
    assert 'dead_ba_crnsch' not in result.columns


def test_dropna_logs_per_plot_warning_for_rows_with_missing_required_columns(caplog):
    plot_fire_df = pd.DataFrame({
        'unique_id': ['A', 'B'],
        'instand_ws_mps': [1.0, np.nan],
        'canopy_cover': [50.0, 50.0],
        'ht_ovrstry_live': [20.0, 20.0],
        'fsg': [1.0, 1.0], 'ws': [1.0, 1.0], 'hfi': [1.0, 1.0],
        'fire_type': ['surface', 'surface'], 'temp': [20.0, 20.0],
    })
    required_cols = [
        'instand_ws_mps', 'canopy_cover', 'ht_ovrstry_live', 'fsg', 'ws', 'hfi', 'fire_type', 'temp',
    ]
    filtered_required_cols = [c for c in required_cols if c in plot_fire_df.columns]

    with caplog.at_level(logging.WARNING, logger='fuel_analyst.components.fofem_mortality'):
        mortality._log_and_drop_incomplete_rows(plot_fire_df, filtered_required_cols, 'unique_id')

    matching = [r for r in caplog.records if getattr(r, 'unique_id', None) == 'B']
    assert len(matching) == 1
    assert 'instand_ws_mps' in matching[0].message


def test_no_required_columns_present_logs_general_error(caplog):
    plot_fire_df = pd.DataFrame({'unique_id': ['A'], 'other_col': [1.0]})
    with caplog.at_level(logging.WARNING, logger='fuel_analyst.components.fofem_mortality'):
        mortality._log_and_drop_incomplete_rows(plot_fire_df, [], 'unique_id')
    assert len(caplog.records) == 1
    assert not hasattr(caplog.records[0], 'unique_id') or caplog.records[0].unique_id is None


def test_prepare_soil_family_logs_general_error_when_column_missing(caplog):
    df = pd.DataFrame({'other_col': [1]})
    with caplog.at_level(logging.WARNING, logger='fuel_analyst.components.fofem_emissions'):
        result = emissions._prepare_soil_family(df)
    assert result is None
    assert len(caplog.records) == 1
    assert 'SoilFamily' in caplog.records[0].message
