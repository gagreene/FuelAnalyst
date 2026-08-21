"""Regression coverage for duff/litter output when the declared spp_comp_type is empty."""

import logging

import pandas as pd
import pytest

from fuel_analyst.components.woody_debris import (
    _calc_plot_duff_litter_biomass,
    _resolve_spp_comp_type,
)


@pytest.mark.regression
def test_calc_plot_duff_litter_biomass_uses_resolved_fallback_source(caplog):
    """A plot declaring 'tree_data' with no tree data previously left ffl_duff_kgpm2/
    ffl_litter_kgpm2 as NaN even though 'transect_data' was available for that plot."""
    df = pd.DataFrame({
        'unique_id': ['A'],
        'spp_comp_type': ['tree_data'],
        'stand_duff_depth_cm': [2.0],
        'stand_litter_depth_cm': [1.0],
    })
    spp_comp_df = pd.DataFrame({
        'unique_id': ['A'],
        'spp_comp_type': ['transect_data'],
        'stand_duff_bd_kgpm3': [50.0],
        'stand_litter_bd_kgpm3': [30.0],
    })
    with caplog.at_level(logging.INFO, logger='fuel_analyst.components.woody_debris'):
        df, _ = _resolve_spp_comp_type(df, spp_comp_df)
    plot_df = pd.DataFrame({'unique_id': ['A'], 'pc_flammable': [100.0]})
    result, keep = _calc_plot_duff_litter_biomass(plot_df, df, spp_comp_df)
    assert keep == ['ffl_duff_kgpm2', 'ffl_litter_kgpm2']
    assert result.loc[0, 'ffl_duff_kgpm2'] == pytest.approx(1.0)
    assert result.loc[0, 'ffl_litter_kgpm2'] == pytest.approx(0.3)
