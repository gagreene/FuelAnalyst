"""The standalone example must refresh fuel assignments without losing weather rows."""
from pathlib import Path
import runpy

import pandas as pd


def test_example_refresh_preserves_weather_and_replaces_stale_plot_inputs(tmp_path):
    demo = runpy.run_path(str(Path(__file__).resolve().parents[2] / 'examples/run_fuel_analyst_conpyro_demo.py'))
    weather = tmp_path / 'weather.csv'
    fuels = tmp_path / 'fuels.csv'
    output = tmp_path / 'out/merged.csv'
    pd.DataFrame({'unique_id': ['a', 'a'], 'wx_date': [20240601, 20240602], 'ws': [3., 7.],
                  'stand_type': ['P', 'P'], 'sros_model': [13, 13]}).to_csv(weather, index=False)
    pd.DataFrame({'unique_id': ['a'], 'stand_type': [10], 'sros_model': [31],
                  'surface_fuel_type': ['shrubs']}).to_csv(fuels, index=False)
    demo['_refresh_weather_inputs'](str(weather), str(fuels), str(output))
    result = pd.read_csv(output)
    assert result.wx_date.tolist() == [20240601, 20240602]
    assert result.ws.tolist() == [3., 7.]
    assert result.sros_model.tolist() == [31, 31]
    assert result.stand_type.tolist() == [10, 10]


def test_cfis_example_refresh_adds_surface_model_and_fbp_fuel_type(tmp_path):
    """The CFIS demo must supply sros_model (required by the default use_csv setting) and FBP fuel types."""
    demo = runpy.run_path(str(Path(__file__).resolve().parents[2] / 'examples/run_fuel_analyst_cfis_demo.py'))
    weather = tmp_path / 'weather.csv'
    fuels = tmp_path / 'conpyro_df_fbp.csv'
    output = tmp_path / 'out/conpyro_df_wx_fbp.csv'
    pd.DataFrame({'unique_id': ['a', 'a', 'b'], 'wx_date': [20240601, 20240602, 20240601], 'ws': [3., 7., 5.],
                  'temp': [20., 22., 21.], 'fbp_fuel_type': [None, None, None]}).to_csv(weather, index=False)
    pd.DataFrame({'unique_id': ['a', 'b'], 'stand_type': ['P', 10], 'sros_model': [13, 31],
                  'surface_fuel_type': ['forest', 'grass_herbs'], 'fbp_fuel_type': ['C3', 'O1b']}).to_csv(fuels, index=False)
    demo['_refresh_weather_inputs'](str(weather), str(fuels), str(output))
    result = pd.read_csv(output)
    assert result.wx_date.tolist() == [20240601, 20240602, 20240601]
    assert result.ws.tolist() == [3., 7., 5.]
    assert result.temp.tolist() == [20., 22., 21.]
    assert result.sros_model.tolist() == [13, 13, 31]
    assert result.surface_fuel_type.tolist() == ['forest', 'forest', 'grass_herbs']
    assert result.fbp_fuel_type.tolist() == ['C3', 'C3', 'O1b']
