import importlib
import logging
import os

import pandas as pd
import pytest

fofem_gui_emissions = importlib.import_module('fuel_analyst.components.fofem_gui_emissions')
fofem_units = importlib.import_module('fuel_analyst.components.fofem_units')

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
_BUNDLE_FIXTURE_DIR = os.path.join(_REPO_ROOT, 'tests', 'test_data', 'fofem694')


def test_get_fofem_dir_uses_env_var_override(tmp_path, monkeypatch):
    for name in fofem_gui_emissions._REQUIRED_FOFEM_RUNTIME_FILES:
        (tmp_path / name).write_text('x')
    monkeypatch.setenv('FUEL_ANALYST_FOFEM_DIR', str(tmp_path))
    assert fofem_gui_emissions._get_fofem_dir() == str(tmp_path)


def test_get_fofem_dir_rejects_nonexistent_env_var_override(tmp_path, monkeypatch):
    monkeypatch.setenv('FUEL_ANALYST_FOFEM_DIR', str(tmp_path / 'does_not_exist'))
    with pytest.raises(FileNotFoundError, match='FUEL_ANALYST_FOFEM_DIR'):
        fofem_gui_emissions._get_fofem_dir()


def test_get_fofem_dir_rejects_env_var_override_missing_runfofem_exe(tmp_path, monkeypatch):
    """A directory that exists but lacks runfofem.exe itself (e.g. only the CSVs present)
    must fail clearly, not be silently accepted."""
    monkeypatch.setenv('FUEL_ANALYST_FOFEM_DIR', str(tmp_path))
    with pytest.raises(FileNotFoundError, match='runfofem.exe'):
        fofem_gui_emissions._get_fofem_dir()


def test_get_fofem_dir_rejects_env_var_override_missing_species_csv(tmp_path, monkeypatch):
    for name in ('runfofem.exe', 'Emission_Factors.csv'):
        (tmp_path / name).write_text('x')
    monkeypatch.setenv('FUEL_ANALYST_FOFEM_DIR', str(tmp_path))

    with pytest.raises(FileNotFoundError, match='fof_spp.csv'):
        fofem_gui_emissions._get_fofem_dir()


def test_get_fofem_dir_resolves_bundled_directory_without_override(monkeypatch):
    """Without FUEL_ANALYST_FOFEM_DIR, _get_fofem_dir() must resolve the bundled fofem_694 dir."""
    monkeypatch.delenv('FUEL_ANALYST_FOFEM_DIR', raising=False)
    result = fofem_gui_emissions._get_fofem_dir()
    assert os.path.basename(os.path.normpath(result)) == 'fofem_694'
    assert os.path.isfile(os.path.join(result, fofem_gui_emissions._RUNFOFEM_EXE))


def test_get_fofem_dir_raises_clear_error_when_bundle_missing_runfofem_exe(monkeypatch):
    """A wheel-only install (bundle directory exists because its *.csv files are included,
    but runfofem.exe/its DLLs are not) must fail clearly and immediately, not resolve to an
    incomplete directory that only fails later, per-row."""
    monkeypatch.delenv('FUEL_ANALYST_FOFEM_DIR', raising=False)
    monkeypatch.setattr(os.path, 'isfile', lambda path: False)
    with pytest.raises(FileNotFoundError, match='runfofem.exe'):
        fofem_gui_emissions._get_fofem_dir()


def _install_fake_runtime_package(monkeypatch, runtime_dir):
    """
    Register a fake importable fuel_analyst_fofem694_runtime module for
    _get_fofem_dir()'s installed-runtime-package resolution tier, without needing the real
    package installed.

    :param monkeypatch: pytest monkeypatch fixture.
    :param runtime_dir: Directory the fake module's get_runtime_dir() should return.
    :return: None.
    """
    import sys
    import types
    fake_module = types.ModuleType('fuel_analyst_fofem694_runtime')
    fake_module.get_runtime_dir = lambda: str(runtime_dir)
    monkeypatch.setitem(sys.modules, 'fuel_analyst_fofem694_runtime', fake_module)


def test_get_fofem_dir_resolves_installed_runtime_package_without_override(tmp_path, monkeypatch):
    """Without FUEL_ANALYST_FOFEM_DIR, an installed fuel-analyst-fofem694-runtime package
    takes priority over the source-checkout bundle."""
    monkeypatch.delenv('FUEL_ANALYST_FOFEM_DIR', raising=False)
    for name in fofem_gui_emissions._REQUIRED_FOFEM_RUNTIME_FILES:
        (tmp_path / name).write_text('x')
    _install_fake_runtime_package(monkeypatch, tmp_path)

    assert fofem_gui_emissions._get_fofem_dir() == str(tmp_path)


def test_get_fofem_dir_env_var_override_takes_priority_over_runtime_package(tmp_path, monkeypatch):
    override_dir = tmp_path / 'override'
    override_dir.mkdir()
    for name in fofem_gui_emissions._REQUIRED_FOFEM_RUNTIME_FILES:
        (override_dir / name).write_text('x')
    monkeypatch.setenv('FUEL_ANALYST_FOFEM_DIR', str(override_dir))

    runtime_dir = tmp_path / 'runtime_pkg'
    runtime_dir.mkdir()
    for name in fofem_gui_emissions._REQUIRED_FOFEM_RUNTIME_FILES:
        (runtime_dir / name).write_text('x')
    _install_fake_runtime_package(monkeypatch, runtime_dir)

    assert fofem_gui_emissions._get_fofem_dir() == str(override_dir)


def test_get_fofem_dir_falls_back_to_bundle_when_runtime_package_incomplete(tmp_path, monkeypatch):
    """An installed runtime missing its species CSV falls back to the complete source bundle."""
    monkeypatch.delenv('FUEL_ANALYST_FOFEM_DIR', raising=False)
    import sys
    import types
    fake_module = types.ModuleType('fuel_analyst_fofem694_runtime')
    for name in ('runfofem.exe', 'Emission_Factors.csv'):
        (tmp_path / name).write_text('x')
    fake_module.get_runtime_dir = lambda: str(tmp_path)
    monkeypatch.setitem(sys.modules, 'fuel_analyst_fofem694_runtime', fake_module)

    result = fofem_gui_emissions._get_fofem_dir()
    assert os.path.basename(os.path.normpath(result)) == 'fofem_694'


def test_ensure_worker_fofem_runtime_copies_required_files(tmp_path):
    """No Microsoft Visual C++ DLLs are copied - the redistributable is a documented,
    separately-installed Windows prerequisite, not an app-local file FuelAnalyst manages."""
    fofem_dir = tmp_path / 'shared_bundle'
    fofem_dir.mkdir()
    for name in fofem_gui_emissions._REQUIRED_FOFEM_RUNTIME_FILES:
        (fofem_dir / name).write_text(f'content of {name}')
    worker_dir = tmp_path / 'worker'
    worker_dir.mkdir()

    result = fofem_gui_emissions._ensure_worker_fofem_runtime(str(worker_dir), str(fofem_dir))

    assert result == str(worker_dir)
    for name in fofem_gui_emissions._REQUIRED_FOFEM_RUNTIME_FILES:
        assert (worker_dir / name).read_text() == f'content of {name}'
    # Never written into the shared bundle itself
    assert set(os.listdir(fofem_dir)) == set(fofem_gui_emissions._REQUIRED_FOFEM_RUNTIME_FILES)


def test_ensure_worker_fofem_runtime_raises_when_required_file_missing(tmp_path):
    fofem_dir = tmp_path / 'shared_bundle'
    fofem_dir.mkdir()
    (fofem_dir / fofem_gui_emissions._RUNFOFEM_EXE).write_text('x')
    # Emission_Factors.csv/fof_spp.csv deliberately missing.
    worker_dir = tmp_path / 'worker'
    worker_dir.mkdir()

    with pytest.raises(FileNotFoundError, match='Emission_Factors.csv'):
        fofem_gui_emissions._ensure_worker_fofem_runtime(str(worker_dir), str(fofem_dir))


def test_ensure_worker_fofem_runtime_does_not_recopy_existing_files(tmp_path):
    """A worker reusing its own directory across several rows only pays the copy cost once -
    an already-present file in worker_dir is left alone, not overwritten from fofem_dir."""
    fofem_dir = tmp_path / 'shared_bundle'
    fofem_dir.mkdir()
    for name in fofem_gui_emissions._REQUIRED_FOFEM_RUNTIME_FILES:
        (fofem_dir / name).write_text('fresh from bundle')
    worker_dir = tmp_path / 'worker'
    worker_dir.mkdir()
    (worker_dir / fofem_gui_emissions._RUNFOFEM_EXE).write_text('already copied earlier')

    fofem_gui_emissions._ensure_worker_fofem_runtime(str(worker_dir), str(fofem_dir))

    assert (worker_dir / fofem_gui_emissions._RUNFOFEM_EXE).read_text() == 'already copied earlier'


def _make_row_consume_df(units):
    """
    Build a single-row consumption DataFrame with all 17 load columns + DuffDepth populated.

    :param units: 'SI' or 'Imperial' - determines the source values used.
    :return: DataFrame with one row.
    """
    value = 1.0 if units == 'SI' else 1.0 * fofem_units.LOAD_CONV_FACTOR
    depth_value = 3.0 if units == 'SI' else 3.0 * fofem_units.DEPTH_CONV_FACTOR
    data = {col: [value] for col in fofem_units.FOFEM_LOAD_COLUMNS}
    data['DuffDepth'] = [depth_value]
    data['#PlotId'] = ['p1']
    return pd.DataFrame(data)


def test_convert_consume_row_to_imperial_converts_si_source_values():
    row_consume_df = _make_row_consume_df('SI')
    result = fofem_gui_emissions._convert_consume_row_to_imperial(row_consume_df, 'SI')
    assert result.loc[0, 'Litter'] == pytest.approx(round(1.0 * fofem_units.LOAD_CONV_FACTOR, 2))
    assert result.loc[0, 'DuffDepth'] == pytest.approx(round(3.0 * fofem_units.DEPTH_CONV_FACTOR, 2))
    assert result.columns.tolist() == row_consume_df.columns.tolist()


def test_convert_consume_row_to_imperial_passes_through_imperial_source_values():
    row_consume_df = _make_row_consume_df('Imperial')
    result = fofem_gui_emissions._convert_consume_row_to_imperial(row_consume_df, 'Imperial')
    assert result.loc[0, 'Litter'] == pytest.approx(round(1.0 * fofem_units.LOAD_CONV_FACTOR, 2))
    assert result.loc[0, 'DuffDepth'] == pytest.approx(round(3.0 * fofem_units.DEPTH_CONV_FACTOR, 2))
    assert result.columns.tolist() == row_consume_df.columns.tolist()


def test_convert_consume_row_to_imperial_does_not_add_or_remove_columns():
    row_consume_df = _make_row_consume_df('SI')
    result = fofem_gui_emissions._convert_consume_row_to_imperial(row_consume_df, 'SI')
    assert set(result.columns) == set(row_consume_df.columns)
    assert len(result.columns) == len(row_consume_df.columns)


def test_write_burnup_params_694_matches_verified_fixture_byte_for_byte(tmp_path):
    """The verified tests/test_data/fofem694/burnup_parameters_694.brn fixture used these exact
    five dynamic values; regenerating must reproduce its content with Windows CRLF."""
    out_path = tmp_path / 'burnup.brn'
    fofem_gui_emissions._write_burnup_params_694(
        str(out_path), intensity=500, ig_time=60, windspeed=2, depth=0.3, ambient_temp=20,
    )
    fixture_path = os.path.join(_BUNDLE_FIXTURE_DIR, 'burnup_parameters_694.brn')
    with open(fixture_path, 'rb') as f:
        # Git can check out this text fixture with LF on Linux; the writer always
        # emits CRLF for the Windows batch application on every platform.
        expected = f.read().replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')
    with open(out_path, 'rb') as f:
        actual = f.read()
    assert actual == expected


@pytest.mark.parametrize('intensity', [1234.5, 39.999])
def test_write_burnup_params_694_substitutes_dynamic_values(tmp_path, intensity):
    out_path = tmp_path / 'burnup.brn'
    fofem_gui_emissions._write_burnup_params_694(
        str(out_path), intensity=intensity, ig_time=61.25, windspeed=3.14, depth=0.42, ambient_temp=25.5,
    )
    content = out_path.read_text()
    assert f'#INTENSITY {intensity}' in content
    assert '#IG_TIME 61.25' in content
    assert '#WINDSPEED 3.14' in content
    assert '#DEPTH 0.42' in content
    assert '#AMBIENT_TEMP 25.5' in content
    # Fixed physical-property switches are unaffected by the dynamic substitution
    assert '#MAX_TIMES 3000' in content
    assert '#R0 1.83' in content
    assert content.count('\n') == 113


def _make_consumption_row_series(consume_model):
    """
    Build a Series with every field _write_consumption_input() reads by name, in an
    intentionally scrambled order (unrelated to _CONSUMPTION_FIELD_ORDER) to prove the writer
    looks fields up by name rather than relying on incidental Series order.

    :param consume_model: 'C' or 'S'.
    :return: pd.Series.
    """
    data = {
        'FuelCategory': 'Natural', '#PlotId': 'p1', 'CoverGroup': 'GrassGroup',
        'Litter': 1.11, 'wfl1Hour': 2.0, 'wfl10Hour': 3.0, 'wfl10HourMoisture': 4.0,
        'wfl100Hour': 5.0, 'wfl3_6S': 6.0, 'wfl6_9S': 7.0, 'wfl9_20S': 8.0, 'wfl20plusS': 9.0,
        'wfl3_6R': 10.0, 'wfl6_9R': 11.0, 'wfl9_20R': 12.0, 'wfl20plusR': 13.0,
        'wfl1000HourMoisture': 14.0, 'Duff': 15.0, 'DuffMoisture': 16.0, 'DuffDepth': 17.0,
        'Herbaceous': 18.0, 'Shrub': 19.0, 'CrownFoliage': 20.0, 'CrownBranch': 21.0,
        'PercentCrownBurned': 22.0, 'Region': 'InteriorWest', 'Season': 'Summer',
        'temp': 23.5,
        'LitterLoad_ConsumEq1': -1, 'PctDuff_ConsumEq2': -1, 'DuffDepth_ConsumEq3': -1,
        'MSE_ConsumEq4': -1, 'Herb_ConsumEq5': -1, 'Shrub_ConsumEq6': -1,
    }
    if consume_model == 'S':
        data['SoilFamily'] = 'Loamy-Skeletal'
        data['SoilMoisture'] = 10.0
    return pd.Series(data)


def test_write_consumption_input_writes_expected_switches_and_field_order_for_consumption(tmp_path):
    input_path = tmp_path / 'input.txt'
    burnup_path = tmp_path / 'Burnup-In.brn'
    fofem_gui_emissions._write_consumption_input(
        str(input_path), _make_consumption_row_series('C'), 'C', str(burnup_path),
    )
    lines = input_path.read_text().splitlines()
    assert lines[0] == '#1k-SizeClass'
    assert lines[1] == '#ConsumptionEquation'
    assert lines[2] == f'#EFG-STFS {fofem_gui_emissions._EFG_STFS}'
    assert lines[3] == f'#EFG-CWDRSC {fofem_gui_emissions._EFG_CWDRSC}'
    assert lines[4] == f'#EFG-DuffRSC {fofem_gui_emissions._EFG_DUFFRSC}'
    assert lines[5] == f'#BurnUpFile {os.path.abspath(str(burnup_path))}'
    assert lines[6] == '#PlotId,Litter'
    fields = lines[7].split(',')
    assert fields[0] == 'p1'
    assert fields[1] == '1.11'  # Litter
    assert fields[-6:] == ['-1', '-1', '-1', '-1', '-1', '-1']  # six equation overrides last
    # No SoilFamily/SoilMoisture/AmbientTemp for a non-soil run
    assert 'Loamy-Skeletal' not in lines[7]
    assert len(fields) == len(fofem_gui_emissions._CONSUMPTION_FIELD_ORDER) + 6


def test_write_consumption_input_inserts_soil_fields_and_ambient_temp_before_equations(tmp_path):
    input_path = tmp_path / 'input.txt'
    burnup_path = tmp_path / 'Burnup-In.brn'
    fofem_gui_emissions._write_consumption_input(
        str(input_path), _make_consumption_row_series('S'), 'S', str(burnup_path),
    )
    fields = input_path.read_text().splitlines()[7].split(',')
    expected_len = len(fofem_gui_emissions._CONSUMPTION_FIELD_ORDER) + len(fofem_gui_emissions._SOIL_FIELD_ORDER) + 1 + 6
    assert len(fields) == expected_len
    # SoilFamily, SoilMoisture, AmbientTemp appear immediately before the six equation overrides
    assert fields[-9:-6] == ['Loamy-Skeletal', '10.0', '23.5']
    assert fields[-6:] == ['-1', '-1', '-1', '-1', '-1', '-1']


def test_write_consumption_input_writes_required_expanded_emission_factor_switches(tmp_path):
    """Required by the runfofem.exe build verified 2026-09-29: their absence produces 'Input
    File has a missing or invalid Expanded Emission Factor switch(es)' against that build."""
    input_path = tmp_path / 'input.txt'
    burnup_path = tmp_path / 'Burnup-In.brn'
    for consume_model in ('C', 'S'):
        fofem_gui_emissions._write_consumption_input(
            str(input_path), _make_consumption_row_series(consume_model), consume_model, str(burnup_path),
        )
        lines = input_path.read_text().splitlines()
        assert f'#EFG-STFS {fofem_gui_emissions._EFG_STFS}' in lines
        assert f'#EFG-CWDRSC {fofem_gui_emissions._EFG_CWDRSC}' in lines
        assert f'#EFG-DuffRSC {fofem_gui_emissions._EFG_DUFFRSC}' in lines
        # Switches precede #BurnUpFile/#PlotId,Litter/the data row, matching the upstream
        # sample input files' ordering (sampledata/ConE-In.txt, sampledata/Soil-In.txt).
        assert lines.index('#ConsumptionEquation') < lines.index(f'#EFG-STFS {fofem_gui_emissions._EFG_STFS}')
        assert lines.index(f'#EFG-DuffRSC {fofem_gui_emissions._EFG_DUFFRSC}') < lines.index('#PlotId,Litter')


def _write_runfofem_output_csv(path, header_cols, plot_ids, data_row_values):
    """
    Write a small CSV shaped like a real runfofem.exe consumption/soil output (header row, a
    shorter units row, then data rows) for _parse_runfofem_output() tests.

    :param path: Output CSV path.
    :param header_cols: Full header column list, first entry 'Std'.
    :param plot_ids: Plot IDs for the data rows, in order.
    :param data_row_values: List of per-row value lists (excluding the plot ID).
    :return: None.
    """
    with open(path, 'w') as f:
        f.write(','.join(header_cols) + '\n')
        f.write('Id,' + ','.join(['x'] * (len(header_cols) - 1)) + '\n')
        for plot_id, values in zip(plot_ids, data_row_values):
            f.write(f'"{plot_id}", ' + ', '.join(str(v) for v in values) + '\n')


@pytest.mark.parametrize('platform', ['win32', 'linux'])
def test_run_runfofem_uses_platform_launcher(tmp_path, monkeypatch, platform):
    """Windows runs the EXE directly; Linux launches Wine without Windows flags."""
    fofem_dir = tmp_path / 'runtime with spaces'
    fofem_dir.mkdir()
    exe_path = fofem_dir / fofem_gui_emissions._RUNFOFEM_EXE
    exe_path.write_text('x')
    output_path = tmp_path / 'output.csv'
    output_path.write_text('output')
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return fofem_gui_emissions.subprocess.CompletedProcess(args, 0, '', '')

    monkeypatch.setattr(fofem_gui_emissions.sys, 'platform', platform)
    monkeypatch.setattr(fofem_gui_emissions.subprocess, 'run', fake_run)
    if platform == 'win32':
        monkeypatch.setattr(fofem_gui_emissions.subprocess, 'CREATE_NO_WINDOW', 0x08000000, raising=False)
    else:
        monkeypatch.delattr(fofem_gui_emissions.subprocess, 'CREATE_NO_WINDOW', raising=False)
    monkeypatch.setenv('WINEPREFIX', str(tmp_path / 'prefix'))

    fofem_gui_emissions._run_runfofem(
        '2', str(tmp_path / 'input.tre'), str(output_path), str(tmp_path / 'error.txt'),
        str(tmp_path), str(fofem_dir), extra_args=['S', '10'],
    )

    args, kwargs = calls[0]
    expected_args = [str(exe_path), '2', str(tmp_path / 'input.tre'), str(output_path),
                     str(tmp_path / 'error.txt'), 'S', '10']
    assert args == (['wine'] + expected_args if platform == 'linux' else expected_args)
    assert kwargs['creationflags'] == (0x08000000 if platform == 'win32' else 0)
    assert kwargs['cwd'] == str(tmp_path)
    assert kwargs['env']['FOFEM_DATA'] == str(fofem_dir)
    assert kwargs['env']['WINEPREFIX'] == str(tmp_path / 'prefix')


def test_run_runfofem_raises_actionable_error_on_missing_vcredist_dll(tmp_path, monkeypatch):
    """A STATUS_DLL_NOT_FOUND exit code (missing Microsoft Visual C++ Redistributable) must
    raise a specific, actionable message rather than the generic exit-code message."""
    fofem_dir = tmp_path / 'fofem_dir'
    fofem_dir.mkdir()
    (fofem_dir / fofem_gui_emissions._RUNFOFEM_EXE).write_text('x')
    worker_dir = tmp_path / 'worker'
    worker_dir.mkdir()

    class _FakeCompletedProcess:
        returncode = -1073741515  # 0xC0000135, STATUS_DLL_NOT_FOUND, as a signed 32-bit int.
        stdout = ''
        stderr = ''

    monkeypatch.setattr(
        fofem_gui_emissions.subprocess, 'run', lambda *args, **kwargs: _FakeCompletedProcess()
    )

    with pytest.raises(RuntimeError, match='Visual C\\+\\+ Redistributable'):
        fofem_gui_emissions._run_runfofem(
            '0', str(tmp_path / 'in.txt'), str(tmp_path / 'out.txt'), str(tmp_path / 'err.txt'),
            str(worker_dir), str(fofem_dir),
        )


def test_run_runfofem_reports_generic_exit_code_for_other_failures(tmp_path, monkeypatch):
    """A non-zero exit code unrelated to STATUS_DLL_NOT_FOUND keeps the generic message."""
    fofem_dir = tmp_path / 'fofem_dir'
    fofem_dir.mkdir()
    (fofem_dir / fofem_gui_emissions._RUNFOFEM_EXE).write_text('x')
    worker_dir = tmp_path / 'worker'
    worker_dir.mkdir()

    class _FakeCompletedProcess:
        returncode = 1
        stdout = ''
        stderr = 'some other failure'

    monkeypatch.setattr(
        fofem_gui_emissions.subprocess, 'run', lambda *args, **kwargs: _FakeCompletedProcess()
    )

    with pytest.raises(RuntimeError, match='exited with code 1'):
        fofem_gui_emissions._run_runfofem(
            '0', str(tmp_path / 'in.txt'), str(tmp_path / 'out.txt'), str(tmp_path / 'err.txt'),
            str(worker_dir), str(fofem_dir),
        )


def test_parse_runfofem_output_drops_std_after_validating_plot_identity(tmp_path):
    header = ['Std', 'LitPre', 'LitCon'] + [f'col{i}' for i in range(77)]
    assert len(header) == 80
    output_path = tmp_path / 'out.csv'
    _write_runfofem_output_csv(output_path, header, ['p1'], [[1.0, 2.0] + [0] * 77])
    result = fofem_gui_emissions._parse_runfofem_output(str(output_path), ['p1'], 'C')
    assert 'Std' not in result.columns
    assert result.loc[0, 'LitPre'] == pytest.approx(1.0)


def test_parse_runfofem_output_rejects_unexpected_column_count(tmp_path):
    header = ['Std', 'LitPre']
    output_path = tmp_path / 'out.csv'
    _write_runfofem_output_csv(output_path, header, ['p1'], [[1.0]])
    with pytest.raises(ValueError, match='column count'):
        fofem_gui_emissions._parse_runfofem_output(str(output_path), ['p1'], 'C')


def test_parse_runfofem_output_rejects_plot_identity_mismatch(tmp_path):
    header = ['Std', 'LitPre', 'LitCon'] + [f'col{i}' for i in range(77)]
    output_path = tmp_path / 'out.csv'
    _write_runfofem_output_csv(output_path, header, ['unexpected_plot'], [[1.0, 2.0] + [0] * 77])
    with pytest.raises(ValueError, match='plot identity'):
        fofem_gui_emissions._parse_runfofem_output(str(output_path), ['p1'], 'C')


_CONSUME_ROW = {
    '#PlotId': 'p1', 'Litter': 1.0, 'Duff': 2.0, 'DuffDepth': 3.0,
    'Region': 'InteriorWest', 'CoverGroup': 'GrassGroup', 'FuelCategory': 'Natural',
    'Season': 'Summer', 'remove_hereafter': None, 'fuel_bed_depth_m': 0.25,
}
_FIRE_ROW = {
    'unique_id': 'p1', 'wx_date': 20250615, 'hfi': 1500.0, 'flame_res_time_sec': 60.0,
    'flame_depth_m': 2.5,
    'instand_ws_mps': 2.0, 'temp': 20.0, 'mc_sa': 10.0, 'mc_dmc': 20.0, 'dc': 100.0, 'cfb': 0.1,
}


def _write_process_emissions_inputs(tmp_path, units):
    """
    Write a matching consumption/fire CSV pair for process_emissions() end-to-end tests.

    :param tmp_path: pytest tmp_path fixture.
    :param units: 'SI' or 'Imperial'.
    :return: (consume_csv_path, fire_csv_path, out_dir) as strings.
    """
    consume_csv_path = tmp_path / fofem_units.consume_filename(units)
    pd.DataFrame([_CONSUME_ROW]).to_csv(consume_csv_path, index=False)
    fire_csv_path = tmp_path / 'fire.csv'
    pd.DataFrame([_FIRE_ROW]).to_csv(fire_csv_path, index=False)
    return str(consume_csv_path), str(fire_csv_path), str(tmp_path / 'out')


def test_process_emissions_rejects_invalid_units(tmp_path):
    consume_csv, fire_csv, out_dir = _write_process_emissions_inputs(tmp_path, 'SI')
    with pytest.raises(ValueError, match='Invalid FOFEM processing units'):
        fofem_gui_emissions.process_emissions(
            plot_wx_fire_csv_path=fire_csv,
            plot_id_col_name='unique_id',
            fofem_consume_csv_path=consume_csv,
            out_dir=out_dir,
            emissions_units='metric',
        )


def test_process_emissions_rejects_units_filename_mismatch(tmp_path):
    consume_csv, fire_csv, out_dir = _write_process_emissions_inputs(tmp_path, 'SI')
    with pytest.raises(ValueError, match='SI.*Imperial|Imperial.*SI'):
        fofem_gui_emissions.process_emissions(
            plot_wx_fire_csv_path=fire_csv,
            plot_id_col_name='unique_id',
            fofem_consume_csv_path=consume_csv,
            out_dir=out_dir,
            emissions_units='Imperial',
        )


def _fake_model_emissions_factory(recorded_units):
    """
    Build a _model_emissions() stub that records emissions_units and returns canned Imperial
    runfofem.exe-style results (LitPre in T/ac, DufDepPre in inches, PM25F in lb/ac), skipping
    any real Burnup/subprocess execution.

    :param recorded_units: List to append each call's emissions_units argument to.
    :return: Callable matching _model_emissions()'s signature.
    """
    def _fake(row, out_dir, consume_model, emissions_units, fofem_dir):
        recorded_units.append(emissions_units)
        return {'LitPre': 4.46089561, 'DufDepPre': 1.1811, 'PM25F': 10.0}
    return _fake


def test_process_emissions_threads_units_and_converts_si_final_result(tmp_path, monkeypatch):
    consume_csv, fire_csv, out_dir = _write_process_emissions_inputs(tmp_path, 'SI')
    recorded_units = []
    monkeypatch.setattr(
        fofem_gui_emissions, '_model_emissions', _fake_model_emissions_factory(recorded_units)
    )
    monkeypatch.setattr(fofem_gui_emissions.shutil, 'rmtree', lambda path, **kwargs: None)

    result = fofem_gui_emissions.process_emissions(
        plot_wx_fire_csv_path=fire_csv,
        plot_id_col_name='unique_id',
        fofem_consume_csv_path=consume_csv,
        out_dir=out_dir,
        emissions_units='SI',
        return_df=True,
    )

    assert recorded_units == ['SI']
    # runfofem.exe always returns Imperial (4.46089561 T/ac, 1.1811 in, 10.0 lb/ac); converted
    # back to the SI equivalents of the canned values above.
    assert result.loc[0, 'LitPre_kgpm2'] == pytest.approx(1.0, abs=1e-6)
    assert result.loc[0, 'DufDepPre_cm'] == pytest.approx(3.0, abs=1e-3)
    assert result.loc[0, 'PM25F_gpm2'] == pytest.approx(5.0, abs=1e-6)


def test_process_emissions_threads_units_and_passes_through_imperial_final_result(tmp_path, monkeypatch):
    consume_csv, fire_csv, out_dir = _write_process_emissions_inputs(tmp_path, 'Imperial')
    recorded_units = []
    monkeypatch.setattr(
        fofem_gui_emissions, '_model_emissions', _fake_model_emissions_factory(recorded_units)
    )
    monkeypatch.setattr(fofem_gui_emissions.shutil, 'rmtree', lambda path, **kwargs: None)

    result = fofem_gui_emissions.process_emissions(
        plot_wx_fire_csv_path=fire_csv,
        plot_id_col_name='unique_id',
        fofem_consume_csv_path=consume_csv,
        out_dir=out_dir,
        emissions_units='Imperial',
        return_df=True,
    )

    assert recorded_units == ['Imperial']
    assert result.loc[0, 'LitPre_tpac'] == pytest.approx(4.46089561, abs=1e-6)
    assert result.loc[0, 'DufDepPre_in'] == pytest.approx(1.1811, abs=1e-6)
    assert result.loc[0, 'PM25F_lbpac'] == pytest.approx(10.0, abs=1e-6)


def test_process_emissions_defaults_to_si(tmp_path, monkeypatch):
    consume_csv, fire_csv, out_dir = _write_process_emissions_inputs(tmp_path, 'SI')
    recorded_units = []
    monkeypatch.setattr(
        fofem_gui_emissions, '_model_emissions', _fake_model_emissions_factory(recorded_units)
    )
    monkeypatch.setattr(fofem_gui_emissions.shutil, 'rmtree', lambda path, **kwargs: None)

    fofem_gui_emissions.process_emissions(
        plot_wx_fire_csv_path=fire_csv,
        plot_id_col_name='unique_id',
        fofem_consume_csv_path=consume_csv,
        out_dir=out_dir,
    )

    assert recorded_units == ['SI']


def test_process_emissions_threads_units_via_process_map_path(tmp_path, monkeypatch):
    """num_workers >= 4 takes the process_map()/ProcessPoolExecutor dispatch path."""
    consume_csv, fire_csv, out_dir = _write_process_emissions_inputs(tmp_path, 'SI')
    recorded_units = []

    def _fake_process_map(fn, records, out_dirs, consume_models, emissions_units_list, fofem_dirs, **kwargs):
        return [
            fn(r, d, m, u, f)
            for r, d, m, u, f in zip(records, out_dirs, consume_models, emissions_units_list, fofem_dirs)
        ]

    monkeypatch.setattr(
        fofem_gui_emissions, '_model_emissions', _fake_model_emissions_factory(recorded_units)
    )
    monkeypatch.setattr(fofem_gui_emissions, 'process_map', _fake_process_map)
    monkeypatch.setattr(fofem_gui_emissions, '_TQDM_PROCESS_MAP_AVAILABLE', True)
    monkeypatch.setattr(fofem_gui_emissions.shutil, 'rmtree', lambda path, **kwargs: None)

    fofem_gui_emissions.process_emissions(
        plot_wx_fire_csv_path=fire_csv,
        plot_id_col_name='unique_id',
        fofem_consume_csv_path=consume_csv,
        out_dir=out_dir,
        emissions_units='SI',
        num_workers=4,
    )

    assert recorded_units == ['SI']


# ── Reporting runfofem.exe failures from the parent process ──────────────────────────────────────────────────────────

def _failure(plot_id, wx_date, cause):
    """The result a failed _model_emissions() call returns."""
    return {'fofem_gui_error': f'runfofem.exe failed for plot "{plot_id}", wx_date {wx_date}: {cause}'}


def test_failed_emissions_rows_are_logged_once_per_plot_and_cause(caplog):
    merged = pd.DataFrame({
        '#PlotId': ['A_1', 'A_1', 'A_1', 'B'],
        'wx_date': [20250101, 20250102, 20250103, 20250101],
    })
    results = [
        _failure('A_1', 20250101, 'windspeed above 5 m/s'),
        {'LitPre': 1.0},
        _failure('A_1', 20250103, 'windspeed above 5 m/s'),
        _failure('B', 20250101, 'unexpected output'),
    ]
    with caplog.at_level(logging.ERROR, logger='fuel_analyst.components.fofem_gui_emissions'):
        fofem_gui_emissions._log_emissions_failures(results, merged, {'A_1': 'A 1'})
    logged = {r.unique_id: r for r in caplog.records}
    assert len(caplog.records) == 2
    assert logged['A 1'].issue_code == 'fofem_gui_emissions_runfofem_failure'  # the original plot ID, with its space
    assert logged['A 1'].getMessage() == (
        'runfofem.exe failed for 2 of 3 weather scenarios of this plot (first wx_date 20250101): windspeed above 5 m/s'
    )
    assert 'for 1 of 1 weather scenarios' in logged['B'].getMessage()
    assert logged['B'].getMessage().endswith('unexpected output')


def test_runfofem_failures_with_different_causes_are_logged_separately(caplog):
    merged = pd.DataFrame({'#PlotId': ['A', 'A'], 'wx_date': [1, 2]})
    results = [_failure('A', 1, 'cause one'), _failure('A', 2, 'cause two')]
    with caplog.at_level(logging.ERROR, logger='fuel_analyst.components.fofem_gui_emissions'):
        fofem_gui_emissions._log_emissions_failures(results, merged, {})
    assert sorted(r.getMessage().rsplit(': ', 1)[1] for r in caplog.records) == ['cause one', 'cause two']


def test_no_runfofem_failure_logs_nothing(caplog):
    merged = pd.DataFrame({'#PlotId': ['A'], 'wx_date': [1]})
    with caplog.at_level(logging.ERROR, logger='fuel_analyst.components.fofem_gui_emissions'):
        fofem_gui_emissions._log_emissions_failures([{'LitPre': 1.0}], merged, {})
    assert not caplog.records


def test_the_worker_returns_the_failure_without_logging_it(tmp_path, caplog):
    row = {'#PlotId': 'p1', 'wx_date': 20250615}
    with caplog.at_level(logging.ERROR, logger='fuel_analyst.components.fofem_gui_emissions'):
        result = fofem_gui_emissions._model_emissions(row, str(tmp_path), 'C', 'SI', str(tmp_path / 'missing_runtime'))
    assert 'runfofem.exe failed for plot "p1", wx_date 20250615' in result['fofem_gui_error']
    assert not caplog.records  # the parent process reports it; a worker's log record would never reach the report


@pytest.mark.parametrize('num_workers', [1, 4])
def test_process_emissions_reports_failed_rows_for_every_worker_count(tmp_path, monkeypatch, caplog, num_workers):
    consume_csv, fire_csv, out_dir = _write_process_emissions_inputs(tmp_path, 'SI')
    pd.DataFrame([dict(_FIRE_ROW, wx_date=20250615), dict(_FIRE_ROW, wx_date=20250616)]).to_csv(fire_csv, index=False)

    def failing(row, out_dir, consume_model, emissions_units, fofem_dir):
        return _failure(row['#PlotId'], row['wx_date'], 'windspeed above 5 m/s')

    monkeypatch.setattr(fofem_gui_emissions, '_model_emissions', failing)
    monkeypatch.setattr(fofem_gui_emissions, 'process_map', lambda fn, *args, **kwargs: [fn(*a) for a in zip(*args)],
                        raising=False)
    monkeypatch.setattr(fofem_gui_emissions, '_TQDM_PROCESS_MAP_AVAILABLE', True)
    monkeypatch.setattr(fofem_gui_emissions.shutil, 'rmtree', lambda path, **kwargs: None)
    with caplog.at_level(logging.ERROR, logger='fuel_analyst.components.fofem_gui_emissions'):
        fofem_gui_emissions.process_emissions(
            plot_wx_fire_csv_path=fire_csv, plot_id_col_name='unique_id', fofem_consume_csv_path=consume_csv,
            out_dir=out_dir, num_workers=num_workers,
        )
    [record] = caplog.records
    assert record.unique_id == 'p1'
    assert 'for 2 of 2 weather scenarios of this plot (first wx_date 20250615)' in record.getMessage()
