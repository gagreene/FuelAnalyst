"""Integration checks for upstream policies that affect FuelAnalyst's exported fire metrics."""
import numpy as np
import pandas as pd
import pytest

from real_conpyro_fixtures import ROW, WINDS, make_params, run_conpyro_module  # noqa: F401


def _run_scenario(module, tmp_path, row, cros_model=1):
    frame = pd.DataFrame([dict(row, ws=wind, wx_date=20240609+i) for i, wind in enumerate(WINDS)])
    source = tmp_path / 'input.csv'
    frame.to_csv(source, index=False)
    settings = make_params(module)
    settings['conpyro']['input_params']['cros_model'] = cros_model
    module.run_conpyro(str(tmp_path / 'out'), str(source), fire_modelling_params=settings)
    return pd.read_csv(tmp_path / 'out/fire_behavior/conpyro_results.csv')


@pytest.mark.parametrize('mixed', [False, True])
def test_nonfuel_rows_preserve_zero_fire_metrics_and_skip_flame_models(run_conpyro_module, tmp_path, mixed):
    rows = [dict(ROW, unique_id='nonfuel', stand_type='UNKNOWN')]
    if mixed:
        rows.append(dict(ROW, unique_id='forest'))
    frame = pd.DataFrame(rows)
    source = tmp_path / 'input.csv'
    frame.to_csv(source, index=False)
    settings = make_params(run_conpyro_module)
    settings['conpyro']['output_params']['out_request'] += ['nonfuel_mask', 'inferred_nonfuel_mask']
    run_conpyro_module.run_conpyro(str(tmp_path / 'out'), str(source), fire_modelling_params=settings)
    result = pd.read_csv(tmp_path / 'out/fire_behavior/conpyro_results.csv').set_index('unique_id')
    physical = ['sros', 'hros', 'sfc', 'cfc', 'tfc', 'hfi', 'fire_type']
    assert result.loc['nonfuel', physical].eq(0).all()
    assert result.loc['nonfuel', ['nonfuel_mask', 'inferred_nonfuel_mask']].eq(True).all()
    assert result.loc['nonfuel', ['flame_length_m', 'flame_res_time_sec', 'flame_depth_m']].isna().all()
    if mixed:
        assert result.loc['forest', 'hfi'] > 0
        assert result.loc['forest', 'flame_length_m'] > 0
        assert not result.loc['forest', 'nonfuel_mask']


@pytest.mark.parametrize('cros_model', [1, 2])
def test_zero_cbd_exports_surface_only_metrics(run_conpyro_module, tmp_path, cros_model):
    row = dict(ROW, cbd_ovrstry=0.)
    result = _run_scenario(run_conpyro_module, tmp_path, row, cros_model)
    assert len(result) == len(WINDS)
    assert result.unique_id.eq(ROW['unique_id']).all()
    assert result[['cfo_prob', 'cfb', 'cfc', 'cfi']].eq(0).all(axis=None)
    assert np.isfinite(result[['sros', 'hros', 'sfc', 'tfc', 'hfi']]).all().all()
    assert result.hros.tolist() == pytest.approx(result.sros.tolist())
    assert result.tfc.tolist() == pytest.approx(result.sfc.tolist())
    assert result.hfi.tolist() == pytest.approx(result.sfi.tolist())
    assert result.fire_type.eq(1).all()
