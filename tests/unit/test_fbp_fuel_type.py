import numpy as np
import pandas as pd
import pytest

from fuel_analyst.tools import fbp_fuel_type


def test_coerce_datetime_columns_accepts_tz_aware_naive_and_string_dates():
    df = pd.DataFrame({
        'HARVEST_DATE': [
            pd.Timestamp('2016-05-19', tz='UTC'),
            pd.Timestamp('2016-05-19'),
            '2016-05-19',
            None,
        ],
        'unrelated': ['a', 'b', 'c', 'd'],
    })
    field_dict = {'HARVEST_DATE': 'datetime64[ns]', 'unrelated': 'str'}

    result = fbp_fuel_type._coerce_datetime_columns(df, field_dict)

    assert result['HARVEST_DATE'].dtype == 'datetime64[ns]'
    assert result.loc[0, 'HARVEST_DATE'] == pd.Timestamp('2016-05-19')
    assert result.loc[1, 'HARVEST_DATE'] == pd.Timestamp('2016-05-19')
    assert result.loc[2, 'HARVEST_DATE'] == pd.Timestamp('2016-05-19')
    assert pd.isna(result.loc[3, 'HARVEST_DATE'])
    # non-datetime fields are left untouched
    assert result['unrelated'].tolist() == ['a', 'b', 'c', 'd']


def test_coerce_missing_species_codes_replaces_nan_with_none_not_string():
    # A rank with zero non-null values across every row (e.g. no plot has a 6th species) is a
    # genuine all-NaN float64 column, not an object column - this must still become real None,
    # not a value astype(str) would later turn into the literal text 'nan'.
    df = pd.DataFrame({
        'SPECIES_CD_1': ['FD', 'PL'],
        'SPECIES_CD_2': ['PL', np.nan],
        'SPECIES_CD_6': [np.nan, np.nan],
        'unrelated': ['a', 'b'],
    })
    assert df['SPECIES_CD_6'].dtype == np.float64

    result = fbp_fuel_type._coerce_missing_species_codes(df)

    assert result.loc[0, 'SPECIES_CD_1'] == 'FD'
    assert result.loc[1, 'SPECIES_CD_2'] is None
    assert result.loc[0, 'SPECIES_CD_6'] is None
    assert result.loc[1, 'SPECIES_CD_6'] is None
    assert result['unrelated'].tolist() == ['a', 'b']


def test_coerce_missing_species_codes_is_noop_when_no_species_columns_present():
    df = pd.DataFrame({'unrelated': ['a', 'b']})
    result = fbp_fuel_type._coerce_missing_species_codes(df)
    assert result['unrelated'].tolist() == ['a', 'b']


def _valid_required_fbp_fields():
    """
    Build a single-row DataFrame with all of _validate_user_supplied_fbp_fields()'s
    required fields correctly filled in.

    :return: DataFrame with 'unique_id' plus valid COAST_INTERIOR_CD/BEC_ZONE_CODE/
        BEC_SUBZONE/PROJ_AGE_1 values.
    """
    return pd.DataFrame({
        'unique_id': ['p1'],
        'COAST_INTERIOR_CD': ['I'], 'BEC_ZONE_CODE': ['IDF'], 'BEC_SUBZONE': ['dm'],
        'PROJ_AGE_1': [60.0],
    })


def test_validate_user_supplied_fbp_fields_accepts_fully_populated_row():
    fbp_fuel_type._validate_user_supplied_fbp_fields(_valid_required_fbp_fields())  # no raise


def test_validate_user_supplied_fbp_fields_accepts_none_for_proj_age_1():
    df = _valid_required_fbp_fields()
    df['PROJ_AGE_1'] = [None]
    fbp_fuel_type._validate_user_supplied_fbp_fields(df)  # no raise


@pytest.mark.parametrize('field', ['COAST_INTERIOR_CD', 'BEC_ZONE_CODE', 'BEC_SUBZONE'])
@pytest.mark.parametrize('missing_value', [np.nan, pd.NA, None])
def test_validate_user_supplied_fbp_fields_rejects_unfilled_string_field(field, missing_value):
    df = _valid_required_fbp_fields()
    df[field] = [missing_value]
    with pytest.raises(ValueError, match=field):
        fbp_fuel_type._validate_user_supplied_fbp_fields(df)


def test_validate_user_supplied_fbp_fields_accepts_nan_proj_age_1():
    # A plain float NaN passes isinstance(x, (int, float, type(None))) - matching
    # BCWFT2018's own verifyInputs() contract for this field, confirmed by direct testing
    # against the vendored bcwft2018.py (unlike pd.NA, which isinstance() rejects and which
    # does crash BCWFT2018, tested below).
    df = _valid_required_fbp_fields()
    df['PROJ_AGE_1'] = [np.nan]
    fbp_fuel_type._validate_user_supplied_fbp_fields(df)  # no raise


def test_validate_user_supplied_fbp_fields_rejects_pd_na_proj_age_1():
    df = _valid_required_fbp_fields()
    df['PROJ_AGE_1'] = [pd.NA]
    with pytest.raises(ValueError, match='PROJ_AGE_1'):
        fbp_fuel_type._validate_user_supplied_fbp_fields(df)


def test_validate_user_supplied_fbp_fields_names_every_affected_plot():
    df = pd.DataFrame({
        'unique_id': ['p1', 'p2', 'p3'],
        'COAST_INTERIOR_CD': ['I', np.nan, 'C'],
        'BEC_ZONE_CODE': ['IDF', 'ICH', np.nan],
        'BEC_SUBZONE': ['dm', 'wk', 'xc'],
        'PROJ_AGE_1': [60.0, 40.0, 20.0],
    })
    with pytest.raises(ValueError) as exc_info:
        fbp_fuel_type._validate_user_supplied_fbp_fields(df)
    message = str(exc_info.value)
    assert 'p2' in message  # COAST_INTERIOR_CD affected plot
    assert 'p3' in message  # BEC_ZONE_CODE affected plot
    assert 'p1' not in message


def test_validate_user_supplied_fbp_fields_reports_missing_column():
    df = _valid_required_fbp_fields().drop(columns=['BEC_SUBZONE'])
    with pytest.raises(ValueError, match='BEC_SUBZONE'):
        fbp_fuel_type._validate_user_supplied_fbp_fields(df)


def test_calc_fbp_fuel_type_raises_before_processing_when_required_field_missing():
    """The validation must run before BCWFT2018 processing starts, not surface as its own
    cryptic TypeError partway through the per-plot loop."""
    df = pd.DataFrame(_minimal_fuel_typing_row(BEC_ZONE_CODE=[np.nan]))
    with pytest.raises(ValueError, match='BEC_ZONE_CODE'):
        fbp_fuel_type._calc_fbp_fuel_type(df, season='growing')


def test_calc_fbp_fuel_type_accepts_unfilled_proj_age_1_when_stand_has_no_live_trees():
    """Regression: an earlier draft validated PROJ_AGE_1 before _calc_fbp_fuel_type()'s own
    'assign stand age to 0 if no live trees' step ran, wrongly rejecting a plot whose
    unfilled PROJ_AGE_1 that later step was always going to default to 0 anyway."""
    df = pd.DataFrame(_minimal_fuel_typing_row(
        stand_dens_tpha_live_sum=[0.0], PROJ_AGE_1=[pd.NA],
    ))

    result = fbp_fuel_type._calc_fbp_fuel_type(df, season='growing')

    assert result.loc[0, 'fbp_fuel_type'] not in (None, 'NoMatchingFuelType_ERROR')


@pytest.mark.parametrize('season', ['Growing', 'growing', 'GROWING', ' Growing '])
def test_calc_fbp_fuel_type_normalizes_season_casing(season):
    """Regression: BCWFT2018's verifyInputs() only accepts the exact lowercase strings
    'growing'/'dormant', but this module's own default parameter value and
    process_fbp_fuel_type()'s docstring both use 'Growing'/'Dormant'."""
    df = pd.DataFrame(_minimal_fuel_typing_row())

    result = fbp_fuel_type._calc_fbp_fuel_type(df, season=season)

    assert result.loc[0, 'fbp_fuel_type'] not in (None, 'NoMatchingFuelType_ERROR')


def test_calc_fbp_fuel_type_rejects_a_genuinely_invalid_season():
    df = pd.DataFrame(_minimal_fuel_typing_row())
    with pytest.raises(ValueError, match='season'):
        fbp_fuel_type._calc_fbp_fuel_type(df, season='summer')


def _minimal_fuel_typing_row(**overrides):
    """
    Build one minimal, valid row of _calc_fbp_fuel_type() input, with overrides applied.

    :param overrides: Column values to override on top of the minimal defaults.
    :return: Dict of column name to single-element list, ready for pd.DataFrame(...).
    """
    row = {
        'unique_id': ['p1'], '_date': ['06/15/2025 10:00'],
        'stand_dens_tpha_live_sum': [500.0], 'cc': [40.0],
        'stand_pct_cnfr_live': [100.0], 'stand_pct_brdlf_live': [0.0],
        'dom_substrate': ['TC'], 'treatment_type': ['untreated'],
        'PROJ_AGE_1': [60.0], 'stand_dens_tpha_dead_sum': [0.0],
        'stand_ba_m2pha_dead_sum': [0.0], 'stand_ba_m2pha_sum': [30.0],
        'COAST_INTERIOR_CD': ['I'], 'BEC_ZONE_CODE': ['IDF'], 'BEC_SUBZONE': ['dm'],
        'PROJ_HEIGHT_1': [20.0],
        'SPECIES_CD_1': ['FD'], 'SPECIES_PCT_1': [80.0],
        'SPECIES_CD_2': [np.nan], 'SPECIES_PCT_2': [np.nan],
        'SPECIES_CD_3': [np.nan], 'SPECIES_PCT_3': [np.nan],
        'SPECIES_CD_4': [np.nan], 'SPECIES_PCT_4': [np.nan],
        'SPECIES_CD_5': [np.nan], 'SPECIES_PCT_5': [np.nan],
        'SPECIES_CD_6': [np.nan], 'SPECIES_PCT_6': [np.nan],
    }
    row.update(overrides)
    return row


def test_calc_fbp_fuel_type_passes_real_none_not_a_stringified_nan(monkeypatch):
    """Regression for GitHub issue #24: a plot recording fewer than 6 species previously
    could reach BCWFT2018's verifyInputs() with a raw NaN SPECIES_CD_x, raising
    TypeError('The "SPECIES_CD_3" parameter must be string data type.'). Asserted here by
    capturing getFuelType()'s actual arguments directly, rather than only checking for an
    absence of TypeError - astype('str') stringifying NaN into 'nan' would also avoid a
    crash on some pandas versions while still passing a wrong, non-None value downstream."""
    from fuel_analyst._vendor import bcwft2018

    captured_calls = []
    original_get_fuel_type = bcwft2018.FuelTyping.getFuelType

    def _capturing_get_fuel_type(self, season, *args):
        captured_calls.append(args)
        return original_get_fuel_type(self, season, *args)

    monkeypatch.setattr(bcwft2018.FuelTyping, 'getFuelType', _capturing_get_fuel_type)

    df = pd.DataFrame(_minimal_fuel_typing_row())
    result = fbp_fuel_type._calc_fbp_fuel_type(df, season='growing')

    assert result.loc[0, 'fbp_fuel_type'] not in (None, 'NoMatchingFuelType_ERROR')
    # args mirror bc_fuel_type.getFuelType(season, *row[4:]) in production code, i.e.
    # fldList[3:] (everything from COAST_INTERIOR_CD onward) in that exact order - build the
    # name -> value mapping dynamically rather than hardcoding fragile positional indices.
    (call_args,) = captured_calls
    arg_names = bcwft2018.FuelTyping().fldList[3:]
    named_args = dict(zip(arg_names, call_args))
    assert named_args['SPECIES_CD_1'] == 'FD'
    for rank in (2, 3, 4, 5, 6):
        assert named_args[f'SPECIES_CD_{rank}'] is None


def test_calc_fbp_fuel_type_handles_dataset_where_every_plot_lacks_a_species_rank():
    """The all-NaN-column case specifically: when no plot in the whole input has a given
    species rank at all, that rank is a genuine float64 column of nothing but NaN."""
    df = pd.DataFrame(_minimal_fuel_typing_row(
        unique_id=['p1', 'p2'], _date=['06/15/2025 10:00', '06/15/2025 10:00'],
        stand_dens_tpha_live_sum=[500.0, 300.0], cc=[40.0, 20.0],
        stand_pct_cnfr_live=[100.0, 100.0], stand_pct_brdlf_live=[0.0, 0.0],
        dom_substrate=['TC', 'TC'], treatment_type=['untreated', 'untreated'],
        PROJ_AGE_1=[60.0, 40.0], stand_dens_tpha_dead_sum=[0.0, 0.0],
        stand_ba_m2pha_dead_sum=[0.0, 0.0], stand_ba_m2pha_sum=[30.0, 15.0],
        COAST_INTERIOR_CD=['I', 'I'], BEC_ZONE_CODE=['IDF', 'IDF'], BEC_SUBZONE=['dm', 'dm'],
        PROJ_HEIGHT_1=[20.0, 15.0],
        SPECIES_CD_1=['FD', 'PL'], SPECIES_PCT_1=[80.0, 100.0],
        SPECIES_CD_2=['PL', np.nan], SPECIES_PCT_2=[20.0, np.nan],
        SPECIES_CD_3=[np.nan, np.nan], SPECIES_PCT_3=[np.nan, np.nan],
        SPECIES_CD_4=[np.nan, np.nan], SPECIES_PCT_4=[np.nan, np.nan],
        SPECIES_CD_5=[np.nan, np.nan], SPECIES_PCT_5=[np.nan, np.nan],
        SPECIES_CD_6=[np.nan, np.nan], SPECIES_PCT_6=[np.nan, np.nan],
    ))
    assert df['SPECIES_CD_3'].dtype == np.float64

    result = fbp_fuel_type._calc_fbp_fuel_type(df, season='growing')

    assert (result['fbp_fuel_type'] != 'NoMatchingFuelType_ERROR').all()


def test_process_fbp_fuel_type_merges_fuel_type_into_conpyro_output(tmp_path, monkeypatch):
    master_path, prep_path, conpyro_path = (
        tmp_path / 'master.csv', tmp_path / 'prep.csv', tmp_path / 'conpyro.csv'
    )
    pd.DataFrame({'unique_id': ['p1'], '_date': ['2025-01-01'], 'cc': [50]}).to_csv(master_path, index=False)
    pd.DataFrame({
        'unique_id': ['p1'], '_date': ['2025-01-01'], 'treatment_area': ['A'],
        'treatment_unit': ['U'], 'treatment_type': ['treated'], 'plot_id': ['1'],
        'SPECIES_CD_1': ['FDI'], 'BEC_Zone': ['IDF'],
    }).to_csv(prep_path, index=False)
    pd.DataFrame({'unique_id': ['p1'], 'fbp_fuel_type': [None]}).to_csv(conpyro_path, index=False)

    def fake_calc(df, season):
        assert season == 'Growing'
        df['fbp_fuel_type'] = 'C2'
        return df

    monkeypatch.setattr(fbp_fuel_type, '_calc_fbp_fuel_type', fake_calc)
    fbp_fuel_type.process_fbp_fuel_type(
        str(master_path), str(prep_path), str(conpyro_path), str(tmp_path), 'Growing'
    )

    result = pd.read_csv(tmp_path / 'conpyro_fbp.csv')
    assert result.loc[0, 'fbp_fuel_type'] == 'C2'


def test_process_fbp_fuel_type_preserves_existing_assignment(tmp_path, monkeypatch):
    master_path, prep_path, conpyro_path = tmp_path / 'master.csv', tmp_path / 'prep.csv', tmp_path / 'conpyro.csv'
    pd.DataFrame({'unique_id': ['p1'], '_date': ['2025-01-01']}).to_csv(master_path, index=False)
    pd.DataFrame({
        'unique_id': ['p1'], '_date': ['2025-01-01'], 'treatment_area': ['A'],
        'treatment_unit': ['U'], 'treatment_type': ['treated'], 'plot_id': ['1'],
        'SPECIES_CD_1': ['FDI'],
    }).to_csv(prep_path, index=False)
    pd.DataFrame({'unique_id': ['p1'], 'fbp_fuel_type': ['M1']}).to_csv(conpyro_path, index=False)
    monkeypatch.setattr(
        fbp_fuel_type, '_calc_fbp_fuel_type',
        lambda df, season: df.assign(fbp_fuel_type='C2'),
    )
    fbp_fuel_type.process_fbp_fuel_type(
        str(master_path), str(prep_path), str(conpyro_path), str(tmp_path), 'Growing'
    )
    assert pd.read_csv(tmp_path / 'conpyro_fbp.csv').loc[0, 'fbp_fuel_type'] == 'M1'
