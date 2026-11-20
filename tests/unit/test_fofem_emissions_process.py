import importlib
import sys
import types

import pandas as pd
import pytest

# Register a fake 'pyfofem' package before importing fofem_emissions.py, matching the pattern in
# test_fofem_emissions_helpers.py, so process_emissions() can be exercised without the real
# (optional) pyfofem dependency installed. run_fofem_emissions is monkeypatched per-test below.
fake_package = types.ModuleType('pyfofem')
fake_package.pyfofem = types.SimpleNamespace(run_fofem_emissions=lambda **kwargs: {})
sys.modules['pyfofem'] = fake_package

fofem_emissions = importlib.import_module('fuel_analyst.components.fofem_emissions')
fofem_units = importlib.import_module('fuel_analyst.components.fofem_units')

_CONSUME_ROW = {
    '#PlotId': 'p1',
    'Litter': 1.0, 'Duff': 2.0, 'DuffDepth': 3.0, 'Herbaceous': 0.5, 'Shrub': 0.1,
    'CrownFoliage': 0.4, 'CrownBranch': 0.5,
    'Region': 'InteriorWest', 'CoverGroup': 'GrassGroup', 'FuelCategory': 'Natural',
    'DuffMoisture': 20, 'wfl10HourMoisture': 6, 'wfl1000HourMoisture': 10,
    'wfl1Hour': 0.1, 'wfl10Hour': 0.2, 'wfl100Hour': 0.3,
    'wfl3_6S': 0.1, 'wfl6_9S': 0.1, 'wfl9_20S': 0.1, 'wfl20plusS': 0.1,
    'wfl3_6R': 0.1, 'wfl6_9R': 0.1, 'wfl9_20R': 0.1, 'wfl20plusR': 0.1,
    'fuel_bed_depth_m': 0.25,
}
_FIRE_ROW = {
    'unique_id': 'p1', 'wx_date': 20250615, 'hfi': 1500.0, 'flame_res_time_sec': 60.0,
    'flame_depth_m': 2.5,
    'instand_ws_mps': 2.0, 'temp': 20.0, 'mc_sa': 10.0, 'mc_dmc': 20.0, 'dc': 100.0, 'cfb': 0.1,
}

_FAKE_RESULT = {
    # process_emissions() always passes ndarray inputs to run_fofem_emissions(), so the real
    # function's per-cell (non-scalar) outputs are length-1 arrays, not bare scalars.
    'LitPre': [1.0], 'LitCon': [0.5], 'LitPos': [0.5],
    'DufDepPre': [3.0], 'DufDepCon': [1.0], 'DufDepPos': [2.0],
    'FlaDur': [30.0], 'SmoDur': [300.0],
    'MSE': [15.0],
    'Lay0': [80.0],
    'Lay60d': [1.0],
    'PM25F': [5.0],
    'Lit-Equ': [1],
    'BurnupError': [0],
}


def _write_inputs(tmp_path, units, monkeypatch):
    """
    Write a matching consumption/fire CSV pair for a given unit system and stub pyfofem.

    :param tmp_path: pytest tmp_path fixture.
    :param units: 'SI' or 'Imperial'.
    :param monkeypatch: pytest monkeypatch fixture.
    :return: (consume_csv_path, fire_csv_path, out_dir, recorded_kwargs) where recorded_kwargs
        is a dict that captures the kwargs passed to the stubbed run_fofem_emissions() call.
    """
    consume_csv_path = tmp_path / fofem_units.consume_filename(units)
    pd.DataFrame([_CONSUME_ROW]).to_csv(consume_csv_path, index=False)
    fire_csv_path = tmp_path / 'fire.csv'
    pd.DataFrame([_FIRE_ROW]).to_csv(fire_csv_path, index=False)
    out_dir = tmp_path / 'out'

    recorded_kwargs = {}

    def _fake_run_fofem_emissions(**kwargs):
        recorded_kwargs.update(kwargs)
        return dict(_FAKE_RESULT)

    # raising=False: fofem_emissions.fofem is a shared fake pyfofem.pyfofem namespace whose
    # exact identity/attribute set depends on which test module in the session imported
    # fuel_analyst.components.fofem_emissions first (module caching means only the first import
    # actually executes/binds it) - it may not already define run_fofem_emissions.
    monkeypatch.setattr(
        fofem_emissions.fofem, 'run_fofem_emissions', _fake_run_fofem_emissions, raising=False
    )

    return str(consume_csv_path), str(fire_csv_path), str(out_dir), recorded_kwargs


@pytest.mark.parametrize('dmc', [40., None])
def test_grass_emissions_uses_weather_moisture_and_reports_missing_dmc(tmp_path, monkeypatch, caplog, dmc):
    consume_csv, fire_csv, out_dir, recorded = _write_inputs(tmp_path, 'SI', monkeypatch)
    consume = pd.read_csv(consume_csv)
    consume['#PlotId'] = 'plot with space'
    consume['DuffMoisture'] = 80.
    consume.to_csv(consume_csv, index=False)
    fire = pd.read_csv(fire_csv)
    fire['unique_id'] = 'plot with space'
    fire['surface_fuel_type'] = 'grass_herbs'
    fire['stand_type'] = 10
    fire['mc_dmc'] = None
    fire['dmc'] = dmc
    fire.to_csv(fire_csv, index=False)
    result = fofem_emissions.process_emissions(fire_csv, 'unique_id', consume_csv, out_dir, return_df=True)
    if dmc is None:
        assert result.empty
        assert not recorded
        assert {r.unique_id for r in caplog.records if r.issue_code.startswith('fofem_grass')} == {'plot with space'}
    else:
        import math
        assert recorded['duff_moist'].tolist() == pytest.approx([20 + math.exp((244.72 - 40) / 43.43)])
        assert not [r for r in caplog.records if getattr(r, 'issue_code', '').startswith('fofem_grass')]


def test_process_emissions_passes_areal_intensity_and_skips_invalid_depth(tmp_path, monkeypatch, caplog):
    consume_csv, fire_csv, out_dir, recorded = _write_inputs(tmp_path, 'SI', monkeypatch)
    pd.DataFrame([
        dict(_FIRE_ROW, hfi=30.0, flame_depth_m=0.5, _fofem_scenario_id=9),
        dict(_FIRE_ROW, wx_date=20250616, flame_depth_m=0.0, _fofem_scenario_id=10),
        dict(_FIRE_ROW, wx_date=20250617, hfi=-30.0, _fofem_scenario_id=11),
    ]).to_csv(fire_csv, index=False)

    result = fofem_emissions.process_emissions(fire_csv, 'unique_id', consume_csv, out_dir, return_df=True)

    assert recorded['hfi'].tolist() == [60.0]
    assert result['hfi'].tolist() == [30.0]
    assert result['burnup_ign_intensity_kWpm2'].tolist() == [60.0]
    assert result['_fofem_scenario_id'].tolist() == [9]
    assert '_fofem_scenario_id' not in pd.read_csv(f'{out_dir}/fofem_emissions_results.csv')
    [warning] = [record for record in caplog.records if 'flame depth' in record.message]
    assert warning.unique_id == 'p1'
    assert warning.levelname == 'WARNING'
    assert warning.issue_code == 'fofem_burnup_ignition_invalid'


def test_process_emissions_si_writes_suffixed_columns_and_passes_si_units(tmp_path, monkeypatch):
    consume_csv, fire_csv, out_dir, recorded_kwargs = _write_inputs(tmp_path, 'SI', monkeypatch)

    result = fofem_emissions.process_emissions(
        plot_wx_fire_csv_path=fire_csv,
        plot_id_col_name='unique_id',
        fofem_consume_csv_path=consume_csv,
        out_dir=out_dir,
        emissions_units='SI',
        return_df=True,
    )

    assert recorded_kwargs['units'] == 'SI'
    assert 'LitPre_kgpm2' in result.columns
    assert 'DufDepPre_cm' in result.columns
    assert 'FlaDur_sec' in result.columns
    assert 'MSE_pct' in result.columns
    assert 'Lay0_degC' in result.columns
    assert 'PM25F_gpm2' in result.columns
    # Unsuffixed status/index/equation fields are untouched
    assert 'Lay60d' in result.columns
    assert 'Lit-Equ' in result.columns
    assert 'BurnupError' in result.columns
    # No stale unsuffixed physical result columns remain
    assert 'LitPre' not in result.columns
    assert 'PM25F' not in result.columns

    final_csv = pd.read_csv(f'{out_dir}/fofem_emissions_results.csv')
    assert 'LitPre_kgpm2' in final_csv.columns


def test_process_emissions_imperial_writes_suffixed_columns_and_passes_imperial_units(tmp_path, monkeypatch):
    consume_csv, fire_csv, out_dir, recorded_kwargs = _write_inputs(tmp_path, 'Imperial', monkeypatch)

    result = fofem_emissions.process_emissions(
        plot_wx_fire_csv_path=fire_csv,
        plot_id_col_name='unique_id',
        fofem_consume_csv_path=consume_csv,
        out_dir=out_dir,
        emissions_units='Imperial',
        return_df=True,
    )

    assert recorded_kwargs['units'] == 'Imperial'
    assert 'LitPre_tpac' in result.columns
    assert 'DufDepPre_in' in result.columns
    assert 'PM25F_lbpac' in result.columns


def test_process_emissions_defaults_to_si(tmp_path, monkeypatch):
    consume_csv, fire_csv, out_dir, recorded_kwargs = _write_inputs(tmp_path, 'SI', monkeypatch)

    fofem_emissions.process_emissions(
        plot_wx_fire_csv_path=fire_csv,
        plot_id_col_name='unique_id',
        fofem_consume_csv_path=consume_csv,
        out_dir=out_dir,
    )

    assert recorded_kwargs['units'] == 'SI'


def test_process_emissions_rejects_invalid_units(tmp_path, monkeypatch):
    consume_csv, fire_csv, out_dir, _ = _write_inputs(tmp_path, 'SI', monkeypatch)
    with pytest.raises(ValueError, match='Invalid FOFEM processing units'):
        fofem_emissions.process_emissions(
            plot_wx_fire_csv_path=fire_csv,
            plot_id_col_name='unique_id',
            fofem_consume_csv_path=consume_csv,
            out_dir=out_dir,
            emissions_units='metric',
        )


def test_process_emissions_rejects_units_filename_mismatch(tmp_path, monkeypatch):
    consume_csv, fire_csv, out_dir, _ = _write_inputs(tmp_path, 'SI', monkeypatch)
    with pytest.raises(ValueError, match='SI.*Imperial|Imperial.*SI'):
        fofem_emissions.process_emissions(
            plot_wx_fire_csv_path=fire_csv,
            plot_id_col_name='unique_id',
            fofem_consume_csv_path=consume_csv,
            out_dir=out_dir,
            emissions_units='Imperial',
        )
