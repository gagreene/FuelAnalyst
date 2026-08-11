import pandas as pd
import pytest

from fuel_analyst.components.helper import get_unique_id


@pytest.mark.regression
def test_duplicate_survey_records_keep_latest_datetime_not_latest_date_string():
    """Raw MM/DD date strings previously sorted lexicographically."""
    rows = pd.DataFrame({
        '_date': ['01/01/2025 11:00:00 AM', '01/01/2025 01:00:00 PM'],
        'treatment_area': ['A', 'A'], 'treatment_unit': ['U', 'U'],
        'treatment_type': ['treated', 'treated'], 'plot_id': ['1', '1'],
        'value': ['older', 'newer'],
    })
    result = get_unique_id(rows)
    assert result['value'].tolist() == ['newer']


@pytest.mark.regression
def test_current_survey_schema_does_not_require_retired_treatment_field():
    row = pd.DataFrame({
        '_date': ['01/01/2025 10:00'], 'treatment_area': ['A'],
        'treatment_unit': ['U'], 'treatment_type': ['treated'], 'plot_id': ['1'],
    })
    result = get_unique_id(row)
    assert result.loc[0, 'unique_id'] == 'A_U_treated_1_2025'
