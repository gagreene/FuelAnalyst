import importlib
import sys
import types

import pandas as pd
import pytest

# Register a fake 'pyfofem' package before importing fofem_gui_emissions.py. Both the top-level
# package names (imported directly via 'from pyfofem import ..., DEFAULT_CONSUMPTION_VARS') and
# the 'pyfofem.pyfofem' submodule's own DEFAULT_CONSUMPTION_VARS attribute (accessed as
# 'fofem.DEFAULT_CONSUMPTION_VARS' at fofem_gui_emissions.py's module scope) must be present, or
# import itself fails - this module has zero pre-existing test coverage.
_CONSUMPTION_VARS = ['LitPre', 'DufDepPre', 'PM25F']
fake_package = types.ModuleType('pyfofem')
fake_package.pyfofem = types.SimpleNamespace(DEFAULT_CONSUMPTION_VARS=_CONSUMPTION_VARS)
fake_package.DEFAULT_CONSUMPTION_VARS = _CONSUMPTION_VARS
fake_package.TOTAL_DURATION_CONSUMED_VARS = []
fake_package.EQUATION_VARS = []
fake_package.SOIL_HEAT_VARS = []
sys.modules['pyfofem'] = fake_package

fofem_gui_emissions = importlib.import_module('fuel_analyst.components.fofem_gui_emissions')
fofem_units = importlib.import_module('fuel_analyst.components.fofem_units')


def test_module_imports_cleanly_without_a_source_checkout():
    """Regression test for the pre-existing 'pkg_dir' NameError at import time."""
    assert not hasattr(fofem_gui_emissions, 'pkg_dir')
    assert not hasattr(fofem_gui_emissions, 'FOFEM_DIR')
    assert callable(fofem_gui_emissions._get_fofem_dir)


def test_get_fofem_dir_uses_env_var_override(tmp_path, monkeypatch):
    monkeypatch.setenv('FUEL_ANALYST_FOFEM_DIR', str(tmp_path))
    assert fofem_gui_emissions._get_fofem_dir() == str(tmp_path)


def test_get_fofem_dir_rejects_nonexistent_env_var_override(tmp_path, monkeypatch):
    monkeypatch.setenv('FUEL_ANALYST_FOFEM_DIR', str(tmp_path / 'does_not_exist'))
    with pytest.raises(FileNotFoundError, match='FUEL_ANALYST_FOFEM_DIR'):
        fofem_gui_emissions._get_fofem_dir()


def test_get_fofem_dir_raises_clear_error_without_checkout_or_override(monkeypatch):
    monkeypatch.delenv('FUEL_ANALYST_FOFEM_DIR', raising=False)
    monkeypatch.setattr(
        fofem_gui_emissions.helper, 'get_repo_root',
        lambda start_dir: (_ for _ in ()).throw(FileNotFoundError('no repo root')),
    )
    with pytest.raises(FileNotFoundError, match='FUEL_ANALYST_FOFEM_DIR'):
        fofem_gui_emissions._get_fofem_dir()


def _make_row_consume_df(units):
    """
    Build a single-row consumption DataFrame with all 17 load columns + DuffDepth populated.

    :param units: 'SI' or 'Imperial' - determines the source values used.
    :return: DataFrame with one row.
    """
    value = 1.0 if units == 'SI' else 1.0 * fofem_units.LOAD_CONV_FACTOR
    depth_value = 3.0 if units == 'SI' else 3.0 * fofem_units.DEPTH_CONV_FACTOR
    data = {col: [value] for col in fofem_units.FOFEM_LOAD_COLUMNS}
    data['DuffDepth'] = [depth_value]
    data['#PlotId'] = ['p1']
    return pd.DataFrame(data)


def test_convert_consume_row_to_imperial_converts_si_source_values():
    row_consume_df = _make_row_consume_df('SI')
    result = fofem_gui_emissions._convert_consume_row_to_imperial(row_consume_df, 'SI')
    assert result.loc[0, 'Litter'] == pytest.approx(round(1.0 * fofem_units.LOAD_CONV_FACTOR, 2))
    assert result.loc[0, 'DuffDepth'] == pytest.approx(round(3.0 * fofem_units.DEPTH_CONV_FACTOR, 2))
    assert result.columns.tolist() == row_consume_df.columns.tolist()


def test_convert_consume_row_to_imperial_passes_through_imperial_source_values():
    row_consume_df = _make_row_consume_df('Imperial')
    result = fofem_gui_emissions._convert_consume_row_to_imperial(row_consume_df, 'Imperial')
    assert result.loc[0, 'Litter'] == pytest.approx(round(1.0 * fofem_units.LOAD_CONV_FACTOR, 2))
    assert result.loc[0, 'DuffDepth'] == pytest.approx(round(3.0 * fofem_units.DEPTH_CONV_FACTOR, 2))
    assert result.columns.tolist() == row_consume_df.columns.tolist()


def test_convert_consume_row_to_imperial_does_not_add_or_remove_columns():
    row_consume_df = _make_row_consume_df('SI')
    result = fofem_gui_emissions._convert_consume_row_to_imperial(row_consume_df, 'SI')
    assert set(result.columns) == set(row_consume_df.columns)
    assert len(result.columns) == len(row_consume_df.columns)


_CONSUME_ROW = {
    '#PlotId': 'p1', 'Litter': 1.0, 'Duff': 2.0, 'DuffDepth': 3.0,
    'Region': 'InteriorWest', 'CoverGroup': 'GrassGroup', 'FuelCategory': 'Natural',
    'remove_hereafter': None, 'fuel_bed_depth_m': 0.25,
}
_FIRE_ROW = {
    'unique_id': 'p1', 'wx_date': 20250615, 'hfi': 1500.0, 'flame_res_time_sec': 60.0,
    'instand_ws_mps': 2.0, 'temp': 20.0, 'mc_sa': 10.0, 'mc_dmc': 20.0, 'dc': 100.0, 'cfb': 0.1,
}


def _write_process_emissions_inputs(tmp_path, units):
    """
    Write a matching consumption/fire CSV pair for process_emissions() end-to-end tests.

    :param tmp_path: pytest tmp_path fixture.
    :param units: 'SI' or 'Imperial'.
    :return: (consume_csv_path, fire_csv_path, out_dir) as strings.
    """
    consume_csv_path = tmp_path / fofem_units.consume_filename(units)
    pd.DataFrame([_CONSUME_ROW]).to_csv(consume_csv_path, index=False)
    fire_csv_path = tmp_path / 'fire.csv'
    pd.DataFrame([_FIRE_ROW]).to_csv(fire_csv_path, index=False)
    return str(consume_csv_path), str(fire_csv_path), str(tmp_path / 'out')


def test_process_emissions_rejects_invalid_units(tmp_path):
    consume_csv, fire_csv, out_dir = _write_process_emissions_inputs(tmp_path, 'SI')
    with pytest.raises(ValueError, match='Invalid FOFEM processing units'):
        fofem_gui_emissions.process_emissions(
            plot_wx_fire_csv_path=fire_csv,
            plot_id_col_name='unique_id',
            fofem_consume_csv_path=consume_csv,
            out_dir=out_dir,
            emissions_units='metric',
        )


def test_process_emissions_rejects_units_filename_mismatch(tmp_path):
    consume_csv, fire_csv, out_dir = _write_process_emissions_inputs(tmp_path, 'SI')
    with pytest.raises(ValueError, match='SI.*Imperial|Imperial.*SI'):
        fofem_gui_emissions.process_emissions(
            plot_wx_fire_csv_path=fire_csv,
            plot_id_col_name='unique_id',
            fofem_consume_csv_path=consume_csv,
            out_dir=out_dir,
            emissions_units='Imperial',
        )


def _fake_model_emissions_factory(recorded_units):
    """
    Build a _model_emissions() stub that records emissions_units and returns canned Imperial
    fof_gui-style results (LitPre in T/ac, DufDepPre in inches, PM25F in lb/ac), skipping any
    real Burnup/subprocess execution.

    :param recorded_units: List to append each call's emissions_units argument to.
    :return: Callable matching _model_emissions()'s signature.
    """
    def _fake(row, out_dir, consume_model, emissions_units):
        recorded_units.append(emissions_units)
        return [4.46089561, 1.1811, 10.0], out_dir
    return _fake


def test_process_emissions_threads_units_and_converts_si_final_result(tmp_path, monkeypatch):
    consume_csv, fire_csv, out_dir = _write_process_emissions_inputs(tmp_path, 'SI')
    recorded_units = []
    monkeypatch.setattr(
        fofem_gui_emissions, '_model_emissions', _fake_model_emissions_factory(recorded_units)
    )
    monkeypatch.setattr(fofem_gui_emissions.shutil, 'rmtree', lambda path: None)

    result = fofem_gui_emissions.process_emissions(
        plot_wx_fire_csv_path=fire_csv,
        plot_id_col_name='unique_id',
        fofem_consume_csv_path=consume_csv,
        out_dir=out_dir,
        emissions_units='SI',
        return_df=True,
    )

    assert recorded_units == ['SI']
    # fof_gui always returns Imperial (4.46089561 T/ac, 1.1811 in, 10.0 lb/ac); converted back
    # to the SI equivalents of the canned values above.
    assert result.loc[0, 'LitPre_kgpm2'] == pytest.approx(1.0, abs=1e-6)
    assert result.loc[0, 'DufDepPre_cm'] == pytest.approx(3.0, abs=1e-3)
    assert result.loc[0, 'PM25F_gpm2'] == pytest.approx(5.0, abs=1e-6)


def test_process_emissions_threads_units_and_passes_through_imperial_final_result(tmp_path, monkeypatch):
    consume_csv, fire_csv, out_dir = _write_process_emissions_inputs(tmp_path, 'Imperial')
    recorded_units = []
    monkeypatch.setattr(
        fofem_gui_emissions, '_model_emissions', _fake_model_emissions_factory(recorded_units)
    )
    monkeypatch.setattr(fofem_gui_emissions.shutil, 'rmtree', lambda path: None)

    result = fofem_gui_emissions.process_emissions(
        plot_wx_fire_csv_path=fire_csv,
        plot_id_col_name='unique_id',
        fofem_consume_csv_path=consume_csv,
        out_dir=out_dir,
        emissions_units='Imperial',
        return_df=True,
    )

    assert recorded_units == ['Imperial']
    assert result.loc[0, 'LitPre_tpac'] == pytest.approx(4.46089561, abs=1e-6)
    assert result.loc[0, 'DufDepPre_in'] == pytest.approx(1.1811, abs=1e-6)
    assert result.loc[0, 'PM25F_lbpac'] == pytest.approx(10.0, abs=1e-6)


def test_process_emissions_defaults_to_si(tmp_path, monkeypatch):
    consume_csv, fire_csv, out_dir = _write_process_emissions_inputs(tmp_path, 'SI')
    recorded_units = []
    monkeypatch.setattr(
        fofem_gui_emissions, '_model_emissions', _fake_model_emissions_factory(recorded_units)
    )
    monkeypatch.setattr(fofem_gui_emissions.shutil, 'rmtree', lambda path: None)

    fofem_gui_emissions.process_emissions(
        plot_wx_fire_csv_path=fire_csv,
        plot_id_col_name='unique_id',
        fofem_consume_csv_path=consume_csv,
        out_dir=out_dir,
    )

    assert recorded_units == ['SI']


def test_process_emissions_threads_units_via_process_map_path(tmp_path, monkeypatch):
    """num_workers >= 4 takes the process_map()/ProcessPoolExecutor dispatch path."""
    consume_csv, fire_csv, out_dir = _write_process_emissions_inputs(tmp_path, 'SI')
    recorded_units = []

    def _fake_process_map(fn, records, out_dirs, consume_models, emissions_units_list, **kwargs):
        return [fn(r, d, m, u) for r, d, m, u in zip(records, out_dirs, consume_models, emissions_units_list)]

    monkeypatch.setattr(
        fofem_gui_emissions, '_model_emissions', _fake_model_emissions_factory(recorded_units)
    )
    monkeypatch.setattr(fofem_gui_emissions, 'process_map', _fake_process_map)
    monkeypatch.setattr(fofem_gui_emissions, '_TQDM_PROCESS_MAP_AVAILABLE', True)
    monkeypatch.setattr(fofem_gui_emissions.shutil, 'rmtree', lambda path: None)

    fofem_gui_emissions.process_emissions(
        plot_wx_fire_csv_path=fire_csv,
        plot_id_col_name='unique_id',
        fofem_consume_csv_path=consume_csv,
        out_dir=out_dir,
        emissions_units='SI',
        num_workers=4,
    )

    assert recorded_units == ['SI']
