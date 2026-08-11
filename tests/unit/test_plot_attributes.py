import pandas as pd
import pytest

from fuel_analyst.components.plot_attributes import process_plot_attributes


def test_process_plot_attributes_supports_current_survey_schema_and_converts_slope(tmp_path):
    in_dir, out_dir = tmp_path / 'input', tmp_path / 'output'
    in_dir.mkdir()
    pd.DataFrame({
        'ObjectID': [1, 2], 'GlobalID': ['a', 'b'],
        '_date': ['01/01/2025 10:00', '01/01/2025 10:00'],
        'treatment_area': ['Area', 'Area'], 'treatment_unit': ['U1', 'U1'],
        'treatment_type': ['treated', 'treated'], 'plot_id': ['1', '2'],
        'comments': ['', ''], 'plot_slope_units': ['degrees', 'percent'],
        'plot_slope': [45.0, 25.0], 'plot_slope_pct': [None, None],
        'form_select': ['trees', 'trees'], 'witness_tree_ne_present': ['no', 'no'],
    }).to_csv(in_dir / 'survey_0.csv', index=False)

    result, keep = process_plot_attributes(str(in_dir), str(out_dir))

    assert result['plot_slope_pct'].tolist() == pytest.approx([100.0, 25.0])
    assert 'treatment_unit' in keep
    assert 'ObjectID' not in keep
    assert 'witness_tree_ne_present' not in keep
    assert (out_dir / 'survey_0.csv').exists()
