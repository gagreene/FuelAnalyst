"""Regression coverage for write_report() with a non-unique plot_df index.

Confirmed defect: write_report() built its identity lookup with
plot_df.set_index('unique_id')[cols].to_dict('index'), which raises
ValueError: DataFrame index must be unique for orient='index' whenever plot_df
has more than one row per unique_id. run_conpyro() passes exactly that shape
(one row per plot per weather date), so every real multi-date ConPyro run
raised at the very end and wrote no error report at all.
"""

import pandas as pd
import pytest

from fuel_analyst.components import error_handling


@pytest.mark.regression
def test_write_report_handles_duplicate_unique_ids_in_plot_df(tmp_path):
    error_handling.start_run()
    error_handling.get_logger('trees').warning(
        'Plot dropped from FOFEM mortality processing.',
        extra={'unique_id': 'A', 'issue_code': 'fofem_mortality_missing_required_column'},
    )
    # One row per plot per weather date - the shape run_conpyro.py passes.
    plot_df = pd.DataFrame({
        'unique_id': ['A', 'A', 'B'],
        'wx_date': [20250101, 20250102, 20250101],
        'treatment_area': ['Area1', 'Area1', 'Area2'],
        'plot_id': [1, 1, 2],
    })

    out_path = tmp_path / 'run_conpyro_errors.csv'
    error_handling.write_report(str(out_path), plot_df=plot_df)

    result = pd.read_csv(out_path, keep_default_na=False)
    # One row per plot with >=1 issue, not one row per plot/date pairing.
    assert len(result) == 1
    assert result.loc[0, 'unique_id'] == 'A'
    assert result.loc[0, 'treatment_area'] == 'Area1'
    assert result.loc[0, 'plot_id'] == 1
    assert result.loc[0, 'Trees'] == (
        '1. [WARNING] Plot dropped from FOFEM mortality processing.'
    )
