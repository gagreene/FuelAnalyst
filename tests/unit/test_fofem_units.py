import pytest

from fuel_analyst.components import fofem_units


def test_validate_fofem_units_accepts_exact_strings():
    assert fofem_units.validate_fofem_units('SI') == 'SI'
    assert fofem_units.validate_fofem_units('Imperial') == 'Imperial'


@pytest.mark.parametrize('bad_units', ['si', 'IMPERIAL', 'Metric', '', None])
def test_validate_fofem_units_rejects_invalid_spellings(bad_units):
    with pytest.raises(ValueError, match='Invalid FOFEM processing units'):
        fofem_units.validate_fofem_units(bad_units)


def test_consume_filename_returns_canonical_names():
    assert fofem_units.consume_filename('SI') == 'fofem_consume_si_df.csv'
    assert fofem_units.consume_filename('Imperial') == 'fofem_consume_imperial_df.csv'


def test_consume_filename_rejects_invalid_units():
    with pytest.raises(ValueError, match='Invalid FOFEM processing units'):
        fofem_units.consume_filename('metric')


def test_infer_consume_units_reads_canonical_basenames():
    # os.path.basename() only splits on the current OS's separator(s) - a literal
    # Windows-style backslash path is not portable to POSIX CI runners, so both
    # paths here use forward slashes only.
    assert fofem_units.infer_consume_units('/out/fofem_consume_si_df.csv') == 'SI'
    assert fofem_units.infer_consume_units('/out/fofem_consume_imperial_df.csv') == 'Imperial'


def test_infer_consume_units_rejects_old_ambiguous_filename():
    with pytest.raises(ValueError, match='Cannot infer FOFEM processing units'):
        fofem_units.infer_consume_units('/out/fofem_consume_df.csv')


def test_infer_consume_units_rejects_renamed_file():
    with pytest.raises(ValueError, match='Cannot infer FOFEM processing units'):
        fofem_units.infer_consume_units('/out/my_copy_of_the_consume_file.csv')


def test_validate_consume_units_passes_on_match():
    fofem_units.validate_consume_units('/out/fofem_consume_si_df.csv', 'SI')
    fofem_units.validate_consume_units('/out/fofem_consume_imperial_df.csv', 'Imperial')


def test_validate_consume_units_raises_on_mismatch():
    with pytest.raises(ValueError, match='SI.*Imperial|Imperial.*SI'):
        fofem_units.validate_consume_units('/out/fofem_consume_si_df.csv', 'Imperial')


def test_validate_consume_units_raises_on_invalid_configured_units():
    with pytest.raises(ValueError, match='Invalid FOFEM processing units'):
        fofem_units.validate_consume_units('/out/fofem_consume_si_df.csv', 'metric')


def test_emissions_result_rename_map_uses_si_suffixes():
    rename_map = fofem_units.emissions_result_rename_map('SI')
    assert rename_map['LitPre'] == 'LitPre_kgpm2'
    assert rename_map['DufDepPre'] == 'DufDepPre_cm'
    assert rename_map['FlaDur'] == 'FlaDur_sec'
    assert rename_map['MSE'] == 'MSE_pct'
    assert rename_map['Lay0'] == 'Lay0_degC'
    assert rename_map['PM25F'] == 'PM25F_gpm2'
    assert rename_map['PM25S_Duff'] == 'PM25S_Duff_gpm2'


def test_emissions_result_rename_map_uses_imperial_suffixes():
    rename_map = fofem_units.emissions_result_rename_map('Imperial')
    assert rename_map['LitPre'] == 'LitPre_tpac'
    assert rename_map['DufDepPre'] == 'DufDepPre_in'
    assert rename_map['FlaDur'] == 'FlaDur_sec'
    assert rename_map['MSE'] == 'MSE_pct'
    assert rename_map['Lay0'] == 'Lay0_degC'
    assert rename_map['PM25F'] == 'PM25F_lbpac'


def test_emissions_result_rename_map_omits_unsuffixed_fields():
    rename_map = fofem_units.emissions_result_rename_map('SI')
    for field in ('Lay60d', 'Lay275d', 'Lit-Equ', 'BurnupError', 'BurnupLimitAdj'):
        assert field not in rename_map


def test_emissions_result_rename_map_rejects_invalid_units():
    with pytest.raises(ValueError, match='Invalid FOFEM processing units'):
        fofem_units.emissions_result_rename_map('metric')


def test_emissions_backends_share_the_same_rename_map_for_schema_parity():
    """Both fofem_emissions.py (pyfofem) and fofem_gui_emissions.py (fof_gui) rename their raw
    results via this exact shared function, so a given unit system always produces the same
    final result schema regardless of backend - see each module's own SI/Imperial tests
    (test_fofem_emissions_process.py, test_fofem_gui_emissions.py) for the concrete column-name
    assertions this guarantees."""
    from fuel_analyst.components import fofem_emissions, fofem_gui_emissions

    assert fofem_emissions.fofem_units.emissions_result_rename_map is fofem_units.emissions_result_rename_map
    assert fofem_gui_emissions.fofem_units.emissions_result_rename_map is fofem_units.emissions_result_rename_map
