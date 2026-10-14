import warnings

import pandas as pd
import pytest

from fuel_analyst.components.conpyro_attributes import (
    _calc_stand_density,
    _calc_stand_type,
    _calc_veg_fuel_loads,
    _join_first_seen_unique_types,
    _prep_fbp_df,
)


def test_calc_stand_density_assigns_boundaries():
    df = pd.DataFrame({
        'conpyro_density_class': ['stale'] * 8,
        'cc': [0, 45, 45.1, 60, 60.1, 100, 101, None],
    })
    result = _calc_stand_density(df, 'cc')
    assert list(result.columns) == list(df.columns)
    assert result.columns.tolist().count('conpyro_density_class') == 1
    assert result['conpyro_density_class'].tolist() == ['L', 'L', 'M', 'M', 'H', 'H', None, None]


def test_calc_stand_type_identifies_mixedwood_and_dominant_type():
    params = pd.DataFrame({
        'TreeType': ['conifer', 'broadleaf'],
        'ConPyro_StandType': ['C', 'D'],
    }, index=['FDI', 'ACT'])
    rows = []
    for uid, first, second, pct in [('mixed', 'FDI', 'ACT', 60), ('conifer', 'FDI', None, 90)]:
        row = {'unique_id': uid, 'SPECIES_PCT_1': pct}
        row.update({f'SPECIES_CD_{i}': None for i in range(1, 7)})
        row['SPECIES_CD_1'], row['SPECIES_CD_2'] = first, second
        rows.append(row)
    df = pd.DataFrame(rows)
    df.insert(1, 'tree_type', 'stale')
    df.insert(3, 'conpyro_stand_type', 'stale')
    result = _calc_stand_type(df, params)
    assert list(result.columns) == list(df.columns)
    assert result.columns.tolist().count('tree_type') == 1
    assert result.columns.tolist().count('conpyro_stand_type') == 1
    assert result.set_index('unique_id')['conpyro_stand_type'].to_dict() == {'mixed': 'MW', 'conifer': 'C'}


def _stand_type_row(unique_id: str, species_codes: list, species_pct_1: float = 90) -> dict:
    row = {'unique_id': unique_id, 'SPECIES_PCT_1': species_pct_1}
    row.update({f'SPECIES_CD_{i}': None for i in range(1, 7)})
    for position, code in enumerate(species_codes, start=1):
        row[f'SPECIES_CD_{position}'] = code
    return row


def test_calc_stand_type_dedupes_repeated_tree_type():
    params = pd.DataFrame({
        'TreeType': ['conifer', 'conifer'],
        'ConPyro_StandType': ['C', 'C2'],
    }, index=['FDI', 'PLI'])
    df = pd.DataFrame([_stand_type_row('dup_conifer', ['FDI', 'PLI'])])
    result = _calc_stand_type(df, params)
    assert result.set_index('unique_id')['tree_type'].to_dict() == {'dup_conifer': 'conifer'}


def test_calc_stand_type_row_with_no_species_yields_empty_type_and_stand_type():
    params = pd.DataFrame({
        'TreeType': ['conifer'],
        'ConPyro_StandType': ['C'],
    }, index=['FDI'])
    df = pd.DataFrame([_stand_type_row('no_species', [])])
    result = _calc_stand_type(df, params)
    row = result.set_index('unique_id').loc['no_species']
    assert row['tree_type'] == ''
    assert row['conpyro_stand_type'] == ''


@pytest.mark.parametrize('species_codes, expected_tree_type', [
    (['FDI', 'ACT'], 'conifer broadleaf'),
    (['ACT', 'FDI'], 'broadleaf conifer'),
])
def test_calc_stand_type_preserves_first_seen_species_order(species_codes, expected_tree_type):
    params = pd.DataFrame({
        'TreeType': ['conifer', 'broadleaf'],
        'ConPyro_StandType': ['C', 'D'],
    }, index=['FDI', 'ACT'])
    df = pd.DataFrame([_stand_type_row('mixed', species_codes, species_pct_1=50)])
    result = _calc_stand_type(df, params)
    row = result.set_index('unique_id').loc['mixed']
    assert row['tree_type'] == expected_tree_type
    assert row['conpyro_stand_type'] == 'MW'


def test_calc_stand_type_shrub_species_reaches_tree_type_and_stand_type():
    # JD/JH (juniper) carry TreeType='shrub' in tree_parameters.csv and can be
    # tallied as a live tree species, so 'shrub' reaches this function through
    # SPECIES_CD_1..6 in practice.
    params = pd.DataFrame({
        'TreeType': ['shrub'],
        'ConPyro_StandType': ['S'],
    }, index=['JD'])
    df = pd.DataFrame([_stand_type_row('shrub_only', ['JD'])])
    result = _calc_stand_type(df, params)
    row = result.set_index('unique_id').loc['shrub_only']
    assert row['tree_type'] == 'shrub'
    assert row['conpyro_stand_type'] == 'S'


def test_calc_stand_type_shrub_with_conifer_does_not_trigger_mixedwood():
    # mw_mask only fires when 'conifer' and 'broadleaf' both appear in
    # tree_type; a shrub+conifer stand must fall through to the SPECIES_CD_1
    # lookup, not become 'MW'. ('all', the DECAYED sentinel, is never written
    # into SPECIES_CD_1..6 by trees.py, so it cannot reach this path today.)
    params = pd.DataFrame({
        'TreeType': ['shrub', 'conifer'],
        'ConPyro_StandType': ['S', 'C'],
    }, index=['JD', 'FDI'])
    df = pd.DataFrame([_stand_type_row('shrub_conifer', ['JD', 'FDI'], species_pct_1=50)])
    result = _calc_stand_type(df, params)
    row = result.set_index('unique_id').loc['shrub_conifer']
    assert row['tree_type'] == 'shrub conifer'
    assert row['conpyro_stand_type'] == 'S'


def test_calc_stand_type_three_distinct_types_preserves_order_and_triggers_mixedwood():
    params = pd.DataFrame({
        'TreeType': ['shrub', 'conifer', 'broadleaf'],
        'ConPyro_StandType': ['S', 'C', 'D'],
    }, index=['JD', 'FDI', 'ACT'])
    df = pd.DataFrame([_stand_type_row('three_types', ['JD', 'FDI', 'ACT'], species_pct_1=50)])
    result = _calc_stand_type(df, params)
    row = result.set_index('unique_id').loc['three_types']
    assert row['tree_type'] == 'shrub conifer broadleaf'
    assert row['conpyro_stand_type'] == 'MW'


def test_calc_stand_type_unknown_species_code_raises_keyerror():
    params = pd.DataFrame({
        'TreeType': ['conifer'],
        'ConPyro_StandType': ['C'],
    }, index=['FDI'])
    df = pd.DataFrame([_stand_type_row('unknown', ['ZZZ'])])
    with pytest.raises(KeyError):
        _calc_stand_type(df, params)


def test_calc_veg_fuel_loads_does_not_fragment_or_duplicate_existing_columns():
    df = pd.DataFrame({
        'grass_kgpm2': [1.0],
        'conpyro_herbaceous_fuel_load': [-1.0],
        'herb_kgpm2': [2.0],
    })
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', pd.errors.PerformanceWarning)
        for index in range(110):
            df[f'padding_{index}'] = index

    with warnings.catch_warnings():
        warnings.simplefilter('error', pd.errors.PerformanceWarning)
        result = _calc_veg_fuel_loads(
            df,
            {
                'herbaceous': ['grass', 'herb'],
                'grass': ['grass'],
                'empty': [],
            },
        )

    assert list(result.columns[:len(df.columns)]) == list(df.columns)
    assert result.columns.tolist().count('conpyro_herbaceous_fuel_load') == 1
    assert result[['conpyro_herbaceous_fuel_load',
                   'conpyro_grass_fuel_load',
                   'conpyro_empty_fuel_load']].iloc[0].tolist() == [3.0, 1.0, 0.0]


def test_calc_veg_fuel_loads_sums_fields_and_treats_missing_as_zero():
    df = pd.DataFrame({'grass_kgpm2': [1.0, None], 'herb_kgpm2': [2.0, 3.0]})
    result = _calc_veg_fuel_loads(df, {'herbaceous': ['grass', 'herb']})
    assert result['conpyro_herbaceous_fuel_load'].tolist() == [3.0, 3.0]


def test_prep_fbp_df_accepts_current_survey123_treatment_fields():
    source = pd.DataFrame({
        'unique_id': ['area_unit_treated_1_2025'],
        '_date': ['01/01/2025 10:00'],
        'treatment_area': ['area'],
        'treatment_unit': ['unit'],
        'treatment_type': ['treated'],
        'plot_id': ['1'],
        'SPECIES_CD_1': ['FDI'],
    })

    result = _prep_fbp_df(source)

    assert list(result.columns[:6]) == [
        'unique_id',
        '_date',
        'treatment_area',
        'treatment_unit',
        'treatment_type',
        'plot_id',
    ]


@pytest.mark.parametrize('dtype', ['object', 'string[pyarrow]'])
def test_join_first_seen_unique_types_handles_missing_values_in_any_string_dtype(dtype):
    # With pandas 3 and pyarrow installed, string columns are Arrow-backed and cannot be compared with a placeholder
    # object, which an earlier version of this function used for missing values.
    if dtype == 'string[pyarrow]':
        pytest.importorskip('pyarrow')
    columns = pd.DataFrame({
        'a': pd.array(['conifer', None, 'broadleaf', None], dtype=dtype),
        'b': pd.array(['conifer', 'broadleaf', None, None], dtype=dtype),
        'c': pd.array(['shrub', 'broadleaf', 'broadleaf', 'shrub'], dtype=dtype),
    })

    result = _join_first_seen_unique_types(columns)

    assert result.tolist() == ['conifer shrub', 'broadleaf', 'broadleaf', 'shrub']

