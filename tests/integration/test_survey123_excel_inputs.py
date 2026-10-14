import shutil

import pandas as pd
import pytest

from .survey123_formats import (
    COMPARED_OUTPUTS, csv_form_to_workbook, example_dir, form_dirs, read_output, run_pipeline,
)


@pytest.mark.integration
@pytest.mark.slow
def test_excel_inputs_give_the_same_pipeline_outputs_as_csv_inputs(tmp_path):
    csv_dir = example_dir()
    excel_dir = tmp_path / 'excel_in'
    for form_dir in form_dirs(csv_dir):
        csv_form_to_workbook(form_dir, excel_dir / form_dir.name)
    assert not list(excel_dir.rglob('*.csv'))

    expected = run_pipeline(csv_dir, tmp_path / 'out_csv')
    actual = run_pipeline(excel_dir, tmp_path / 'out_excel')

    for name in COMPARED_OUTPUTS:
        pd.testing.assert_frame_equal(read_output(actual / name), read_output(expected / name), obj=name)


@pytest.mark.integration
@pytest.mark.slow
def test_a_mix_of_excel_and_csv_forms_gives_the_same_outputs_as_all_csv(tmp_path):
    csv_dir = example_dir()
    mixed_dir = tmp_path / 'mixed_in'
    excel_forms = {'1_Plot_Attributes', '3_Trees', '5_Woody_Debris'}
    for form_dir in form_dirs(csv_dir):
        if form_dir.name in excel_forms:
            csv_form_to_workbook(form_dir, mixed_dir / form_dir.name)
        else:
            shutil.copytree(form_dir, mixed_dir / form_dir.name)

    expected = run_pipeline(csv_dir, tmp_path / 'out_csv')
    actual = run_pipeline(mixed_dir, tmp_path / 'out_mixed')

    for name in COMPARED_OUTPUTS:
        pd.testing.assert_frame_equal(read_output(actual / name), read_output(expected / name), obj=name)
