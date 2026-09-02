# -*- coding: utf-8 -*-
"""
Python conversion of the official ConPyro R implementation (conpyro.R).

Converted from: conpyro_official.R
Reference:       Perrakis et al. (2023)

This module is a reference/validation implementation mirroring the logic of
the official R conpyro() function. It is not intended for production use —
see the main ConPyro Python package instead.

@author: Gregory A. Greene
"""

from __future__ import annotations

import math
import warnings
from typing import Any, Optional, Union

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Helper / coefficient loaders
# ---------------------------------------------------------------------------

def _load_coefs(csv_path: str) -> pd.DataFrame:
    """Load a coefficient CSV shipped alongside this module."""
    return pd.read_csv(csv_path)


# ---------------------------------------------------------------------------
# Moisture content sub-functions
# ---------------------------------------------------------------------------

def mc_ffmc(ffmc: float) -> float:
    """
    Convert FFMC to fine-fuel moisture content (mcFFMC, %).

    Inverse of the Van Wagner (1987) FFMC equation.

    :param ffmc: Fine Fuel Moisture Code value (80–99).
    :return: Fine-fuel moisture content (%).
    """
    return 147.2 * (101.0 - ffmc) / (59.5 + ffmc)


def mc_dmc(dmc: float) -> float:
    """
    Convert DMC to duff moisture content (mcDMC, %).

    :param dmc: Duff Moisture Code value (5–250).
    :return: Duff moisture content (%).
    """
    return 20.0 + np.exp((dmc - 244.72) / -43.43)


def mcsa_idx(
        ffmc: float,
        season: str,
        density: str,
        stand: str,
        model_mcsa: str = "corrected",
) -> int:
    """
    Derive the coefficient-table row index for the stand-adjusted moisture
    content (mcsa) model.

    :param ffmc: FFMC value.
    :param season: Season string ('spring', 'sp-su', 'summer', 'fall') or
        numeric equivalent (1, 1.5, 2, 3).
    :param density: Density string ('light', 'moderate', 'dense') or
        numeric equivalent (1, 2, 3).
    :param stand: Stand-type string ('pine', 'spruce', 'douglas-fir',
        'deciduous', 'mixedwood') or abbreviated equivalent
        ('p', 's', 'df', 'd', 'm').
    :param model_mcsa: Model variant — 'corrected' (default) or 'original'.
    :return: Integer row index into the mcsa coefficient table.
    """
    # Normalise season
    season_map = {
        "spring": 1, "sp": 1, "1": 1, 1: 1,
        "sp-su": 2, "t": 2, "1.5": 2, 1.5: 2,
        "summer": 3, "su": 3, "2": 3, 2: 3,
        "fall": 4, "f": 4, "3": 4, 3: 4,
    }
    season_code = season_map.get(
        str(season).lower().strip() if isinstance(season, str) else season
    )
    if season_code is None:
        raise ValueError(f"Unrecognised season value: {season!r}")

    # Normalise density
    density_map = {
        "light": 1, "l": 1, "1": 1, 1: 1,
        "moderate": 2, "m": 2, "2": 2, 2: 2,
        "dense": 3, "d": 3, "3": 3, 3: 3,
    }
    density_code = density_map.get(
        str(density).lower().strip() if isinstance(density, str) else density
    )
    if density_code is None:
        raise ValueError(f"Unrecognised density value: {density!r}")

    # Normalise stand
    stand_map = {
        "pine": 1, "p": 1,
        "spruce": 2, "s": 2,
        "douglas-fir": 3, "df": 3,
        "deciduous": 4, "d": 4,
        "mixedwood": 5, "m": 5,
        "mw": 5,
    }
    stand_code = stand_map.get(
        str(stand).lower().strip() if isinstance(stand, str) else stand
    )
    if stand_code is None:
        raise ValueError(f"Unrecognised stand value: {stand!r}")

    # FFMC bin (80–84 → 1, 85–89 → 2, 90–94 → 3, 95–99 → 4)
    ffmc_bin = min(int((ffmc - 80) // 5) + 1, 4)

    # Combine into a single index (matches R table structure)
    # model_mcsa selects a sub-table offset; corrected = rows 1–120, original = rows 121–240
    model_offset = 0 if model_mcsa == "corrected" else 120
    idx = model_offset + (season_code - 1) * 30 + (density_code - 1) * 10 + (stand_code - 1) * 2 + ffmc_bin
    return idx


def mcsa(
        idx: int,
        mc_ffmc_val: float,
        mc_dmc_val: float,
        coefs: pd.DataFrame,
) -> float:
    """
    Calculate stand-adjusted fine dead surface litter moisture content (mcsa, %).

    :param idx: Coefficient table row index (from :func:`mcsa_idx`).
    :param mc_ffmc_val: Fine-fuel moisture content from FFMC (%).
    :param mc_dmc_val: Duff moisture content from DMC (%).
    :param coefs: Coefficient data frame loaded from coefs_mcsa.csv.
    :return: Stand-adjusted moisture content (%).
    """
    row = coefs.iloc[idx - 1]
    return float(row["b0"] + row["b1"] * mc_ffmc_val + row["b2"] * mc_dmc_val)


# ---------------------------------------------------------------------------
# Crown fire occurrence (pCFO)
# ---------------------------------------------------------------------------

def pcfo(
        ws10: np.ndarray,
        mc: float,
        fsg: float,
        sfc: float,
        model_pcfo: int,
        coefs: pd.DataFrame,
) -> np.ndarray:
    """
    Calculate crown fire occurrence probability (pCFO) as a function of wind
    speed.

    :param ws10: 1-D array of 10-m open wind speeds (km/h).
    :param mc: Moisture content (% — either mcFFMC or mcsa).
    :param fsg: Fuel strata gap (m).
    :param sfc: Surface fuel consumption (kg/m²).
    :param model_pcfo: Model number (see :func:`conpyro`).
    :param coefs: Coefficient data frame loaded from coefs_pcfo.csv.
    :return: Array of pCFO values, same length as *ws10*.
    """
    row = coefs.loc[coefs["model"] == model_pcfo].iloc[0]
    b0 = float(row["b0"])
    b1 = float(row["b1"])
    b2 = float(row["b2"])
    b3 = float(row["b3"])
    b4 = float(row["b4"])
    b5 = float(row["b5"])

    logit = b0 + b1 * ws10 + b2 * fsg + b3 * mc + b4 * sfc + b5 * (ws10 * mc)
    return 1.0 / (1.0 + np.exp(-logit))


# ---------------------------------------------------------------------------
# Rate of spread sub-functions
# ---------------------------------------------------------------------------

_SROS_PARAMS: dict[int, tuple[float, float, float]] = {
    # model: (a, b, c) for sROS = a * (1 - exp(-b * ISI))^c  or equivalent
    # Values match Table 3 of Perrakis et al. (2023)
    1:  (0.269, 0.05039, 1.0),
    2:  (0.239, 0.05039, 1.0),
    3:  (0.323, 0.05039, 1.0),
    4:  (0.350, 0.05039, 1.0),
    12: (0.229, 0.04757, 1.0),
    13: (0.176, 0.04238, 1.0),
    20: (0.350, 0.05039, 1.0),
}

_CROS_PARAMS: dict[int, tuple[float, float, float, float]] = {
    # model: (b1, b2, b3, b4)
    1: (0.084, 0.0, -0.0028, 0.0),
    2: (0.084, 0.0,  0.0,    0.0),
    3: (0.100, 0.0,  0.0,    0.0),
}


def _isi(ws10: np.ndarray, mc: float) -> np.ndarray:
    """
    Calculate Initial Spread Index (ISI) from wind speed and moisture content.

    Follows the Canadian FWI System formulation used internally by ConPyro.

    :param ws10: Wind speed array (km/h).
    :param mc: Fine-fuel moisture content (%).
    :return: ISI array.
    """
    f_w = np.exp(0.05039 * ws10)
    f_f = 91.9 * np.exp(-0.1386 * mc) * (1.0 + mc ** 5.31 / 4.93e7)
    return 0.208 * f_w * f_f


def sros(
        ws10: np.ndarray,
        mc: float,
        sfc: float,
        model_sros: int,
) -> np.ndarray:
    """
    Calculate surface fire rate of spread (sROS, m/min).

    :param ws10: Wind speed array (km/h).
    :param mc: Moisture content (%).
    :param sfc: Surface fuel consumption (kg/m²).
    :param model_sros: sROS model number (1–4, 12, 13, 20).
    :return: sROS array (m/min).
    """
    if model_sros not in _SROS_PARAMS:
        raise ValueError(f"Unknown model_sros: {model_sros}")
    a, b, c = _SROS_PARAMS[model_sros]
    isi_vals = _isi(ws10, mc)
    return a * sfc * (1.0 - np.exp(-b * isi_vals)) ** c


def cros_a(
        ws10: np.ndarray,
        mc: float,
        cbd: float,
        model_cros: int,
) -> np.ndarray:
    """
    Calculate active crown fire rate of spread (cROS_A, m/min).

    :param ws10: Wind speed array (km/h).
    :param mc: Moisture content (%).
    :param cbd: Crown bulk density (kg/m³).
    :param model_cros: cROS model number (1, 2, or 3).
    :return: cROS_A array (m/min).
    """
    if model_cros not in _CROS_PARAMS:
        raise ValueError(f"Unknown model_cros: {model_cros}")
    b1, b2, b3, b4 = _CROS_PARAMS[model_cros]
    return (b1 * ws10 + b2 * mc + b3 * ws10 * mc + b4) * 60.0


def cac(cros_a_vals: np.ndarray, cbd: float) -> np.ndarray:
    """
    Calculate Criterion for Active Crowning (CAC).

    CAC = cROS_A / R0  where  R0 = 3.0 / CBD

    :param cros_a_vals: Active crown ROS array (m/min).
    :param cbd: Crown bulk density (kg/m³).
    :return: CAC array (dimensionless).
    """
    r0 = 3.0 / cbd
    return cros_a_vals / r0


def cros_p(cros_a_vals: np.ndarray, cac_vals: np.ndarray) -> np.ndarray:
    """
    Calculate passive crown fire rate of spread (cROS_P, m/min).

    :param cros_a_vals: Active crown ROS array (m/min).
    :param cac_vals: CAC array (dimensionless).
    :return: cROS_P array (m/min).
    """
    return cros_a_vals * cac_vals


def ros_smooth(
        pcfo_vals: np.ndarray,
        passive_crowning: np.ndarray,
        sros_vals: np.ndarray,
        cros_p_vals: Optional[np.ndarray],
        cros_a_vals: np.ndarray,
) -> np.ndarray:
    """
    Apply smooth crown fire occurrence transition between sROS, cROS_P, and
    cROS_A when ``smooth_CFO=True``.

    :param pcfo_vals: Crown fire occurrence probability array.
    :param passive_crowning: Boolean array indicating passive-crowning pixels.
    :param sros_vals: sROS array (m/min).
    :param cros_p_vals: cROS_P array (m/min), or ``None`` if no passive phase.
    :param cros_a_vals: cROS_A array (m/min).
    :return: Smoothed composite ROS array (m/min).
    """
    result = sros_vals.copy()
    if cros_p_vals is not None and np.any(passive_crowning):
        result[passive_crowning] = (
            pcfo_vals[passive_crowning] * cros_p_vals[passive_crowning]
            + (1.0 - pcfo_vals[passive_crowning]) * sros_vals[passive_crowning]
        )
    active_crowning = ~passive_crowning & (pcfo_vals >= 0.5)
    if np.any(active_crowning):
        result[active_crowning] = cros_a_vals[active_crowning]
    return result


# ---------------------------------------------------------------------------
# Main conpyro() function
# ---------------------------------------------------------------------------

def conpyro(
        ws10: Union[np.ndarray, list],
        ffmc: Union[float, list],
        fsg: Union[float, list],
        sfc: Union[float, list],
        cbd: Union[float, list],
        dmc: Union[float, None, list] = None,
        season: Union[str, None, list] = None,
        density: Union[str, None, list] = None,
        stand: Union[str, None, list] = None,
        smooth_cfo: Union[bool, list] = False,
        scenario_id: Union[str, int, None, list] = None,
        ros_output: str = "composite",
        cf_thresh: float = 0.5,
        model_mcsa: str = "corrected",
        model_pcfo: Optional[int] = None,
        model_sros: Optional[int] = None,
        model_cros: int = 1,
        coefs_mcsa_path: Optional[str] = None,
        coefs_pcfo_path: Optional[str] = None,
) -> list[dict]:
    """
    Calculate probability of crown fire occurrence (pCFO), crowning thresholds,
    and rate of spread (ROS) for one or more scenarios.

    Python equivalent of the official R ``conpyro()`` function. See
    Perrakis et al. (2023) for full methodology.

    Parameters
    ----------
    ws10 : array-like
        10-m open wind speed in km/h. Applied to all scenarios.
    ffmc : float or list of float
        Fine Fuel Moisture Code (80–99).
    fsg : float or list of float
        Fuel strata gap in metres (0.5–20).
    sfc : float or list of float
        Surface fuel consumption in kg/m² (0.1–6).
    cbd : float or list of float
        Crown bulk density in kg/m³ (0.01–0.8).
    dmc : float or list of float, optional
        Duff Moisture Code (5–250). Required for the mcsa moisture path.
    season : str or list of str, optional
        Season — one of ``{'spring', 'sp-su', 'summer', 'fall'}`` or
        numeric equivalents ``{1, 1.5, 2, 3}``. Required for the mcsa path.
    density : str or list of str, optional
        Stand density — one of ``{'light', 'moderate', 'dense'}`` or
        numeric equivalents ``{1, 2, 3}``. Required for the mcsa path.
    stand : str or list of str, optional
        Stand type — one of ``{'pine', 'spruce', 'douglas-fir', 'deciduous',
        'mixedwood'}`` or abbreviated equivalents. Required for the mcsa path.
    smooth_cfo : bool or list of bool, optional
        If ``True``, apply smooth ROS transition at crown fire onset.
        Default ``False``.
    scenario_id : str, int, or list, optional
        Unique scenario identifier(s). Auto-numbered if ``None``.
    ros_output : str, optional
        One of ``{'composite', 'sROS', 'cROS_P', 'cROS_A'}``.
        Default ``'composite'``.
    cf_thresh : float, optional
        Crown fire occurrence probability threshold. Default ``0.5``.
    model_mcsa : str, optional
        mcsa model variant — ``'corrected'`` (default) or ``'original'``.
    model_pcfo : int, optional
        pCFO model number. Default: 10 (mcF path) or 11 (mcsa path).
    model_sros : int, optional
        sROS model number. Default: 12 (mcF path) or 13 (mcsa path).
    model_cros : int, optional
        cROS model number (1, 2, or 3). Default ``1``.
    coefs_mcsa_path : str, optional
        Absolute path to ``coefs_mcsa.csv``. If ``None``, the file is
        expected alongside this module.
    coefs_pcfo_path : str, optional
        Absolute path to ``coefs_pcfo.csv``. If ``None``, the file is
        expected alongside this module.

    Returns
    -------
    list of dict
        One dict per scenario containing:

        - ``id``
        - ``mc_ffmc`` (%)
        - ``mcsa`` (%) — ``None`` when using the mcF path
        - ``ws10`` (km/h)
        - ``pcfo`` — crown fire occurrence probability array
        - ``pcfo_passive_threshold_ws10`` (km/h) — ``None`` if never passive
        - ``pcfo_active_threshold_ws10`` (km/h) — ``None`` if never active
        - ``ros`` — ROS array (m/min), content depends on *ros_output*
        - ``ros_type`` — label describing what ``ros`` contains
    """
    import os

    # ------------------------------------------------------------------
    # Resolve coefficient paths
    # ------------------------------------------------------------------
    _here = os.path.dirname(os.path.abspath(__file__))
    if coefs_mcsa_path is None:
        coefs_mcsa_path = os.path.join(_here, "coefs_mcsa.csv")
    if coefs_pcfo_path is None:
        coefs_pcfo_path = os.path.join(_here, "coefs_pcfo.csv")

    coefs_mcsa_df = _load_coefs(coefs_mcsa_path)
    coefs_pcfo_df = _load_coefs(coefs_pcfo_path)

    # ------------------------------------------------------------------
    # Coerce scalar scenario inputs to lists
    # ------------------------------------------------------------------
    def _to_list(v):
        return v if isinstance(v, (list, np.ndarray)) else [v]

    ws10 = np.asarray(_to_list(ws10), dtype=float)
    ffmc_list     = _to_list(ffmc)
    fsg_list      = _to_list(fsg)
    sfc_list      = _to_list(sfc)
    cbd_list      = _to_list(cbd)
    dmc_list      = _to_list(dmc)
    season_list   = _to_list(season)
    density_list  = _to_list(density)
    stand_list    = _to_list(stand)
    smooth_list   = _to_list(smooth_cfo)
    id_list       = _to_list(scenario_id)
    ros_out_list  = _to_list(ros_output)
    cf_thresh_list = _to_list(cf_thresh)
    model_mcsa_list = _to_list(model_mcsa)
    model_pcfo_list = _to_list(model_pcfo)
    model_sros_list = _to_list(model_sros)
    model_cros_list = _to_list(model_cros)

    # Determine number of scenarios (longest list wins, length-1 lists recycle)
    n = max(
        len(ffmc_list), len(fsg_list), len(sfc_list), len(cbd_list),
        len(dmc_list), len(season_list), len(density_list), len(stand_list),
        len(smooth_list), len(id_list),
    )

    def _recycle(lst, length):
        if len(lst) == 1:
            return lst * length
        if len(lst) != length:
            raise ValueError(
                f"All per-scenario inputs must have length 1 or {length}; "
                f"got length {len(lst)}."
            )
        return lst

    ffmc_list     = _recycle(ffmc_list, n)
    fsg_list      = _recycle(fsg_list, n)
    sfc_list      = _recycle(sfc_list, n)
    cbd_list      = _recycle(cbd_list, n)
    dmc_list      = _recycle(dmc_list, n)
    season_list   = _recycle(season_list, n)
    density_list  = _recycle(density_list, n)
    stand_list    = _recycle(stand_list, n)
    smooth_list   = _recycle(smooth_list, n)
    ros_out_list  = _recycle(ros_out_list, n)
    cf_thresh_list = _recycle(cf_thresh_list, n)
    model_mcsa_list = _recycle(model_mcsa_list, n)
    model_pcfo_list = _recycle(model_pcfo_list, n)
    model_sros_list = _recycle(model_sros_list, n)
    model_cros_list = _recycle(model_cros_list, n)

    # Auto-generate IDs
    if len(id_list) == 1 and id_list[0] is None:
        id_list = list(range(1, n + 1))
    else:
        id_list = _recycle(id_list, n)

    # ------------------------------------------------------------------
    # Per-scenario calculations
    # ------------------------------------------------------------------
    results = []

    for i in range(n):
        ffmc_val      = float(ffmc_list[i])
        fsg_val       = float(fsg_list[i])
        sfc_val       = float(sfc_list[i])
        cbd_val       = float(cbd_list[i])
        dmc_val       = dmc_list[i]
        season_val    = season_list[i]
        density_val   = density_list[i]
        stand_val     = stand_list[i]
        smooth_val    = bool(smooth_list[i]) if smooth_list[i] is not None else False
        id_val        = id_list[i]
        ros_out_val   = ros_out_list[i] if ros_out_list[i] is not None else "composite"
        cf_thresh_val = float(cf_thresh_list[i]) if cf_thresh_list[i] is not None else 0.5
        mcsa_model    = model_mcsa_list[i] if model_mcsa_list[i] is not None else "corrected"
        mcros_val     = int(model_cros_list[i]) if model_cros_list[i] is not None else 1

        # Determine moisture content path
        use_mcsa = (
            dmc_val is not None and
            season_val is not None and
            density_val is not None and
            stand_val is not None
        )
        mc_type = "mcsa" if use_mcsa else "mcF"

        # Resolve model defaults
        mpcfo = model_pcfo_list[i]
        if mpcfo is None:
            mpcfo = 11 if mc_type == "mcsa" else 10
        msros = model_sros_list[i]
        if msros is None:
            msros = 13 if mc_type == "mcsa" else 12

        # Moisture content
        mc_ffmc_val = mc_ffmc(ffmc_val)
        mcsa_val = None
        if mc_type == "mcF":
            mc_val = mc_ffmc_val
        else:
            mc_dmc_val = mc_dmc(float(dmc_val))
            idx = mcsa_idx(ffmc_val, season_val, density_val, stand_val, mcsa_model)
            mcsa_val = mcsa(idx, mc_ffmc_val, mc_dmc_val, coefs_mcsa_df)
            mc_val = mcsa_val

        # pCFO
        pcfo_vals = pcfo(ws10, mc_val, fsg_val, sfc_val, int(mpcfo), coefs_pcfo_df)

        # Fire-type masks
        surface_fire    = pcfo_vals < cf_thresh_val
        cros_a_vals     = cros_a(ws10, mc_val, cbd_val, mcros_val)
        cac_vals        = cac(cros_a_vals, cbd_val)
        passive_mask    = (pcfo_vals >= cf_thresh_val) & (cac_vals < 1.0)
        active_mask     = (pcfo_vals >= cf_thresh_val) & (cac_vals >= 1.0)

        # Thresholds
        passive_thresh = float(ws10[np.argmax(passive_mask)]) if np.any(passive_mask) else None
        active_thresh  = float(ws10[np.argmax(active_mask)])  if np.any(active_mask)  else None

        # sROS and cROS_P
        sros_vals = sros(ws10, mc_val, sfc_val, int(msros))
        cros_p_vals = cros_p(cros_a_vals, cac_vals) if np.any(passive_mask) else None

        # Apply smoothing if requested
        if smooth_val:
            composite = ros_smooth(pcfo_vals, passive_mask, sros_vals, cros_p_vals, cros_a_vals)
        else:
            composite = np.where(
                surface_fire, sros_vals,
                np.where(passive_mask,
                         cros_p_vals if cros_p_vals is not None else np.nan,
                         cros_a_vals)
            )

        # Select ROS output
        ros_type = ros_out_val.lower()
        if ros_type == "composite":
            ros_out = np.round(composite, 1)
            ros_label = "Composite Rate of Spread (m/min)"
        elif ros_type == "sros":
            ros_out = np.round(sros_vals, 1)
            ros_label = "Surface Rate of Spread (m/min)"
        elif ros_type == "cros_p":
            ros_out = np.round(cros_p_vals, 1) if cros_p_vals is not None else None
            ros_label = "Passive Crowning Rate of Spread (m/min)"
        elif ros_type == "cros_a":
            ros_out = np.round(cros_a_vals, 1)
            ros_label = "Active Crowning Rate of Spread (m/min)"
        else:
            raise ValueError(f"Unknown ros_output value: {ros_out_val!r}")

        results.append({
            "id": id_val,
            "mc_ffmc": round(mc_ffmc_val, 1),
            "mcsa": round(mcsa_val, 1) if mcsa_val is not None else None,
            "ws10": ws10,
            "pcfo": np.round(pcfo_vals, 2),
            "pcfo_passive_threshold_ws10": passive_thresh,
            "pcfo_active_threshold_ws10": active_thresh,
            "ros": ros_out,
            "ros_type": ros_label,
        })

    return results

