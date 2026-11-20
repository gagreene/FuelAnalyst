"""Real-engine coverage for CSV-selected forest and open-fuel scenarios."""
import numpy as np
import pandas as pd
import pytest

from real_conpyro_fixtures import ROW, make_params, run_conpyro_module  # noqa: F401


def _open_row(category='grass_herbs', model=31, load=0.2):
    return dict(ROW, unique_id=category, surface_fuel_type=category, stand_type=10, stand_density='L',
                sros_model=model, slope=0., canopy_cover=0., ht_ovrstry_live=0., cbh_ovrstry=0., fsg=0.,
                cbd_ovrstry=0., cfl_ovrstry=0., herbaceous_fuel_load=load, grass_fuel_load=0.05,
                shrub_fuel_load=0.4 if category == 'shrubs' else 0.)


def _run(module, tmp_path, rows, curing=60, sros='use_csv'):
    source = tmp_path / 'inputs.csv'
    pd.DataFrame(rows).to_csv(source, index=False)
    settings = make_params(module, sros_model=sros, terrain_wind=False)
    settings['conpyro']['input_params'].update(grass_curing=curing, model_terrain_effects_on_ffmc=False)
    module.run_conpyro(str(tmp_path / 'out'), str(source), fire_modelling_params=settings)
    return pd.read_csv(tmp_path / 'out/fire_behavior/conpyro_results.csv').set_index('unique_id')


@pytest.mark.parametrize('column', ['temp', 'rh'])
def test_cheney_requires_air_temperature_and_humidity_columns(run_conpyro_module, tmp_path, column):
    row = _open_row(model=32)
    del row[column]

    with pytest.raises(ValueError, match=f'Columns required by ConPyro.*{column}'):
        _run(run_conpyro_module, tmp_path, [row])


@pytest.mark.parametrize('model', [32, 33, 34])
def test_cheney_surface_models_run_on_grass(run_conpyro_module, tmp_path, model):
    result = _run(run_conpyro_module, tmp_path, [_open_row(model=model)]).loc['grass_herbs']

    assert result['sros_model'] == model
    assert result['fire_type'] == 1
    assert np.isfinite(result['sros']) and result['sros'] > 0
    assert np.isfinite(result['hfi']) and result['hfi'] > 0


@pytest.mark.parametrize('curing', [True, None, -1, 101, float('nan'), 'bad'])
def test_grass_curing_rejects_invalid_settings(run_conpyro_module, tmp_path, curing):
    with pytest.raises(ValueError, match='grass_curing'):
        _run(run_conpyro_module, tmp_path, [_open_row()], curing=curing)


@pytest.mark.parametrize('category', ['grass_herbs', 'shrubs'])
@pytest.mark.parametrize('mixed', [False, True])
def test_grass_mc_dmc_is_derived_from_weather(run_conpyro_module, tmp_path, mixed, category):
    rows = [dict(_open_row(category), unique_id=f'g{i}', dmc=dmc) for i, dmc in enumerate([0., 40., 250.])]
    if mixed:
        rows.append(dict(ROW, unique_id='forest', sros_model=13, dmc=40.))
    result = _run(run_conpyro_module, tmp_path, rows)
    # Match the existing forest conversion and its DMC bounds of 10-200.
    expected = 20 + np.exp((244.72 - np.array([10., 40., 200.])) / 43.43)
    assert result.loc[['g0', 'g1', 'g2'], 'mc_dmc'].tolist() == pytest.approx(expected)
    if mixed:
        assert result.loc['forest', 'mc_dmc'] == pytest.approx(expected[1])


def test_legacy_dictionary_without_curing_uses_sixty_percent(run_conpyro_module, tmp_path):
    expected = _run(run_conpyro_module, tmp_path, [_open_row()])
    settings = make_params(run_conpyro_module, sros_model='use_csv', terrain_wind=False)
    settings['conpyro']['input_params'].pop('grass_curing')
    settings['conpyro']['input_params']['model_terrain_effects_on_ffmc'] = False
    run_conpyro_module.run_conpyro(str(tmp_path / 'legacy'), str(tmp_path / 'inputs.csv'), fire_modelling_params=settings)
    result = pd.read_csv(tmp_path / 'legacy/fire_behavior/conpyro_results.csv')
    assert result.sros.iloc[0] == pytest.approx(expected.sros.iloc[0])


@pytest.mark.parametrize('missing_column', ['herbaceous_fuel_load', 'shrub_fuel_load'])
def test_missing_shrub_proxy_load_is_reported_without_zero_fill(run_conpyro_module, tmp_path, missing_column):
    row = dict(_open_row('shrubs'), **{missing_column: np.nan})
    rows = [row, dict(row, wx_date=20240610), _open_row(), dict(ROW, unique_id='forest', sros_model=13)]
    result = _run(run_conpyro_module, tmp_path, rows)

    # An unknown component leaves combined consumption unknown, not 0 or the known component alone.
    assert result.loc['shrubs', 'sfc'].isna().all()
    assert result.loc['grass_herbs', 'sfc'] == pytest.approx(0.2)
    assert result.loc['forest', 'sfc'] > 0
    report = pd.read_csv(tmp_path / 'out/run_conpyro_errors.csv').set_index('unique_id')
    assert report.index.tolist() == ['shrubs']
    message = report.loc['shrubs', 'ConPyro Fire Behavior']
    assert missing_column in message
    assert message.count('[WARNING]') == 1
    original = pd.read_csv(tmp_path / 'inputs.csv')
    assert original.loc[original.unique_id.eq('shrubs'), missing_column].isna().all()


@pytest.mark.parametrize('mixed', [False, True])
@pytest.mark.parametrize('category', ['grass_herbs', 'shrubs'])
def test_open_fuels_use_o1b_curing_and_correct_consumption(run_conpyro_module, tmp_path, mixed, category):
    row = _open_row(category)
    rows = [row]
    if mixed:
        rows.append(dict(ROW, unique_id='forest', surface_fuel_type='forest', sros_model=13))
    result = _run(run_conpyro_module, tmp_path, rows)
    actual = result.loc[category]
    moisture = (250 * 59.5 / 101) * (101 - ROW['ffmc']) / (59.5 + ROW['ffmc'])
    fine_fuel = 91.9 * np.exp(-0.1386 * moisture) * (1 + moisture ** 5.31 / 4.93e7)
    isi = 0.208 * np.exp(0.05039 * ROW['ws']) * fine_fuel
    expected_ros = 250 * (1 - np.exp(-0.035 * isi)) ** 1.7 * (0.176 + 0.02 * (60 - 58.8))
    assert actual.sros == pytest.approx(expected_ros)
    assert actual.sfc == pytest.approx(0.6 if category == 'shrubs' else 0.2)
    assert actual.fire_type == 1
    assert actual.cfc == actual.cfi == 0
    assert np.isfinite(actual[['flame_length_m', 'flame_res_time_sec', 'flame_depth_m']].to_numpy(dtype=float)).all()
    if mixed:
        baseline = _run(run_conpyro_module, tmp_path, [rows[1]], sros=13)
        fields = ['sros', 'hros', 'hfi', 'sfc', 'cfc', 'fire_type']
        assert result.loc['forest', fields].to_numpy(dtype=float) == pytest.approx(baseline.loc['forest', fields].to_numpy(dtype=float))


def test_open_zero_load_remains_nonburning(run_conpyro_module, tmp_path):
    result = _run(run_conpyro_module, tmp_path, [_open_row(load=0.)])
    assert result.loc['grass_herbs', ['sfc', 'hfi', 'fire_type']].eq(0).all()
    assert pd.isna(result.loc['grass_herbs', 'flame_length_m'])


def test_reloaded_grass_results_export_weather_derived_mc_dmc(run_conpyro_module, tmp_path, monkeypatch):
    source = tmp_path / 'previous_results.csv'
    pd.DataFrame({'unique_id': ['grass', 'shrub'], 'wx_date': [20240601, 20240602],
                  'stand_type': [10, 10], 'surface_fuel_type': ['grass_herbs', 'shrubs'],
                  'hfi': 120.0, 'flame_depth_m': 0.5,
                  'dmc': [40., 70.], 'mc_dmc': [np.nan, np.nan]}).to_csv(source, index=False)
    original = source.read_bytes()
    settings = make_params(run_conpyro_module)
    settings['conpyro']['run_model'] = False
    settings['fofem_emissions']['run_model'] = True

    def capture_emissions(df, **kwargs):
        return df.assign(emissions_test=1.)

    monkeypatch.setattr(run_conpyro_module, '_model_fofem_emissions', capture_emissions)
    run_conpyro_module.run_conpyro(str(tmp_path / 'out'), str(source),
                                   in_fofem_consume_csv_path='unused.csv', fire_modelling_params=settings)
    result = pd.read_csv(tmp_path / 'out/conpyro_emissions_results.csv')
    assert result.mc_dmc.tolist() == pytest.approx((20 + np.exp((244.72 - np.array([40., 70.])) / 43.43)).tolist())
    assert source.read_bytes() == original


def test_scalar_override_records_actual_model_and_applies_nondefault_curing(run_conpyro_module, tmp_path):
    row = _open_row(model=30)
    result = _run(run_conpyro_module, tmp_path, [row], curing=90, sros=31)
    assert result.loc['grass_herbs', 'sros_model'] == 31
    baseline = _run(run_conpyro_module, tmp_path, [row], curing=60, sros=31)
    ratio = (0.176 + 0.02 * (90 - 58.8)) / (0.176 + 0.02 * (60 - 58.8))
    assert result.loc['grass_herbs', 'sros'] == pytest.approx(baseline.loc['grass_herbs', 'sros'] * ratio)


def test_surface_models_accept_csv_aliases(run_conpyro_module, tmp_path):
    result = _run(run_conpyro_module, tmp_path, [_open_row(model='O1b'), dict(ROW, unique_id='forest', sros_model='9c')])
    assert result.loc['grass_herbs', 'fire_type'] == 1
    assert result.loc['forest', 'sros'] > 0


@pytest.mark.parametrize('stand_type', [None, 'P'])
def test_unassigned_surface_models_write_empty_results_and_report(run_conpyro_module, tmp_path, stand_type):
    row = dict(ROW, unique_id='unclassified', stand_type=stand_type, sros_model=None)
    result = _run(run_conpyro_module, tmp_path, [row])
    assert result.empty
    report = pd.read_csv(tmp_path / 'out/run_conpyro_errors.csv')
    assert report.unique_id.tolist() == ['unclassified']


@pytest.mark.parametrize('stand_code, model', [(20, 32), (21, 33), (22, 34)])
def test_wheat_stand_codes_survive_mixed_stand_csv_input(run_conpyro_module, tmp_path, stand_code, model):
    forest = dict(ROW, sros_model=13)
    wheat = dict(_open_row(category='wheat', model=model), stand_type=stand_code)
    result = _run(run_conpyro_module, tmp_path, [forest, wheat]).loc['wheat']

    assert result['fire_type'] == 1
    assert np.isfinite(result['sros']) and result['sros'] > 0
