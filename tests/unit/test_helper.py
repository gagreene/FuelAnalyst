from pathlib import Path

import pandas as pd
import pytest

from fuel_analyst.components import helper


def test_attach_columns_replaces_existing_columns_in_place():
    df = pd.DataFrame({'a': [1], 'stale': ['old'], 'b': [2]})
    result = helper.attach_columns(df, {'stale': pd.Series(['new']), 'c': pd.Series([3])})
    assert list(result.columns) == ['a', 'stale', 'b', 'c']
    assert result['stale'].tolist() == ['new']
    assert result.columns.tolist().count('stale') == 1


def test_attach_columns_accepts_a_dataframe_of_columns():
    df = pd.DataFrame({'a': [1]})
    new_columns = pd.DataFrame({'b': [2], 'c': [3]})
    result = helper.attach_columns(df, new_columns)
    assert list(result.columns) == ['a', 'b', 'c']
    assert result.loc[0, ['b', 'c']].tolist() == [2, 3]


def test_get_missing_df_columns_reports_only_absent_columns():
    df = pd.DataFrame(columns=['a', 'c'])
    assert helper.get_missing_df_columns(df, ['a', 'b', 'c']) == ['b']


def test_sort_list_uses_natural_numeric_order():
    assert helper.sort_list(['plot10', 'Plot2', 'plot1']) == ['plot1', 'Plot2', 'plot10']


def test_get_unique_id_supports_both_date_formats_and_adds_year():
    df = pd.DataFrame({
        '_date': ['01/02/2025 03:04', '01/03/2026 03:04:05 PM'],
        'treatment_area': ['A', 'B'],
        'treatment_unit': ['U1', 'U2'],
        'treatment_type': ['treated', 'burned'],
        'plot_id': ['1', '2'],
    })

    result = helper.get_unique_id(df)

    assert result['year'].tolist() == [2025, 2026]
    assert result['unique_id'].tolist() == [
        'A_U1_treated_1_2025',
        'B_U2_burned_2_2026',
    ]


def test_get_unique_id_keeps_most_recent_duplicate():
    df = pd.DataFrame({
        '_date': ['01/01/2025 10:00', '02/01/2025 10:00'],
        'treatment_area': ['A', 'A'],
        'treatment_unit': ['U', 'U'],
        'treatment_type': ['treated', 'treated'],
        'plot_id': ['1', '1'],
        'value': ['old', 'new'],
    })
    result = helper.get_unique_id(df)
    assert result['value'].tolist() == ['new']


@pytest.mark.parametrize(
    ('older_date', 'newer_date'),
    [
        ('01/01/2025 11:59:59 AM', '01/01/2025 12:00:00 PM'),
        ('01/01/2025 11:59:59 PM', '01/02/2025 12:00:00 AM'),
    ],
)
def test_get_unique_id_orders_am_pm_boundaries(older_date, newer_date):
    df = pd.DataFrame({
        '_date': [newer_date, older_date],
        'treatment_area': ['A', 'A'],
        'treatment_unit': ['U', 'U'],
        'treatment_type': ['treated', 'treated'],
        'plot_id': ['1', '1'],
        'value': ['newer', 'older'],
    })

    result = helper.get_unique_id(df)

    assert result['value'].tolist() == ['newer']


def test_get_unique_id_rejects_unparseable_dates():
    df = pd.DataFrame({
        '_date': ['not-a-date'],
        'treatment_area': ['A'],
        'treatment_unit': ['U'],
        'treatment_type': ['treated'],
        'plot_id': ['1'],
    })
    with pytest.raises(ValueError, match='unparseable'):
        helper.get_unique_id(df)


def test_csv_helpers_round_trip_and_append(tmp_path):
    path = tmp_path / 'nested' / 'data.csv'
    path.parent.mkdir()
    source = pd.DataFrame({'name': ['alpha'], 'value': [1]})

    helper.export_csv(source, str(path))
    helper.add_line_to_csv(str(path), ['beta', 2], 2)

    result = helper.get_df(str(path))
    assert result.to_dict('records') == [
        {'name': 'alpha', 'value': 1},
        {'name': 'beta', 'value': 2},
    ]
    assert helper.file_exists(str(path))


def test_delete_files_clears_files_and_nested_directories(tmp_path):
    csv_path = tmp_path / 'remove.csv'
    nested = tmp_path / 'nested'
    nested.mkdir()
    csv_path.write_text('a\n1\n', encoding='utf-8')
    (nested / 'remove.txt').write_text('remove', encoding='utf-8')

    helper.delete_files(str(tmp_path))

    assert list(tmp_path.iterdir()) == []


def test_get_repo_root_and_derived_directories(tmp_path):
    package_dir = tmp_path / 'src' / 'fuel_analyst'
    package_dir.mkdir(parents=True)
    (tmp_path / 'pyproject.toml').write_text('[project]\nname = "fuel-analyst"\n', encoding='utf-8')

    assert not (tmp_path / 'requirements.txt').exists()
    assert Path(helper.get_repo_root(str(package_dir))) == tmp_path
    assert Path(helper.get_examples_dir(str(package_dir))) == tmp_path / 'examples'
    assert Path(helper.get_development_dir(str(package_dir))) == tmp_path / 'development'
