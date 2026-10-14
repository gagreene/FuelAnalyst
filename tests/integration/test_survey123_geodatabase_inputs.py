import pandas as pd
import pytest

from .survey123_formats import COMPARED_OUTPUTS, example_dir, read_output, run_pipeline, write_forms


@pytest.mark.integration
@pytest.mark.slow
def test_geodatabase_inputs_give_the_same_pipeline_outputs_as_csv_inputs(tmp_path):
    csv_dir, gdb_dir = tmp_path / 'csv_in', tmp_path / 'gdb_in'
    write_forms(example_dir(), csv_dir, gdb_dir)
    assert not list(gdb_dir.rglob('*.csv'))

    expected = run_pipeline(csv_dir, tmp_path / 'out_csv')
    actual = run_pipeline(gdb_dir, tmp_path / 'out_gdb')

    for name in COMPARED_OUTPUTS:
        pd.testing.assert_frame_equal(read_output(actual / name), read_output(expected / name), obj=name)
