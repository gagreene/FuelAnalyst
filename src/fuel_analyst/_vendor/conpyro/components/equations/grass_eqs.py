"""FBP O1 inputs and curing; owner-selected bounds are explicit here.

Equations: cffdrs/cffdrs_r at 4d20a303, rate_of_spread.r (FCFDG 1992,
Eq. 36; Wotton et al. 2009 curing Eqs. 35a/b), and fine_fuel_moisture_code.r.
See docs/SURFACE_ROS_MODELS.md for intentional input-policy differences.
"""

import numpy as np
from numpy import ma


def normalize_grass_input(value: np.ndarray, name: str) -> np.ndarray:
    """Preserve missingness and apply grass-specific finite input rules."""
    if name not in {"ffmc", "ws", "gfl", "gcf", "slope"}:
        raise ValueError(f"Unknown grass input {name!r}")
    if value is None:
        raise ValueError(f"{name} is required for the selected surface ROS model")
    raw = ma.atleast_1d(ma.asarray(value, dtype=float))
    missing = ma.getmaskarray(raw) | ~np.isfinite(raw.data)
    data = np.where(missing, 0.0, raw.data).copy()
    if name in {"ffmc", "ws", "slope"}:
        maximum = {"ffmc": 101.0, "ws": 300.0, "slope": 200.0}[name]
        data[(data < 0) | (data > maximum)] = 0.0
    elif name == "gfl":
        data[data < 0] = 0.35
        data = np.minimum(data, 100.0)
    else:
        data[data <= 0] = 0.1
        data[data > 100] = 95.0
    return ma.array(data, mask=missing)


def calc_grass_curing_factor(gcf: np.ndarray) -> np.ndarray:
    """Curing percentage multiplier, with the published 58.8% breakpoint."""
    value = normalize_grass_input(gcf, "gcf")
    return ma.where(
        value < 58.8, 0.005 * (ma.exp(0.061 * value) - 1), 0.176 + 0.02 * (value - 58.8)
    )


def calc_grass_mc_ffmc(ffmc: np.ndarray) -> np.ndarray:
    """Exact FBP FFMC moisture conversion, separate from forest 147.2."""
    value = normalize_grass_input(ffmc, "ffmc")
    return (250.0 * 59.5 / 101.0) * (101.0 - value) / (59.5 + value)
