# -*- coding: utf-8 -*-
"""
Rothermel (1983) Dead Fine Fuel Moisture Content Calculation

Created on Thu Oct 16, 11:45:00 2025

@author: Gregory A. Greene
"""
__author__ = ['Gregory A. Greene']

import inspect
import numpy as np
from numpy import ma as mask
from datetime import datetime as dt
from typing import Union
from .validation_utils import validate_numeric
from operator import itemgetter

from .equations.rothermel_eqs import (
    calc_reference_fm,
    calc_correction_fm,
)


class RothMC(object):
    def __init__(self):
        """Initialize RothMC class with necessary parameters."""
        # Initialize input variables
        self.wx_date = None
        self.time = None
        self.temp = None
        self.rh = None
        self.site_elev = None
        self.stn_elev = None
        self.aspect = None
        self.slope = None
        self.cc = None

        # Initialize flags
        self.roth_return_array = False  # Boolean to indicate if output should be an array
        self.roth_inputs_verified = False  # Boolean to indicate if inputs have been verified

        # Initialize intermediate variables
        self.month = None
        self.time_of_day = None
        self.ref_fm = None  # Reference Fuel Moisture

        # Initialize output variables
        self.mc_roth = None  # Final Moisture Content output

        # Dict for valid months
        self.valid_months = {
            1: 'January',
            2: 'February',
            3: 'March',
            4: 'April',
            5: 'May',
            6: 'June',
            7: 'July',
            8: 'August',
            9: 'September',
            10: 'October',
            11: 'November',
            12: 'December'
        }


    def _check_array_roth(self) -> None:
        """
        Function to check if any of the input parameters are numpy arrays.

        :return: None
        """
        # ### CHECK FOR NUMPY ARRAYS IN INPUT PARAMETERS
        params = inspect.signature(self.initialize_roth).parameters
        param_names = list(params.keys())
        param_list = [getattr(self, param) for param in param_names if param != 'self']

        if any(isinstance(data, np.ndarray) for data in param_list):
            # Set return_array flag to True
            self.roth_return_array = True

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

                # Get first input array as a masked array
                first_array = param_list[array_indices[0]]
                # Create float reference array
                self.ref_array = mask.array(
                    np.full(first_array.shape, 0, dtype=np.float64),
                    mask=~np.isfinite(first_array)
                )

                # Create integer reference array
                self.ref_int_array = mask.array(
                    np.full(first_array.shape, 0, dtype=np.int8),
                    mask=~np.isfinite(first_array)
                )
        else:
            # Set return_array flag to False
            self.roth_return_array = False
            # Create float reference array
            self.ref_array = mask.array([0], mask=np.isnan([self.temp])).astype(np.float64)
            # Create integer reference array
            self.ref_int_array = mask.array([0], mask=np.isnan([self.temp])).astype(np.int8)
        return

    def _verify_inputs_roth(self) -> None:
        """
        Function to verify MoistureContent input parameters.

        :return: None
        """
        # Verify wx_date
        if not isinstance(self.wx_date, (int, str)):
            raise ValueError(f'wx_date must be an integer (YYYYMMDD) or string (YYYY-MM-DD). '
                             f'Provided value: {self.wx_date}')
        elif isinstance(self.wx_date, int):
            try:
                wx_date_dt = dt.strptime(str(self.wx_date), '%Y%m%d')
            except ValueError:
                raise ValueError(f'wx_date integer must be in YYYYMMDD format. Provided value: {self.wx_date}')
        else:  # string
            try:
                wx_date_dt = dt.strptime(self.wx_date, '%Y-%m-%d')
            except ValueError:
                raise ValueError(f'wx_date string must be in YYYY-MM-DD format. Provided value: {self.wx_date}')
        self.month = wx_date_dt.strftime('%B')  # Get month name

        # Verify time
        if not (isinstance(self.time, int) and 0 <= self.time <= 2400):
            raise ValueError('time must be an integer between 0 and 2400 representing time in HHMM format.')
        else:
            # Make full like ref_array, filled with the time value
            self.time = mask.array(
                np.full(self.ref_array.shape, self.time, dtype=np.int16),
                mask=self.ref_array.mask,
                dtype=np.int16
            )

        # Verify temp
        self.temp = validate_numeric(self.temp, 'temp')

        # Verify rh
        self.rh = validate_numeric(self.rh, 'rh', clip_min=0, clip_max=100)

        # Verify site_elev
        self.site_elev = validate_numeric(self.site_elev, 'site_elev')

        # Verify stn_elev
        self.stn_elev = validate_numeric(self.stn_elev, 'stn_elev')

        # Verify aspect
        self.aspect = validate_numeric(self.aspect, 'aspect')
        # Modify aspect value to range between 0-360
        self.aspect = self.aspect % 360

        # Verify slope (%)
        self.slope = validate_numeric(self.slope, 'slope')

        # Verify cc
        self.cc = validate_numeric(self.cc, 'cc', clip_min=0, clip_max=100)

        # Set mc_inputs_verified flag to True
        self.roth_inputs_verified = True
        return

    def initialize_roth(
            self,
            wx_date: Union[int, str],
            time: int,
            temp: Union[int, float, np.ndarray],
            rh: Union[int, float, np.ndarray],
            aspect: Union[int, float, np.ndarray],
            slope: Union[int, float, np.ndarray],
            cc: Union[int, float, np.ndarray],
            site_elev: Union[int, float, np.ndarray],
            stn_elev: Union[int, float, np.ndarray],
    ) -> None:
        """Store scalars (month, time) + arrays."""
        # store scalars
        self.wx_date = wx_date
        self.time = time

        # store arrays
        self.temp = temp
        self.rh = rh
        self.aspect = aspect
        self.slope = slope
        self.cc = cc
        self.site_elev = site_elev
        self.stn_elev = stn_elev

        self._check_array_roth()
        self._verify_inputs_roth()

        return

    def get_roth_mc(self) -> None:
        """
        Function to compute Dead Fine Fuel Moisture Content using Rothermel (1983) method.

        :return: numpy ndarray of Dead Fine Fuel Moisture Content values
        """
        if not self.roth_inputs_verified:
            self._check_array_roth()
            self._verify_inputs_roth()

        # Determine if daytime (0800-2000)
        is_daytime = (self.time >= 800) & (self.time < 2000)
        
        # Calculate reference and correction fuel moisture using refactored functions
        ref_fm = calc_reference_fm(self.temp, self.rh, is_daytime)
        cor_fm = calc_correction_fm(
            self.time, 
            self.site_elev, 
            self.stn_elev, 
            self.aspect, 
            self.slope, 
            self.cc, 
            self.month, 
            is_daytime
        )
        
        # Combine to get final moisture content
        self.mc_roth = ref_fm + cor_fm

        return