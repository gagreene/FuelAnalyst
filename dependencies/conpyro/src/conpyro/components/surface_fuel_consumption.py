# -*- coding: utf-8 -*-
"""
Created on Thu Oct 16, 11:45:00 2025

@author: Gregory A. Greene
"""
__author__ = ['Gregory A. Greene, map.n.trowel@gmail.com']

import inspect
import numpy as np
from numpy import ma as mask
from typing import Union
from operator import itemgetter
from .equations.sfc_eqs import calc_degroot_ffc, calc_fbp_sfc, compare_fuels
from .validation_utils import validate_numeric


class SFC(object):
    def __init__(self):
        # Initialize inputs
        self.fuel_type = None  # CFFBPS Fuel Type Alphanumeric Code
        self.ffmc = None  # Fine Fuel Moisture Code
        self.bui = None  # Buildup Index
        self.ffl = None  # Forest floor load (kg/m2)
        self.wfl = None  # Woody fuel load (kg/m2)
        self.gfl = None  # Grass fuel load (kg/m2)
        self.pct_cnfr = None  # Percent Conifer (%, 0-100)

        # Initialize flags
        self.sfc_return_array = False  # Boolean to indicate if output should be an array
        self.sfc_inputs_verified = False  # Boolean to indicate if inputs have been verified

        # Initialize outputs
        self.ffc_degroot = None  # Forest floor consumption using De Groot method (kg/m2)
        self.ffc_fbp = None  # Forest floor consumption using FBP method (kg/m2)
        self.wfc_fbp = None  # Woody Fuel Consumption using FBP method (kg/m2)
        self.sfc_fbp = None  # Surface Fuel Consumption using FBP method (kg/m2)
        self.ffc = None  # Forest floor consumption (kg/m2)
        self.wfc = None  # Woody fuel consumption (kg/m2)
        self.sfc = None  # Surface fuel consumption (kg/m2)

        # CFFBPS Fuel Type Alphanumeric-Numeric Code Lookup Table
        self.fbp_ftcode_alphatonum_dict = {
            'C1': 1,  # C-1
            'C2': 2,  # C-2
            'C3': 3,  # C-3
            'C4': 4,  # C-4
            'C5': 5,  # C-5
            'C6': 6,  # C-6
            'C7': 7,  # C-7
            'D1': 8,  # D-1
            'D2': 9,  # D-2
            'M1': 10,  # M-1
            'M2': 11,  # M-2
            'M3': 12,  # M-3
            'M4': 13,  # M-4
            'O1a': 14,  # O-1a
            'O1b': 15,  # O-1b
            'S1': 16,  # S-1
            'S2': 17,  # S-2
            'S3': 18,  # S-3
            'NF': 19,  # NF (non-fuel)
            'WA': 20,  # WA (water)
        }

    def _check_array_sfc(self) -> None:
        """
        Function to check if any of the input parameters are numpy arrays.

        :return: None
        """
        # ### CHECK FOR NUMPY ARRAYS IN INPUT PARAMETERS
        params = inspect.signature(self.initialize_sfc).parameters
        param_names = list(params.keys())
        param_list = [getattr(self, param) for param in param_names if param != 'self']

        if any(isinstance(data, np.ndarray) for data in param_list):
            # Set return_array flag to True
            self.sfc_return_array = True

            # Get indices of input parameters that are arrays
            array_indices = [i for i in range(len(param_list)) if isinstance(param_list[i], np.ndarray)]

            arrays = itemgetter(*array_indices)(param_list)
            if isinstance(arrays, np.ndarray):
                arrays = [arrays]

            # Use first non-scalar array as the reference shape; fall back to first array if all scalar.
            non_scalar_arrays = [arr for arr in arrays if np.asarray(arr).size > 1]
            first_array = non_scalar_arrays[0] if non_scalar_arrays else arrays[0]

            # Verify non-scalar array inputs all share the same shape.
            if len(non_scalar_arrays) > 1:
                shapes = {arr.shape for arr in non_scalar_arrays}
                if len(shapes) > 1:
                    raise ValueError(
                        'All non-scalar arrays must have the same dimensions. '
                        f'The following range of dimensions exists: {shapes}'
                    )

            # Get first input array as a masked array
            if '<U' in str(first_array.dtype):
                # Convert the string representations to numeric codes using the lookup table
                convert_to_numeric = np.vectorize(self.fbp_ftcode_alphatonum_dict.get)
                converted_fuel_type = convert_to_numeric(first_array)
                if None in converted_fuel_type:
                    raise ValueError('Unknown fuel type found, conversion failed.')
                first_array = converted_fuel_type.astype(np.int8)

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
            self.sfc_return_array = False
            # Convert fuel_type if string
            if isinstance(self.fuel_type, str):
                fuel_type_numeric = self.fbp_ftcode_alphatonum_dict.get(self.fuel_type)
                if fuel_type_numeric is None:
                    raise ValueError(f'Unknown fuel type: {self.fuel_type}')
                self.fuel_type = fuel_type_numeric
            # Create float reference array
            self.ref_array = mask.array([0], mask=np.isnan([float(self.fuel_type)])).astype(np.float64)
            # Create integer reference array
            self.ref_int_array = mask.array([0], mask=np.isnan([float(self.fuel_type)])).astype(np.int8)
        return

    def _broadcast_scalar_inputs_sfc(self) -> None:
        """
        Function to broadcast scalar inputs to match the shape of the reference array.
        This is called after _verify_inputs_sfc() to ensure all SFC-specific inputs have the same shape.
        Only broadcasts variables that are not passed to other component modules.

        :return: None
        """
        def _broadcast_if_scalar(arr, dtype):
            if arr is None:
                return None

            arr = mask.array(arr, copy=False)
            if arr.size != 1:
                return arr

            value = np.asarray(arr.data).reshape(-1)[0]
            value_mask = np.asarray(mask.getmaskarray(arr)).reshape(-1)[0]
            return mask.array(
                np.full(self.ref_array.shape, value, dtype=dtype),
                mask=np.full(self.ref_array.shape, bool(value_mask), dtype=bool)
            )

        if self.sfc_return_array and self.ref_array.shape != (1,):
            self.fuel_type = _broadcast_if_scalar(self.fuel_type, np.int8)
            self.ffmc = _broadcast_if_scalar(self.ffmc, np.float64)
            self.bui = _broadcast_if_scalar(self.bui, np.float64)
            self.ffl = _broadcast_if_scalar(self.ffl, np.float64)
            self.wfl = _broadcast_if_scalar(self.wfl, np.float64)
            self.gfl = _broadcast_if_scalar(self.gfl, np.float64)
            self.pct_cnfr = _broadcast_if_scalar(self.pct_cnfr, np.float64)
        return

    def _verify_inputs_sfc(self) -> None:
        """
        Function to verify SFC input parameters.

        :return:
        """
        # ### VERIFY ALL INPUTS AND CONVERT TO MASKED NUMPY ARRAYS
        # Verify fuel_type
        if not isinstance(self.fuel_type, (int, str, np.ndarray, type(None))):
            raise TypeError('fuel_type must be either None, int, string, numpy ndarray data types')
        elif isinstance(self.fuel_type, np.ndarray):
            if '<U' in str(self.fuel_type.dtype):
                invalid_value = np.int8(-99)  # Define an explicit invalid value
                # Convert using np.vectorize and replace unknown fuel types with invalid_value
                convert_to_numeric = np.vectorize(lambda x: self.fbp_ftcode_alphatonum_dict.get(x, invalid_value))
                self.fuel_type = convert_to_numeric(self.fuel_type).astype(np.int8)
            if self.fuel_type.dtype != np.int8:
                self.fuel_type = np.asarray(self.fuel_type, dtype=np.int8)
            self.fuel_type = mask.array(self.fuel_type, mask=np.isnan(self.fuel_type))
        elif isinstance(self.fuel_type, str):
            self.fuel_type = mask.array([self.fbp_ftcode_alphatonum_dict.get(self.fuel_type)],
                                        mask=np.isnan([self.fbp_ftcode_alphatonum_dict.get(self.fuel_type)]))
        elif isinstance(self.fuel_type, type(None)):
            self.fuel_type = self.ref_int_array
        else:
            self.fuel_type = mask.array([self.fuel_type], mask=np.isnan([self.fuel_type]))

        # # Verify ffmc
        # if not isinstance(self.ffmc, (int, float, np.ndarray)):
        #     raise TypeError('ffmc must be either int, float, or numpy ndarray data types')
        # elif isinstance(self.ffmc, np.ndarray):
        #     self.ffmc = mask.array(self.ffmc, mask=np.isnan(self.ffmc))
        # else:
        #     self.ffmc = mask.array([self.ffmc], mask=np.isnan([self.ffmc]))

        # Verify bui
        self.bui = validate_numeric(self.bui, 'bui', use_isfinite=False, clip_min=5, clip_max=200)

        # Verify ffl
        self.ffl = validate_numeric(self.ffl, 'ffl', use_isfinite=False, clip_min=0, clip_max=5)

        # Verify wfl
        self.wfl = validate_numeric(self.wfl, 'wfl', use_isfinite=False, clip_min=0, clip_max=2)

        # Verify gfl
        self.gfl = validate_numeric(self.gfl, 'gfl', use_isfinite=False)

        # Verify pct_cnfr
        if isinstance(self.pct_cnfr, np.ndarray):
            self.pct_cnfr = validate_numeric(self.pct_cnfr, 'pct_cnfr', use_isfinite=False)
        elif isinstance(self.pct_cnfr, (int, float)):
            if np.isnan(self.pct_cnfr) or self.pct_cnfr is None:
                self.pct_cnfr = 50  # Default to 50%
            self.pct_cnfr = validate_numeric(self.pct_cnfr, 'pct_cnfr', use_isfinite=False)
        else:
            raise TypeError('pct_cnfr must be either int, float, or numpy ndarray data types')

        return

    def initialize_sfc(
            self,
            fuel_type: Union[int, str, np.ndarray],
            ffmc: Union[int, float, np.ndarray],
            bui: Union[int, float, np.ndarray],
            ffl: Union[int, float, np.ndarray],
            wfl: Union[int, float, np.ndarray],
            gfl: Union[int, float, np.ndarray],
            pct_cnfr: Union[int, float, np.ndarray]
    ) -> None:
        """
        Function to initialize SFC class inputs.

        :param fuel_type: CFFBPS Fuel Type Alphanumeric Code
        :param ffmc: Fine Fuel Moisture Code
        :param bui: Buildup Index
        :param ffl: Forest floor load (kg/m2)
        :param wfl: Woody fuel load (kg/m2)
        :param gfl: Grass fuel load (kg/m2)
        :param pct_cnfr: Percent Conifer (%, 0-100)
        :return: None
        """
        # Initialize inputs
        self.fuel_type = fuel_type
        self.ffmc = ffmc
        self.bui = bui
        self.ffl = ffl
        self.wfl = wfl
        self.gfl = gfl
        self.pct_cnfr = pct_cnfr

        # Verify input parameters
        self._check_array_sfc()
        self._verify_inputs_sfc()
        self._broadcast_scalar_inputs_sfc()
        return

    def get_sfc_params(self, keys: list) -> dict:
        """
        Function to get MoistureContent parameters as a dictionary.

        :param keys: List of SFC parameter names to retrieve from the SFC class object
        :return: Dictionary of parameter names and their values
        """
        params = {}
        for key in keys:
            if hasattr(self, key):
                value = getattr(self, key)
                params[key] = value
        return params

    def set_sfc_params(self, set_dict: dict) -> None:
        """
        Function to set SFC parameters to specific values.

        :param set_dict: Dictionary of SFC parameter names and the values to assign to the SFC class object
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

    def run_sfc(self, cfo_model: np.ndarray) -> None:
        """
        Function to calculate Surface Fuel Consumption (SFC).

        :return: None
        """
        if not self.sfc_inputs_verified:
            self._check_array_sfc()
            self._verify_inputs_sfc()
            self._broadcast_scalar_inputs_sfc()

        # Calculate De Groot FFC
        self.ffc_degroot = calc_degroot_ffc(bui=self.bui, ffl=self.ffl)

        # Calculate FBP SFC, FFC, and WFC for CFIS model (cfo model 10) only
        if 10 in np.unique(self.cfo_model):
            self.ffc_fbp, self.wfc_fbp, self.sfc_fbp = calc_fbp_sfc(
                fuel_type=self.fuel_type,
                ffmc=self.ffmc,
                bui=self.bui,
                pct_cnfr=self.pct_cnfr,
                gfl=self.gfl
            )
        else:
            self.ffc_fbp = np.full_like(self.ref_array, np.inf, dtype=np.float64)
            self.wfc_fbp = np.full_like(self.ref_array, np.inf, dtype=np.float64)
            self.sfc_fbp = np.full_like(self.ref_array, np.inf, dtype=np.float64)

        # Compare fuel consumption estimates and apply bounds checking
        self.ffc, self.wfc, self.sfc = compare_fuels(
            ffc_degroot=self.ffc_degroot,
            ffc_fbp=self.ffc_fbp,
            wfc_fbp=self.wfc_fbp,
            sfc_fbp=self.sfc_fbp,
            ffl=self.ffl,
            wfl=self.wfl
        )

        return
