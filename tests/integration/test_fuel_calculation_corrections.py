import importlib

import numpy as np
import pandas as pd
import pytest

from fuel_analyst.components import conpyro_attributes, fofem_attributes, fofem_units, trees, woody_debris
from fuel_analyst.components.plants_regen import _process_top_five_spp
from fuel_calculation_fixtures import (
    _depth_frame,
    _make_consumption_input_df,
    _plot_cover,
    _sloped_tally_frames,
    _transect_row,
)

fofem_emissions = importlib.import_module('fuel_analyst.components.fofem_emissions')
fofem_gui_emissions = importlib.import_module('fuel_analyst.components.fofem_gui_emissions')


def _conpyro_source(cover):
    row = {
        'unique_id': 'p1', 'GlobalID': 'plot-1', '_date': '01/01/2025 10:00',
        'treatment_area': 'area', 'treatment_unit': 'unit', 'treatment_type': 'untreated',
        'plot_id': '1', 'SPECIES_PCT_1': 100.0, 'cc': cover,
    }
    for index in range(1, 7):
        row[f'SPECIES_CD_{index}'] = 'FDI' if index == 1 else None
    for field in [
        'x', 'y', 'plot_elevation', 'plot_slope_pct', 'plot_aspect', 'stand_pct_cnfr_live',
        'conpyro_cfl_ovrstry', 'conpyro_cbd_ovrstry', 'conpyro_cfl_midstry',
        'conpyro_cbd_midstry', 'conpyro_dead_branch_fl_midstry', 'conpyro_ht_ovrstry_live',
        'conpyro_ht_midstry_live', 'conpyro_ht_midstry_dead', 'conpyro_cbh_ovrstry',
        'conpyro_cbh_midstry', 'conpyro_fsg', 'ffl_duff_kgpm2', 'ffl_litter_kgpm2',
        'woody_kgpm2_conpyro_lt7cm_7',
    ]:
        row[field] = 1.0
    return pd.DataFrame([row])


@pytest.mark.parametrize('mode', ['single', 'absent', 'invalid', 'excluded'])
def test_canopy_cover_reaches_conpyro_with_existing_missing_defaults(mode):
    rows = {
        'single': [_transect_row(1, ['cnfr'] * 15)],
        'absent': [],
        'invalid': [_transect_row(3, ['cnfr'] * 15)],
        'excluded': [_transect_row(1, ['exclude'] * 15)],
    }[mode]
    cover = _plot_cover(rows).loc[0, 'cc']
    result, _ = conpyro_attributes.gen_conpyro_df(
        _conpyro_source(cover),
        {'canopy_cover_attribute': 'cc', 'vegetative_fuel_loads': {'herbaceous': [], 'grass': [], 'shrub': []}},
    )
    if mode == 'single':
        assert cover == 100
        assert result.loc[0, 'canopy_cover'] == 100
        assert result.loc[0, 'stand_density'] == 'H'
    else:
        assert np.isnan(cover)
        assert result.loc[0, 'canopy_cover'] == 0
        assert result.loc[0, 'stand_density'] is None


@pytest.mark.parametrize(
    ('covers', 'heights', 'expected'),
    [([50, 20, 15, 10, 5], [10, 20, 30, 40, 100], 0.22), ([], [], 0.0), ([20], [0], 0.0)],
)
def test_plant_depth_consumption_csv_reaches_both_emissions_routes(
        tmp_path,
        monkeypatch,
        covers,
        heights,
        expected
):
    plant, _ = _process_top_five_spp(_depth_frame(covers, heights))
    source = _make_consumption_input_df()
    source['fuel_bed_depth_m'] = plant['fuel_bed_depth_m']
    consume = fofem_attributes.gen_fofem_consumption_df(
        source, {
            'region': 'West', 'season': 'Summer', 'moisture_regime': 'Moderate',
            'fofem_processing_units': 'SI', 'soil_heating': {'use_soil_heating': False},
        },
    )
    consume_path = tmp_path / fofem_units.consume_filename('SI')
    consume.to_csv(consume_path, index=False)
    reloaded = pd.read_csv(consume_path)
    assert reloaded.loc[0, 'fuel_bed_depth_m'] == expected

    fire = {
        'unique_id': 'p1', 'wx_date': 20250615, 'hfi': 1500.0, 'flame_res_time_sec': 60.0,
        'instand_ws_mps': 2.0, 'temp': 20.0, 'mc_sa': 10.0, 'mc_dmc': 20.0, 'dc': 100.0, 'cfb': 0.1,
    }
    fire_path = tmp_path / 'fire.csv'
    pd.DataFrame([fire]).to_csv(fire_path, index=False)
    received = {}

    def run_backend(**kwargs):
        received.update(kwargs)
        return {'BurnupError': [0]}

    monkeypatch.setattr(fofem_emissions.fofem, 'run_fofem_emissions', run_backend, raising=False)
    fofem_emissions.process_emissions(
        plot_wx_fire_csv_path=str(fire_path), plot_id_col_name='unique_id',
        fofem_consume_csv_path=str(consume_path), out_dir=str(tmp_path / 'pyfofem'), return_df=True,
    )
    assert received['fuel_bed_depth'].tolist() == [expected]

    runtime = tmp_path / 'runtime'
    runtime.mkdir()
    for name in fofem_gui_emissions._REQUIRED_FOFEM_RUNTIME_FILES:
        (runtime / name).write_text('fixture')

    def unavailable_backend(**kwargs):
        raise RuntimeError('External executable deliberately not run')

    monkeypatch.setattr(fofem_gui_emissions, '_run_runfofem', unavailable_backend)
    writer = fofem_gui_emissions._write_burnup_params_694
    written_depths = []

    def write_burnup(**kwargs):
        written_depths.append(kwargs['depth'])
        return writer(**kwargs)

    monkeypatch.setattr(fofem_gui_emissions, '_write_burnup_params_694', write_burnup)
    merged_row = reloaded.iloc[0].to_dict() | fire
    fofem_gui_emissions._model_emissions(merged_row, str(tmp_path / 'legacy'), 'S', 'SI', str(runtime))
    assert written_depths == [expected]


def test_tree_fsg_uses_field_height_independent_of_plant_depth():
    source = pd.DataFrame({
        'tree_status': ['L', 'L'], 'tree_cbh': [3.0, 3.0], 'tree_dcbh': [4.0, 4.0],
        'tree_fuel_bed_ht': [0.5, 0.5], 'fuel_bed_depth_m': [0.0, 1.0],
    })
    result = trees._calc_tree_fsg(source)
    assert result['tree_fsg'].tolist() == [2.5, 2.5]


@pytest.mark.parametrize('compare', [False, True])
def test_woody_tallied_mass_reaches_final_requested_class(compare):
    plot, pieces, params = _sloped_tally_frames(compare=compare)
    tallied, _ = woody_debris._calc_tallied_woody_biomass(plot, pieces, params)
    params['protocol_transect_params']['size_classes'] = [1, 3, np.inf]
    pieces['woody_sg'] = 0.6
    pieces = woody_debris._calc_woody_corrected_tsct_lengths(plot, pieces, params)
    pieces = woody_debris._calc_woody_weight(woody_debris._calc_woody_volume(pieces))
    final, keep = woody_debris._calc_plot_woody_debris(tallied, pieces, params)
    factor = np.sqrt(2)
    # Counts 4/1, nominal lengths 8/20 m, and class midpoints 0.5/2 cm
    # give adjusted-frequency ratio 1/20 and this independent QMD integral.
    exponent = np.log(1 / 20) / np.log(4)
    qmd_squared = ((exponent + 1) * (1 - 0.1 ** (exponent + 3))) / (
        (exponent + 3) * (1 - 0.1 ** (exponent + 1))
    )
    expected_mass = 0.5 * 4 * (np.pi ** 2 / 8) * qmd_squared / (8 / factor) / 10
    assert final.loc[0, 'woody_kgpm2_test_all_1'] == pytest.approx(expected_mass)
    measured_mass = 0.6 * (np.pi ** 2 / 8) * 4 / (20 / factor) / 10
    assert final.loc[0, 'woody_kgpm2_test_all_3'] == pytest.approx(measured_mass)
    assert 'woody_kgpm2_test_all_1' in keep
