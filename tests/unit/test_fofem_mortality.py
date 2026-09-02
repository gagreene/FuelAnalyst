import logging
import sys
import types

import pandas as pd

if 'pyfofem' not in sys.modules:
    fake_package = types.ModuleType('pyfofem')
    fake_package.pyfofem = types.SimpleNamespace()
    sys.modules['pyfofem'] = fake_package

from fuel_analyst.components.fofem_mortality import _filter_live_trees


def test_filter_live_trees_keeps_only_live_positive_density_rows():
    tree_df = pd.DataFrame({
        'unique_id': ['p1', 'p1', 'p1'],
        'status': ['L', 'D', 'L'],
        'dens_live_ha': [2.47105, 0.0, 0.0],
    })
    result = _filter_live_trees(tree_df)
    assert result['status'].tolist() == ['L']
    assert result['dens_live_ha'].tolist() == [2.47105]


def test_filter_live_trees_missing_status_logs_and_falls_back(caplog):
    tree_df = pd.DataFrame({
        'unique_id': ['p1', 'p1'],
        'dens_live_ha': [2.47105, 0.0],
    })
    with caplog.at_level(logging.ERROR, logger='fuel_analyst.components.fofem_mortality'):
        result = _filter_live_trees(tree_df)

    assert result['dens_live_ha'].tolist() == [2.47105]
    matching = [r for r in caplog.records if getattr(r, 'issue_code', None) ==
                'fofem_mortality_missing_status_column']
    assert len(matching) == 1
