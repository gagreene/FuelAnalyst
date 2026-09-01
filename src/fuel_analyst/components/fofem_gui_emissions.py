# -*- coding: utf-8 -*-
"""
Created on Sun Feb 1, 16:30:00 2026

@author: Gregory A. Greene
"""
__author__ = ['Gregory A. Greene']

import os
import shutil
import numpy as np
import pandas as pd
import subprocess
from csv import reader as CSV
import concurrent.futures
from typing import Union

from . import helper
from . import fwis_moisture_content as mc
from pyfofem import pyfofem as fofem, TOTAL_DURATION_CONSUMED_VARS, EQUATION_VARS, \
    SOIL_HEAT_VARS, DEFAULT_CONSUMPTION_VARS
import tqdm
try:
    from tqdm.contrib.concurrent import process_map
    _TQDM_PROCESS_MAP_AVAILABLE = True
except ImportError:
    _TQDM_PROCESS_MAP_AVAILABLE = False

# Dictionary of seasons for each month in the year
default_season_start_dict = {
    'Spring': '0415',
    'Summer': '0615',
    'Fall': '0915',
    'Winter': '1115',
}
FOFEM_DIR = os.path.join(pkg_dir, 'dependencies', 'pyfofem', 'src', 'pyfofem', 'supporting_data', 'FOFEM6.7')
CONSUMPTION_VARS = fofem.DEFAULT_CONSUMPTION_VARS


def _calc_fuel_moisture_content(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate fuel moisture content columns and add them to the DataFrame.

    :param df: DataFrame with 'mc_sa', 'dmc', and 'dc' columns.
    :return: DataFrame with 'wfl10HourMoisture', 'DuffMoisture', and 'wfl1000HourMoisture' columns added.
    """
    # Calculate fuel moisture values
    # hr10_mc = mc.ffmc_mc(ffmc=df['ffmc'].to_numpy())
    # duff_mc = mc.dmc_mc(dmc=df['dmc'].to_numpy())
    df['wfl10HourMoisture'] = df['mc_sa']
    df['DuffMoisture'] = df['mc_dmc']
    df['wfl1000HourMoisture'] = mc.dc_mc(dc=df['dc'].to_numpy())

    return df


def _create_burnup_in_file(
        out_dir: str,
        unique_id: int,
        intensity: float,
        ig_time: float,
        instand_ws: float,
        depth: float,
        amb_temp: float,
) -> str:
    """
    Create a Burnup-In.brn file for a given row of fire behavior and weather data.

    :param out_dir: Output directory for Burnup-In.brn file.
    :param unique_id: Unique identifier for the row (used in output file name).
    :param intensity: Heat per unit area (kJ/m^2).
    :param ig_time: Ignition (flame residence) time (seconds).
    :param instand_ws: In-stand/mid-flame wind speed (m/s).
    :param depth: Flame depth (m).
    :param amb_temp: Ambient temperature (°C).
    :return: Path to worker-specific Burnup-In directory.
    """
    # Check if directory exists and remove if it does
    out_emission_dir = os.path.join(out_dir, f'FOFEM_Emissions_{unique_id}')
    os.makedirs(out_emission_dir, exist_ok=True)
    out_brn = os.path.join(out_emission_dir, f'Burnup-In.brn')

    # Generate Burnup-In.brn file using FOFEM pyfofem module
    fofem.gen_burnup_in_file(
        out_brn_path=out_brn,
        intensity=round(intensity, 2),
        ig_time=round(ig_time, 2),
        windspeed=round(instand_ws, 2),
        depth=round(depth, 2),
        ambient_temp=round(amb_temp, 2)
    )

    return out_emission_dir


def _create_consume_file(out_dir: str, consume_df: pd.DataFrame) -> str:
    """
    Create a Consume CSV file for a given row of fire behavior and weather data.

    :param out_dir: Output directory for Consume CSV file.
    :param consume_df: DataFrame containing the Consume data for a single row of fire behavior and weather data.
    :return: Path to generated Consume CSV file.
    """
    # Check if file exists and remove if it does
    out_consume = os.path.join(out_dir, f'fofemConsumedEmissions_df.csv')
    if os.path.exists(out_consume):
        os.remove(out_consume)

    # Save consume_df to csv
    consume_df.to_csv(out_consume, index=False, sep=',')

    # Add switches to consume_df csv
    helper.add_line_to_csv(out_consume, ['#1k-SizeClass'], 0)
    helper.add_line_to_csv(out_consume, ['#ConsumptionEquation'], 1)
    helper.add_line_to_csv(out_consume, [f'#BurnUpFile Burnup-In.brn'], 2)

    return out_consume


def _gen_plot_id(df: pd.DataFrame):
    """
    Replace spaces with underscores in the '#PlotId' column and return a mapping
    from underscored to original values.

    :param df: DataFrame with '#PlotId' column.
    :return: (DataFrame with updated '#PlotId', dict mapping underscored to original values)
    """
    # Create mapping from underscored PlotId to original
    plotid_map = dict(zip(df['#PlotId'].str.replace(' ', '_'), df['#PlotId']))
    # Replace spaces in #PlotId column data with underscores for consistency
    df['#PlotId'] = df['#PlotId'].str.replace(' ', '_')
    return df, plotid_map


def _restore_plot_id(df: pd.DataFrame, plotid_map: dict) -> pd.DataFrame:
    """
    Restore the original '#PlotId' values using the mapping.

    :param df: DataFrame with underscored '#PlotId' column.
    :param plotid_map: Mapping from underscored to original '#PlotId' values.
    :return: DataFrame with '#PlotId' restored to original values.
    """
    df['#PlotId'] = df['#PlotId'].map(plotid_map).fillna(df['#PlotId'])
    return df


def _get_merged_consumption_df(
        plot_wx_fire_csv_path: str,
        plot_id_col_name: str,
        fofem_consume_csv_path: str,
        consume_model: str = 'C'
) -> pd.DataFrame:
    """
    Merge stand fire severity and FOFEM consumption dataframes.

    :param plot_wx_fire_csv_path: Path to stand weather and fire severity CSV file.
    :param plot_id_col_name: Name of the unique ID column in the stand fire severity CSV used for merging (e.g., 'unique_id').
    :param fofem_consume_csv_path: Path to FOFEM consumption CSV file.
    :param consume_model: FOFEM consumption model ('C' or 'S').
    :return: Merged DataFrame.
    """
    # Ensure files exist
    if not helper.file_exists(plot_wx_fire_csv_path):
        raise FileNotFoundError(f'Stand weather and fire behavior CSV file not found: {plot_wx_fire_csv_path}')
    if not helper.file_exists(fofem_consume_csv_path):
        raise FileNotFoundError(f'FOFEM consumption CSV file not found: {fofem_consume_csv_path}')

    # Read CSV files into DataFrames
    plot_fire_df = helper.get_df(plot_wx_fire_csv_path)  # Use plot_id_col_name for merge
    fofem_consume_df = helper.get_df(fofem_consume_csv_path)  # Use #PlotId column for merge

    if consume_model == 'C':
        # Remove soil heat modelling columns from fofem_consume_df
        remove_cols = ['SoilFamily', 'SoilMoisture']
        soil_heating_cols = [col for col in fofem_consume_df.columns if col not in remove_cols]
        fofem_consume_df = fofem_consume_df[soil_heating_cols]
    else:  # if consume_model == 'S':
        # Replace missing data in SoilFamily column with 'NA' for soil heating modelling
        fofem_consume_df['SoilFamily'] = fofem_consume_df['SoilFamily'].fillna('NA')

    # Get required columns for merge and emissions processing
    required_cols = [
        plot_id_col_name, 'wx_date', 'hfi',
        'flame_res_time_sec', 'instand_ws_mps',
        'temp', 'mc_sa', 'mc_dmc', 'dc', 'cfb'
    ]

    # Verify required columns are present in plot_fire_df
    missing_cols = helper.get_missing_df_columns(plot_fire_df, required_cols)
    if missing_cols:
        raise ValueError(
            f'Missing required column(s) in weather and fire behavior CSV: {required_cols}'
        )

    # Filter columns in plot_fire_df
    plot_fire_df = plot_fire_df[required_cols]

    # Merge fofem consume data (one) with stand fire severity data (many) = one-to-many relationship
    merged_df = pd.merge(
        left=fofem_consume_df,
        right=plot_fire_df,
        left_on='#PlotId',
        right_on=plot_id_col_name,
        how='left',
        suffixes=('', '_plot')
    )
    # Drop columns with "_plot" suffix
    merged_df = merged_df.drop(columns=[col for col in merged_df.columns if col.endswith('_plot')])
    # Drop rows with missing plot_id_col_name values
    merged_df = merged_df.dropna(subset=[plot_id_col_name])

    return merged_df


def _get_pct_crown_burned(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate percent crown burned and add to DataFrame.

    :param df: DataFrame with 'cfb' column.
    :return: DataFrame with 'PercentCrownBurned' column added.
    """
    # Copy cfb column to PercentCrownBurned
    df['PercentCrownBurned'] = 100 * df['cfb']

    return df


def _get_season(df: pd.DataFrame, season_start_dict: dict = None) -> pd.DataFrame:
    """
    Determine the season for each row in the DataFrame based on date and season start dates.

    :param df: DataFrame with 'wx_date' column.
    :param season_start_dict: Dictionary defining season start dates.
    :return: DataFrame with 'season' column added.
    """
    if season_start_dict is None:
        season_start_dict = default_season_start_dict

    # Verify that required columns are present
    required_cols = ['wx_date']
    missing_cols = helper.get_missing_df_columns(df, required_cols)
    if missing_cols:
        raise ValueError(
            f'Missing required column(s) in weather CSV: {required_cols}'
        )

    # Create season start dates
    season_starts = {
        'Spring': int(season_start_dict['Spring']),
        'Summer': int(season_start_dict['Summer']),
        'Fall': int(season_start_dict['Fall']),
        'Winter': int(season_start_dict['Winter']),
    }

    def determine_season(row):
        """
        Determine the configured season for one weather-data row.

        :param row: Weather-data row containing a YYYYMMDD wx_date value.
        :return: Season name containing the weather date.
        """
        # Get dates from wx_date column in df (formatted as YYYYMMDD)
        date_str = str(row['wx_date'])
        month_day = int(date_str[4:8])  # Extract MMDD as integer
        if season_starts['Spring'] <= month_day < season_starts['Summer']:
            return 'Spring'
        elif season_starts['Summer'] <= month_day < season_starts['Fall']:
            return 'Summer'
        elif season_starts['Fall'] <= month_day < season_starts['Winter']:
            return 'Fall'
        else:
            return 'Winter'

    df['season'] = df.apply(determine_season, axis=1)

    return df


def _model_emissions(row: dict, out_dir: str, consume_model: str) -> tuple:
    """
    Model emissions using FOFEM with Burnup-In.brn files for a given row of fire behavior and weather data.

    :param row: Dict of merged DataFrame row containing fire behavior and weather data for a single plot.
    :param out_dir: Output directory for Burnup-In.brn files.
    :param consume_model: FOFEM consumption model ('C' or 'S').
    :return: Tuple (list of FOFEM results, output emission directory).
    """
    # Get unique identifier for the multiprocessing worker
    process_id = os.getpid()

    # Check if required columns are present in DataFrame
    required_cols = [
        'wx_date', 'hfi', 'flame_res_time_sec', 'instand_ws_mps', 'temp'
    ]
    missing_cols = helper.get_missing_df_columns(pd.DataFrame([row]), required_cols)
    if missing_cols:
        raise ValueError(f'Missing required columns in DataFrame: {missing_cols}')

    # Create Burnup-In.brn files for each row in the DataFrame
    out_emission_dir = _create_burnup_in_file(
        out_dir=out_dir,
        unique_id=process_id,
        intensity=row['hfi'],
        ig_time=row['flame_res_time_sec'],
        instand_ws=row['instand_ws_mps'],
        depth=row['fuel_bed_depth_m'],
        amb_temp=row['temp']
    )

    try:
        # Convert row to Dataframe, removing all data including and after 'remove_hereafter' column
        row_consume_df = pd.DataFrame(
            [row]
        ).loc[:, :'remove_hereafter'].drop(columns=['remove_hereafter'])

        # Save Consume data to file
        out_consume = _create_consume_file(
            out_dir=out_emission_dir,
            consume_df=row_consume_df,
        )
        del row_consume_df

        # Run FOFEM with Burnup-In.brn files and capture results
        fofem_consume_results = _run_fofem(
            out_dir=out_emission_dir,
            out_consume=out_consume,
            consume_model=consume_model,
        )
    except Exception as e:
        print(f'Error processing row with unique_id {row.get("unique_id", "N/A")}: {e}')
        fofem_consume_results = [f'Error: {e}'] * len(CONSUMPTION_VARS)

    return fofem_consume_results, out_emission_dir


def _run_fofem(out_dir: str, out_consume: str, consume_model: str) -> list:
    """
    Run FOFEM Consumed Emissions Modelling and capture results.

    :param out_dir: Output directory for FOFEM results.
    :param out_consume: Path to Consume CSV file for FOFEM input.
    :param consume_model: FOFEM consumption model ('C' or 'S').
    :return: List containing FOFEM results and any errors.
    """
    # Create output file paths for FOFEM results
    out_results = os.path.join(out_dir, f'fofemConsumedEmissionsDF_Temp-Out.csv')
    out_run = os.path.join(out_dir, f'fofemConsumedEmissionsDF_Temp-Run.csv')
    out_err = os.path.join(out_dir, f'fofemConsumedEmissionsDF_Temp-Err.txt')

    # Get all files in FOFEM_DIR and copy to out_dir if they don't already exist
    # (to avoid issues with multiple workers trying to read the same files in FOFEM_DIR)
    for filename in os.listdir(FOFEM_DIR):
        src_file = os.path.join(FOFEM_DIR, filename)
        dst_file = os.path.join(out_dir, filename)
        if not os.path.exists(dst_file):
            shutil.copy(src_file, dst_file)

    # Run FOFEM Consumed Emissions Modelling
    os.chdir(out_dir)
    _ = subprocess.run(
        ['fof_gui',
         consume_model,
         out_consume,
         out_results,
         out_run,
         out_err],
        capture_output=True,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW
    )

    # Check if FOFEM run was successful
    if not helper.file_exists(out_results):
        raise FileNotFoundError(f'FOFEM output file not found: {out_results}')
    if not helper.file_exists(out_run):
        raise FileNotFoundError(f'FOFEM run file not found: {out_run}')
    if not helper.file_exists(out_err):
        raise FileNotFoundError(f'FOFEM error file not found: {out_err}')

    # Read FOFEM output files
    with open(out_results, newline='') as f:
        reader = CSV(f)
        cons_data = list(reader)
    if cons_data:
        consume_results = cons_data[0][1:]
    else:
        # with open(out_err, newline='') as f:
        #     error_message = f.read()
        consume_results = [0] * len(CONSUMPTION_VARS)

    return consume_results


def process_emissions(
        plot_wx_fire_csv_path: str,
        plot_id_col_name: str,
        fofem_consume_csv_path: str,
        out_dir: str,
        model_soil_heating: bool = False,
        num_workers: int = 1,
        return_df: bool = False,
) -> Union[None, str]:
    """
    Process emissions modelling with FOFEM.

    :param plot_wx_fire_csv_path: Path to CSV file containing plot weather and fire data.
    :param plot_id_col_name: Name of the unique ID column in the stand fire severity CSV used for merging
        (e.g., 'unique_id').
    :param fofem_consume_csv_path: Path to FOFEM consumption CSV file.
    :param out_dir: Output directory for Burnup-In.brn files.
    :param model_soil_heating: Whether to use FOFEM soil heating consumption model (True) or not (False).
    :param num_workers: Number of workers for parallel processing
    :param return_df: Whether to return a path to the final DataFrame with emissions results (True) or not (False).
    :return: None if return_df is False, otherwise the DataFrame containing the merged input data and
        FOFEM emissions results.
    """
    # Ensure output directory exists
    os.makedirs(out_dir, exist_ok=True)

    # Assign FOFEM consumption model based on whether soil heating is being modeled
    global CONSUMPTION_VARS
    if model_soil_heating:
        consume_model = 'S'
        CONSUMPTION_VARS = DEFAULT_CONSUMPTION_VARS + TOTAL_DURATION_CONSUMED_VARS + SOIL_HEAT_VARS + EQUATION_VARS
    else:
        consume_model = 'C'
        CONSUMPTION_VARS = DEFAULT_CONSUMPTION_VARS +TOTAL_DURATION_CONSUMED_VARS + EQUATION_VARS


    # Get merged consumption DataFrame
    merged_df = _get_merged_consumption_df(
        plot_wx_fire_csv_path=plot_wx_fire_csv_path,
        plot_id_col_name=plot_id_col_name,
        fofem_consume_csv_path=fofem_consume_csv_path,
        consume_model=consume_model,
    )

    # Generate new PlotId column for merged_df based on plot_id_col_name (to be used in FOFEM input files)
    merged_df, plotid_map = _gen_plot_id(merged_df)

    # Get percent crown burned
    merged_df = _get_pct_crown_burned(merged_df)

    # Get season start dates
    merged_df = _get_season(merged_df)

    # Drop unnecessary columns after merge
    merged_df = merged_df.drop(columns=[plot_id_col_name, 'cfb'])

    # Calculate percentage fuel moisture content
    merged_df =_calc_fuel_moisture_content(merged_df)

    # Model emissions using FOFEM with Burnup-In.brn files
    if num_workers >= 4:  # Use multiprocessing if 4 or more CPU cores are available
        print(
            f'\tProcessing Emissions (via BURNUP model) in parallel with {num_workers} workers...'
        )
        records = merged_df.to_dict(orient='records')
        out_dirs = [out_dir] * len(merged_df)
        consume_models = [consume_model] * len(merged_df)
        if _TQDM_PROCESS_MAP_AVAILABLE:
            results = process_map(
                _model_emissions,
                records,
                out_dirs,
                consume_models,
                max_workers=num_workers,
                desc='Emissions',
                chunksize=1,
            )
        else:
            with concurrent.futures.ProcessPoolExecutor(max_workers=num_workers) as executor:
                results = list(tqdm.tqdm(
                    executor.map(_model_emissions, records, out_dirs, consume_models),
                    total=len(records),
                    desc='Emissions',
                ))
    else:
        print('\tProcessing Emissions (via BURNUP model)...')
        results = [
            _model_emissions(row, out_dir, consume_model) for row in tqdm.tqdm(merged_df.to_dict(orient='records'), desc='Emissions')
        ]

    # Unpack results
    fofem_consume_results, out_emission_dirs = zip(*results)

    # Remove worker-specific directories and contents
    for out_emission_dir in set(out_emission_dirs):
        shutil.rmtree(out_emission_dir)

    # Convert FOFEM results to DataFrame
    fofem_results_df = pd.DataFrame(fofem_consume_results, columns=CONSUMPTION_VARS)
    helper.export_csv(fofem_results_df, os.path.join(out_dir, 'fofem_results_df_temp.csv'))

    # Delete "remove" column from merged_df
    merged_df = merged_df.drop(columns=['remove_hereafter'])
    helper.export_csv(merged_df, os.path.join(out_dir, 'merged_df_temp.csv'))

    # Append to merged_df
    final_df = pd.concat([merged_df.reset_index(drop=True), fofem_results_df], axis=1)

    # Restore original PlotId values in final_df
    final_df = _restore_plot_id(final_df, plotid_map)

    # Sort final_df by plot_id_col_name and wx_date
    final_df = final_df.sort_values(by=['#PlotId', 'wx_date']).reset_index(drop=True)

    # Save as csv to output directory
    csv_out_path = os.path.join(out_dir, 'fofem_emissions_results.csv')
    helper.export_csv(final_df, csv_out_path)

    if return_df:
        return final_df

    return None


# Test routine for FOFEM emissions processing
if __name__ == '__main__':
    # Define input and output folders
    examples_dir = helper.get_examples_dir(os.path.dirname(__file__))
    _in_fofem_consume_dir = os.path.join(examples_dir, 'results', 'fuel_analyst')
    _in_fire_data_dir = os.path.join(examples_dir, 'results', 'fofem_mortality')
    _out_dir = os.path.join(examples_dir, 'results', 'fofem_emissions')

    # Get stand fire and fofem consume csv paths
    _plot_wx_fire_csv_path = os.path.join(_in_fire_data_dir, 'fofem_severity_results.csv')
    _fofem_consume_csv_path = os.path.join(_in_fofem_consume_dir, 'fofem_consume_df.csv')
    _plot_id_col_name = 'unique_id'

    # Process emissions modelling
    process_emissions(
        plot_wx_fire_csv_path=_plot_wx_fire_csv_path,
        plot_id_col_name=_plot_id_col_name,
        fofem_consume_csv_path=_fofem_consume_csv_path,
        out_dir=_out_dir,
        num_workers=os.cpu_count() - 1,
    )
