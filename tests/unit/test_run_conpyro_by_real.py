"""BY surface consumption and explicit nonfuel routing through real ConPyro."""
import numpy as np
import pandas as pd
import pytest

from real_conpyro_fixtures import ROW, make_params, run_conpyro_module  # noqa: F401


def test_bui_below_five_is_bounded_not_missing(run_conpyro_module):
    rows = pd.DataFrame([dict(ROW, bui=0.), dict(ROW, bui=5.)])
    consumption = run_conpyro_module._calc_by_surface_consumption(rows)
    assert not np.ma.getmaskarray(consumption).any()
    assert consumption[0] == pytest.approx(consumption[1])


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


def test_explicit_scalar_override_applies_to_by_surface(run_conpyro_module):
    params = make_params(run_conpyro_module, sros_model=13)['conpyro']['input_params']
    rows = pd.DataFrame([dict(ROW, stand_type=10, sros_model=1, surface_fuel_type='forest_floor')])
    result = run_conpyro_module._single_run_fire_behavior(
        (ROW['wx_date'], 1200, rows, params, ['sros', 'sfc', 'hfi', 'mc_dmc']))
    assert result.loc[0, 'sros_model'] == 13
    assert result.loc[0, 'sfc'] > 0


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


@pytest.mark.parametrize('value', [np.nan, np.inf, 'invalid'])
@pytest.mark.parametrize('missing', ['duff_fuel_load', 'litter_fuel_load', 'woody_fuel_load', 'bui'])
def test_missing_by_consumption_is_reported_per_plot(run_conpyro_module, tmp_path, missing, value):
    rows = [dict(ROW, unique_id='missing', stand_type=10, sros_model=1, surface_fuel_type='forest_floor'),
            dict(ROW, unique_id='good', stand_type=10, sros_model=1, surface_fuel_type='forest_floor')]
    rows[0][missing] = value
    source = tmp_path / 'input.csv'
    pd.DataFrame(rows).to_csv(source, index=False)
    settings = make_params(run_conpyro_module)
    settings['conpyro']['input_params']['sros_model'] = 'use_csv'
    run_conpyro_module.run_conpyro(str(tmp_path / 'out'), str(source), fire_modelling_params=settings)
    result = pd.read_csv(tmp_path / 'out/fire_behavior/conpyro_results.csv').set_index('unique_id')
    errors = pd.read_csv(tmp_path / 'out/run_conpyro_errors.csv').set_index('unique_id')
    message = ' '.join(errors.loc['missing'].astype(str))
    assert '[WARNING]' in message and 'BY surface consumption' in message and missing in message
    assert pd.isna(result.loc['missing', 'sfc'])
    assert result.loc['good', 'sfc'] > 0


def test_missing_model_still_skips_fuel_bearing_stand(run_conpyro_module, tmp_path):
    source = tmp_path / 'input.csv'
    pd.DataFrame([dict(ROW, unique_id='bad', stand_type='P', sros_model=np.nan),
                  dict(ROW, unique_id='good', stand_type='P', sros_model=13)]).to_csv(source, index=False)
    settings = make_params(run_conpyro_module)
    settings['conpyro']['input_params']['sros_model'] = 'use_csv'
    run_conpyro_module.run_conpyro(str(tmp_path / 'out'), str(source), fire_modelling_params=settings)
    result = pd.read_csv(tmp_path / 'out/fire_behavior/conpyro_results.csv')
    assert result.unique_id.tolist() == ['good']


def test_mixed_by_duplicate_index_preserves_row_alignment(run_conpyro_module):
    rows = pd.DataFrame([
        dict(ROW, unique_id='forest', sros_model=13, surface_fuel_type='forest'),
        dict(ROW, unique_id='by', stand_type=10, sros_model=1, surface_fuel_type='forest_floor'),
        dict(ROW, unique_id='grass', stand_type=10, sros_model=31, surface_fuel_type='grass_herbs'),
    ], index=[7, 7, 3])
    params = make_params(run_conpyro_module)['conpyro']['input_params']
    params['sros_model'] = 'use_csv'
    before = rows.copy(deep=True)
    result = run_conpyro_module._single_run_fire_behavior(
        (ROW['wx_date'], 1200, rows, params, ['sros', 'sfc', 'hfi', 'mc_dmc']))
    assert result.unique_id.tolist() == ['forest', 'by', 'grass']
    assert result['sros'].gt(0).all()
    pd.testing.assert_frame_equal(rows, before)


def test_mixed_by_split_preserves_batch_cfis_fuel_type_policy(run_conpyro_module):
    params = make_params(run_conpyro_module, cfo_model=10)['conpyro']['input_params']
    params['sros_model'] = 'use_csv'
    rows = pd.DataFrame([
        dict(ROW, unique_id='forest', sros_model=13, surface_fuel_type='forest', fbp_fuel_type='C5'),
        dict(ROW, unique_id='by', stand_type=10, sros_model=1, surface_fuel_type='forest_floor'),
    ])
    outputs = ['sros', 'sfc', 'hfi', 'mc_dmc']
    mixed = run_conpyro_module._single_run_fire_behavior((ROW['wx_date'], 1200, rows, params, outputs))
    # The original batch contains a missing FBP type, so forest CFIS must still run without one.
    forest = rows.iloc[[0]].copy()
    forest['fbp_fuel_type'] = None
    expected = run_conpyro_module._single_run_fire_behavior((ROW['wx_date'], 1200, forest, params, outputs))
    assert mixed.loc[0, 'sfc'] == pytest.approx(expected.loc[0, 'sfc'])
    assert mixed.loc[0, 'hfi'] == pytest.approx(expected.loc[0, 'hfi'])


@pytest.mark.parametrize('category', [None, 'nonfuel_error'])
@pytest.mark.parametrize('mixed', [False, True])
@pytest.mark.parametrize('missing_density', [False, True])
def test_nonfuel_without_sros_survives_csv_filter_and_returns_zero(
        run_conpyro_module,
        tmp_path,
        mixed,
        missing_density,
        category
):
    rows = [dict(ROW, unique_id='nonfuel', stand_type=0, sros_model=np.nan, surface_fuel_type=category)]
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
