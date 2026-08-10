import pandas as pd
import pytest

from fuel_analyst.components.conpyro_attributes import (
    _calc_stand_density,
    _calc_stand_type,
    _calc_veg_fuel_loads,
    _prep_fbp_df,
)


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


def test_calc_veg_fuel_loads_sums_fields_and_treats_missing_as_zero():
    df = pd.DataFrame({'grass_kgpm2': [1.0, None], 'herb_kgpm2': [2.0, 3.0]})
    result = _calc_veg_fuel_loads(df, {'herbaceous': ['grass', 'herb']})
    assert result['conpyro_herbaceous_fuel_load'].tolist() == [3.0, 3.0]


def test_calc_stand_density_assigns_boundaries():
    df = pd.DataFrame({'cc': [0, 45, 45.1, 60, 60.1, 100, 101, None]})
    result = _calc_stand_density(df, 'cc')
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
    result = _calc_stand_type(pd.DataFrame(rows), params)
    assert result.set_index('unique_id')['conpyro_stand_type'].to_dict() == {'mixed': 'MW', 'conifer': 'C'}
