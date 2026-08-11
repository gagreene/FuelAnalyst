import pandas as pd
import pytest

from fuel_analyst.components.trees import _calc_tree_fire_attributes


@pytest.mark.regression
def test_crown_fire_char_sentinel_resolves_to_measured_tree_height():
    """Survey123 sentinel 444 must not be interpreted as a 444-metre char height."""
    result = _calc_tree_fire_attributes(
        pd.DataFrame({'tree_bark_char_high': [444.0], 'tree_ht': [12.0]}), 'Byram'
    )
    assert result.loc[0, 'tree_bark_char_high'] == 12.0
    assert result.loc[0, 'tree_flame_length'] == 21.6
