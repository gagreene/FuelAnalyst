# -*- coding: utf-8 -*-
"""
Created on Thu Oct 16, 11:45:00 2025

@author: Gregory A. Greene
"""
__author__ = ['Gregory A. Greene']

import inspect
import warnings
from contextlib import contextmanager
from copy import copy
from functools import wraps
import numpy as np
from numpy import ma as mask
from typing import Union, Optional, ClassVar
from operator import itemgetter
from .components import LadderFuels, MoistureContent, RothMC, SFC
from .components.equations import cheney_eqs, cheney_terrain_eqs, conpyro_eqs, ffmc_adj_eqs, grass_eqs, moisture_eqs
from .components.validation_utils import validate_numeric


class ConPyro(MoistureContent, RothMC, SFC, LadderFuels):
    # Only documented component inputs/outputs participate in stage state transfer.
    _FOREST_STAGE_CONTRACTS: ClassVar[dict[str, tuple[str, str, str]]] = {
        'run_mc': (
            'season density stand_type ffmc dmc cc',
            ('mc_ffmc mc_dmc mc_sa use_adjusted_mc '
             'season density stand_type ffmc dmc cc'),
            'mc_inputs_verified mc_return_array month_day model_mcsa _using_forest_codes _forest_moisture_cache'),
        'run_sfc': (
            'fuel_type ffmc bui ffl wfl gfl pct_cnfr cfo_model',
            'ffc_degroot ffc_fbp wfc_fbp sfc_fbp ffc wfc sfc',
            'sfc_inputs_verified sfc_return_array'),
        'run_ladder_fuels': (
            ('sfc ht_midstry_live ht_midstry_dead cbh_ovrstry cbh_midstry '
             'cfl_midstry dead_branch_fl fmc lat long elevation d0 dj fsg wx_date'),
            ('fsg_live_ladder fsg_dead_ladder sfc_live_ladder sfc_dead_ladder '
             'sfc fsg cfl_midstry fmc latn d0 dj nd'),
            'ladder_inputs_verified ladder_return_array'),
        'get_roth_mc': (
            'temp rh aspect slope cc site_elev stn_elev time',
            'mc_roth', 'roth_inputs_verified roth_return_array month time_of_day'),
        '_calculate_forest_wind': (
            ('ws wd aspect slope mc_sa mc_ffmc sros_mc_ffmc sfc sros_model stand_type _cheney_mask cheney_mf gcf model_terrain_effects_on_wind '
             'sros_param_a sros_param_b sros_param_c sros_param_d sros_param_e'),
            ('fF fW bfw isi bisi sf isz isf wsv raz '
             'sros_param_a sros_param_b sros_param_c sros_param_d sros_param_e'),
            'sros_params_initialized'),
        '_calculate_forest_cfo': (
            ('wsv fsg mc_sa sfc cbd cfo_model '
             'cfo_param_b0 cfo_param_b1 cfo_param_b2 cfo_param_b3 cfo_param_b4 cfo_param_b5'),
            ('logit cfo_prob cfo_param_b0 cfo_param_b1 cfo_param_b2 '
             'cfo_param_b3 cfo_param_b4 cfo_param_b5'), 'cfo_params_initialized'),
        '_calculate_forest_crown_ros': (
            ('wsv cbd mc_sa cros_model stand_type '
             'cros_param_b1 cros_param_b2 cros_param_b3 cros_param_b4'),
            ('cros_a r0 cac cros_p cros cros_param_b1 cros_param_b2 '
             'cros_param_b3 cros_param_b4'), 'cros_params_initialized'),
        '_calculate_forest_metrics': (
            'cfo_prob cac stand_type hros cros_a _metrics_density cfl_ovrstry sfc cbd sros_model cros_model cfo_model',
            'fire_type cfb accel_param cfl cfc tfc', ''),
    }
    _STAGE_NO_COPY_BACK: ClassVar[frozenset[str]] = frozenset({'season', 'density'})

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
        self._season_codes = self._density_codes = None
        self._using_forest_codes = False
        self._forest_moisture_cache = False
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
        self.sros_param_d = None
        self.sros_param_e = None
        self.sros_isi = None
        self.sros_bisi = None
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

    @property
    def season_codes(self) -> mask.MaskedArray | None:
        """Snapshot of normalized season codes from the latest forest moisture run."""
        return None if self._season_codes is None else self._season_codes.copy()

    @property
    def density_codes(self) -> mask.MaskedArray | None:
        """Snapshot of normalized density codes from the latest forest moisture run."""
        return None if self._density_codes is None else self._density_codes.copy()

    def _log(self, msg: str):
        if not self.suppress_messages:
            print(msg)

    def _check_array(self):
        """Set the output grid from the first array, including a single array."""
        arrays = [getattr(self, name) for name in inspect.signature(self.initialize).parameters
                  if isinstance(getattr(self, name), np.ndarray)
                  and getattr(self, name).ndim > 0]
        self.return_array = bool(arrays)
        if arrays:
            if len({arr.shape for arr in arrays}) > 1:
                raise ValueError("All arrays must have the same dimensions.")
            shape = arrays[0].shape
            # Curing supplies grid shape but is consumed only by O1 forward
            # spread. It must never impose a mask on independent components.
            source_item = next(((name, getattr(self, name))
                           for name in inspect.signature(self.initialize).parameters
                            if name not in ('gcf', 'cheney_mf_override')
                            and isinstance(getattr(self, name), np.ndarray)
                            and getattr(self, name).ndim > 0), None)
            if source_item is None:
                invalid = np.zeros(shape, dtype=bool)
            else:
                source_name, source = source_item
                first = mask.asarray(source)
                if first.dtype.kind in "USO":
                    invalid = mask.getmaskarray(first) | (first.data == "")
                else:
                    invalid = mask.getmaskarray(first) | ~np.isfinite(first.data)
                if source_name in ('cfo_model', 'sros_model', 'cros_model'):
                    invalid &= (mask.getmaskarray(first)
                                | ~self._raw_missing(first, shape=shape))
                elif source_name in ('season', 'density', 'dmc'):
                    invalid &= ~self._raw_missing(first, shape=shape)
        else:
            invalid = [False]
            shape = (1,)
        if getattr(self, '_domain_policy_active', False):
            # Stand classification, not an arbitrary first input, defines fuel.
            invalid = np.zeros(shape, dtype=bool)
        self.ref_array = mask.array(np.zeros(shape, dtype=np.float64), mask=invalid)
        self.ref_int_array = mask.array(np.zeros(shape, dtype=np.int8), mask=invalid)

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
            self.sros_model = _broadcast_if_scalar(self.sros_model, np.int16)
            self.cros_model = _broadcast_if_scalar(self.cros_model, np.int8)
            self.ws = _broadcast_if_scalar(self.ws, np.float64)
            self.wd = _broadcast_if_scalar(self.wd, np.float64)
            self.cbd = _broadcast_if_scalar(self.cbd, np.float64)
            self.cfl_ovrstry = _broadcast_if_scalar(self.cfl_ovrstry, np.float64)
            self.fsg = _broadcast_if_scalar(self.fsg, np.float64)
            self.sfc = _broadcast_if_scalar(self.sfc, np.float64)
            self.slope = _broadcast_if_scalar(self.slope, np.float64)
            self.aspect = _broadcast_if_scalar(self.aspect, np.float64)
        return

    def _normalize_stand_type(self) -> None:
        """Classify before narrowing integers; preserve raw data for diagnostics."""
        if self.stand_type is None:
            raise ValueError('stand_type is required')
        was_array = isinstance(self.stand_type, np.ndarray)
        raw = mask.asarray(self.stand_type)
        self._stand_type_input = raw.copy()
        codes = np.zeros(raw.shape, dtype=np.int8)
        explicit_zero = np.zeros(raw.shape, dtype=bool)
        raw_mask = mask.getmaskarray(raw)
        if raw.dtype.kind in 'iuf':
            present = ~raw_mask & np.isfinite(raw.data)
            recognized = present & np.isin(raw.data, [1, 2, 3, 4, 5, 10, 20, 21, 22])
            # Classify before casting: large integer sentinels must not wrap.
            codes[recognized] = raw.data[recognized].astype(np.int8)
            explicit_zero = present & (raw.data == 0)
            self._stand_codes = codes
            self._explicit_nonfuel = explicit_zero
            self._nonfuel_policy_active = bool(np.any(codes == 0))
            return

        def label_code(label):
            if isinstance(label, (bytes, np.bytes_)):
                try:
                    label = label.decode('ascii', 'strict')
                except UnicodeDecodeError:
                    return 0
            wheat_labels = {'WHEAT_UNHARVESTED': 20, 'WHEAT_HARVESTED': 21, 'WHEAT_BALED': 22,
                            'wheat_unharvested': 20, 'wheat_harvested': 21, 'wheat_baled': 22}
            return wheat_labels.get(label, self.stand_type_code_dict_inv.get(label, 0))

        if raw.dtype.kind in 'US':
            present = ~raw_mask
            labels, inverse = np.unique(raw.data[present], return_inverse=True)
            mapped = np.fromiter(
                (label_code(label) for label in labels),
                dtype=np.int8, count=labels.size)
            codes[present] = mapped[inverse]
            self._stand_codes = codes
            self._explicit_nonfuel = explicit_zero
            self._nonfuel_policy_active = bool(np.any(codes == 0))
            # Parent forest validation handles numeric codes; never pass raw
            # byte labels through its Unicode-only conversion path.
            self.stand_type = codes.copy() if was_array else int(codes.item())
            return
        for index in np.ndindex(raw.shape):
            if raw_mask[index]:
                continue
            value = raw.data[index]
            if isinstance(value, (bool, np.bool_)):
                continue
            if isinstance(value, (str, bytes, np.bytes_)):
                codes[index] = label_code(value)
            elif isinstance(value, (int, float, np.integer, np.floating)) and np.isfinite(value):
                if value in (1, 2, 3, 4, 5, 10, 20, 21, 22):
                    codes[index] = int(value)
                explicit_zero[index] = value == 0
        self._stand_codes = codes
        self._explicit_nonfuel = explicit_zero
        self._nonfuel_policy_active = bool(np.any(codes == 0))
        self.stand_type = codes.copy() if was_array else int(codes.item())

    def _set_stand_domain(self) -> None:
        codes = np.broadcast_to(self._stand_codes, self.ref_array.shape)
        self.nonfuel_mask = (codes == 0).copy()
        self.valid_fuel_mask = ~self.nonfuel_mask
        self.inferred_nonfuel_mask = (
            self.nonfuel_mask & ~np.broadcast_to(self._explicit_nonfuel, codes.shape)).copy()
        self.inferred_nonfuel_count = int(np.count_nonzero(self.inferred_nonfuel_mask))
        self._wheat_mask = np.isin(codes, [20, 21, 22])
        self.grass_mask = np.isin(codes, [10, 20, 21, 22])
        if self._domain_policy_active:
            self.stand_type = mask.array(codes, mask=False, copy=True)

    def _grid_numeric(self, value) -> mask.MaskedArray:
        if value is None:
            return mask.array(np.zeros(self.ref_array.shape), mask=True)
        raw = mask.atleast_1d(mask.asarray(value, dtype=float))
        missing = mask.getmaskarray(raw) | ~np.isfinite(raw.data)
        return mask.array(np.broadcast_to(np.where(missing, 0., raw.data), self.ref_array.shape),
                          mask=np.broadcast_to(missing, self.ref_array.shape), copy=True)

    def _raw_missing(self, value, *, shape: tuple | None = None) -> np.ndarray:
        """Locate raw None/NaN values without treating explicit masks as data."""
        raw = mask.atleast_1d(mask.asarray(value))
        missing = mask.getmaskarray(raw).copy()
        if raw.dtype.kind in 'biuf':
            missing |= np.isnan(raw.data)
        elif raw.dtype.kind == 'O':
            is_missing = np.frompyfunc(
                lambda item: item is None or (
                    isinstance(item, (float, np.floating)) and np.isnan(item)), 1, 1)
            missing |= is_missing(raw.data).astype(bool)
        return np.broadcast_to(missing, self.ref_array.shape if shape is None else shape).copy()

    def _default_selector(self, name: str, defaults: np.ndarray,
                          selected: np.ndarray) -> mask.MaskedArray:
        """Replace unmasked None/NaN only; retain explicit selector masks."""
        value = getattr(self, name)
        raw = mask.atleast_1d(mask.asarray(value))
        data = np.array(np.broadcast_to(raw.data, self.ref_array.shape), copy=True)
        missing = np.broadcast_to(mask.getmaskarray(raw), data.shape).copy()
        defaulted = self._raw_missing(value) & ~missing & selected
        # Object dtype also accommodates defaults alongside public string aliases.
        if data.dtype.kind in 'US':
            data = data.astype(object)
        data[defaulted] = np.broadcast_to(defaults, data.shape)[defaulted]
        self.forest_model_default_counts[name] = int(np.count_nonzero(
            defaulted & ~self.grass_mask))
        return mask.array(data, mask=missing | ~selected)

    def _resolve_surface_models(self) -> None:
        forest = self.valid_fuel_mask & ~self.grass_mask
        self._mc_ffmc_path = forest & (
            self._raw_missing(self.dmc) | self._raw_missing(self.season)
            | self._raw_missing(self.density))
        self._invalid_moisture_context = np.zeros(forest.shape, dtype=bool)
        self._invalid_context_codes = np.zeros(forest.shape, dtype=bool)
        self.forest_model_default_counts = {}
        defaults = np.select([np.isin(self._stand_codes, [1, 2, 3, 4, 5]), self._stand_codes == 20,
                              self._stand_codes == 21, self._stand_codes == 22],
                             [np.where(self._mc_ffmc_path, 12, 13), 32, 33, 34], default=30)
        defaults = np.broadcast_to(defaults, self.ref_array.shape)
        self.sros_model = conpyro_eqs.normalize_sros_model(
            self._default_selector('sros_model', defaults, self.valid_fuel_mask))
        # R CFO 10/11 are Python 4/5; Python 10 remains the explicit CFIS model.
        for name, default, choices in (
                ('cfo_model', np.where(self._mc_ffmc_path, 4, 5), [1, 2, 3, 4, 5, 10]),
                ('cros_model', np.ones(self.ref_array.shape), [1, 2, 3])):
            resolved = self._default_selector(name, default, forest)
            data = np.zeros(resolved.shape, dtype=np.int8)
            present = ~mask.getmaskarray(resolved)
            values = resolved.data[present]
            if not np.all(np.isin(values, choices)):
                raise ValueError(f'{name} model choice is invalid. Should be {choices}.')
            data[present] = values.astype(np.int8)
            setattr(self, name, mask.array(data, mask=~present))
        self.o1_mask = (np.isin(self.sros_model.data, conpyro_eqs.GRASS_SROS_IDS)
                        & ~mask.getmaskarray(self.sros_model) & self.valid_fuel_mask)
        self._cheney_mask = (np.isin(self.sros_model.data, conpyro_eqs.CHENEY_SROS_IDS)
                           & ~mask.getmaskarray(self.sros_model) & self.valid_fuel_mask)

    def _prepare_cheney_inputs(self) -> None:
        """Preserve raw values and normalize only fields consumed by Cheney cells."""
        selected = self._cheney_mask
        self.cheney_mf = None
        if not np.any(selected):
            return
        self.cheney_mf = mask.masked_all(self.ref_array.shape)
        if self.ws is None or self.gcf is None:
            raise ValueError('ws and gcf are required for Cheney surface models')
        for name in ('ws', 'gcf'):
            value = self._grid_numeric(getattr(self, name))
            normalized = (cheney_eqs.normalize_cheney_wind(value[selected], self.sros_model.data[selected])
                          if name == 'ws' else cheney_eqs.normalize_cheney_curing(value[selected]))
            value[selected] = mask.masked_invalid(normalized)
            setattr(self, name, value)
        def consumed(name):
            value = getattr(self, name)
            return None if value is None else self._grid_numeric(value)[selected]
        self.cheney_mf[selected] = mask.masked_invalid(cheney_eqs.calc_cheney_moisture(
            consumed('temp'), consumed('rh'), consumed('cheney_mf_override')))

    def _prepare_grass_inputs(self) -> None:
        limited = self.grass_mask | self.o1_mask
        if np.any(limited):
            for name in ('ws', 'wd', 'slope', 'aspect', 'cbd', 'cfl_ovrstry', 'fsg'):
                raw = getattr(self, name)
                if raw is not None:
                    value = self._grid_numeric(raw)
                    if name in ('ws', 'slope'):
                        value = mask.where(limited & ~self._cheney_mask,
                            grass_eqs.normalize_grass_input(value, name), value)
                    setattr(self, name, value)

    def _finish_grass_validation(self) -> None:
        if np.any(self.o1_mask):
            if self.gcf is None:
                raise ValueError('gcf is required for O1 surface models')
            self.gcf = grass_eqs.normalize_grass_input(self._grid_numeric(self.gcf), 'gcf')
        if not np.any(self.grass_mask):
            return
        for name in ('ws', 'wd'):
            if getattr(self, name) is None:
                raise ValueError(f'{name} is required for grass')
            setattr(self, name, self._grid_numeric(getattr(self, name)))
        terrain_inputs_used = self.model_terrain_effects_on_ffmc or self.model_terrain_effects_on_wind
        if (terrain_inputs_used
                and (self.slope is None or self.aspect is None)):
            raise ValueError('slope and aspect are required for terrain adjustment')
        for name in ('slope', 'aspect'):
            if getattr(self, name) is not None:
                setattr(self, name, self._grid_numeric(getattr(self, name)))
        if self._sfc_input is not None:
            raw = self._grid_numeric(self._sfc_input)
            value = mask.where(raw <= 0, 0., mask.minimum(raw, 100.))
            self.sfc = mask.where(self.grass_mask, value, self._grid_numeric(self.sfc))
        elif self.gfl is None and np.any(self.grass_mask & ~self._wheat_mask):
            raise ValueError('gfl is required for computed grass consumption')
        if np.any(self._wheat_mask):
            raw = self._grid_numeric(self.gfl)
            defaulted = self._wheat_mask & (mask.getmaskarray(raw) | (raw.data < 0))
            messages = []
            stands = np.broadcast_to(self._stand_codes, self.ref_array.shape)
            for stand, fuel in ((20, .53), (21, .39), (22, .32)):
                used = defaulted & (stands == stand)
                if np.any(used):
                    raw[used] = fuel
                    messages.append(f'stand {stand}: {np.count_nonzero(used)} cell(s) = {fuel:g} kg/m2')
            self.gfl = raw
            if messages:
                warnings.warn('Wheat consumed fuel defaults: ' + '; '.join(messages), UserWarning, stacklevel=3)
        if self.gfl is not None:
            raw = self._grid_numeric(self.gfl)
            self.gfl = mask.where(self.grass_mask,
                                  grass_eqs.normalize_grass_input(raw, 'gfl'), raw)

    def _stand_sros_warning(self):
        mismatch = (self.valid_fuel_mask & ~mask.getmaskarray(self.sros_model)
                    & ((self.grass_mask != (self.o1_mask | self._cheney_mask))
                       | (self._wheat_mask & ~self._cheney_mask)))
        if not np.any(mismatch):
            return None
        codes = np.broadcast_to(self._stand_codes, self.ref_array.shape)
        pairs, counts = np.unique(np.stack((codes[mismatch], self.sros_model.data[mismatch]), axis=1),
                                  axis=0, return_counts=True)
        return 'Using supplied SROS across stand classes: ' + '; '.join(
            f'stand {stand}/SROS {model}: {count} cell(s)' for (stand, model), count in zip(pairs, counts))

    def _verify_inputs(self):
        for name in ('model_terrain_effects_on_wind', 'model_terrain_effects_on_ffmc',
                     'process_ladder'):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f'{name} must be boolean data type')
        self._resolve_surface_models()
        if self.model_terrain_effects_on_wind and np.any(
                np.isin(self.sros_model.compressed(), [16, 17, 20])):
            raise ValueError('Selected surface ROS model has no terrain wind extension')
        self._prepare_cheney_inputs()
        self._prepare_grass_inputs()
        if not self._domain_policy_active:
            self._verify_forest_inputs()
            self._finish_grass_validation()
            return
        selection = self.valid_fuel_mask & ~self.grass_mask
        if not np.any(selection):
            for name in ('cfo_model', 'cros_model'):
                setattr(self, name, mask.masked_all(self.ref_array.shape, dtype=np.int8))
            self._finish_grass_validation()
            return
        component = copy(self)
        for name in inspect.signature(self.initialize).parameters:
            value = getattr(self, name)
            if isinstance(value, np.ndarray) and value.shape == selection.shape:
                setattr(component, name, value[selection].copy())
        component.ref_array = mask.zeros(np.count_nonzero(selection), dtype=float)
        component.ref_int_array = mask.zeros(component.ref_array.shape, dtype=np.int8)
        component._verify_forest_inputs()
        for name in ('cfo_model', 'sros_model', 'cros_model', 'ws', 'wd', 'cbd',
                     'cfl_ovrstry', 'slope', 'aspect', 'fsg', 'sfc'):
            value = getattr(component, name)
            if isinstance(value, np.ndarray):
                if name in ('cfo_model', 'cros_model'):
                    setattr(self, name, mask.masked_all(selection.shape, dtype=value.dtype))
                self._scatter_component_output(name, value, selection)
        self._finish_grass_validation()

    def _verify_forest_inputs(self):
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
        if np.any(mask_invalid & ~mask.getmaskarray(self.cfo_model)):
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

        # Normalize public labels before parameter lookup and equation dispatch.
        self.sros_model = conpyro_eqs.normalize_sros_model(self.sros_model)
        if self.model_terrain_effects_on_wind and np.any(
                np.isin(self.sros_model.compressed(), [16, 17, 20])):
            raise ValueError("Selected surface ROS model has no terrain wind extension")

        # Verify cros_model
        if not isinstance(self.cros_model, (int, np.ndarray)):
            raise TypeError('cros_model must be int or numpy ndarray data types')
        if isinstance(self.cros_model, np.ndarray):
            self.cros_model = mask.array(self.cros_model, mask=~np.isfinite(self.cros_model))
        else:
            self.cros_model = mask.array(np.full_like(self.ref_int_array, self.cros_model, dtype=np.int8),
                                         mask=~np.isfinite(self.ref_int_array))
        # Raise error for invalid model choices
        mask_invalid = ~mask.isin(self.cros_model, [1, 2, 3])
        if np.any(mask_invalid & ~mask.getmaskarray(self.cros_model)):
            raise Exception('Crown Fire Rate of Spread model choice is invalid. Should be 1, 2 and/or 3.')

        # Verify ws
        self.ws = validate_numeric(self.ws, 'ws', use_isfinite=True)
        # Mask negative values
        self.ws = mask.where(self.ws < 0, mask.masked, self.ws)

        # Verify wd
        self.wd = validate_numeric(self.wd, 'wd', use_isfinite=False)

        # Verify cbd
        self.cbd = validate_numeric(self.cbd, 'cbd', ref_array=self.ref_array)
        self.cbd = mask.masked_invalid(self.cbd)
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
        self.fsg = validate_numeric(self.fsg, 'fsg', use_isfinite=False)
        if self.sfc is not None:
            self.sfc = validate_numeric(self.sfc, 'sfc', use_isfinite=False)
            nonpositive = np.isfinite(self.sfc) & (self.sfc <= 0)
            self.sfc = mask.where(nonpositive, 0., mask.clip(self.sfc, 0.1, 6))

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
            cfo_model: int | np.ndarray | None = None,        # Defaults: FFMC 4, stand-adjusted 5
            sros_model: int | str | np.ndarray | None = None,  # Defaults: forest 12/13, grass 30, wheat 32–34
            cros_model: int | np.ndarray | None = None,       # Default: 1
            smooth_ros: bool,                               # ConPyro
            model_terrain_effects_on_wind: bool,            # ConPyro
            model_terrain_effects_on_ffmc: bool,            # ConPyro
            process_ladder: bool,                           # Ladder
            season: Union[int, str, np.ndarray, None],      # Moisture Content
            density: Union[int, str, np.ndarray, None],     # ConPyro, Moisture Content
            stand_type: Union[int, str, np.ndarray, None],  # ConPyro, Moisture Content
            cbd: float | np.ndarray | None,             # ConPyro
            cfl_ovrstry: float | np.ndarray | None,     # ConPyro, Ladder
            fsg: float | np.ndarray | None,             # ConPyro, Ladder
            ffl: float | np.ndarray | None,             # ConPyro, SFC
            wfl: float | np.ndarray | None,             # ConPyro, SFC
            gfl: float | np.ndarray | None,             # ConPyro, SFC
            ws: float | np.ndarray | None,              # ConPyro (if wind terrain-effect True)
            wd: float | np.ndarray | None,              # ConPyro (if wind terrain-effect True)
            slope: Optional[Union[int, float, np.ndarray]],   # ConPyro (if either terrain-effect True), Rothermel MC (CFIS Only)
            aspect: Optional[Union[int, float, np.ndarray]],  # ConPyro (if either terrain-effect True), Rothermel MC (CFIS Only)
            wx_date: int | str | None,       # Ladder (if fmc is None); missing raw season selects FFMC moisture
            ffmc: float | np.ndarray | None,            # Moisture Content, SFC, ConPyro (if ffmc terrain-effect True)
            dmc: float | np.ndarray | None,             # Moisture Content
            bui: float | np.ndarray | None,             # Moisture Content, SFC
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
            temp: Optional[Union[int, float, np.ndarray]] = None,   # Rothermel MC (CFIS only: cfo_model=10), Cheney AM60 moisture (SROS 32-34, wheat stands)
            rh: Optional[Union[int, float, np.ndarray]] = None,     # Rothermel MC (CFIS only: cfo_model=10), Cheney AM60 moisture (SROS 32-34, wheat stands)
            cc: Optional[Union[int, float, np.ndarray]] = None,     # Rothermel MC (CFIS only: cfo_model=10); missing raw density selects FFMC moisture
            site_elev: Optional[Union[int, float, np.ndarray]] = None,     # Rothermel MC (CFIS only: cfo_model=10)
            stn_elev: Optional[Union[int, float, np.ndarray]] = None,      # Rothermel MC (CFIS only: cfo_model=10)
            elevation: Optional[Union[int, float, np.ndarray]] = None,     # Ladder (if fmc is None), Rothermel MC (CFIS only: cfo_model=10)
            lat: Optional[Union[int, float, np.ndarray]] = None,    # Ladder (if fmc is None)
            long: Optional[Union[int, float, np.ndarray]] = None,   # Ladder (if fmc is None)
            d0: Optional[Union[int, float, np.ndarray]] = None,     # Ladder (if fmc is None, and wx_date is None)
            dj: Optional[Union[int, float, np.ndarray]] = None,     # Ladder (if fmc is None, and wx_date is None)
            sfc: Optional[Union[int, float, np.ndarray]] = None,    # ConPyro (overrides modelled SFC value if not None)
            suppress_messages: bool = False,    # ConPyro (whether to suppress processing messages)
            smoothing_wind_axis: Optional[int] = None,
            gcf: float | np.ndarray | None = None,
            cheney_mf_override: float | np.ndarray | None = None,  # Cheney (optional standing dead-fuel Mf %, overrides AM60 per cell)
    ) -> None:
        self._season_codes = self._density_codes = None
        self._forest_moisture_cache = False
        # Initialize parent classes
        MoistureContent.__init__(self)
        RothMC.__init__(self)
        SFC.__init__(self)
        LadderFuels.__init__(self)

        # Enable/disable ConPyro processing messages
        self.suppress_messages = suppress_messages
        self.smoothing_wind_axis = smoothing_wind_axis

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
        self._sfc_input = mask.array(sfc, copy=True) if sfc is not None else None
        self.gcf = gcf
        self.cheney_mf_override = cheney_mf_override
        if isinstance(self.cheney_mf_override, np.ndarray) and self.cheney_mf_override.ndim == 0:
            self.cheney_mf_override = (np.nan if mask.getmaskarray(self.cheney_mf_override).item()
                                       else self.cheney_mf_override.item())

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

        # Components interpret ndarray inputs as grids. A visible 0-d value is
        # a scalar; masked selectors retain their explicit missing semantics.
        for name in inspect.signature(self.initialize).parameters:
            if name in ('smooth_ros', 'suppress_messages', 'smoothing_wind_axis',
                        'model_terrain_effects_on_wind', 'model_terrain_effects_on_ffmc',
                        'process_ladder'):
                # Control truthiness/validation is distinct from numeric nodata.
                continue
            value = getattr(self, name, None)
            if isinstance(value, np.ndarray) and value.ndim == 0:
                if mask.getmaskarray(value).item():
                    if name not in ('cfo_model', 'sros_model', 'cros_model'):
                        setattr(self, name, np.nan)
                else:
                    setattr(self, name, value.item())

        self._normalize_stand_type()
        if np.any(np.isin(self._stand_codes, [20, 21, 22])) and isinstance(self.gfl, np.ndarray) and self.gfl.ndim == 0:
            # A masked scalar is a missing value, not a second raster shape.
            self.gfl = np.nan if mask.getmaskarray(self.gfl).item() else self.gfl.item()
        self._domain_policy_active = self._nonfuel_policy_active or bool(np.any(np.isin(self._stand_codes, [10, 20, 21, 22])))
        self._check_array()
        self._set_stand_domain()
        self._ffmc_base = self._grid_numeric(self.ffmc)
        self._verify_inputs()
        self._broadcast_scalar_inputs()
        self.forest_mask = self.valid_fuel_mask & ~self.grass_mask & ~mask.getmaskarray(self.sros_model)
        self._update_no_burn_mask()
        message = self._stand_sros_warning()
        if message:
            warnings.warn(message, UserWarning, stacklevel=2)
        counts = self.forest_model_default_counts
        if any(counts.values()):
            warnings.warn('Using forest model defaults: ' + '; '.join(
                f'{name}: {count} cell(s)' for name, count in counts.items() if count),
                UserWarning, stacklevel=2)
        fallback_count = np.count_nonzero(
            self._mc_ffmc_path & ~mask.getmaskarray(self.sros_model))
        if fallback_count:
            warnings.warn('Using FFMC moisture for missing raw DMC/season/density: '
                          f'{fallback_count} cell(s); '
                          'count includes only unmasked surface selectors; '
                          'date and canopy cover do not replace missing context, and '
                          'density-dependent acceleration remains missing without density.',
                          UserWarning, stacklevel=2)
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
            if model != 1:
                continue  # Wind-only models do not consume fitted parameters.
            mask_model = self.cros_model == model
            params = conpyro_eqs.CROS_PARAMS_DICT[int(model)]
            self.cros_param_b1[mask_model] = params[0]
            self.cros_param_b2[mask_model] = params[1]
            self.cros_param_b3[mask_model] = params[2]
            self.cros_param_b4[mask_model] = params[3]
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
        self.sros_param_d = np.full_like(self.ref_array, np.nan, dtype=np.float64)
        self.sros_param_e = np.full_like(self.ref_array, np.nan, dtype=np.float64)
        for model in mask.unique(self.sros_model[~self.sros_model.mask]):
            mask_model = self.sros_model == model
            if int(model) not in conpyro_eqs.SROS_PARAMS_DICT:
                continue  # Model 20 has no fitted parameters.
            params = conpyro_eqs.SROS_PARAMS_DICT[int(model)]
            self.sros_param_a[mask_model] = params[0]
            self.sros_param_b[mask_model] = params[1]
            self.sros_param_c[mask_model] = params[2]
            self.sros_param_d[mask_model] = params[3]
            self.sros_param_e[mask_model] = params[4]
        # Set flag to indicate SROS parameters have been initialized
        self.sros_params_initialized = True
        return

    def _use_forest_partition(self) -> bool:
        """Keep ordinary forest calls on the original full-grid fast path."""
        return self._domain_policy_active or bool(np.any(self.no_burn_mask))

    def _forest_stage_selection(self) -> np.ndarray:
        """Retain model-independent diagnostics at every baseline forest cell."""
        return self.valid_fuel_mask.copy()

    def _select_component_input(self, name: str, selection: np.ndarray) -> object:
        """Copy a component value, gathering grid arrays only for a subset."""
        value = getattr(self, name)
        if not isinstance(value, np.ndarray):
            return value
        if value.shape == selection.shape and not np.all(selection):
            return value[selection].copy()
        # Keep the original axes in the all-forest equivalence path.
        return value.copy()

    def _scatter_component_output(self, name: str, value: np.ndarray,
                                  selection: np.ndarray) -> None:
        """Restore component data and masks without flattening full-grid work."""
        if np.all(selection):
            setattr(self, name, value.copy())
            return
        current = getattr(self, name, None)
        if isinstance(current, np.ndarray) and current.shape == selection.shape:
            result = mask.array(current, dtype=np.result_type(current.dtype, value.dtype), copy=True)
        else:
            # Masked payloads can still be evaluated by NumPy ufuncs. Keep
            # numerical backing values safe instead of leaving them uninitialized.
            result = mask.array(np.zeros(selection.shape, dtype=value.dtype), mask=True)
        result[selection] = value
        setattr(self, name, result)

    def _run_forest_stage(self, method: str, *args,
                          selection: np.ndarray | None = None,
                          copy_inputs_back: bool = True) -> None:
        """Run an existing component against an isolated copy of its state."""
        if selection is None and not self._use_forest_partition():
            getattr(self, method)(*args)
            return
        # Component diagnostics can remain valid where SROS is masked. Until
        # stand-domain routing is introduced, preserve every baseline cell.
        if selection is None:
            selection = self._forest_stage_selection()
        if method != '_calculate_forest_wind':
            selection &= ~self.grass_mask
        if method in ('run_ladder_fuels', '_calculate_forest_cfo', '_calculate_forest_crown_ros',
                      '_calculate_forest_metrics'):
            selection &= ~self.no_burn_mask
        inputs, outputs, metadata = (
            set(fields.split()) for fields in self._FOREST_STAGE_CONTRACTS[method])
        full_grid = bool(np.all(selection))
        if not np.any(selection):
            return
        component = copy(self)
        for name, value in vars(self).items():
            if isinstance(value, np.ndarray):
                if name in inputs | outputs | {'ref_array', 'ref_int_array'}:
                    setattr(component, name, self._select_component_input(name, selection))
                else:
                    # Lookup/shared arrays must never be gathered merely because
                    # their dimensions happen to match a scenario grid.
                    setattr(component, name, value.copy())
            elif isinstance(value, (dict, list)):
                setattr(component, name, copy(value))
        stage_args = (component.cfo_model,) if method == 'run_sfc' else args
        getattr(component, method)(*stage_args)
        # Validation can expand scalar inputs into arrays. Keep those arrays
        # with the validation flags so cached runs retain consistent shapes.
        state_arrays = (outputs | inputs) - self._STAGE_NO_COPY_BACK
        if not copy_inputs_back:
            state_arrays -= inputs
        if full_grid:
            state_arrays |= {'ref_array', 'ref_int_array'}
        for name in state_arrays:
            value = getattr(component, name, None)
            if isinstance(value, np.ndarray):
                self._scatter_component_output(name, value, selection)
        for name in metadata:
            if hasattr(component, name):
                value = getattr(component, name)
                setattr(self, name, value)

    @staticmethod
    def _decode_context_labels(values, name, codes):
        """Resolve visible labels, including mixed Unicode, bytes and numeric objects."""
        if values.dtype.kind == 'O':
            label_kind = np.frompyfunc(
                lambda item: 1 if isinstance(item, str) else
                2 if isinstance(item, (bytes, np.bytes_)) else 0, 1, 1
            )(values).astype(np.int8)
        else:
            label_kind = np.full(values.shape, 2 if values.dtype.kind == 'S' else 1, dtype=np.int8)
        numeric = np.empty(values.shape, dtype=float)
        # Bytes and Unicode cannot be sorted together in an object array.
        for kind in (1, 2):
            for label in np.unique(values[label_kind == kind]):
                try:
                    decoded = label.decode('ascii') if kind == 2 else label
                    numeric[values == label] = codes[decoded]
                except (UnicodeDecodeError, KeyError) as error:
                    raise ValueError(f'Unknown {name} found, conversion failed.') from error
        numeric[label_kind == 0] = values[label_kind == 0].astype(float)
        return numeric

    def _context_fields(self):
        return (('season', self.season_code_dict_inv), ('density', self.density_code_dict_inv))

    def _classify_context_field(self, name, codes, forest):
        """Return native numeric codes and distinguish missing from rejected inputs."""
        raw = mask.atleast_1d(mask.asarray(getattr(self, name)))
        missing = self._raw_missing(raw, shape=raw.shape)
        if raw.shape == forest.shape:
            missing |= ~forest
        present = ~missing
        values = raw.data[present]
        if values.dtype.kind in 'OUS':
            values = self._decode_context_labels(values, name, codes)
        # Reject fractional and out-of-range numbers before narrowing to int8.
        valid = np.isin(values, tuple(codes.values()))
        data = np.zeros(raw.shape, dtype=float)
        data[present] = np.where(valid, values, 0)
        invalid = present & (data == 0)
        return mask.array(data, mask=missing | invalid), missing, invalid

    def _normalize_forest_context(self, forest: np.ndarray) -> tuple:
        """Classify current inputs without changing the caller's values or masks."""
        next_path = forest & self._raw_missing(self.dmc)
        rejected = np.zeros(forest.shape, dtype=bool)
        invalid_counts = {}
        native_codes = []
        grid_codes = []
        for name, codes in self._context_fields():
            native, missing, invalid = self._classify_context_field(name, codes, forest)
            invalid_grid = forest & invalid
            if np.any(invalid_grid):
                invalid_counts[name] = np.count_nonzero(invalid_grid)
            rejected |= invalid_grid
            next_path |= forest & missing
            native_codes.append(native)
            grid_codes.append(self._context_code_grid(native, forest))

        newly_missing = np.count_nonzero(
            next_path & ~self._mc_ffmc_path & ~mask.getmaskarray(self.sros_model))
        if newly_missing:
            warnings.warn('Using FFMC moisture for newly missing raw context: '
                          f'{newly_missing} cell(s); resolved model selectors are retained.',
                          UserWarning, stacklevel=3)
        if invalid_counts:
            warnings.warn('Invalid forest context codes masked: ' + '; '.join(
                f'{name}: {count} cell(s)' for name, count in invalid_counts.items()),
                UserWarning, stacklevel=3)

        # A native scalar keeps run_mc's scalar reference grid. On the FFMC
        # path numeric scalars historically enter the gathered stage as (1,).
        fallback = np.any(next_path)
        for index, original in enumerate((self.season, self.density)):
            native = native_codes[index]
            if (np.ndim(original) == 0 and not np.any(native.mask)
                    and (not fallback or isinstance(original, (str, bytes)))):
                native_codes[index] = int(native.item())
        self._season_codes, self._density_codes = grid_codes
        self._mc_ffmc_path = next_path
        self._invalid_context_codes = rejected
        return tuple(native_codes)

    @staticmethod
    def _context_code_grid(native, forest):
        return mask.array(np.broadcast_to(native.data, forest.shape),
                          mask=~forest | native.mask, dtype=np.int8, copy=True)

    @contextmanager
    def _validated_forest_stage(self):
        """Use the orchestrator's prepared codes only during its component call."""
        previous = self._using_forest_codes
        self._using_forest_codes = True
        try:
            yield
        finally:
            self._using_forest_codes = previous

    @contextmanager
    def _installed_context(self, season_work, density_work):
        """Give the moisture component independent inputs for this call."""
        season, density = self.season, self.density
        # run_mc can temporarily choose a scalar reference on a gridded scenario.
        ref_array, ref_int_array = self.ref_array, self.ref_int_array
        self.season, self.density = season_work, density_work
        try:
            with self._validated_forest_stage():
                yield
        finally:
            self.season, self.density = season, density
            self.ref_array, self.ref_int_array = ref_array, ref_int_array

    @wraps(MoistureContent.initialize_mc)
    def initialize_mc(self, *args, **kwargs):
        # Direct component initialization enables its date/canopy derivation.
        self._forest_moisture_cache = False
        self._season_codes = self._density_codes = None
        return super().initialize_mc(*args, **kwargs)

    def run_mc(self):
        if self.mc_inputs_verified and self._forest_moisture_cache and not self._using_forest_codes:
            # The forest pipeline restored raw labels, masks and rejected codes.
            # Validate current inputs for an independent cached component call.
            with self._installed_context(*self._current_moisture_codes()):
                return super().run_mc()
        return super().run_mc()

    def _current_moisture_codes(self):
        forest = self.valid_fuel_mask & ~self.grass_mask
        return tuple(self._classify_context_field(name, codes, forest)[0]
                     for name, codes in self._context_fields())

    def _mask_invalid_forest_context(self, forest: np.ndarray, ffmc_missing: np.ndarray) -> None:
        """Mask selected moisture while retaining independent diagnostics."""
        invalid = forest & self._invalid_context_codes
        self._invalid_moisture_context = invalid
        if np.any(forest & ffmc_missing):
            # run_mc can temporarily use a scalar reference grid. Compose on
            # the original forest grid rather than that component reference.
            value = mask.asarray(self.mc_ffmc)
            self.mc_ffmc = mask.array(np.broadcast_to(value.data, forest.shape),
                mask=np.broadcast_to(mask.getmaskarray(value), forest.shape)
                     | (forest & ffmc_missing), copy=True)
        if not np.any(invalid | (forest & ffmc_missing)):
            return
        selected_missing = invalid | (forest & ffmc_missing) | mask.getmaskarray(self.mc_sa)
        for name in ('mc_sa', 'use_adjusted_mc'):
            value = mask.asarray(getattr(self, name))
            if value.shape != forest.shape:
                value = mask.array(np.broadcast_to(value.data, forest.shape),
                    mask=np.broadcast_to(mask.getmaskarray(value), forest.shape), copy=True)
            setattr(self, name, mask.array(value, mask=mask.getmaskarray(value) | selected_missing))
        # Crown ROS evaluates the logarithm before applying the moisture mask.
        # Keep missing moisture payloads positive without changing their masks.
        self.mc_sa.data[mask.getmaskarray(self.mc_sa)] = 1.

    def _run_forest_moisture(self) -> None:
        forest = self.valid_fuel_mask & ~self.grass_mask
        if not np.any(forest):
            return
        self._forest_moisture_cache = True
        with self._installed_context(*self._normalize_forest_context(forest)):
            self._calculate_forest_moisture(forest)

    def _clip_forest_dmc(self, value, forest):
        """Clip forest DMC while preserving other cells and native shapes."""
        raw = mask.atleast_1d(mask.asarray(value, dtype=float))
        infinite = np.isinf(raw.data)
        outside = ((raw < 10.) | (raw > 200.)).filled(False) | infinite
        selected = forest & outside
        if not np.any(selected):
            return value
        # A shared scalar is consumed only by forest when all other
        # cells are nonfuel. Retain native shape and normal CFIS clips.
        if np.all(forest) or (raw.size == 1 and not np.any(self.grass_mask)):
            selected = outside
        # The moisture equations consume the clipped backing data even where
        # DMC validation masks infinity. Match the component's first run.
        clipped = mask.array(mask.clip(raw, 10., 200.), mask=infinite)
        return mask.where(selected, clipped, raw)

    def _calculate_forest_moisture(self, forest: np.ndarray) -> None:
        """Calculate moisture after current context has been normalized."""
        fallback = bool(np.any(self._mc_ffmc_path))
        ffmc_missing = mask.getmaskarray(self._grid_numeric(self.ffmc))
        if not fallback:
            if self.mc_inputs_verified:
                # DMC can change after the component has cached its validation.
                self.dmc = self._clip_forest_dmc(self.dmc, forest)
            self._run_forest_stage('run_mc')
            self._mask_invalid_forest_context(forest, ffmc_missing)
            return
        complete = forest & ~self._mc_ffmc_path
        # Missing context chooses R's FFMC scenario. Never synthesize stand
        # covariates merely to satisfy the standalone adjusted-MC component.
        for name in ('ffmc', 'dmc'):
            raw = mask.atleast_1d(mask.asarray(getattr(self, name)))
            missing = self._raw_missing(raw, shape=raw.shape)
            value = mask.array(np.where(missing, 0., raw.data).astype(float), mask=missing)
            value = validate_numeric(value, name)
            if name == 'dmc':
                value = self._clip_forest_dmc(value, forest)
            elif not self.mc_inputs_verified:
                # Retain the component's first-run FFMC clipping and shape.
                if np.all(forest) or (value.size == 1 and not np.any(self.grass_mask)):
                    value = mask.clip(value, 80., 97.)
                elif value.shape == forest.shape:
                    value = mask.where(forest, mask.clip(value, 80., 97.), value)
                elif value.size == 1 and np.any((value < 80.) | (value > 97.)):
                    grid = self._grid_numeric(value)
                    value = mask.where(forest, mask.clip(grid, 80., 97.), grid)
            setattr(self, name, value)
        self._run_forest_stage('run_mc', selection=complete, copy_inputs_back=False)
        # Enforce fallback bounds on the consumed grid regardless of native
        # input layout, including shared scalars on forest/nonfuel grids.
        ffmc = mask.clip(self._grid_numeric(self.ffmc), 80., 97.)
        selected_mc = mask.array(
            moisture_eqs.calc_mc_ffmc(np.zeros(self.ref_array.shape), ffmc.filled(80.)),
            mask=mask.getmaskarray(ffmc) | ~forest)
        self.mc_ffmc = mask.where(self._mc_ffmc_path, selected_mc,
                                  self._grid_numeric(self.mc_ffmc))
        self.mc_sa = mask.where(self._mc_ffmc_path, selected_mc,
                                self._grid_numeric(self.mc_sa))
        dmc = mask.clip(self._grid_numeric(self.dmc), 10., 200.)
        self.mc_dmc = mask.array(
            moisture_eqs.calc_mc_dmc(np.zeros(self.ref_array.shape), dmc.filled(10.)),
            mask=mask.getmaskarray(dmc) | ~forest)
        adjusted = getattr(self, 'use_adjusted_mc', None)
        if adjusted is None:
            adjusted = mask.masked_all(self.ref_array.shape, dtype=bool)
        self.use_adjusted_mc = mask.where(self._mc_ffmc_path, False, adjusted)
        self._mask_invalid_forest_context(forest, ffmc_missing)
        # The full-grid native inputs above are now normalized too. Repeated
        # terrain runs retain the ordinary component's validation/clip timing.
        self.mc_inputs_verified = True

    def _run_forest_sfc(self) -> None:
        # The copied state includes cfo_model, also read by SFC.run_sfc.
        self._run_forest_stage('run_sfc', self.cfo_model)

    def _run_forest_ladder(self) -> None:
        self._run_forest_stage('run_ladder_fuels')

    def _run_forest_roth(self) -> None:
        self._run_forest_stage('get_roth_mc')

    def _process_forest_cfo(self) -> None:
        self._run_forest_stage('_calculate_forest_cfo')

    def _process_forest_crown_ros(self) -> None:
        # Mixed-grid composition and later CFIS moisture can replace the array.
        # NumPy evaluates masked backing values in the crown logarithm too.
        if mask.is_masked(self.mc_sa):
            self.mc_sa = mask.array(self.mc_sa, copy=True)
            self.mc_sa.data[mask.getmaskarray(self.mc_sa)] = 1.
        self._run_forest_stage('_calculate_forest_crown_ros')

    def process_cfo(self) -> None:
        """
        Function to process Crown Fire Occurrence (CFO) calculations.
        :return:
        """
        self._process_wind()
        self._process_forest_cfo()

    def _process_wind(self) -> None:
        """Calculate shared wind and indices on the original scenario grid."""
        self._run_forest_stage('_calculate_forest_wind')

    def _calculate_forest_wind(self) -> None:
        self._log('[ConPyro] process_cfo: calculating FFMC function...')
        self.fF = conpyro_eqs.calc_ff(self.mc_sa)

        if self.model_terrain_effects_on_wind and not np.all(self._cheney_mask):
            # Models 12/18c use standard ISI for surface slope inversion.
            terrain_ff = mask.where(np.isin(self.sros_model, [12, 18, 30, 31]),
                                    conpyro_eqs.calc_ff(self.sros_mc_ffmc), self.fF)
            self._log('\t[ConPyro] process_cfo: applying slope effects (invert wind/aspect, slope factor, ISZ/ISF, WSV/RAZ)...')
            self._log('\t[ConPyro] process_cfo: inverting wind direction and slope aspect...')
            wind_azimuth, upslope_azimuth = conpyro_eqs.calc_inverted_wind_aspect(self.wd, self.aspect)

            self._log('\t[ConPyro] process_cfo: calculating slope factor...')
            self.sf = conpyro_eqs.calc_sf(self.slope)

            self._log('\t[ConPyro] process_cfo: calculating ISZ (no wind/slope ISI)...')
            self.isz = conpyro_eqs.calc_isz(terrain_ff)

            self._log('\t[ConPyro] process_cfo: calculating ISF (slope/wind adjusted ISI)...')
            if not self.sros_params_initialized:
                self.get_sros_params()
            terrain_models = mask.array(self.sros_model,
                mask=mask.getmaskarray(self.sros_model) | self._cheney_mask)
            self.isf = conpyro_eqs.calc_isf(self.isz, self.sf, self.sfc, terrain_models,
                                            self.sros_param_a, self.sros_param_b, self.sros_param_c,
                                            self.sros_param_d, self.sros_param_e,
                                            stand_type=self.stand_type)

            self._log('\t[ConPyro] process_cfo: calculating effective wind speed and direction (WSV/RAZ)...')
            self.wsv, self.raz = conpyro_eqs.calc_wsv_raz(
                self.ws, wind_azimuth, self.isf, terrain_ff, upslope_azimuth)
            # Avoid inverse roundoff moving flat cells across the 40 km/h branch.
            flat_valid = (
                (self.sf == 1)
                & ~mask.getmaskarray(self.wsv)
                & ~mask.getmaskarray(self.raz)
            )
            self.wsv = mask.where(flat_valid, self.ws, self.wsv)
            self.raz = mask.where(flat_valid, wind_azimuth, self.raz)
        else:
            self._log('\t[ConPyro] process_cfo: slope effects disabled; using input wind speed and direction.')
            self.wsv = self.ws
            self.raz = (self.wd + 180) % 360

        self._apply_cheney_terrain_wind()
        self._log('\t[ConPyro] process_cfo: calculating wind and backing fire indices...')
        self.fW = conpyro_eqs.calc_fw(self.wsv)
        self.isi = conpyro_eqs.calc_isi(self.fW, self.fF)
        self.bfw = conpyro_eqs.calc_bfw(self.wsv)
        self.bisi = conpyro_eqs.calc_bisi(self.bfw, self.fF)

    def _apply_cheney_terrain_wind(self) -> None:
        """Replace only Cheney wind with the selected local FBP reference."""
        selected = self._cheney_mask
        if not self.model_terrain_effects_on_wind or not np.any(selected):
            return
        speed, bearing = cheney_terrain_eqs.calc_cheney_wsv_raz(
            self._grid_numeric(self.ws)[selected], self._grid_numeric(self.wd)[selected],
            self._grid_numeric(self.slope)[selected], self._grid_numeric(self.aspect)[selected],
            self.cheney_mf[selected], self._grid_numeric(self.gcf)[selected],
            self.sros_model.data[selected])
        # The no-terrain branch can alias ws; never scatter into raw inputs.
        self.wsv = mask.array(self.wsv, copy=True)
        self.raz = mask.array(self.raz, copy=True)
        self.wsv[selected] = mask.masked_invalid(speed)
        self.raz[selected] = mask.masked_invalid(bearing)

    def _calculate_forest_cfo(self) -> None:
        self._log('\t[ConPyro] process_cfo: calculating crown fire occurrence probability...')
        if not self.cfo_params_initialized:
            self.get_cfo_params()
        self.logit = conpyro_eqs.calc_logit(self.wsv, self.fsg, self.mc_sa, self.sfc,
                                            self.cfo_model, self.cfo_param_b0, self.cfo_param_b1,
                                            self.cfo_param_b2, self.cfo_param_b3, self.cfo_param_b4,
                                            self.cfo_param_b5)
        self.cfo_prob = conpyro_eqs.calc_cfo_prob(self.logit)
        # Owner decision: canopy-free cells cannot sustain crown fire.
        self.cfo_prob = mask.where(self.cbd == 0, 0.0, self.cfo_prob)
        self._log('\t[ConPyro] process_cfo: complete.')
        return

    def process_intensity(self) -> None:
        self.sfi = conpyro_eqs.calc_sfi(self.hros, self.sfc)
        self.cfi = conpyro_eqs.calc_cfi(self.hros, self.cfc)
        self.hfi = conpyro_eqs.calc_hfi(self.hros, self.tfc)
        if np.any(self._cheney_mask):
            heat = mask.masked_invalid(cheney_eqs.calc_cheney_heat_yield(self.cheney_mf))
            self.sfi = mask.where(self._cheney_mask,
                                 conpyro_eqs.calc_sfi(self.hros, self.sfc, heat_yield=heat), self.sfi)
            self.hfi = mask.where(self._cheney_mask,
                                 conpyro_eqs.calc_hfi(self.hros, self.tfc, sfc=self.sfc,
                                                      cfc=self.cfc, heat_yield=heat), self.hfi)
        return

    def process_fire_metrics(self) -> None:
        if self._using_forest_codes:
            density = self._density_codes
        else:
            selected = self.valid_fuel_mask & ~self.grass_mask & ~self.no_burn_mask
            if not np.any(selected):
                self._apply_nonfuel_outputs()
                return
            native, _, _ = self._classify_context_field('density', self.density_code_dict_inv, selected)
            density = self._context_code_grid(native, selected)
        # Metrics consume their inputs without normalizing them. Copying an
        # excluded scalar input back would fabricate nodata at zero-SFC cells.
        self._metrics_density = density
        try:
            self._run_forest_stage('_calculate_forest_metrics', copy_inputs_back=False)
        finally:
            del self._metrics_density
        self._apply_nonfuel_outputs()

    def _calculate_forest_metrics(self) -> None:
        # Calculate fire type and mask invalid areas
        self.fire_type = conpyro_eqs.calc_fire_type(self.cfo_prob, self.cac)
        self.fire_type = mask.array(self.fire_type,
            mask=mask.getmaskarray(self.fire_type) | mask.getmaskarray(self.hros)
                 | mask.getmaskarray(self.cfo_prob) | mask.getmaskarray(self.sros_model)
                 | mask.getmaskarray(self.cros_model) | mask.getmaskarray(self.cfo_model))
        # The forest-stage adapter selects recognized forest stands. Full-grid
        # grass/non-fuel fire types are composed by _apply_nonfuel_outputs.
        self.fire_type = self.fire_type.astype(np.int8)

        # Calculate crown fraction burned
        self.cfb = conpyro_eqs.calc_cfb(self.hros, self.cros_a)
        self.cfb = mask.where(self.cbd == 0, 0., self.cfb)

        # Calculate acceleration parameter
        self.accel_param = conpyro_eqs.calc_accel_param(self.cfb, self._metrics_density)
        self.accel_param = mask.array(self.accel_param, mask=mask.getmaskarray(self._metrics_density))

        # Calculate canopy fuel load and consumption
        self.cfl = conpyro_eqs.calc_cfl(self.cfl_ovrstry)
        self.cfc = conpyro_eqs.calc_cfc(self.cfl, self.cfb)
        self.cfc = mask.where(self.cbd == 0, 0., self.cfc)

        # Calculate total fuel consumption
        self.tfc = conpyro_eqs.calc_tfc(self.sfc, self.cfc)
        return

    def process_ladder_fuels(self) -> None:
        if self.process_ladder:
            self._run_forest_ladder()
        return

    def process_roth_mc(self) -> None:
        cfis_mask = mask.filled(self.cfo_model == 10, False) & ~self.grass_mask
        if np.any(cfis_mask):
            self._run_forest_roth()
            self.mc_sa[cfis_mask] = self.mc_roth[cfis_mask]
        return

    def process_mc_sa(self) -> None:
        self._season_codes = self._density_codes = None
        if np.any(self.grass_mask) or np.any(self.o1_mask):
            self._process_surface_moisture()
            return
        if self.model_terrain_effects_on_ffmc:
            self.ffmc = ffmc_adj_eqs.adjust_ffmc_for_terrain(self.ffmc, self.slope, self.aspect)
        self._run_forest_moisture()
        # Component calculations may use a scalar grid; retain the scenario grid.
        for name in ('mc_ffmc', 'mc_dmc', 'mc_sa'):
            value = mask.asarray(getattr(self, name))
            setattr(self, name, mask.array(
                np.broadcast_to(value.data, self.ref_array.shape),
                mask=np.broadcast_to(mask.getmaskarray(value), self.ref_array.shape)
                     | mask.getmaskarray(self.ref_array),
                copy=True))  # broadcast_to is read-only; CFIS assigns into mc_sa in place
        self.sros_mc_ffmc = mask.array(self.mc_ffmc, copy=True)
        return

    def _adjust_surface_ffmc(self, value):
        if not self.model_terrain_effects_on_ffmc:
            return mask.array(value, copy=True)
        slope = self._grid_numeric(self.slope)
        aspect = self._grid_numeric(self.aspect)
        adjusted = ffmc_adj_eqs.adjust_ffmc_for_terrain(
            value.filled(80.), slope.filled(0.), aspect.filled(0.))
        return mask.array(adjusted, mask=mask.getmaskarray(value)
                          | mask.getmaskarray(slope) | mask.getmaskarray(aspect))

    def _process_surface_moisture(self):
        adjusted = self._adjust_surface_ffmc(self._ffmc_base)
        self.ffmc = mask.where(self.grass_mask, adjusted, mask.clip(adjusted, 80., 97.))
        if np.any(self.valid_fuel_mask & ~self.grass_mask):
            self._run_forest_moisture()
        for name in ('mc_ffmc', 'mc_dmc', 'mc_sa'):
            setattr(self, name, self._grid_numeric(getattr(self, name)))
        o1_ffmc = self._adjust_surface_ffmc(
            grass_eqs.normalize_grass_input(self._ffmc_base, 'ffmc'))
        o1_mc = grass_eqs.calc_grass_mc_ffmc(o1_ffmc)
        legacy_ffmc = mask.clip(adjusted, 80., 97.)
        legacy_mc = 147.2 * (101. - legacy_ffmc) / (59.5 + legacy_ffmc)
        grass_mc = mask.where(self.o1_mask, o1_mc, legacy_mc)
        self.mc_ffmc = mask.where(self.grass_mask, grass_mc, self.mc_ffmc)
        self.mc_sa = mask.where(self.grass_mask, grass_mc, self.mc_sa)
        previous = getattr(self, 'use_adjusted_mc', None)
        if previous is None:
            previous = mask.masked_all(self.ref_array.shape, dtype=bool)
        self.use_adjusted_mc = mask.where(self.grass_mask, False, previous)
        self.ffmc = mask.where(self.grass_mask,
                               mask.where(self.o1_mask, o1_ffmc, legacy_ffmc),
                               self._grid_numeric(self.ffmc))
        self.sros_mc_ffmc = mask.where(self.o1_mask, o1_mc, self.mc_ffmc)

    def process_ros(self) -> None:
        # Get SROS parameters
        if not self.sros_params_initialized:
            self.get_sros_params()

        # Paper models 12/18c use standard ISI; other models retain adjusted ISI.
        standard_isi = np.isin(self.sros_model, [12, 18, 30, 31])
        surface_ff = mask.where(standard_isi, conpyro_eqs.calc_ff(self.sros_mc_ffmc), self.fF)
        self.sros_isi = conpyro_eqs.calc_isi(self.fW, surface_ff)
        self.sros_bisi = conpyro_eqs.calc_bisi(self.bfw, surface_ff)
        wind_only = self.grass_mask & np.isin(self.sros_model, [20, 32, 33, 34])
        self.sros_isi = mask.where(wind_only, 0., self.sros_isi)
        self.sros_bisi = mask.where(wind_only, 0., self.sros_bisi)
        surface_sfc = mask.where(self.grass_mask & ~np.isin(self.sros_model, [4, 9]),
                                 0., self.sfc)

        # Calculate surface fire rate of spread and mask invalid areas
        self.sros = conpyro_eqs.calc_sros(self.sros_isi, surface_sfc, self.sros_model,
                                          self.sros_param_a, self.sros_param_b, self.sros_param_c,
                                          self.sros_param_d, self.sros_param_e,
                                          wsv=self.wsv, stand_type=self.stand_type,
                                          mc_sa=self.mc_sa, mc_ffmc=self.mc_ffmc, gcf=self.gcf,
                                          _cheney_mf=self.cheney_mf)
        # Stand validity was resolved before selector dispatch. Consumed input
        # masks remain here; non-fuel zeros are composed at the stage barrier.

        self._process_forest_crown_ros()
        self._apply_nonfuel_outputs()

        # Calculate head fire rate of spread
        if self.smooth_ros:
            # Apply smoothing if requested
            smoothing = (self.sros, self.cros_p, self.cros_a, self.cfo_prob, self.cac)
            excluded = self.grass_mask | self.no_burn_mask
            if np.any(excluded):
                smoothing = tuple(mask.array(value,
                    mask=mask.getmaskarray(value) | excluded, copy=False)
                    for value in smoothing)
            self.hros = conpyro_eqs.calc_ros_smooth(
                *smoothing,
                wind_axis=self.smoothing_wind_axis)
        else:
            self.hros = conpyro_eqs.calc_hros(self.sros, self.cros, self.cfo_prob)

        # Canopy-free cells use surface spread, including when smoothing is enabled.
        self.hros = mask.where(self.cbd == 0, self.sros, self.hros)

        # Calculate backing fire rate of spread and mask invalid areas
        self.bros = conpyro_eqs.calc_bros(self.sros_bisi, surface_sfc, self.sros_model,
                                          self.sros_param_a, self.sros_param_b, self.sros_param_c,
                                          self.sros_param_d, self.sros_param_e,
                                          wsv=self.wsv, surface_ros=self.sros,
                                          stand_type=self.stand_type, gcf=self.gcf)
        self._apply_nonfuel_outputs()
        return

    def _calculate_forest_crown_ros(self) -> None:
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

        # Calculate crown fire rate of spread and mask invalid areas
        self.cros = conpyro_eqs.calc_cros(self.cros_a, self.cros_p, self.cac)

    def process_sfc(self) -> None:
        if self.sfc is None:
            ref_array, ref_int_array = self.ref_array, self.ref_int_array
            self._run_forest_sfc()
            value = mask.asarray(self.sfc)
            self.sfc = mask.array(
                np.broadcast_to(value.data, ref_array.shape),
                mask=np.broadcast_to(mask.getmaskarray(value), ref_array.shape)
                     | mask.getmaskarray(ref_array),
                copy=True)
            self.ref_array, self.ref_int_array = ref_array, ref_int_array
        if np.any(self.grass_mask) and self._sfc_input is None:
            self.sfc = mask.where(self.grass_mask, self.gfl, self._grid_numeric(self.sfc))
        return

    def return_params(self, out_request: list) -> list:
        """
        Function to return requested conpyro module parameters.

        Masked values in integer arrays are filled with -128; masked values in
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
                if val.dtype.kind == 'b' and np.any(mask.getmaskarray(val)):
                    val = val.astype(float)
                val = _safe_int(val)
                return val.filled(_fill_value(val))
            if val is not None:
                arr = _safe_int(np.ma.masked_array(val))
                return arr.filled(_fill_value(arr))
            return np.nan

        if self.return_array:
            return [_filled(getattr(self, var, np.nan)) for var in out_request]
        else:
            return [np.asarray(_filled(getattr(self, var, np.nan))).item()
                    for var in out_request]

    def _update_no_burn_mask(self) -> None:
        self.no_burn_mask = self.nonfuel_mask.copy()
        if self.sfc is not None:
            value = mask.asarray(self.sfc)
            zero = (np.isfinite(value.data) & (value.data <= 0)
                    & ~mask.getmaskarray(value))
            self.no_burn_mask |= np.broadcast_to(zero, self.ref_array.shape)

    def _apply_nonfuel_outputs(self) -> None:
        """Known non-fuel/no consumption is zero, not missing fire behavior."""
        if not np.any(self.no_burn_mask) and not np.any(self.grass_mask):
            return
        for name in ('sros', 'hros', 'bros', 'sfc', 'tfc', 'cfo_prob', 'cros_a',
                     'cros_p', 'cros', 'cac', 'cfb', 'cfl', 'cfc', 'sfi', 'cfi', 'hfi'):
            value = getattr(self, name, None)
            if value is None:
                value = mask.masked_all(self.ref_array.shape, dtype=float)
            setattr(self, name, mask.where(self.no_burn_mask, 0., value))
        value = self.fire_type
        if value is None:
            value = mask.masked_all(self.ref_array.shape, dtype=np.int8)
        self.fire_type = mask.where(self.no_burn_mask, 0, value).astype(np.int8)
        if np.any(self.grass_mask):
            for name in ('cfo_prob', 'cros_a', 'cros_p', 'cros', 'cac', 'cfb', 'cfl', 'cfc', 'cfi'):
                setattr(self, name, mask.where(self.grass_mask, 0., getattr(self, name)))
            self.hros = mask.where(self.grass_mask & ~self.no_burn_mask, self.sros, self.hros)
            self.tfc = mask.where(self.grass_mask, self.sfc, self.tfc)
            self.fire_type = mask.where(self.grass_mask & ~self.no_burn_mask, 1, self.fire_type).astype(np.int8)
            current_accel = self.accel_param
            if current_accel is None:
                current_accel = mask.masked_all(self.ref_array.shape)
            self.accel_param = mask.where(self.grass_mask, .115, current_accel)
            for name in ('logit', 'r0'):
                value = self._grid_numeric(getattr(self, name))
                setattr(self, name, mask.array(value.data,
                    mask=mask.getmaskarray(value) | self.grass_mask))
        for name in ('accel_param', 'wsv', 'raz', 'fF', 'fW', 'bfw', 'isi', 'bisi',
                     'sros_isi', 'sros_bisi', 'sros_mc_ffmc', 'sf', 'isz', 'isf', 'mc_ffmc', 'mc_dmc',
                     'mc_sa', 'mc_roth', 'use_adjusted_mc', 'logit', 'r0',
                     'fsg_live_ladder', 'fsg_dead_ladder', 'sfc_live_ladder',
                     'sfc_dead_ladder', 'latn', 'nd'):
            value = getattr(self, name, None)
            if value is None:
                value = mask.masked_all(self.ref_array.shape, dtype=float)
                setattr(self, name, value)
            if self._nonfuel_policy_active:
                value = mask.asarray(value)
                setattr(self, name, mask.array(
                    np.broadcast_to(value.data, self.ref_array.shape),
                    mask=np.broadcast_to(mask.getmaskarray(value), self.ref_array.shape)
                         | self.nonfuel_mask, copy=True))

    def run_conpyro(self) -> None:
        self._season_codes = self._density_codes = None
        # Weather/override fields may be updated between runs, including in place.
        # Each public call validates once, then shares Mf across head/back/heat.
        if np.any(self._cheney_mask):
            self._prepare_cheney_inputs()
        if not np.any(self.valid_fuel_mask):
            self._apply_nonfuel_outputs()
            return
        self._log('[ConPyro] Starting run_conpyro...')
        self._log('[ConPyro] Step 1/8: process_mc_sa')
        self.process_mc_sa()
        self._log('[ConPyro] Step 2/8: process_roth_mc')
        self.process_roth_mc()
        self._log('[ConPyro] Step 3/8: process_sfc')
        self.process_sfc()
        self._update_no_burn_mask()
        if np.all(self.no_burn_mask):
            # These are still valid fuel stands with observable weather, even
            # though there is no consumption and no crown/ladder work to run.
            self._process_wind()
            self._apply_nonfuel_outputs()
            return
        self._log('[ConPyro] Step 4/8: process_ladder_fuels')
        self.process_ladder_fuels()
        self._log('[ConPyro] Step 5/8: process_cfo')
        self.process_cfo()
        self._apply_nonfuel_outputs()
        self._log('[ConPyro] Step 6/8: process_ros')
        self.process_ros()
        self._apply_nonfuel_outputs()
        self._log('[ConPyro] Step 7/8: process_fire_metrics')
        with self._validated_forest_stage():
            self.process_fire_metrics()
        self._log('[ConPyro] Step 8/8: process_intensity')
        self.process_intensity()
        self._apply_nonfuel_outputs()
        self._log('[ConPyro] run_conpyro complete.')
        return
