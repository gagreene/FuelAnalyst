# -*- coding: utf-8 -*-
"""
Rothermel (1983) Fuel Moisture Content Calculation Equations and Reference Data

Created on Thu Oct 16, 11:45:00 2025

@author: Gregory A. Greene
"""
__author__ = ['Gregory A. Greene, map.n.trowel@gmail.com']

from typing import Dict, Tuple
import numpy as np
from numpy import ma as mask


# ============================================================================
# ROTHERMEL REFERENCE DATA TABLES
# ============================================================================

# Temperature cutoffs (°C)
ROTH_TEMP_BINS = np.array([
    [-1.7, 9.4, 20.6, 31.7, 42.8, 100]
], dtype=np.float16)

# Relative Humidity cutoffs (%)
ROTH_RH_BINS = np.array([
    [4, 9, 14, 19, 24, 29, 34, 39, 44, 49, 54, 59, 64, 69, 74, 79, 84, 89, 94, 99, 100]
], dtype=np.float16)

# Daytime reference fuel moisture (May-July)
ROTH_DAY_REF_FM_LIST1 = np.array([
    [1, 2, 2, 3, 4, 5, 5, 6, 7, 8, 8, 8, 9, 9, 10, 11, 12, 12, 13, 13, 14],
    [1, 2, 2, 3, 4, 5, 5, 6, 7, 7, 7, 8, 9, 9, 10, 10, 11, 12, 13, 13, 13],
    [1, 2, 2, 3, 4, 5, 5, 6, 6, 7, 7, 8, 8, 9, 9, 10, 11, 12, 12, 12, 13],
    [1, 1, 2, 2, 3, 4, 5, 5, 6, 7, 7, 8, 8, 8, 9, 10, 10, 11, 12, 12, 13],
    [1, 1, 2, 2, 3, 4, 4, 5, 6, 7, 7, 8, 8, 8, 9, 10, 10, 11, 12, 12, 13],
    [1, 1, 2, 2, 3, 4, 4, 5, 6, 7, 7, 8, 8, 8, 9, 10, 10, 11, 12, 12, 12]
], dtype=np.int16)

# Daytime reference fuel moisture (February-April, August-October)
ROTH_DAY_REF_FM_LIST2 = np.array([
    [1, 2, 2, 3, 4, 5, 5, 6, 7, 8, 8, 8, 9, 9, 10, 11, 12, 12, 13, 13, 14],
    [1, 2, 2, 3, 4, 5, 5, 6, 7, 7, 7, 8, 9, 9, 10, 10, 11, 12, 13, 13, 13],
    [1, 2, 2, 3, 4, 5, 5, 6, 6, 7, 7, 8, 8, 9, 9, 10, 11, 12, 12, 12, 13],
    [1, 1, 2, 2, 3, 4, 5, 5, 6, 7, 7, 8, 8, 8, 9, 10, 10, 11, 12, 12, 13],
    [1, 1, 2, 2, 3, 4, 4, 5, 6, 7, 7, 8, 8, 8, 9, 10, 10, 11, 12, 12, 13],
    [1, 1, 2, 2, 3, 4, 4, 5, 6, 7, 7, 8, 8, 8, 9, 10, 10, 11, 12, 12, 12]
], dtype=np.int16)

# Nighttime reference fuel moisture
ROTH_NIGHT_REF_FM = np.array([
    [1, 2, 4, 5, 5, 6, 7, 8, 9, 10, 11, 12, 12, 14, 15, 17, 19, 22, 25, 25, 25],
    [1, 2, 3, 4, 5, 6, 7, 8, 9, 9, 11, 11, 12, 13, 14, 16, 18, 21, 24, 25, 25],
    [1, 2, 3, 4, 5, 6, 6, 8, 8, 9, 10, 11, 11, 12, 14, 16, 17, 20, 23, 25, 25],
    [1, 2, 3, 4, 4, 5, 6, 7, 8, 9, 10, 10, 11, 12, 13, 15, 17, 20, 23, 25, 25],
    [1, 2, 3, 3, 4, 5, 6, 7, 8, 9, 9, 10, 10, 11, 13, 14, 16, 19, 22, 25, 25],
    [1, 2, 2, 3, 4, 5, 6, 6, 8, 8, 9, 9, 10, 11, 12, 14, 16, 19, 21, 24, 25]
], dtype=np.int16)

# Same day/night reference tables for other month groups
ROTH_DAY_REF_FM_LIST3 = np.array([
    [1, 2, 2, 3, 4, 5, 5, 6, 7, 8, 8, 8, 9, 9, 10, 11, 12, 12, 13, 13, 14],
    [1, 2, 2, 3, 4, 5, 5, 6, 7, 7, 7, 8, 9, 9, 10, 10, 11, 12, 13, 13, 13],
    [1, 2, 2, 3, 4, 5, 5, 6, 6, 7, 7, 8, 8, 9, 9, 10, 11, 12, 12, 12, 13],
    [1, 1, 2, 2, 3, 4, 5, 5, 6, 7, 7, 8, 8, 8, 9, 10, 10, 11, 12, 12, 13],
    [1, 1, 2, 2, 3, 4, 4, 5, 6, 7, 7, 8, 8, 8, 9, 10, 10, 11, 12, 12, 13],
    [1, 1, 2, 2, 3, 4, 4, 5, 6, 7, 7, 8, 8, 8, 9, 10, 10, 11, 12, 12, 12]
], dtype=np.int16)

# ============================================================================
# ROTHERMEL DEAD FUEL MOISTURE CORRECTION TABLES
# ============================================================================

# Daytime correction table (May-July)
ROTH_DEAD_MC_DAY_TABLE_1 = np.array([
    [2,3,4,1,1,1,0,0,1,0,0,1,1,1,1,2,3,4,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
    [3,4,4,1,2,2,1,1,2,1,1,2,1,2,2,3,4,4,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
    [2,2,3,1,1,1,0,0,1,0,0,1,1,1,2,3,4,4,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
    [1,2,2,0,0,1,0,0,1,1,1,2,2,3,4,4,5,6,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
    [2,3,3,1,1,1,0,0,1,0,0,1,1,1,1,2,3,3,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
    [2,3,3,1,1,2,0,1,1,0,1,1,1,1,2,2,3,3,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
    [2,3,4,1,1,2,0,0,1,0,0,1,0,1,1,2,3,3,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
    [4,5,6,2,3,4,1,1,2,0,0,1,0,0,1,1,2,2,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
    [4,5,5,3,4,5,3,3,4,3,3,4,3,4,5,4,5,5,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
    [4,4,5,3,4,5,3,3,4,3,4,4,3,4,5,4,5,6,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
    [4,4,5,3,4,5,3,3,4,3,3,4,3,4,5,4,5,5,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
    [4,5,6,3,4,5,3,3,4,3,3,4,3,4,5,4,4,5,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]
], dtype=np.int16)

# Daytime correction table (February-April, August-October)
ROTH_DEAD_MC_DAY_TABLE_2 = np.array([
    [3,4,5,1,2,3,1,1,2,1,1,2,1,2,3,3,4,5,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
    [3,4,5,3,3,4,2,3,4,2,3,4,3,3,4,3,4,5,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
    [3,4,5,1,2,3,1,1,1,1,1,2,1,2,3,3,4,5,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
    [3,3,4,1,1,4,1,1,1,1,2,3,3,4,5,4,5,6,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
    [3,4,5,1,2,2,1,1,1,1,1,1,1,2,3,3,4,5,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
    [3,4,5,1,2,2,0,1,1,0,1,1,1,2,2,3,4,5,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
    [3,4,5,1,2,3,1,1,1,1,1,1,1,2,3,3,4,5,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
    [4,5,6,3,4,5,1,2,3,1,1,1,1,1,1,3,3,4,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
    [4,5,6,4,5,5,3,4,5,3,4,5,4,5,5,4,5,6,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
    [4,5,6,3,4,5,3,4,5,3,4,5,4,5,6,4,5,6,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
    [4,5,6,3,4,5,3,4,5,3,4,5,3,4,5,4,5,6,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
    [4,5,6,4,5,6,3,4,5,3,4,5,3,4,5,4,5,6,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]
], dtype=np.int16)

# Daytime correction table (November-December, January)
ROTH_DEAD_MC_DAY_TABLE_3 = np.array([
    [4,5,6,3,4,5,2,3,4,2,3,4,3,4,5,4,5,6,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
    [4,5,6,4,5,6,4,5,6,4,5,6,4,5,6,4,5,6,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
    [4,5,6,3,4,4,2,3,3,2,3,3,3,4,5,4,5,6,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
    [4,5,6,2,3,4,2,2,3,3,4,4,4,5,6,4,5,6,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
    [4,5,6,3,4,5,2,3,3,2,2,3,3,4,4,4,5,6,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
    [4,5,6,2,3,3,1,1,2,1,1,2,2,3,3,4,5,6,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
    [4,5,6,3,4,5,2,3,3,2,3,3,3,4,4,4,5,6,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
    [4,5,6,4,5,6,3,4,4,2,2,3,2,3,4,4,5,6,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
    [4,5,6,4,5,6,4,5,6,4,5,6,4,5,6,4,5,6,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
    [4,5,6,4,5,6,4,5,6,4,5,6,4,5,6,4,5,6,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
    [4,5,6,4,5,6,4,5,6,4,5,6,4,5,6,4,5,6,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
    [4,5,6,4,5,6,4,5,6,4,5,6,4,5,6,4,5,6,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]
], dtype=np.int16)

# Nighttime correction table
ROTH_DEAD_MC_NIGHT_TABLE = np.array([
    [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,9,1,1,13,1,2,16,2,2,17,1,1,18,1,1,16,2,1],
    [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,9,1,1,13,1,2,16,2,2,17,1,1,18,1,1,16,2,1],
    [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,9,0,1,14,0,1,16,0,2,17,0,1,18,0,0,9,0,1],
    [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,9,0,1,14,0,1,16,0,2,17,0,1,18,0,0,9,0,1]
], dtype=np.int16)

# Time of day categories in HHMM format
TIME_OF_DAY_CATEGORIES = np.array(
    [200, 400, 600, 800, 1000, 1200, 1400, 1600, 1800, 2000, 2200, 2400],
    dtype=np.int16
)

# Time ordering (for column indexing)
TIME_ORDER_COLS = [800, 1000, 1200, 1400, 1600, 1800, 2000, 2200, 2400, 200, 400, 600]

# Elevation ordering
ELEV_ORDER_COLS = ['B', 'L', 'A']

# Create lookup dictionaries for time and elevation positions
_TIME_POS = {t: i for i, t in enumerate(TIME_ORDER_COLS)}
_ELEV_POS = {e: i for i, e in enumerate(ELEV_ORDER_COLS)}

# Aspect/slope/shade combinations for daytime
DAY_ASPECT_SLOPE_SHADE_LIST = [
    ['North', 30, 50], ['North', 100, 50],
    ['East', 30, 50], ['East', 100, 50],
    ['South', 30, 50], ['South', 100, 50],
    ['West', 30, 50], ['West', 100, 50],
    ['North', 100, 100], ['East', 100, 100],
    ['South', 100, 100], ['West', 100, 100]
]

# Aspect/slope/shade combinations for nighttime
NIGHT_ASPECT_SLOPE_SHADE_LIST = [
    ['North', 100, 100], ['East', 100, 100],
    ['South', 100, 100], ['West', 100, 100]
]

# Create lookup dictionaries for row mapping
_DAY_ROW_MAP = {tuple(x): i for i, x in enumerate(DAY_ASPECT_SLOPE_SHADE_LIST)}
_NIGHT_ROW_MAP = {tuple(x): i for i, x in enumerate(NIGHT_ASPECT_SLOPE_SHADE_LIST)}

# Month groupings
MONTH_GROUPS = {
    'group_1': ['May', 'June', 'July'],
    'group_2': ['February', 'March', 'April', 'August', 'September', 'October'],
    'group_3': ['November', 'December', 'January']
}


# ============================================================================
# HELPER FUNCTIONS FOR INDEXING
# ============================================================================

def get_temp_index(temp: np.ndarray) -> np.ndarray:
    """
    Get temperature bin index for reference table lookup.

    :param temp: Temperature values (°C), can be scalar or array
    :return: Temperature bin indices
    """
    bins = ROTH_TEMP_BINS
    if isinstance(temp, mask.MaskedArray):
        vals = temp.filled(np.nan)
    else:
        vals = np.atleast_1d(np.asarray(temp))
    idx = np.searchsorted(bins.ravel(), vals, side='left')
    return np.clip(idx, 0, len(bins) - 1)


def get_rh_index(rh: np.ndarray) -> np.ndarray:
    """
    Get relative humidity bin index for reference table lookup.

    :param rh: Relative humidity values (%), can be scalar or array
    :return: Relative humidity bin indices
    """
    bins = ROTH_RH_BINS
    if isinstance(rh, mask.MaskedArray):
        vals = rh.filled(np.nan)
    else:
        vals = np.atleast_1d(np.asarray(rh))
    idx = np.searchsorted(bins.ravel(), vals, side='left')
    return np.clip(idx, 0, len(bins) - 1)


def get_time_of_day_category(time: np.ndarray) -> np.ndarray:
    """
    Classify time into nearest time-of-day category.

    :param time: Time values in HHMM format (0-2400)
    :return: Time category values
    """
    bins = TIME_OF_DAY_CATEGORIES
    pos = np.searchsorted(bins, time, side='left')
    pos = np.clip(pos, 0, len(bins) - 1)
    return bins[pos]


def get_elevation_class(site_elev: np.ndarray, stn_elev: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    Classify elevation as 'B' (far), 'L' (local/close), or mark as too far.

    :param site_elev: Site elevation (m)
    :param stn_elev: Station elevation (m)
    :return: Tuple of (elevation_class, too_far_flag)
    """
    if isinstance(site_elev, mask.MaskedArray):
        se = site_elev.filled(np.nan)
    else:
        se = np.atleast_1d(np.asarray(site_elev))
    
    if isinstance(stn_elev, mask.MaskedArray):
        st = stn_elev.filled(np.nan)
    else:
        st = np.atleast_1d(np.asarray(stn_elev))
    
    dz = np.abs(st - se)
    too_far = dz > 609.6
    close = (st - 304.8 <= se) & (se <= st + 304.8)
    elev = np.where(close, 'L', 'B')
    return elev, too_far


def get_aspect_class(aspect: np.ndarray) -> np.ndarray:
    """
    Classify aspect (0-360°) into cardinal directions.

    :param aspect: Aspect values in degrees
    :return: Aspect class names ('North', 'East', 'South', 'West')
    """
    if isinstance(aspect, mask.MaskedArray):
        a = aspect.filled(0)
    else:
        a = np.atleast_1d(np.asarray(aspect))
    
    # Ensure a is properly shaped for output
    a_shape = a.shape
    
    out = np.full(a_shape, 'North', dtype=object)
    out[(a > 45) & (a <= 135)] = 'East'
    out[(a > 135) & (a <= 225)] = 'South'
    out[(a > 225) & (a <= 315)] = 'West'
    out[(a > 315)] = 'North'
    return out


def get_shade_class(cc: np.ndarray) -> np.ndarray:
    """
    Classify canopy closure into shade categories.

    :param cc: Canopy closure (%)
    :return: Shade class (50 or 100)
    """
    if isinstance(cc, mask.MaskedArray):
        c = cc.filled(0)
    else:
        c = np.atleast_1d(np.asarray(cc))
    
    return np.where(c < 50, 50, 100)


def get_slope_class(slope: np.ndarray, shade_class: np.ndarray) -> np.ndarray:
    """
    Classify slope into slope categories based on shade.

    :param slope: Slope values (%)
    :param shade_class: Shade class from get_shade_class()
    :return: Slope class (30 or 100)
    """
    if isinstance(slope, mask.MaskedArray):
        s = slope.filled(0)
    else:
        s = np.atleast_1d(np.asarray(slope))
    
    return np.where(shade_class == 100, 100, np.where(np.abs(s) <= 30, 30, 100))


def get_month_group(month: str) -> int:
    """
    Get the month group code for a given month name.

    :param month: Month name (e.g., 'January', 'May', 'December')
    :return: Month group code (1, 2, 3, or -1 if unknown)
    """
    if month in MONTH_GROUPS['group_1']:
        return 1
    elif month in MONTH_GROUPS['group_2']:
        return 2
    elif month in MONTH_GROUPS['group_3']:
        return 3
    else:
        return -1


def get_day_row_index(aspect: np.ndarray, slope_class: np.ndarray, shade_class: np.ndarray) -> np.ndarray:
    """
    Get row index for daytime correction table lookup.

    :param aspect: Aspect class from get_aspect_class()
    :param slope_class: Slope class from get_slope_class()
    :param shade_class: Shade class from get_shade_class()
    :return: Row indices into daytime correction tables
    """
    out = np.full(np.atleast_1d(aspect).shape, -1, dtype=np.int16)
    for k, v in _DAY_ROW_MAP.items():
        sel = (aspect == k[0]) & (slope_class == int(k[1])) & (shade_class == int(k[2]))
        out[sel] = v
    return out


def get_night_row_index(aspect: np.ndarray) -> np.ndarray:
    """
    Get row index for nighttime correction table lookup.

    :param aspect: Aspect class from get_aspect_class()
    :return: Row indices into nighttime correction table
    """
    out = np.full(np.atleast_1d(aspect).shape, -1, dtype=np.int16)
    for k, v in _NIGHT_ROW_MAP.items():
        out[aspect == k[0]] = v
    return out


def get_col_index(time_of_day_val: np.ndarray, elev_class: np.ndarray) -> np.ndarray:
    """
    Get column index for correction table lookup.

    :param time_of_day_val: Time-of-day category from get_time_of_day_category()
    :param elev_class: Elevation class from get_elevation_class()
    :return: Column indices into correction tables
    """
    time_pos = np.vectorize(_TIME_POS.get)(time_of_day_val)
    elev_pos = np.vectorize(_ELEV_POS.get)(elev_class)
    return (time_pos * 3 + elev_pos).astype(np.int16)


# ============================================================================
# MAIN CALCULATION FUNCTIONS
# ============================================================================

def calc_reference_fm(
    temp: np.ndarray,
    rh: np.ndarray,
    is_daytime: np.ndarray,
) -> np.ndarray:
    """
    Calculate reference fuel moisture from temperature and relative humidity.

    Uses daytime reference table for times 0800-2000, nighttime table otherwise.

    :param temp: Temperature values (°C)
    :param rh: Relative humidity values (%)
    :param is_daytime: Boolean array indicating daytime (True) vs nighttime (False)
    :return: Reference fuel moisture values (%)
    """
    temp_idx = get_temp_index(temp)
    rh_idx = get_rh_index(rh)
    
    day_vals = ROTH_DAY_REF_FM_LIST1[temp_idx, rh_idx]
    night_vals = ROTH_NIGHT_REF_FM[temp_idx, rh_idx]
    
    return np.where(is_daytime, day_vals, night_vals)


def calc_correction_fm(
    time: np.ndarray,
    site_elev: np.ndarray,
    stn_elev: np.ndarray,
    aspect: np.ndarray,
    slope: np.ndarray,
    cc: np.ndarray,
    month: str,
    is_daytime: np.ndarray,
) -> np.ndarray:
    """
    Calculate fuel moisture correction from Rothermel tables.

    Applies different correction tables based on daytime/nighttime and month group.

    :param time: Time values in HHMM format (0-2400)
    :param site_elev: Site elevation (m)
    :param stn_elev: Station elevation (m)
    :param aspect: Aspect values (degrees 0-360)
    :param slope: Slope values (%)
    :param cc: Canopy closure (%)
    :param month: Month name (e.g., 'May', 'January')
    :param is_daytime: Boolean array indicating daytime (True) vs nighttime (False)
    :return: Fuel moisture correction values (%)
    """
    # Ensure all inputs are at least 1-d arrays
    time_arr = np.atleast_1d(np.asarray(time))
    
    # Handle masked arrays properly
    if isinstance(site_elev, mask.MaskedArray):
        site_elev_arr = np.atleast_1d(site_elev.filled(np.nan))
    else:
        site_elev_arr = np.atleast_1d(np.asarray(site_elev))
    
    if isinstance(stn_elev, mask.MaskedArray):
        stn_elev_arr = np.atleast_1d(stn_elev.filled(np.nan))
    else:
        stn_elev_arr = np.atleast_1d(np.asarray(stn_elev))
    
    if isinstance(aspect, mask.MaskedArray):
        aspect_arr = np.atleast_1d(aspect.filled(0))
    else:
        aspect_arr = np.atleast_1d(np.asarray(aspect))
    
    if isinstance(slope, mask.MaskedArray):
        slope_arr = np.atleast_1d(slope.filled(0))
    else:
        slope_arr = np.atleast_1d(np.asarray(slope))
    
    if isinstance(cc, mask.MaskedArray):
        cc_arr = np.atleast_1d(cc.filled(0))
    else:
        cc_arr = np.atleast_1d(np.asarray(cc))
    
    # Broadcast all to the same shape (assuming time is the primary shape)
    result_shape = time_arr.shape
    if site_elev_arr.size == 1:
        site_elev_arr = np.full(result_shape, site_elev_arr.item())
    if stn_elev_arr.size == 1:
        stn_elev_arr = np.full(result_shape, stn_elev_arr.item())
    if aspect_arr.size == 1:
        aspect_arr = np.full(result_shape, aspect_arr.item())
    if slope_arr.size == 1:
        slope_arr = np.full(result_shape, slope_arr.item())
    if cc_arr.size == 1:
        cc_arr = np.full(result_shape, cc_arr.item())
    
    # Get auxiliary classifications
    tod_val = get_time_of_day_category(time_arr)
    elev_class, _ = get_elevation_class(site_elev_arr, stn_elev_arr)
    col_idx = get_col_index(tod_val, elev_class)
    asp = get_aspect_class(aspect_arr)
    
    # Initialize output
    cor_vals = np.zeros(result_shape, dtype=np.int16)
    
    # Daytime processing
    day_mask = np.atleast_1d(is_daytime)
    if day_mask.size == 1:
        day_mask = np.full(result_shape, day_mask.item(), dtype=bool)
    
    if np.any(day_mask):
        month_code = get_month_group(month)
        shade = get_shade_class(cc_arr)
        slp = get_slope_class(slope_arr, shade)
        day_row = get_day_row_index(asp, slp, shade)
        
        # Select correct table based on month group
        if month_code == 1:
            table = ROTH_DEAD_MC_DAY_TABLE_1
        elif month_code == 2:
            table = ROTH_DEAD_MC_DAY_TABLE_2
        elif month_code == 3:
            table = ROTH_DEAD_MC_DAY_TABLE_3
        else:
            table = None
        
        if table is not None:
            cor_vals[day_mask] = table[day_row[day_mask], col_idx[day_mask]]
    
    # Nighttime processing
    night_mask = np.atleast_1d(~is_daytime)
    if night_mask.size == 1:
        night_mask = np.full(result_shape, night_mask.item(), dtype=bool)
    
    if np.any(night_mask):
        night_row = get_night_row_index(asp)
        cor_vals[night_mask] = ROTH_DEAD_MC_NIGHT_TABLE[night_row[night_mask], col_idx[night_mask]]
    
    return cor_vals


def calc_rothermel_mc(
    wx_date: str,
    time: int,
    temp: np.ndarray,
    rh: np.ndarray,
    site_elev: np.ndarray,
    stn_elev: np.ndarray,
    aspect: np.ndarray,
    slope: np.ndarray,
    cc: np.ndarray,
) -> np.ndarray:
    """
    Calculate Dead Fine Fuel Moisture Content using Rothermel (1983) method.

    Combines reference fuel moisture with elevation/aspect/slope/time corrections.

    :param wx_date: Weather date as YYYY-MM-DD string
    :param time: Time in HHMM format (0-2400)
    :param temp: Temperature (°C)
    :param rh: Relative humidity (%)
    :param site_elev: Site elevation (m)
    :param stn_elev: Station elevation (m)
    :param aspect: Aspect (degrees 0-360)
    :param slope: Slope (%)
    :param cc: Canopy closure (%)
    :return: Rothermel moisture content (%)
    """
    # Extract month from date string
    month = wx_date.split('-')[1]  # YYYY-MM-DD format
    month_num = int(month)
    month_names = {
        1: 'January', 2: 'February', 3: 'March', 4: 'April',
        5: 'May', 6: 'June', 7: 'July', 8: 'August',
        9: 'September', 10: 'October', 11: 'November', 12: 'December'
    }
    month_name = month_names.get(month_num, 'Unknown')
    
    # Determine if daytime (0800-2000)
    is_daytime = (time >= 800) & (time < 2000)
    
    # Calculate reference and correction fuel moisture
    ref_fm = calc_reference_fm(temp, rh, is_daytime)
    cor_fm = calc_correction_fm(time, site_elev, stn_elev, aspect, slope, cc, month_name, is_daytime)
    
    # Combine to get final moisture content
    mc_roth = ref_fm + cor_fm
    
    return mc_roth

