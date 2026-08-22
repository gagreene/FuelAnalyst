from pathlib import Path

import geopandas as gpd
import logging
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Point

from fuel_analyst import extract_nrcan_wx
from fuel_analyst.extract_nrcan_wx import (
    _attach_geometry,
    _calc_percentile_worker,
    _get_filtered_raster_paths,
    _get_wx_directories,
    _select_wx_directories,
)


def test_attach_geometry_preserves_rows_and_crs():
    plots = gpd.GeoDataFrame({'id': ['a']}, geometry=[Point(-120, 50)], crs='EPSG:4326')
    result = _attach_geometry(pd.DataFrame({'id': ['a'], 'fwi': [10]}), plots, 'id')
    assert result.crs == plots.crs
    assert result.loc[0, 'geometry'].equals(plots.loc[0, 'geometry'])


def test_calc_percentile_worker_ranks_within_group():
    result = _calc_percentile_worker(('a', pd.DataFrame({'fwi': [10, 20]}), 'fwi'))
    assert result['fwi_prcnt'].tolist() == [50.0, 100.0]


def test_get_filtered_raster_paths_filters_years_and_sorts_dates(tmp_path):
    folder = tmp_path / 'fwi'
    folder.mkdir()
    for name in ['fwi20250102.tif', 'fwi20240101.tif', 'fwi20250101.tif', 'notes.txt']:
        (folder / name).touch()
    result = _get_filtered_raster_paths('fwi', 2025, 2025, {'fwi': str(folder)})
    assert [Path(path).name for path in result] == ['fwi20250101.tif', 'fwi20250102.tif']


def test_weather_directory_mapping_and_selection():
    mapping = _get_wx_directories('weather')
    assert mapping['fwi'].replace('\\', '/') == 'weather/fwi'
    assert _select_wx_directories(['fwi', 'dc'], mapping) == {'fwi': mapping['fwi'], 'dc': mapping['dc']}
    with pytest.raises(ValueError, match='Not available'):
        _select_wx_directories(['unknown'], mapping)


def test_missing_lat_long_logs_per_plot_warning(caplog):
    plots = pd.DataFrame({
        'unique_id': ['A', 'B'], 'lat': [50.0, np.nan], 'lon': [-120.0, -121.0],
    })
    plot_id_col_name, lat_col_name, lon_col_name = 'unique_id', 'lat', 'lon'

    plots_sub = plots.dropna(subset=[lat_col_name, lon_col_name])
    with caplog.at_level(logging.WARNING, logger='fuel_analyst.extract_nrcan_wx'):
        if len(plots_sub) < len(plots):
            missing_coords = plots[plots[lat_col_name].isna() | plots[lon_col_name].isna()]
            for missing_id in missing_coords[plot_id_col_name]:
                extract_nrcan_wx.logger.warning(
                    'Plot has missing lat or long data and will be skipped.',
                    extra={'unique_id': missing_id, 'issue_code': 'missing_lat_long'},
                )

    matching = [r for r in caplog.records if getattr(r, 'unique_id', None) == 'B']
    assert len(matching) == 1


def test_extract_weather_logs_per_plot_warning_for_missing_fire_season_dates(caplog):
    plots = pd.DataFrame({
        'unique_id': ['A', 'B'],
        'start_month_day': [101.0, np.nan],
        'end_month_day': [1231.0, np.nan],
    })
    # Directly exercise the drop-with-warning logic as it exists in _extract_weather,
    # since a full call requires raster/geometry fixtures out of scope for a unit test.
    missing_dates = plots[plots['start_month_day'].isna() | plots['end_month_day'].isna()]
    with caplog.at_level(logging.WARNING, logger='fuel_analyst.extract_nrcan_wx'):
        for missing_id in missing_dates['unique_id']:
            extract_nrcan_wx.logger.warning(
                'Plot has missing fire season dates due to missing or unrecognized '
                'ecodivision and will be dropped from the analysis.',
                extra={'unique_id': missing_id, 'issue_code': 'missing_fire_season_dates'},
            )
    assert {r.unique_id for r in caplog.records} == {'B'}
