import pandas as pd
import pytest

from fuel_analyst.tools.merge_wx_data import (
    _add_season_column,
    _refine_fbp_fuel_types_by_season,
    merge_weather_data,
)


def test_add_season_column_classifies_boundaries_and_places_column_after_date():
    df = pd.DataFrame({'id': [1, 2, 3], 'wx_date': [20250614, 20250615, 20250915], 'value': [1, 2, 3]})
    result = _add_season_column(df, 615, 915)
    assert result['season'].tolist() == ['Spring', 'Summer', 'Fall']
    assert result.columns.tolist() == ['id', 'wx_date', 'season', 'value']


def test_add_season_column_is_noop_without_weather_date():
    df = pd.DataFrame({'value': [1]})
    assert _add_season_column(df.copy(), 615, 915).equals(df)


def test_refine_fbp_fuel_types_by_season():
    df = pd.DataFrame({
        'season': ['Spring', 'Summer', 'Fall'],
        'fbp_fuel_type': ['O1b M2 M4 D2', 'O1a M1 M3 D1', 'O1a M2 M4 D2'],
    })
    result = _refine_fbp_fuel_types_by_season(df)
    assert result['fbp_fuel_type'].tolist() == [
        'O1a M1 M3 D1', 'O1b M2 M4 D2', 'O1b M1 M3 D1'
    ]


def _merge_with_fbp_column(tmp_path, fuel_types):
    """Merge two plots with the given fbp_fuel_type values (written to CSV as plain text cells) on 15 July."""
    plot_path, wx_path, out_path = tmp_path / 'plots.csv', tmp_path / 'wx.csv', tmp_path / 'out.csv'
    pd.DataFrame({'unique_id': ['a', 'b'], 'fbp_fuel_type': fuel_types}).to_csv(plot_path, index=False)
    pd.DataFrame({'station_id': ['a', 'b'], 'wx_date': [20250715, 20250715], 'fwi': [10, 20]}).to_csv(wx_path, index=False)
    merge_weather_data(
        str(plot_path), 'unique_id', str(wx_path), 'station_id', ['wx_date', 'fwi'], str(out_path),
        add_season=True, refine_fbp_seasonally=True, summer_start=615, fall_start=915,
    )
    return pd.read_csv(out_path, dtype={'fbp_fuel_type': 'string'})


def test_merge_weather_data_accepts_the_empty_fbp_fuel_type_placeholder(tmp_path):
    """conpyro_df.csv ships fbp_fuel_type as an empty placeholder that pandas reads back as a float column."""
    result = _merge_with_fbp_column(tmp_path, ['', ''])

    assert result['season'].tolist() == ['Summer', 'Summer']
    assert result['fbp_fuel_type'].isna().all()


def test_merge_weather_data_refines_the_filled_part_of_a_partly_typed_fbp_column(tmp_path):
    result = _merge_with_fbp_column(tmp_path, ['M1', ''])

    assert result.loc[0, 'fbp_fuel_type'] == 'M2'   # M1 becomes M2 in Summer
    assert pd.isna(result.loc[1, 'fbp_fuel_type'])


def test_refine_fbp_fuel_types_by_season_leaves_an_all_missing_float_column_missing():
    df = pd.DataFrame({'season': ['Spring', 'Summer'], 'fbp_fuel_type': [float('nan'), float('nan')]})

    result = _refine_fbp_fuel_types_by_season(df)

    assert result['fbp_fuel_type'].isna().all()


def test_merge_weather_data_cartesian_product_does_not_write_missing_wx_and_preserves_row_count(tmp_path):
    plot_path, wx_path, out_path = tmp_path / 'plots.csv', tmp_path / 'wx.csv', tmp_path / 'out.csv'
    pd.DataFrame({'unique_id': ['a', 'b']}).to_csv(plot_path, index=False)
    pd.DataFrame({'wx_date': [20250101, 20250102], 'fwi': [1, 2]}).to_csv(wx_path, index=False)
    merge_weather_data(
        str(plot_path), 'unique_id', str(wx_path), None, None, str(out_path),
        add_season=False, refine_fbp_seasonally=False,
    )
    assert len(pd.read_csv(out_path)) == 4
    assert not (tmp_path / 'missing_wx.csv').exists()


def test_merge_weather_data_keyed_merge_excludes_unmatched_plots_and_writes_missing_wx(tmp_path):
    """Documents the new filtering contract: a keyed merge's unmatched plot rows are excluded
    from the primary output and written to missing_wx.csv instead, detected via pandas' merge
    indicator rather than a weather value such as wx_date."""
    plot_path, wx_path, out_path = tmp_path / 'plots.csv', tmp_path / 'wx.csv', tmp_path / 'out.csv'
    pd.DataFrame({'unique_id': ['a', 'b'], 'plot': [1, 2]}).to_csv(plot_path, index=False)
    pd.DataFrame({'station_id': ['a'], 'wx_date': [20250615], 'fwi': [10], 'unused': [99]}).to_csv(wx_path, index=False)

    merge_weather_data(
        str(plot_path), 'unique_id', str(wx_path), 'station_id', ['wx_date', 'fwi'], str(out_path),
        add_season=False, refine_fbp_seasonally=False,
    )

    result = pd.read_csv(out_path)
    assert result.columns.tolist() == ['unique_id', 'plot', 'station_id', 'wx_date', 'fwi']
    assert result['unique_id'].tolist() == ['a']
    assert result.loc[0, 'fwi'] == 10

    missing = pd.read_csv(tmp_path / 'missing_wx.csv')
    assert missing.columns.tolist() == result.columns.tolist()
    assert missing['unique_id'].tolist() == ['b']
    assert '_wx_merge_status' not in result.columns
    assert '_wx_merge_status' not in missing.columns
    assert 'Unnamed: 0' not in result.columns
    assert 'Unnamed: 0' not in missing.columns


def test_merge_weather_data_keyed_merge_matches_rows_with_missing_wx_date(tmp_path):
    """A matched row's own missing wx_date must not be mistaken for an unmatched merge - proves
    match detection uses the merge indicator, not the value of wx_date."""
    plot_path, wx_path, out_path = tmp_path / 'plots.csv', tmp_path / 'wx.csv', tmp_path / 'out.csv'
    pd.DataFrame({'unique_id': ['a'], 'plot': [1]}).to_csv(plot_path, index=False)
    pd.DataFrame({'station_id': ['a'], 'wx_date': [None], 'fwi': [10]}).to_csv(wx_path, index=False)

    merge_weather_data(
        str(plot_path), 'unique_id', str(wx_path), 'station_id', ['wx_date', 'fwi'], str(out_path),
        add_season=False, refine_fbp_seasonally=False,
    )

    result = pd.read_csv(out_path)
    assert result['unique_id'].tolist() == ['a']
    assert pd.isna(result.loc[0, 'wx_date'])

    missing = pd.read_csv(tmp_path / 'missing_wx.csv')
    assert len(missing) == 0


def test_merge_weather_data_keyed_merge_null_keys_do_not_spuriously_match(tmp_path):
    """pandas matches a null left key against a null right key by default; a plot row with a
    missing merge key must not be spuriously matched to a weather row that also has a missing
    merge key - both are genuinely unmatched, not a real join on "no id"."""
    plot_path, wx_path, out_path = tmp_path / 'plots.csv', tmp_path / 'wx.csv', tmp_path / 'out.csv'
    pd.DataFrame({'unique_id': ['a', None], 'plot': [1, 2]}).to_csv(plot_path, index=False)
    pd.DataFrame(
        {'station_id': ['a', None], 'wx_date': [20250615, 20250616], 'fwi': [10, 20]}
    ).to_csv(wx_path, index=False)

    merge_weather_data(
        str(plot_path), 'unique_id', str(wx_path), 'station_id', ['wx_date', 'fwi'], str(out_path),
        add_season=False, refine_fbp_seasonally=False,
    )

    result = pd.read_csv(out_path)
    assert result['unique_id'].tolist() == ['a']

    missing = pd.read_csv(tmp_path / 'missing_wx.csv')
    assert len(missing) == 1
    assert pd.isna(missing.loc[0, 'unique_id'])


def test_merge_weather_data_keyed_merge_with_wx_date_omitted_from_wx_merge_vars(tmp_path):
    """Keyed merging must work without a selected wx_date when seasonal behavior is disabled,
    without raising KeyError - proves matching and unmatched-row filtering never depend on
    wx_date being present."""
    plot_path, wx_path, out_path = tmp_path / 'plots.csv', tmp_path / 'wx.csv', tmp_path / 'out.csv'
    pd.DataFrame({'unique_id': ['a', 'b'], 'plot': [1, 2]}).to_csv(plot_path, index=False)
    pd.DataFrame({'station_id': ['a'], 'wx_date': [20250615], 'fwi': [10]}).to_csv(wx_path, index=False)

    merge_weather_data(
        str(plot_path), 'unique_id', str(wx_path), 'station_id', ['fwi'], str(out_path),
        add_season=False, refine_fbp_seasonally=False,
    )

    result = pd.read_csv(out_path)
    assert 'wx_date' not in result.columns
    assert result['unique_id'].tolist() == ['a']

    missing = pd.read_csv(tmp_path / 'missing_wx.csv')
    assert missing['unique_id'].tolist() == ['b']


def test_merge_weather_data_keyed_merge_writes_empty_missing_wx_when_all_plots_match(tmp_path):
    plot_path, wx_path, out_path = tmp_path / 'plots.csv', tmp_path / 'wx.csv', tmp_path / 'out.csv'
    pd.DataFrame({'unique_id': ['a', 'b'], 'plot': [1, 2]}).to_csv(plot_path, index=False)
    pd.DataFrame(
        {'station_id': ['a', 'b'], 'wx_date': [20250615, 20250616], 'fwi': [10, 20]}
    ).to_csv(wx_path, index=False)

    merge_weather_data(
        str(plot_path), 'unique_id', str(wx_path), 'station_id', ['wx_date', 'fwi'], str(out_path),
        add_season=False, refine_fbp_seasonally=False,
    )

    result = pd.read_csv(out_path)
    assert result['unique_id'].tolist() == ['a', 'b']

    missing = pd.read_csv(tmp_path / 'missing_wx.csv')
    assert len(missing) == 0
    assert missing.columns.tolist() == result.columns.tolist()


def test_merge_weather_data_raises_when_missing_wx_diagnostic_path_collides_with_an_input_or_output_path(tmp_path):
    """The fixed missing_wx.csv diagnostic name must not silently overwrite out_path (or an
    input path) if the caller's out_path directory already resolves to that filename."""
    plot_path, wx_path = tmp_path / 'plots.csv', tmp_path / 'wx.csv'
    out_path = tmp_path / 'missing_wx.csv'
    pd.DataFrame({'unique_id': ['a'], 'plot': [1]}).to_csv(plot_path, index=False)
    pd.DataFrame({'station_id': ['a'], 'wx_date': [20250615], 'fwi': [10]}).to_csv(wx_path, index=False)

    with pytest.raises(ValueError, match='missing-weather diagnostic path'):
        merge_weather_data(
            str(plot_path), 'unique_id', str(wx_path), 'station_id', ['wx_date', 'fwi'], str(out_path),
            add_season=False, refine_fbp_seasonally=False,
        )


def test_merge_weather_data_validates_required_columns_and_season_boundaries(tmp_path):
    plot_path, wx_path = tmp_path / 'plots.csv', tmp_path / 'wx.csv'
    pd.DataFrame({'wrong': ['a']}).to_csv(plot_path, index=False)
    pd.DataFrame({'id': ['a']}).to_csv(wx_path, index=False)
    with pytest.raises(ValueError, match='Summer_start'):
        merge_weather_data(str(plot_path), 'id', str(wx_path), 'id', None, str(tmp_path / 'x.csv'), summer_start=None)
    with pytest.raises(ValueError, match='Plot ID column'):
        merge_weather_data(
            str(plot_path), 'id', str(wx_path), 'id', None, str(tmp_path / 'x.csv'),
            add_season=False, refine_fbp_seasonally=False,
        )
