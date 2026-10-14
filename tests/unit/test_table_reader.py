import contextlib
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


def _write_gdb(path, layers):
    """
    Write an ArcGIS-style file geodatabase.

    :param layers: {layer: (DataFrame, xy)}; the DataFrame needs an 'objectid' column (the FID); xy is a
        (x, y) pair of lists for a Point layer named SHAPE, or None for a table.
    """
    import geopandas as gpd
    import pyogrio
    for name, (df, xy) in layers.items():
        # ArcGIS fields are 32-bit; GDAL warns when asked to write 64-bit integers.
        df = df.astype({c: 'int32' for c in df.columns if str(df[c].dtype) == 'int64'})
        if xy is None:
            pyogrio.write_dataframe(df, str(path), layer=name, driver='OpenFileGDB', layer_options={'FID': 'objectid'})
            continue
        gdf = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(*xy), crs='EPSG:4326')
        gdf.geometry.name = 'SHAPE'
        pyogrio.write_dataframe(gdf, str(path), layer=name, driver='OpenFileGDB', geometry_type='Point',
                                layer_options={'FID': 'objectid', 'GEOMETRY_NAME': 'SHAPE'})
    return path


GDB_SURVEY = pd.DataFrame({
    'objectid': [717, 725, 760],
    'globalid': ['{4DB55FC8-C839-4C25-93B6-B73180C39247}', '{8CA667E4-11C3-41CA-AEB9-4A50A6E83FB3}', None],
    '_date': pd.to_datetime(['2026-09-21 19:00:00', '2026-09-21 19:00:00', '2026-09-22 08:30:00']).tz_localize('UTC'),
    'plot_id': ['GTUF3', 'GTUF4', 'GTUF5'],
    'tree_dbh': pd.Series([33.1, None, 12.7], dtype='float32'),
    'count': pd.Series([1, 2, None], dtype='Int32'),
})
GDB_TREES = pd.DataFrame({
    'objectid': [13502, 13509],
    'globalid': ['{5B8D3AB3-BDAB-4203-9FBB-02BC9B321486}', '{7DE0DEC5-247C-4A3A-963A-F411A6C1C691}'],
    'tree_id': [1, 2],
    'parentglobalid': ['{4DB55FC8-C839-4C25-93B6-B73180C39247}', '{8CA667E4-11C3-41CA-AEB9-4A50A6E83FB3}'],
})


def test_resolve_form_source_finds_a_geodatabase_in_the_form_folder_and_one_folder_below(tmp_path):
    direct = tmp_path / 'direct'
    nested = tmp_path / 'nested' / 'S123_abc_FGDB'
    direct.mkdir()
    nested.mkdir(parents=True)
    layers = {'survey': (GDB_SURVEY, ([-122.7, 0.0, -121.0], [50.3, 0.0, 49.9])), 'tree_plot': (GDB_TREES, None)}
    _write_gdb(direct / '533e7d23-a00e.gdb', layers)
    _write_gdb(nested / '9f4829a6-b6e6.gdb', layers)

    for folder, relative in ((direct, '533e7d23-a00e.gdb'), (tmp_path / 'nested', os.path.join('S123_abc_FGDB', '9f4829a6-b6e6.gdb'))):
        source = table_reader.ensure_form_source(str(folder))
        assert source.kind == 'gdb'
        assert source.tables == ('survey', 'tree_plot')
        assert source.files == (str(folder / relative),)
        assert table_reader.has_table(source, 'survey_0')
        assert table_reader.has_table(source, 'tree_plot_2')
        assert not table_reader.has_table(source, 'sapling_1')


def test_excel_is_used_before_a_geodatabase_and_csv_before_both(tmp_path):
    _write_gdb(tmp_path / 'a.gdb', {'survey': (GDB_SURVEY, ([0.0] * 3, [0.0] * 3))})
    _write_workbook(tmp_path / 'S123_abc_EXCEL.xlsx', {'survey_0': SURVEY})
    assert table_reader.ensure_form_source(str(tmp_path)).kind == 'workbook'

    _write_form(tmp_path, {'survey_0': pd.DataFrame({'a': [1]})})
    assert table_reader.ensure_form_source(str(tmp_path)).kind == 'csv_folder'


def test_geodatabase_layer_reads_like_the_csv_table(tmp_path):
    _write_gdb(tmp_path / 'a.gdb', {'survey': (GDB_SURVEY, ([-122.7, 0.0, -121.0], [50.3, 0.0, 49.9]))})

    result = table_reader.read_table(str(tmp_path), 'survey_0')

    assert list(result.columns) == ['ObjectID', 'GlobalID', '_date', 'plot_id', 'tree_dbh', 'count', 'x', 'y']
    assert 'geometry' not in result.columns and 'SHAPE' not in result.columns
    # The layer FID is the object ID and keeps its non-consecutive values.
    assert result['ObjectID'].tolist() == [717, 725, 760]
    # GUIDs are lower case without braces, as in the CSV; a missing GUID stays missing.
    assert result['GlobalID'].iloc[:2].tolist() == ['4db55fc8-c839-4c25-93b6-b73180c39247', '8ca667e4-11c3-41ca-aeb9-4a50a6e83fb3']
    assert pd.isna(result['GlobalID'].iloc[2])
    # UTC dates become naive datetimes with the same wall-clock value.
    assert result['_date'].tolist() == GDB_SURVEY['_date'].dt.tz_localize(None).tolist()
    assert result['_date'].dt.tz is None
    # A 32-bit float comes back with its short decimal form, not as 33.099998.
    assert result['tree_dbh'].iloc[0] == 33.1
    assert result['tree_dbh'].dtype == 'float64'
    assert result['count'].dtype == 'float64'
    assert result['count'].iloc[:2].tolist() == [1.0, 2.0]
    assert result[['x', 'y']].iloc[0].tolist() == pytest.approx([-122.7, 50.3])


def test_geodatabase_coordinate_noise_is_snapped_to_zero(tmp_path):
    _write_gdb(tmp_path / 'a.gdb', {'survey': (GDB_SURVEY, ([5.684341886080803e-14, -122.7, 0.0], [5.684341886080803e-14, 50.3, 0.0]))})

    result = table_reader.read_table(str(tmp_path), 'survey_0')

    assert result['x'].iloc[0] == 0.0 and result['y'].iloc[0] == 0.0
    assert result['x'].iloc[1] == pytest.approx(-122.7)


def test_geodatabase_layer_keeps_x_and_y_fields_when_it_has_them(tmp_path):
    with_xy = GDB_SURVEY.assign(x=[1.0, 2.0, 3.0], y=[4.0, 5.0, 6.0])
    _write_gdb(tmp_path / 'a.gdb', {'survey': (with_xy, ([9.0] * 3, [9.0] * 3))})

    result = table_reader.read_table(str(tmp_path), 'survey_0')

    assert result['x'].tolist() == [1.0, 2.0, 3.0]
    assert list(result.columns).count('x') == 1


def test_geodatabase_repeat_table_has_parent_ids_and_no_coordinates(tmp_path):
    _write_gdb(tmp_path / 'a.gdb', {'tree_plot': (GDB_TREES, None)})

    result = table_reader.read_table(str(tmp_path), 'tree_plot_2')

    assert list(result.columns) == ['ObjectID', 'GlobalID', 'tree_id', 'ParentGlobalID']
    assert result['ObjectID'].tolist() == [13502, 13509]
    assert result['ParentGlobalID'].tolist() == ['4db55fc8-c839-4c25-93b6-b73180c39247', '8ca667e4-11c3-41ca-aeb9-4a50a6e83fb3']


def test_empty_geodatabase_table_keeps_its_columns(tmp_path):
    empty = pd.DataFrame({'objectid': pd.Series([], dtype='int64'), 'globalid': pd.Series([], dtype=object),
                          'spp_comp_code': pd.Series([], dtype=object), 'spp_comp_percent': pd.Series([], dtype='float64')})
    _write_gdb(tmp_path / 'a.gdb', {'spp_comp_manual': (empty, None)})

    result = table_reader.read_table(str(tmp_path), 'spp_comp_manual_1')

    assert result.empty
    assert list(result.columns) == ['ObjectID', 'GlobalID', 'spp_comp_code', 'spp_comp_percent']


def test_missing_geodatabase_layer_raises_or_returns_none_when_optional(tmp_path):
    _write_gdb(tmp_path / 'a.gdb', {'tree_plot': (GDB_TREES, None)})
    source = table_reader.ensure_form_source(str(tmp_path))

    with pytest.raises(FileNotFoundError, match='t2_woody'):
        table_reader.read_table(source, 't2_woody_3')
    assert table_reader.read_table(source, 't2_woody_3', required=False) is None


def test_a_layer_in_two_geodatabases_is_an_error_naming_both(tmp_path):
    _write_gdb(tmp_path / 'first.gdb', {'tree_plot': (GDB_TREES, None)})
    _write_gdb(tmp_path / 'second.gdb', {'tree_plot': (GDB_TREES, None)})
    source = table_reader.ensure_form_source(str(tmp_path))

    with pytest.raises(ValueError, match='first.gdb, second.gdb'):
        table_reader.read_table(source, 'tree_plot_2')


def test_a_zipped_download_without_tables_says_to_unzip_it(tmp_path):
    (tmp_path / 'S123_abc_FGDB.zip').write_bytes(b'PK')

    with pytest.raises(ValueError, match='Unzip it first'):
        table_reader.ensure_form_source(str(tmp_path))


def test_a_zip_next_to_usable_tables_is_ignored(tmp_path):
    _write_form(tmp_path, {'survey_0': pd.DataFrame({'a': [1]})})
    (tmp_path / 'S123_abc_FGDB.zip').write_bytes(b'PK')

    assert table_reader.ensure_form_source(str(tmp_path)).kind == 'csv_folder'


def test_an_unreadable_geodatabase_gives_a_clear_error(tmp_path):
    broken = tmp_path / 'broken.gdb'
    broken.mkdir()
    (broken / 'a00000001.gdbtable').write_bytes(b'not a geodatabase table')

    with pytest.raises(ValueError, match='Cannot open broken.gdb'):
        table_reader.ensure_form_source(str(tmp_path))


# ---------------------------------------------------------------- GeoPackage, SQLite, Parquet, and Feather

def _write_gpkg(path, layers):
    """Write a GeoPackage: {layer: (DataFrame with an 'fid' column, xy or None)}; xy is (x list, y list) for a Point layer."""
    import geopandas as gpd
    import pyogrio
    for name, (df, xy) in layers.items():
        df = df.astype({c: 'int32' for c in df.columns if str(df[c].dtype) == 'int64'})
        if xy is None:
            pyogrio.write_dataframe(df, str(path), layer=name, driver='GPKG', layer_options={'FID': 'fid'})
            continue
        gdf = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(*xy), crs='EPSG:4326')
        pyogrio.write_dataframe(gdf, str(path), layer=name, driver='GPKG', geometry_type='Point', layer_options={'FID': 'fid'})
    return path


def _write_sqlite(path, tables):
    """Write plain SQLite tables: {table: DataFrame}; datetimes are stored as ISO text, as SQLite does."""
    import sqlite3
    with contextlib.closing(sqlite3.connect(path)) as connection:
        for name, df in tables.items():
            df = df.copy()
            for column in df.columns:
                if pd.api.types.is_datetime64_any_dtype(df[column]):
                    df[column] = df[column].dt.strftime('%Y-%m-%d %H:%M:%S')
            df.to_sql(name, connection, index=False)
    return path


GPKG_SURVEY = GDB_SURVEY.rename(columns={'objectid': 'fid'})
GPKG_TREES = GDB_TREES.rename(columns={'objectid': 'fid'})


def test_geopackage_layers_read_like_the_csv_tables(tmp_path):
    _write_gpkg(tmp_path / 'trees_form.gpkg', {
        'survey': (GPKG_SURVEY, ([-122.7, 0.0, -121.0], [50.3, 0.0, 49.9])), 'tree_plot': (GPKG_TREES, None),
    })

    source = table_reader.ensure_form_source(str(tmp_path))
    survey = table_reader.read_table(source, 'survey_0')
    trees = table_reader.read_table(source, 'tree_plot_2')

    assert source.kind == 'gpkg'
    assert source.tables == ('survey', 'tree_plot')
    assert list(survey.columns) == ['ObjectID', 'GlobalID', '_date', 'plot_id', 'tree_dbh', 'count', 'x', 'y']
    assert survey['ObjectID'].tolist() == [717, 725, 760]
    assert survey['GlobalID'].iloc[0] == '4db55fc8-c839-4c25-93b6-b73180c39247'
    assert survey['tree_dbh'].iloc[0] == 33.1
    assert survey['_date'].dt.tz is None
    assert list(trees.columns) == ['ObjectID', 'GlobalID', 'tree_id', 'ParentGlobalID']
    assert trees['ObjectID'].tolist() == [13502, 13509]


def test_an_objectid_field_wins_over_the_row_id(tmp_path):
    # Editing in QGIS or ArcGIS Pro renumbers the row IDs (fid) but keeps an ObjectID field.
    edited = GPKG_TREES.assign(ObjectID=[500, 501])
    _write_gpkg(tmp_path / 'form.gpkg', {'tree_plot': (edited, None)})

    result = table_reader.read_table(str(tmp_path), 'tree_plot_2')

    assert list(result.columns)[0] == 'ObjectID'
    assert result['ObjectID'].tolist() == [500, 501]
    assert list(result.columns).count('ObjectID') == 1


def test_containers_match_a_table_with_or_without_its_number_ignoring_case(tmp_path):
    _write_workbook(tmp_path / 'form_EXCEL.xlsx', {'Survey': SURVEY, 'tree_plot_2': SURVEY.iloc[:1]})
    source = table_reader.ensure_form_source(str(tmp_path))

    assert table_reader.has_table(source, 'survey_0')
    assert table_reader.has_table(source, 'tree_plot_2')
    assert len(table_reader.read_table(source, 'survey_0')) == 3


def test_plain_sqlite_tables_read_like_the_csv_tables(tmp_path):
    plain = SURVEY.assign(x=[-122.7, 0.0, -121.0], y=[50.3, 0.0, 49.9])
    _write_sqlite(tmp_path / 'form.sqlite', {'survey_0': plain, 'tree_plot': GDB_TREES.drop(columns='objectid')})

    source = table_reader.ensure_form_source(str(tmp_path))
    survey = table_reader.read_table(source, 'survey_0')

    assert source.kind == 'sqlite'
    assert source.tables == ('survey_0', 'tree_plot')
    assert table_reader.has_table(source, 'tree_plot_2')
    # SQLite keeps dates as text, so they are parsed back into datetimes, and the other columns read like a CSV.
    assert survey['_date'].tolist() == SURVEY['_date'].tolist()
    assert survey['code'].dtype == 'int64'
    assert survey['height'].isna().tolist() == [False, True, False]
    assert survey['x'].tolist() == [-122.7, 0.0, -121.0]
    assert 'sqlite_sequence' not in source.tables


def test_sqlite_dates_give_the_same_unique_ids_as_csv_text(tmp_path):
    parent = pd.DataFrame({
        'treatment_area': ['Demo'], 'treatment_unit': ['TU1'], 'treatment_type': ['burned'], 'plot_id': ['P04'],
        '_date': pd.to_datetime(['2021-10-26 12:00:00']),
    })
    _write_sqlite(tmp_path / 'form.db', {'survey_0': parent})

    result = helper.get_unique_id(table_reader.read_table(str(tmp_path), 'survey_0'))

    assert result['unique_id'].tolist() == ['Demo_TU1_burned_P04_2021']


def test_a_sqlite_file_holding_geopackage_tables_is_read_as_a_geopackage(tmp_path):
    _write_gpkg(tmp_path / 'form.gpkg', {'tree_plot': (GPKG_TREES, None)})
    os.rename(tmp_path / 'form.gpkg', tmp_path / 'form.sqlite')

    source = table_reader.ensure_form_source(str(tmp_path))

    assert source.kind == 'gpkg'
    assert table_reader.read_table(source, 'tree_plot_2')['ObjectID'].tolist() == [13502, 13509]


def test_a_table_in_two_geopackages_or_two_sqlite_files_is_an_error_naming_both(tmp_path):
    for name in ('first.gpkg', 'second.gpkg'):
        _write_gpkg(tmp_path / name, {'tree_plot': (GPKG_TREES, None)})
    with pytest.raises(ValueError, match='first.gpkg, second.gpkg'):
        table_reader.read_table(str(tmp_path), 'tree_plot_2')

    other = tmp_path / 'sql'
    other.mkdir()
    for name in ('one.sqlite', 'two.sqlite'):
        _write_sqlite(other / name, {'survey_0': SURVEY})
    with pytest.raises(ValueError, match='one.sqlite, two.sqlite'):
        table_reader.read_table(str(other), 'survey_0')


def test_an_unreadable_sqlite_or_geopackage_file_gives_a_clear_error(tmp_path):
    (tmp_path / 'broken.sqlite').write_bytes(b'this is not a database')

    with pytest.raises(ValueError, match='Cannot open SQLite file'):
        table_reader.ensure_form_source(str(tmp_path))


@pytest.mark.parametrize('kind, extension', [('parquet_folder', '.parquet'), ('feather_folder', '.feather'),
                                             ('feather_folder', '.arrow')])
def test_parquet_and_feather_tables_read_like_the_equivalent_csv(tmp_path, kind, extension):
    pytest.importorskip('pyarrow')
    typed = SURVEY.assign(_date=SURVEY['_date'].dt.tz_localize('UTC'))
    for stem, df in (('survey_0', typed), ('tree_plot_2', typed.iloc[:2])):
        path = tmp_path / f'{stem}{extension}'
        df.to_parquet(path, index=False) if extension == '.parquet' else df.reset_index(drop=True).to_feather(path)
    csv_folder = tmp_path / 'csv'
    _write_form(csv_folder, {'survey_0': SURVEY.assign(_date=SURVEY['_date'].dt.strftime('%m/%d/%Y %H:%M'))})

    source = table_reader.ensure_form_source(str(tmp_path))
    result = table_reader.read_table(source, 'survey_0')
    from_csv = table_reader.read_table(str(csv_folder), 'survey_0')

    assert source.kind == kind
    assert source.tables == ('survey_0', 'tree_plot_2')
    assert len(table_reader.read_table(source, 'tree_plot_2')) == 2
    assert list(result.columns) == list(from_csv.columns)
    # Text cells that hold only numbers become numbers, a time-zone-aware date becomes a naive datetime, as for a CSV.
    assert str(result['code'].dtype) == str(from_csv['code'].dtype) == 'int64'
    assert result['_date'].tolist() == SURVEY['_date'].tolist()
    assert result['_date'].dt.tz is None
    for column in from_csv.columns.drop('_date'):
        pd.testing.assert_series_equal(result[column], from_csv[column], check_names=False)


def test_parquet_and_feather_say_how_to_install_pyarrow_when_it_is_missing(tmp_path, monkeypatch):
    pd.DataFrame({'a': [1]}).to_csv(tmp_path / 'seed.csv', index=False)
    (tmp_path / 'survey_0.parquet').write_bytes(b'PAR1')
    os.remove(tmp_path / 'seed.csv')
    monkeypatch.setitem(__import__('sys').modules, 'pyarrow', None)

    with pytest.raises(ImportError, match='pyarrow'):
        table_reader.read_table(str(tmp_path), 'survey_0')


def test_every_format_is_chosen_in_the_documented_order(tmp_path):
    pytest.importorskip('pyarrow')
    folder = tmp_path / 'form'
    folder.mkdir()
    _write_form(folder, {'survey_0': pd.DataFrame({'a': [1]})})
    pd.DataFrame({'a': [1]}).to_parquet(folder / 'survey_0.parquet', index=False)
    pd.DataFrame({'a': [1]}).to_feather(folder / 'survey_0.feather')
    _write_workbook(folder / 'form_EXCEL.xlsx', {'survey_0': pd.DataFrame({'a': [1]})})
    _write_gpkg(folder / 'form.gpkg', {'survey': (pd.DataFrame({'fid': [1], 'a': [1]}), None)})
    _write_sqlite(folder / 'form.sqlite', {'survey_0': pd.DataFrame({'a': [1]})})
    _write_gdb(folder / 'form.gdb', {'survey': (pd.DataFrame({'objectid': [1], 'a': [1]}), None)})

    order = []
    for remove in ('survey_0.csv', 'survey_0.parquet', 'survey_0.feather', 'form_EXCEL.xlsx', 'form.gpkg', 'form.sqlite', None):
        order.append(table_reader.ensure_form_source(str(folder)).kind)
        if remove:
            os.remove(folder / remove)

    assert order == ['csv_folder', 'parquet_folder', 'feather_folder', 'workbook', 'gpkg', 'sqlite', 'gdb']
