# -*- coding: utf-8 -*-
"""
Created on Sun Feb 2, 11:15:00 2026

@author: Gregory A. Greene
"""
__author__ = ['Gregory A. Greene, map.n.trowel@gmail.com']

import os
from numpy import array, column_stack, full, nan
import pandas as pd
from typing import Optional

import sys
pkg_dir = os.path.join(os.path.dirname(__file__), '..', '..')
if pkg_dir not in sys.path:
    sys.path.insert(0, pkg_dir)

from src.fuel_analyst.components import helper
from dependencies.conpyro.src.conpyro import conpyro
from dependencies.flame_components import flame_components as fc
import tqdm
import concurrent.futures
try:
    from tqdm.contrib.concurrent import process_map
    _TQDM_PROCESS_MAP_AVAILABLE = True
except ImportError:
    _TQDM_PROCESS_MAP_AVAILABLE = False


default_fire_modelling_dict = {
    'num_workers': max(1, int(os.cpu_count())-1),
    'conpyro': {
        'run_model': True,
        'plot_id_col_name': 'unique_id',
        'input_params': {
            'cfo_model': 5,  # Options: 1, 2, 3, 4, 5, 10, or string "use_csv" (assumes cfo_model column in csv)
            'sros_model': 13,  # Options: 1, 2, 3, 4, 12, 13, 20, or string "use_csv" (assumes sros_model column in csv)
            'cros_model': 1,  # Options: 1, 2, or string "use_csv" (assumes cros_model column in csv)
            'smooth_ros': True,
            'model_terrain_effects_on_wind': True,  # Toggle terrain (slope/aspect) effects on wind speed and direction
            'model_terrain_effects_on_ffmc': True,  # Toggle terrain (slope/aspect) effects on FFMC
            'suppress_messages': True,              # Toggle ConPyro processing messages on/off
            'wx_date': 'use_csv',   # Options: Integer in format YYYYMMDD, or string "use_csv" (default)
                                    #    wx_date used for fine dead fuel and ladder foliar MC calculations
            'fmc': None,            # Options: float, integer, None (default)
                                    #     fmc overrides wx_date for foliar MC calculations
            'season': None,         # Options: None (default), "Spring", "Summer", "Fall", "use_csv";
                                    #     season overrides wx_date for fine dead fuel MC calculations
            'time': None,           # Options: Integer in format HHMM, None (default), or string "use_csv"
                                    #     time is only needed for CFIS (cfo_model == 10) to calculate
                                    #     Rothermel dead fuel moisture content at a specific time of day
        },
        'output_params': {
            'out_request': [
                'mc_sa', 'mc_dmc', # Needed for FOFEM emissions modelling
                'fsg', 'cac', 'cfo_prob',
                'sros', 'cros', 'hros', 'bros',
                'tfc', 'sfi', 'cfi', 'hfi',
                'cfb', 'fire_type'
            ],
            # Leave flame_comp_out_list fixed for the time being - do not let user adjust
            'flame_comp_out_list': [
                'instand_ws', 'flame_length_m', 'flame_tilt', 'flame_height', 'flame_res_time', 'flame_depth'
            ],
        },
    },
    'fofem_mortality': {
        'run_model': True,
        'plot_id_col_name': 'unique_id',
        'fofem_tree_id_col_name': 'unique_id',
    },
    'fofem_emissions': {
        'run_model': True,
        'plot_id_col_name': 'unique_id',
    },
}


def _calc_instand_ws(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate in-stand wind speed.

    :param df: DataFrame with required columns: 'ws', 'canopy_cover', 'ht_ovrstry_live', 'fsg'.
    :return: DataFrame with new in-stand wind speed values.
    """
    # Verify that required columns exist
    required_cols = ['ws', 'canopy_cover', 'ht_ovrstry_live', 'fsg']
    missing_cols = set(required_cols) - set(df.columns)
    if missing_cols:
        raise ValueError(f'Required columns for in-stand wind speed calculation not found in DataFrame: {missing_cols}')

    # Calculate in-stand wind speed
    df['instand_ws_model'] = pd.Series([nan] * len(df), dtype='object')
    df['instand_ws_mps'] = full(len(df), nan)
    # Use Albini and Baughman (1979) model
    valid_mask = df[required_cols].notna().all(axis=1)
    df.loc[valid_mask, 'instand_ws_model'] = 'Albini and Baughman (1979)'
    df.loc[valid_mask, 'instand_ws_mps'] = fc.getMidFlameWS(
        wind_speed = df.loc[valid_mask, 'ws'].to_numpy(),
        canopy_cover = df.loc[valid_mask, 'canopy_cover'].to_numpy(),
        canopy_ht = df.loc[valid_mask, 'ht_ovrstry_live'].to_numpy(),
        canopy_baseht = df.loc[valid_mask, 'fsg'].to_numpy(),
        units = 'SI'
    )

    return df


def _calc_flame_length_m(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate flame length using FLAME components.

    :param df: DataFrame with required columns.
    :return: Series with flame length values.
    """
    # Verify that required columns exist
    required_cols = ['fire_type', 'hfi', 'ht_ovrstry_live']
    missing_cols = set(required_cols) - set(df.columns)
    if missing_cols:
        raise ValueError(f'Required columns for flame length calculation not found in DataFrame: {missing_cols}')

    # Model flame length
    df['flame_length_model'] = pd.Series([nan] * len(df), dtype='object')
    df['flame_length_m'] = full(len(df), nan)

    # Use Butler_HEAD model for crown fires (add value to stand height)
    crown_fire = (df['fire_type'] == 3) & (df['hfi'] >= 0)
    df.loc[crown_fire, 'flame_length_model'] = 'Butler et al. (2004)'
    df.loc[crown_fire, 'flame_length_m'] = fc.getFlameLength(
        model='Butler_HEAD',
        fire_intensity=df.loc[crown_fire, 'hfi'].to_numpy()
    ) + df.loc[crown_fire, 'ht_ovrstry_live'].to_numpy()

    # Use Byram_HEAD model for other fires
    other_fire = (df['fire_type'] != 3) & (df['hfi'] >= 0)
    df.loc[other_fire, 'flame_length_model'] = 'Byram (1959)'
    df.loc[other_fire, 'flame_length_m'] = fc.getFlameLength(
        model='Byram_HEAD',
        fire_intensity=df.loc[other_fire, 'hfi'].to_numpy()
    )

    return df


def _calc_flame_height(df: pd.DataFrame,
                       fh_model: str = 'Nelson',
                       recalc_crown_fire: bool = False) -> pd.DataFrame:
    """
    Calculate flame height using the Nelson model.

    :param df: DataFrame with required columns.
    :param fh_model: Model used to estimate flame height ("Nelson" only currently supported).
    :param recalc_crown_fire: If True, recalculate existing crown fire flame heights using Finney model.
    :return: DataFrame with flame height values.
    """
    if recalc_crown_fire:
        # Verify that required columns for the Finney model exist
        required_cols = ['flame_length_m', 'flame_tilt_deg', 'slope']
        missing_cols = set(required_cols) - set(df.columns)
        if missing_cols:
            raise ValueError(f'Required columns for flame length calculation not found in DataFrame: {missing_cols}')

        # Use Finney model for crown fires only
        crown_fire = (df['fire_type'] == 3) & (df['hfi'] >= 0)
        df.loc[crown_fire, 'flame_ht_model'] = 'Finney and Martin (1992)'
        df.loc[crown_fire, 'flame_ht_m'] = fc.getFlameHeight(
            model='Finney',
            flame_length=df.loc[crown_fire, 'flame_length_m'].to_numpy(),
            flame_tilt=df.loc[crown_fire, 'flame_tilt_deg'].to_numpy(),
            slope_angle=df.loc[crown_fire, 'slope'].to_numpy(),
            slope_units='percent'
        )
    else:
        # Verify that required columns for the Nelson model exist
        required_cols = ['fire_type', 'hfi', 'instand_ws_mps', 'flame_length_m']
        missing_cols = set(required_cols) - set(df.columns)
        if missing_cols:
            raise ValueError(f'Required columns for flame length calculation not found in DataFrame: {missing_cols}')

        # Calculate flame height
        df['flame_ht_model'] = pd.Series([nan] * len(df), dtype='object')
        df['flame_ht_m'] = full(len(df), nan)
        # Use Nelson model
        nelson_model = df['instand_ws_mps'].notna() & df['hfi'].notna() & df['fire_type'].notna()
        df.loc[nelson_model, 'flame_ht_model'] = 'Nelson and Adkins (1986)'
        df.loc[nelson_model, 'flame_ht_m'] = fc.getFlameHeight(
            model='Nelson',
            flame_length=df.loc[nelson_model, 'flame_length_m'].to_numpy(),
            fire_type=df.loc[nelson_model, 'fire_type'].to_numpy(),
            fire_intensity=df.loc[nelson_model, 'hfi'].to_numpy(),
            midflame_ws=df.loc[nelson_model, 'instand_ws_mps'].to_numpy()
        )

    return df


def _calc_flame_tilt(df: pd.DataFrame) -> pd.Series:
    """
    Calculate flame tilt using FLAME components.

    :param df: DataFrame with required columns.
    :return: Series with flame tilt values.
    """
    # Verify that required columns exist
    required_cols = ['fire_type', 'hfi']
    missing_cols = set(required_cols) - set(df.columns)
    if missing_cols:
        raise ValueError(f'Required columns for flame tilt calculation not found in DataFrame: {missing_cols}')

    # Calculate flame tilt
    df['flame_tilt_model'] = pd.Series([nan] * len(df), dtype='object')
    df['flame_tilt_deg'] = full(len(df), nan)
    # Use Butler model for crown fires
    butler_model = (df['fire_type'] == 3) & (df['hfi'] >= 0)
    df.loc[butler_model, 'flame_tilt_model'] = 'Butler et al. (2004)'
    df.loc[butler_model, 'flame_tilt_deg'] = fc.getFlameTilt(
        model='Butler',
        wind_speed=df.loc[butler_model, 'ws'].to_numpy(),
        wind_speed_units='kph',
        canopy_ht=df.loc[butler_model, 'ht_ovrstry_live'].to_numpy()
    )

    # Use Standard model if slope is less than 10% and not a crown fire
    standard_model = (df['fire_type'] != 3) & (df['hfi'] >= 0) & (df['slope'] <= 10)
    df.loc[standard_model, 'flame_tilt_model'] = 'Standard Geometry'
    df.loc[standard_model, 'flame_tilt_deg'] = fc.getFlameTilt(
        model='Standard',
        flame_length=df.loc[standard_model, 'flame_length_m'].to_numpy(),
        flame_height=df.loc[standard_model, 'flame_ht_m'].to_numpy()
    )

    # Use Finney model if slope is greater than 10% and not a crown fire
    finney_model = (df['fire_type'] != 3) & (df['hfi'] >= 0) & (df['slope'] > 10)
    df.loc[finney_model, 'flame_tilt_model'] = 'Finney and Martin (1992)'
    df.loc[finney_model, 'flame_tilt_deg'] = fc.getFlameTilt(
        model='Finney',
        flame_length=df.loc[finney_model, 'flame_length_m'].to_numpy(),
        flame_height=df.loc[finney_model, 'flame_ht_m'].to_numpy(),
        slope_angle=df.loc[finney_model, 'slope'].to_numpy(),
        slope_units='percent'
    )

    return df


def _calc_flame_res_time(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate flame residence time using FLAME components.

    :param df: DataFrame with required columns.
    :return: DataFrame with flame residence time values.
    """
    # Verify that required columns exist
    required_cols = ['hros', 'tfc', 'instand_ws_mps']
    missing_cols = set(required_cols) - set(df.columns)
    if missing_cols:
        raise ValueError(f'Required columns for flame resident time calculation not found in DataFrame: {missing_cols}')

    # Calculate flame residence time
    df['flame_res_time_model'] = pd.Series([nan] * len(df), dtype='object')
    df['flame_res_time_min'] = full(len(df), nan)
    df['flame_res_time_sec'] = full(len(df), nan)
    # Use Nelson and Adkins (1988) model
    valid_mask = df[required_cols].notna().all(axis=1)
    df.loc[valid_mask, 'flame_res_time_model'] = 'Nelson and Adkins (1988)'
    df.loc[valid_mask, 'flame_res_time_min'] = fc.getFlameResidenceTime(
        ros=df.loc[valid_mask, 'hros'].to_numpy(),
        fuel_consumption=df.loc[valid_mask, 'tfc'].to_numpy(),
        midflame_ws=df.loc[valid_mask, 'instand_ws_mps'].to_numpy(),
        units='min'
    )
    df.loc[valid_mask, 'flame_res_time_sec'] = df.loc[valid_mask, 'flame_res_time_min'] * 60

    return df


def _calc_flame_depth(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate flame depth using FLAME components.

    :param df: DataFrame with required columns.
    :return: DataFrame with flame depth values.
    """
    # Verify that required columns exist
    required_cols = ['hros', 'flame_res_time_min']
    missing_cols = set(required_cols) - set(df.columns)
    if missing_cols:
        raise ValueError(f'Required columns for flame depth calculation not found in DataFrame: {missing_cols}')

    # Calculate flame depth
    df['flame_depth_model'] = pd.Series([nan] * len(df), dtype='object')
    df['flame_depth_m'] = full(len(df), nan)
    # Use Fons et al. (1963) model
    valid_mask = df[required_cols].notna().all(axis=1)
    df.loc[valid_mask, 'flame_depth_model'] = 'Fons et al. (1963)'
    df.loc[valid_mask, 'flame_depth_m'] = fc.getFlameDepth(
        ros=df.loc[valid_mask, 'hros'].to_numpy(),
        res_time=df.loc[valid_mask, 'flame_res_time_min'].to_numpy(),
    )

    return df


def _single_run_fire_behavior(args):
    wx_date, time, subset_df, input_params, conpyro_out_list = args
    cp = conpyro.ConPyro()
    cp.initialize(
        cfo_model=(input_params['cfo_model'] if input_params['cfo_model'] != 'use_csv' else subset_df['cfo_model'].values.astype(int)),
        sros_model=(input_params['sros_model'] if input_params['sros_model'] != 'use_csv' else subset_df['sros_model'].values.astype(int)),
        cros_model=(input_params['cros_model'] if input_params['cros_model'] != 'use_csv' else subset_df['cros_model'].values.astype(int)),
        smooth_ros=bool(input_params['smooth_ros']),
        model_terrain_effects_on_wind=bool(input_params['model_terrain_effects_on_wind']),
        model_terrain_effects_on_ffmc=bool(input_params['model_terrain_effects_on_ffmc']),
        season=(input_params['season'] if input_params['season'] != 'use_csv' else subset_df['season'].values.astype(str)),
        density=subset_df['stand_density'].values.astype(str),
        stand_type=subset_df['stand_type'].values.astype(str),
        cbd=subset_df['cbd_ovrstry'].values,
        cfl_ovrstry=subset_df['cfl_ovrstry'].values,
        fsg=subset_df['fsg'].values,
        ffl=subset_df[['duff_fuel_load', 'litter_fuel_load']].sum(axis=1).values,
        wfl=subset_df['woody_fuel_load'].values,
        gfl=subset_df['herbaceous_fuel_load'].values,
        ws=subset_df['ws'].values,
        wd=subset_df['wd'].values,
        slope=subset_df['slope'].values,
        aspect=subset_df['aspect'].values,
        wx_date=wx_date,
        ffmc=subset_df['ffmc'].values,
        dmc=subset_df['dmc'].values,
        bui=subset_df['bui'].values,
        fuel_type=subset_df['fbp_fuel_type'].values.astype(str),
        pct_cnfr=subset_df['pct_cnfr'].values,
        ht_midstry_live=None, #subset_df['ht_midstry_live'].values,
        ht_midstry_dead=None, #subset_df['ht_midstry_dead'].values,
        cbh_ovrstry=None, #subset_df['cbh_ovrstry'].values,
        cbh_midstry=None, #subset_df['cbh_midstry'].values,
        cfl_midstry=None, #subset_df['cfl_midstry'].values,
        dead_branch_fl=None, #subset_df['dead_branch_fl'].values,
        fmc=(input_params['fmc'] if input_params['fmc'] != 'use_csv' else subset_df['fmc'].values.astype(float)),
        time=time,
        temp=subset_df['temp'].values,
        rh=subset_df['rh'].values,
        cc=subset_df['canopy_cover'].values,
        site_elev=subset_df['elevation'].values,
        stn_elev=subset_df['elevation'].values,
        elevation=subset_df['elevation'].values,
        slope=subset_df['slope'].values,
        aspect=subset_df['aspect'].values,
        lat=subset_df['lat'].values,
        long=subset_df['long'].values,
        suppress_messages=input_params['suppress_messages'],
    )
    cp.run_conpyro()
    temp_df = pd.DataFrame(
        column_stack(array(cp.return_params(out_request=conpyro_out_list), dtype=object)),
        columns=conpyro_out_list
    )
    subset_df = subset_df.drop(columns=[col for col in subset_df.columns if col in temp_df.columns], errors='ignore')
    subset_df = subset_df.reset_index(drop=True)
    subset_df = pd.concat([subset_df, temp_df], axis=1)
    del cp, temp_df
    return subset_df


def _model_fire_behavior(
        df: pd.DataFrame,
        input_params: dict,
        conpyro_out_list: list,
        conpyro_params: dict,
        num_workers: int = 1
) -> pd.DataFrame:
    """
    Run ConPyro for each weather date and time combination and return the resulting DataFrame.

    :param df: Input DataFrame with required columns.
    :param input_params: Dictionary of input parameters for ConPyro.
    :param conpyro_out_list: List of output parameters to request from ConPyro.
    :param conpyro_params: Dictionary of ConPyro model parameters.
    :param num_workers: Number of parallel workers to use (default 1 = no multiprocessing).
    :return: DataFrame with ConPyro results.
    """
    # Prepare all combinations
    wx_dates = (
        input_params['wx_date'] if isinstance(input_params['wx_date'], list)
        else [input_params['wx_date']] if isinstance(input_params['wx_date'], (int, type(None)))
        else list(set(df['wx_date'].astype(int)))
    )
    times = (
        input_params['time'] if isinstance(input_params['time'], list)
        else [input_params['time']] if isinstance(input_params['time'], (int, type(None)))
        else list(set(df['wx_date'].astype(int)))
    )
    tasks = []
    for wx_date in wx_dates:
        for time in times:
            subset_df = (df[(df['wx_date'] == wx_date)] if input_params['wx_date'] == 'use_csv' else df)
            subset_df = (subset_df[(subset_df['time'] == time)] if input_params['time'] == 'use_csv' else subset_df)
            tasks.append((wx_date, time, subset_df.copy(), input_params, conpyro_out_list))

    if num_workers > 1:
        if _TQDM_PROCESS_MAP_AVAILABLE:
            results = process_map(_single_run_fire_behavior, tasks, max_workers=num_workers, desc='ConPyro', chunksize=1)
        else:
            with concurrent.futures.ProcessPoolExecutor(max_workers=num_workers) as executor:
                results = list(tqdm.tqdm(executor.map(_single_run_fire_behavior, tasks), total=len(tasks), desc='ConPyro'))
    else:
        results = [
            _single_run_fire_behavior(task) for task in tqdm.tqdm(tasks, desc='ConPyro')
        ]
    df = pd.concat(results, ignore_index=True)
    for col in df.select_dtypes(include=['object']).columns:
        try:
            df[col] = pd.to_numeric(df[col])
        except ValueError:
            pass
    df = df.sort_values(by=[conpyro_params['plot_id_col_name'], 'wx_date']).reset_index(drop=True)

    return df


def _model_flame_components(df: pd.DataFrame, flame_comp_out_list: list) -> pd.DataFrame:
    """
    Model flame components using ConPyro output fire behavior parameters.

    :param df: DataFrame with ConPyro output parameters.
    :param flame_comp_out_list: List of flame component variables to calculate and add to the DataFrame.
    :return: DataFrame with additional flame component columns.
    """
    # Calculate in-stand wind speed (km/h)
    print('\tCalculating in-stand wind speed...')
    df = _calc_instand_ws(df)

    # Calculate flame length (m)
    print('\tCalculating flame length...')
    df = _calc_flame_length_m(df)

    # Calculate flame height (m)
    print('\tCalculating flame height...')
    df = _calc_flame_height(df)

    # Calculate flame tilt (degrees)
    print('\tCalculating flame tilt...')
    df = _calc_flame_tilt(df)

    # Recalculate crown fire flame ht using tilt values
    print('\tRecalculating flame height for crown fires using new tilt values...')
    df = _calc_flame_height(df, recalc_crown_fire=True)

    # Calculate flame residence time
    print('\tCalculating flame residence time...')
    df = _calc_flame_res_time(df)

    # Calculate flame depth
    print('\tCalculating flame depth...')
    df = _calc_flame_depth(df)

    return df


def _model_fofem_emissions(
        df: pd.DataFrame,
        fire_csv_path: str,
        fofem_emissions_params: dict,
        in_fofem_consume_csv_path: str,
        out_dir: str,
        conpyro_params: dict,
        num_workers: int = 1,
) -> pd.DataFrame:
    """
    Run FOFEM emissions modelling and merge results with the input DataFrame.

    :param df: DataFrame with plot-level fire behavior results from ConPyro.
    :param fire_csv_path: Path to the CSV file with fire behavior results.
    :param fofem_emissions_params: Dictionary of FOFEM emissions model parameters.
    :param in_fofem_consume_csv_path: Path to the input CSV file containing FOFEM fuel
        consumption data for emissions modelling.
    :param out_dir: Directory to save FOFEM emissions output files.
    :param conpyro_params: Dictionary of ConPyro model parameters.
    :param num_workers: Number of parallel workers to use (default 1 = no multiprocessing).
    :return: DataFrame with FOFEM emissions results merged.
    """
    from src.fuel_analyst.components import fofem_emissions as fe

    # Create FOFEM emissions output directory and remove any existing files if it already exists
    emissions_dir = os.path.join(out_dir, 'fofem_emissions')
    os.makedirs(emissions_dir, exist_ok=True)
    helper.delete_files(emissions_dir)

    # Run FOFEM emissions modelling with the plot-level fire behavior results from ConPyro
    emiss_df = fe.process_emissions(
        plot_wx_fire_csv_path=fire_csv_path,
        plot_id_col_name=fofem_emissions_params['plot_id_col_name'],
        fofem_consume_csv_path=in_fofem_consume_csv_path,
        out_dir=emissions_dir,
        num_workers=num_workers,
        return_df=True,
    )

    # Merge emissions results back to original plot_fire_df to preserve all columns
    df = pd.merge(
        df,
        emiss_df,
        left_on=[conpyro_params['plot_id_col_name'], 'wx_date'],
        right_on=['#PlotId', 'wx_date'],
        how='left',
        suffixes=('', '_fofem_emissions'),
    )

    # Drop columns with "_fofem_emissions" suffix
    df = df.drop(columns=['#PlotId'] + [col for col in df.columns if col.endswith('_fofem_emissions')])

    return df


def _model_fofem_mortality(
        df: pd.DataFrame,
        fire_csv_path: str,
        in_tree_csv_path: str,
        out_dir: str,
        fofem_mortality_params: dict,
        conpyro_params: dict,
) -> pd.DataFrame:
    """
    Run FOFEM mortality modelling and merge results with the input DataFrame.

    :param df: DataFrame with plot-level fire behavior results from ConPyro.
    :param fire_csv_path: Path to the CSV file with fire behavior results.
    :param in_tree_csv_path: Path to the input CSV file containing tree data for FOFEM mortality modelling.
    :param out_dir: Directory to save FOFEM mortality output files.
    :param fofem_mortality_params: Dictionary of FOFEM mortality model parameters.
    :param conpyro_params: Dictionary of ConPyro model parameters.
    :return: DataFrame with FOFEM mortality results merged.
    """
    from src.fuel_analyst.components import fofem_mortality as fm

    # Create FOFEM mortality output directory and remove any existing files if it already exists
    mortality_dir = os.path.join(out_dir, 'fofem_mortality')
    os.makedirs(mortality_dir, exist_ok=True)
    helper.delete_files(mortality_dir)

    # Run FOFEM mortality modelling with the plot-level fire behavior results from ConPyro
    tree_mort_df, severity_df = fm.process_mortality(
        plot_wx_fire_csv_path=fire_csv_path,
        fofem_tree_csv_path=in_tree_csv_path,
        out_dir=mortality_dir,
        plot_id_col_name=fofem_mortality_params['plot_id_col_name'],
        fofem_tree_id_col_name=fofem_mortality_params['fofem_tree_id_col_name'],
        return_dfs=True
    )
    del tree_mort_df

    # Merge severity results back to original plot_fire_df to preserve all columns
    df = pd.merge(
        df,
        severity_df,
        left_on=[conpyro_params['plot_id_col_name'], 'wx_date'],
        right_on=[fofem_mortality_params['plot_id_col_name'], 'wx_date'],
        how='left',
        suffixes=('', '_fofem_mortality'),
    )

    # Drop columns with "_fofem_mortality" suffix
    df = df.drop(columns=[col for col in df.columns if col.endswith('_fofem_mortality')])

    return df


def run_conpyro(
        out_dir: str,
        in_conpyro_csv_path: str,
        in_tree_csv_path: Optional[str] = None,
        in_fofem_consume_csv_path: Optional[str] = None,
        fire_modelling_params: Optional[dict] = None
) -> None:
    """
    Run ConPyro with the test datasets.

    :param out_dir: Directory to save output CSV files.
    :param in_conpyro_csv_path: Path to the input CSV file containing required columns for ConPyro.
        If only running FOFEM mortality or emissions modelling, this should be the path to a CSV file with
        ConPyro results.
    :param in_tree_csv_path: Optional path to the input CSV file containing tree data for
        FOFEM mortality modelling.
    :param in_fofem_consume_csv_path: Optional path to the input CSV file containing
        FOFEM fuel consumption data for emissions modelling.
    :param fire_modelling_params: Optional dictionary containing fire modelling parameters for ConPyro,
        FOFEM mortality, and FOFEM emissions modelling.
    :return: None
    """
    # Ensure the output directory exists
    os.makedirs(out_dir, exist_ok=True)

    # Set default fire modelling parameters if not provided
    if fire_modelling_params is None:
        fire_modelling_params = default_fire_modelling_dict

    # Get ConPyro, FOFEM mortality, and FOFEM emissions parameters from fire_modelling_params
    num_workers = fire_modelling_params['num_workers']
    conpyro_params = fire_modelling_params['conpyro']
    fofem_mortality_params = fire_modelling_params['fofem_mortality']
    fofem_emissions_params = fire_modelling_params['fofem_emissions']

    # Get modelling parameters
    input_params = conpyro_params['input_params']
    conpyro_out_list = conpyro_params['output_params']['out_request']
    flame_comp_out_list = conpyro_params['output_params']['flame_comp_out_list']

    if conpyro_params['run_model']:
        # Create fire behavior output directory and remove any existing files if it already exists
        fire_dir = os.path.join(out_dir, 'fire_behavior')
        os.makedirs(fire_dir, exist_ok=True)
        helper.delete_files(fire_dir)

        # Get dataframe of plot data for ConPyro modelling
        df = pd.read_csv(in_conpyro_csv_path, low_memory=False)

        # Drop rows with empty values in required columns
        drop_empty_rows_in_cols = ['stand_density', 'stand_type']
        for col in drop_empty_rows_in_cols:
            df = df[df[col].notna()]

        # ### MODEL FIRE BEHAVIOR WITH CONPYRO ###
        print('\n>>>> Running ConPyro...')
        df = _model_fire_behavior(
            df=df,
            input_params=input_params,
            conpyro_out_list=conpyro_out_list,
            conpyro_params=conpyro_params,
            num_workers=num_workers,
        )

        # ### MODEL FLAME COMPONENTS ###
        print('\n>>>> Modeling flame components with ConPyro output...')
        df = _model_flame_components(df, flame_comp_out_list)

        # Save ConPyro results to CSV
        fire_csv_path = os.path.join(fire_dir, 'conpyro_results.csv')
        print(f'\tSaving results to {fire_csv_path}...')
        helper.export_csv(df, fire_csv_path)
    else:
        if os.path.exists(in_conpyro_csv_path):
            print(f'\nLoading existing ConPyro results from {in_conpyro_csv_path}...')
            df = pd.read_csv(in_conpyro_csv_path, low_memory=False)
            fire_csv_path = in_conpyro_csv_path
        else:
            raise FileNotFoundError(f'ConPyro results CSV not found at {in_conpyro_csv_path}.'
                                    f'Please run ConPyro model first or provide existing results CSV.')

    fofem_ext = ''
    # ### MODEL FOFEM MORTALITY (IF ENABLED) ###
    if fofem_mortality_params['run_model']:
        print('\n>>>> Running FOFEM mortality modelling...')
        if in_tree_csv_path is not None:
            df = _model_fofem_mortality(
                df=df,
                fire_csv_path=fire_csv_path,
                in_tree_csv_path=in_tree_csv_path,
                out_dir=out_dir,
                fofem_mortality_params=fofem_mortality_params,
                conpyro_params=conpyro_params,
            )
            fofem_ext += '_mortality'
        else:
            raise ValueError('The in_tree_csv_path parameter was not provided. '
                             'Unable to run FOFEM mortality modelling')

    # ### MODEL FOFEM EMISSIONS (IF ENABLED) ###
    if fofem_emissions_params['run_model']:
        print('\n>>>> Running FOFEM emissions modelling...')
        if in_fofem_consume_csv_path is not None:
            df = _model_fofem_emissions(
                df=df,
                fire_csv_path=fire_csv_path,
                fofem_emissions_params=fofem_emissions_params,
                in_fofem_consume_csv_path=in_fofem_consume_csv_path,
                out_dir=out_dir,
                conpyro_params=conpyro_params,
                num_workers=num_workers,
            )
            fofem_ext += '_emissions'
        else:
            raise ValueError('The in_fofem_consume_csv_path parameter was not provided. '
                             'Unable to run FOFEM emissions modelling')

    # ### SAVE FINAL RESULTS TO CSV ###
    if fofem_mortality_params['run_model'] or fofem_emissions_params['run_model']:
        out_csv_path = os.path.join(out_dir, f'conpyro{fofem_ext}_results.csv')
        print(f'\nSaving final modelling results to {out_csv_path}...')
        # Sort by plot_id_col_name and wx_date
        df = df.sort_values(by=[conpyro_params['plot_id_col_name'], 'wx_date']).reset_index(drop=True)
        # Save final DataFrame to CSV
        helper.export_csv(df, out_csv_path)

    return


# Test routine for ConPyro modelling
if __name__ == '__main__':
    # Define input and output folders
    # test_dir = os.path.join(os.path.dirname(__file__), 'tests')
    test_dir = r'E:\UBC_FuelAnalyst_Testing\Student_Data\AFN'
    _out_dir = os.path.join(test_dir, 'results', 'conpyro')
    # The ConPyro input dataframe must have weather data attached for ConPyro/FOFEM modelling
    # Required weather columns for ConPyro modelling: 'ws', 'wd', 'ffmc', 'dmc', 'bui', 'temp', 'rh'
    # Required weather columns for FOFEM mortality modelling: 'ws', 'temp'
    _in_dir = os.path.join(test_dir, 'results', 'wx_extract')
    _in_conpyro_csv_path = os.path.join(_in_dir, 'conpyro_df_wx.csv')
    _tree_csv_path = os.path.join(test_dir, 'results', 'fuel_analyst', 'master_tree_df.csv')
    _fofem_consume_csv_path = os.path.join(test_dir, 'results', 'fuel_analyst', 'fofem_consume_df.csv')
    _fire_modelling_dict = None

    # Run ConPyro modelling
    run_conpyro(
        out_dir=_out_dir,
        in_conpyro_csv_path=_in_conpyro_csv_path,
        in_tree_csv_path=_tree_csv_path,
        in_fofem_consume_csv_path=_fofem_consume_csv_path,
        fire_modelling_params=_fire_modelling_dict,
    )