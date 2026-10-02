# -*- coding: utf-8 -*-
"""
Created on Thu Oct 16, 11:45:00 2025

@author: Gregory A. Greene
"""
__author__ = ['Gregory A. Greene']

import inspect
import numpy as np
from numpy import ma as mask
from typing import Union, Optional
from operator import itemgetter
from .components import LadderFuels, MoistureContent, RothMC, SFC
from .components.equations import conpyro_eqs, ffmc_adj_eqs
from .components.validation_utils import validate_numeric


class ConPyro(MoistureContent, RothMC, SFC, LadderFuels):
    def __init__(self):
        MoistureContent.__init__(self)
        RothMC.__init__(self)
        SFC.__init__(self)
        LadderFuels.__init__(self)

        # Enable/disable ConPyro processing messages
        self.suppress_messages = False

        # ### Conifer Pyrometrics variables
        # Input variables
        self.cfo_model = None  # CCP Crown Fire Occurrence model type
        self.sros_model = None  # Surface Fire Rate of Spread model type
        self.cros_model = None  # Crown Fire Rate of Spread model type

        # Initialize flags
        self.return_array = False  # Flag to indicate if output should be an array
        self.ccp_inputs_verified = False  # Flag to indicate if CCP inputs have been verified
        self.model_terrain_effects_on_wind = False  # Option to include terrain effects in crown fire rate of spread
        self.model_terrain_effects_on_ffmc = False  # Option to include terrain effects on FFMC
        self.process_ladder = False  # Option to include ladder fuel processing
        self.cfo_params_initialized = False  # Flag to indicate if CFI parameters have been initialized
        self.cros_params_initialized = False  # Flag to indicate if CROS parameters have been initialized
        self.sros_params_initialized = False  # Flag to indicate if SROS parameters have been initialized
        self.smooth_ros = False  # Option to smooth CFI values

        # Interim variables
        self.ref_array = None  # Reference float array for CCP calculations
        self.ref_int_array = None  # Reference integer array for CCP calculations
        self.logit = None  # Crown Fire Initiation logit
        self.cfo_prob = None  # Crown Fire Probability
        self.sfc0 = None  # Adjusted Surface Fuel Consumption for CFIS model
        self.sfc1 = None
        self.cfo_param_b0 = None
        self.cfo_param_b1 = None
        self.cfo_param_b2 = None
        self.cfo_param_b3 = None
        self.cfo_param_b4 = None
        self.cfo_param_b5 = None
        self.sros_param_a = None
        self.sros_param_b = None
        self.sros_param_c = None
        self.cros_param_b1 = None
        self.cros_param_b2 = None
        self.cros_param_b3 = None
        self.cros_param_b4 = None
        self.sros_smooth = None
        self.cros_p_smooth = None
        self.cros_a_smooth = None
        self.cros_smooth = None
        self.hros_smooth = None
        self.bros_smooth = None
        self.hros_cfb = None
        self.cros_a_cfb = None

        # Weather variables
        self.temp = None
        self.rh = None
        self.ws = None
        self.wd = None
        self.fF = None
        self.fW = None
        self.bfw = None
        self.isz = None
        self.isf = None
        self.wsv = None
        self.raz = None
        self.isi = None
        self.bisi = None

        # Topographic variables
        self.slope = None  # Slope steepness (%)
        self.aspect = None  # Slope aspect (degrees)
        self.sf = None  # Slope Factor

        # Fuel variables
        self.cbd = None  # Canopy Bulk Density (kg/m^3)
        self.cfl_ovrstry = None  # Overstory Canopy Fuel Load (kg/m^2)
        self.cfl = None  # Canopy Fuel Load (kg/m^2)
        self.cfc = None  # Canopy Fuel Consumption (kg/m^2)
        self.bcfc = None  # Backing Canopy Fuel Consumption (kg/m^2)
        self.tfc = None  # Total Fuel Consumption (kg/m^2)
        self.btfc = None  # Backing Total Fuel Consumption (kg/m^2)

        # Fire behavior variables
        self.sros = None  # Surface Fire Rate of Spread (m/min)
        self.cros_a = None  # Active Crown Fire Rate of Spread (m/min)
        self.r0 = None  # Critical minimum rate of spread (R0) for active crowning (m/min)
        self.cac = None  # Criterion for Active Crowning (unitless)
        self.cros_p = None  # Passive Crown Fire Rate of Spread (m/min)
        self.cros = None  # Crown Fire Rate of Spread (m/min)
        self.hros = None  # Head Fire Rate of Spread (m/min)
        self.bros = None  # Backing Fire Rate of Spread (m/min)
        self.fire_type = None  # Fire type classification
        self.accel_param = None  # Fire acceleration parameter
        self.cfb = None  # Crown Fraction Burned (proportion, 0-1)
        self.bcfb = None  # Backing Crown Fraction Burned (proportion, 0-1)
        self.sfi = None  # Surface Fire Intensity (kW/m)
        self.cfi = None  # Crown Fire Intensity (kW/m)
        self.hfi = None  # Head Fire Intensity (kW/m)
        self.bfi = None  # Backing Fire Intensity (kW/m)

    def _log(self, msg: str):
        if not self.suppress_messages:
            print(msg)

    def _check_array(self):
        # ### CHECK FOR NUMPY ARRAYS IN INPUT PARAMETERS
        params = inspect.signature(self.initialize).parameters
        param_names = list(params.keys())
        param_list = [getattr(self, param) for param in param_names if param != 'self']

        if any(isinstance(data, np.ndarray) for data in param_list):
            # Set return_array flag to True
            self.return_array = True

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
                        'All arrays must have the same dimensions. '
                        f'The following range of dimensions exists: {shapes}'
                    )

                # Get first input array as a masked array
                first_array = param_list[array_indices[0]]

                # If first array is a character array, change all valid (not nodata) values to 1
                if hasattr(first_array, 'dtype') and first_array.dtype.kind in {'U', 'S'}:
                    # Assume nodata is represented by masked values if MaskedArray, or by empty string otherwise
                    if isinstance(first_array, mask.MaskedArray):
                        valid_mask = ~mask.getmaskarray(first_array)
                    else:
                        valid_mask = first_array != ''
                    # Create an integer array of 1s where valid, 0 elsewhere
                    arr_ones = np.zeros(first_array.shape, dtype=np.int8)
                    arr_ones[valid_mask] = 1
                    # If original was masked, preserve mask
                    if isinstance(first_array, mask.MaskedArray):
                        first_array = mask.array(arr_ones, mask=mask.getmaskarray(first_array))
                    else:
                        first_array = arr_ones
                    # Update param_list as well for downstream use
                    param_list[array_indices[0]] = first_array

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
            self.return_array = False
            # Create float reference array
            self.ref_array = mask.array([0], mask=np.isnan([self.cfo_model])).astype(np.float64)
            # Create integer reference array
            self.ref_int_array = mask.array([0], mask=np.isnan([self.cfo_model])).astype(np.int8)
        return

    def _broadcast_scalar_inputs(self) -> None:
        """
        Function to broadcast scalar inputs to match the shape of the reference array.
        This is called after _verify_inputs() to ensure all ConPyro-specific inputs have the same shape.
        Only broadcasts variables that are not passed to component modules.

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

        if self.return_array and self.ref_array.shape != (1,):
            self.cfo_model = _broadcast_if_scalar(self.cfo_model, np.int8)
            self.sros_model = _broadcast_if_scalar(self.sros_model, np.int8)
            self.cros_model = _broadcast_if_scalar(self.cros_model, np.int8)
            self.ws = _broadcast_if_scalar(self.ws, np.float64)
            self.wd = _broadcast_if_scalar(self.wd, np.float64)
            self.cbd = _broadcast_if_scalar(self.cbd, np.float64)
            self.cfl_ovrstry = _broadcast_if_scalar(self.cfl_ovrstry, np.float64)
            self.slope = _broadcast_if_scalar(self.slope, np.float64)
            self.aspect = _broadcast_if_scalar(self.aspect, np.float64)
        return

    def _verify_inputs(self):
        # Verify cfo_model
        if not isinstance(self.cfo_model, (int, np.ndarray)):
            raise TypeError('cfo_model must be int or numpy ndarray data types')
        if isinstance(self.cfo_model, np.ndarray):
            self.cfo_model = mask.array(self.cfo_model, mask=~np.isfinite(self.cfo_model))
        else:
            self.cfo_model = mask.array(np.full_like(self.ref_int_array, self.cfo_model, dtype=np.int8),
                                        mask=~np.isfinite(self.ref_int_array))
        # Raise error for invalid model choices
        mask_invalid = ~mask.isin(self.cfo_model, [1, 2, 3, 4, 5, 10])
        if np.any(mask_invalid):
            raise Exception('Crown Fire Occurrence model choice is invalid. '
                            'Should be 1, 2, 3, 4, 5 and/or 10.')
        # Raise error for missing CFIS input parameters
        # cfo_model=10 (CFIS) requires cc, time, temp, rh, stn_elev, site_elev, slope, aspect
        if np.any(mask.isin(self.cfo_model, [10])):
            cfis_params = {
                'cc': self.cc, 'time': self.time, 'temp': self.temp,
                'rh': self.rh, 'stn_elev': self.stn_elev, 'site_elev': self.site_elev,
                'slope': self.slope, 'aspect': self.aspect,
            }
            missing = [name for name, val in cfis_params.items() if val is None]
            if missing:
                raise ValueError(
                    'Missing required CFIS input parameters. If running the CFIS model (where cfo_model=10), '
                    'the following input datasets are required:\n'
                    '\tcc, time, temp, rh, stn_elev, site_elev, slope, aspect.\n'
                    f'Missing: {", ".join(missing)}.'
                )

        # Verify sros_model
        if not isinstance(self.sros_model, (int, np.ndarray)):
            raise TypeError('sros_model must be int or numpy ndarray data types')
        if isinstance(self.sros_model, np.ndarray):
            self.sros_model = mask.array(self.sros_model, mask=~np.isfinite(self.sros_model))
        else:
            self.sros_model = mask.array(np.full_like(self.ref_int_array, self.sros_model, dtype=np.int8),
                                         mask=~np.isfinite(self.ref_int_array))
        # Raise error for invalid model choices
        mask_invalid = ~mask.isin(self.sros_model, [1, 2, 3, 4, 12, 13, 20])
        if np.any(mask_invalid):
            raise Exception('Surface Fire Rate of Spread model choice is invalid. '
                            'Should be 1, 2, 3, 4, 12, 13, and/or 20.')

        # Verify cros_model
        if not isinstance(self.cros_model, (int, np.ndarray)):
            raise TypeError('cros_model must be int or numpy ndarray data types')
        if isinstance(self.cros_model, np.ndarray):
            self.cros_model = mask.array(self.cros_model, mask=~np.isfinite(self.cros_model))
        else:
            self.cros_model = mask.array(np.full_like(self.ref_int_array, self.cros_model, dtype=np.int8),
                                         mask=~np.isfinite(self.ref_int_array))
        # Raise error for invalid model choices
        mask_invalid = ~mask.isin(self.cros_model, [1, 2])
        if np.any(mask_invalid):
            raise Exception('Crown Fire Rate of Spread model choice is invalid. Should be 1 and/or 2.')

        # Verify ws
        self.ws = validate_numeric(self.ws, 'ws', use_isfinite=False)
        # Mask negative values
        self.ws = mask.where(self.ws < 0, mask.masked, self.ws)

        # Verify wd
        self.wd = validate_numeric(self.wd, 'wd', use_isfinite=False)

        # Verify cbd
        self.cbd = validate_numeric(self.cbd, 'cbd', ref_array=self.ref_array)
        # Mask negative values
        self.cbd = mask.where(self.cbd < 0, mask.masked, self.cbd)

        # Verify cfl_ovrstry
        self.cfl_ovrstry = validate_numeric(self.cfl_ovrstry, 'cfl_ovrstry', ref_array=self.ref_array)
        # Mask negative values
        self.cfl_ovrstry = mask.where(self.cfl_ovrstry < 0, mask.masked, self.cfl_ovrstry)

        # Verify slope
        if self.slope is not None:
            self.slope = validate_numeric(self.slope, 'slope', use_isfinite=False, clip_min=0)

        # Verify aspect
        if self.aspect is not None:
            self.aspect = validate_numeric(self.aspect, 'aspect', use_isfinite=False)
            # Set negative values to 270 degrees (assuming they represent "flat" terrain)
            self.aspect = mask.where(self.aspect < 0, 270, self.aspect)

        # Verify sfc
        if self.sfc is not None:
            self.sfc = validate_numeric(self.sfc, 'sfc', use_isfinite=False, clip_min=0.1, clip_max=6)

        # Verify model_terrain_effects_on_wind
        if not isinstance(self.model_terrain_effects_on_wind, bool):
            raise TypeError('model_terrain_effects_on_wind must be boolean data type')
        if self.model_terrain_effects_on_wind:
            if (self.slope is None) or (self.aspect is None):
                raise ValueError('When model_terrain_effects_on_wind is True, slope and aspect inputs must be provided.')

        # Verify model_terrain_effects_on_ffmc
        if not isinstance(self.model_terrain_effects_on_ffmc, bool):
            raise TypeError('model_terrain_effects_on_ffmc must be boolean data type')
        if self.model_terrain_effects_on_ffmc:
            if (self.slope is None) or (self.aspect is None):
                raise ValueError('When model_terrain_effects_on_ffmc is True, slope and aspect inputs must be provided.')

        # Verify process_ladder
        if not isinstance(self.process_ladder, bool):
            raise TypeError('process_ladder must be boolean data type')

    def initialize(
            self,
            *,
            cfo_model: Union[int, np.ndarray],              # ConPyro
            sros_model: Union[int, np.ndarray],             # ConPyro
            cros_model: Union[int, np.ndarray],             # ConPyro
            smooth_ros: bool,                               # ConPyro
            model_terrain_effects_on_wind: bool,            # ConPyro
            model_terrain_effects_on_ffmc: bool,            # ConPyro
            process_ladder: bool,                           # Ladder
            season: Union[int, str, np.ndarray, None],      # Moisture Content
            density: Union[int, str, np.ndarray, None],     # ConPyro, Moisture Content
            stand_type: Union[int, str, np.ndarray, None],  # ConPyro, Moisture Content
            cbd: Union[int, float, np.ndarray],             # ConPyro
            cfl_ovrstry: Union[int, float, np.ndarray],     # ConPyro, Ladder
            fsg: Union[int, float, np.ndarray],             # ConPyro, Ladder
            ffl: Union[int, float, np.ndarray],             # ConPyro, SFC
            wfl: Union[int, float, np.ndarray],             # ConPyro, SFC
            gfl: Union[int, float, np.ndarray],             # ConPyro, SFC
            ws: Union[int, float, np.ndarray],              # ConPyro (if wind terrain-effect True)
            wd: Union[int, float, np.ndarray],              # ConPyro (if wind terrain-effect True)
            slope: Optional[Union[int, float, np.ndarray]],   # ConPyro (if either terrain-effect True), Rothermel MC (CFIS Only)
            aspect: Optional[Union[int, float, np.ndarray]],  # ConPyro (if either terrain-effect True), Rothermel MC (CFIS Only)
            wx_date: Union[int, str],       # Moisture Content (if season is None), Ladder (if fmc is None)
            ffmc: Union[int, float, np.ndarray],            # Moisture Content, SFC, ConPyro (if ffmc terrain-effect True)
            dmc: Union[int, float, np.ndarray],             # Moisture Content
            bui: Union[int, float, np.ndarray],             # Moisture Content, SFC
            fuel_type: Union[int, str, np.ndarray, None],   # SFC (CFIS only) - set to None if not using CFIS
            pct_cnfr: Union[int, float, np.ndarray, None],  # SFC (CFIS only) - set to None if not using CFIS
            ht_midstry_live: Union[int, float, np.ndarray, None],   # Ladder
            ht_midstry_dead: Union[int, float, np.ndarray, None],   # Ladder
            cbh_ovrstry: Union[int, float, np.ndarray, None],       # Ladder
            cbh_midstry: Union[int, float, np.ndarray, None],       # Ladder
            cfl_midstry: Union[int, float, np.ndarray, None],       # Ladder
            dead_branch_fl: Union[int, float, np.ndarray, None],    # Ladder
            fmc: Union[int, float, np.ndarray, None],               # Ladder (derived from wx_date or d0/dj if None)
            time: Optional[int] = None,                             # Rothermel MC (CFIS only: cfo_model=10)
            temp: Optional[Union[int, float, np.ndarray]] = None,   # Rothermel MC (CFIS only: cfo_model=10)
            rh: Optional[Union[int, float, np.ndarray]] = None,     # Rothermel MC (CFIS only: cfo_model=10)
            cc: Optional[Union[int, float, np.ndarray]] = None,     # Rothermel MC (CFIS only: cfo_model=10), Moisture Content (if density is None)
            site_elev: Optional[Union[int, float, np.ndarray]] = None,     # Rothermel MC (CFIS only: cfo_model=10)
            stn_elev: Optional[Union[int, float, np.ndarray]] = None,      # Rothermel MC (CFIS only: cfo_model=10)
            elevation: Optional[Union[int, float, np.ndarray]] = None,     # Ladder (if fmc is None), Rothermel MC (CFIS only: cfo_model=10)
            lat: Optional[Union[int, float, np.ndarray]] = None,    # Ladder (if fmc is None)
            long: Optional[Union[int, float, np.ndarray]] = None,   # Ladder (if fmc is None)
            d0: Optional[Union[int, float, np.ndarray]] = None,     # Ladder (if fmc is None, and wx_date is None)
            dj: Optional[Union[int, float, np.ndarray]] = None,     # Ladder (if fmc is None, and wx_date is None)
            sfc: Optional[Union[int, float, np.ndarray]] = None,    # ConPyro (overrides modelled SFC value if not None)
            suppress_messages: bool = False,    # ConPyro (whether to suppress processing messages)
    ) -> None:
        # Initialize parent classes
        MoistureContent.__init__(self)
        RothMC.__init__(self)
        SFC.__init__(self)
        LadderFuels.__init__(self)

        # Enable/disable ConPyro processing messages
        self.suppress_messages = suppress_messages

        # Moisture Content Variables
        self.season = season
        self.density = density
        self.stand_type = stand_type
        self.ffmc = ffmc
        self.dmc = dmc
        self.wx_date = wx_date

        # Rothermel MC Variables
        self.time = time
        self.temp = temp
        self.rh = rh
        self.cc = cc
        self.site_elev = site_elev
        self.stn_elev = stn_elev

        # Surface Fuel Consumption Variables
        self.bui = bui  # Buildup Index
        self.ffl = ffl  # Forest floor load (kg/m2)
        self.wfl = wfl  # Woody fuel load (kg/m2)
        self.gfl = gfl  # Grass fuel load (kg/m2)
        self.fuel_type = fuel_type  # CFFBPS Fuel Type Alphanumeric Code
        self.pct_cnfr = pct_cnfr  # Percent Conifer (%, 0-100)
        self.sfc = sfc  # Surface Fuel Consumption (kg/m2)

        # Ladder Fuel Variables
        self.ht_midstry_live = ht_midstry_live  # Mean height of live midstory trees (saplings) (m)
        self.ht_midstry_dead = ht_midstry_dead  # Mean height of the dead midstory cohort (saplings) (m)
        self.cbh_ovrstry = cbh_ovrstry  # Live overstory canopy base height (aka LCBH) (m)
        self.cbh_midstry = cbh_midstry  # Mean live canopy base height of midstory trees (saplings) (m)
        self.cfl_ovrstry = cfl_ovrstry  # Mean overstory canopy fuel load (kg/m^2)
        self.cfl_midstry = cfl_midstry  # Midstory canopy fuel load (kg/m2)
        self.dead_branch_fl = dead_branch_fl  # Estimated biomass of dead branches (roundwood) <= 1 cm diameter (kg/m2)
        self.fmc = fmc  # Foliar moisture content of live midstory trees (saplings) (%)
        self.fsg = fsg  # Fuel Strata Gap
        self.elevation = elevation  # Elevation (meters)
        self.lat = lat  # Latitude (decimal degrees)
        self.long = long  # Longitude (decimal degrees)
        self.d0 = d0  # Date of minimum foliar moisture content
        self.dj = dj  # Julian date

        # ### Conifer Pyrometrics variables
        # Input variables
        self.cfo_model = cfo_model  # CCP model type
        self.sros_model = sros_model  # Surface Fire Rate of Spread model type
        self.cros_model = cros_model  # Crown Fire Rate of Spread model type

        # Flags
        self.process_ladder = process_ladder  # Whether to process ladder fuels
        self.smooth_ros = smooth_ros  # Whether to smooth rate of spread outputs
        self.model_terrain_effects_on_wind = model_terrain_effects_on_wind  # Whether to model terrain effects on wind
        self.model_terrain_effects_on_ffmc = model_terrain_effects_on_ffmc  # Whether to model terrain effects on FFMC

        # Weather variables
        self.ws = ws
        self.wd = wd

        # Topographic variables
        self.slope = slope  # Slope steepness (%)
        self.aspect = aspect  # Slope aspect (degrees)

        # Stand and fuel variables
        self.cbd = cbd  # Canopy Bulk Density

        self._check_array()
        self._verify_inputs()
        self._broadcast_scalar_inputs()
        return

    def get_cfo_params(self) -> None:
        """
        Function to get Crown Fire Occurrence (CFO) parameters.

        :return: None
        """
        # Get CFI parameters
        self.cfo_param_b0 = np.full_like(self.ref_array, np.nan, dtype=np.float64)
        self.cfo_param_b1 = np.full_like(self.ref_array, np.nan, dtype=np.float64)
        self.cfo_param_b2 = np.full_like(self.ref_array, np.nan, dtype=np.float64)
        self.cfo_param_b3 = np.full_like(self.ref_array, np.nan, dtype=np.float64)
        self.cfo_param_b4 = np.full_like(self.ref_array, np.nan, dtype=np.float64)
        self.cfo_param_b5 = np.full_like(self.ref_array, np.nan, dtype=np.float64)
        for model in mask.unique(self.cfo_model[~self.cfo_model.mask]):
            mask_model = self.cfo_model == model
            params = conpyro_eqs.CFO_PARAMS_DICT[int(model)]
            self.cfo_param_b0[mask_model] = params[0]
            self.cfo_param_b1[mask_model] = params[1]
            self.cfo_param_b2[mask_model] = params[2]
            self.cfo_param_b3[mask_model] = params[3]
            self.cfo_param_b4[mask_model] = params[4]
            self.cfo_param_b5[mask_model] = params[5]
        # Set flag to indicate CFI parameters have been initialized
        self.cfo_params_initialized = True
        return

    def get_cros_params(self) -> None:
        """
        Function to get Crown Rate of Spread (cros) parameters.
        :return: None
        """
        self.cros_param_b1 = np.full_like(self.ref_array, np.nan, dtype=np.float64)
        self.cros_param_b2 = np.full_like(self.ref_array, np.nan, dtype=np.float64)
        self.cros_param_b3 = np.full_like(self.ref_array, np.nan, dtype=np.float64)
        self.cros_param_b4 = np.full_like(self.ref_array, np.nan, dtype=np.float64)
        for model in mask.unique(self.cros_model[~self.cros_model.mask]):
            mask_model = self.cros_model == model
            params = conpyro_eqs.CROS_PARAMS_DICT[int(model)]
            self.cros_param_b1[mask_model] = params[0]
            self.cros_param_b2[mask_model] = params[1]
            self.cros_param_b3[mask_model] = params[2]
            self.cros_param_b4[mask_model] = params[2]
        # Set flag to indicate CROS parameters have been initialized
        self.cros_params_initialized = True
        return

    def get_sros_params(self) -> None:
        """
        Function to get Surface Rate of Spread (sros) parameters.
        :return: None
        """
        self.sros_param_a = np.full_like(self.ref_array, np.nan, dtype=np.float64)
        self.sros_param_b = np.full_like(self.ref_array, np.nan, dtype=np.float64)
        self.sros_param_c = np.full_like(self.ref_array, np.nan, dtype=np.float64)
        for model in mask.unique(self.sros_model[~self.sros_model.mask]):
            mask_model = self.sros_model == model
            params = conpyro_eqs.SROS_PARAMS_DICT[int(model)]
            self.sros_param_a[mask_model] = params[0]
            self.sros_param_b[mask_model] = params[1]
            self.sros_param_c[mask_model] = params[2]
        # Set flag to indicate SROS parameters have been initialized
        self.sros_params_initialized = True
        return

    def process_cfo(self) -> None:
        """
        Function to process Crown Fire Occurrence (CFO) calculations.
        :return:
        """
        self._log('[ConPyro] process_cfo: calculating FFMC function...')
        self.fF = conpyro_eqs.calc_ff(self.mc_sa)

        if self.model_terrain_effects_on_wind:
            self._log('\t[ConPyro] process_cfo: applying slope effects (invert wind/aspect, slope factor, ISZ/ISF, WSV/RAZ)...')
            self._log('\t[ConPyro] process_cfo: inverting wind direction and slope aspect...')
            self.wd, self.aspect = conpyro_eqs.calc_inverted_wind_aspect(self.wd, self.aspect)

            self._log('\t[ConPyro] process_cfo: calculating slope factor...')
            self.sf = conpyro_eqs.calc_sf(self.slope)

            self._log('\t[ConPyro] process_cfo: calculating ISZ (no wind/slope ISI)...')
            self.isz = conpyro_eqs.calc_isz(self.fF)

            self._log('\t[ConPyro] process_cfo: calculating ISF (slope/wind adjusted ISI)...')
            if not self.sros_params_initialized:
                self.get_sros_params()
            self.isf = conpyro_eqs.calc_isf(self.isz, self.sf, self.sfc, self.sros_model,
                                            self.sros_param_a, self.sros_param_b, self.sros_param_c)

            self._log('\t[ConPyro] process_cfo: calculating effective wind speed and direction (WSV/RAZ)...')
            self.wsv, self.raz = conpyro_eqs.calc_wsv_raz(self.ws, self.wd, self.isf, self.fF, self.aspect)
        else:
            self._log('\t[ConPyro] process_cfo: slope effects disabled; using input wind speed and direction.')
            self.wsv = self.ws
            self.raz = self.wd

        self._log('\t[ConPyro] process_cfo: calculating wind and backing fire indices...')
        self.fW = conpyro_eqs.calc_fw(self.wsv)
        self.isi = conpyro_eqs.calc_isi(self.fW, self.fF)
        self.bfw = conpyro_eqs.calc_bfw(self.wsv)
        self.bisi = conpyro_eqs.calc_bisi(self.bfw, self.fF)

        self._log('\t[ConPyro] process_cfo: calculating crown fire occurrence probability...')
        if not self.cfo_params_initialized:
            self.get_cfo_params()
        self.logit = conpyro_eqs.calc_logit(self.wsv, self.fsg, self.mc_sa, self.sfc,
                                            self.cfo_model, self.cfo_param_b0, self.cfo_param_b1,
                                            self.cfo_param_b2, self.cfo_param_b3, self.cfo_param_b4,
                                            self.cfo_param_b5)
        self.cfo_prob = conpyro_eqs.calc_cfo_prob(self.logit)
        self._log('\t[ConPyro] process_cfo: complete.')
        return

    def process_intensity(self) -> None:
        self.sfi = conpyro_eqs.calc_sfi(self.hros, self.sfc)
        self.cfi = conpyro_eqs.calc_cfi(self.hros, self.cfc)
        self.hfi = conpyro_eqs.calc_hfi(self.hros, self.tfc)
        return

    def process_fire_metrics(self) -> None:
        # Calculate fire type and mask invalid areas
        self.fire_type = conpyro_eqs.calc_fire_type(self.cfo_prob, self.cac)
        self.fire_type = mask.where(np.isfinite(self.stand_type), self.fire_type, mask.masked).astype(np.int8)

        # Calculate crown fraction burned
        self.cfb = conpyro_eqs.calc_cfb(self.hros, self.cros_a)

        # Calculate acceleration parameter
        self.accel_param = conpyro_eqs.calc_accel_param(self.cfb, self.density)

        # Calculate canopy fuel load and consumption
        self.cfl = conpyro_eqs.calc_cfl(self.cfl_ovrstry)
        self.cfc = conpyro_eqs.calc_cfc(self.cfl, self.cfb)

        # Calculate total fuel consumption
        self.tfc = conpyro_eqs.calc_tfc(self.sfc, self.cfc)
        return

    def process_ladder_fuels(self) -> None:
        if self.process_ladder:
            self.run_ladder_fuels()
        return

    def process_roth_mc(self) -> None:
        cfis_mask = self.cfo_model == 10
        if np.any(cfis_mask):
            self.get_roth_mc()
            self.mc_sa[cfis_mask] = self.mc_roth[cfis_mask]
        return

    def process_mc_sa(self) -> None:
        if self.model_terrain_effects_on_ffmc:
            self.ffmc = ffmc_adj_eqs.adjust_ffmc_for_terrain(self.ffmc, self.slope, self.aspect)
        self.run_mc()
        return

    def process_ros(self) -> None:
        # Get SROS parameters
        if not self.sros_params_initialized:
            self.get_sros_params()

        # Calculate surface fire rate of spread and mask invalid areas
        self.sros = conpyro_eqs.calc_sros(self.isi, self.sfc, self.sros_model,
                                          self.sros_param_a, self.sros_param_b, self.sros_param_c)
        self.sros = mask.where(np.isfinite(self.stand_type), self.sros, mask.masked)

        # Get CROS parameters
        if not self.cros_params_initialized:
            self.get_cros_params()

        # Calculate active crown fire rate of spread
        self.cros_a = conpyro_eqs.calc_cros_a(self.wsv, self.cbd, self.mc_sa, self.cros_model,
                                              self.cros_param_b1, self.cros_param_b2,
                                              self.cros_param_b3, self.cros_param_b4)

        # Calculate critical minimum rate of spread
        self.r0 = conpyro_eqs.calc_r0(self.cbd)

        # Calculate criterion for active crowning
        self.cac = conpyro_eqs.calc_cac(self.cros_a, self.r0)

        # Calculate passive crown fire rate of spread and mask invalid areas
        self.cros_p = conpyro_eqs.calc_cros_p(self.cros_a, self.cac)
        self.cros_p = mask.where(np.isfinite(self.stand_type), self.cros_p, mask.masked)

        # Calculate crown fire rate of spread and mask invalid areas
        self.cros = conpyro_eqs.calc_cros(self.cros_a, self.cros_p, self.cac)
        self.cros = mask.where(np.isfinite(self.stand_type), self.cros, mask.masked)

        # Calculate head fire rate of spread
        if self.smooth_ros:
            # Apply smoothing if requested
            self.hros = conpyro_eqs.calc_ros_smooth(self.sros, self.cros_p, self.cros_a, self.cfo_prob, self.cac)
        else:
            self.hros = conpyro_eqs.calc_hros(self.sros, self.cros, self.cfo_prob)

        # Calculate backing fire rate of spread and mask invalid areas
        self.bros = conpyro_eqs.calc_bros(self.bisi, self.sfc, self.sros_model,
                                          self.sros_param_a, self.sros_param_b, self.sros_param_c)
        self.bros = mask.where(np.isfinite(self.stand_type), self.bros, mask.masked)
        return

    def process_sfc(self) -> None:
        if self.sfc is None:
            self.run_sfc(self.cfo_model)
        return

    def return_params(self, out_request: list) -> list:
        """
        Function to return requested conpyro module parameters.

        Masked values in integer arrays are filled with -9; masked values in
        float arrays are filled with np.nan.

        :param out_request: List of parameter names to return
        :return: List of requested outputs.
        """
        _INT_FILL = -128

        def _fill_value(arr):
            """Return the appropriate fill value for *arr*'s dtype."""
            try:
                if np.issubdtype(arr.dtype, np.integer):
                    return _INT_FILL
            except AttributeError:
                pass
            return np.nan

        def _safe_int(arr):
            """
            If *arr* is an unsigned integer array, promote it to the smallest
            signed integer dtype wide enough to hold all values plus -128.
            uint8  -> int16   (int8 max is 127, too narrow for existing uint8 values)
            uint16 -> int32
            uint32 -> int64
            uint64 -> int64   (best effort; values > 2^63-1 would overflow but
                               are extremely unlikely in a fire-type/model array)
            """
            _uint_to_sint = {
                np.uint8: np.int16,
                np.uint16: np.int32,
                np.uint32: np.int64,
                np.uint64: np.int64,
            }
            target = _uint_to_sint.get(arr.dtype.type)
            if target is not None:
                if isinstance(arr, np.ma.MaskedArray):
                    return arr.astype(target)
                return arr.astype(target)
            return arr

        def _filled(val):
            """Convert *val* to a plain numpy array with masked cells filled."""
            if isinstance(val, np.ma.MaskedArray):
                val = _safe_int(val)
                return val.filled(_fill_value(val))
            if val is not None:
                arr = _safe_int(np.ma.masked_array(val))
                return arr.filled(_fill_value(arr))
            return np.nan

        if self.return_array:
            return [_filled(getattr(self, var, np.nan)) for var in out_request]
        else:
            return [
                getattr(self, var, np.nan).item() if hasattr(getattr(self, var, np.nan), "item")
                else np.nan
                for var in out_request
            ]

    def run_conpyro(self) -> None:
        self._log('[ConPyro] Starting run_conpyro...')
        self._log('[ConPyro] Step 1/8: process_mc_sa')
        self.process_mc_sa()
        self._log('[ConPyro] Step 2/8: process_roth_mc')
        self.process_roth_mc()
        self._log('[ConPyro] Step 3/8: process_sfc')
        self.process_sfc()
        self._log('[ConPyro] Step 4/8: process_ladder_fuels')
        self.process_ladder_fuels()
        self._log('[ConPyro] Step 5/8: process_cfo')
        self.process_cfo()
        self._log('[ConPyro] Step 6/8: process_ros')
        self.process_ros()
        self._log('[ConPyro] Step 7/8: process_fire_metrics')
        self.process_fire_metrics()
        self._log('[ConPyro] Step 8/8: process_intensity')
        self.process_intensity()
        self._log('[ConPyro] run_conpyro complete.')
        return
