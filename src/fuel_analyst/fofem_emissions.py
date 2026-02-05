# -*- coding: utf-8 -*-
"""
Created on Sun Feb 1, 16:30:00 2026

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

from src.fuel_analyst.components import helper
from dependencies.flame_components import flame_components as fc
from dependencies.pyfofem.src.pyfofem import pyfofem as fofem


def process_emissions() -> None:
    """Process emissions using FOFEM and FLAME components."""
    pass  # Placeholder for emissions processing logic

    return


# Test routine for FOFEM emissions processing
if __name__ == '__main__':
    # Define input and output folders
    test_dir = os.path.join(os.path.dirname(__file__), 'tests')
    _in_stand_data_dir = os.path.join(test_dir, 'results', 'fuel_analyst')
    _in_fire_data_dir = os.path.join(test_dir, 'results', 'fofem_mortality')
    _out_dir = os.path.join(test_dir, 'results', 'fofem_mortality')

    # Get stand fire and tree csv paths
    _stand_fire_df_path = os.path.join(_in_fire_data_dir, 'ccp_df_results.csv')
    _tree_df_path = os.path.join(_in_tree_data_dir, 'master_tree_df.csv')

    # Process mortality
    process_emissions(
        stand_fire_csv_path=_stand_fire_df_path,
        tree_csv_path=_tree_df_path,
        out_dir=_out_dir,
        aspen_sev=_aspen_sev,
    )