# -*- coding: utf-8 -*-
"""
Created on Sun Feb 2, 11:15:00 2026

@author: Gregory A. Greene
"""
__author__ = ['Gregory A. Greene, map.n.trowel@gmail.com']

import os
import numpy as np
import pandas as pd

import sys
pkg_dir = os.path.join(os.path.dirname(__file__), '..', '..')
if pkg_dir not in sys.path:
    sys.path.insert(0, pkg_dir)

from dependencies.conpyro.conpyro import conpyro


def run_conpyro(csv_path: str,
                output_request_list: list,
                out_path: str) -> None:
    # Get dataframe
    df = pd.read_csv(csv_path)

    # Drop rows with empty values in required columns
    drop_empty_rows_in_cols = ['stand_density', 'stand_type']
    for col in drop_empty_rows_in_cols:
        df = df[df[col].notna()]

    # Initialize ConPyro class
    cp = conpyro.ConPyro()
    cp.initialize(
        cfo_model=10,
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
    cp.run_conpyro()

    # Get requested output parameters
    new_df = pd.DataFrame(
        np.column_stack(np.array(cp.return_params(out_request=output_request_list), dtype=object)),
        columns=output_request_list)

    # Add new columns to original dataframe
    df = pd.concat([df.reset_index(drop=True), new_df.reset_index(drop=True)], axis=1)
    del new_df

    # Save results to CSV
    df.to_csv(out_path, index=False)

    return


# Test routine for MoistureContent class
if __name__ == '__main__':
    _csv_path = os.path.join(os.path.dirname(__file__), 'tests', 'test_data', 'conpyro', 'ccp_df.csv')
    _out_dir = os.path.join(os.path.dirname(__file__), 'tests', 'results', 'conpyro')
    os.makedirs(_out_dir, exist_ok=True)
    _out_path = os.path.join(_out_dir, 'ccp_df_results.csv')

    _output_request_list = [
        'fsg', 'mc_ffmc', 'mc_dmc', 'mc_sa', 'cac', 'cfo_prob',
        'sros', 'cros', 'hros', 'bros', 'fire_type', 'accel_param',
        'cfb', 'sfi', 'cfi', 'hfi'
    ]

    run_conpyro(csv_path=_csv_path,
                output_request_list=_output_request_list,
                out_path=_out_path)