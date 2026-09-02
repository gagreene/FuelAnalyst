import logging

import pandas as pd

from fuel_analyst.components.fofem_mortality import filter_live_trees

_ISSUE_CODE = 'fofem_mortality_missing_status_column'


def test_filter_live_trees_keeps_only_live_positive_density_rows():
    tree_df = pd.DataFrame({
        'unique_id': ['p1', 'p1', 'p1'],
        'status': ['L', 'D', 'L'],
        'dens_live_ha': [2.47105, 0.0, 0.0],
    })
    logger = logging.getLogger('fuel_analyst.components.fofem_mortality')
    result = filter_live_trees(tree_df, logger, _ISSUE_CODE)
    assert result['status'].tolist() == ['L']
    assert result['dens_live_ha'].tolist() == [2.47105]


def test_filter_live_trees_missing_status_logs_and_falls_back(caplog):
    tree_df = pd.DataFrame({
        'unique_id': ['p1', 'p1'],
        'dens_live_ha': [2.47105, 0.0],
    })
    logger = logging.getLogger('fuel_analyst.components.fofem_mortality')
    with caplog.at_level(logging.ERROR, logger='fuel_analyst.components.fofem_mortality'):
        result = filter_live_trees(tree_df, logger, _ISSUE_CODE)

    assert result['dens_live_ha'].tolist() == [2.47105]
    matching = [r for r in caplog.records if getattr(r, 'issue_code', None) == _ISSUE_CODE]
    assert len(matching) == 1
