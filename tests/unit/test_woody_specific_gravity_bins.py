"""Specific gravity follows the size of the piece or tally class: greater than the previous column, up to its own."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from fuel_analyst.components.woody_debris import (
    _calc_tallied_woody_biomass,
    _calc_woody_specific_gravity,
    _get_sg_output_column,
    specific_gravity_map,
)

_TREE_PARAMETERS = Path(__file__).resolve().parents[2] / 'src' / 'fuel_analyst' / 'supporting_data' / 'tree_parameters.csv'
_PARAM_BY_OUTPUT = {out_col: param_col for out_col, param_col, _, _ in specific_gravity_map}


@pytest.mark.parametrize(('diameter', 'expected'), [
    (0.45, 'SG_0.5'), (0.5, 'SG_0.5'),
    (0.51, 'SG_0.635'), (0.635, 'SG_0.635'),
    (0.7, 'SG_1'), (1.0, 'SG_1'),
    (1.5, 'SG_2'), (2.0, 'SG_2'),
    (2.3, 'SG_2.54'), (2.54, 'SG_2.54'),
    (2.7, 'SG_3'), (3.0, 'SG_3'),
    (3.5, 'SG_4'), (4.0, 'SG_4'),
    (4.8, 'SG_5'), (5.0, 'SG_5'),
    (5.5, 'SG_6'), (6.0, 'SG_6'),
    (6.5, 'SG_7'), (7.0, 'SG_7'),
    (7.1, 'SG_7.62'), (7.6, 'SG_7.62'), (7.62, 'SG_7.62'),
    (7.63, 'SG_7.62+'), (20.0, 'SG_7.62+'),
])
def test_diameter_uses_the_first_column_at_or_above_it(diameter: float, expected: str) -> None:
    assert _PARAM_BY_OUTPUT[_get_sg_output_column(diameter)] == expected


@pytest.mark.parametrize('diameter', [0, -1.0, np.nan])
def test_diameter_without_a_column_is_rejected(diameter: float) -> None:
    with pytest.raises(ValueError):
        _get_sg_output_column(diameter)


def test_columns_are_contiguous_and_match_the_parameter_table() -> None:
    lowers = [lower for _, _, lower, _ in specific_gravity_map]
    uppers = [upper for _, _, _, upper in specific_gravity_map]
    assert lowers[0] == 0
    assert lowers[1:] == uppers[:-1]
    assert uppers[-1] == np.inf
    assert uppers == sorted(uppers)

    table_columns = {c for c in pd.read_csv(_TREE_PARAMETERS, nrows=0).columns if c.startswith('SG_')}
    assert {param_col for _, param_col, _, _ in specific_gravity_map} == table_columns


def test_measured_pieces_take_the_specific_gravity_of_their_size() -> None:
    tree_params = pd.read_csv(_TREE_PARAMETERS).set_index('Species')
    diameters = [0.45, 0.5, 4.8, 3.0, 7.6, 20.0]
    expected = ['SG_0.5', 'SG_0.5', 'SG_5', 'SG_3', 'SG_7.62', 'SG_7.62+']
    pieces = pd.DataFrame({
        'ParentGlobalID': ['p1'] * len(diameters),
        'woody_diam_cm': diameters,
        'woody_species_adj': ['FDI'] * len(diameters),
    })

    result = _calc_woody_specific_gravity(pieces, tree_params)

    assert result['woody_sg'].tolist() == pytest.approx([tree_params.loc['FDI', col] for col in expected])


def test_tally_class_uses_the_column_of_its_upper_cutoff() -> None:
    """A class ending at 2.5 cm uses the 2.54 column (there is no 2.5 column)."""
    df = pd.DataFrame({
        'GlobalID': ['p1'], 'num_transects': [2],
        't1_slope_cor': [1.0], 't2_slope_cor': [1.0], 'tsct_slope_cor': [1.0],
        'woody_tally_count': [4.0], 'woody_sg_2_54cm': [0.55],
    })
    pieces = pd.DataFrame({'ParentGlobalID': ['p1'], 'woody_diam_cm': [5.0], 'woody_diamSquared': [25.0]})
    params = {
        'measure_vs_tally_qmd_comparison': False,
        'woody_debris_classes': {
            'test': {
                'process_classes': True, 'class_extension': 'test',
                'diameter_cutoffs': [2.5], 'transect_lengths': [4, 30],
            },
        },
    }

    result, _ = _calc_tallied_woody_biomass(df, pieces, params)

    assert result.loc[0, 'woody_kgpm2_test_2_5'] == pytest.approx(0.55 * result.loc[0, 'woody_volume_test_2_5'] / 10)
    assert result.loc[0, 'woody_kgpm2_test_2_5'] > 0
