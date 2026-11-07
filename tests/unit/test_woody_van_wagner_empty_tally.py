"""A plot with no usable tally points must not stop the Van Wagner QMD calculation."""

import numpy as np
import pandas as pd
import pytest

from fuel_analyst.components.woody_debris import _get_van_wagner_qmd

_CLASSES = [0.5, 1, 3, 7]
_LENGTHS = [4, 10, 30, 30]


def _counts() -> pd.DataFrame:
    """
    Build tally counts for three plots: several classes, no counts at all, and one class only.

    :return: Count and transect length columns in the layout _get_van_wagner_qmd expects.
    """
    return pd.DataFrame({
        'tsct_length_max_can': [60.0, 60.0, 60.0],
        'tsct_length_total_can_4': [8.0, 8.0, 8.0],
        'tsct_length_total_can_10': [20.0, 20.0, 20.0],
        'tsct_length_total_can_30': [60.0, 60.0, 60.0],
        'woody_count_can_0_5': [5.0, 0.0, 0.0],
        'woody_count_can_1': [4.0, 0.0, 0.0],
        'woody_count_can_3': [3.0, 0.0, 2.0],
        'woody_count_can_7': [2.0, 0.0, 0.0],
    }, index=['a', 'none', 'one'])


@pytest.mark.parametrize('empty_count', [0., np.nan])
def test_all_empty_tally_rows_keep_qmd_missing(empty_count):
    counts = _counts().loc[['none']].copy()
    counts.loc[:, counts.columns.str.startswith('woody_count_')] = empty_count
    result = _get_van_wagner_qmd(counts, 'can', _CLASSES, _LENGTHS)

    assert result.index.tolist() == ['none']
    assert result.columns.tolist() == ['qmd0.5', 'qmd1', 'qmd3', 'qmd7']
    assert result.isna().all(axis=None)


def test_plot_with_a_single_class_falls_back_to_the_published_qmd():
    result = _get_van_wagner_qmd(_counts(), 'can', _CLASSES, _LENGTHS)

    # Delisle and Woodard (1988): QMD of the 1-3 cm class is 1.80575 cm.
    assert result.loc['one', 'qmd3'] == 1.80575
    assert result.loc['one', ['qmd0.5', 'qmd1', 'qmd7']].isna().all()


def test_plot_without_any_counts_does_not_fail_the_calculation():
    result = _get_van_wagner_qmd(_counts(), 'can', _CLASSES, _LENGTHS)

    assert list(result.index) == ['a', 'none', 'one']
    assert list(result.columns) == [f'qmd{dc}' for dc in _CLASSES]
    assert result.loc['a'].notna().all()
    assert result.loc['none'].isna().all()


def test_results_for_other_plots_do_not_depend_on_a_plot_without_counts():
    alone = _get_van_wagner_qmd(_counts().loc[['a']], 'can', _CLASSES, _LENGTHS)
    together = _get_van_wagner_qmd(_counts(), 'can', _CLASSES, _LENGTHS)

    np.testing.assert_allclose(together.loc['a'].to_numpy(float), alone.loc['a'].to_numpy(float))
