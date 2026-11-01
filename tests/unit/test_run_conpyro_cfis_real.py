"""The real vendored ConPyro must run the CFIS crown fire initiation model (cfo_model 10) through run_conpyro().

The other CFIS tests replace ConPyro with a stub, so they cannot see a failure inside it. After the vendored ConPyro was
refreshed to upstream 6086a4f, every CFIS run with array inputs failed with 'assignment destination is read-only'.

test_run_conpyro_helpers.py puts a fake flame_components in sys.modules when it is imported and relies on being the
first to import fuel_analyst.run_conpyro, which binds that name once. So this file does not import run_conpyro at
collection time (that would change which module the helper tests get), and its fixture gives these tests the real
flame_components instead.
"""
import copy
import importlib
import sys

import numpy as np
import pandas as pd
import pytest

# One real plot-and-weather row of examples/data/weather/conpyro_df_wx.csv (plot P15, 2024-06-09)
_ROW = {
    'unique_id': 'Demo_TU2_untreated_P15_2021', 'plot_id': 'P15', 'lat': 49.901, 'long': -120.216, 'elevation': 1160,
    'slope': 7.0, 'aspect': 62.0, 'stand_density': 'L', 'stand_type': 'P', 'fbp_fuel_type': None, 'pct_cnfr': 100.0,
    'canopy_cover': 36.67, 'cfl_ovrstry': 1.0494, 'cbd_ovrstry': 0.07227, 'cfl_midstry': 0.0, 'cbd_midstry': 0.0,
    'dead_branch_fl_midstry': 0.0, 'ht_ovrstry_live': 21.03, 'ht_midstry_live': None, 'ht_midstry_dead': None,
    'cbh_ovrstry': 6.513, 'cbh_midstry': None, 'fsg': 6.513, 'duff_fuel_load': 2.8593, 'litter_fuel_load': 0.32598,
    'woody_fuel_load': 0.31446, 'herbaceous_fuel_load': 0.11699, 'grass_fuel_load': 0.11521,
    'shrub_fuel_load': 0.0036007, 'wx_date': 20240609, 'season': 'Spring', 'temp': 19.983, 'pcp': 0.0, 'rh': 27.104,
    'ws': 7.78, 'wd': 175.719, 'ffmc': 92.3, 'dmc': 28.493, 'dc': 374.328, 'bui': 47.876, 'isi': 8.801, 'fwi': 19.846,
    'fwi_prcnt': 74.7,
}
_WINDS = [0.0, 4.0, 8.0, 15.0, 30.0]


@pytest.fixture
def run_conpyro_module(monkeypatch):
    """fuel_analyst.run_conpyro, with the real flame_components even when another test file installed a fake."""
    module = importlib.import_module('fuel_analyst.run_conpyro')
    if getattr(sys.modules.get('flame_components'), '__file__', None) is None:  # missing, or a fake without a file
        monkeypatch.delitem(sys.modules, 'flame_components', raising=False)  # monkeypatch puts a fake back afterwards
        real = importlib.import_module('flame_components')
    else:
        real = sys.modules['flame_components']
    monkeypatch.setattr(module, 'fc', real)
    return module


def _cfis_input(tmp_path, cfo_models=None):
    """Write five scenarios of the real row, one per wind speed, and return the CSV path."""
    df = pd.DataFrame([dict(_ROW, ws=ws, wx_date=20240609 + i) for i, ws in enumerate(_WINDS)])
    if cfo_models is not None:
        df['cfo_model'] = cfo_models
    path = tmp_path / 'conpyro_input.csv'
    df.to_csv(path, index=False)
    return str(path)


def _params(module, cfo_model):
    """Fire modelling settings with only ConPyro enabled, run serially with the given crown fire initiation model."""
    params = copy.deepcopy(module.default_fire_modelling_dict)
    params['num_workers'] = 1
    params['fofem_mortality']['run_model'] = False
    params['fofem_emissions']['run_model'] = False
    params['conpyro']['input_params']['cfo_model'] = cfo_model
    params['conpyro']['input_params']['time'] = 1200
    return params


def _run(module, tmp_path, cfo_model, cfo_models=None):
    """Run run_conpyro() on the five scenarios and return the fire behaviour results."""
    module.run_conpyro(
        out_dir=str(tmp_path / 'out'),
        in_conpyro_csv_path=_cfis_input(tmp_path, cfo_models),
        fire_modelling_params=_params(module, cfo_model),
    )
    return pd.read_csv(tmp_path / 'out' / 'fire_behavior' / 'conpyro_results.csv')


def test_run_conpyro_runs_the_cfis_model_on_array_inputs(run_conpyro_module, tmp_path):
    result = _run(run_conpyro_module, tmp_path, cfo_model=10)
    assert len(result) == len(_WINDS)
    assert np.isfinite(result['hros']).all()
    assert set(result['fire_type']) <= {1, 2, 3}


def test_run_conpyro_runs_a_mix_of_cfis_and_other_crown_fire_models(run_conpyro_module, tmp_path):
    result = _run(run_conpyro_module, tmp_path, cfo_model='use_csv', cfo_models=[10, 5, 10, 5, 10])
    assert len(result) == len(_WINDS)
    assert np.isfinite(result['hros']).all()
