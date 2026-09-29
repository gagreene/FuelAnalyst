"""
Opt-in integration tests exercising FuelAnalyst's public entry points against the real,
bundled FOFEM 6.9.4 batch runtime (src/fuel_analyst/supporting_data/fofem_694). These require
Windows (runfofem.exe is a Windows executable) and are never run automatically, even on
Windows CI - set FUEL_ANALYST_RUN_FOFEM694_TESTS=1 to opt in. See
tests/manual/fofem694_no_install_smoke.ps1 for the equivalent raw-executable-level smoke test
this file's fixtures/expectations were cross-verified against.
"""
import os
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from fuel_analyst.components import fofem_attributes, fofem_gui_emissions, fofem_units

_RUN_ENV_VAR = 'FUEL_ANALYST_RUN_FOFEM694_TESTS'
_should_run = sys.platform == 'win32' and os.environ.get(_RUN_ENV_VAR) == '1'
pytestmark = [
    pytest.mark.windows_fofem694,
    pytest.mark.skipif(
        not _should_run,
        reason=f'opt-in Windows-only test: set {_RUN_ENV_VAR}=1 on Windows to run',
    ),
]

_CONSUME_ROW = {
    '#PlotId': 'p1', 'Litter': 1.0, 'Duff': 2.0, 'DuffDepth': 3.0,
    'Herbaceous': 0.5, 'Shrub': 0.1, 'CrownFoliage': 0.4, 'CrownBranch': 0.5,
    'Region': 'InteriorWest', 'CoverGroup': 'GrassGroup', 'FuelCategory': 'Natural', 'Season': 'Summer',
    'DuffMoisture': 20, 'wfl10HourMoisture': 6, 'wfl1000HourMoisture': 10,
    'wfl1Hour': 0.1, 'wfl10Hour': 0.2, 'wfl100Hour': 0.3,
    'wfl3_6S': 0.1, 'wfl6_9S': 0.1, 'wfl9_20S': 0.1, 'wfl20plusS': 0.1,
    'wfl3_6R': 0.1, 'wfl6_9R': 0.1, 'wfl9_20R': 0.1, 'wfl20plusR': 0.1,
    'SoilFamily': 'Loamy-Skeletal', 'SoilMoisture': 10,
    'LitterLoad_ConsumEq1': -1, 'PctDuff_ConsumEq2': -1, 'DuffDepth_ConsumEq3': -1,
    'MSE_ConsumEq4': -1, 'Herb_ConsumEq5': -1, 'Shrub_ConsumEq6': -1,
    'remove_hereafter': None, 'fuel_bed_depth_m': 0.25,
}
_FIRE_ROW = {
    'unique_id': 'p1', 'wx_date': 20250615, 'hfi': 1500.0, 'flame_res_time_sec': 60.0,
    'instand_ws_mps': 2.0, 'temp': 20.0, 'mc_sa': 10.0, 'mc_dmc': 20.0, 'dc': 100.0, 'cfb': 0.1,
}


def _write_inputs(tmp_path, units='SI'):
    """
    Write a matching consumption/fire CSV pair for process_emissions() end-to-end tests.

    :param tmp_path: pytest tmp_path fixture.
    :param units: 'SI' or 'Imperial'.
    :return: (consume_csv_path, fire_csv_path, out_dir) as strings.
    """
    consume_csv = tmp_path / fofem_units.consume_filename(units)
    pd.DataFrame([_CONSUME_ROW]).to_csv(consume_csv, index=False)
    fire_csv = tmp_path / 'fire.csv'
    pd.DataFrame([_FIRE_ROW]).to_csv(fire_csv, index=False)
    return str(consume_csv), str(fire_csv), str(tmp_path / 'out')


def test_process_emissions_consumption_mode_matches_direct_runfofem_output(tmp_path):
    """process_emissions()'s parsed/SI-converted result must round-trip back to the same
    Imperial values a direct, independently-built runfofem.exe call produces."""
    consume_csv, fire_csv, out_dir = _write_inputs(tmp_path)
    result = fofem_gui_emissions.process_emissions(
        plot_wx_fire_csv_path=fire_csv,
        plot_id_col_name='unique_id',
        fofem_consume_csv_path=consume_csv,
        out_dir=out_dir,
        emissions_units='SI',
        return_df=True,
    )
    assert len(result) == 1
    assert result.loc[0, 'LitPre_kgpm2'] > 0

    # Independently reproduce the same call by hand (not via FuelAnalyst's own writers) and
    # compare a raw Imperial result directly against process_emissions()'s SI-converted one.
    fofem_dir = fofem_gui_emissions._get_fofem_dir()
    manual_dir = tmp_path / 'manual'
    manual_dir.mkdir()
    burnup_path = manual_dir / 'Burnup-In.brn'
    fofem_gui_emissions._write_burnup_params_694(
        str(burnup_path), intensity=1500.0, ig_time=60.0, windspeed=2.0, depth=0.25, ambient_temp=20.0,
    )
    input_path = manual_dir / 'input.txt'
    with open(input_path, 'w', newline='\r\n') as f:
        f.write('#1k-SizeClass\n#ConsumptionEquation\n')
        f.write(
            f'#EFG-STFS {fofem_gui_emissions._EFG_STFS}\n'
            f'#EFG-CWDRSC {fofem_gui_emissions._EFG_CWDRSC}\n'
            f'#EFG-DuffRSC {fofem_gui_emissions._EFG_DUFFRSC}\n'
        )
        f.write(f'#BurnUpFile {os.path.abspath(burnup_path)}\n')
        f.write('#PlotId,Litter\n')
        # Imperial-converted Litter (1.0 kg/m2 * LOAD_CONV_FACTOR), matching _CONSUME_ROW
        f.write(
            'p1,4.46,0.45,0.89,6.0,1.34,0.45,0.45,0.45,0.45,0.45,0.45,0.45,0.45,'
            '10.0,8.92,20.0,1.18,2.23,0.45,1.78,2.23,10.0,InteriorWest,GrassGroup,'
            'Summer,Natural,-1,-1,-1,-1,-1,-1\n'
        )
    output_path = manual_dir / 'output.csv'
    error_path = manual_dir / 'error.txt'
    fofem_gui_emissions._run_runfofem('0', str(input_path), str(output_path), str(error_path), str(manual_dir), fofem_dir)
    manual_df = fofem_gui_emissions._parse_runfofem_output(str(output_path), ['p1'], 'C')

    assert result.loc[0, 'LitPre_kgpm2'] * fofem_units.LOAD_CONV_FACTOR == pytest.approx(
        manual_df.loc[0, 'LitPre'], abs=0.05
    )


def test_process_emissions_soil_mode(tmp_path):
    consume_csv, fire_csv, out_dir = _write_inputs(tmp_path)
    result = fofem_gui_emissions.process_emissions(
        plot_wx_fire_csv_path=fire_csv,
        plot_id_col_name='unique_id',
        fofem_consume_csv_path=consume_csv,
        out_dir=out_dir,
        model_soil_heating=True,
        emissions_units='SI',
        return_df=True,
    )
    assert len(result) == 1
    assert result.loc[0, 'LitPre_kgpm2'] > 0
    assert 'Lay0_degC' in result.columns
    assert 'Lay275d' in result.columns


def test_process_emissions_windspeed_at_boundary_succeeds(tmp_path):
    """Burnup's real, documented windspeed-at-fuelbed-top range is 0-5 m/s (verified directly
    against runfofem.exe, and matches pyfofem's own _FIRE_BOUNDS['u'], itself cited from
    FOFEM's C++ BRN_CheckData()). 5.0 m/s exactly must be accepted, unclipped."""
    fire_row = dict(_FIRE_ROW)
    fire_row['instand_ws_mps'] = 5.0
    consume_csv = tmp_path / fofem_units.consume_filename('SI')
    pd.DataFrame([_CONSUME_ROW]).to_csv(consume_csv, index=False)
    fire_csv = tmp_path / 'fire.csv'
    pd.DataFrame([fire_row]).to_csv(fire_csv, index=False)

    result = fofem_gui_emissions.process_emissions(
        plot_wx_fire_csv_path=str(fire_csv),
        plot_id_col_name='unique_id',
        fofem_consume_csv_path=str(consume_csv),
        out_dir=str(tmp_path / 'out'),
        emissions_units='SI',
        return_df=True,
    )
    assert 'fofem_gui_error' not in result.columns or pd.isna(result.loc[0, 'fofem_gui_error'])
    assert result.loc[0, 'LitPre_kgpm2'] > 0


def test_process_emissions_windspeed_over_range_reports_clear_error_unclipped(tmp_path):
    """A windspeed genuinely outside Burnup's 0-5 m/s range must fail that scenario with a
    clear, plot/scenario-identifying error - not be silently clipped, and not surface as an
    unexplained NaN with no cause given."""
    fire_row = dict(_FIRE_ROW)
    fire_row['instand_ws_mps'] = 8.0  # real value, above the documented 5.0 m/s Burnup limit
    consume_csv = tmp_path / fofem_units.consume_filename('SI')
    pd.DataFrame([_CONSUME_ROW]).to_csv(consume_csv, index=False)
    fire_csv = tmp_path / 'fire.csv'
    pd.DataFrame([fire_row]).to_csv(fire_csv, index=False)

    result = fofem_gui_emissions.process_emissions(
        plot_wx_fire_csv_path=str(fire_csv),
        plot_id_col_name='unique_id',
        fofem_consume_csv_path=str(consume_csv),
        out_dir=str(tmp_path / 'out'),
        emissions_units='SI',
        return_df=True,
    )
    assert len(result) == 1
    assert 'LitPre_kgpm2' not in result.columns  # no fabricated result for the rejected scenario
    assert 'fofem_gui_error' in result.columns
    error = result.loc[0, 'fofem_gui_error']
    assert 'windspeed' in error.lower()
    assert 'p1' in error  # names the affected plot
    assert '20250615' in error  # names the affected wx_date/scenario
    # The original, unmodified input value is preserved in the output alongside the error -
    # process_emissions() never clips or silently rewrites the scientific input.
    assert result.loc[0, 'instand_ws_mps'] == pytest.approx(8.0)


def test_process_emissions_equation_auto_selection_populates_real_values(tmp_path):
    """LitterLoad_ConsumEq1's default -1 ('auto-select') only accepts 997/998/999 as explicit
    overrides (verified directly: any other integer is rejected by runfofem.exe with 'Invalid
    Litter Equation'); the other five equation fields auto-select a real equation id from
    Region/CoverGroup. This exercises that every equation-selection field round-trips a real,
    non-placeholder value end to end, since FuelAnalyst never overrides them today."""
    consume_csv, fire_csv, out_dir = _write_inputs(tmp_path)
    result = fofem_gui_emissions.process_emissions(
        plot_wx_fire_csv_path=fire_csv,
        plot_id_col_name='unique_id',
        fofem_consume_csv_path=consume_csv,
        out_dir=out_dir,
        emissions_units='SI',
        return_df=True,
    )
    assert result.loc[0, 'Lit-Equ'] == 999  # FOFEM's own "no override" sentinel for this field
    for col in ('DufCon-Equ', 'DufRed-Equ', 'MSE-Equ', 'Herb-Equ', 'Shurb-Equ'):
        assert result.loc[0, col] > 0


def test_process_emissions_missing_fofem_data_reports_error_without_crashing(tmp_path, monkeypatch):
    """A worker directory missing Emission_Factors.csv must fail that row without the failure
    propagating as an unhandled exception out of process_emissions() - no FOFEM result columns
    exist at all when every row in the batch fails this way (runfofem.exe's real 74/80/86-column
    schema is discovered from its own output header, not hardcoded, so there is no fixed set of
    columns to backfill with NaN when a row never produces output in the first place)."""
    broken_dir = tmp_path / 'broken_fofem_dir'
    broken_dir.mkdir()
    real_dir = fofem_gui_emissions._get_fofem_dir()
    import shutil
    shutil.copy(os.path.join(real_dir, 'runfofem.exe'), broken_dir / 'runfofem.exe')
    # Emission_Factors.csv deliberately omitted.
    monkeypatch.setenv('FUEL_ANALYST_FOFEM_DIR', str(broken_dir))

    consume_csv, fire_csv, out_dir = _write_inputs(tmp_path)
    result = fofem_gui_emissions.process_emissions(
        plot_wx_fire_csv_path=fire_csv,
        plot_id_col_name='unique_id',
        fofem_consume_csv_path=consume_csv,
        out_dir=out_dir,
        emissions_units='SI',
        return_df=True,
    )
    assert len(result) == 1
    assert result.loc[0, 'Litter'] == pytest.approx(1.0)  # input columns survive
    assert 'LitPre_kgpm2' not in result.columns  # no fabricated FOFEM output for the failed row
    assert 'fofem_gui_error' in result.columns
    assert 'Emission_Factors.csv' in result.loc[0, 'fofem_gui_error']


def test_run_runfofem_invalid_input_raises_with_batch_error_message(tmp_path):
    fofem_dir = fofem_gui_emissions._get_fofem_dir()
    input_path = tmp_path / 'garbage_input.txt'
    input_path.write_text('this is not a valid FOFEM batch input file\n')
    output_path = tmp_path / 'output.csv'
    error_path = tmp_path / 'error.txt'
    with pytest.raises(RuntimeError):
        fofem_gui_emissions._run_runfofem(
            '0', str(input_path), str(output_path), str(error_path), str(tmp_path), fofem_dir,
        )


def test_gen_fofem_gui_app_tree_df_output_accepted_by_runfofem_mortality(tmp_path):
    """The mortality hand-off CSV's header/format must be directly accepted by runfofem.exe
    run type 2, exercising the narrow header-name fix (PlotId/FlHt-ScHt/FS)."""
    plots = pd.DataFrame({'unique_id': ['p1'], 'treatment_type': ['treated'], 'year': [2025]})
    trees = pd.DataFrame({
        'unique_id': ['p1', 'p1'], 'status': ['L', 'L'],
        'spp_fofem': ['PSME', 'PIPO'], 'dens_live_ha': [2.47105, 4.9421],
        'dbh': [30.0, 20.0], 'ht': [20.0, 15.0], 'crown_depth': [8.0, 6.0],
        'decay_cnfr': [1, 1], 'decay_brdlf': [np.nan, np.nan], 'crown_class': ['D', 'C'],
    })
    tree_df = fofem_attributes.gen_fofem_gui_app_tree_df(plots, trees)
    tre_path = tmp_path / 'tree_mortality.tre'
    tree_df.to_csv(tre_path, index=False)

    fofem_dir = fofem_gui_emissions._get_fofem_dir()
    output_path = tmp_path / 'mortality_out.csv'
    error_path = tmp_path / 'mortality_err.txt'
    fofem_gui_emissions._run_runfofem(
        '2', str(tre_path), str(output_path), str(error_path), str(tmp_path), fofem_dir,
        extra_args=['S', '10'],
    )
    lines = output_path.read_text().splitlines()
    assert len(lines) >= 3  # header, units, at least one plot row
    assert lines[-1].startswith('p1-treated-2025,')
