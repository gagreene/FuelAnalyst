# -*- coding: utf-8 -*-
"""
Shared validation and conversion utilities for ConPyro component inputs.

Provides helper functions to reduce repetitive type-checking, masked-array
conversion, and clipping boilerplate across component ``_verify_inputs_*``
methods.

Created on Wed Apr 2, 2026

@author: Gregory A. Greene
"""

from typing import Optional, Tuple, Union
import numpy as np
from numpy import ma as mask


def validate_numeric(
        value,
        name: str,
        *,
        clip_min: Optional[float] = None,
        clip_max: Optional[float] = None,
        use_isfinite: bool = True,
        ref_array: Optional[mask.MaskedArray] = None,
) -> mask.MaskedArray:
    """
    Validate a numeric input parameter, convert it to a masked array, and
    optionally clip its values.

    This consolidates the repetitive pattern used across all component
    ``_verify_inputs_*`` methods::

        if not isinstance(value, (int, float, np.ndarray)):
            raise TypeError(...)
        if isinstance(value, np.ndarray):
            value = mask.array(value, mask=<mask_fn>(value))
        else:
            value = mask.array([value], mask=<mask_fn>([value]))
        value = mask.clip(value, lo, hi)

    :param value: The raw input value (scalar or array).
    :param name: Parameter name (used in error messages).
    :param clip_min: Lower bound for clipping (``None`` = no lower bound).
    :param clip_max: Upper bound for clipping (``None`` = no upper bound).
    :param use_isfinite: If ``True``, mask non-finite values (NaN and Inf).
        If ``False``, mask only NaN values (matching the ``np.isnan`` pattern
        used for some weather variables).
    :param ref_array: If provided and *value* is a scalar, broadcast to this
        shape using ``np.full_like`` instead of wrapping in a length-1 array.
        Used by components that need scalar inputs to match a pre-existing
        reference array shape.
    :return: Validated and converted masked array.
    :raises TypeError: If *value* is not ``int``, ``float``, or ``np.ndarray``.
    """
    if not isinstance(value, (int, float, np.ndarray)):
        raise TypeError(f'{name} must be int, float, or numpy ndarray data types')

    if isinstance(value, np.ndarray):
        if use_isfinite:
            result = mask.array(value, mask=~np.isfinite(value))
        else:
            result = mask.array(value, mask=np.isnan(value))
    else:
        if ref_array is not None:
            filled = np.full_like(ref_array, value, dtype=np.float64)
            if use_isfinite:
                result = mask.array(filled, mask=~np.isfinite(ref_array))
            else:
                result = mask.array(filled, mask=np.isnan(filled))
        else:
            if use_isfinite:
                result = mask.array([value], mask=~np.isfinite([value]))
            else:
                result = mask.array([value], mask=np.isnan([value]))

    if clip_min is not None or clip_max is not None:
        result = mask.clip(result, clip_min, clip_max)

    return result

