"""A plot with no usable tally points must not stop the Van Wagner QMD calculation."""

import logging
import warnings

import numpy as np
import pandas as pd
import pytest

from fuel_analyst.components import woody_debris
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


@pytest.mark.parametrize('empty_count', [0., np.nan, [0., np.nan, 0., np.nan]])
def test_all_empty_tally_rows_keep_qmd_missing(empty_count):
    counts = _counts().loc[['none']].copy()
    counts.loc[:, counts.columns.str.startswith('woody_count_')] = empty_count
    result = _get_van_wagner_qmd(counts, 'can', _CLASSES, _LENGTHS)

    assert result.index.tolist() == ['none']
    assert result.columns.tolist() == ['qmd0.5', 'qmd1', 'qmd3', 'qmd7']
    assert result.isna().all(axis=None)


@pytest.mark.parametrize('uncounted', [0., np.nan])
def test_exactly_two_usable_classes_fit_regression(uncounted):
    counts = _counts().loc[['a']].copy()
    columns = ['woody_count_can_0_5', 'woody_count_can_1', 'woody_count_can_3', 'woody_count_can_7']
    counts.loc['a', columns] = [0., uncounted, 25., 8.]
    result = _get_van_wagner_qmd(counts, 'can', _CLASSES, _LENGTHS)

    # Midpoints 2 and 5 cm have adjusted frequencies 25/2 and 8/4.
    # Their ratio is (5/2)^-2, so slope = -2 and QMD = sqrt(lower * upper).
    np.testing.assert_allclose(result.loc['a', ['qmd3', 'qmd7']].to_numpy(float),
                               [np.sqrt(3.), np.sqrt(21.)], rtol=1e-12)
    assert result.loc['a', ['qmd0.5', 'qmd1']].isna().all()


@pytest.mark.parametrize(('missing_classes', 'expected'), [
    ([0.5], [np.nan, np.nan, np.sqrt(3.), np.sqrt(21.)]),
    ([1], [np.nan, np.nan, np.sqrt(3.), np.sqrt(21.)]),
    ([3], [np.nan, np.nan, np.nan, 5.8905]),
    ([7], [np.nan, np.nan, 1.80575, np.nan]),
    (_CLASSES, [np.nan, np.nan, np.nan, np.nan]),
])
def test_missing_count_columns_keep_their_qmd_missing(missing_classes, expected):
    counts = _counts().loc[['a']].copy()
    columns = ['woody_count_can_0_5', 'woody_count_can_1', 'woody_count_can_3', 'woody_count_can_7']
    counts.loc['a', columns] = [0., 0., 25., 8.]
    counts = counts.drop(columns=[f'woody_count_can_{str(dc).replace(".", "_")}' for dc in missing_classes])
    original = counts.copy(deep=True)

    result = _get_van_wagner_qmd(counts, 'can', _CLASSES, _LENGTHS)

    # The remaining two-point fit has slope -2; one point uses the published fallback.
    np.testing.assert_allclose(result.loc['a'].to_numpy(float), expected, rtol=1e-12, equal_nan=True)
    pd.testing.assert_frame_equal(counts, original)


def test_plot_with_a_single_class_falls_back_to_the_published_qmd():
    result = _get_van_wagner_qmd(_counts(), 'can', _CLASSES, _LENGTHS)

    # Delisle and Woodard (1988): QMD of the 1-3 cm class is 1.80575 cm.
    assert result.loc['one', 'qmd3'] == 1.80575
    assert result.loc['one', ['qmd0.5', 'qmd1', 'qmd7']].isna().all()


def test_plot_without_any_counts_does_not_fail_the_calculation(caplog):
    with caplog.at_level(logging.WARNING, logger=woody_debris.__name__):
        result = _get_van_wagner_qmd(_counts(), 'can', _CLASSES, _LENGTHS)

    assert list(result.index) == ['a', 'none', 'one']
    assert list(result.columns) == [f'qmd{dc}' for dc in _CLASSES]
    assert result.loc['a'].notna().all()
    assert result.loc['none'].isna().all()
    assert not caplog.records


@pytest.mark.parametrize('failure', ['value_error', 'runtime_warning'])
@pytest.mark.parametrize('warning_mode', ['default', 'error'])
def test_regression_failure_falls_back_only_for_affected_plot(caplog, monkeypatch, failure, warning_mode):
    counts = _counts().rename(index={'a': 'bad', 'none': 'good'})
    counts['unique_id'] = counts.index
    columns = ['woody_count_can_0_5', 'woody_count_can_1', 'woody_count_can_3', 'woody_count_can_7']
    counts.loc['good', columns] = [0., 0., 25., 8.]
    real_linregress = woody_debris.linregress

    def fail_four_point_fit(in_x, in_y):
        if len(in_x) == 4:
            if failure == 'value_error':
                raise ValueError('Cannot calculate a linear regression if all x values are identical')
            warnings.warn('invalid value encountered in scalar divide', RuntimeWarning)
        return real_linregress(in_x, in_y)

    # Valid inputs cannot force every SciPy failure mode, so inject only the failing fit.
    monkeypatch.setattr(woody_debris, 'linregress', fail_four_point_fit)
    with warnings.catch_warnings(), caplog.at_level(logging.WARNING, logger=woody_debris.__name__):
        warnings.simplefilter(warning_mode, RuntimeWarning)
        result = _get_van_wagner_qmd(counts, 'can', _CLASSES, _LENGTHS)

    np.testing.assert_allclose(result.loc['bad'].to_numpy(float), [0.3155, 0.68975, 1.80575, 5.8905])
    np.testing.assert_allclose(result.loc['good'].to_numpy(float),
                               [np.nan, np.nan, np.sqrt(3.), np.sqrt(21.)], rtol=1e-12, equal_nan=True)
    assert result.loc['one', 'qmd3'] == 1.80575
    assert len(caplog.records) == 1
    assert caplog.records[0].unique_id == 'bad'
    assert caplog.records[0].issue_code == 'woody_qmd_regression_failed'


def test_regression_programming_errors_are_not_silenced(monkeypatch):
    def fail_fit(in_x, in_y):
        raise TypeError('unexpected regression API change')

    monkeypatch.setattr(woody_debris, 'linregress', fail_fit)
    with pytest.raises(TypeError, match='unexpected regression API change'):
        _get_van_wagner_qmd(_counts(), 'can', _CLASSES, _LENGTHS)


def test_results_for_other_plots_do_not_depend_on_a_plot_without_counts():
    alone = _get_van_wagner_qmd(_counts().loc[['a']], 'can', _CLASSES, _LENGTHS)
    together = _get_van_wagner_qmd(_counts(), 'can', _CLASSES, _LENGTHS)

    np.testing.assert_allclose(together.loc['a'].to_numpy(float), alone.loc['a'].to_numpy(float))


def test_zero_row_input_returns_empty_qmd_schema():
    counts = _counts().iloc[:0].copy()
    counts.index.name = 'plot'
    result = _get_van_wagner_qmd(counts, 'can', _CLASSES, _LENGTHS)

    assert result.empty
    assert result.columns.tolist() == ['qmd0.5', 'qmd1', 'qmd3', 'qmd7']
    pd.testing.assert_index_equal(result.index, counts.index, exact=True)
    assert all(dtype.kind == 'f' for dtype in result.dtypes)
