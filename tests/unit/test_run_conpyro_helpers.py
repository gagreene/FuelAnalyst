import importlib
import logging
import sys
import types

import numpy as np
import pandas as pd
import pytest


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


def test_run_conpyro_writes_error_report_with_fofem_mortality_warning(tmp_path, monkeypatch):
    conpyro_csv_path = tmp_path / 'conpyro_results.csv'
    pd.DataFrame({'unique_id': ['A'], 'wx_date': [20250101]}).to_csv(conpyro_csv_path, index=False)

    def fake_model_fofem_mortality(df, fire_csv_path, in_tree_csv_path, out_dir,
                                    fofem_mortality_params, conpyro_params):
        from fuel_analyst.components import error_handling
        error_handling.get_logger('trees').warning(
            'Plot dropped from FOFEM mortality processing; missing required column(s): ws.',
            extra={'unique_id': 'A', 'issue_code': 'fofem_mortality_missing_required_column'},
        )
        return df

    monkeypatch.setattr(module, '_model_fofem_mortality', fake_model_fofem_mortality)

    params = {
        'num_workers': 1,
        'conpyro': {
            'run_model': False, 'plot_id_col_name': 'unique_id',
            'input_params': {}, 'output_params': {'out_request': [], 'flame_comp_out_list': []},
        },
        'fofem_mortality': {
            'run_model': True, 'plot_id_col_name': 'unique_id', 'fofem_tree_id_col_name': 'unique_id',
        },
        'fofem_emissions': {'run_model': False},
    }

    module.run_conpyro(
        out_dir=str(tmp_path),
        in_conpyro_csv_path=str(conpyro_csv_path),
        in_tree_csv_path='unused_tree.csv',
        fire_modelling_params=params,
    )

    error_report_path = tmp_path / 'run_conpyro_errors.csv'
    assert error_report_path.is_file()
    report = pd.read_csv(error_report_path, keep_default_na=False)
    assert (report['unique_id'] == 'A').any()


def test_run_conpyro_writes_error_report_with_multiple_weather_dates(tmp_path, monkeypatch):
    """Regression: run_conpyro() passes its own multi-date DataFrame (one row per plot
    per wx_date) to write_report(), which used to raise
    'DataFrame index must be unique for orient=index' and write no report at all."""
    conpyro_csv_path = tmp_path / 'conpyro_results.csv'
    pd.DataFrame({
        'unique_id': ['A', 'A'],
        'wx_date': [20250101, 20250102],
    }).to_csv(conpyro_csv_path, index=False)

    def fake_model_fofem_mortality(df, fire_csv_path, in_tree_csv_path, out_dir,
                                    fofem_mortality_params, conpyro_params):
        from fuel_analyst.components import error_handling
        error_handling.get_logger('trees').warning(
            'Plot dropped from FOFEM mortality processing; missing required column(s): ws.',
            extra={'unique_id': 'A', 'issue_code': 'fofem_mortality_missing_required_column'},
        )
        return df

    monkeypatch.setattr(module, '_model_fofem_mortality', fake_model_fofem_mortality)

    params = {
        'num_workers': 1,
        'conpyro': {
            'run_model': False, 'plot_id_col_name': 'unique_id',
            'input_params': {}, 'output_params': {'out_request': [], 'flame_comp_out_list': []},
        },
        'fofem_mortality': {
            'run_model': True, 'plot_id_col_name': 'unique_id', 'fofem_tree_id_col_name': 'unique_id',
        },
        'fofem_emissions': {'run_model': False},
    }

    module.run_conpyro(
        out_dir=str(tmp_path),
        in_conpyro_csv_path=str(conpyro_csv_path),
        in_tree_csv_path='unused_tree.csv',
        fire_modelling_params=params,
    )

    error_report_path = tmp_path / 'run_conpyro_errors.csv'
    assert error_report_path.is_file()
    report = pd.read_csv(error_report_path, keep_default_na=False)
    assert (report['unique_id'] == 'A').sum() == 1


def test_model_fofem_emissions_rejects_units_filename_mismatch_before_any_backend_import(tmp_path):
    """_model_fofem_emissions() must validate emissions_units against the consumption CSV's
    unit-bearing filename before importing/running either backend - confirmed here by using a
    consumption CSV path that doesn't even exist, since the ValueError must fire first."""
    from fuel_analyst.components import fofem_units

    df = pd.DataFrame({'unique_id': ['A'], 'wx_date': [20250101]})
    with pytest.raises(ValueError, match='SI.*Imperial|Imperial.*SI'):
        module._model_fofem_emissions(
            df=df,
            fire_csv_path=str(tmp_path / 'unused_fire.csv'),
            fofem_emissions_params={
                'run_model': True, 'plot_id_col_name': 'unique_id', 'emissions_units': 'Imperial',
            },
            in_fofem_consume_csv_path=str(tmp_path / fofem_units.consume_filename('SI')),
            out_dir=str(tmp_path),
            conpyro_params={'plot_id_col_name': 'unique_id'},
            num_workers=1,
        )


def _cfis_frame(fuel_types, wx_dates=None, cfo_models=None):
    """ConPyro input rows for plots P0, P1, ... with the given fuel types (None for a missing one)."""
    count = len(fuel_types)
    return pd.DataFrame({
        'unique_id': [f'P{i}' for i in range(count)],
        'fbp_fuel_type': fuel_types,
        'wx_date': wx_dates if wx_dates is not None else [20250101] * count,
        'time': [1200] * count,
        'cfo_model': cfo_models if cfo_models is not None else [10] * count,
    })


def test_cfis_fuel_type_warning_names_each_plot_without_a_fuel_type(caplog):
    df = _cfis_frame(['C2', None, 'M1'])
    with caplog.at_level(logging.WARNING, logger='fuel_analyst.run_conpyro'):
        module._log_cfis_fuel_type_issues(df, {'cfo_model': 10, 'wx_date': 20250101, 'time': 1200})
    logged = {r.unique_id: r for r in caplog.records}
    assert logged['P1'].issue_code == 'cfis_missing_fuel_type'
    assert 'No FBP fuel type for this plot' in logged['P1'].getMessage()
    # The plots that have one still run without it, because ConPyro takes fuel types only when every plot has one
    assert logged['P0'].issue_code == logged['P2'].issue_code == 'cfis_fuel_type_not_used'
    assert len(caplog.records) == 3


def test_cfis_fuel_type_warning_is_silent_when_every_plot_has_a_fuel_type(caplog):
    with caplog.at_level(logging.WARNING, logger='fuel_analyst.run_conpyro'):
        module._log_cfis_fuel_type_issues(_cfis_frame(['C2', 'M1']), {'cfo_model': 10, 'wx_date': 1, 'time': 1})
    assert not caplog.records


def test_cfis_fuel_type_warning_is_silent_for_other_crown_fire_models(caplog):
    with caplog.at_level(logging.WARNING, logger='fuel_analyst.run_conpyro'):
        module._log_cfis_fuel_type_issues(_cfis_frame([None, None]), {'cfo_model': 5, 'wx_date': 1, 'time': 1})
    assert not caplog.records


def test_cfis_fuel_type_warning_follows_the_cfo_model_column_and_weather_dates(caplog):
    # Two dates: the plot without a fuel type is only on the first one, so the second date still uses fuel types.
    # P3 on the first date does not use CFIS, so it is not reported.
    df = _cfis_frame(['C2', None, 'M1', 'C2'], wx_dates=[1, 1, 2, 1], cfo_models=[10, 10, 10, 5])
    with caplog.at_level(logging.WARNING, logger='fuel_analyst.run_conpyro'):
        module._log_cfis_fuel_type_issues(df, {'cfo_model': 'use_csv', 'wx_date': 'use_csv', 'time': 1200})
    assert {r.unique_id: r.issue_code for r in caplog.records} == {
        'P0': 'cfis_fuel_type_not_used', 'P1': 'cfis_missing_fuel_type',
    }


def test_cfis_fuel_type_warning_logs_a_plot_once_across_dates(caplog):
    df = _cfis_frame([None, None], wx_dates=[1, 2])
    df['unique_id'] = 'P0'
    with caplog.at_level(logging.WARNING, logger='fuel_analyst.run_conpyro'):
        module._log_cfis_fuel_type_issues(df, {'cfo_model': 10, 'wx_date': 'use_csv', 'time': 1200})
    assert len(caplog.records) == 1


def test_run_conpyro_reports_a_missing_cfis_fuel_type_in_the_error_csv(tmp_path, monkeypatch):
    conpyro_csv_path = tmp_path / 'conpyro_df.csv'
    pd.DataFrame({
        'unique_id': ['A', 'B'], 'stand_density': ['L', 'L'], 'stand_type': ['P', 'P'],
        'ws': [10.0, 10.0], 'wd': [180.0, 180.0], 'ffmc': [90.0, 90.0], 'dmc': [40.0, 40.0], 'bui': [60.0, 60.0],
        'temp': [20.0, 20.0], 'rh': [30.0, 30.0], 'fbp_fuel_type': ['C2', None],
    }).to_csv(conpyro_csv_path, index=False)
    monkeypatch.setattr(module, '_model_fire_behavior', lambda df, **kwargs: df)
    monkeypatch.setattr(module, '_model_flame_components', lambda df, *args, **kwargs: df)
    params = {
        'num_workers': 1,
        'conpyro': {
            'run_model': True, 'plot_id_col_name': 'unique_id',
            'input_params': {'cfo_model': 10},
            'output_params': {'out_request': [], 'flame_comp_out_list': []},
        },
        'fofem_mortality': {'run_model': False},
        'fofem_emissions': {'run_model': False},
    }

    module.run_conpyro(out_dir=str(tmp_path), in_conpyro_csv_path=str(conpyro_csv_path), fire_modelling_params=params)

    report = pd.read_csv(tmp_path / 'run_conpyro_errors.csv', keep_default_na=False).set_index('unique_id')
    assert 'No FBP fuel type for this plot' in report.loc['B', 'ConPyro Fire Behavior']
    assert 'every plot with the same weather date' in report.loc['A', 'ConPyro Fire Behavior']
