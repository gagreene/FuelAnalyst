"""BY surface consumption and explicit nonfuel routing through real ConPyro."""
import numpy as np
import pandas as pd
import pytest

from real_conpyro_fixtures import ROW, make_params, run_conpyro_module  # noqa: F401


@pytest.mark.parametrize('bui', [10., 100.])
def test_by_consumption_changes_with_bui_without_changing_other_stands(run_conpyro_module, tmp_path, bui):
    by = dict(ROW, unique_id='by', stand_type=10, sros_model=1, surface_fuel_type='forest_floor',
              canopy_cover=0., cfl_ovrstry=0., cbd_ovrstry=0., cfl_midstry=0., cbd_midstry=0.,
              ht_ovrstry_live=0., ht_midstry_live=0., ht_midstry_dead=0., cbh_ovrstry=0., cbh_midstry=0.,
              fsg=0., dead_branch_fl_midstry=0., herbaceous_fuel_load=0., grass_fuel_load=0.,
              shrub_fuel_load=0., bui=bui)
    rows = [dict(ROW, unique_id='forest', sros_model=13, surface_fuel_type='forest'), by,
            dict(ROW, unique_id='grass', stand_type=10, sros_model=31, surface_fuel_type='grass_herbs')]
    settings = make_params(run_conpyro_module)
    settings['conpyro']['input_params']['sros_model'] = 'use_csv'
    source = tmp_path / 'mixed.csv'
    pd.DataFrame(rows).to_csv(source, index=False)
    run_conpyro_module.run_conpyro(str(tmp_path / 'mixed'), str(source), fire_modelling_params=settings)
    mixed = pd.read_csv(tmp_path / 'mixed/fire_behavior/conpyro_results.csv').set_index('unique_id')
    floor = ROW['duff_fuel_load'] + ROW['litter_fuel_load']
    expected = np.clip(min(floor, 0.156 * floor + 0.015 * bui - 0.176) + ROW['woody_fuel_load'], 0.1, 6.)
    assert mixed.loc['by', 'sfc'] == pytest.approx(expected)
    assert mixed.loc['by', 'hfi'] > 0
    for row in rows[::2]:
        pd.DataFrame([row]).to_csv(source, index=False)
        run_conpyro_module.run_conpyro(str(tmp_path / row['unique_id']), str(source), fire_modelling_params=settings)
        alone = pd.read_csv(tmp_path / row['unique_id'] / 'fire_behavior/conpyro_results.csv').iloc[0]
        for column in ['sros', 'hros', 'sfc', 'hfi', 'mc_sa', 'mc_dmc']:
            assert mixed.loc[row['unique_id'], column] == pytest.approx(alone[column], nan_ok=True)


def test_forest_floor_only_runs_without_canopy_or_vegetation(run_conpyro_module, tmp_path):
    row = dict(ROW, stand_type=10, sros_model=1, surface_fuel_type='forest_floor',
               canopy_cover=0., cfl_ovrstry=0., cbd_ovrstry=0., cfl_midstry=0., cbd_midstry=0.,
               ht_ovrstry_live=0., ht_midstry_live=0., ht_midstry_dead=0., cbh_ovrstry=0., cbh_midstry=0.,
               fsg=0., dead_branch_fl_midstry=0., herbaceous_fuel_load=0., grass_fuel_load=0., shrub_fuel_load=0.)
    source = tmp_path / 'input.csv'
    pd.DataFrame([row]).to_csv(source, index=False)
    settings = make_params(run_conpyro_module)
    settings['conpyro']['input_params']['sros_model'] = 'use_csv'
    run_conpyro_module.run_conpyro(str(tmp_path / 'out'), str(source), fire_modelling_params=settings)
    result = pd.read_csv(tmp_path / 'out/fire_behavior/conpyro_results.csv').iloc[0]
    # Default consumption: bounded de Groot forest floor consumption plus measured wood.
    forest_floor = ROW['duff_fuel_load'] + ROW['litter_fuel_load']
    expected = np.clip(min(forest_floor, 0.156 * forest_floor + 0.015 * ROW['bui'] - 0.176)
                       + ROW['woody_fuel_load'], 0.1, 6.)
    assert result.sfc == pytest.approx(expected)
    assert result.hfi == pytest.approx(300. * expected * result.hros)
    assert np.isfinite(result.mc_dmc)
    assert result.sros > 0 and result.hfi > 0
    assert result[['cfo_prob', 'cfb', 'cfc', 'cfi']].eq(0).all()
    assert result.hros == pytest.approx(result.sros)
    assert result.hfi == pytest.approx(result.sfi)
    assert result.fire_type == 1


def test_missing_model_still_skips_fuel_bearing_stand(run_conpyro_module, tmp_path):
    source = tmp_path / 'input.csv'
    pd.DataFrame([dict(ROW, unique_id='bad', stand_type='P', sros_model=np.nan),
                  dict(ROW, unique_id='good', stand_type='P', sros_model=13)]).to_csv(source, index=False)
    settings = make_params(run_conpyro_module)
    settings['conpyro']['input_params']['sros_model'] = 'use_csv'
    run_conpyro_module.run_conpyro(str(tmp_path / 'out'), str(source), fire_modelling_params=settings)
    result = pd.read_csv(tmp_path / 'out/fire_behavior/conpyro_results.csv')
    assert result.unique_id.tolist() == ['good']


@pytest.mark.parametrize('mixed', [False, True])
@pytest.mark.parametrize('missing_density', [False, True])
def test_nonfuel_without_sros_survives_csv_filter_and_returns_zero(
        run_conpyro_module,
        tmp_path,
        mixed,
        missing_density
):
    rows = [dict(ROW, unique_id='nonfuel', stand_type=0, sros_model=np.nan, surface_fuel_type='nonfuel_error')]
    if missing_density:
        rows[0]['stand_density'] = None
    if mixed:
        rows.append(dict(ROW, unique_id='forest', stand_type='DF', sros_model=13, surface_fuel_type='forest'))
    source = tmp_path / 'input.csv'
    pd.DataFrame(rows).to_csv(source, index=False)
    settings = make_params(run_conpyro_module)
    settings['conpyro']['input_params']['sros_model'] = 'use_csv'
    run_conpyro_module.run_conpyro(str(tmp_path / 'out'), str(source), fire_modelling_params=settings)
    result = pd.read_csv(tmp_path / 'out/fire_behavior/conpyro_results.csv').set_index('unique_id')
    assert 'nonfuel' in result.index
    assert result.loc['nonfuel', ['sros', 'hros', 'sfc', 'cfc', 'tfc', 'hfi', 'fire_type']].eq(0).all()
    assert pd.isna(result.loc['nonfuel', 'flame_length_m'])
    if mixed:
        assert result.loc['forest', 'hfi'] > 0
