import numpy as np
import pandas as pd
import pytest

from fuel_analyst.components import trees


def _plots(ids=('p1',), small_radius=5.64):
    return trees._calc_plot_multipliers(pd.DataFrame({
        'GlobalID': list(ids), 'unique_id': [f'plot_{value}' for value in ids],
        'lgtree_plot_radius': [11.28] * len(ids),
        'smtree_plot_radius': [small_radius] * len(ids),
        'sapling_plot_radius': [3.99] * len(ids),
    }))


@pytest.mark.parametrize('status', ['L', 'D'])
def test_sapling_source_keeps_counted_area_above_dbh_boundaries(status):
    frame = pd.DataFrame({
        'ParentGlobalID': ['p1'] * 6, 'tree_dbh': [2.5, 5.0, 13.0] * 2,
        'tree_count': [3] * 6, 'tree_status': [status] * 6,
        'tree_density_source_table': ['sapling_1.csv'] * 3 + ['tree_plot_2.csv'] * 3,
    })
    result = trees._calc_tree_density(_plots(), frame)
    assert result.tree_dens_ha.tolist() == [600, 600, 600, 600, 300, 75]
    assert result.tree_density_radius_class.tolist() == ['sapling'] * 4 + ['smtree', 'lgtree']


def test_sapling_source_preserves_invalid_dbh_and_zero_count_handling():
    frame = pd.DataFrame({
        'ParentGlobalID': ['p1'] * 2, 'tree_dbh': [np.nan, 5.0], 'tree_count': [3, 0],
        'tree_density_source_table': ['sapling_1.csv'] * 2,
    })
    result = trees._calc_tree_density(_plots(), frame)
    assert result.tree_dens_ha.tolist() == [0, 0]
    assert result.tree_density_input_valid.tolist() == [False, True]
    assert result.loc[1, 'tree_density_multiplier'] == 200
