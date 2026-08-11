import numpy as np
import pandas as pd
import pytest

from fuel_analyst.components.canopy_cover import _process_cc_data, _process_transect_data


def _transect_row(transect, values, parent='plot-1'):
    row = {'ParentGlobalID': parent, 'cc_transect': transect}
    row.update({f'cc_{distance}': value for distance, value in zip(range(2, 32, 2), values)})
    return row


def test_process_transect_data_calculates_cover_and_excludes_points():
    values = ['cnfr'] * 6 + ['brdlf'] * 3 + ['cnfr_brdlf'] * 3 + ['none', 'exclude', 'exclude']
    result = _process_transect_data(pd.DataFrame([_transect_row(1, values)]))

    assert result.loc[0, 'cc'] == pytest.approx(100 * 12 / 13)
    assert result.loc[0, 'cc_cnfr'] == pytest.approx(100 * 9 / 13)
    assert result.loc[0, 'cc_brdlf'] == pytest.approx(100 * 6 / 13)
    assert result.loc[0, 'CC_t1'] == result.loc[0, 'cc']
    assert result.loc[0, 'CC_t2'] == 0


def test_process_cc_data_aggregates_transects_by_parent_id():
    transects = pd.DataFrame({
        'ParentGlobalID': ['p1', 'p1'],
        'CC_t1': [40.0, 0.0], 'CC_t2': [0.0, 60.0],
        'CC_cnfr_t1': [20.0, 0.0], 'CC_cnfr_t2': [0.0, 30.0],
        'CC_brdlf_t1': [20.0, 0.0], 'CC_brdlf_t2': [0.0, 30.0],
    })
    result = _process_cc_data(pd.DataFrame({'GlobalID': ['p1', 'missing']}), transects)

    assert result.loc[0, 'cc'] == 50.0
    assert result.loc[0, 'cc_cnfr'] == 25.0
    assert np.isnan(result.loc[1, 'cc'])
