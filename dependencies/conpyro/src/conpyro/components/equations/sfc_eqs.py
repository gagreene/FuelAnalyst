# -*- coding: utf-8 -*-
"""
Surface Fuel Consumption Calculation Equations

Created on Thu Oct 16, 11:45:00 2025

@author: Gregory A. Greene
"""
__author__ = ['Gregory A. Greene, map.n.trowel@gmail.com']

from typing import Union, Tuple
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
        return mask.array([data], mask=np.isnan([data]))
    elif isinstance(data, mask.MaskedArray):
        # Already masked - return as-is, preserving all existing masks
        return data
    else:
        # Regular array - convert to masked array with invalid values masked
        data_arr = np.asarray(data)
        return mask.array(data_arr, mask=np.isnan(data_arr))


def calc_degroot_ffc(
    bui: Union[int, float, np.ndarray],
    ffl: Union[int, float, np.ndarray],
) -> Union[int, float, np.ndarray]:
    """
    Calculate Forest Floor Consumption (FFC) using de Groot et al. (2009) method.

    Returns estimated FFC value. Does not estimate woody fuel consumption.
    Based on fuel load & BUI from CFFBPS experimental burns.

    Note: This equation may give nonsensical results (e.g. FFC > FFL) for cases of
    low forest floor load (FFL) and high BUI.

    :param bui: Buildup Index
    :param ffl: Forest floor loading (litter + duff) (kg/m2)
    :return: Forest Floor Consumption using De Groot method (kg/m2)
    :raises TypeError: If inputs are not numeric types
    """
    if not isinstance(bui, (int, float, np.ndarray)):
        raise TypeError(f"bui must be numeric or array, got {type(bui)}")
    if not isinstance(ffl, (int, float, np.ndarray)):
        raise TypeError(f"ffl must be numeric or array, got {type(ffl)}")

    # Ensure inputs are masked arrays
    bui = _ensure_masked_array(bui)
    ffl = _ensure_masked_array(ffl)

    # FFC = 0.156 * ffl + 0.015 * bui - 0.176
    # R^2 = 0.787
    ffc_degroot = (0.156 * ffl) + (0.015 * bui) - 0.176

    # Assign ffc_degroot as ffl wherever ffl < ffc_degroot
    ffc_degroot = np.where(ffc_degroot > ffl, ffl, ffc_degroot)

    return ffc_degroot


def calc_fbp_sfc(
    fuel_type: Union[int, np.ndarray],
    ffmc: Union[int, float, np.ndarray],
    bui: Union[int, float, np.ndarray],
    pct_cnfr: Union[int, float, np.ndarray],
    gfl: Union[int, float, np.ndarray],
) -> Tuple:
    """
    Calculate surface fuel consumption (SFC) using Canadian Forest Fire Behavior Prediction System equations.

    Estimates total surface fuel consumption (SFC), forest floor consumption (FFC), and woody fuel
    consumption (WFC) using fuel type-specific approaches developed for the FBP System.
    Each fuel type has its own equation based on FFMC, BUI, percent conifer, or grass fuel load.

    :param fuel_type: CFFBPS Fuel Type numeric code (1-20)
    :param ffmc: Fine Fuel Moisture Code
    :param bui: Buildup Index
    :param pct_cnfr: Percent Conifer (0-100%)
    :param gfl: Grass fuel load (kg/m2)
    :return: Tuple of (ffc_fbp, wfc_fbp, sfc_fbp)
             ffc_fbp: Forest floor consumption using FBP method (kg/m2)
             wfc_fbp: Woody fuel consumption using FBP method (kg/m2)
             sfc_fbp: Surface fuel consumption using FBP method (kg/m2)
    :raises TypeError: If inputs are not numeric types
    """
    if not isinstance(fuel_type, (int, np.ndarray)):
        raise TypeError(f'fuel_type must be int or array, got {type(fuel_type)}')
    if not isinstance(ffmc, (int, float, np.ndarray)):
        raise TypeError(f'ffmc must be numeric or array, got {type(ffmc)}')
    if not isinstance(bui, (int, float, np.ndarray)):
        raise TypeError(f'bui must be numeric or array, got {type(bui)}')
    if not isinstance(pct_cnfr, (int, float, np.ndarray)):
        raise TypeError(f'pct_cnfr must be numeric or array, got {type(pct_cnfr)}')
    if not isinstance(gfl, (int, float, np.ndarray)):
        raise TypeError(f'gfl must be numeric or array, got {type(gfl)}')

    # Ensure inputs are masked arrays
    fuel_type = _ensure_masked_array(fuel_type)
    ffmc = _ensure_masked_array(ffmc)
    bui = _ensure_masked_array(bui)
    pct_cnfr = _ensure_masked_array(pct_cnfr)
    gfl = _ensure_masked_array(gfl)

    # Initialize output arrays
    ffc = np.full_like(fuel_type, np.inf, dtype=np.float64)
    wfc = np.full_like(fuel_type, np.inf, dtype=np.float64)
    sfc = np.full_like(fuel_type, np.inf, dtype=np.float64)

    # 1: C-1
    mask_1 = fuel_type == 1
    if np.any(mask_1):
        np.seterr(invalid='ignore', over='ignore')
        sfc[mask_1] = np.where(
            ffmc[mask_1] > 84,
            0.75 + 0.75 * np.sqrt(1 - np.exp(-0.23 * (ffmc[mask_1] - 84))),
            0.75 - 0.75 * np.sqrt(1 - np.exp(0.23 * (ffmc[mask_1] - 84)))
        )
        np.seterr(invalid='warn', over='warn')

    # 2: C-2
    mask_2 = fuel_type == 2
    if np.any(mask_2):
        sfc[mask_2] = 5 * (1 - np.exp(-0.0115 * bui[mask_2]))

    # 3, 4: C-3, C-4
    mask_34 = np.isin(fuel_type, [3, 4])
    if np.any(mask_34):
        sfc[mask_34] = 5 * np.power(1 - np.exp(-0.0164 * bui[mask_34]), 2.24)

    # 5, 6: C-5, C-6
    mask_56 = np.isin(fuel_type, [5, 6])
    if np.any(mask_56):
        sfc[mask_56] = 5 * np.power(1 - np.exp(-0.0149 * bui[mask_56]), 2.48)

    # 7: C-7
    mask_7 = fuel_type == 7
    if np.any(mask_7):
        ffc_7 = 2 * (1 - np.exp(-0.104 * (ffmc[mask_7] - 70)))
        ffc_7 = np.where(ffc_7 < 0, 0, ffc_7)
        wfc_7 = 1.5 * (1 - np.exp(-0.0201 * bui[mask_7]))
        ffc[mask_7] = ffc_7
        wfc[mask_7] = wfc_7
        sfc[mask_7] = ffc_7 + wfc_7

    # 8, 9: D-1, D-2
    mask_89 = np.isin(fuel_type, [8, 9])
    if np.any(mask_89):
        sfc[mask_89] = 1.5 * (1 - np.exp(-0.0183 * bui[mask_89]))

    # 10, 11: M-1, M-2
    mask_1011 = np.isin(fuel_type, [10, 11])
    if np.any(mask_1011):
        c2_sfc = 5 * (1 - np.exp(-0.0115 * bui[mask_1011]))
        d1_sfc = 1.5 * (1 - np.exp(-0.0183 * bui[mask_1011]))
        sfc[mask_1011] = ((pct_cnfr[mask_1011] / 100) * c2_sfc) + (((100 - pct_cnfr[mask_1011]) / 100) * d1_sfc)

    # 12, 13: M-3, M-4
    mask_1213 = np.isin(fuel_type, [12, 13])
    if np.any(mask_1213):
        sfc[mask_1213] = 5 * (1 - np.exp(-0.0115 * bui[mask_1213]))

    # 14, 15: O-1a, O-1b
    mask_1415 = np.isin(fuel_type, [14, 15])
    if np.any(mask_1415):
        sfc[mask_1415] = gfl[mask_1415]

    # 16: S-1
    mask_16 = fuel_type == 16
    if np.any(mask_16):
        ffc_16 = 4 * (1 - np.exp(-0.025 * bui[mask_16]))
        wfc_16 = 4 * (1 - np.exp(-0.034 * bui[mask_16]))
        ffc[mask_16] = ffc_16
        wfc[mask_16] = wfc_16
        sfc[mask_16] = ffc_16 + wfc_16

    # 17: S-2
    mask_17 = fuel_type == 17
    if np.any(mask_17):
        ffc_17 = 10 * (1 - np.exp(-0.013 * bui[mask_17]))
        wfc_17 = 6 * (1 - np.exp(-0.06 * bui[mask_17]))
        ffc[mask_17] = ffc_17
        wfc[mask_17] = wfc_17
        sfc[mask_17] = ffc_17 + wfc_17

    # 18: S-3
    mask_18 = fuel_type == 18
    if np.any(mask_18):
        ffc_18 = 12 * (1 - np.exp(-0.0166 * bui[mask_18]))
        wfc_18 = 20 * (1 - np.exp(-0.021 * bui[mask_18]))
        ffc[mask_18] = ffc_18
        wfc[mask_18] = wfc_18
        sfc[mask_18] = ffc_18 + wfc_18

    # 19: NF (non-fuel)
    mask_19 = fuel_type == 19
    if np.any(mask_19):
        sfc[mask_19] = np.nan

    # 20: WA (water)
    mask_20 = fuel_type == 20
    if np.any(mask_20):
        sfc[mask_20] = np.nan

    return ffc, wfc, sfc


def compare_fuels(
    ffc_degroot: Union[int, float, np.ndarray],
    ffc_fbp: Union[int, float, np.ndarray],
    wfc_fbp: Union[int, float, np.ndarray],
    sfc_fbp: Union[int, float, np.ndarray],
    ffl: Union[int, float, np.ndarray],
    wfl: Union[int, float, np.ndarray],
) -> Tuple:
    """
    Compare De Groot and FBP fuel consumption estimates and apply bounds checking.

    Uses De Groot FFC estimates where FBP FFC is NaN, and ensures fuel consumption
    does not exceed measured fuel loads. Calculates total SFC as the minimum of the
    sum of FFC+WFC and the FBP SFC.

    :param ffc_degroot: Forest floor consumption using De Groot method (kg/m2)
    :param ffc_fbp: Forest floor consumption using FBP method (kg/m2)
    :param wfc_fbp: Woody fuel consumption using FBP method (kg/m2)
    :param sfc_fbp: Surface fuel consumption using FBP method (kg/m2)
    :param ffl: Measured forest floor load (kg/m2)
    :param wfl: Measured woody fuel load (kg/m2)
    :return: Tuple of (ffc, wfc, sfc)
             ffc: Final forest floor consumption (kg/m2)
             wfc: Final woody fuel consumption (kg/m2)
             sfc: Final total surface fuel consumption (kg/m2)
    :raises TypeError: If inputs are not numeric types
    """
    if not isinstance(ffc_degroot, (int, float, np.ndarray)):
        raise TypeError(f'ffc_degroot must be numeric or array, got {type(ffc_degroot)}')
    if not isinstance(ffc_fbp, (int, float, np.ndarray, type(None))):
        raise TypeError(f'ffc_fbp must be None, numeric or array, got {type(ffc_fbp)}')
    if not isinstance(wfc_fbp, (int, float, np.ndarray, type(None))):
        raise TypeError(f'wfc_fbp must be None, numeric or array, got {type(wfc_fbp)}')
    if not isinstance(sfc_fbp, (int, float, np.ndarray, type(None))):
        raise TypeError(f'sfc_fbp must be None, numeric or array, got {type(sfc_fbp)}')
    if not isinstance(ffl, (int, float, np.ndarray)):
        raise TypeError(f'ffl must be numeric or array, got {type(ffl)}')
    if not isinstance(wfl, (int, float, np.ndarray)):
        raise TypeError(f'wfl must be numeric or array, got {type(wfl)}')

    # Ensure inputs are masked arrays
    ffc_degroot = _ensure_masked_array(ffc_degroot)
    ffc_fbp = _ensure_masked_array(ffc_fbp)
    wfc_fbp = _ensure_masked_array(wfc_fbp)
    sfc_fbp = _ensure_masked_array(sfc_fbp)
    ffl = _ensure_masked_array(ffl)
    wfl = _ensure_masked_array(wfl)

    # Assign De Groot FFC values where FBP FFC is NaN
    ffc = mask.where(np.isfinite(ffc_fbp), ffc_fbp, ffc_degroot)
    wfc = mask.where(np.isfinite(wfc_fbp), wfc_fbp, wfl)

    # Compare fuel consumption values with measured fuel loads, and assign minimum of the two
    ffc = mask.where(ffl < ffc, ffl, ffc)
    wfc = mask.where(wfl < wfc, wfl, wfc)

    # Calculate total SFC
    sfc = mask.where((ffc + wfc) < sfc_fbp, ffc + wfc, sfc_fbp)

    # Limit SFC to range between 0.1 and 6 kg/m^2
    sfc = mask.clip(sfc, 0.1, 6)

    return ffc, wfc, sfc

