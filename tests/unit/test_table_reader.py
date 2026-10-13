import os

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
