# -*- coding: utf-8 -*-
"""
Moisture Content Calculation Equations

Created on Thu Oct 16, 11:45:00 2025

@author: Gregory A. Greene
"""
__author__ = ['Gregory A. Greene']

from typing import Union, Dict
import numpy as np
from numpy import ma as mask


def _ensure_masked_array(data: Union[int, float, np.ndarray]) -> np.ndarray:
    """
    Ensure input data is a masked array, preserving existing masks.

    If input is already a masked array, returns it unchanged (preserving all existing masks).
    If input is a regular array or scalar, converts to masked array with NaN/inf values masked.

    :param data: Input data (scalar, regular array, or masked array)
    :return: Masked array - original if already masked, or newly created with invalid values masked
    """
    if isinstance(data, (int, float)):
        return mask.array([data], mask=~np.isfinite([data]))
    elif isinstance(data, mask.MaskedArray):
        # Already masked - return as-is, preserving all existing masks
        return data
    else:
        # Regular array - convert to masked array with invalid values masked
        data_arr = np.asarray(data)
        return mask.array(data_arr, mask=~np.isfinite(data_arr))


def calc_mc_ffmc(
    ref_array: np.ndarray,
    ffmc: Union[int, float, np.ndarray],
) -> Union[int, float, np.ndarray]:
    """
    Calculate moisture content derived from Fine Fuel Moisture Code (FFMC).

    Converts FFMC values to moisture content (MC) using the empirical relationship
    from the Canadian Forest Fire Weather Index System.

    :param ref_array: Reference array for output shape consistency (must be same shape as ffmc or broadcastable)
    :param ffmc: CFFWIS Fine Fuel Moisture Code (typically 0-101.3)
    :return: Moisture content derived from FFMC (%)
    :raises TypeError: If inputs are not numeric types
    :raises ValueError: If ref_array shape incompatible with ffmc
    """
    # Validate ffmc type
    if not isinstance(ffmc, (int, float, np.ndarray)):
        raise TypeError(f"ffmc must be numeric or array, got {type(ffmc)}")

    # Convert to arrays
    ffmc_arr = np.atleast_1d(np.asarray(ffmc, dtype=np.float64))
    ref_array = np.atleast_1d(np.asarray(ref_array))

    # Validate shapes are compatible
    try:
        np.broadcast(ffmc_arr, ref_array)
    except ValueError as e:
        raise ValueError(
            f"ref_array shape {ref_array.shape} incompatible with ffmc shape {ffmc_arr.shape}"
        ) from e

    # Initialize mc_ffmc array with shape of ref_array
    mc_ffmc = np.zeros_like(ref_array, dtype=np.float64)

    # Calculate moisture content from FFMC
    # 147.27723 * (101 - ffmc) / (59.5 + ffmc)
    mc_ffmc += 147.27723 * (101.0 - ffmc_arr) / (59.5 + ffmc_arr)
    return mc_ffmc


def calc_mc_dmc(
    ref_array: np.ndarray,
    dmc: Union[int, float, np.ndarray],
) -> Union[int, float, np.ndarray]:
    """
    Calculate moisture content derived from Drought Moisture Code (DMC).

    Converts DMC values to moisture content (MC) using the empirical relationship
    from the Canadian Forest Fire Weather Index System.

    :param ref_array: Reference array for output shape consistency (must be same shape as dmc or broadcastable)
    :param dmc: CFFWIS Drought Moisture Code (typically 0-500+)
    :return: Moisture content derived from DMC (%)
    :raises TypeError: If inputs are not numeric types
    :raises ValueError: If ref_array shape incompatible with dmc
    """
    # Validate dmc type
    if not isinstance(dmc, (int, float, np.ndarray)):
        raise TypeError(f"dmc must be numeric or array, got {type(dmc)}")

    # Convert to arrays
    dmc_arr = np.atleast_1d(np.asarray(dmc, dtype=np.float64))
    ref_array = np.atleast_1d(np.asarray(ref_array))

    # Validate shapes are compatible
    try:
        np.broadcast(dmc_arr, ref_array)
    except ValueError as e:
        raise ValueError(
            f"ref_array shape {ref_array.shape} incompatible with dmc shape {dmc_arr.shape}"
        ) from e

    # Initialize mc_dmc array with shape of ref_array
    mc_dmc = np.zeros_like(ref_array, dtype=np.float64)

    # Calculate moisture content from DMC
    # 20 + exp(-(dmc - 244.72) / 43.43)
    mc_dmc += 20.0 + np.exp(-(dmc_arr - 244.72) / 43.43)
    return mc_dmc


def calc_mc_sa(
    ref_array: np.ndarray,
    season: Union[int, np.ndarray],
    density: Union[int, np.ndarray],
    stand_type: Union[int, np.ndarray],
    ffmc: Union[int, float, np.ndarray],
    mc_ffmc: Union[int, float, np.ndarray],
    mc_dmc: Union[int, float, np.ndarray],
    use_adjusted_mc: Union[bool, np.ndarray],
    mc_sa_coeff_a: np.ndarray,
    mc_sa_coeff_b: np.ndarray,
    model_mcsa: str = 'corrected',
) -> Union[int, float, np.ndarray]:
    """
    Calculate Stand-Adjusted Moisture Content (MCSA) from FFMC and DMC.

    Estimates stand-adjusted moisture content based on season, stand density, stand type,
    and FFMC/DMC values using Wotton and Beverly (2007) coefficients. Handles transitional
    season (Sp-Su) by averaging spring and summer coefficients.

    :param ref_array: Reference array for output shape consistency
    :param season: Season code (1-4: Spring, Transitional, Summer, Fall)
    :param density: Stand density class (1-3: Low, Moderate, High)
    :param stand_type: Stand type code (1-5: Deciduous, Douglas-fir, Mixedwood, Pine, Spruce)
    :param ffmc: CFFWIS Fine Fuel Moisture Code
    :param mc_ffmc: Moisture content derived from FFMC (%)
    :param mc_dmc: Moisture content derived from DMC (%)
    :param use_adjusted_mc: Boolean mask indicating which cells should use adjusted MC
    :param mc_sa_coeff_a: Coefficient 'a' lookup table for Wotton and Beverly (2007) model
                          Shape must be (5, 4, 6) for [season, density, stand_type]
    :param mc_sa_coeff_b: Coefficient 'b' lookup table for Wotton and Beverly (2007) model
                          Shape must be (5, 4, 6) for [season, density, stand_type]
    :param model_mcsa: Moisture content model variant ('corrected' or 'original')
    :return: Stand-Adjusted Moisture Content (%)
    :raises TypeError: If inputs are not proper types
    :raises ValueError: If coefficient arrays have wrong shape or season/density/stand_type values invalid
    """
    def _broadcast_masked_input(data, dtype):
        arr = mask.array(data, copy=False)
        data_vals = np.asarray(arr.data, dtype=dtype)
        data_mask = np.asarray(mask.getmaskarray(arr), dtype=bool)

        try:
            data_vals = np.array(np.broadcast_to(data_vals, ref_array.shape), copy=True)
            data_mask = np.array(np.broadcast_to(data_mask, ref_array.shape), copy=False)
        except ValueError as e:
            raise ValueError(
                f"Input with shape {np.shape(data)} is incompatible with ref_array shape {ref_array.shape}"
            ) from e

        return data_vals, data_mask

    # Validate coefficient arrays
    if not isinstance(mc_sa_coeff_a, np.ndarray) or not isinstance(mc_sa_coeff_b, np.ndarray):
        raise TypeError("mc_sa_coeff_a and mc_sa_coeff_b must be numpy arrays")

    expected_shape = (5, 4, 6)  # [season 0-4, density 0-3, stand_type 0-5]
    if mc_sa_coeff_a.shape != expected_shape:
        raise ValueError(
            f"mc_sa_coeff_a has shape {mc_sa_coeff_a.shape}, expected {expected_shape}"
        )
    if mc_sa_coeff_b.shape != expected_shape:
        raise ValueError(
            f"mc_sa_coeff_b has shape {mc_sa_coeff_b.shape}, expected {expected_shape}"
        )

    # Validate model_mcsa parameter
    if model_mcsa not in ('corrected', 'original'):
        raise ValueError(f"model_mcsa must be 'corrected' or 'original', got '{model_mcsa}'")

    mc_sa = ref_array.copy().astype(np.float64)

    season_vals, season_mask = _broadcast_masked_input(season, np.int8)
    density_adj, density_mask = _broadcast_masked_input(density, np.int8)
    stand_vals, stand_mask = _broadcast_masked_input(stand_type, np.int8)
    ffmc_raw_vals, ffmc_mask = _broadcast_masked_input(ffmc, np.float64)
    mc_ffmc_vals, mc_ffmc_mask = _broadcast_masked_input(mc_ffmc, np.float64)
    mc_dmc_vals, mc_dmc_mask = _broadcast_masked_input(mc_dmc, np.float64)

    # Base validity mask shared by both seasonal paths.
    base_invalid = (
        season_mask
        | density_mask
        | stand_mask
        | mc_ffmc_mask
        | mc_dmc_mask
        | ffmc_mask
    )

    # Validate season/density/stand_type values are within expected ranges
    if np.any((season_vals < 0) | (season_vals >= 5)):
        raise ValueError(f"season values must be 0-4, got {np.unique(season_vals)}")
    if np.any((density_adj < 0) | (density_adj >= 4)):
        raise ValueError(f"density values must be 0-3, got {np.unique(density_adj)}")
    if np.any((stand_vals < 0) | (stand_vals >= 6)):
        raise ValueError(f"stand_type values must be 0-5, got {np.unique(stand_vals)}")

    # Implement corrected mc_sa if requested
    if model_mcsa == 'corrected':
        density_adj[(ffmc_raw_vals > 92.93) & (density_adj == 3)] = 2
        density_adj[(ffmc_raw_vals > 96.15) & (density_adj == 1)] = 2

    finite_inputs = np.isfinite(mc_ffmc_vals) & np.isfinite(mc_dmc_vals) & np.isfinite(ffmc_raw_vals)
    transitional_mask = (season_vals == 2) & (~season_mask)
    regular_mask = (season_vals != 2) & (~season_mask)

    # Transitional (Sp-Su): average spring (1xx) and summer (3xx) coefficients.
    sel = transitional_mask & (~base_invalid) & finite_inputs
    if np.any(sel):
        dens = density_adj[sel]
        stand = stand_vals[sel]
        ffmc_sel = mc_ffmc_vals[sel]
        dmc_sel = mc_dmc_vals[sel]

        a_sp = mc_sa_coeff_a[1, dens, stand]
        b_sp = mc_sa_coeff_b[1, dens, stand]
        a_su = mc_sa_coeff_a[3, dens, stand]
        b_su = mc_sa_coeff_b[3, dens, stand]

        val_sp = np.exp(a_sp + (b_sp * np.log(ffmc_sel)) + (0.002232 * dmc_sel))
        val_su = np.exp(a_su + (b_su * np.log(ffmc_sel)) + (0.002232 * dmc_sel))
        mc_sa[sel] = (val_sp + val_su) / 2.0

        # Release large transitional temporaries before next path.
        del dens, stand, ffmc_sel, dmc_sel, a_sp, b_sp, a_su, b_su, val_sp, val_su

    # Spring/Summer/Fall direct lookup by season code.
    sel = regular_mask & (~base_invalid) & finite_inputs
    if np.any(sel):
        seas = season_vals[sel]
        dens = density_adj[sel]
        stand = stand_vals[sel]
        ffmc_sel = mc_ffmc_vals[sel]
        dmc_sel = mc_dmc_vals[sel]

        a = mc_sa_coeff_a[seas, dens, stand]
        b = mc_sa_coeff_b[seas, dens, stand]
        mc_sa[sel] = np.exp(a + (b * np.log(ffmc_sel)) + (0.002232 * dmc_sel))

        # Release large regular-season temporaries.
        del seas, dens, stand, ffmc_sel, dmc_sel, a, b

    # Release shared full-grid temporaries before final output assignment.
    del base_invalid, season_vals, season_mask, density_adj, density_mask, stand_vals, stand_mask
    del ffmc_raw_vals, ffmc_mask, mc_ffmc_vals, mc_ffmc_mask, mc_dmc_vals, mc_dmc_mask
    del finite_inputs, transitional_mask, regular_mask, sel

    # Preserve previous behavior: non-adjusted cells fall back to mc_ffmc.
    if isinstance(use_adjusted_mc, np.ndarray):
        mc_sa = np.where(use_adjusted_mc, mc_sa, mc_ffmc)
    else:
        mc_sa = mc_sa

    return mc_sa


def calc_season(
    ref_int_array: np.ndarray,
    month_day: int,
    season_cutoff_dates_dict: Dict[int, int],
) -> Union[int, np.ndarray]:
    """
    Calculate season code from month and day extracted from weather date.

    Determines the appropriate season (Spring, Transitional, Summer, or Fall) based on
    the calendar date using predefined cutoff dates.

    :param ref_int_array: Reference integer array for output shape consistency
    :param month_day: Month and day extracted from wx_date (MMDD format, e.g., 0531 for May 31)
    :param season_cutoff_dates_dict: Dictionary mapping season codes to cutoff dates (MMDD format)
    :return: Season code (1-4: Spring, Transitional, Summer, Fall)
    :raises TypeError: If month_day is not int or season_cutoff_dates_dict not a dict
    :raises ValueError: If month_day is invalid MMDD format or dict values not int
    """
    # Validate month_day type
    if not isinstance(month_day, (int, np.integer)):
        raise TypeError(f"month_day must be int (MMDD format), got {type(month_day)}")

    # Validate month_day format (MMDD should be 0-1231)
    if month_day < 0 or month_day > 1231:
        raise ValueError(f"month_day must be 0-1231 (MMDD format), got {month_day}")

    # Validate cutoff dates dict
    if not isinstance(season_cutoff_dates_dict, dict):
        raise TypeError(f"season_cutoff_dates_dict must be dict, got {type(season_cutoff_dates_dict)}")

    for season_code, cutoff_date in season_cutoff_dates_dict.items():
        if not isinstance(cutoff_date, (int, np.integer)):
            raise ValueError(f"Cutoff dates must be int, got {type(cutoff_date)} for season {season_code}")
        if cutoff_date < 0 or cutoff_date > 1231:
            raise ValueError(f"Cutoff date must be 0-1231, got {cutoff_date} for season {season_code}")

    season = np.zeros_like(ref_int_array, dtype=np.int8)
    for season_code, cutoff_date in sorted(season_cutoff_dates_dict.items()):
        if month_day <= cutoff_date:
            season += season_code
            break
    return season


def calc_stand_density(
    ref_int_array: np.ndarray,
    cc: Union[int, float, np.ndarray],
) -> Union[int, np.ndarray]:
    """
    Calculate stand density class from canopy cover percentage.

    Estimates stand density class (Low, Moderate, High) based on canopy cover
    using threshold values typical for fire behavior prediction systems.

    :param ref_int_array: Reference integer array for output shape consistency
    :param cc: Canopy cover percentage (0-100%)
    :return: Stand density class code (1: Low, 2: Moderate, 3: High)
    :raises TypeError: If inputs are not numeric types
    :raises ValueError: If canopy cover values are outside 0-100 range
    """
    # Validate cc type
    if not isinstance(cc, (int, float, np.ndarray)):
        raise TypeError(f"cc must be numeric or array, got {type(cc)}")

    # Ensure cc is array for consistent handling - preserve if already masked
    if isinstance(cc, mask.MaskedArray):
        cc_arr = np.atleast_1d(cc)
    else:
        cc_arr = np.atleast_1d(np.asarray(cc, dtype=np.float64))

    # Create/preserve mask for invalid values (NaN, inf) 
    if isinstance(cc_arr, mask.MaskedArray):
        # Combine existing mask with new mask for invalid values
        invalid_mask = ~np.isfinite(cc_arr.data)
        if cc_arr.mask is not mask.nomask:
            combined_mask = cc_arr.mask | invalid_mask
        else:
            combined_mask = invalid_mask
        cc_arr = mask.array(cc_arr.data, mask=combined_mask)
    else:
        # Create mask for invalid values in regular array
        invalid_mask = ~np.isfinite(cc_arr)
        if np.any(invalid_mask):
            cc_arr = mask.array(cc_arr, mask=invalid_mask)
    # For validation, use filled() to replace masked values with a valid value
    cc_check = cc_arr.filled(50) if isinstance(cc_arr, mask.MaskedArray) else cc_arr
    
    # Validate cc range (0-100%) - only check non-masked values
    if isinstance(cc_arr, mask.MaskedArray):
        # Check only valid (non-masked) values
        valid_mask = ~mask.getmaskarray(cc_arr)
        if np.any(valid_mask):
            valid_values = cc_arr[valid_mask]
            if np.any((valid_values < 0) | (valid_values > 100)):
                invalid_vals = valid_values[(valid_values < 0) | (valid_values > 100)]
                raise ValueError(f"Canopy cover must be 0-100%, got values: {np.unique(invalid_vals)}")
    else:
        # For regular arrays, check all values
        if np.any((cc_arr < 0) | (cc_arr > 100)):
            invalid_vals = cc_arr[(cc_arr < 0) | (cc_arr > 100)]
            raise ValueError(f"Canopy cover must be 0-100%, got values: {np.unique(invalid_vals)}")

    # Estimate stand density class from canopy cover
    mask_l = (cc_check >= 0) & (cc_check <= 45)
    mask_m = (cc_check > 45) & (cc_check <= 60)
    mask_h = (cc_check > 60) & (cc_check <= 100)

    density = ref_int_array.copy()
    density[mask_l] = 1  # 'L' (Low)
    density[mask_m] = 2  # 'M' (Moderate)
    density[mask_h] = 3  # 'H' (High)

    # For masked arrays, preserve the mask
    if isinstance(cc_arr, mask.MaskedArray):
        density = mask.array(density, mask=mask.getmaskarray(cc_arr))

    del mask_l, mask_m, mask_h
    return density


def get_adjusted_mc_areas(
    ref_int_array: np.ndarray,
    stand_type: Union[int, np.ndarray],
    stand_type_code_dict_inv: Dict[str, int],
) -> np.ndarray:
    """
    Determine which areas should use adjusted moisture content values.

    Creates a boolean mask indicating which cells have valid stand types and should
    use the adjusted MC (MCSA) values rather than falling back to FFMC-derived MC.
    Density corrections at high FFMC are handled separately in calc_mc_sa().

    :param ref_int_array: Reference integer array for output shape consistency
    :param stand_type: Stand type code
    :param stand_type_code_dict_inv: Dictionary mapping stand type codes to numeric values
    :return: Boolean array mask indicating areas with valid stand types
    :raises TypeError: If stand_type_code_dict_inv is not a dict
    :raises ValueError: If stand_type codes are not integers or outside expected range
    """
    # Validate dictionary type
    if not isinstance(stand_type_code_dict_inv, dict):
        raise TypeError(f"stand_type_code_dict_inv must be dict, got {type(stand_type_code_dict_inv)}")

    # Validate dictionary values are integers in valid range (1-5)
    for code_name, code_val in stand_type_code_dict_inv.items():
        if not isinstance(code_val, (int, np.integer)):
            raise ValueError(f"Stand type code for '{code_name}' must be int, got {type(code_val)}")
        if code_val < 1 or code_val > 5:
            raise ValueError(f"Stand type code for '{code_name}' must be 1-5, got {code_val}")

    # Initialize use_adjusted_mc array
    use_adjusted_mc = np.ones_like(ref_int_array, dtype=bool)

    # Keep adjusted MC for valid stands
    if stand_type is not None:
        valid_codes = list(stand_type_code_dict_inv.values())
        mask_invalid_stand = ~np.isin(stand_type, valid_codes)
        use_adjusted_mc[mask_invalid_stand] = False
        del mask_invalid_stand
    return use_adjusted_mc






