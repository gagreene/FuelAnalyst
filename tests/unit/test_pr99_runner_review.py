"""Review contracts for nonfuel overrides and the pinned BY consumption adapter."""

import numpy as np
import pandas as pd
import pytest

from real_conpyro_fixtures import ROW, make_params, run_conpyro_module  # noqa: F401


def test_by_consumption_adapter_uses_measured_loads_and_preserves_missing_inputs(run_conpyro_module):
    # A vendor refresh that requires a different SFC setup or selects CFIS must
    # fail here. Literal values use de Groot FFC plus wood, bounded to 0.1..6.
    # Vendor input caps FFL at 5 and WFL at 2, so the large-load row is
    # 0.156 * 5 + 0.015 * 100 - 0.176 + 2 = 4.104 kg/m2.
    rows = pd.DataFrame([
        dict(ROW, duff_fuel_load=1., litter_fuel_load=1., woody_fuel_load=0.2, bui=20.),
        dict(ROW, duff_fuel_load=1., litter_fuel_load=1., woody_fuel_load=0.2, bui=40.),
        dict(ROW, duff_fuel_load=0., litter_fuel_load=0., woody_fuel_load=0., bui=0.),
        dict(ROW, duff_fuel_load=0.1, litter_fuel_load=0.1, woody_fuel_load=0.3, bui=200.),
        dict(ROW, duff_fuel_load=10., litter_fuel_load=10., woody_fuel_load=10., bui=100.),
        dict(ROW, duff_fuel_load=1., litter_fuel_load=1., woody_fuel_load=0.2, bui=np.nan),
    ])
    result = run_conpyro_module._calc_by_surface_consumption(rows)
    assert result.shape == (6,)
    assert np.ma.getmaskarray(result).tolist() == [False, False, False, False, False, True]
    assert result[:5].tolist() == pytest.approx([0.636, 0.936, 0.1, 0.5, 4.104])


@pytest.mark.parametrize('stand_type', [0, '0.0'])
@pytest.mark.parametrize('mixed', [False, True])
@pytest.mark.parametrize('sros_model', [13, 31, 'r20', 'use_csv'])
def test_nonfuel_stays_nonburning_with_scalar_and_csv_surface_models(
        run_conpyro_module,
        tmp_path,
        sros_model,
        mixed,
        stand_type
):
    # Retain the real plot's positive loads and canopy: stand code 0 must
    # override them, even when the selected scalar model can otherwise burn.
    rows = [dict(ROW, unique_id='nonfuel', stand_type=stand_type, stand_density=None,
                 sros_model='noSROS', surface_fuel_type='nonfuel_error')]
    if mixed:
        rows.append(dict(ROW, unique_id='forest', sros_model=13, surface_fuel_type='forest'))
    source = tmp_path / 'input.csv'
    pd.DataFrame(rows).to_csv(source, index=False)
    settings = make_params(run_conpyro_module, sros_model=sros_model, terrain_wind=False)
    run_conpyro_module.run_conpyro(
        str(tmp_path / 'out'), str(source), fire_modelling_params=settings)
    result = pd.read_csv(tmp_path / 'out/fire_behavior/conpyro_results.csv').set_index('unique_id')
    assert set(result.index) == {row['unique_id'] for row in rows}
    assert result.loc['nonfuel', ['sros', 'hros', 'sfc', 'cfc', 'tfc', 'hfi', 'fire_type']].eq(0).all()
    assert pd.isna(result.loc['nonfuel', 'flame_length_m'])
    if mixed:
        assert result.loc['forest', 'hfi'] > 0
