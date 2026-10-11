"""The default conpyro_fsg entry summarizes live conifers, as the canopy base height entries do."""

import numpy as np
import pandas as pd
import pytest

from fuel_analyst.components.trees import _calc_stand_attributes
from fuel_analyst.fuel_analyst import default_conpyro_dict


def _default_entry(name: str) -> dict:
    return default_conpyro_dict['stand_attributes'][name]


def test_default_conpyro_fsg_uses_crown_base_height_of_live_conifers() -> None:
    entry = _default_entry('conpyro_fsg')

    assert entry['att_source'] == 'cbh'
    assert entry['summary'] == ['live', 'conifer']
    assert entry['summary'] == _default_entry('conpyro_cbh_ovrstry')['summary']


def test_default_conpyro_fsg_ignores_dead_conifers_without_crown_base_height() -> None:
    """Dead conifers have no crown base height, and their basal area must not dilute the live conifer mean."""
    plot_df = pd.DataFrame({'GlobalID': ['plot-1']})
    tree_df = pd.DataFrame({
        'ParentGlobalID': ['plot-1'] * 3,
        'tree_status': ['L', 'D', 'L'],
        'tree_type': ['conifer', 'conifer', 'broadleaf'],
        'tree_dbh': [20.0, 20.0, 20.0],
        'tree_ba_ha': [10.0, 10.0, 5.0],
        'tree_cbh': [4.0, np.nan, 2.0],
        'tree_cbh_wtd': [40.0, np.nan, 10.0],
    })
    params = {name: _default_entry(name) for name in ('conpyro_cbh_ovrstry', 'conpyro_fsg')}

    result, _ = _calc_stand_attributes(plot_df, tree_df, params)

    assert result.loc[0, 'conpyro_cbh_ovrstry'] == pytest.approx(4.0)
    assert result.loc[0, 'conpyro_fsg'] == pytest.approx(4.0)
