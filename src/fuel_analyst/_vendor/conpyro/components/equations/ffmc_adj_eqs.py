"""
Apply slope and aspect adjustments to FFMC using the lookup table shown in
'FFMC terrain (slope-aspect) adjustments'.

Best-practice choice:
- Use the table directly instead of fitted equations.
- Linearly interpolate for non-integer FFMC values.
- Preserve the original slope classes and aspect quadrants from the table.

Inputs can be scalars or NumPy-broadcastable arrays.
"""

import numpy as np
from typing import Union

_FFMC_GRID = np.arange(80.0, 98.0, 1.0)
_SLOPE_LABELS = (
    '1-15%',
    '16-30%',
    '31-45%',
    '46-60%',
    '61-75%',
)
_ASPECT_LABELS = ('N', 'E', 'S', 'W')

# Table shape: [slope_class, aspect_class, ffmc_index]
# FFMC index corresponds to 80..97 inclusive.
_FFMC_ADJ_TABLE = np.array([
    [  # 1-15% slope
        [78, 79, 80, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96],  # N
        [79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96],  # E
        [82, 83, 84, 85, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98],  # S
        [80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97],  # W
    ],
    [  # 16-30% slope
        [77, 78, 79, 80, 81, 82, 83, 84, 85, 87, 88, 89, 90, 91, 92, 93, 94, 95],  # N
        [78, 79, 80, 81, 82, 83, 84, 85, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96],  # E
        [82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 92, 93, 94, 95, 96, 97, 98],  # S
        [80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97],  # W
    ],
    [  # 31-45% slope
        [74, 75, 76, 78, 79, 80, 81, 82, 83, 85, 86, 87, 88, 89, 91, 91, 92, 93],  # N
        [77, 78, 79, 80, 81, 82, 83, 84, 86, 87, 88, 89, 90, 91, 92, 93, 93, 95],  # E
        [83, 84, 85, 86, 87, 88, 89, 90, 91, 91, 92, 93, 94, 95, 96, 97, 98, 99],  # S
        [81, 82, 83, 84, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97],  # W
    ],
    [  # 46-60% slope
        [72, 73, 74, 75, 76, 77, 78, 80, 82, 83, 84, 86, 87, 88, 90, 91, 92, 94],  # N
        [76, 77, 78, 79, 80, 81, 82, 83, 85, 86, 87, 88, 89, 90, 92, 93, 94, 95],  # E
        [84, 85, 85, 87, 88, 89, 90, 90, 91, 92, 93, 93, 94, 95, 96, 97, 98, 99],  # S
        [81, 82, 83, 84, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97],  # W
    ],
    [  # 61-75% slope
        [72, 73, 74, 75, 76, 77, 78, 80, 82, 83, 84, 86, 87, 88, 90, 91, 92, 94],  # N
        [76, 77, 78, 79, 80, 81, 82, 83, 85, 86, 87, 88, 89, 90, 92, 93, 94, 95],  # E
        [84, 85, 85, 87, 88, 89, 90, 90, 91, 92, 93, 93, 94, 95, 96, 97, 98, 99],  # S
        [81, 82, 83, 84, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97],  # W
    ],
], dtype=np.float64)


def _as_broadcast_arrays(
        ffmc: Union[int, float, np.ndarray],
        slope: Union[int, float, np.ndarray],
        aspect: Union[int, float, np.ndarray]
) -> tuple[np.ndarray, np.ndarray, np.ndarray, bool]:
    """
    Broadcast inputs to a common shape so that element-wise operations can be
    applied across all three arrays simultaneously.

    :param ffmc: Fine Fuel Moisture Code value(s). Scalar or array.
    :param slope: Terrain slope in percent. Scalar or array.
    :param aspect: Terrain aspect in degrees azimuth (0–360). Scalar or array.
    :return: A 4-tuple of (ffmc_arr, slope_arr, aspect_arr, is_scalar) where the
        first three elements are broadcast float64 arrays of the same shape and
        ``is_scalar`` is True when all inputs were zero-dimensional (scalar).
    """
    ffmc_arr, slope_arr, aspect_arr = np.broadcast_arrays(
        np.asarray(ffmc, dtype=np.float64),
        np.asarray(slope, dtype=np.float64),
        np.asarray(aspect, dtype=np.float64),
    )
    is_scalar = ffmc_arr.ndim == 0
    return ffmc_arr, slope_arr, aspect_arr, is_scalar


def _aspect_to_index(aspect: np.ndarray) -> np.ndarray:
    """
    Convert azimuth aspect in degrees to the cardinal quadrant index used by
    the FFMC adjustment table.

    Quadrant mapping:
    - 0 (N): [315, 360) and [0, 45)
    - 1 (E): [45, 135)
    - 2 (S): [135, 225)
    - 3 (W): [225, 315)

    :param aspect: Terrain aspect in degrees azimuth (0–360). Scalar or array.
    :return: Integer index array with values in {0, 1, 2, 3} corresponding to
        the N, E, S, W quadrant classes in ``_FFMC_ADJ_TABLE``.
    """
    aspect_norm = np.mod(aspect, 360.0)
    return np.where(
        (aspect_norm >= 315.0) | (aspect_norm < 45.0),
        0,
        np.where(
            aspect_norm < 135.0,
            1,
            np.where(aspect_norm < 225.0, 2, 3),
        ),
    )


def _slope_to_index(slope: np.ndarray) -> np.ndarray:
    """
    Convert slope percentage to the slope class index used by the FFMC
    adjustment table.

    Class mapping:
    - 0: 0 < slope <= 15%  (1-15% class)
    - 1: 15 < slope <= 30% (16-30% class)
    - 2: 30 < slope <= 45% (31-45% class)
    - 3: 45 < slope <= 60% (46-60% class)
    - 4: slope > 60%       (61-75% class)

    Negative slope values are treated as 0 before binning.

    :param slope: Terrain slope in percent. Scalar or array.
    :return: Integer index array with values in {0, 1, 2, 3, 4} corresponding
        to the slope classes in ``_FFMC_ADJ_TABLE``.
    """
    slope_pos = np.maximum(slope, 0.0)
    return np.digitize(slope_pos, [15.0, 30.0, 45.0, 60.0], right=True)


def _interp_series(x: np.ndarray, series: np.ndarray) -> np.ndarray:
    """
    Linearly interpolate (or extrapolate) adjusted FFMC values along the FFMC
    axis of a pre-selected table row.

    For each element in ``x``, the two nearest grid points in ``_FFMC_GRID``
    are identified and the corresponding ``series`` values are used to perform
    linear interpolation. Values outside the grid range [80, 97] are
    extrapolated using the first or last interval respectively.

    :param x: FFMC query values. Same shape as the leading dimensions of
        ``series``.
    :param series: Adjusted FFMC values selected from ``_FFMC_ADJ_TABLE`` for
        the relevant slope and aspect class. Shape ``(..., n_ffmc)``.
    :return: Interpolated (or extrapolated) adjusted FFMC values with the same
        shape as ``x``.
    """
    idx = np.searchsorted(_FFMC_GRID, x, side='right') - 1
    idx = np.clip(idx, 0, _FFMC_GRID.size - 2)

    x0 = _FFMC_GRID[idx]
    x1 = _FFMC_GRID[idx + 1]

    y0 = np.take_along_axis(series, idx[..., None], axis=-1)[..., 0]
    y1 = np.take_along_axis(series, (idx + 1)[..., None], axis=-1)[..., 0]

    return y0 + (x - x0) * (y1 - y0) / (x1 - x0)


def adjust_ffmc_for_terrain(
        ffmc: Union[int, float, np.ndarray],
        slope: Union[int, float, np.ndarray],
        aspect: Union[int, float, np.ndarray]
) -> Union[int, float, np.ndarray]:
    """
    Adjust FFMC using the slope/aspect lookup table.

    The source table is discrete by slope class and aspect quadrant, so this
    function preserves those class boundaries and only interpolates across FFMC.

    Slope handling:
    - slope <= 0 returns the original FFMC unchanged
    - 0 < slope <= 15 uses the 1-15% class
    - 15 < slope <= 30 uses the 16-30% class
    - 30 < slope <= 45 uses the 31-45% class
    - 45 < slope <= 60 uses the 46-60% class
    - slope > 60 uses the 61-75% class

    Aspect handling:
    - N: [315, 360) and [0, 45)
    - E: [45, 135)
    - S: [135, 225)
    - W: [225, 315)

    FFMC handling:
    - Table rows are defined for FFMC 80..97.
    - Non-integer FFMC values are linearly interpolated.
    - Values outside 80..97 are linearly extrapolated using the end segments.

    Inputs may be scalars or NumPy-broadcastable arrays.

    :param ffmc: Fine Fuel Moisture Code value(s). Scalar or array.
    :param slope: Terrain slope in percent. Scalar or array.
    :param aspect: Terrain aspect in degrees azimuth (0–360). Scalar or array.
    :return: Terrain-adjusted FFMC value(s), clipped to [0, 101]. Returns a
        Python ``float`` when all inputs are scalars, otherwise a NumPy array
        with the broadcast shape of the inputs.
    """
    ffmc_arr, slope_arr, aspect_arr, is_scalar = _as_broadcast_arrays(ffmc, slope, aspect)

    slope_idx = _slope_to_index(slope_arr)
    aspect_idx = _aspect_to_index(aspect_arr)

    series = _FFMC_ADJ_TABLE[slope_idx, aspect_idx]
    ffmc_adj = _interp_series(ffmc_arr, series)

    ffmc_adj = np.where(slope_arr <= 0.0, ffmc_arr, ffmc_adj)
    ffmc_adj = np.clip(ffmc_adj, 0.0, 101.0)

    if is_scalar:
        return float(ffmc_adj)
    return ffmc_adj


__all__ = [
    'adjust_ffmc_for_terrain',
]
