"""Regression coverage for species-composition concatenation warnings."""

import warnings

import pandas as pd
import pytest

from fuel_analyst.components.woody_debris import (
    _add_spp_comp_type,
    _assign_spp_comp_id_col,
    _merge_spp_comp,
)


@pytest.mark.regression
def test_merge_spp_comp_with_empty_manual_data_and_no_tree_data():
    plot_df = pd.DataFrame({'unique_id': ['plot-1']})
    plot_ids = pd.DataFrame({'GlobalID': ['parent-1'], 'unique_id': ['plot-1']})
    woody_df = pd.DataFrame({
        'ParentGlobalID': ['parent-1'],
        'woody_species': ['FDI'],
        'woody_spp_percent_wtd': [100.0],
    })
    manual_df = pd.DataFrame(columns=[
        'ObjectID',
        'GlobalID',
        'spp_comp_code',
        'spp_comp_percent',
        'ParentGlobalID',
    ])
    manual_df = _assign_spp_comp_id_col(plot_ids, manual_df)
    manual_df = _add_spp_comp_type(manual_df)

    with warnings.catch_warnings():
        warnings.filterwarnings(
            'error',
            category=FutureWarning,
            message='.*DataFrame concatenation with empty or all-NA entries.*',
        )
        result = _merge_spp_comp(plot_df, plot_ids, woody_df, manual_df)

    assert len(result) == 1
    assert result.loc[0, 'spp_comp_code'] == 'FDI'
    assert result.loc[0, 'spp_comp_percent'] == 100.0
    assert result.loc[0, 'spp_comp_type'] == 'transect_data'
    assert result.loc[0, 'unique_id'] == 'plot-1'


@pytest.mark.regression
def test_concat_with_populated_all_na_metadata_preserves_numeric_dtype():
    """All-NA metadata previously participated in pandas concat dtype inference."""
    from fuel_analyst.components.woody_debris import _concat_spp_comp_frames

    existing = pd.DataFrame({'spp_comp_percent': [pd.NA], 'metadata': [pd.NA]})
    incoming = pd.DataFrame({'spp_comp_percent': [100.0]})
    with warnings.catch_warnings():
        warnings.filterwarnings('error', category=FutureWarning)
        result = _concat_spp_comp_frames(existing, incoming)
    assert result.loc[1, 'spp_comp_percent'] == 100.0
    assert result['spp_comp_percent'].dtype == incoming['spp_comp_percent'].dtype
