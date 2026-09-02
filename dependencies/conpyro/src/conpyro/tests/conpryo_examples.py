# -*- coding: utf-8 -*-
"""
Created on Thu Oct 16, 11:45:00 2025

@author: Gregory A. Greene
"""
__author__ = ['Gregory A. Greene, map.n.trowel@gmail.com']

import os
import pandas as pd
import numpy as np
from src.conpyro.conpyro import ConPyro


def _test_mc() -> None:
    # Initialize ConPyro class
    cp = ConPyro()
    cp.initialize(
        cfo_model=3,
        sros_model=1,
        cros_model=1,
        smooth_ros=True,
        model_terrain_effects_on_wind=True,
        model_terrain_effects_on_ffmc=True,
        process_ladder=True,
        season=np.array(['Sp', 'Su', 'F']),
        # season=None,
        density=np.array(['M', 'H', 'L']),
        stand_type=np.array(['D', 'P', 'S']),
        ffmc=np.array([85.0, 90.0, 95.0]),
        dmc=np.array([20.0, 100.0, 150.0]),
        bui=np.array([10.0, 50.0, 80.0]),
        wx_date=20230715,
        fsg=np.array([2.0, 3.5, 1.8]),
        sfc=np.array([1.2, 2.0, 1.5]),
        cbd=np.array([0.12, 0.25, 0.18]),
        cc=np.array([30.0, 50.0, 70.0]),
        ffl=np.array([1.0, 2.5, 1.8]),
        wfl=np.array([0.5, 1.0, 0.8]),
        gfl=np.array([0.2, 0.5, 0.3]),
        pct_cnfr=np.array([20.0, 40.0, 60.0]),
        ht_midstry_live=np.array([2.0, 4.0, 3.0]),
        ht_midstry_dead=np.array([1.5, 3.0, 2.5]),
        cbh_ovrstry=np.array([3.0, 5.0, 4.0]),
        cbh_midstry=np.array([1.0, 2.0, 1.5]),
        cfl_ovrstry=np.array([0.8, 1.5, 1.0]),
        cfl_midstry=np.array([0.3, 0.7, 0.5]),
        dead_branch_fl=np.array([0.1, 0.3, 0.2]),
        fmc=90,
        fuel_type=np.array(['C1', 'C3', 'C5']),
        ws=np.array([10.0, 20.0, 15.0]),
        wd=np.array([0.0, 90.0, 180.0]),
        slope=np.array([10.0, 20.0, 15.0]),
        aspect=np.array([0.0, 90.0, 180.0]),
        suppress_messages=True,
    )

    # Run ConPyro MoistureContent calculations
    cp.run_conpyro()

    # Print results
    print('mcsa:', cp.mc_sa)

    return


def _test_conpyro_dataframe() -> None:
    csv_path = os.path.join(os.path.dirname(__file__), 'test_data', 'conpyro_df.csv')
    out_dir = os.path.join(os.path.dirname(__file__), 'results')
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, 'conpyro_df_results.csv')

    # Get dataframe
    df = pd.read_csv(csv_path)

    # Drop rows with empty values in required columns
    drop_empty_rows_in_cols = ['stand_density', 'stand_type']
    for col in drop_empty_rows_in_cols:
        df = df[df[col].notna()]

    # Initialize ConPyro class
    cp = ConPyro()
    cp.initialize(
        cfo_model=5,
        sros_model=13,
        cros_model=1,
        smooth_ros=True,
        model_terrain_effects_on_wind=True,
        model_terrain_effects_on_ffmc=True,
        process_ladder=True,
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
        suppress_messages=True,
    )

    # Run ConPyro MoistureContent calculations
    cp.run_conpyro()

    # Generate output request list
    output_request_list = [
        'fsg', 'mc_ffmc', 'mc_dmc', 'mc_sa', 'cac', 'cfo_prob',
        'sros', 'cros', 'hros', 'bros', 'fire_type', 'accel_param',
        'cfb', 'sfi', 'cfi', 'hfi'
    ]

    # Get results and append to dataframe
    new_df = pd.DataFrame(
        np.column_stack(np.array(cp.return_params(out_request=output_request_list), dtype=object)),
        columns=output_request_list)
    df = pd.concat([df.reset_index(drop=True), new_df.reset_index(drop=True)], axis=1)
    del new_df

    # Print entire dataframe
    pd.set_option('display.max_columns', None)
    print(df)

    # Save results to CSV
    df.to_csv(out_path, index=False)

    return


# Test routine for MoistureContent class
if __name__ == '__main__':
    _test_mc()
    _test_conpyro_dataframe()