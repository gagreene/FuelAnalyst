import numpy as np
import pandas as pd
import pytest

from fuel_analyst._vendor import bcwft2018
from fuel_analyst.tools import fbp_fuel_type


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
        'PROJ_AGE_1': [60.0], 'stand_dens_tpha_sum': [500.0], 'stand_dens_tpha_dead_sum': [0.0],
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


def _valid_required_fbp_fields():
    """
    Build a single-row DataFrame with all of _validate_user_supplied_fbp_fields()'s
    required fields correctly filled in (already-normalized values).

    :return: DataFrame with 'unique_id' plus valid COAST_INTERIOR_CD/BEC_ZONE_CODE/
        BEC_SUBZONE/PROJ_AGE_1 values.
    """
    return pd.DataFrame({
        'unique_id': ['p1'],
        'COAST_INTERIOR_CD': ['I'], 'BEC_ZONE_CODE': ['IDF'], 'BEC_SUBZONE': ['dm'],
        'PROJ_AGE_1': [60.0],
    })


@pytest.fixture(scope='module')
def bc_fuel_type():
    """Real bcwft.FuelTyping() instance, shared read-only across tests in this module."""
    return bcwft2018.FuelTyping()


def test_calc_fbp_fuel_type_accepts_unfilled_proj_age_1_when_stand_has_no_live_trees():
    """An earlier draft validated PROJ_AGE_1 before _calc_fbp_fuel_type()'s own
    'assign stand age to 0 if no live trees' step ran, wrongly rejecting a plot whose
    unfilled PROJ_AGE_1 that later step was always going to default to 0 anyway."""
    df = pd.DataFrame(_minimal_fuel_typing_row(
        stand_dens_tpha_live_sum=[0.0], PROJ_AGE_1=[pd.NA],
    ))

    result = fbp_fuel_type._calc_fbp_fuel_type(df, season='growing')

    assert result.loc[0, 'fbp_fuel_type'] not in (None, 'NoMatchingFuelType_ERROR')


def test_calc_fbp_fuel_type_ambiguous_live_density_names_only_the_affected_plot():
    df = pd.DataFrame({
        col: [
            _minimal_fuel_typing_row()[col][0],
            _minimal_fuel_typing_row()[col][0],
            _minimal_fuel_typing_row()[col][0],
        ]
        for col in _minimal_fuel_typing_row()
    })
    df['unique_id'] = ['ambiguous_plot', 'valid_live_plot', 'confirmed_all_dead_plot']
    df['stand_dens_tpha_live_sum'] = [np.nan, 500.0, np.nan]
    df['stand_dens_tpha_sum'] = [np.nan, 500.0, 300.0]
    df['stand_dens_tpha_dead_sum'] = [np.nan, 0.0, 300.0]

    with pytest.raises(ValueError) as exc_info:
        fbp_fuel_type._calc_fbp_fuel_type(df, season='growing')

    message = str(exc_info.value)
    assert 'ambiguous_plot' in message
    assert 'valid_live_plot' not in message
    assert 'confirmed_all_dead_plot' not in message


def test_calc_fbp_fuel_type_does_not_mutate_caller_dataframe():
    df = pd.DataFrame(_minimal_fuel_typing_row(BEC_ZONE_CODE=[' idf ']))
    original_bec_zone = df.loc[0, 'BEC_ZONE_CODE']
    fbp_fuel_type._calc_fbp_fuel_type(df, season='growing')
    assert df.loc[0, 'BEC_ZONE_CODE'] == original_bec_zone


def test_calc_fbp_fuel_type_handles_dataset_where_every_plot_lacks_a_species_rank():
    """The all-NaN-column case specifically: when no plot in the whole input has a given
    species rank at all, that rank is a genuine float64 column of nothing but NaN."""
    df = pd.DataFrame(_minimal_fuel_typing_row(
        unique_id=['p1', 'p2'], _date=['06/15/2025 10:00', '06/15/2025 10:00'],
        stand_dens_tpha_live_sum=[500.0, 300.0], cc=[40.0, 20.0],
        stand_pct_cnfr_live=[100.0, 100.0], stand_pct_brdlf_live=[0.0, 0.0],
        dom_substrate=['TC', 'TC'], treatment_type=['untreated', 'untreated'],
        PROJ_AGE_1=[60.0, 40.0], stand_dens_tpha_sum=[500.0, 300.0], stand_dens_tpha_dead_sum=[0.0, 0.0],
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


def test_calc_fbp_fuel_type_missing_proj_age_1_column_ok_when_no_live_trees_anywhere():
    df = pd.DataFrame(_minimal_fuel_typing_row(stand_dens_tpha_live_sum=[0.0]))
    df = df.drop(columns=['PROJ_AGE_1'])

    result = fbp_fuel_type._calc_fbp_fuel_type(df, season='growing')

    assert result.loc[0, 'fbp_fuel_type'] not in (None, 'NoMatchingFuelType_ERROR')


def test_calc_fbp_fuel_type_missing_proj_age_1_column_raises_when_a_live_stand_exists():
    df = pd.DataFrame(_minimal_fuel_typing_row(stand_dens_tpha_live_sum=[500.0]))
    df = df.drop(columns=['PROJ_AGE_1'])
    with pytest.raises(ValueError, match='PROJ_AGE_1'):
        fbp_fuel_type._calc_fbp_fuel_type(df, season='growing')


def test_calc_fbp_fuel_type_missing_proj_age_1_column_reports_only_live_plots():
    base = _minimal_fuel_typing_row()
    columns = list(base.keys())
    mixed = {
        col: [base[col][0], base[col][0]] if col not in ('unique_id', 'stand_dens_tpha_live_sum')
        else base[col]
        for col in columns
    }
    mixed['unique_id'] = ['live_plot', 'nonlive_plot']
    mixed['stand_dens_tpha_live_sum'] = [500.0, 0.0]
    df = pd.DataFrame(mixed).drop(columns=['PROJ_AGE_1'])

    with pytest.raises(ValueError) as exc_info:
        fbp_fuel_type._calc_fbp_fuel_type(df, season='growing')

    message = str(exc_info.value)
    assert 'live_plot' in message
    assert 'nonlive_plot' not in message


def test_calc_fbp_fuel_type_no_bcwft_row_processing_begins_when_validation_fails(monkeypatch):
    """Confirms the ValueError really does fire before the per-plot BCWFT2018 loop, not
    merely somewhere before the function returns."""
    calls = []
    monkeypatch.setattr(
        bcwft2018.FuelTyping, 'getFuelType',
        lambda self, season, *args: calls.append(args),
    )
    df = pd.DataFrame(_minimal_fuel_typing_row(BEC_ZONE_CODE=[np.nan]))
    with pytest.raises(ValueError, match='BEC_ZONE_CODE'):
        fbp_fuel_type._calc_fbp_fuel_type(df, season='growing')
    assert calls == []


def test_calc_fbp_fuel_type_normalizes_geographic_code_whitespace_and_casing():
    df = pd.DataFrame(_minimal_fuel_typing_row(
        COAST_INTERIOR_CD=[' i '], BEC_ZONE_CODE=['idf'], BEC_SUBZONE=['DM'],
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


def test_calc_fbp_fuel_type_passes_real_none_not_a_stringified_nan(monkeypatch):
    """Regression for GitHub issue #24: a plot recording fewer than 6 species previously
    could reach BCWFT2018's verifyInputs() with a raw NaN SPECIES_CD_x, raising
    TypeError('The "SPECIES_CD_3" parameter must be string data type.'). Asserted here by
    capturing getFuelType()'s actual arguments directly, rather than only checking for an
    absence of TypeError - astype('str') stringifying NaN into 'nan' would also avoid a
    crash on some pandas versions while still passing a wrong, non-None value downstream."""
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
    # Also confirms normalized (already-uppercase/lowercase) geographic values reach BCWFT2018.
    assert named_args['COAST_INTERIOR_CD'] == 'I'
    assert named_args['BEC_ZONE_CODE'] == 'IDF'
    assert named_args['BEC_SUBZONE'] == 'dm'


def test_calc_fbp_fuel_type_raises_before_processing_when_required_field_missing():
    """The validation must run before BCWFT2018 processing starts, not surface as its own
    cryptic TypeError partway through the per-plot loop."""
    df = pd.DataFrame(_minimal_fuel_typing_row(BEC_ZONE_CODE=[np.nan]))
    with pytest.raises(ValueError, match='BEC_ZONE_CODE'):
        fbp_fuel_type._calc_fbp_fuel_type(df, season='growing')


def test_calc_fbp_fuel_type_raises_directly_when_stand_dens_tpha_sum_missing():
    """stand_dens_tpha_sum is a dependency _validate_live_density() introduces; a DataFrame
    missing it entirely must raise the same clear ValueError as any other missing required
    column, not a raw KeyError from fbp_df['stand_dens_tpha_sum'] deep inside _no_live_trees()."""
    df = pd.DataFrame(_minimal_fuel_typing_row()).drop(columns=['stand_dens_tpha_sum'])
    with pytest.raises(ValueError, match='stand_dens_tpha_sum'):
        fbp_fuel_type._calc_fbp_fuel_type(df, season='growing')


def test_calc_fbp_fuel_type_raises_directly_when_unique_id_missing():
    """unique_id is accessed by _validate_live_density() before _validate_user_supplied_fbp_fields()
    ever runs its own identity-column check; a missing unique_id must still raise a clear
    ValueError, not a raw KeyError."""
    df = pd.DataFrame(_minimal_fuel_typing_row()).drop(columns=['unique_id'])
    with pytest.raises(ValueError, match='unique_id'):
        fbp_fuel_type._calc_fbp_fuel_type(df, season='growing')


def test_calc_fbp_fuel_type_raises_for_ambiguous_missing_live_density(monkeypatch):
    """A missing live density with no total/dead corroboration is ambiguous input (e.g. no tree
    records, unjoined identifiers, missing tree statuses), not a confirmed all-dead stand, and
    must be rejected before any BCWFT2018 row processing begins."""
    calls = []
    monkeypatch.setattr(
        bcwft2018.FuelTyping, 'getFuelType',
        lambda self, season, *args: calls.append(args),
    )
    df = pd.DataFrame(_minimal_fuel_typing_row(
        stand_dens_tpha_live_sum=[np.nan], stand_dens_tpha_sum=[np.nan], stand_dens_tpha_dead_sum=[np.nan],
    ))
    with pytest.raises(ValueError, match='stand_dens_tpha_live_sum'):
        fbp_fuel_type._calc_fbp_fuel_type(df, season='growing')
    assert calls == []


def test_calc_fbp_fuel_type_raises_for_ambiguous_missing_live_density_in_nullable_float_dtype(monkeypatch):
    """Regression: pandas' nullable 'Float64' dtype makes live_density.eq(0) return pd.NA rather
    than a plain bool wherever live_density is NA. Before _no_live_trees() filled NA results to
    False, this let an ambiguous missing live density silently bypass validation (a pd.NA-laden
    ambiguous mask's .any() returns False) and reach np.where() as a three-state Boolean, raising
    an unrelated TypeError instead of the intended ValueError."""
    calls = []
    monkeypatch.setattr(
        bcwft2018.FuelTyping, 'getFuelType',
        lambda self, season, *args: calls.append(args),
    )
    df = pd.DataFrame(_minimal_fuel_typing_row(
        stand_dens_tpha_live_sum=[np.nan], stand_dens_tpha_sum=[np.nan], stand_dens_tpha_dead_sum=[np.nan],
    ))
    for col in ('stand_dens_tpha_live_sum', 'stand_dens_tpha_sum', 'stand_dens_tpha_dead_sum'):
        df[col] = df[col].astype('Float64')
    with pytest.raises(ValueError, match='stand_dens_tpha_live_sum'):
        fbp_fuel_type._calc_fbp_fuel_type(df, season='growing')
    assert calls == []


def test_calc_fbp_fuel_type_rejects_a_genuinely_invalid_season():
    df = pd.DataFrame(_minimal_fuel_typing_row())
    with pytest.raises(ValueError, match='season'):
        fbp_fuel_type._calc_fbp_fuel_type(df, season='summer')


def test_calc_fbp_fuel_type_rejects_ambiguous_live_density_even_with_populated_age():
    """Proves ambiguous density itself is rejected, not merely caught incidentally by missing-age
    validation: PROJ_AGE_1 and every other required field is validly populated, but live density
    is missing and contradicted (not corroborated) by unequal total/dead density."""
    df = pd.DataFrame(_minimal_fuel_typing_row(
        stand_dens_tpha_live_sum=[np.nan], stand_dens_tpha_sum=[500.0], stand_dens_tpha_dead_sum=[300.0],
    ))
    with pytest.raises(ValueError, match='stand_dens_tpha_live_sum'):
        fbp_fuel_type._calc_fbp_fuel_type(df, season='growing')


def test_calc_fbp_fuel_type_rejects_missing_proj_age_1_for_a_live_stand():
    """The semantic reason this validation exists: BCWFT2018 branches on
    'if self.PROJ_AGE_1 < 60: ... elif self.PROJ_AGE_1 <= 99: ... else:' - both comparisons
    are False for NaN, so an unvalidated missing age for a live stand would silently fall
    into the '> 99 years old' branch instead of raising anything."""
    df = pd.DataFrame(_minimal_fuel_typing_row(
        stand_dens_tpha_live_sum=[500.0], PROJ_AGE_1=[np.nan],
    ))
    with pytest.raises(ValueError, match='PROJ_AGE_1'):
        fbp_fuel_type._calc_fbp_fuel_type(df, season='growing')


def test_calc_fbp_fuel_type_treats_confirmed_all_dead_stand_as_no_live_trees(monkeypatch):
    """Regression matching the Demo-WorkingWithConPyro tutorial's Demo_TU7_burned_P19_2021 plot:
    17 recorded trees, all dead, giving a missing stand_dens_tpha_live_sum corroborated by equal,
    populated stand_dens_tpha_sum/stand_dens_tpha_dead_sum. cc is set high enough that the old
    exact-zero-only fallback would have classified the row as treed."""
    captured_calls = []
    original_get_fuel_type = bcwft2018.FuelTyping.getFuelType

    def _capturing_get_fuel_type(self, season, *args):
        captured_calls.append(args)
        return original_get_fuel_type(self, season, *args)

    monkeypatch.setattr(bcwft2018.FuelTyping, 'getFuelType', _capturing_get_fuel_type)

    df = pd.DataFrame(_minimal_fuel_typing_row(
        stand_dens_tpha_live_sum=[np.nan], stand_dens_tpha_sum=[400.0], stand_dens_tpha_dead_sum=[400.0],
        stand_ba_m2pha_dead_sum=[30.0], stand_ba_m2pha_sum=[30.0], cc=[60.0],
    )).drop(columns=['PROJ_AGE_1'])

    result = fbp_fuel_type._calc_fbp_fuel_type(df, season='growing')

    assert result.loc[0, 'fbp_fuel_type'] not in (None, 'NoMatchingFuelType_ERROR')
    (call_args,) = captured_calls
    arg_names = bcwft2018.FuelTyping().fldList[3:]
    named_args = dict(zip(arg_names, call_args))
    assert named_args['BCLCS_LEVEL_2'] == 'N'
    assert named_args['PROJ_AGE_1'] == 0
    assert named_args['VRI_LIVE_STEMS_PER_HA'] == 0


def test_calc_fbp_fuel_type_treats_mixed_live_and_all_dead_rows_correctly(monkeypatch):
    captured_calls = []
    original_get_fuel_type = bcwft2018.FuelTyping.getFuelType

    def _capturing_get_fuel_type(self, season, *args):
        captured_calls.append(args)
        return original_get_fuel_type(self, season, *args)

    monkeypatch.setattr(bcwft2018.FuelTyping, 'getFuelType', _capturing_get_fuel_type)

    df = pd.DataFrame({
        col: [
            _minimal_fuel_typing_row()[col][0],
            _minimal_fuel_typing_row()[col][0],
            _minimal_fuel_typing_row()[col][0],
        ]
        for col in _minimal_fuel_typing_row()
    })
    df['unique_id'] = ['exact_zero_plot', 'confirmed_all_dead_plot', 'live_plot']
    df['stand_dens_tpha_live_sum'] = [0.0, np.nan, 500.0]
    df['stand_dens_tpha_sum'] = [0.0, 400.0, 500.0]
    df['stand_dens_tpha_dead_sum'] = [0.0, 400.0, 0.0]
    df['PROJ_AGE_1'] = [np.nan, np.nan, 60.0]

    result = fbp_fuel_type._calc_fbp_fuel_type(df, season='growing')

    assert (result['fbp_fuel_type'] != 'NoMatchingFuelType_ERROR').all()
    arg_names = bcwft2018.FuelTyping().fldList[3:]
    named_calls = [dict(zip(arg_names, call_args)) for call_args in captured_calls]

    exact_zero, confirmed_all_dead, live = named_calls
    assert exact_zero['BCLCS_LEVEL_2'] == 'N'
    assert exact_zero['PROJ_AGE_1'] == 0
    assert exact_zero['VRI_LIVE_STEMS_PER_HA'] == 0
    assert confirmed_all_dead['BCLCS_LEVEL_2'] == 'N'
    assert confirmed_all_dead['PROJ_AGE_1'] == 0
    assert confirmed_all_dead['VRI_LIVE_STEMS_PER_HA'] == 0
    assert live['BCLCS_LEVEL_2'] == 'T'
    assert live['PROJ_AGE_1'] == 60.0
    assert live['VRI_LIVE_STEMS_PER_HA'] == 500.0


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


def test_coerce_missing_species_codes_is_noop_when_no_species_columns_present():
    df = pd.DataFrame({'unrelated': ['a', 'b']})
    result = fbp_fuel_type._coerce_missing_species_codes(df)
    assert result['unrelated'].tolist() == ['a', 'b']


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


def test_is_valid_stand_age_accepts_pandas_nullable_numeric_value():
    series = pd.Series([60, pd.NA], dtype='Int64')
    assert fbp_fuel_type._is_valid_stand_age(series.iloc[0]) is True
    assert fbp_fuel_type._is_valid_stand_age(series.iloc[1]) is False


@pytest.mark.parametrize('value', [
    0, 0.0, 60, 60.5, np.int64(60), np.float64(60.5),
])
def test_is_valid_stand_age_accepts_valid_values(value):
    assert fbp_fuel_type._is_valid_stand_age(value) is True


@pytest.mark.parametrize('value', [
    None, pd.NA, np.nan, float('inf'), float('-inf'), '60', True, False, -5, -0.1,
])
def test_is_valid_stand_age_rejects_invalid_values(value):
    assert fbp_fuel_type._is_valid_stand_age(value) is False


def test_no_live_trees_false_for_pandas_na_in_nullable_float_dtype():
    """Regression: on pandas' nullable 'Float64' dtype, live_density.eq(0) returns pd.NA (not
    False) wherever live_density is NA, which would otherwise make the returned mask a
    three-state Boolean instead of the ordinary two-state mask callers rely on."""
    result = fbp_fuel_type._no_live_trees(
        pd.Series([pd.NA], dtype='Float64'),
        pd.Series([pd.NA], dtype='Float64'),
        pd.Series([pd.NA], dtype='Float64'),
    )
    assert result.tolist() == [False]


def test_no_live_trees_false_for_positive_live_density():
    result = fbp_fuel_type._no_live_trees(
        pd.Series([500.0]), pd.Series([500.0]), pd.Series([0.0]),
    )
    assert result.tolist() == [False]


def test_no_live_trees_false_when_live_total_and_dead_are_all_missing():
    result = fbp_fuel_type._no_live_trees(
        pd.Series([np.nan]), pd.Series([np.nan]), pd.Series([np.nan]),
    )
    assert result.tolist() == [False]


def test_no_live_trees_false_when_missing_live_and_total_differs_from_dead():
    result = fbp_fuel_type._no_live_trees(
        pd.Series([np.nan]), pd.Series([500.0]), pd.Series([300.0]),
    )
    assert result.tolist() == [False]


def test_no_live_trees_preserves_index_and_is_elementwise_across_mixed_cases():
    index = ['a', 'b', 'c', 'd', 'e']
    live = pd.Series([0.0, np.nan, 500.0, np.nan, np.nan], index=index)
    total = pd.Series([0.0, 500.0, 500.0, np.nan, 500.0], index=index)
    dead = pd.Series([0.0, 500.0, 0.0, np.nan, 300.0], index=index)

    result = fbp_fuel_type._no_live_trees(live, total, dead)

    assert result.index.tolist() == index
    assert result.tolist() == [True, True, False, False, False]


def test_no_live_trees_true_for_confirmed_all_dead_when_live_missing():
    result = fbp_fuel_type._no_live_trees(
        pd.Series([np.nan]), pd.Series([500.0]), pd.Series([500.0]),
    )
    assert result.tolist() == [True]


def test_no_live_trees_true_for_exact_zero_live_density():
    result = fbp_fuel_type._no_live_trees(
        pd.Series([0.0]), pd.Series([0.0]), pd.Series([0.0]),
    )
    assert result.tolist() == [True]


def test_normalize_user_supplied_fbp_fields_does_not_mutate_caller_dataframe():
    df = pd.DataFrame({'COAST_INTERIOR_CD': [' i '], 'BEC_ZONE_CODE': ['idf'], 'BEC_SUBZONE': ['DM']})
    fbp_fuel_type._normalize_user_supplied_fbp_fields(df)
    assert df.loc[0, 'COAST_INTERIOR_CD'] == ' i '
    assert df.loc[0, 'BEC_SUBZONE'] == 'DM'


def test_normalize_user_supplied_fbp_fields_is_noop_when_no_geographic_columns_present():
    df = pd.DataFrame({'unrelated': ['a', 'b']})
    result = fbp_fuel_type._normalize_user_supplied_fbp_fields(df)
    assert result['unrelated'].tolist() == ['a', 'b']


def test_normalize_user_supplied_fbp_fields_leaves_missing_and_non_string_values_untouched():
    df = pd.DataFrame({
        'COAST_INTERIOR_CD': [np.nan, None, pd.NA, 5],
        'BEC_ZONE_CODE': ['idf', 'idf', 'idf', 'idf'],
        'BEC_SUBZONE': ['dm', 'dm', 'dm', 'dm'],
    })

    result = fbp_fuel_type._normalize_user_supplied_fbp_fields(df)

    assert pd.isna(result.loc[0, 'COAST_INTERIOR_CD'])
    assert result.loc[1, 'COAST_INTERIOR_CD'] is None
    assert pd.isna(result.loc[2, 'COAST_INTERIOR_CD'])
    assert result.loc[3, 'COAST_INTERIOR_CD'] == 5


def test_normalize_user_supplied_fbp_fields_strips_and_cases_geographic_codes():
    df = pd.DataFrame({
        'COAST_INTERIOR_CD': [' i ', 'c'],
        'BEC_ZONE_CODE': [' idf ', 'ich'],
        'BEC_SUBZONE': [' DM ', 'WK'],
    })

    result = fbp_fuel_type._normalize_user_supplied_fbp_fields(df)

    assert result['COAST_INTERIOR_CD'].tolist() == ['I', 'C']
    assert result['BEC_ZONE_CODE'].tolist() == ['IDF', 'ICH']
    assert result['BEC_SUBZONE'].tolist() == ['dm', 'wk']


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


def test_validate_live_density_raises_for_ambiguous_missing_live_density():
    df = pd.DataFrame({
        'unique_id': ['p1'],
        'stand_dens_tpha_live_sum': [np.nan],
        'stand_dens_tpha_sum': [np.nan],
        'stand_dens_tpha_dead_sum': [np.nan],
    })
    with pytest.raises(ValueError, match='stand_dens_tpha_live_sum'):
        fbp_fuel_type._validate_live_density(df)


def test_validate_live_density_raises_when_a_required_column_is_missing():
    df = pd.DataFrame({
        'unique_id': ['p1'],
        'stand_dens_tpha_live_sum': [500.0],
        'stand_dens_tpha_dead_sum': [0.0],
    })
    with pytest.raises(ValueError, match='stand_dens_tpha_sum'):
        fbp_fuel_type._validate_live_density(df)


def test_validate_live_density_raises_when_unique_id_is_missing():
    df = pd.DataFrame({
        'stand_dens_tpha_live_sum': [np.nan],
        'stand_dens_tpha_sum': [500.0],
        'stand_dens_tpha_dead_sum': [500.0],
    })
    with pytest.raises(ValueError, match='unique_id'):
        fbp_fuel_type._validate_live_density(df)


def test_validate_live_density_returns_the_no_live_trees_mask_when_valid():
    df = pd.DataFrame({
        'unique_id': ['exact_zero', 'confirmed_all_dead', 'live'],
        'stand_dens_tpha_live_sum': [0.0, np.nan, 500.0],
        'stand_dens_tpha_sum': [0.0, 300.0, 500.0],
        'stand_dens_tpha_dead_sum': [0.0, 300.0, 0.0],
    })
    result = fbp_fuel_type._validate_live_density(df)
    assert result.tolist() == [True, True, False]


def test_validate_user_supplied_fbp_fields_accepts_fully_populated_row(bc_fuel_type):
    fbp_fuel_type._validate_user_supplied_fbp_fields(_valid_required_fbp_fields(), bc_fuel_type)  # no raise


@pytest.mark.parametrize('value', [0, 0.0, 60, 60.5, np.int64(60), np.float64(60.5)])
def test_validate_user_supplied_fbp_fields_accepts_valid_proj_age_1(value, bc_fuel_type):
    df = _valid_required_fbp_fields()
    df['PROJ_AGE_1'] = [value]
    fbp_fuel_type._validate_user_supplied_fbp_fields(df, bc_fuel_type)  # no raise


def test_validate_user_supplied_fbp_fields_names_every_affected_field_and_plot(bc_fuel_type):
    df = pd.DataFrame({
        'unique_id': ['p1', 'p2', 'p3'],
        'COAST_INTERIOR_CD': ['I', np.nan, 'C'],
        'BEC_ZONE_CODE': ['IDF', 'ICH', 'ZZZ'],
        'BEC_SUBZONE': ['dm', 'wk', 'xc'],
        'PROJ_AGE_1': [60.0, 40.0, np.nan],
    })
    with pytest.raises(ValueError) as exc_info:
        fbp_fuel_type._validate_user_supplied_fbp_fields(df, bc_fuel_type)
    message = str(exc_info.value)
    assert 'COAST_INTERIOR_CD' in message and 'p2' in message
    assert 'BEC_ZONE_CODE' in message and 'ZZZ' in message and 'p3' in message
    assert 'PROJ_AGE_1' in message and 'p3' in message
    assert 'p1' not in message


def test_validate_user_supplied_fbp_fields_raises_directly_when_unique_id_missing(bc_fuel_type):
    df = _valid_required_fbp_fields().drop(columns=['unique_id'])
    with pytest.raises(ValueError, match='unique_id'):
        fbp_fuel_type._validate_user_supplied_fbp_fields(df, bc_fuel_type)


@pytest.mark.parametrize('value', [
    None, pd.NA, np.nan, float('inf'), float('-inf'), '60', True, False, -5,
])
def test_validate_user_supplied_fbp_fields_rejects_invalid_proj_age_1(value, bc_fuel_type):
    df = _valid_required_fbp_fields()
    df['PROJ_AGE_1'] = [value]
    with pytest.raises(ValueError, match='PROJ_AGE_1'):
        fbp_fuel_type._validate_user_supplied_fbp_fields(df, bc_fuel_type)


@pytest.mark.parametrize('field', ['COAST_INTERIOR_CD', 'BEC_ZONE_CODE', 'BEC_SUBZONE'])
@pytest.mark.parametrize('invalid_value', [np.nan, pd.NA, None, '', '   ', 5])
def test_validate_user_supplied_fbp_fields_rejects_missing_string_field(field, invalid_value, bc_fuel_type):
    df = _valid_required_fbp_fields()
    df[field] = [invalid_value]
    with pytest.raises(ValueError, match=field):
        fbp_fuel_type._validate_user_supplied_fbp_fields(df, bc_fuel_type)


@pytest.mark.parametrize('field,unknown_value', [
    ('COAST_INTERIOR_CD', 'X'),
    ('BEC_ZONE_CODE', 'ZZZ'),
    ('BEC_SUBZONE', 'zz'),
])
def test_validate_user_supplied_fbp_fields_rejects_out_of_domain_string_value(field, unknown_value, bc_fuel_type):
    df = _valid_required_fbp_fields()
    df[field] = [unknown_value]
    with pytest.raises(ValueError, match=field) as exc_info:
        fbp_fuel_type._validate_user_supplied_fbp_fields(df, bc_fuel_type)
    assert unknown_value in str(exc_info.value)


def test_validate_user_supplied_fbp_fields_reports_missing_proj_age_1_column(bc_fuel_type):
    df = _valid_required_fbp_fields().drop(columns=['PROJ_AGE_1'])
    with pytest.raises(ValueError, match='PROJ_AGE_1'):
        fbp_fuel_type._validate_user_supplied_fbp_fields(df, bc_fuel_type)


def test_validate_user_supplied_fbp_fields_reports_missing_string_column(bc_fuel_type):
    df = _valid_required_fbp_fields().drop(columns=['BEC_SUBZONE'])
    with pytest.raises(ValueError, match='BEC_SUBZONE'):
        fbp_fuel_type._validate_user_supplied_fbp_fields(df, bc_fuel_type)


def test_process_fbp_fuel_type_fills_the_empty_placeholder_and_keeps_existing_values(tmp_path, monkeypatch):
    """The fbp_fuel_type placeholder is read as text, so it is filled where empty and kept where already set."""
    prep_columns = {
        '_date': ['2021-10-26'] * 3, 'treatment_area': ['A'] * 3, 'treatment_unit': ['U'] * 3,
        'treatment_type': ['burned'] * 3, 'plot_id': ['p1', 'p2', 'p3'], 'SPECIES_CD_1': ['PL'] * 3,
    }
    ids = ['a', 'b', 'c']
    pd.DataFrame({'unique_id': ids, '_date': ['2021-10-26'] * 3}).to_csv(tmp_path / 'master.csv', index=False)
    pd.DataFrame({'unique_id': ids, **prep_columns}).to_csv(tmp_path / 'prep.csv', index=False)
    pd.DataFrame({'unique_id': ids, 'fbp_fuel_type': ['', 'D1', '']}).to_csv(tmp_path / 'conpyro_df.csv', index=False)
    monkeypatch.setattr(
        fbp_fuel_type, '_calc_fbp_fuel_type',
        lambda df, season: df.assign(fbp_fuel_type=['C3', 'C5', 'M1']),
    )

    fbp_fuel_type.process_fbp_fuel_type(
        str(tmp_path / 'master.csv'), str(tmp_path / 'prep.csv'), str(tmp_path / 'conpyro_df.csv'),
        str(tmp_path / 'out'), 'Growing',
    )

    result = pd.read_csv(tmp_path / 'out' / 'conpyro_df_fbp.csv')
    assert result['fbp_fuel_type'].tolist() == ['C3', 'D1', 'M1']
