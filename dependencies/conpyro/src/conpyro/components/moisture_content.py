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

from .equations.moisture_eqs import (
    calc_mc_ffmc,
    calc_mc_dmc,
    calc_mc_sa,
    calc_season,
    calc_stand_density,
    get_adjusted_mc_areas,
)


class MoistureContent(object):
    def __init__(self):
        # Initialize inputs
        self.suppress_messages = False  # Boolean to control message printing
        self.wx_date = None
        self.ffmc = None
        self.dmc = None
        self.season = None
        self.cc = None
        self.stand_type = None  # Options: (D) deciduous, (DF) Douglas-fir, (MW) Mixedwood, (P) Pine, (S) Spruce
        self.model_mcsa = 'corrected'  # Options: 'corrected' (default) or 'original'

        # Initialize flags
        self.mc_return_array = False  # Boolean to indicate if output should be an array
        self.mc_inputs_verified = False  # Boolean to indicate if inputs have been verified
        self.use_adjusted_mc = None  # Boolean to indicate if adjusted MC should be used

        # Initialize Moisture Content variables
        self.ref_array = None  # Reference masked array for calculations
        self.ref_int_array = None  # Reference masked integer array for calculations
        self.month_day = None  # Month and day extracted from wx_date
        self.density = None  # Stand density class
        self.mc_ffmc = None  # Moisture Content derived from FFMC
        self.mc_dmc = None  # Moisture Content derived from DMC

        # Initialize outputs
        self.mc_sa = None  # Stand Adjusted Moisture Content

        # Dict for season cutoff dates
        self.season_cutoff_dates_dict = {
            1: 531,   # 'Spring' End of spring June 1
            2: 615,   # 'Transitional' End of spring/summer transition June 15
            3: 901,   # 'Summer' End of summer September 1
            4: 1231,  # 'Fall' Fall goes to end of year December 31
        }

        # Alpha to numeric dict for season codes
        self.season_code_dict_inv = {
            'Sp': 1,     # 'Spring'
            'Sp-Su': 2,  # 'Transitional' == 'Sp-Su'
            'T': 2,      # 'Transitional' == 'Sp-Su'
            'Su': 3,     # 'Summer'
            'F': 4,      # 'Fall'
        }

        # Alpha to numeric dict for stand density codes
        self.density_code_dict_inv = {
            'L': 1,  # 'Low'
            'M': 2,  # 'Moderate'
            'H': 3   # 'High'
        }

        # Alpha to numeric dict for stand type codes
        self.stand_type_code_dict_inv = {
            'D': 1,   # 'Deciduous'
            'DF': 2,  # 'Douglas-fir'
            'MW': 3,  # 'Mixedwood'
            'P': 4,   # 'Pine'
            'S': 5    # 'Spruce'
        }

        # Input parameter dictionary
        self.alpha_input_param_dict = {
            'season': self.season_code_dict_inv,
            'density': self.density_code_dict_inv,
            'stand_type': self.stand_type_code_dict_inv
        }

        ## Dict for Stand-Adjusted Moisture Content (mcsa) parameters using numerical codes
        # effm_sa_dict returns coeff1, coeff2 for the Wotton and Beverly (2007) fuel moisture content model
        self.mc_sa_coeff_dict = {
            '111': (0.7299, 0.5221),    # Spring, Low, Deciduous
            '112': (0.0202, 0.6264),    # Spring, Low, Douglas-fir
            '113': (0.7977, 0.5042),    # Spring, Low, Mixedwood
            '114': (0.8517, 0.3709),    # Spring, Low, Pine
            '115': (0.7391, 0.4285),    # Spring, Low, Spruce
            '121': (0.4387, 0.7133),    # Spring, Moderate, Deciduous
            '122': (-0.271, 0.8176),    # Spring, Moderate, Douglas-fir
            '123': (0.5065, 0.6954),    # Spring, Moderate, Mixedwood
            '124': (0.5605, 0.5621),    # Spring, Moderate, Pine
            '125': (0.4479, 0.6197),    # Spring, Moderate, Spruce
            '131': (-0.2449, 1.0462),   # Spring, High, Deciduous
            '132': (-0.9546, 1.1505),   # Spring, High, Douglas-fir
            '133': (-0.1771, 1.0283),   # Spring, High, Mixedwood
            '134': (-0.1231, 0.895),    # Spring, High, Pine
            '135': (-0.2357, 0.9526),   # Spring, High, Spruce
            '311': (0.1348, 0.8691),    # Summer, Low, Deciduous
            '312': (-0.5749, 0.9734),   # Summer, Low, Douglas-fir
            '313': (0.2026, 0.8512),    # Summer, Low, Mixedwood
            '314': (0.2566, 0.7179),    # Summer, Low, Pine
            '315': (0.144, 0.7755),     # Summer, Low, Spruce
            '321': (-0.1564, 1.0603),   # Summer, Moderate, Deciduous
            '322': (-0.8661, 1.1646),   # Summer, Moderate, Douglas-fir
            '323': (-0.0886, 1.0424),   # Summer, Moderate, Mixedwood
            '324': (-0.0346, 0.9091),   # Summer, Moderate, Pine
            '325': (-0.1472, 0.9667),   # Summer, Moderate, Spruce
            '331': (-0.84, 1.3932),     # Summer, High, Deciduous
            '332': (-1.5497, 1.4975),   # Summer, High, Douglas-fir
            '333': (-0.7722, 1.3753),   # Summer, High, Mixedwood
            '334': (-0.7182, 1.242),    # Summer, High, Pine
            '335': (-0.8308, 1.2996),   # Summer, High, Spruce
            '411': (0.1601, 0.9495),    # Fall, Low, Deciduous
            '412': (-0.55, 1.0538),     # Fall, Low, Douglas-fir
            '413': (0.2279, 0.9316),    # Fall, Low, Mixedwood
            '414': (0.2819, 0.7983),    # Fall, Low, Pine
            '415': (0.1693, 0.8559),    # Fall, Low, Spruce
            '421': (-0.1311, 1.1407),   # Fall, Moderate, Deciduous
            '422': (-0.8408, 1.245),    # Fall, Moderate, Douglas-fir
            '423': (-0.0633, 1.1228),   # Fall, Moderate, Mixedwood
            '424': (-0.0093, 0.9895),   # Fall, Moderate, Pine
            '425': (-0.1219, 1.0471),   # Fall, Moderate, Spruce
            '431': (-0.8147, 1.4736),   # Fall, High, Deciduous
            '432': (-1.5244, 1.5779),   # Fall, High, Douglas-fir
            '433': (-0.7469, 1.4557),   # Fall, High, Mixedwood
            '434': (-0.6929, 1.3224),   # Fall, High, Pine
            '435': (-0.8055, 1.38)      # Fall, High, Spruce
        }

        # Fast coefficient lookup tables using [season, density, stand] integer indexing.
        # Valid coded ranges are season 1-4, density 1-3, stand 1-5.
        self.mc_sa_coeff_a = np.full((5, 4, 6), np.nan, dtype=np.float64)
        self.mc_sa_coeff_b = np.full((5, 4, 6), np.nan, dtype=np.float64)
        for key, (a_val, b_val) in self.mc_sa_coeff_dict.items():
            season_code = int(key[0])
            density_code = int(key[1])
            stand_code = int(key[2])
            self.mc_sa_coeff_a[season_code, density_code, stand_code] = a_val
            self.mc_sa_coeff_b[season_code, density_code, stand_code] = b_val

    def _log(self, msg: str):
        if not self.suppress_messages:
            print(msg)

    def _check_array_mc(self) -> None:
        """
        Function to check if any of the input parameters are numpy arrays.

        :return: None
        """
        # ### CHECK FOR NUMPY ARRAYS IN INPUT PARAMETERS
        params = inspect.signature(self.initialize_mc).parameters
        param_names = list(params.keys())
        param_list = [getattr(self, param) for param in param_names if param != 'self']

        if any(isinstance(data, np.ndarray) for data in param_list):
            # Set return_array flag to True
            self.mc_return_array = True

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

            if '<U' in str(first_array.dtype):
                # Convert the string representations to numeric codes using the lookup table
                convert_to_numeric = np.vectorize(self.alpha_input_param_dict[param_names[array_indices[0]]].get)
                converted_season = convert_to_numeric(first_array)
                if None in converted_season:
                    raise ValueError('Unknown season found, conversion failed.')
                first_array = converted_season.astype(np.int8)
                del convert_to_numeric, converted_season

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

            # Release temporary references as early as possible.
            del arrays, non_scalar_arrays, first_array, array_indices
        else:
            # Set return_array flag to False
            self.mc_return_array = False
            # Create float reference array
            self.ref_array = mask.array([0], mask=np.isnan([self.season])).astype(np.float64)
            # Create integer reference array
            self.ref_int_array = mask.array([0], mask=np.isnan([self.season])).astype(np.int8)

        del params, param_names, param_list
        return

    def _broadcast_scalar_inputs(self) -> None:
        """
        Function to broadcast scalar inputs to match the shape of the reference array.
        This is called after _verify_inputs_mc() to ensure all inputs have the same shape.

        :return: None
        """
        def _broadcast_if_scalar(arr: Optional[mask.MaskedArray], dtype):
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

        if self.mc_return_array and self.ref_array.shape != (1,):
            self.season = _broadcast_if_scalar(self.season, np.int8)
            self.density = _broadcast_if_scalar(self.density, np.int8)
            self.stand_type = _broadcast_if_scalar(self.stand_type, np.int8)
            self.ffmc = _broadcast_if_scalar(self.ffmc, np.float64)
            self.dmc = _broadcast_if_scalar(self.dmc, np.float64)
            self.cc = _broadcast_if_scalar(self.cc, np.float64)
        return

    def _verify_inputs_mc(self) -> None:
        """
        Function to verify MoistureContent input parameters.

        :return: None
        """
        # Verify season
        if self.season is not None:
            if isinstance(self.season, (int, float)):
                if self.season not in self.season_code_dict_inv.values():
                    raise ValueError('season code invalid')
                self.season = mask.array([self.season], mask=~np.isfinite([self.season]))
            elif isinstance(self.season, str):
                if self.season not in self.season_code_dict_inv.keys():
                    raise ValueError('season string invalid')
                else:
                    self.season = self.season_code_dict_inv[self.season]
                    self.season = mask.array([self.season], mask=~np.isfinite([self.season]))
            elif isinstance(self.season, np.ndarray):
                if '<U' in str(self.season.dtype):
                    # Convert the string representations to numeric codes using the lookup table
                    convert_to_numeric = np.vectorize(self.season_code_dict_inv.get)
                    converted_season = convert_to_numeric(self.season)
                    if None in converted_season:
                        raise ValueError('Unknown season found, conversion failed.')
                    self.season = converted_season
                    del convert_to_numeric, converted_season
                self.season = mask.array(self.season, mask=~np.isfinite(self.season)).astype(np.int8)

                # Apply an additional mask to remove seasons that are not in the season code dictionary
                valid_season_types = self.season_code_dict_inv.values()  # Get valid numeric codes
                invalid_mask = ~mask.isin(self.season, list(valid_season_types))
                self.season = mask.array(self.season, mask=invalid_mask | self.season.mask)
                del valid_season_types, invalid_mask
            else:
                raise TypeError('season must be int, str, or numpy ndarray data types')
        else:
            if self.wx_date is None:
                raise ValueError('Either season or wx_date must be provided for moisture content calculations.')

        # Verify density
        if self.density is not None:
            if isinstance(self.density, (int, float)):
                if self.density not in self.density_code_dict_inv.values():
                    raise ValueError('density code invalid')
                self.density = mask.array([self.density], mask=~np.isfinite([self.density]))
            elif isinstance(self.density, str):
                if self.density not in self.density_code_dict_inv.keys():
                    raise ValueError('density string invalid')
                else:
                    self.density = self.density_code_dict_inv[self.density]
                    self.density = mask.array([self.density], mask=~np.isfinite([self.density]))
            elif isinstance(self.density, np.ndarray):
                if '<U' in str(self.density.dtype):
                    # Convert the string representations to numeric codes using the lookup table
                    convert_to_numeric = np.vectorize(self.density_code_dict_inv.get)
                    converted_density = convert_to_numeric(self.density)
                    if None in converted_density:
                        raise ValueError('Unknown density found, conversion failed.')
                    self.density = converted_density
                    del convert_to_numeric, converted_density
                self.density = mask.array(self.density, mask=~np.isfinite(self.density)).astype(np.int8)

                # Apply an additional mask to remove densities that are not in the density code dictionary
                valid_density_types = self.density_code_dict_inv.values()  # Get valid numeric codes
                invalid_mask = ~mask.isin(self.density, list(valid_density_types))
                self.density = mask.array(self.density, mask=invalid_mask | self.density.mask)
                del valid_density_types, invalid_mask
            else:
                raise TypeError('density must be int, str, or numpy ndarray data types')
        else:
            if self.cc is None:
                raise ValueError('Either density or canopy cover (cc) must be provided '
                                 'for moisture content calculations.')

        # Verify stand_type
        if not isinstance(self.stand_type, (int, str, np.ndarray)):
            raise TypeError('stand_type must be int, str, or numpy ndarray data types')
        elif isinstance(self.stand_type, str):
            if self.stand_type not in self.stand_type_code_dict_inv.keys():
                raise ValueError('stand_type string invalid')
            else:
                self.stand_type = self.stand_type_code_dict_inv[self.stand_type]
                self.stand_type = mask.array([self.stand_type], mask=~np.isfinite([self.stand_type]))
        elif isinstance(self.stand_type, np.ndarray):
            if '<U' in str(self.stand_type.dtype):
                # Convert the string representations to numeric codes using the lookup table
                convert_to_numeric = np.vectorize(self.stand_type_code_dict_inv.get)
                converted_stand_type = convert_to_numeric(self.stand_type)
                if None in converted_stand_type:
                    raise ValueError('Unknown stand_type found, conversion failed.')
                self.stand_type = converted_stand_type
                del convert_to_numeric, converted_stand_type
            self.stand_type = mask.array(self.stand_type, mask=~np.isfinite(self.stand_type)).astype(np.int8)

            # Apply an additional mask to remove stand_types that are not in the stand type code dictionary
            valid_stand_types = self.stand_type_code_dict_inv.values()  # Get valid numeric codes
            invalid_mask = ~mask.isin(self.stand_type, list(valid_stand_types))
            self.stand_type = mask.array(self.stand_type, mask=invalid_mask | self.stand_type.mask)
            del valid_stand_types, invalid_mask
        else:
            if self.stand_type not in self.stand_type_code_dict_inv.values():
                raise ValueError('stand_type code invalid')

        # Verify ffmc
        self.ffmc = validate_numeric(self.ffmc, 'ffmc')
        # Modify ffmc value to range between 80-97
        self.ffmc = mask.clip(self.ffmc, 80, 97)

        # Verify dmc
        self.dmc = validate_numeric(self.dmc, 'dmc')
        # Modify dmc value to range between 10-200
        self.dmc = mask.clip(self.dmc, 10, 200)

        # Verify wx_date
        if self.wx_date is not None:
            if not isinstance(self.wx_date, (int, str)):
                raise TypeError('wx_date must be int or str data types')
            try:
                date_string = str(self.wx_date)
                dt.fromisoformat(f'{date_string[:4]}-{date_string[4:6]}-{date_string[6:]}')
                self.month_day = int(date_string[4:6] + date_string[6:8])
            except ValueError:
                raise ValueError('wx_date must be formatted as: YYYYMMDD')

        # Verify cc
        if self.cc is not None:
            self.cc = validate_numeric(self.cc, 'cc', clip_min=0, clip_max=100)

        # Verify model_mcsa
        if not isinstance(self.model_mcsa, str):
            raise TypeError('model_mcsa must be a string data type')
        self.model_mcsa = self.model_mcsa.lower()
        if self.model_mcsa not in {'corrected', 'original'}:
            raise ValueError("model_mcsa must be either 'corrected' or 'original'")

        # Validate and broadcast scalar inputs to match array shapes
        if self.mc_return_array and self.ref_array.shape != (1,):
            # Collect all non-scalar arrays to check shapes
            array_params = {
                'season': self.season,
                'density': self.density,
                'stand_type': self.stand_type,
                'ffmc': self.ffmc,
                'dmc': self.dmc,
                'cc': self.cc
            }
            
            # Get shapes of all non-scalar arrays
            array_shapes = {}
            for param_name, param_value in array_params.items():
                if param_value is not None and np.asarray(param_value).size > 1:
                    array_shapes[param_name] = param_value.shape
            
            # If there are multiple different shapes, raise an error
            if len(set(array_shapes.values())) > 1:
                raise ValueError(
                    'All array inputs must have the same shape. '
                    f'Found shapes: {array_shapes}'
                )
            
            # Broadcast scalar inputs to match the reference array shape
            self._broadcast_scalar_inputs()

            del array_params, array_shapes
        
        # Set mc_inputs_verified flag to True
        self.mc_inputs_verified = True
        return

    def initialize_mc(
            self,
            season: Union[int, str, np.ndarray, None],
            density: Union[int, str, np.ndarray, None],
            stand_type: Union[int, str, np.ndarray],
            ffmc: Union[int, float, np.ndarray],
            dmc: Union[int, float, np.ndarray],
            wx_date: Optional[Union[int, str]] = None,
            cc: Optional[Union[int, float, np.ndarray]] = None,
            model_mcsa: str = 'corrected',
            suppress_messages: bool = False,
    ) -> None:
        """
        Function to initialize MoistureContent class inputs.

        :param season: Season code or string (1-4 or 'Sp', 'T', 'Su', 'F')
        :param density: Stand density string or code (1-3, or 'H', 'M', 'L'). If None, will be calculated from canopy cover.
        :param stand_type: Stand type string or code
        :param wx_date: Date of weather observation (used for fmc calculation) (YYYYMMDD)
        :param ffmc: CFFWIS Fine Fuel Moisture Code
        :param dmc: CFFWIS Drought Moisture Code
        :param cc: Canopy Cover percentage (0-100)
        :param model_mcsa: Moisture content model variant ('corrected' or 'original')
        :param suppress_messages: Suppress messages
        :return: None
        """
        # Initialize inputs
        self.suppress_messages = suppress_messages
        self.season = season
        self.density = density
        self.stand_type = stand_type
        self.wx_date = wx_date
        self.ffmc = ffmc
        self.dmc = dmc
        self.cc = cc
        self.model_mcsa = model_mcsa

        # Verify input parameters
        self._check_array_mc()
        self._verify_inputs_mc()

        return

    def get_mc_params(self, keys: list) -> dict:
        """
        Function to get MoistureContent parameters as a dictionary.

        :param keys: List of MC parameter names to retrieve from the MC class object
        :return: Dictionary of parameter names and their values
        """
        params = {}
        for key in keys:
            if hasattr(self, key):
                value = getattr(self, key)
                params[key] = value
        return params

    def set_mc_params(self, set_dict: dict) -> None:
        """
        Function to set MC parameters to specific values.

        :param set_dict: Dictionary of MC parameter names and the values to assign to the MC class object
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

    def run_mc(self):
        self._log('\t[MoistureContent] Starting run_mc...')

        if not self.mc_inputs_verified:
            self._log('\t[MoistureContent] Verifying inputs...')
            self._check_array_mc()
            self._verify_inputs_mc()

        if self.season is None:
            self._log('\t[MoistureContent] Calculating season from wx_date...')
            self.season = calc_season(
                ref_int_array=self.ref_int_array,
                month_day=self.month_day,
                season_cutoff_dates_dict=self.season_cutoff_dates_dict,
            )
        if self.density is None:
            self._log('\t[MoistureContent] Calculating stand density from cc...')
            self.density = calc_stand_density(
                ref_int_array=self.ref_int_array,
                cc=self.cc,
            )

        self._log('\t[MoistureContent] Determining adjusted-MC areas...')
        self.use_adjusted_mc = get_adjusted_mc_areas(
            ref_int_array=self.ref_int_array,
            stand_type=self.stand_type,
            stand_type_code_dict_inv=self.stand_type_code_dict_inv,
        )
        self._log('\t[MoistureContent] Calculating mc_ffmc...')
        self.mc_ffmc = calc_mc_ffmc(
            ref_array=self.ref_array,
            ffmc=self.ffmc,
        )
        self._log('\t[MoistureContent] Calculating mc_dmc...')
        self.mc_dmc = calc_mc_dmc(
            ref_array=self.ref_array,
            dmc=self.dmc,
        )
        self._log('\t[MoistureContent] Calculating mc_sa...')
        self.mc_sa = calc_mc_sa(
            ref_array=self.ref_array,
            season=self.season,
            density=self.density,
            stand_type=self.stand_type,
            ffmc=self.ffmc,
            mc_ffmc=self.mc_ffmc,
            mc_dmc=self.mc_dmc,
            use_adjusted_mc=self.use_adjusted_mc,
            mc_sa_coeff_a=self.mc_sa_coeff_a,
            mc_sa_coeff_b=self.mc_sa_coeff_b,
            model_mcsa=self.model_mcsa,
        )
        self._log('\t[MoistureContent] run_mc complete.')
        return