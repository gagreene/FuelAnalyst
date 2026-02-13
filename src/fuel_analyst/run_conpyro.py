# -*- coding: utf-8 -*-
"""
Created on Sun Feb 2, 11:15:00 2026

@author: Gregory A. Greene
"""
__author__ = ['Gregory A. Greene, map.n.trowel@gmail.com']

import os
from numpy import array, column_stack, full, nan
import pandas as pd

import sys
pkg_dir = os.path.join(os.path.dirname(__file__), '..', '..')
if pkg_dir not in sys.path:
    sys.path.insert(0, pkg_dir)

from dependencies.conpyro.src.conpyro import conpyro
from dependencies.flame_components import flame_components as fc


default_fire_modelling_dict = {
    'conpyro': {
        'out_request': [
            'fsg', 'mc_ffmc', 'mc_dmc', 'mc_sa', 'cac', 'cfo_prob',
            'sros', 'cros', 'hros', 'bros', 'fire_type', 'accel_param',
            'cfb', 'tfc', 'sfi', 'cfi', 'hfi'
        ],
        'flame_comp_out_list': [
            'instand_ws', 'flame_length_m', 'flame_tilt', 'flame_height', 'flame_res_time', 'flame_depth'
        ],
    },
    'fofem_mortality': {
        'model_mortality': True,
    },
    'fofem_emissions': {
        'model_emissions': True,
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
    df['instand_ws_kmph'] = full(len(df), nan)
    # Use Albini and Baughman (1979) model
    valid_mask = df[required_cols].notna().all(axis=1)
    df.loc[valid_mask, 'instand_ws_model'] = 'Albini and Baughman (1979)'
    df.loc[valid_mask, 'instand_ws_kmph'] = fc.getMidFlameWS(
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
        required_cols = ['fire_type', 'hfi', 'instand_ws_kmph', 'flame_length_m']
        missing_cols = set(required_cols) - set(df.columns)
        if missing_cols:
            raise ValueError(f'Required columns for flame length calculation not found in DataFrame: {missing_cols}')

        # Calculate flame height
        df['flame_ht_model'] = pd.Series([nan] * len(df), dtype='object')
        df['flame_ht_m'] = full(len(df), nan)
        # Use Nelson model
        nelson_model = df['instand_ws_kmph'].notna() & df['hfi'].notna() & df['fire_type'].notna()
        df.loc[nelson_model, 'flame_ht_model'] = 'Nelson and Adkins (1986)'
        df.loc[nelson_model, 'flame_ht_m'] = fc.getFlameHeight(
            model='Nelson',
            flame_length=df.loc[nelson_model, 'flame_length_m'].to_numpy(),
            fire_type=df.loc[nelson_model, 'fire_type'].to_numpy(),
            fire_intensity=df.loc[nelson_model, 'hfi'].to_numpy(),
            midflame_ws=df.loc[nelson_model, 'instand_ws_kmph'].to_numpy()
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
    required_cols = ['hros', 'tfc', 'instand_ws_kmph']
    missing_cols = set(required_cols) - set(df.columns)
    if missing_cols:
        raise ValueError(f'Required columns for flame resident time calculation not found in DataFrame: {missing_cols}')

    # Calculate flame residence time
    df['flame_res_time_model'] = pd.Series([nan] * len(df), dtype='object')
    df['flame_res_time_min'] = full(len(df), nan)
    # Use Nelson and Adkins (1988) model
    valid_mask = df[required_cols].notna().all(axis=1)
    df.loc[valid_mask, 'flame_res_time_model'] = 'Nelson and Adkins (1988)'
    df.loc[valid_mask, 'flame_res_time_min'] = fc.getFlameResidenceTime(
        ros=df.loc[valid_mask, 'hros'].to_numpy(),
        fuel_consumption=df.loc[valid_mask, 'tfc'].to_numpy(),
        midflame_ws=df.loc[valid_mask, 'instand_ws_kmph'].to_numpy(),
        units='min'
    )

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


def model_flame_components(df: pd.DataFrame, flame_comp_out_list) -> pd.DataFrame:
    """
    Model flame components based on ConPyro output parameters.

    :param df: DataFrame with ConPyro output parameters.
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


def run_conpyro(in_csv_path: str,
                conpyro_out_list: list,
                flame_comp_out_list: list,
                out_csv_path: str) -> None:
    """
    Run ConPyro on the input data and model flame components based on ConPyro output.

    :param in_csv_path: Path to the input CSV file containing required columns for ConPyro.
    :param conpyro_out_list: List of ConPyro output parameters to include in the output DataFrame.
    :param flame_comp_out_list: List of flame component output parameters to model and include in the output DataFrame.
    :param out_csv_path: Path to save the output CSV file with ConPyro results and flame components.
    :return: None
    """
    # Get dataframe
    df = pd.read_csv(in_csv_path)

    # Drop rows with empty values in required columns
    drop_empty_rows_in_cols = ['stand_density', 'stand_type']
    for col in drop_empty_rows_in_cols:
        df = df[df[col].notna()]

    # Initialize ConPyro class
    cp = conpyro.ConPyro()
    cp.initialize(
        cfo_model=3,
        sros_model=1,
        cros_model=1,
        smooth_ros=True,
        model_slope_effects=True,
        season=None,
        density=df['stand_density'].values.astype(str),
        stand_type=df['stand_type'].values.astype(str),
        ws=df['ws'].values,
        wd=df['wd'].values,
        ffmc=df['ffmc'].values,
        dmc=df['dmc'].values,
        bui=df['bui'].values,
        fsg=df['fsg'].values,
        fuel_type=df['fbp_fuel_type'].values.astype(str),
        ffl=df[['duff_fuel_load', 'litter_fuel_load']].sum(axis=1).values,
        wfl=df['woody_fuel_load'].values,
        gfl=df['herbaceous_fuel_load'].values,
        pct_cnfr=df['pct_cnfr'].values,
        cbd=df['cbd_ovrstry'].values,
        ht_midstry_live=df['ht_midstry_live'].values,
        ht_midstry_dead=df['ht_midstry_dead'].values,
        cbh_ovrstry=df['cbh_ovrstry'].values,
        cbh_midstry=df['cbh_midstry'].values,
        cfl_ovrstry=df['cfl_ovrstry'].values,
        cfl_midstry=df['cfl_midstry'].values,
        dead_branch_fl=df['dead_branch_fl'].values,
        fmc=90,
        wx_date=20170706,
        time=1200,
        site_elev=df['elevation'].values,
        stn_elev=df['elevation'].values,
        temp=df['temp'].values,
        rh=df['rh'].values,
        cc=df['canopy_cover'].values,
        slope=df['slope'].values,
        aspect=df['aspect'].values,
    )

    # Run ConPyro
    print('Running ConPyro...')
    cp.run_conpyro()

    # Get requested output parameters
    new_df = pd.DataFrame(
        column_stack(array(cp.return_params(out_request=conpyro_out_list), dtype=object)),
        columns=conpyro_out_list)

    # Drop columns from df if they are present in new_df
    df = df.drop(columns=[col for col in new_df.columns if col in df.columns], errors='ignore')

    # Add new columns to original dataframe
    df = pd.concat([df.reset_index(drop=True), new_df.reset_index(drop=True)], axis=1)
    del new_df

    # Change string values to int or float (as appropriate) if they are numeric
    for col in df.select_dtypes(include=['object']).columns:
        try:
            df[col] = pd.to_numeric(df[col])
        except ValueError:
            pass

    # Model flame components with ConPyro output
    print('Modeling flame components with ConPyro output...')
    df = model_flame_components(df, flame_comp_out_list)

    # Save results to CSV
    print(f'Saving results to {out_csv_path}...')
    df.to_csv(out_csv_path, index=False)

    return


# Test routine for ConPyro modelling
if __name__ == '__main__':
    # Define input and output folders
    test_dir = os.path.join(os.path.dirname(__file__), 'tests')
    _in_dir = os.path.join(test_dir, 'results', 'wx_extract')
    _out_dir = os.path.join(test_dir, 'results', 'conpyro')
    os.makedirs(_out_dir, exist_ok=True)
    _in_csv_path = os.path.join(_in_dir, 'ccp_df_wx.csv')
    _out_csv_path = os.path.join(_out_dir, 'ccp_df_results.csv')

    _conpyro_out_list = [
        'fsg', 'mc_ffmc', 'mc_dmc', 'mc_sa', 'cac', 'cfo_prob',
        'sros', 'cros', 'hros', 'bros', 'fire_type', 'accel_param',
        'cfb', 'tfc', 'sfi', 'cfi', 'hfi'
    ]

    _flame_comp_out_list = [
        'instand_ws', 'flame_length_m', 'flame_tilt', 'flame_height', 'flame_res_time', 'flame_depth'
    ]

    # Run ConPyro and flame components modelling
    run_conpyro(in_csv_path=_in_csv_path,
                conpyro_out_list=_conpyro_out_list,
                flame_comp_out_list=_flame_comp_out_list,
                out_csv_path=_out_csv_path)