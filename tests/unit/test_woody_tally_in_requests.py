"""Tallied fines are included in every output class that holds the tallied size class."""

import numpy as np
import pandas as pd
import pytest

from fuel_analyst.components.woody_debris import _calc_plot_woody_debris


def _plots() -> pd.DataFrame:
    return pd.DataFrame({
        'GlobalID': ['p1', 'p2', 'p3'],
        'woody_kgpm2_test_0_5': [0.2, 0.3, np.nan],   # tallied fines of the 0.5 cm class
    })


def _pieces() -> pd.DataFrame:
    return pd.DataFrame({
        'ParentGlobalID': ['p1', 'p1', 'p1', 'p2', 'p3'],
        'woody_diam_cm': [2.0, 2.5, 5.0, 5.0, 2.0],
        'woody_mass_kgpm2': [1.0, 0.5, 4.0, 2.0, 1.0],
        'woody_decay': [1, 5, 1, 1, 1],
    })


def _params(output_request: list) -> dict:
    return {'woody_debris_classes': {'test': {
        'process_classes': True, 'class_extension': 'test',
        'diameter_cutoffs': [0.5, 1, 3], 'output_request': output_request,
    }}}


def test_unfiltered_requests_include_the_tally_whatever_their_position() -> None:
    request = [
        ['default', {}, [0, 0.5, 1, 3, float('inf')]],
        ['lt3cm', {}, [0, 3]],
        ['coarse', {}, [3, float('inf')]],
    ]

    result, _ = _calc_plot_woody_debris(_plots(), _pieces(), _params(request))

    # The second request holds the tallied class, so it gets the tally: measured 1.0 + 0.5 plus tally 0.2
    assert result['woody_kgpm2_test_lt3cm_3'].iloc[0] == pytest.approx(1.7)
    # No measured pieces up to 3 cm on p2: the tally alone, not a missing value
    assert result['woody_kgpm2_test_lt3cm_3'].iloc[1] == pytest.approx(0.3)
    # No tally on p3: the measured mass alone, not a missing value
    assert result['woody_kgpm2_test_lt3cm_3'].iloc[2] == pytest.approx(1.0)
    # A class above the tallied size class never gets the tally
    assert result['woody_kgpm2_test_coarse_gt3'].tolist()[:2] == pytest.approx([4.0, 2.0])


def test_lt7cm_style_class_equals_the_sum_of_the_default_classes() -> None:
    request = [
        ['default', {}, [0, 0.5, 1, 3, float('inf')]],
        ['lt3cm', {}, [0, 3]],
    ]

    result, _ = _calc_plot_woody_debris(_plots(), _pieces(), _params(request))

    parts = ['woody_kgpm2_test_default_0_5', 'woody_kgpm2_test_default_1', 'woody_kgpm2_test_default_3']
    summed = result[parts].fillna(0).sum(axis=1)
    assert result['woody_kgpm2_test_lt3cm_3'].tolist()[:2] == pytest.approx(summed.tolist()[:2])


def test_requests_filtered_on_decay_give_the_tally_to_the_first_only() -> None:
    """The tally has no decay class, so sound and rotten classes must not both count it."""
    request = [
        ['sound', {'woody_decay': '<=3'}, [0, 0.5, 3]],
        ['rotten', {'woody_decay': '>3'}, [0, 0.5, 3]],
        ['sound_all', {'woody_decay': '<=3'}, [0, 3]],
    ]

    result, _ = _calc_plot_woody_debris(_plots(), _pieces(), _params(request))

    assert result['woody_kgpm2_test_sound_0_5'].tolist()[:2] == pytest.approx([0.2, 0.3])
    assert result['woody_kgpm2_test_rotten_0_5'].isna().all()
    # A later filtered request is not the first, so it stays measured only
    assert result['woody_kgpm2_test_sound_all_3'].iloc[0] == pytest.approx(1.0)
