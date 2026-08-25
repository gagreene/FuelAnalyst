import warnings

import pandas as pd
import pytest

from fuel_analyst.components.conpyro_attributes import (
    _calc_stand_density,
    _calc_stand_type,
    _calc_veg_fuel_loads,
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
