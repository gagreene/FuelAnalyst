"""Regression coverage for tree-density input validation surfacing through error_handling."""

import logging

import pandas as pd
import pytest

from fuel_analyst.components.trees import (
    _calc_plot_multipliers,
    _calc_tree_density,
    _log_tree_density_issues,
    _normalize_tree_inputs,
)


@pytest.mark.regression
def test_invalid_plot_radius_zeroes_density_and_logs_instead_of_failing_silently(caplog):
    """An invalid/missing plot radius previously zeroed tree_dens_ha with no diagnostic
    at all; commit 06794a3 added tree_processing_issues.csv to surface this, which this
    test now reproduces through the centralized error_handling logger instead."""
    plots = pd.DataFrame({
        'GlobalID': ['p1'], 'unique_id': ['Unit_Plot_1_2025'],
        'lgtree_plot_radius': [None], 'smtree_plot_radius': [5.64],
        'sapling_plot_radius': [5.64],
    })
    plots = _calc_plot_multipliers(plots)
    trees = _normalize_tree_inputs(pd.DataFrame({
        'GlobalID': ['t1'], 'ParentGlobalID': ['p1'], 'tree_dbh': [20],
    }))

    density = _calc_tree_density(plots, trees)
    assert density.loc[0, 'tree_dens_ha'] == 0.0

    with caplog.at_level(logging.WARNING, logger='fuel_analyst.components.trees'):
        _log_tree_density_issues(plots, pd.DataFrame(), density)

    matching = [r for r in caplog.records if getattr(r, 'unique_id', None) == 'Unit_Plot_1_2025']
    assert len(matching) == 1
    assert matching[0].levelname == 'ERROR'
    assert matching[0].issue_code == 'missing_plot_radius'
