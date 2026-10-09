import numpy as np
import pandas as pd
import pytest

from fuel_analyst.components.canopy_cover import _process_cc_data, _process_transect_data

from fuel_calculation_fixtures import _plot_cover, _transect_row






def test_process_cc_data_aggregates_transects_by_parent_id():
    transects = pd.DataFrame({
        'ParentGlobalID': ['p1', 'p1'],
        'cc_transect': [1, 2], 'cc': [40.0, 60.0],
        'cc_cnfr': [20.0, 30.0], 'cc_brdlf': [20.0, 30.0],
        'CC_t1': [40.0, 0.0], 'CC_t2': [0.0, 60.0],
        'CC_cnfr_t1': [20.0, 0.0], 'CC_cnfr_t2': [0.0, 30.0],
        'CC_brdlf_t1': [20.0, 0.0], 'CC_brdlf_t2': [0.0, 30.0],
    })
    result = _process_cc_data(pd.DataFrame({'GlobalID': ['p1', 'missing']}), transects)

    assert result.loc[0, 'cc'] == 50.0
    assert result.loc[0, 'cc_cnfr'] == 25.0
    assert np.isnan(result.loc[1, 'cc'])

@pytest.mark.parametrize(
    ('rows', 'expected'),
    [
        ([_transect_row(1, ['cnfr'] * 15), _transect_row(2, ['none'] * 15)], 50.0),
        ([_transect_row(1, ['cnfr'] * 15)], 100.0),
        ([], np.nan),
    ],
)
def test_process_cc_data_distinguishes_zero_cover_from_missing(rows, expected):
    result = _plot_cover(rows)
    if np.isnan(expected):
        assert result[['cc', 'cc_cnfr', 'cc_brdlf']].isna().all().all()
    else:
        assert result.loc[0, 'cc'] == expected


def test_process_cc_data_documents_duplicate_record_mean():
    result = _plot_cover([
        _transect_row(1, ['cnfr'] * 15),
        _transect_row(1, ['none'] * 15),
        _transect_row(2, ['none'] * 15),
    ])
    assert result.loc[0, 'cc'] == pytest.approx(100 / 3)
    assert result.loc[0, 'CC_t1'] == 100
    assert result.loc[0, 'CC_t2'] == 0


@pytest.mark.parametrize('include_valid', [False, True])
def test_process_cc_data_ignores_fully_excluded_transect(include_valid):
    rows = [_transect_row(2, ['exclude'] * 15)]
    rows.append(_transect_row(1, ['cnfr' if include_valid else 'exclude'] * 15))
    result = _plot_cover(rows)
    if include_valid:
        assert result.loc[0, 'cc'] == 100
        assert result.loc[0, 'cc_cnfr'] == 100
        assert result.loc[0, 'cc_brdlf'] == 0
    else:
        assert result[['cc', 'cc_cnfr', 'cc_brdlf']].isna().all().all()


@pytest.mark.parametrize('include_valid', [False, True])
def test_process_cc_data_ignores_invalid_transect_ids(include_valid):
    rows = [_transect_row(3, ['none'] * 15)]
    if include_valid:
        rows.append(_transect_row(1, ['cnfr'] * 15))
    result = _plot_cover(rows)
    if include_valid:
        assert result.loc[0, 'cc'] == 100
    else:
        assert result[['cc', 'cc_cnfr', 'cc_brdlf']].isna().all().all()
    assert result.loc[0, 'CC_t2'] == 0


@pytest.mark.parametrize('transect', [1, 2])
def test_process_cc_data_preserves_single_transect_cover(transect):
    result = _plot_cover([_transect_row(transect, ['cnfr'] * 15)])
    assert result.loc[0, 'cc'] == 100
    assert result.loc[0, 'cc_cnfr'] == 100
    assert result.loc[0, 'cc_brdlf'] == 0


def test_process_cc_data_weights_valid_transects_equally():
    result = _plot_cover([
        _transect_row(1, ['cnfr'] * 15),
        _transect_row(2, ['none'] + ['exclude'] * 14),
    ])
    assert result.loc[0, 'cc'] == 50


def test_process_transect_data_calculates_cover_and_excludes_points():
    values = ['cnfr'] * 6 + ['brdlf'] * 3 + ['cnfr_brdlf'] * 3 + ['none', 'exclude', 'exclude']
    result = _process_transect_data(pd.DataFrame([_transect_row(1, values)]))

    assert result.loc[0, 'cc'] == pytest.approx(100 * 12 / 13)
    assert result.loc[0, 'cc_cnfr'] == pytest.approx(100 * 9 / 13)
    assert result.loc[0, 'cc_brdlf'] == pytest.approx(100 * 6 / 13)
    assert result.loc[0, 'CC_t1'] == result.loc[0, 'cc']
    assert result.loc[0, 'CC_t2'] == 0
