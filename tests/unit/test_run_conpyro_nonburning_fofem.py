"""Non-burning ConPyro scenarios must not be sent to fire-effects models."""
import importlib
import sys
import types

import pandas as pd
import pytest

from real_conpyro_fixtures import ROW, make_params, run_conpyro_module  # noqa: F401


@pytest.mark.parametrize('backend', ['pyfofem', 'fof_gui'])
@pytest.mark.parametrize('has_time', [False, True])
def test_effects_keep_same_date_scenarios_distinct(run_conpyro_module, tmp_path, monkeypatch, backend, has_time):
    module = run_conpyro_module
    source = tmp_path / 'fire.csv'
    fire = pd.DataFrame({
        'unique_id': 'plot', 'wx_date': 20240609,
        'scenario': ['invalid-depth', 'first-valid', 'equal-mortality-inputs'],
        'fire_type': 1, 'hfi': [30.0, 60.0, 60.0], 'flame_depth_m': [0.0, 0.5, 0.25],
        'flame_res_time_sec': 60.0, 'instand_ws_mps': 2.0, 'temp': 20.0,
        'mc_sa': 10.0, 'mc_dmc': 20.0, 'dc': 100.0, 'cfb': 0.1,
        'canopy_cover': 50.0, 'ht_ovrstry_live': 20.0, 'fsg': 1.0, 'ws': 3.0,
    })
    if has_time:
        fire['time'] = [1100, 1200, 1200]
    fire.to_csv(source, index=False)
    original = source.read_bytes()
    trees = tmp_path / 'trees.csv'
    pd.DataFrame([{
        'unique_id': 'plot', 'status': 'L', 'dens_live_ha': 10.0, 'spp': 'FD',
        'dbh': 30.0, 'ht': 20.0, 'crown_depth': 5.0, 'bark_thick': 1.5, 'ba_live_ha': 2.0,
    }]).to_csv(trees, index=False)
    consumption = tmp_path / module.fofem_units.consume_filename('SI')
    pd.DataFrame([{
        **dict.fromkeys(module.fofem_units.FOFEM_LOAD_COLUMNS, 0.1),
        '#PlotId': 'plot', 'DuffDepth': 3.0, 'fuel_bed_depth_m': 0.25,
        'Region': 'InteriorWest', 'CoverGroup': 'GrassGroup', 'FuelCategory': 'Natural',
        'Season': 'Summer', 'remove_hereafter': None,
    }]).to_csv(consumption, index=False)

    if 'pyfofem' not in sys.modules:
        stub = types.ModuleType('pyfofem')
        stub.pyfofem = types.SimpleNamespace()
        monkeypatch.setitem(sys.modules, 'pyfofem', stub)
    fofem = sys.modules['pyfofem'].pyfofem
    monkeypatch.setattr(
        fofem, 'run_fofem_mortality', lambda **kwargs: (kwargs['params']['fire_intensity'] >= 60).astype(float),
        raising=False,
    )
    if backend == 'pyfofem':
        emissions = importlib.import_module('fuel_analyst.components.fofem_emissions')
        monkeypatch.setattr(
            emissions.fofem, 'run_fofem_emissions', lambda **kwargs: {'test_emissions': kwargs['hfi'] / 20},
            raising=False,
        )
    else:
        emissions = importlib.import_module('fuel_analyst.components.fofem_gui_emissions')

        def run_worker(row, out_dir, consume_model, emissions_units, fofem_dir):
            intensity = row['burnup_ign_intensity_kWpm2']
            if pd.isna(intensity):
                return {'fofem_gui_error': 'Invalid flame depth'}
            return {'test_emissions': intensity / 20}

        monkeypatch.setattr(emissions, '_get_fofem_dir', lambda: str(tmp_path))
        monkeypatch.setattr(emissions, '_model_emissions', run_worker)

    settings = make_params(module)
    settings['conpyro']['run_model'] = False
    settings['fofem_mortality']['run_model'] = True
    settings['fofem_emissions'].update(run_model=True, model_select=backend, emissions_units='SI')
    module.run_conpyro(
        str(tmp_path / 'out'), str(source), in_tree_csv_path=str(trees), in_fofem_consume_csv_path=str(consumption),
        fire_modelling_params=settings,
    )

    result = pd.read_csv(tmp_path / 'out/conpyro_mortality_emissions_results.csv').set_index('scenario')
    assert len(result) == 3
    assert result['tree_dead_ba_crnsch_m2pha'].to_dict() == {
        'invalid-depth': 0.0, 'first-valid': 2.0, 'equal-mortality-inputs': 2.0,
    }
    assert pd.isna(result.loc['invalid-depth', 'test_emissions'])
    assert result['test_emissions'].dropna().to_dict() == {'first-valid': 6.0, 'equal-mortality-inputs': 12.0}
    assert '_fofem_scenario_id' not in result
    assert 'fofem_gui_error' not in result
    assert source.read_bytes() == original
    output = tmp_path / 'out'
    assert not list(output.glob('fofem-input-*'))
    for csv in output.rglob('*.csv'):
        assert '_fofem_scenario_id' not in csv.read_text().partition('\n')[0]


@pytest.mark.parametrize('backend', ['pyfofem', 'fof_gui'])
def test_effects_preserve_burning_fire_rows_with_invalid_moisture(run_conpyro_module, tmp_path, monkeypatch, caplog, backend):
    module = run_conpyro_module
    source = tmp_path / 'fire.csv'
    common = {'wx_date': 20240609, 'fire_type': 1, 'hfi': 60., 'flame_depth_m': 0.5,
              'flame_res_time_sec': 60., 'instand_ws_mps': 2., 'temp': 20., 'cfb': 0.1}
    fire = pd.DataFrame([
        dict(common, unique_id='forest', stand_type='P', time=1100, ffmc=92.3, dmc=None, mc_dmc=None, mc_sa=10., dc=100.),
        dict(common, unique_id='forest', stand_type='P', time=1200, ffmc=92.3, dmc=40., mc_dmc=20., mc_sa=10., dc=100.),
        dict(common, unique_id='cheney grass', stand_type=10, time=1100, ffmc=None, dmc=40., mc_dmc=120., mc_sa=None, dc=100.),
        dict(common, unique_id='cheney grass', stand_type=10, time=1200, ffmc=92.3, dmc=40., mc_dmc=120., mc_sa=10., dc=100.),
        dict(common, unique_id='wheat', stand_type='wheat_baled', time=1100, dmc=15., mc_dmc=None, mc_sa=0., dc=-1.),
        dict(common, unique_id='wheat', stand_type='wheat_baled', time=1110, dmc=15., mc_dmc=None, mc_sa=0., dc=-1.),
        dict(common, unique_id='wheat', stand_type='wheat_baled', time=1200, dmc=28.493, mc_dmc=None, mc_sa=10., dc=0.),
    ])
    fire.to_csv(source, index=False)
    consumption = tmp_path / module.fofem_units.consume_filename('SI')
    pd.DataFrame([{
        **dict.fromkeys(module.fofem_units.FOFEM_LOAD_COLUMNS, 0.),
        '#PlotId': plot, 'DuffDepth': 0., 'fuel_bed_depth_m': 0.25,
        'Region': 'InteriorWest', 'CoverGroup': 'GrassGroup', 'FuelCategory': 'Natural',
        'Season': 'Summer', 'remove_hereafter': None,
    } for plot in fire['unique_id'].unique()]).to_csv(consumption, index=False)

    dispatches = []
    if backend == 'pyfofem':
        if 'pyfofem' not in sys.modules:
            stub = types.ModuleType('pyfofem')
            stub.pyfofem = types.SimpleNamespace()
            monkeypatch.setitem(sys.modules, 'pyfofem', stub)
        emissions = importlib.import_module('fuel_analyst.components.fofem_emissions')

        def record_emissions(**kwargs):
            dispatches.extend(kwargs['duff_moist'])
            return {'test_emissions': kwargs['duff_moist']}

        monkeypatch.setattr(emissions.fofem, 'run_fofem_emissions', record_emissions, raising=False)
    else:
        emissions = importlib.import_module('fuel_analyst.components.fofem_gui_emissions')

        def record_emissions(row, out_dir, consume_model, emissions_units, fofem_dir):
            dispatches.append(row['DuffMoisture'])
            return {'test_emissions': row['DuffMoisture']}

        monkeypatch.setattr(emissions, '_get_fofem_dir', lambda: str(tmp_path))
        monkeypatch.setattr(emissions, '_model_emissions', record_emissions)

    settings = make_params(module)
    settings['conpyro']['run_model'] = False
    settings['fofem_emissions'].update(run_model=True, model_select=backend, emissions_units='SI')
    output = tmp_path / 'out'
    module.run_conpyro(str(output), str(source), in_fofem_consume_csv_path=str(consumption), fire_modelling_params=settings)

    result = pd.read_csv(output / 'conpyro_emissions_results.csv').set_index(['unique_id', 'time'])
    assert len(result) == 7
    assert result['hfi'].eq(60.).all()
    assert pd.isna(result.loc[('forest', 1100), 'mc_dmc'])
    assert pd.isna(result.loc[('cheney grass', 1100), 'mc_sa'])
    assert result.loc[('wheat', 1100), 'mc_dmc'] == pytest.approx(218.230653)
    assert result['test_emissions'].dropna().to_dict() == pytest.approx({
        ('forest', 1200): 20., ('cheney grass', 1200): 120., ('wheat', 1200): 165.292276,
    })
    assert sorted(dispatches) == pytest.approx([20., 120., 165.292276])
    warnings = [(r.unique_id, r.issue_code, r.getMessage()) for r in caplog.records if r.levelname == 'WARNING']
    duff = ('FOFEM emissions skipped for affected scenarios. DuffMoisture must be finite and within 10-197.2%, '
            'and its converted Burnup fraction must be within 0.1-1.972. Check mc_dmc or the weather DMC used to derive it.')
    fine = ('FOFEM emissions skipped for affected scenarios. Final 10-hour moisture (mc_sa) must be finite and '
            'within 3-298%. Check the modelled moisture or the supplied fire results.')
    coarse = ('FOFEM emissions skipped for affected scenarios. Weather DC must be finite and nonnegative and must '
              'yield 1000-hour moisture within 1-300%.')
    assert sorted(warnings) == sorted([
        ('forest', 'fofem_duff_moisture_invalid', duff), ('wheat', 'fofem_duff_moisture_invalid', duff),
        ('cheney grass', 'fofem_10h_moisture_invalid', fine), ('wheat', 'fofem_10h_moisture_invalid', fine),
        ('wheat', 'fofem_1000h_moisture_invalid', coarse),
    ])


def test_effects_remove_temporary_input_when_emissions_raises(run_conpyro_module, tmp_path, monkeypatch):
    module = run_conpyro_module
    source = tmp_path / 'fire.csv'
    pd.DataFrame([dict(unique_id='plot', wx_date=20240609, fire_type=1, hfi=30.0, flame_depth_m=0.5)]).to_csv(
        source, index=False,
    )
    settings = make_params(module)
    settings['conpyro']['run_model'] = False
    settings['fofem_emissions']['run_model'] = True
    output = tmp_path / 'out'

    def fail_emissions(**kwargs):
        assert list(output.glob('fofem-input-*/fire_scenarios.csv'))
        raise RuntimeError('Emissions failed.')

    monkeypatch.setattr(module, '_model_fofem_emissions', fail_emissions)
    with pytest.raises(RuntimeError, match='Emissions failed'):
        module.run_conpyro(
            str(output), str(source), in_fofem_consume_csv_path='fofem_consume_si_df.csv',
            fire_modelling_params=settings,
        )
    assert not list(output.glob('fofem-input-*'))


def test_empty_fire_results_match_flame_columns_with_legacy_settings(run_conpyro_module, tmp_path):
    module = run_conpyro_module
    settings = make_params(module)
    settings['conpyro']['output_params']['flame_comp_out_list'] = [
        'instand_ws', 'flame_length_m', 'flame_tilt', 'flame_height', 'flame_res_time', 'flame_depth',
    ]
    inputs = pd.DataFrame([ROW])
    outputs = []
    for name, fire_input in [('filled', inputs), ('empty', inputs.iloc[:0])]:
        source = tmp_path / f'{name}.csv'
        fire_input.to_csv(source, index=False)
        module.run_conpyro(str(tmp_path / name), str(source), fire_modelling_params=settings)
        outputs.append(pd.read_csv(tmp_path / name / 'fire_behavior/conpyro_results.csv'))

    filled, empty = outputs
    assert empty.empty
    assert empty.columns.tolist() == filled.columns.tolist()
    assert empty.columns[-2:].tolist() == ['flame_depth_m', 'burnup_ign_intensity_kWpm2']


@pytest.mark.parametrize('times', [None, [1100, 1200]])
def test_fire_results_record_effective_date_and_time(run_conpyro_module, tmp_path, times):
    module = run_conpyro_module
    source = tmp_path / 'inputs.csv'
    pd.DataFrame([ROW]).to_csv(source, index=False)
    settings = make_params(module)
    settings['conpyro']['input_params'].update(wx_date=[20240609, 20240610], time=times)
    module.run_conpyro(str(tmp_path / 'out'), str(source), fire_modelling_params=settings)

    result = pd.read_csv(tmp_path / 'out/fire_behavior/conpyro_results.csv')
    if times is None:
        assert 'time' not in result
        assert result['wx_date'].tolist() == [20240609, 20240610]
    else:
        assert list(result[['wx_date', 'time']].itertuples(index=False, name=None)) == [
            (20240609, 1100), (20240609, 1200), (20240610, 1100), (20240610, 1200),
        ]


@pytest.mark.parametrize('backend', ['pyfofem', 'fof_gui'])
@pytest.mark.parametrize('mixed, same_date', [(False, False), (True, False), (True, True)])
@pytest.mark.parametrize('reload_results', [False, True])
def test_nonburning_scenarios_skip_fofem_backends(
        run_conpyro_module, tmp_path, monkeypatch, backend, mixed, same_date, reload_results
):
    module = run_conpyro_module
    # Same plot across dates or times: eligibility must be per scenario.
    rows = [dict(ROW, unique_id='plot', stand_type='UNKNOWN', wx_date=20240609, time=1100, scenario='nonfuel')]
    if mixed:
        rows.append(dict(ROW, unique_id='plot', wx_date=20240609 if same_date else 20240610, time=1200, scenario='forest'))
    source = tmp_path / 'input.csv'
    pd.DataFrame(rows).to_csv(source, index=False)
    settings = make_params(module)
    if reload_results:
        module.run_conpyro(str(tmp_path / 'initial'), str(source), fire_modelling_params=settings)
        source = tmp_path / 'initial/fire_behavior/conpyro_results.csv'
        legacy = pd.read_csv(source).drop(columns='burnup_ign_intensity_kWpm2', errors='ignore')
        if not mixed:
            legacy = legacy.drop(columns='flame_depth_m')
        legacy.to_csv(source, index=False)
        settings['conpyro']['run_model'] = False
    source_bytes = source.read_bytes()
    if not mixed:
        monkeypatch.setattr(module, 'TemporaryDirectory', lambda **kwargs: pytest.fail('Temporary input created.'))
    calls = []

    def fake_mortality(**kwargs):
        fire = pd.read_csv(kwargs['plot_wx_fire_csv_path'])
        assert fire.fire_type.gt(0).all()
        assert fire.scenario.tolist() == ['forest']
        calls.append('mortality')
        severity = fire[['unique_id', 'wx_date', module.fofem_units.FOFEM_SCENARIO_ID]].assign(test_mortality=0.25)
        return pd.DataFrame(), severity

    def fake_emissions(**kwargs):
        fire = pd.read_csv(kwargs['plot_wx_fire_csv_path'])
        assert fire.fire_type.gt(0).all()
        assert fire.scenario.tolist() == ['forest']
        calls.append('emissions')
        return fire[['unique_id', 'wx_date', module.fofem_units.FOFEM_SCENARIO_ID]].rename(columns={'unique_id': '#PlotId'}).assign(test_emissions=3.)

    components = importlib.import_module('fuel_analyst.components')
    emissions_module = 'fofem_emissions' if backend == 'pyfofem' else 'fofem_gui_emissions'
    for name, function, implementation in [
        ('fofem_mortality', 'process_mortality', fake_mortality),
        (emissions_module, 'process_emissions', fake_emissions),
    ]:
        stub = types.ModuleType(f'fuel_analyst.components.{name}')
        setattr(stub, function, implementation)
        monkeypatch.setitem(sys.modules, stub.__name__, stub)
        monkeypatch.setattr(components, name, stub, raising=False)
    settings['fofem_mortality']['run_model'] = True
    settings['fofem_emissions'].update(run_model=True, model_select=backend, emissions_units='SI')
    module.run_conpyro(
        str(tmp_path / 'out'), str(source), in_tree_csv_path='unused_tree.csv',
        in_fofem_consume_csv_path=str(tmp_path / 'fofem_consume_si_df.csv'),
        fire_modelling_params=settings,
    )
    assert calls == (['mortality', 'emissions'] if mixed else [])
    assert source.read_bytes() == source_bytes
    result = pd.read_csv(tmp_path / 'out/conpyro_mortality_emissions_results.csv').set_index('scenario')
    assert len(result) == len(rows)
    ignition_column = 'burnup_ign_intensity_kWpm2'
    if reload_results and not mixed:
        assert ignition_column not in result
    else:
        assert result.columns.get_loc(ignition_column) == result.columns.get_loc('flame_depth_m') + 1
        assert pd.isna(result.loc['nonfuel', ignition_column])
    assert result.loc['nonfuel', ['fire_type', 'hfi', 'hros', 'tfc']].eq(0).all()
    assert result.reindex(columns=['test_mortality', 'test_emissions']).loc['nonfuel'].isna().all()
    if mixed:
        assert result.loc['forest', ignition_column] == pytest.approx(
            result.loc['forest', 'hfi'] / result.loc['forest', 'flame_depth_m']
        )
        assert result.loc['forest', 'test_mortality'] == 0.25
        assert result.loc['forest', 'test_emissions'] == 3.
    report = pd.read_csv(tmp_path / 'out/run_conpyro_errors.csv').astype(str)
    assert report.unique_id.eq('plot').any()
    assert report.apply(lambda col: col.str.contains('non-burning', regex=False)).any().any()


def test_reloaded_missing_flame_depth_fails_before_mortality(run_conpyro_module, tmp_path, monkeypatch):
    module = run_conpyro_module
    source = tmp_path / 'fire.csv'
    pd.DataFrame([dict(unique_id='plot', wx_date=20240609, fire_type=1, hfi=30.0)]).to_csv(source, index=False)
    settings = make_params(module)
    settings['conpyro']['run_model'] = False
    settings['fofem_mortality']['run_model'] = True
    settings['fofem_emissions']['run_model'] = True
    monkeypatch.setattr(module, '_model_fofem_mortality', lambda **kwargs: pytest.fail('Mortality ran before preflight.'))

    with pytest.raises(ValueError, match='flame_depth_m'):
        module.run_conpyro(
            str(tmp_path / 'out'), str(source), in_tree_csv_path='unused_tree.csv',
            in_fofem_consume_csv_path='fofem_consume_si_df.csv', fire_modelling_params=settings,
        )
