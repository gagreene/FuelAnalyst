# -*- coding: utf-8 -*-
"""
Created on Fri Apr 17, 2026

@author: Gregory A. Greene
"""
__author__ = ['Gregory A. Greene']

import logging
import os
import numpy as np
import pandas as pd
from typing import Union

from . import fofem_units
from . import helper
from ._default_configs import default_season_start_dict
from . import fwis_moisture_content as mc
from pyfofem import pyfofem as fofem

logger = logging.getLogger(__name__)


_VALID_EMISSIONS_MODES = {'legacy', 'default', 'expanded'}


def _calc_fuel_moisture_content(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate fuel moisture content columns and add them to the DataFrame.

    :param df: DataFrame with 'mc_sa', 'mc_dmc', and 'dc' columns.
    :return: DataFrame with FOFEM moisture columns added/updated.
    """
    df['wfl10HourMoisture'] = df['mc_sa']
    df['DuffMoisture'] = df['mc_dmc']
    df['wfl1000HourMoisture'] = mc.dc_mc(dc=df['dc'].to_numpy())

    return df


def _gen_plot_id(df: pd.DataFrame):
    """
    Replace spaces with underscores in '#PlotId' and return reverse mapping.

    :param df: DataFrame with '#PlotId' column.
    :return: (DataFrame with updated '#PlotId', dict mapping underscored to original values)
    """
    plotid_map = dict(zip(df['#PlotId'].str.replace(' ', '_'), df['#PlotId']))
    df['#PlotId'] = df['#PlotId'].str.replace(' ', '_')
    return df, plotid_map


def _restore_plot_id(df: pd.DataFrame, plotid_map: dict) -> pd.DataFrame:
    """
    Restore original '#PlotId' values from underscored values.

    :param df: DataFrame with underscored '#PlotId' values.
    :param plotid_map: Mapping from underscored to original '#PlotId' values.
    :return: DataFrame with restored '#PlotId'.
    """
    df['#PlotId'] = df['#PlotId'].map(plotid_map).fillna(df['#PlotId'])
    return df


def _get_merged_consumption_df(
        plot_wx_fire_csv_path: str,
        plot_id_col_name: str,
        fofem_consume_csv_path: str,
) -> pd.DataFrame:
    """
    Merge stand fire behavior/weather and FOFEM consumption dataframes.

    :param plot_wx_fire_csv_path: Path to stand weather and fire behavior CSV.
    :param plot_id_col_name: Name of stand unique ID column.
    :param fofem_consume_csv_path: Path to FOFEM consumption CSV.
    :return: Merged DataFrame.
    """
    if not helper.file_exists(plot_wx_fire_csv_path):
        raise FileNotFoundError(f'Stand weather and fire behavior CSV file not found: {plot_wx_fire_csv_path}')
    if not helper.file_exists(fofem_consume_csv_path):
        raise FileNotFoundError(f'FOFEM consumption CSV file not found: {fofem_consume_csv_path}')

    plot_fire_df = helper.get_df(plot_wx_fire_csv_path)
    fofem_consume_df = helper.get_df(fofem_consume_csv_path)

    required_fire_cols = [
        plot_id_col_name, 'wx_date', 'hfi',
        'flame_res_time_sec', 'instand_ws_mps',
        'temp', 'mc_sa', 'mc_dmc', 'dc', 'cfb'
    ]
    missing_cols = helper.get_missing_df_columns(plot_fire_df, required_fire_cols)
    if missing_cols:
        raise ValueError(f'Missing required column(s) in weather/fire behavior CSV: {missing_cols}')

    if '#PlotId' not in fofem_consume_df.columns:
        raise ValueError('Missing required column "#PlotId" in FOFEM consumption CSV.')

    plot_fire_df = plot_fire_df[required_fire_cols]

    merged_df = pd.merge(
        left=fofem_consume_df,
        right=plot_fire_df,
        left_on='#PlotId',
        right_on=plot_id_col_name,
        how='left',
        suffixes=('', '_plot')
    )
    merged_df = merged_df.drop(columns=[col for col in merged_df.columns if col.endswith('_plot')])
    merged_df = merged_df.dropna(subset=[plot_id_col_name])

    return merged_df


def _get_pct_crown_burned(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate percent crown burned and add to DataFrame.

    :param df: DataFrame with 'cfb' column.
    :return: DataFrame with 'PercentCrownBurned' updated.
    """
    df['PercentCrownBurned'] = 100.0 * df['cfb']
    return df


def _get_season(df: pd.DataFrame, season_start_dict: dict = None) -> pd.DataFrame:
    """
    Determine season for each row in DataFrame from 'wx_date'.

    :param df: DataFrame with 'wx_date' column.
    :param season_start_dict: Optional season start-day dictionary.
    :return: DataFrame with 'season' column.
    """
    if season_start_dict is None:
        season_start_dict = default_season_start_dict

    required_cols = ['wx_date']
    missing_cols = helper.get_missing_df_columns(df, required_cols)
    if missing_cols:
        raise ValueError(f'Missing required column(s) for season assignment: {missing_cols}')

    season_starts = {
        'Spring': int(season_start_dict['Spring']),
        'Summer': int(season_start_dict['Summer']),
        'Fall': int(season_start_dict['Fall']),
        'Winter': int(season_start_dict['Winter']),
    }

    def determine_season(wx_date):
        """
        Determine the configured season for one YYYYMMDD weather date.

        :param wx_date: Weather date formatted as YYYYMMDD.
        :return: Season name containing the weather date.
        """
        date_str = str(int(wx_date))
        month_day = int(date_str[4:8])
        if season_starts['Spring'] <= month_day < season_starts['Summer']:
            return 'Spring'
        if season_starts['Summer'] <= month_day < season_starts['Fall']:
            return 'Summer'
        if season_starts['Fall'] <= month_day < season_starts['Winter']:
            return 'Fall'
        return 'Winter'

    df['season'] = df['wx_date'].apply(determine_season)
    return df


def _to_float_arr(df: pd.DataFrame, col: str, default: float = 0.0) -> np.ndarray:
    """
    Convert DataFrame column to float ndarray, coercing invalid values.

    :param df: DataFrame containing the column.
    :param col: Column name.
    :param default: Fill value for NaN.
    :return: Float ndarray.
    """
    return pd.to_numeric(df[col], errors='coerce').fillna(default).to_numpy(dtype=float)


def _sanitize_cover_group(series: pd.Series) -> np.ndarray:
    """
    Normalize CoverGroup values to strings expected by pyfofem.

    :param series: CoverGroup column.
    :return: Object ndarray.
    """
    s = series.fillna('').astype(str).str.strip('"').str.strip()
    s = s.replace({'nan': '', 'None': '', 'NA': '', 'N/A': ''})
    return s.to_numpy(dtype=object)


def _prepare_soil_family(df: pd.DataFrame) -> Union[np.ndarray, None]:
    """
    Prepare SoilFamily array for pyfofem soil-heating mode.

    :param df: Input merged DataFrame.
    :return: Soil family object ndarray.
    """
    if 'SoilFamily' not in df.columns:
        logger.warning('SoilFamily column is missing; disabling soil heating for this emissions run.')
        return None

    soil = df['SoilFamily'].astype(str).str.strip()
    return soil.to_numpy(dtype=object)


def process_emissions(
        plot_wx_fire_csv_path: str,
        plot_id_col_name: str,
        fofem_consume_csv_path: str,
        out_dir: str,
        emissions_mode: str = 'legacy',
        model_soil_heating: bool = False,
        emissions_units: str = 'SI',
        num_workers: int = 1,
        return_df: bool = False,
) -> Union[None, pd.DataFrame]:
    """
    Process emissions modelling using pyfofem.run_fofem_emissions.

    :param plot_wx_fire_csv_path: Path to CSV containing plot weather and fire behavior.
    :param plot_id_col_name: Name of unique plot ID column in fire behavior CSV.
    :param fofem_consume_csv_path: Path to FOFEM consumption CSV. Its filename must be one of
        the canonical, unit-bearing names from fofem_units.consume_filename() and must match
        emissions_units.
    :param out_dir: Output directory for temporary/final emissions files.
    :param emissions_mode: Emissions factor mode: legacy, default, or expanded.
    :param model_soil_heating: Toggle FOFEM soil-heating model.
    :param emissions_units: Unit system of the values in fofem_consume_csv_path, passed
        through to pyfofem.run_fofem_emissions(). Options: 'Imperial', 'SI'. Also determines the
        unit suffixes applied to physical result columns in the final analyst-facing DataFrame
        and CSV (see fofem_units.emissions_result_rename_map()).
    :param num_workers: Number of workers for pyfofem burnup processing.
    :param return_df: If True, return final emissions DataFrame.
    :return: None or final DataFrame.
    """
    os.makedirs(out_dir, exist_ok=True)

    em_mode = str(emissions_mode).strip().lower()
    if em_mode not in _VALID_EMISSIONS_MODES:
        raise ValueError(
            f'Invalid emissions_mode "{emissions_mode}". '
            f'Valid options are: {sorted(_VALID_EMISSIONS_MODES)}'
        )

    # Validate the configured units and the input file's unit-bearing filename before any
    # processing, so this public component is safe to call directly (not only via run_conpyro(),
    # which performs the same check on its own behalf before dispatching here).
    emissions_units = fofem_units.validate_fofem_units(emissions_units)
    fofem_units.validate_consume_units(fofem_consume_csv_path, emissions_units)

    merged_df = _get_merged_consumption_df(
        plot_wx_fire_csv_path=plot_wx_fire_csv_path,
        plot_id_col_name=plot_id_col_name,
        fofem_consume_csv_path=fofem_consume_csv_path,
    )

    merged_df, plotid_map = _gen_plot_id(merged_df)
    merged_df = _get_pct_crown_burned(merged_df)
    merged_df = _get_season(merged_df)
    merged_df = _calc_fuel_moisture_content(merged_df)

    model_df = merged_df.drop(columns=[plot_id_col_name, 'cfb'], errors='ignore').copy()

    required_cols = [
        'Litter', 'Duff', 'DuffDepth', 'Herbaceous', 'Shrub',
        'CrownFoliage', 'CrownBranch', 'PercentCrownBurned',
        'Region', 'CoverGroup', 'season', 'FuelCategory',
        'DuffMoisture', 'wfl10HourMoisture', 'wfl1000HourMoisture',
        'wfl1Hour', 'wfl10Hour', 'wfl100Hour',
        'wfl3_6S', 'wfl6_9S', 'wfl9_20S', 'wfl20plusS',
        'wfl3_6R', 'wfl6_9R', 'wfl9_20R', 'wfl20plusR',
        'hfi', 'flame_res_time_sec', 'fuel_bed_depth_m', 'temp', 'instand_ws_mps'
    ]
    missing_cols = helper.get_missing_df_columns(model_df, required_cols)
    if missing_cols:
        raise ValueError(f'Missing required column(s) for pyfofem emissions modelling: {missing_cols}')

    print(
        f'\tProcessing emissions with pyfofem (emissions_mode={em_mode}, '
        f'soil_heating={model_soil_heating})...'
    )
    results = fofem.run_fofem_emissions(
        litter=_to_float_arr(model_df, 'Litter'),
        duff=_to_float_arr(model_df, 'Duff'),
        duff_depth=_to_float_arr(model_df, 'DuffDepth'),
        herb=_to_float_arr(model_df, 'Herbaceous'),
        shrub=_to_float_arr(model_df, 'Shrub'),
        crown_foliage=_to_float_arr(model_df, 'CrownFoliage'),
        crown_branch=_to_float_arr(model_df, 'CrownBranch'),
        pct_crown_burned=_to_float_arr(model_df, 'PercentCrownBurned'),
        region=model_df['Region'].astype(str).to_numpy(dtype=object),
        cvr_grp=_sanitize_cover_group(model_df['CoverGroup']),
        season=model_df['season'].astype(str).to_numpy(dtype=object),
        fuel_category=model_df['FuelCategory'].astype(str).to_numpy(dtype=object),
        duff_moist=_to_float_arr(model_df, 'DuffMoisture'),
        dw10_moist=_to_float_arr(model_df, 'wfl10HourMoisture'),
        dw1000_moist=_to_float_arr(model_df, 'wfl1000HourMoisture'),
        dw1=_to_float_arr(model_df, 'wfl1Hour'),
        dw10=_to_float_arr(model_df, 'wfl10Hour'),
        dw100=_to_float_arr(model_df, 'wfl100Hour'),
        dw3_6s=_to_float_arr(model_df, 'wfl3_6S'),
        dw6_9s=_to_float_arr(model_df, 'wfl6_9S'),
        dw9_20s=_to_float_arr(model_df, 'wfl9_20S'),
        dw20s=_to_float_arr(model_df, 'wfl20plusS'),
        dw3_6r=_to_float_arr(model_df, 'wfl3_6R'),
        dw6_9r=_to_float_arr(model_df, 'wfl6_9R'),
        dw9_20r=_to_float_arr(model_df, 'wfl9_20R'),
        dw20r=_to_float_arr(model_df, 'wfl20plusR'),
        hfi=_to_float_arr(model_df, 'hfi'),
        flame_res_time=_to_float_arr(model_df, 'flame_res_time_sec'),
        fuel_bed_depth=_to_float_arr(model_df, 'fuel_bed_depth_m', default=0.3),
        ambient_temp=_to_float_arr(model_df, 'temp', default=27.0),
        windspeed=_to_float_arr(model_df, 'instand_ws_mps', default=0.0),
        use_burnup=True,
        em_mode=em_mode,
        units=emissions_units,
        soil_heating=model_soil_heating,
        soil_family=_prepare_soil_family(model_df) if model_soil_heating else None,
        # num_workers fans this call out inside pyfofem. logging calls made from code that
        # actually runs in a ProcessPoolExecutor/multiprocessing worker never reach
        # error_handling's collecting handler in the parent process, so any future code moved
        # into a worker must not rely on logger.warning() showing up in the error report.
        num_workers=max(1, int(num_workers)),
        show_progress=True,
    )

    fofem_results_df = pd.DataFrame(results)
    helper.export_csv(fofem_results_df, os.path.join(out_dir, 'fofem_results_df_temp.csv'))

    model_df = model_df.drop(columns=['remove_hereafter'], errors='ignore')
    helper.export_csv(model_df, os.path.join(out_dir, 'merged_df_temp.csv'))

    final_df = pd.concat([model_df.reset_index(drop=True), fofem_results_df.reset_index(drop=True)], axis=1)
    # Unit-qualify pyfofem's raw physical result column names in the final analyst-facing
    # DataFrame/CSV only; the temp exports above keep the backend-native names.
    final_df = final_df.rename(columns=fofem_units.emissions_result_rename_map(emissions_units))
    final_df = _restore_plot_id(final_df, plotid_map)
    final_df = final_df.sort_values(by=['#PlotId', 'wx_date']).reset_index(drop=True)

    csv_out_path = os.path.join(out_dir, 'fofem_emissions_results.csv')
    helper.export_csv(final_df, csv_out_path)

    if return_df:
        return final_df

    return None


if __name__ == '__main__':
    examples_dir = helper.get_examples_dir(os.path.dirname(__file__))
    _in_fofem_consume_dir = os.path.join(examples_dir, 'results', 'fuel_analyst')
    _in_fire_data_dir = os.path.join(examples_dir, 'results', 'fofem_mortality')
    _out_dir = os.path.join(examples_dir, 'results', 'fofem_emissions')

    _plot_wx_fire_csv_path = os.path.join(_in_fire_data_dir, 'fofem_severity_results.csv')
    _fofem_consume_csv_path = os.path.join(_in_fofem_consume_dir, fofem_units.consume_filename('SI'))
    _plot_id_col_name = 'unique_id'

    process_emissions(
        plot_wx_fire_csv_path=_plot_wx_fire_csv_path,
        plot_id_col_name=_plot_id_col_name,
        fofem_consume_csv_path=_fofem_consume_csv_path,
        out_dir=_out_dir,
        emissions_mode='legacy',
        model_soil_heating=False,
        num_workers=max(1, (os.cpu_count() or 2) - 1),
    )
