"""
Whole-pipeline checks for combinations of Survey123 input formats.

One module-scoped fixture builds the inputs (GUID-mapped CSV, Excel, and file geodatabase versions of the example dataset,
plus two combined layouts), runs the pipeline on each, and the tests compare the written outputs with the CSV run.
"""
import shutil

import pandas as pd
import pytest

from .survey123_formats import (
    COMPARED_OUTPUTS, csv_files, csv_form_to_workbook, example_dir, form_dirs, read_output, run_pipeline, write_forms,
)

# One format per form, so a single run reads Excel, geodatabase, and CSV tables.
ALL_THREE_FORMATS = {
    '1_Plot_Attributes': 'excel', '2_Plants_Regeneration': 'gdb', '3_Trees': 'csv',
    '4_Canopy_Cover': 'excel', '5_Woody_Debris': 'gdb',
}


@pytest.fixture(scope='module')
def runs(tmp_path_factory):
    tmp = tmp_path_factory.mktemp('format_combinations')
    csv_in, gdb_in, excel_in = tmp / 'csv', tmp / 'gdb', tmp / 'excel'
    write_forms(example_dir(), csv_in, gdb_in)
    for form_dir in form_dirs(csv_in):
        csv_form_to_workbook(form_dir, excel_in / form_dir.name)

    one_per_form, every_format = tmp / 'one_per_form', tmp / 'every_format'
    for form, kind in ALL_THREE_FORMATS.items():
        shutil.copytree({'csv': csv_in, 'excel': excel_in, 'gdb': gdb_in}[kind] / form, one_per_form / form)
        (every_format / form).mkdir(parents=True)
        for source in (csv_in, excel_in, gdb_in):
            for item in (source / form).iterdir():
                (shutil.copytree if item.is_dir() else shutil.copy)(item, every_format / form / item.name)

    return {
        label: run_pipeline(path, tmp / f'out_{label}')
        for label, path in (('csv', csv_in), ('excel', excel_in), ('gdb', gdb_in),
                            ('one_per_form', one_per_form), ('every_format', every_format))
    }


@pytest.mark.integration
@pytest.mark.slow
def test_one_run_can_read_all_three_formats(runs):
    for name in COMPARED_OUTPUTS:
        pd.testing.assert_frame_equal(read_output(runs['one_per_form'] / name), read_output(runs['csv'] / name), obj=name)


@pytest.mark.integration
@pytest.mark.slow
def test_a_folder_holding_all_three_formats_uses_the_csv_tables(runs):
    assert csv_files(runs['every_format']) == csv_files(runs['csv'])
    for name in csv_files(runs['csv']):
        pd.testing.assert_frame_equal(read_output(runs['every_format'] / name), read_output(runs['csv'] / name), obj=name)


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.parametrize('label', ['excel', 'gdb'])
def test_processed_copies_of_the_input_tables_match_the_csv_run(runs, label):
    # Every CSV the run writes, including the processed copies of the input tables, matches the CSV run. The one allowed
    # difference: the example plants form has no x and y columns, while a geodatabase supplies them from point geometry.
    assert csv_files(runs[label]) == csv_files(runs['csv'])
    for name in csv_files(runs['csv']):
        actual, expected = read_output(runs[label] / name), read_output(runs['csv'] / name)
        if label == 'gdb' and name.replace('\\', '/') == '2_Plants_Regeneration/survey_0.csv':
            assert {'x', 'y'} <= set(actual.columns) - set(expected.columns)
            actual = actual.drop(columns=['x', 'y'])
        pd.testing.assert_frame_equal(actual, expected, obj=name)
