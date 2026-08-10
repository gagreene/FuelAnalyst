from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point

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
