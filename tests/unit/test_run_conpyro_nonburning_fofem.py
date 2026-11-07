"""Non-burning ConPyro scenarios must not be sent to fire-effects models."""
import importlib
import sys
import types

import pandas as pd
import pytest

from real_conpyro_fixtures import ROW, make_params, run_conpyro_module  # noqa: F401


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
        settings['conpyro']['run_model'] = False
    source_bytes = source.read_bytes()
    calls = []

    def fake_mortality(**kwargs):
        fire = pd.read_csv(kwargs['plot_wx_fire_csv_path'])
        assert fire.fire_type.gt(0).all()
        assert fire.scenario.tolist() == ['forest']
        calls.append('mortality')
        severity = fire[['unique_id', 'wx_date']].assign(test_mortality=0.25)
        return pd.DataFrame(), severity

    def fake_emissions(**kwargs):
        fire = pd.read_csv(kwargs['plot_wx_fire_csv_path'])
        assert fire.fire_type.gt(0).all()
        assert fire.scenario.tolist() == ['forest']
        calls.append('emissions')
        return fire[['unique_id', 'wx_date']].rename(columns={'unique_id': '#PlotId'}).assign(test_emissions=3.)

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
    assert result.loc['nonfuel', ['fire_type', 'hfi', 'hros', 'tfc']].eq(0).all()
    assert result.reindex(columns=['test_mortality', 'test_emissions']).loc['nonfuel'].isna().all()
    if mixed:
        assert result.loc['forest', 'test_mortality'] == 0.25
        assert result.loc['forest', 'test_emissions'] == 3.
    report = pd.read_csv(tmp_path / 'out/run_conpyro_errors.csv').astype(str)
    assert report.unique_id.eq('plot').any()
    assert report.apply(lambda col: col.str.contains('non-burning', regex=False)).any().any()
