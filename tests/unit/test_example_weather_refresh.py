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
