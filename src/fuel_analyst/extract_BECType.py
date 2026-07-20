# -*- coding: utf-8 -*-
"""
Extracts BEC information from VRI Rank 1 data and infills missing values
in fbp_prep_df without overwriting existing data.

@author: Sarah Smith-Tripp (updated)
"""

import os
import sys
import numpy as np
import pandas as pd
import geopandas as gpd
from pyproj import CRS


def _extract_BECType(
    plots: gpd.GeoDataFrame,
    plot_id_col_name: str,
    BEC_shp_dir: str,
    BEC_layer: str,
) -> pd.DataFrame:
    """Extract BEC and disturbance attributes from the VRI layer for plot locations."""

    crs = CRS.from_epsg(3005)

    # Spatial filter
    bbox = tuple(plots.to_crs(crs).total_bounds)
    bec = gpd.read_file(
        BEC_shp_dir,
        layer=BEC_layer,
        bbox=bbox,
        engine='pyogrio'
    )

    if bec.crs != plots.crs:
        plots = plots.to_crs(bec.crs)

    # Required columns from BEC layer
    bec_cols = [
        'COAST_INTERIOR_CD', 'BEC_ZONE_CODE', 'BEC_SUBZONE', 'SPECIES_CD_1',
        'PROJ_AGE_1', 'HARVEST_DATE', 'EARLIEST_NONLOGGING_DIST_TYPE',
        'EARLIEST_NONLOGGING_DIST_DATE', 'geometry'
    ]
    missing = [c for c in bec_cols if c not in bec.columns]
    if missing:
        raise ValueError(f"Missing columns in BEC layer: {missing}")

    bec = bec[[c for c in bec_cols if c in bec.columns]]

    # Spatial join
    joined = gpd.sjoin(
        plots[[plot_id_col_name, 'geometry']],
        bec,
        how='left',
        predicate='within'
    )

    # Fire disturbance date
    joined['recent_fire_date_11_yrs'] = np.where(
        joined['EARLIEST_NONLOGGING_DIST_TYPE'] == 'fire',
        joined['EARLIEST_NONLOGGING_DIST_DATE'],
        pd.NaT
    )

    # Select and rename
    result = joined[[plot_id_col_name] + [c for c in bec_cols if c != 'geometry'] +
                    ['recent_fire_date_11_yrs']].copy()

    result = result.rename(columns={
        'BEC_ZONE_CODE': 'BEC_Zone',
        'BEC_SUBZONE': 'BEC_Subzone',
        'PROJ_AGE_1': 'SPECIES_CD_1_max_age',
        'HARVEST_DATE': 'recent_clearcut_date_10_yrs',
    })

    # Drop raw disturbance columns
    result = result.drop(columns=[
        'EARLIEST_NONLOGGING_DIST_TYPE', 'EARLIEST_NONLOGGING_DIST_DATE',
        'PROJ_AGE_1', 'BEC_ZONE_CODE', 'BEC_SUBZONE'
    ], errors='ignore')

    # Clean string columns
    for col in ['COAST_INTERIOR_CD', 'BEC_Zone', 'BEC_Subzone', 'SPECIES_CD_1']:
        if col in result.columns:
            result[col] = result[col].astype(str).replace('nan', '')

    return result


def _load_plots(plot_pts_path: str, lat: str, lon: str) -> gpd.GeoDataFrame:
    """Load plot points from CSV or shapefile and return as GeoDataFrame."""

    if plot_pts_path.lower().endswith('.csv'):
        df = pd.read_csv(plot_pts_path)
        plots = gpd.GeoDataFrame(
            df,
            geometry=gpd.points_from_xy(df[lon], df[lat]),
            crs='EPSG:4326'
        )
    else:
        plots = gpd.read_file(plot_pts_path)

    if plots.crs is None:
        raise ValueError("Plot CRS is undefined")

    if plots.crs.to_epsg() != 3978:
        plots = plots.to_crs(epsg=3978)

    return plots


def infill_bec_data(fbp_prep_path: str, bec_info_df: pd.DataFrame, plot_id_col: str = 'unique_id') -> pd.DataFrame:
    """Merge BEC data and infill missing values without overwriting existing data."""

    fbp_prep_df = pd.read_csv(fbp_prep_path)

    fbp_prep_df_updated = fbp_prep_df.merge(
        bec_info_df,
        on=plot_id_col,
        how='left',
        suffixes=('', '_VRI')
    )

    string_cols = ['COAST_INTERIOR_CD', 'BEC_Zone', 'BEC_Subzone', 'SPECIES_CD_1']
    numeric_cols = ['SPECIES_CD_1_max_age']
    date_cols = ['recent_clearcut_date_10_yrs', 'recent_fire_date_11_yrs']

    for col in string_cols + numeric_cols + date_cols:
        new_col = f'{col}_VRI'
        if new_col not in fbp_prep_df_updated.columns:
            continue

        if col not in fbp_prep_df_updated.columns:
            fbp_prep_df_updated[col] = fbp_prep_df_updated[new_col]
            continue

        if col in string_cols:
            fbp_prep_df_updated[col] = (
                fbp_prep_df_updated[col]
                .replace('', np.nan)
                .fillna(fbp_prep_df_updated[new_col])
                .astype('string')
                .fillna('')
            )
        elif col in numeric_cols:
            orig = pd.to_numeric(fbp_prep_df_updated[col], errors='coerce')
            vri = pd.to_numeric(fbp_prep_df_updated[new_col], errors='coerce')
            fbp_prep_df_updated[col] = orig.fillna(vri).infer_objects(copy=False)
        elif col in date_cols:
            orig = pd.to_datetime(fbp_prep_df_updated[col], errors='coerce')
            vri = pd.to_datetime(fbp_prep_df_updated[new_col], errors='coerce')
            fbp_prep_df_updated[col] = orig.fillna(vri).infer_objects(copy=False)

    return fbp_prep_df_updated

def create_joined_geopackage(
    plots: gpd.GeoDataFrame,
    bec_info_df: pd.DataFrame,
    plot_id_col: str,
    output_path: str
) -> None:
    """Create and save a geopackage of plot points joined with BEC attributes."""
    joined = plots[[plot_id_col, 'geometry']].merge(
        bec_info_df,
        on=plot_id_col,
        how='left'
    )
    joined_gdf = gpd.GeoDataFrame(joined, geometry='geometry', crs=plots.crs)
    joined_gdf.to_file(output_path, driver='GPKG')
    print(f'Joined geopackage saved to {output_path}')

if __name__ == '__main__':
    is_docker = os.path.exists('/.dockerenv')

    if is_docker:
        _BEC_shp_dir = os.path.join(os.getenv('BEC_DATA_DIR', '/app/BEC_data'), 'VEG_COMP_LYR_R1_POLY_2025.gdb')
        _plot_pts_path = os.path.join('OUTPUT_FuelAnalyst', '/app/output/fuel_analyst', 'conpyro_df.csv')
        _fbp_prep_path = os.path.join('OUTPUT_FuelAnalyst', '/app/output/fuel_analyst', 'fbp_prep_df.csv')
        _fbp_out_path = os.path.join('OUTPUT_FBP', '/app/output/fuel_analyst/fbp_prep_df_BEC.csv')  
        _gpkg_out_path = os.path.join('/app/output/plots.gpkg') 
    else:
        _BEC_shp_dir = r"C:\Users\ssmithtr\Desktop\CleanTest\BEC_data\VEG_COMP_LYR_R1_POLY_2025.gdb"
        test_dir = os.path.join(os.path.dirname(__file__), 'tests', 'output', 'fuel_analyst')
        _plot_pts_path = os.path.join(test_dir, 'conpyro_df.csv')
        _fbp_prep_path = os.path.join(test_dir, 'fbp_prep_df.csv')
        _gpkg_out_path = os.path.join(test_dir, 'plots.gpkg')
        _fbp_out_path = os.path.join(test_dir, 'fbp_prep_df_BEC.csv')

    _BEC_layer = 'VEG_COMP_LYR_R1_POLY'
    _plot_id_col_name = 'unique_id'
    _lat_col_name = 'lat'
    _lon_col_name = 'long'

    plots_gdf = _load_plots(_plot_pts_path, _lat_col_name, _lon_col_name)

    bec_info_df = _extract_BECType(
        plots=plots_gdf,
        plot_id_col_name=_plot_id_col_name,
        BEC_shp_dir=_BEC_shp_dir,
        BEC_layer=_BEC_layer
    )

    fbp_prep_df_updated = infill_bec_data(
        fbp_prep_path=_fbp_prep_path,
        bec_info_df=bec_info_df,
        plot_id_col=_plot_id_col_name
    )

    fbp_prep_df_updated.to_csv(_fbp_out_path, index=False)
    print(f'BEC type extraction complete. Results saved to {_fbp_out_path}')
    create_joined_geopackage(
        plots=plots_gdf,
        bec_info_df=bec_info_df,
        plot_id_col=_plot_id_col_name,
        output_path=_gpkg_out_path
    )