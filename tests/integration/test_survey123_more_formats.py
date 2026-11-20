"""
Whole-pipeline checks for the GeoPackage, SQLite, GeoJSON, Parquet, and Feather input formats.

One module-scoped fixture builds GUID-mapped CSV, GeoPackage, SQLite, and GeoJSON versions of the example dataset (plus Parquet and
Feather when pyarrow is installed), runs the pipeline on each, and the tests compare the written outputs with the CSV run.
"""
from contextlib import closing
import shutil
import sqlite3

import pandas as pd
import pytest

from fuel_analyst.components import table_reader

from .survey123_formats import (
    COMPARED_OUTPUTS, csv_files, csv_form_to_workbook, example_dir, form_dirs, read_output, run_pipeline, write_formats,
)

try:
    import pyarrow  # noqa: F401
    HAS_PYARROW = True
except ImportError:
    HAS_PYARROW = False

# One format per form, so a single run reads five different formats.
ONE_FORMAT_PER_FORM = {
    '1_Plot_Attributes': 'gpkg', '2_Plants_Regeneration': 'sqlite', '3_Trees': 'parquet',
    '4_Canopy_Cover': 'feather', '5_Woody_Debris': 'excel',
}


@pytest.fixture(scope='module')
def runs(tmp_path_factory):
    tmp = tmp_path_factory.mktemp('more_formats')
    formats = ['csv', 'gpkg', 'sqlite', 'geojson'] + (['parquet', 'feather'] if HAS_PYARROW else [])
    roots = {fmt: tmp / fmt for fmt in formats}
    write_formats(example_dir(), roots)
    outputs = {fmt: run_pipeline(root, tmp / f'out_{fmt}') for fmt, root in roots.items()}

    if HAS_PYARROW:
        roots['excel'] = tmp / 'excel'
        for form_dir in form_dirs(roots['csv']):
            csv_form_to_workbook(form_dir, roots['excel'] / form_dir.name)
        mixed = tmp / 'one_format_per_form'
        for form, fmt in ONE_FORMAT_PER_FORM.items():
            shutil.copytree(roots[fmt] / form, mixed / form)
        outputs['one_format_per_form'] = run_pipeline(mixed, tmp / 'out_one_format_per_form')
    return outputs


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.parametrize('label', ['gpkg', 'sqlite', 'geojson', 'parquet', 'feather'])
def test_inputs_in_each_format_give_the_same_pipeline_outputs_as_csv(runs, label):
    if label not in runs:
        pytest.skip('Parquet and Feather need pyarrow')
    for name in COMPARED_OUTPUTS:
        pd.testing.assert_frame_equal(read_output(runs[label] / name), read_output(runs['csv'] / name), obj=name)


def test_literal_date_copy_keeps_source_text_and_parsed_date(tmp_path):
    source_date = '05/07/2021 12:00'
    with closing(sqlite3.connect(tmp_path / 'survey.sqlite')) as connection:
        pd.DataFrame({'GlobalID': ['p1'], 'CreationDate': [source_date]}).to_sql('survey_0', connection, index=False)

    result = table_reader.read_table(
        str(tmp_path), 'survey_0', literal_text_columns={'CreationDate': 'protocol_label'},
    )
    assert result.loc[0, 'CreationDate'] == pd.Timestamp('2021-05-07 12:00')
    assert result.loc[0, 'protocol_label'] == source_date


@pytest.mark.integration
@pytest.mark.slow
def test_one_run_can_read_a_different_format_for_every_form(runs):
    if 'one_format_per_form' not in runs:
        pytest.skip('Parquet and Feather need pyarrow')
    for name in COMPARED_OUTPUTS:
        pd.testing.assert_frame_equal(
            read_output(runs['one_format_per_form'] / name), read_output(runs['csv'] / name), obj=name)


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.parametrize('label', ['sqlite', 'parquet', 'feather'])
def test_processed_copies_of_the_input_tables_match_the_csv_run(runs, label):
    if label not in runs:
        pytest.skip('Parquet and Feather need pyarrow')
    assert csv_files(runs[label]) == csv_files(runs['csv'])
    for name in csv_files(runs['csv']):
        pd.testing.assert_frame_equal(read_output(runs[label] / name), read_output(runs['csv'] / name), obj=name)
