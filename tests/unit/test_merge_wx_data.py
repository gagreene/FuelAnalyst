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


def test_merge_weather_data_left_joins_selected_variables(tmp_path):
    plot_path, wx_path, out_path = tmp_path / 'plots.csv', tmp_path / 'wx.csv', tmp_path / 'out.csv'
    pd.DataFrame({'unique_id': ['a', 'b'], 'plot': [1, 2]}).to_csv(plot_path, index=False)
    pd.DataFrame({'station_id': ['a'], 'wx_date': [20250615], 'fwi': [10], 'unused': [99]}).to_csv(wx_path, index=False)

    merge_weather_data(
        str(plot_path), 'unique_id', str(wx_path), 'station_id', ['wx_date', 'fwi'], str(out_path),
        add_season=False, refine_fbp_seasonally=False,
    )

    result = pd.read_csv(out_path)
    assert result.columns.tolist() == ['unique_id', 'plot', 'station_id', 'wx_date', 'fwi']
    assert result.loc[0, 'fwi'] == 10
    assert pd.isna(result.loc[1, 'fwi'])


def test_merge_weather_data_cartesian_product(tmp_path):
    plot_path, wx_path, out_path = tmp_path / 'plots.csv', tmp_path / 'wx.csv', tmp_path / 'out.csv'
    pd.DataFrame({'unique_id': ['a', 'b']}).to_csv(plot_path, index=False)
    pd.DataFrame({'wx_date': [20250101, 20250102], 'fwi': [1, 2]}).to_csv(wx_path, index=False)
    merge_weather_data(
        str(plot_path), 'unique_id', str(wx_path), None, None, str(out_path),
        add_season=False, refine_fbp_seasonally=False,
    )
    assert len(pd.read_csv(out_path)) == 4


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
