# -*- coding: utf-8 -*-
"""
Created on Sun Feb 2, 11:15:00 2026

@author: Gregory A. Greene
"""
__author__ = ['Gregory A. Greene']

import os
from numpy import array, column_stack, full, nan
import pandas as pd
from typing import Optional

from .components import error_handling
from .components import fofem_units
from .components import helper
from conpyro import conpyro
import flame_components as fc
import tqdm
import concurrent.futures
try:
    from tqdm.contrib.concurrent import process_map
    _TQDM_PROCESS_MAP_AVAILABLE = True
except ImportError:
    _TQDM_PROCESS_MAP_AVAILABLE = False

# Matches pyfofem's Burnup _FIRE_BOUNDS['ti'] (surface fire residence time,
# seconds) -- dependencies/pyfofem/src/pyfofem/components/burnup.py. Below
# the min, Burnup hard-fails (BurnupError 11) and silently skips the
# consumption/emissions merge; above the max, Burnup already clips
# internally. Re-verify these against pyfofem if it's updated.
_FOFEM_MIN_FLAME_RES_TIME_S = 10.0
_FOFEM_MAX_FLAME_RES_TIME_S = 200.0


default_fire_modelling_dict = {
    'num_workers': max(1, os.cpu_count()-1),
    'conpyro': {
        'run_model': True,
        'plot_id_col_name': 'unique_id',
        'input_params': {
            'cfo_model': 5,    # Options: 1, 2, 3, 4, 5, 10, or string "use_csv" (assumes cfo_model column in csv)
            'sros_model': 13,  # Options: 1, 2, 3, 4, 12, 13, 20, or string "use_csv" (assumes sros_model column in csv)
            'cros_model': 1,   # Options: 1, 2, or string "use_csv" (assumes cros_model column in csv)
            'process_ladder': False,     # Toggle ladder fuel processing on/off
            'smooth_ros': True,          # Toggle ROS smoothing function on/off
            'model_terrain_effects_on_wind': True,  # Toggle terrain (slope/aspect) effects on wind speed and direction
            'model_terrain_effects_on_ffmc': True,  # Toggle terrain (slope/aspect) effects on FFMC
            'suppress_messages': True,              # Toggle ConPyro processing messages on/off
            'wx_date': 'use_csv',   # Options: Integer in format YYYYMMDD, or string "use_csv" (default)
                                    #    wx_date used for fine dead fuel and ladder foliar MC calculations
            'fmc': None,            # Options: float, integer, None (default)
                                    #     fmc overrides wx_date for foliar MC calculations
            'season': None,         # Options: None (default), "Sp", "Sp-Su", "T", "Su", "F", "use_csv";
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
                'sfc', 'cfc', 'tfc',
                'sfi', 'cfi', 'hfi',
                'cfb', 'fire_type'
            ],
            # Leave flame_comp_out_list fixed for the time being - do not let user adjust
            'flame_comp_out_list': [
                'instand_ws', 'flame_length_m', 'flame_tilt', 'flame_height', 'flame_res_time', 'flame_depth'
            ],
        },
    },
    'fofem_mortality': {
        'run_model': True,                      # Switch; Default: True
        'plot_id_col_name': 'unique_id',        # User defined; default: 'unique_id'
        'fofem_tree_id_col_name': 'unique_id',  # User defined; default: 'unique_id'
    },
    'fofem_emissions': {
        'run_model': True,                  # Switch; Default: True
        'model_select': 'pyfofem',          # Options: 'pyfofem', 'fof_gui'; Default: 'pyfofem'
                                            #     pyfofem uses the pyfofem Python package to model emissions
                                            #     fof_gui uses the USFS FOFEM GUI executable to batch model emissions
                                            #        using "legacy" (old) emissions calculation settings
        'plot_id_col_name': 'unique_id',    # User defined; default: 'unique_id'
        'emissions_mode': 'expanded',       # Emissions modelling modes for pyfofem
                                            #     Options: 'legacy', 'default', 'expanded'
        'model_soil_heating': False,        # If True, pass SoilFamily data to pyfofem soil-heating model
        'emissions_units': 'SI',            # Options: 'Imperial', 'SI'. Must match the unit system
                                            #     of in_fofem_consume_csv_path's own filename (see
                                            #     fofem_units.py) - validated against it before any
                                            #     backend runs. Set independently from, and not
                                            #     automatically synced with, fuel_analyst()'s own
                                            #     fofem_processing_units setting (a separate call,
                                            #     possibly a separate process); it is this setting
                                            #     and the consumption file it points to that must
                                            #     agree, not the two dictionaries themselves.
        'force_flame_res_time_limits': True,  # Clip flame_res_time_sec to FOFEM/Burnup's valid range
                                              #     (10-200s) instead of letting Burnup silently drop
                                              #     out-of-range scenarios from the emissions estimate
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
    df.loc[valid_mask, 'instand_ws_mps'] = fc.get_mid_flame_ws(
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
    df.loc[crown_fire, 'flame_length_m'] = fc.get_flame_length(
        model='Butler_HEAD',
        fire_intensity=df.loc[crown_fire, 'hfi'].to_numpy()
    ) + df.loc[crown_fire, 'ht_ovrstry_live'].to_numpy()

    # Use Byram_HEAD model for other fires
    other_fire = (df['fire_type'] != 3) & (df['hfi'] >= 0)
    df.loc[other_fire, 'flame_length_model'] = 'Byram (1959)'
    df.loc[other_fire, 'flame_length_m'] = fc.get_flame_length(
        model='Byram_HEAD',
        fire_intensity=df.loc[other_fire, 'hfi'].to_numpy()
    )

    return df


def _calc_flame_height(
        df: pd.DataFrame,
        fh_model: str = 'Nelson',
        recalc_crown_fire: bool = False
) -> pd.DataFrame:
    """
    Calculate flame height using the Nelson model.

    :param df: DataFrame with required columns.
    :param fh_model: Model used to estimate flame height (only "Nelson" & "Finney" models are currently supported).
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
        df.loc[crown_fire, 'flame_ht_m'] = fc.get_flame_height(
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
        df.loc[nelson_model, 'flame_ht_m'] = fc.get_flame_height(
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
    df.loc[butler_model, 'flame_tilt_deg'] = fc.get_flame_tilt(
        model='Butler',
        wind_speed=df.loc[butler_model, 'ws'].to_numpy(),
        wind_speed_units='kph',
        canopy_ht=df.loc[butler_model, 'ht_ovrstry_live'].to_numpy()
    )

    # Use Standard model if slope is less than 10% and not a crown fire
    standard_model = (df['fire_type'] != 3) & (df['hfi'] >= 0) & (df['slope'] <= 10)
    df.loc[standard_model, 'flame_tilt_model'] = 'Standard Geometry'
    df.loc[standard_model, 'flame_tilt_deg'] = fc.get_flame_tilt(
        model='Standard',
        flame_length=df.loc[standard_model, 'flame_length_m'].to_numpy(),
        flame_height=df.loc[standard_model, 'flame_ht_m'].to_numpy()
    )

    # Use Finney model if slope is greater than 10% and not a crown fire
    finney_model = (df['fire_type'] != 3) & (df['hfi'] >= 0) & (df['slope'] > 10)
    df.loc[finney_model, 'flame_tilt_model'] = 'Finney and Martin (1992)'
    df.loc[finney_model, 'flame_tilt_deg'] = fc.get_flame_tilt(
        model='Finney',
        flame_length=df.loc[finney_model, 'flame_length_m'].to_numpy(),
        flame_height=df.loc[finney_model, 'flame_ht_m'].to_numpy(),
        slope_angle=df.loc[finney_model, 'slope'].to_numpy(),
        slope_units='percent'
    )

    return df


def _calc_flame_res_time(df: pd.DataFrame, force_flame_res_time_limits: bool = True) -> pd.DataFrame:
    """
    Calculate flame residence time using FLAME components.

    Optionally clips the result to FOFEM/Burnup's valid residence-time
    range (see :data:`_FOFEM_MIN_FLAME_RES_TIME_S` /
    :data:`_FOFEM_MAX_FLAME_RES_TIME_S`) so out-of-range scenarios are
    adjusted rather than silently dropped from Burnup's consumption/
    emissions merge (``BurnupError`` 11 below the min; Burnup already
    clips internally above the max).

    :param df: DataFrame with required columns.
    :param force_flame_res_time_limits: If True (default), clip
        ``flame_res_time_sec`` values below :data:`_FOFEM_MIN_FLAME_RES_TIME_S`
        up to that minimum, and values above :data:`_FOFEM_MAX_FLAME_RES_TIME_S`
        down to that maximum.
    :return: DataFrame with flame residence time values, plus
        ``flame_res_time_sec_orig`` (the unclipped value) and
        ``flame_res_time_comment`` (set on rows that were clipped,
        blank/``NA`` elsewhere).
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
    df.loc[valid_mask, 'flame_res_time_min'] = fc.get_flame_residence_time(
        ros=df.loc[valid_mask, 'hros'].to_numpy(),
        fuel_consumption=df.loc[valid_mask, 'tfc'].to_numpy(),
        midflame_ws=df.loc[valid_mask, 'instand_ws_mps'].to_numpy(),
        units='min'
    )
    df.loc[valid_mask, 'flame_res_time_sec'] = df.loc[valid_mask, 'flame_res_time_min'] * 60

    df['flame_res_time_sec_orig'] = df['flame_res_time_sec']
    df['flame_res_time_comment'] = pd.Series([pd.NA] * len(df), dtype='object')
    if force_flame_res_time_limits:
        too_low = df['flame_res_time_sec'] < _FOFEM_MIN_FLAME_RES_TIME_S
        too_high = df['flame_res_time_sec'] > _FOFEM_MAX_FLAME_RES_TIME_S
        adjusted = (too_low | too_high) & df['flame_res_time_sec'].notna()
        df.loc[too_low, 'flame_res_time_sec'] = _FOFEM_MIN_FLAME_RES_TIME_S
        df.loc[too_high, 'flame_res_time_sec'] = _FOFEM_MAX_FLAME_RES_TIME_S
        df.loc[adjusted, 'flame_res_time_comment'] = (
            'Flame residence time values adjusted to fit within FOFEM limits'
        )
        # Keep flame_res_time_min consistent with the (possibly clipped)
        # seconds value, since _calc_flame_depth() consumes minutes.
        df.loc[adjusted, 'flame_res_time_min'] = df.loc[adjusted, 'flame_res_time_sec'] / 60

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
    df.loc[valid_mask, 'flame_depth_m'] = fc.get_flame_depth(
        ros=df.loc[valid_mask, 'hros'].to_numpy(),
        res_time=df.loc[valid_mask, 'flame_res_time_min'].to_numpy(),
    )

    return df


def _single_run_fire_behavior(args):
    """
    Run one ConPyro fire-behavior calculation for a weather date and time.

    :param args: Weather date, time, input subset, model parameters, and requested outputs.
    :return: ConPyro results for the supplied date and time.
    """
    wx_date, time, subset_df, input_params, conpyro_out_list = args
    cp = conpyro.ConPyro()
    cp.initialize(
        cfo_model=(input_params['cfo_model'] if input_params['cfo_model'] != 'use_csv' else subset_df['cfo_model'].values.astype(int)),
        sros_model=(input_params['sros_model'] if input_params['sros_model'] != 'use_csv' else subset_df['sros_model'].values.astype(int)),
        cros_model=(input_params['cros_model'] if input_params['cros_model'] != 'use_csv' else subset_df['cros_model'].values.astype(int)),
        smooth_ros=bool(input_params['smooth_ros']),
        model_terrain_effects_on_wind=bool(input_params['model_terrain_effects_on_wind']),
        model_terrain_effects_on_ffmc=bool(input_params['model_terrain_effects_on_ffmc']),
        process_ladder=input_params['process_ladder'],
        season=(input_params['season'] if input_params['season'] != 'use_csv' else subset_df['season'].to_numpy(dtype=str)),
        density=subset_df['stand_density'].to_numpy(dtype=str),
        stand_type=subset_df['stand_type'].to_numpy(dtype=str),
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
        fuel_type=(subset_df['fbp_fuel_type'].to_numpy(dtype=str) if subset_df['fbp_fuel_type'].notna().all() else None),
        pct_cnfr=subset_df['pct_cnfr'].values,
        ht_midstry_live=subset_df['ht_midstry_live'].values,
        ht_midstry_dead=subset_df['ht_midstry_dead'].values,
        cbh_ovrstry=subset_df['cbh_ovrstry'].values,
        cbh_midstry=subset_df['cbh_midstry'].values,
        cfl_midstry=subset_df['cfl_midstry'].values,
        dead_branch_fl=subset_df['dead_branch_fl_midstry'].values,
        fmc=(input_params['fmc'] if input_params['fmc'] != 'use_csv' else subset_df['fmc'].values.astype(float)),
        time=time,
        temp=subset_df['temp'].values,
        rh=subset_df['rh'].values,
        cc=subset_df['canopy_cover'].values,
        site_elev=subset_df['elevation'].values,
        stn_elev=subset_df['elevation'].values,
        elevation=subset_df['elevation'].values,
        lat=subset_df['lat'].values,
        long=subset_df['long'].values,
        d0=None,
        dj=None,
        sfc=None,
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
        else list(set(df['time'].astype(int)))
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


def _model_flame_components(
        df: pd.DataFrame,
        flame_comp_out_list: list,
        force_flame_res_time_limits: bool = True,
) -> pd.DataFrame:
    """
    Model flame components using ConPyro output fire behavior parameters.

    :param df: DataFrame with ConPyro output parameters.
    :param flame_comp_out_list: List of flame component variables to calculate and add to the DataFrame.
    :param force_flame_res_time_limits: Passed through to :func:`_calc_flame_res_time`.
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
    df = _calc_flame_res_time(df, force_flame_res_time_limits=force_flame_res_time_limits)

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
    :param fofem_emissions_params: Dictionary of FOFEM emissions model parameters, including
        'emissions_units' ('SI' or 'Imperial'; defaults to 'SI'). Validated against
        in_fofem_consume_csv_path's unit-bearing filename before either backend runs.
    :param in_fofem_consume_csv_path: Path to the input CSV file containing FOFEM fuel
        consumption data for emissions modelling. Its filename must be one of the canonical,
        unit-bearing names from fofem_units.consume_filename() and must match emissions_units.
    :param out_dir: Directory to save FOFEM emissions output files.
    :param conpyro_params: Dictionary of ConPyro model parameters.
    :param num_workers: Number of parallel workers to use (default 1 = no multiprocessing).
    :return: DataFrame with FOFEM emissions results merged.
    """
    # Create FOFEM emissions output directory and remove any existing files if it already exists
    emissions_dir = os.path.join(out_dir, 'fofem_emissions')
    os.makedirs(emissions_dir, exist_ok=True)
    helper.delete_files(emissions_dir)

    # Validate the configured units and the input file's unit-bearing filename before importing
    # or running either backend, so a mismatched/renamed file fails clearly upfront rather than
    # being silently misinterpreted (or surfacing as a per-row error deep inside a worker).
    emissions_units = fofem_units.validate_fofem_units(
        fofem_emissions_params.get('emissions_units', 'SI')
    )
    fofem_units.validate_consume_units(in_fofem_consume_csv_path, emissions_units)

    model_select = str(fofem_emissions_params.get('model_select', 'pyfofem')).strip().lower()
    if model_select == 'pyfofem':
        from .components import fofem_emissions as fe

        process_emissions_kwargs = {
            'plot_wx_fire_csv_path': fire_csv_path,
            'plot_id_col_name': fofem_emissions_params['plot_id_col_name'],
            'fofem_consume_csv_path': in_fofem_consume_csv_path,
            'out_dir': emissions_dir,
            'emissions_mode': fofem_emissions_params.get('emissions_mode', 'legacy'),
            'model_soil_heating': fofem_emissions_params.get('model_soil_heating', False),
            'emissions_units': emissions_units,
            'num_workers': num_workers,
            'return_df': True,
        }
    elif model_select == 'fof_gui':
        from .components import fofem_gui_emissions as fe

        process_emissions_kwargs = {
            'plot_wx_fire_csv_path': fire_csv_path,
            'plot_id_col_name': fofem_emissions_params['plot_id_col_name'],
            'fofem_consume_csv_path': in_fofem_consume_csv_path,
            'out_dir': emissions_dir,
            'model_soil_heating': fofem_emissions_params.get('model_soil_heating', False),
            'emissions_units': emissions_units,
            'num_workers': num_workers,
            'return_df': True,
        }
    else:
        raise ValueError(
            f'Invalid fofem_emissions model_select "{fofem_emissions_params.get("model_select")}". '
            f'Valid options are: ["pyfofem", "fof_gui"]'
        )

    # Run FOFEM emissions modelling with the plot-level fire behavior results from ConPyro
    emiss_df = fe.process_emissions(**process_emissions_kwargs)

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
    from .components import fofem_mortality as fm

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


@error_handling.run_guard
def run_conpyro(
        out_dir: str,
        in_conpyro_csv_path: str,
        in_tree_csv_path: Optional[str] = None,
        in_fofem_consume_csv_path: Optional[str] = None,
        fire_modelling_params: Optional[dict] = None
) -> None:
    """
    Run configured ConPyro, FOFEM mortality, and FOFEM emissions workflows.

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
    :return: None. Writes selected model outputs and run_conpyro_errors.csv.
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

        # Validate that required columns are present before running ConPyro.
        # Core weather columns must be merged in advance via extract_nrcan_wx -> merge_wx_data.
        # temp and rh are only required when cfo_model == 10 (CFIS model).
        # Additional columns are required for any input_params value set to 'use_csv'.
        required_cols = ['ws', 'wd', 'ffmc', 'dmc', 'bui']
        use_csv_params = ['wx_date', 'season', 'time', 'fmc', 'cfo_model', 'sros_model', 'cros_model']
        for param in use_csv_params:
            if input_params.get(param) == 'use_csv':
                required_cols.append(param)
        if input_params.get('cfo_model') == 10:
            required_cols.extend(['temp', 'rh'])
        missing_cols = helper.get_missing_df_columns(df, required_cols)
        if missing_cols:
            raise ValueError(
                f'Columns required by ConPyro are missing from the input CSV: {missing_cols}. '
                f'Weather columns (ws, wd, ffmc, dmc, bui) require running '
                f'extract_nrcan_wx -> merge_wx_data first. '
                f'temp and rh are additionally required when cfo_model == 10 (CFIS). '
                f'Columns corresponding to input_params set to "use_csv" must also be present.'
            )

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
        print('\n>>>> Modelling flame components with ConPyro output...')
        df = _model_flame_components(
            df,
            flame_comp_out_list,
            force_flame_res_time_limits=fofem_emissions_params.get('force_flame_res_time_limits', True),
        )

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

    error_report_path = os.path.join(out_dir, 'run_conpyro_errors.csv')
    print(f'\nSaving the Error Report to: {error_report_path}')
    error_handling.write_report(error_report_path, plot_df=df)

    return


# Test routine for ConPyro modelling
if __name__ == '__main__':
    # Define input and output folders
    examples_dir = helper.get_examples_dir(os.path.dirname(__file__))
    _out_dir = os.path.join(examples_dir, 'results', 'conpyro')
    # The ConPyro input dataframe must have weather data attached for ConPyro/FOFEM modelling
    # Required weather columns for ConPyro modelling: 'ws', 'wd', 'ffmc', 'dmc', 'bui', 'temp', 'rh'
    # Required weather columns for FOFEM mortality modelling: 'ws', 'temp'
    _in_dir = os.path.join(examples_dir, 'results', 'wx_extract')
    _in_conpyro_csv_path = os.path.join(_in_dir, 'conpyro_df_wx.csv')
    _tree_csv_path = os.path.join(examples_dir, 'results', 'fuel_analyst', 'master_tree_df.csv')
    _fofem_consume_csv_path = os.path.join(
        examples_dir, 'results', 'fuel_analyst', fofem_units.consume_filename('SI')
    )
    _fire_modelling_dict = default_fire_modelling_dict

    # Run ConPyro modelling
    run_conpyro(
        out_dir=_out_dir,
        in_conpyro_csv_path=_in_conpyro_csv_path,
        in_tree_csv_path=_tree_csv_path,
        in_fofem_consume_csv_path=_fofem_consume_csv_path,
        fire_modelling_params=_fire_modelling_dict,
    )
