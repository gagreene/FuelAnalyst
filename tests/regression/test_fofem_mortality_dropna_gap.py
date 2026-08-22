"""Regression coverage for the FOFEM mortality required-column dropna gap."""

import logging
import sys
import types

import numpy as np
import pandas as pd
import pytest

if 'pyfofem' not in sys.modules:
    fake_package = types.ModuleType('pyfofem')
    fake_package.pyfofem = types.SimpleNamespace()
    sys.modules['pyfofem'] = fake_package

from fuel_analyst.components import fofem_mortality


@pytest.mark.regression
def test_dropna_no_longer_silently_drops_plot_with_one_missing_required_column(caplog):
    """dropna(subset=filtered_required_cols) previously removed a plot row with a NaN
    in a required column with zero warning whenever most required columns existed -
    the printed message only fired when NONE of the required columns existed at all."""
    plot_fire_df = pd.DataFrame({
        'unique_id': ['A', 'B'],
        'instand_ws_mps': [1.0, np.nan],
        'canopy_cover': [50.0, 50.0],
        'ht_ovrstry_live': [20.0, 20.0],
        'fsg': [1.0, 1.0], 'ws': [1.0, 1.0], 'hfi': [1.0, 1.0],
        'fire_type': ['surface', 'surface'], 'temp': [20.0, 20.0],
    })
    required_cols = [
        'instand_ws_mps', 'canopy_cover', 'ht_ovrstry_live', 'fsg', 'ws', 'hfi', 'fire_type', 'temp',
    ]
    filtered_required_cols = [c for c in required_cols if c in plot_fire_df.columns]

    with caplog.at_level(logging.WARNING, logger='fuel_analyst.components.fofem_mortality'):
        result = fofem_mortality._log_and_drop_incomplete_rows(
            plot_fire_df, filtered_required_cols, 'unique_id'
        )

    assert result['unique_id'].tolist() == ['A']
    matching = [r for r in caplog.records if getattr(r, 'unique_id', None) == 'B']
    assert len(matching) == 1
    assert matching[0].issue_code == 'fofem_mortality_missing_required_column'
