# -*- coding: utf-8 -*-
"""
Created on Thu Oct 16, 11:45:00 2025

@author: Gregory A. Greene
"""
__author__ = ['Gregory A. Greene, map.n.trowel@gmail.com']

import inspect
import numpy as np
from numpy import ma as mask
from datetime import datetime as dt
from typing import Union, Optional
from operator import itemgetter
from .validation_utils import validate_numeric

from .equations.ladder_eqs import (
    calc_dead_ladder_contributions,
    calc_fmc,
    calc_live_ladder_contributions,
    calc_min_ladder_fsg,
    calc_total_sfc,
)


class LadderFuels(object):
    def __init__(self):
        # Ladder Fuel input variables
        self.multiply_cfl = False  # Option to double midstory canopy fuel load (CFL) value
        self.sfc = None
        self.ht_midstry_live = None
        self.ht_midstry_dead = None
        self.cbh_ovrstry = None
        self.cbh_midstry = None
        self.cfl_midstry = None
        self.dead_branch_fl = None
        self.fmc = None

        # Initialize flags
        self.ladder_return_array = False
        self.ladder_inputs_verified = False

        # Initialize Foliar Moisture Content (FMC) variables
        self.ref_array = None  # Reference array for masked calculations
        self.wx_date = None  # Date of weather observation (used for fmc calculation) (YYYYMMDD)
        self.lat = None  # Latitude (decimal degrees)
        self.long = None  # Longitude (decimal degrees)
        self.elevation = None  # Elevation (meters)
        self.latn = None  # Normalized latitude
        self.d0 = None  # Date of minimum foliar moisture content
        self.dj = None  # Julian date
        self.nd = None  # Number of days between Dj and D0

        # Initialize interim Ladder Fuel variables
        self.fsg_live_ladder = None
        self.fsg_dead_ladder = None
        self.fsg = None
        self.sfc_live_ladder = None
        self.sfc_dead_ladder = None
        self.sfc = None

        # ### Ladder Fuel Multiplier
        # This multiplier is used to adjust the live ladder SFC value to equilibriate the vertical heat flux
        # contributions to crown fire initiation between ladder fuel consumption and surface fuel consumption
        # Calculated as M = (4.45 / 3.26)^1.5 = 2.59
        # Refer to Perrakis et al. (202X) for details
        # self.m = 2.59
        # self.m = 3.5
        self.m = 4.2

    def _check_array_ladder(self) -> None:
        """
        Function to check if any of the input parameters are numpy arrays.

        :return: None
        """
        # ### CHECK FOR NUMPY ARRAYS IN INPUT PARAMETERS
        params = inspect.signature(self.initialize_ladder_fuels).parameters
        param_names = list(params.keys())
        param_list = [getattr(self, param) for param in param_names if param != 'self']

        if any(isinstance(data, np.ndarray) for data in param_list):
            # Set return_array flag to True
            self.ladder_return_array = True

            # Get indices of input parameters that are arrays
            array_indices = [i for i in range(len(param_list)) if isinstance(param_list[i], np.ndarray)]

            # If more than one array, verify they are all the same shape
            if len(array_indices) > 1:
                # Verify all arrays have the same shape
                arrays = itemgetter(*array_indices)(param_list)
                # Ensure the result is a list
                if isinstance(arrays, np.ndarray):  # Single array case
                    arrays = [arrays]
                shapes = {arr.shape for arr in arrays}
                if len(shapes) > 1:
                    raise ValueError(
                        'All arrays must have the same dimensions.'
                        f'The following range of dimensions exists: {shapes}'
                    )

                # Get first input array
                first_array = param_list[array_indices[0]]

                # Create float reference array
                self.ref_array = mask.array(
                    np.full(first_array.shape, 0, dtype=np.float64),
                    mask=~np.isfinite(first_array)
                )
        else:
            # Set return_array flag to False
            self.ladder_return_array = False
            # Create float reference array
            self.ref_array = mask.array([0], mask=np.isnan([self.sfc])).astype(np.float64)
        return

    def _verify_inputs_ladder(self) -> None:
            """
            Function to verify LadderFuels input parameters.

            :return: None
            """
            # Verify sfc
            self.sfc = validate_numeric(self.sfc, 'sfc', clip_min=0)

            # Verify ht_midstry_live
            self.ht_midstry_live = validate_numeric(self.ht_midstry_live, 'ht_midstry_live', clip_min=0)

            # Verify ht_midstry_dead
            self.ht_midstry_dead = validate_numeric(self.ht_midstry_dead, 'ht_midstry_dead', clip_min=0)

            # Verify cbh_ovrstry
            self.cbh_ovrstry = validate_numeric(self.cbh_ovrstry, 'cbh_ovrstry', clip_min=0.5)

            # Verify cbh_midstry
            self.cbh_midstry = validate_numeric(self.cbh_midstry, 'cbh_midstry', clip_min=0)

            # Verify cfl_midstry
            self.cfl_midstry = validate_numeric(self.cfl_midstry, 'cfl_midstry', clip_min=0)

            # Verify dead_branch_fl
            self.dead_branch_fl = validate_numeric(self.dead_branch_fl, 'dead_branch_fl', clip_min=0)

            # Verify fmc
            if self.fmc is not None:
                self.fmc = validate_numeric(self.fmc, 'fmc', clip_min=0, clip_max=100,
                                            ref_array=self.ref_array)
            else:
                # ...existing code (fmc is None path)...
                #   (a) wx_date + lat + long + elevation must be provided, OR
                #   (b) d0 + dj + lat + long + elevation must be provided
                has_wx_path = (self.wx_date is not None and self.lat is not None
                               and self.long is not None and self.elevation is not None)
                has_d0dj_path = (self.d0 is not None and self.dj is not None
                                 and self.lat is not None and self.long is not None
                                 and self.elevation is not None)
                if not has_wx_path and not has_d0dj_path:
                    raise ValueError(
                        'Either fmc, or all of (wx_date, lat, long, elevation), '
                        'or all of (d0, dj, lat, long, elevation) '
                        'must be provided for foliar moisture content calculations.'
                    )

                # Verify wx_date
                if self.wx_date is not None:
                    if not isinstance(self.wx_date, int):
                        raise TypeError('wx_date must be int data type')
                    try:
                        date_string = str(self.wx_date)
                        dt.fromisoformat(f'{date_string[:4]}-{date_string[4:6]}-{date_string[6:]}')
                    except ValueError:
                        raise ValueError('wx_date must be formatted as: YYYYMMDD')

                # Verify lat
                if self.lat is not None:
                    self.lat = validate_numeric(self.lat, 'lat', use_isfinite=False)

                # Verify long
                if self.long is not None:
                    self.long = validate_numeric(self.long, 'long', use_isfinite=False)
                    # Get absolute longitude values
                    self.long = np.absolute(self.long)

                # Verify elevation
                if self.elevation is not None:
                    self.elevation = validate_numeric(self.elevation, 'elevation', use_isfinite=False)

                # Verify d0
                if self.d0 is not None:
                    if not isinstance(self.d0, int):
                        raise TypeError('d0 must be int data type')
                    else:
                        self.d0 = mask.array([self.d0], mask=np.isnan([self.d0]))

                # Verify dj
                if self.dj is not None:
                    if not isinstance(self.dj, int):
                        raise TypeError('dj must be int data type')
                    else:
                        self.dj = mask.array([self.dj], mask=np.isnan([self.dj]))
            return

    def initialize_ladder_fuels(
            self,
            sfc: Union[int, float, np.ndarray],
            ht_midstry_live: Union[int, float, np.ndarray],
            ht_midstry_dead: Union[int, float, np.ndarray],
            cbh_ovrstry: Union[int, float, np.ndarray],
            cbh_midstry: Union[int, float, np.ndarray],
            cfl_midstry: Union[int, float, np.ndarray],
            dead_branch_fl: Union[int, float, np.ndarray],
            fmc: Union[int, float, np.ndarray, None] = None,
            wx_date: Optional[int] = None,
            lat: Optional[Union[float, int, np.ndarray]] = None,
            long: Optional[Union[float, int, np.ndarray]] = None,
            elevation: Optional[Union[float, int, np.ndarray]] = None,
            d0: Optional[int] = None,
            dj: Optional[int] = None,
    ) -> None:
        """
        Function to initialize LadderFuels class inputs.

        :param sfc: Estimated surface fuel consumption (kg/m2)
        :param ht_midstry_live: Mean height of live midstory trees (saplings) (m)
        :param ht_midstry_dead: Mean height of the dead midstory cohort (saplings) (m)
        :param cbh_ovrstry: Live overstory canopy base height (aka LCBH) (m)
        :param cbh_midstry: Mean live canopy base height of midstory trees (saplings) (m)
        :param cfl_midstry: Midstory canopy fuel load (kg/m2)
        :param dead_branch_fl: Estimated biomass of branches (roundwood) <= 1 cm diameter (kg/m2).
            Assumes:  (1) continuity with surface fuels,
                      (2) branches are completely consumed  (<= 1 cm roundwood)
        :param fmc: Foliar moisture content of live midstory trees (saplings) (%)
            If None, all of [wx_date, lat, long, elevation], or [d0, dj] must be provided.
        :param wx_date: Date of weather observation (used for fmc calculation) (YYYYMMDD)
        :param lat: Latitude (decimal degrees)
        :param long: Longitude (decimal degrees)
        :param elevation: Elevation (meters)
        :param d0: Date of minimum foliar moisture content
        :param dj: Julian date
        :return: None
        """
        # Initialize inputs
        self.sfc = sfc
        self.ht_midstry_live = ht_midstry_live
        self.ht_midstry_dead = ht_midstry_dead
        self.cbh_ovrstry = cbh_ovrstry
        self.cbh_midstry = cbh_midstry
        self.cfl_midstry = cfl_midstry
        self.dead_branch_fl = dead_branch_fl
        self.fmc = fmc
        self.wx_date = wx_date
        self.lat = lat
        self.long = long
        self.elevation = elevation
        self.d0 = d0
        self.dj = dj

        self._check_array_ladder()
        self._verify_inputs_ladder()
        return

    def get_ladder_params(self, keys: list) -> dict:
        """
        Function to get MoistureContent parameters as a dictionary.

        :param keys: List of Ladder parameter names to retrieve from the Ladder class object
        :return: Dictionary of parameter names and their values
        """
        params = {}
        for key in keys:
            if hasattr(self, key):
                value = getattr(self, key)
                params[key] = value
        return params

    def set_ladder_params(self, set_dict: dict) -> None:
        """
        Function to set Ladder parameters to specific values.

        :param set_dict: Dictionary of Ladder parameter names and the values to assign to the Ladder class object
        :return: None
        """
        # Iterate through the set dictionary and assign values
        for key, value in set_dict.items():
            if hasattr(self, key):  # Check if the class has the attribute
                if isinstance(value, np.ndarray):
                    setattr(self, key, mask.array(value, mask=np.isnan(value)))
                else:
                    setattr(self, key, mask.array([value], mask=np.isnan([value])))
        return

    def run_ladder_fuels(self):
        # Process ladder fuels only if none of the ladder fuel parameters are None
        ladder_fuel_params = [
            self.ht_midstry_live, self.ht_midstry_dead,
            self.cbh_ovrstry, self.cbh_midstry, self.cfl_midstry,
            self.dead_branch_fl
        ]
        if all(param is not None for param in ladder_fuel_params):
            if not self.ladder_inputs_verified:
                self._check_array_ladder()
                self._verify_inputs_ladder()

            if self.fmc is None:
                self.fmc, self.latn, self.d0, self.dj, self.nd = calc_fmc(
                    lat=self.lat,
                    long=self.long,
                    elevation=self.elevation,
                    wx_date=self.wx_date,
                    d0=self.d0,
                    dj=self.dj,
                )

            self.fsg_dead_ladder, self.sfc_dead_ladder = calc_dead_ladder_contributions(
                ht_midstry_dead=self.ht_midstry_dead,
                cbh_ovrstry=self.cbh_ovrstry,
                dead_branch_fl=self.dead_branch_fl,
                m=self.m,
            )

            self.cfl_midstry, self.fsg_live_ladder, self.sfc_live_ladder = calc_live_ladder_contributions(
                multiply_cfl=self.multiply_cfl,
                cfl_midstry=self.cfl_midstry,
                cbh_ovrstry=self.cbh_ovrstry,
                cbh_midstry=self.cbh_midstry,
                ht_midstry_live=self.ht_midstry_live,
                fmc=self.fmc,
                m=self.m,
                fsg=self.fsg,
                sfc=self.sfc,
            )

            self.fsg = calc_min_ladder_fsg(
                fsg=self.fsg,
                fsg_live_ladder=self.fsg_live_ladder,
                fsg_dead_ladder=self.fsg_dead_ladder,
            )

            self.sfc = calc_total_sfc(
                sfc=self.sfc,
                sfc_dead_ladder=self.sfc_dead_ladder,
                sfc_live_ladder=self.sfc_live_ladder,
            )
        return

