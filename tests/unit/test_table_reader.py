import datetime
import os
import shutil

import openpyxl
import pandas as pd
import pytest

from fuel_analyst.components import helper, table_reader
from fuel_analyst.components.table_reader import FormSource

EXAMPLE_TREES_DIR = os.path.join(
    os.path.dirname(__file__), '..', '..', 'examples', 'data', 'Survey123_Data', '3_Trees'
)


def _write_form(folder, tables):
    folder.mkdir(parents=True, exist_ok=True)
    for stem, df in tables.items():
        df.to_csv(folder / f'{stem}.csv', index=False)
    return folder


def test_ensure_form_source_converts_a_missing_folder_without_raising(tmp_path):
    source = table_reader.ensure_form_source(str(tmp_path / 'absent'))

    assert source.kind == 'csv_folder'
    assert source.path == str(tmp_path / 'absent')
    assert source.tables == ()


def test_ensure_form_source_returns_an_existing_source_unchanged(tmp_path):
    source = FormSource(kind='csv_folder', path=str(tmp_path), tables=('survey_0',))

    assert table_reader.ensure_form_source(source) is source


def test_form_exists_follows_resolve_form_source(tmp_path):
    _write_form(tmp_path / '3_Trees', {'survey_0': pd.DataFrame({'a': [1]})})

    assert table_reader.form_exists(str(tmp_path), '3_Trees')
    assert not table_reader.form_exists(str(tmp_path), '4_Canopy_Cover')


def test_has_table_checks_the_named_table(tmp_path):
    folder = _write_form(tmp_path, {'survey_0': pd.DataFrame({'a': [1]})})
    source = table_reader.ensure_form_source(str(folder))

    assert table_reader.has_table(source, 'survey_0')
    assert not table_reader.has_table(source, 't2_woody_3')


def test_read_table_matches_the_standard_csv_reader(tmp_path):
    df = pd.DataFrame({'ObjectID': [5, 9], 'plot_id': ['P01', 'P02'], 'value': [1.5, None]})
    folder = _write_form(tmp_path, {'survey_0': df})

    expected = helper.get_df(str(folder / 'survey_0.csv'))
    pd.testing.assert_frame_equal(table_reader.read_table(str(folder), 'survey_0'), expected)
    pd.testing.assert_frame_equal(
        table_reader.read_table(table_reader.ensure_form_source(str(folder)), 'survey_0'),
        expected,
    )


def test_read_table_missing_required_table_raises_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        table_reader.read_table(str(tmp_path), 'survey_0')


def test_read_table_missing_optional_table_returns_none(tmp_path):
    assert table_reader.read_table(str(tmp_path), 't2_woody_3', required=False) is None


def test_resolve_form_source_lists_the_csv_tables_sorted(tmp_path):
    _write_form(tmp_path / '5_Woody_Debris', {
        't1_woody_2': pd.DataFrame({'a': [1]}),
        'survey_0': pd.DataFrame({'a': [1]}),
    })
    (tmp_path / '5_Woody_Debris' / 'notes.txt').write_text('not a table')

    source = table_reader.resolve_form_source(str(tmp_path), '5_Woody_Debris')

    assert source == FormSource(
        kind='csv_folder', path=str(tmp_path / '5_Woody_Debris'), tables=('survey_0', 't1_woody_2')
    )


def test_resolve_form_source_returns_none_for_an_absent_form(tmp_path):
    assert table_reader.resolve_form_source(str(tmp_path), '3_Trees') is None


def test_woody_transects_accept_a_resolved_source_and_a_folder_path(tmp_path):
    from fuel_analyst.components.woody_debris import _get_merged_woody_df

    folder = _write_form(tmp_path, {
        't1_woody_2': pd.DataFrame({'t1_woody_count': [3]}),
        't2_woody_3': pd.DataFrame({'t2_woody_count': [4]}),
    })

    from_path = _get_merged_woody_df(str(folder))
    from_source = _get_merged_woody_df(table_reader.ensure_form_source(str(folder)))

    pd.testing.assert_frame_equal(from_path, from_source)
    assert from_path['transect_id'].tolist() == [1, 2]
    assert from_path['woody_count'].tolist() == [3, 4]


def test_example_form_reads_identically_through_the_source_reader():
    source = table_reader.resolve_form_source(os.path.dirname(EXAMPLE_TREES_DIR), '3_Trees')

    assert source is not None
    assert {'survey_0', 'sapling_1', 'tree_plot_2'} <= set(source.tables)
    expected = pd.read_csv(
        os.path.join(EXAMPLE_TREES_DIR, 'tree_plot_2.csv'), header=0, index_col=False, low_memory=False
    )
    pd.testing.assert_frame_equal(table_reader.read_table(source, 'tree_plot_2'), expected)


def test_non_survey123_reads_still_use_the_plain_csv_helper(tmp_path):
    # Reference tables, weather files, and FOFEM outputs are read with helper.get_df and are not
    # routed through the Survey123 reader.
    path = tmp_path / 'weather.csv'
    pd.DataFrame({'unique_id': ['a'], 'temp': [20.0]}).to_csv(path, index=False)

    assert helper.get_df(str(path)).to_dict('records') == [{'unique_id': 'a', 'temp': 20.0}]


def _write_workbook(path, tables):
    """Write an ArcGIS-style workbook: one sheet per table, header in row 1, datetimes as date cells."""
    book = openpyxl.Workbook()
    book.remove(book.active)
    for stem, df in tables.items():
        sheet = book.create_sheet(stem)
        sheet.append(list(df.columns))
        for row in df.itertuples(index=False):
            sheet.append([None if pd.isna(v) else (v.to_pydatetime() if isinstance(v, pd.Timestamp) else
                                                   (v.item() if hasattr(v, 'item') else v)) for v in row])
    book.save(path)
    return path


SURVEY = pd.DataFrame({
    'ObjectID': [757, 758, 760],
    'GlobalID': ['7a869465-506b-4a1a-a6a1-339f29d58006', 'f1c3301b-2caf-4b82-8401-444b15cff916', None],
    '_date': pd.to_datetime(['2026-09-21 19:00:00', '2026-09-21 19:00:00', '2026-09-22 08:30:00']),
    'plot_id': ['GTUF3', 'GTUF4', 'GTUF5'],
    'code': ['1', '2', '1'],
    'height': [12.5, None, 9.0],
})


def test_resolve_form_source_finds_a_workbook_with_its_sheets(tmp_path):
    folder = tmp_path / '3_Trees'
    folder.mkdir()
    workbook = _write_workbook(folder / 'S123_abc_EXCEL.xlsx', {
        'survey_0': SURVEY, 'tree_plot_2': SURVEY.iloc[:1],
    })

    source = table_reader.resolve_form_source(str(tmp_path), '3_Trees')

    assert source.kind == 'workbook'
    assert source.path == str(folder)
    assert source.tables == ('survey_0', 'tree_plot_2')
    assert source.files == (str(workbook),)
    assert table_reader.has_table(source, 'tree_plot_2')
    assert not table_reader.has_table(source, 'sapling_1')


def test_csv_tables_are_used_before_an_excel_workbook(tmp_path):
    _write_form(tmp_path, {'survey_0': pd.DataFrame({'a': [1]})})
    _write_workbook(tmp_path / 'S123_abc_EXCEL.xlsx', {'survey_0': pd.DataFrame({'a': [2]})})

    source = table_reader.ensure_form_source(str(tmp_path))

    assert source.kind == 'csv_folder'
    assert table_reader.read_table(source, 'survey_0')['a'].tolist() == [1]


def test_excel_lock_files_are_ignored(tmp_path):
    _write_workbook(tmp_path / 'S123_abc_EXCEL.xlsx', {'survey_0': SURVEY})
    (tmp_path / '~$S123_abc_EXCEL.xlsx').write_bytes(b'lock file, not a workbook')

    source = table_reader.ensure_form_source(str(tmp_path))

    assert source.kind == 'workbook'
    assert [os.path.basename(f) for f in source.files] == ['S123_abc_EXCEL.xlsx']


def test_xlsm_workbooks_are_read(tmp_path):
    workbook = _write_workbook(tmp_path / 'form.xlsx', {'survey_0': SURVEY})
    shutil.copy(workbook, tmp_path / 'macro_book.xlsm')
    os.remove(workbook)

    source = table_reader.ensure_form_source(str(tmp_path))

    assert source.kind == 'workbook'
    assert table_reader.read_table(source, 'survey_0').shape == (3, 6)


def test_workbook_table_reads_like_the_equivalent_csv(tmp_path):
    csv_folder = tmp_path / 'csv'
    xlsx_folder = tmp_path / 'xlsx'
    xlsx_folder.mkdir()
    csv_df = SURVEY.copy()
    csv_df['_date'] = csv_df['_date'].dt.strftime('%m/%d/%Y %H:%M')
    _write_form(csv_folder, {'survey_0': csv_df})
    _write_workbook(xlsx_folder / 'S123_abc_EXCEL.xlsx', {'survey_0': SURVEY})

    from_csv = table_reader.read_table(str(csv_folder), 'survey_0')
    from_xlsx = table_reader.read_table(str(xlsx_folder), 'survey_0')

    assert list(from_xlsx.columns) == list(from_csv.columns)
    # Text cells that hold only numbers become numbers, exactly as in a CSV file.
    assert str(from_xlsx['code'].dtype) == str(from_csv['code'].dtype) == 'int64'
    for column in from_csv.columns.drop('_date'):
        pd.testing.assert_series_equal(from_xlsx[column], from_csv[column], check_names=False)
    # Dates stay datetimes, and get_unique_id accepts them.
    assert pd.api.types.is_datetime64_any_dtype(from_xlsx['_date'])
    assert from_xlsx['_date'].tolist() == SURVEY['_date'].tolist()


def test_workbook_dates_give_the_same_unique_ids_as_csv_text(tmp_path):
    parent = pd.DataFrame({
        'treatment_area': ['Demo'], 'treatment_unit': ['TU1'], 'treatment_type': ['burned'], 'plot_id': ['P04'],
        '_date': pd.to_datetime(['2021-10-26 12:00:00']),
    })
    _write_workbook(tmp_path / 'S123_abc_EXCEL.xlsx', {'survey_0': parent})
    csv_parent = parent.assign(_date=['10/26/2021 12:00'])
    _write_form(tmp_path / 'csv', {'survey_0': csv_parent})

    from_xlsx = helper.get_unique_id(table_reader.read_table(str(tmp_path), 'survey_0'))
    from_csv = helper.get_unique_id(table_reader.read_table(str(tmp_path / 'csv'), 'survey_0'))

    assert from_xlsx['unique_id'].tolist() == from_csv['unique_id'].tolist() == ['Demo_TU1_burned_P04_2021']


def test_header_only_sheet_returns_an_empty_table_with_its_columns(tmp_path):
    empty = pd.DataFrame(columns=['ObjectID', 'GlobalID', 'spp_comp_code', 'spp_comp_percent'])
    _write_workbook(tmp_path / 'S123_abc_EXCEL.xlsx', {'survey_0': SURVEY, 'spp_comp_manual_1': empty})

    result = table_reader.read_table(str(tmp_path), 'spp_comp_manual_1')

    assert result.empty
    assert list(result.columns) == list(empty.columns)


def test_missing_sheet_raises_or_returns_none_when_optional(tmp_path):
    _write_workbook(tmp_path / 'S123_abc_EXCEL.xlsx', {'survey_0': SURVEY})
    source = table_reader.ensure_form_source(str(tmp_path))

    with pytest.raises(FileNotFoundError, match='t2_woody_3'):
        table_reader.read_table(source, 't2_woody_3')
    assert table_reader.read_table(source, 't2_woody_3', required=False) is None


def test_a_sheet_in_two_workbooks_is_an_error_naming_both(tmp_path):
    _write_workbook(tmp_path / 'first_EXCEL.xlsx', {'survey_0': SURVEY})
    _write_workbook(tmp_path / 'second_EXCEL.xlsx', {'survey_0': SURVEY})
    source = table_reader.ensure_form_source(str(tmp_path))

    with pytest.raises(ValueError, match='first_EXCEL.xlsx, second_EXCEL.xlsx'):
        table_reader.read_table(source, 'survey_0')


def test_different_sheets_in_two_workbooks_are_both_available(tmp_path):
    _write_workbook(tmp_path / 'a_EXCEL.xlsx', {'survey_0': SURVEY})
    _write_workbook(tmp_path / 'b_EXCEL.xlsx', {'tree_plot_2': SURVEY.iloc[:2]})
    source = table_reader.ensure_form_source(str(tmp_path))

    assert source.tables == ('survey_0', 'tree_plot_2')
    assert len(table_reader.read_table(source, 'tree_plot_2')) == 2


def test_an_unreadable_workbook_gives_a_clear_error(tmp_path):
    (tmp_path / 'broken_EXCEL.xlsx').write_bytes(b'this is not a zip archive')

    with pytest.raises(ValueError, match='Cannot open Excel workbook'):
        table_reader.ensure_form_source(str(tmp_path))


def test_excel_dates_are_datetimes_not_text(tmp_path):
    _write_workbook(tmp_path / 'S123_abc_EXCEL.xlsx', {'survey_0': SURVEY})

    result = table_reader.read_table(str(tmp_path), 'survey_0')

    assert result['_date'].iloc[2] == pd.Timestamp(datetime.datetime(2026, 9, 22, 8, 30))
