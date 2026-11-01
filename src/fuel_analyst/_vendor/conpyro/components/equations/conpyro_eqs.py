# -*- coding: utf-8 -*-
"""
ConPyro Calculation Equations

Created on Thu Oct 16, 11:45:00 2025

@author: Gregory A. Greene
"""
__author__ = ['Gregory A. Greene']

from typing import Union, Optional
import numpy as np
from numpy import ma as mask


# ============================================================================
# MODEL PARAMETER DICTIONARIES
# ============================================================================

# Canadian Conifer Pyrometrics (CCP) Crown Fire Occurrence parameters
CFO_PARAMS_DICT = {
    1: (-3.0923, 1.2611, -0.39518, -0.06588, 2.8324, None),     # Perrakis et al. (2023) model 7
    2: (-2.4341, 1.0449, -0.37591, -0.04869, 2.1943, None),     # Perrakis et al. (2023) model 8
    3: (-4.6830, 1.3156, -0.41448, -0.06632, 1.6792, 3.2814),   # Perrakis et al. (2023) model 9
    4: (-4.0204, 1.3514, -0.43355, -0.06881, 2.8906, None),     # Perrakis et al. (2023) model 10
    5: (-3.5550, 1.4407, -0.53211, -0.07019, 2.4897, None),     # Perrakis et al. (2023) model 11
    10: (4.236, 0.357, -0.71, -4.613, -1.856, -0.331, None),    # CFIS Crown Fire Occurrence model
}

# Surface Fire Rate of Spread parameters
SROS_PARAMS_DICT = {
    # model: (a, b, c)
    1: (25, 0.035177, 1.9875),          # FBPS aggregated surface fire ROS model V4
    2: (30, 0.0232, 1.6),               # FBPS D-1 (no BE)
    3: (30, 0.08, 3),                   # FBPS C-6 (surface only, no BE)
    4: (0.015822, 0.344379, None),      # ISI2SFC.agg (Perrakis et al. 2026, model 7)
    12: (0.15, 0.12832, 5.24622),       # sl.con.ISI: default for mcFFMC
    13: (0.15, 0.09661, 3.84172),       # sl.con.isim: default for mcSA
    9: (0.01473, 0.59430, None),        # R 9c
    11: (0.15, 0.06680, 2.20254),        # R 11c
    18: (0.15, 0.07207, 2.28189),        # R 18c
    20: (120, 0.02751, 1.7),            # Perrakis gray-stage MPB-affected stand model
}

# Crown Fire Rate of Spread parameters
CROS_PARAMS_DICT = {
    1: (11.02, 0.9, 0.19, 0.17)
}


# ============================================================================
# BASIC CALCULATIONS
# ============================================================================

def calc_ff(mc_sa: np.ndarray) -> np.ndarray:
    """
    Calculate the FFMC function of the ISI equation.

    :param mc_sa: Surface Fuel Moisture Content (%)
    :return: FFMC function value
    """
    return (
        (91.9 * np.exp(-0.1386 * mc_sa)) *
        (1 + (np.power(mc_sa, 5.31) / (4.93 * np.power(10, 7))))
    )


def calc_fw(wsv: np.ndarray) -> np.ndarray:
    """
    Calculate the Wind function of the ISI equation.

    :param wsv: Effective wind speed (m/min)
    :return: Wind function value
    """
    return mask.where(wsv > 40,
                      12 * (1 - np.exp(-0.0818 * (wsv - 28))),
                      np.exp(0.05039 * wsv))


def calc_isi(fw: np.ndarray, ff: np.ndarray) -> np.ndarray:
    """
    Calculate Initial Spread Index with slope and wind.

    :param fw: Wind function
    :param ff: FFMC function
    :return: ISI value
    """
    return 0.208 * fw * ff


def calc_isz(ff: np.ndarray) -> np.ndarray:
    """
    Calculate Initial Spread Index with no slope and no wind.

    :param ff: FFMC function
    :return: ISZ value
    """
    return 0.208 * ff


def calc_bfw(wsv: np.ndarray) -> np.ndarray:
    """
    Calculate Backing Fire Wind Speed (m/min).

    :param wsv: Effective wind speed (m/min)
    :return: Backing fire wind function
    """
    return np.exp(-0.05039 * wsv)


def calc_bisi(bfw: np.ndarray, ff: np.ndarray) -> np.ndarray:
    """
    Calculate Backing Fire ISI.

    :param bfw: Backing fire wind function
    :param ff: FFMC function
    :return: Backing ISI value
    """
    return bfw * ff * 0.208


def calc_sf(slope: np.ndarray) -> np.ndarray:
    """
    Calculate the slope factor.

    :param slope: Slope steepness (%)
    :return: Slope factor
    """
    return mask.where(slope < 70,
                      np.exp(3.533 * np.power((slope / 100), 1.2)),
                      10)


def calc_r0(cbd: np.ndarray) -> np.ndarray:
    """
    Calculate critical minimum rate of spread for active crowning (R0) in m/min.
    
    R0 = MFR0 / cbd, where MFR0 is the critical mass flow rate (3 kg*m^-2*min^-1)

    :param cbd: Canopy Bulk Density (kg/m^3)
    :return: R0 value (m/min)
    """
    return 3 / cbd


def calc_cfl(cfl_ovrstry: np.ndarray) -> np.ndarray:
    """
    Calculate Canopy Fuel Load (CFL).

    :param cfl_ovrstry: Overstory Canopy Fuel Load (kg/m^2)
    :return: CFL value
    """
    return cfl_ovrstry


def calc_cfc(cfl: np.ndarray, cfb: np.ndarray) -> np.ndarray:
    """
    Calculate Canopy Fuel Consumption (CFC).

    :param cfl: Canopy Fuel Load (kg/m^2)
    :param cfb: Crown Fraction Burned
    :return: CFC value
    """
    return cfl * cfb


def calc_cfb(hros: np.ndarray, cros_a: np.ndarray) -> np.ndarray:
    """
    Calculate Crown Fraction Burned (CFB).

    :param hros: Head Fire Rate of Spread (m/min)
    :param cros_a: Active Crown Fire Rate of Spread (m/min)
    :return: CFB value (0-1)
    """
    # At zero wind the active crown estimate is zero; no crown fuel is consumed.
    denominator = mask.where(cros_a == 0, 1, cros_a)
    ratio = mask.where(cros_a == 0, 0, hros / denominator)
    return mask.clip(mask.round(ratio, 2), 0, 1)


def calc_tfc(sfc: np.ndarray, cfc: np.ndarray) -> np.ndarray:
    """
    Calculate Total Fuel Consumption (TFC).

    :param sfc: Surface Fuel Consumption (kg/m^2)
    :param cfc: Canopy Fuel Consumption (kg/m^2)
    :return: TFC value
    """
    return sfc + cfc


def calc_cfi(hros: np.ndarray, cfc: np.ndarray) -> np.ndarray:
    """
    Calculate Crown Fire Intensity (kW/m).

    :param hros: Head Fire Rate of Spread (m/min)
    :param cfc: Canopy Fuel Consumption (kg/m^2)
    :return: Crown Fire Intensity (kW/m)
    """
    return 300 * hros * cfc


def calc_sfi(hros: np.ndarray, sfc: np.ndarray) -> np.ndarray:
    """
    Calculate Surface Fire Intensity (kW/m).

    :param hros: Head Fire Rate of Spread (m/min)
    :param sfc: Surface Fuel Consumption (kg/m^2)
    :return: Surface Fire Intensity (kW/m)
    """
    return 300 * hros * sfc


def calc_hfi(hros: np.ndarray, tfc: np.ndarray) -> np.ndarray:
    """
    Calculate Head Fire Intensity (kW/m).

    :param hros: Head Fire Rate of Spread (m/min)
    :param tfc: Total Fuel Consumption (kg/m^2)
    :return: Head Fire Intensity (kW/m)
    """
    return mask.where(hros >= 0,
                      300 * hros * tfc,
                      np.nan)


def calc_cac(cros_a: np.ndarray, r0: np.ndarray) -> np.ndarray:
    """
    Calculate Criterion for Active Crowning (CAC).
    
    CAC = Rc / R0, where Rc is predicted active crown fire ROS, and R0 is minimum rate of spread

    :param cros_a: Active Crown Fire Rate of Spread (m/min)
    :param r0: Critical minimum rate of spread (m/min)
    :return: CAC value (unitless)
    """
    return cros_a / r0


def calc_accel_param(cfb: np.ndarray, density: np.ndarray) -> np.ndarray:
    """
    Calculate the acceleration parameter.

    :param cfb: Crown Fraction Burned
    :param density: Fuel density type code
    :return: Acceleration parameter
    """
    accel_param = np.full_like(cfb, np.nan, dtype=np.float64)
    
    # Mask for open fuel types (density=1) - fixed acceleration parameter
    fixed_accel_mask = np.isin(density, [1])
    accel_param = mask.where(fixed_accel_mask, 0.115, accel_param)

    # Mask for closed fuel types - compute acceleration parameter
    variable_accel_mask = ~fixed_accel_mask
    accel_param = mask.where(variable_accel_mask,
                             0.115 - 18.8 * np.power(cfb, 2.5) * np.exp(-8 * cfb),
                             accel_param)
    return accel_param


def calc_inverted_wind_aspect(wd: np.ndarray, aspect: np.ndarray) -> tuple:
    """
    Invert/flip wind direction and slope aspect by 180 degrees.

    :param wd: Wind direction (degrees)
    :param aspect: Slope aspect (degrees)
    :return: Tuple of (inverted_wind_direction, inverted_aspect)
    """
    wd_inv = (wd + 180) % 360
    aspect_inv = (aspect + 180) % 360
    return wd_inv, aspect_inv


def calc_wsv_raz(
        ws: np.ndarray,
        wd: np.ndarray,
        isf: np.ndarray,
        ff: np.ndarray,
        aspect: np.ndarray
) -> tuple:
    """
    Calculate the effective wind speed (wsv) and the net effective wind direction (raz).

    :param ws: Wind speed (m/s)
    :param wd: Wind direction (degrees)
    :param isf: Initial Spread Index with slope/wind
    :param ff: FFMC function
    :param aspect: Slope aspect (degrees)
    :return: Tuple of (effective_wind_speed, net_effective_wind_direction)
    """
    # Calculate the slope equivalent wind speed (for lower wind speeds)
    with np.errstate(divide='ignore', invalid='ignore'):
        wse1 = (1 / 0.05039) * np.log(isf / (0.208 * ff))
        wse2 = mask.where(
            isf < (0.999 * 2.496 * ff),
            28 - (1 / 0.0818) * np.log(1 - (isf / (2.496 * ff))),
            112.45
        )
        wse = mask.where(wse1 <= 40, wse1, wse2)

    # Calculate vector magnitude in x and y directions
    wsx = (ws * np.sin(np.radians(wd))) + (wse * np.sin(np.radians(aspect)))
    wsy = (ws * np.cos(np.radians(wd))) + (wse * np.cos(np.radians(aspect)))
    wsv = np.sqrt(np.square(wsx) + np.square(wsy))

    # Calculate the net effective wind direction (RAZ)
    with np.errstate(invalid='ignore'):
        raz = np.degrees(np.arccos(np.clip(wsy / wsv, -1, 1)))
        raz = mask.where(wsx < 0, 360 - raz, raz)
    
    return wsv, raz


# ============================================================================
# SURFACE RATE OF SPREAD (SROS) CALCULATIONS
# ============================================================================

SROS_MODEL_IDS = frozenset((1, 2, 3, 4, 9, 11, 12, 13, 16, 17, 18, 19, 20, 21))
SROS_ALIASES = {"9c": 9, "11c": 11, "18c": 18, "r20": 21}


def normalize_sros_model(value) -> mask.MaskedArray:
    """Normalize labels and numeric grids without per-cell numeric iteration."""
    raw = mask.atleast_1d(mask.asarray(value))
    missing = mask.getmaskarray(raw).copy()
    result = np.zeros(raw.shape, dtype=np.int16)
    if raw.dtype.kind in "biuf":
        missing |= ~np.isfinite(raw.data)
        valid = ~missing
        numbers = raw.data[valid]
        if not np.all(np.isin(numbers, tuple(SROS_MODEL_IDS))):
            raise ValueError("Unknown or fractional surface ROS model ID")
        result[valid] = numbers.astype(np.int16)
        return mask.array(result, mask=missing)

    def parse(item):
        if isinstance(item, (str, np.str_)):
            label = item.strip().lower()
            if label in SROS_ALIASES:
                return SROS_ALIASES[label]
            if label.isdigit():
                code = int(label)
            else:
                raise ValueError(f"Unknown surface ROS model: {item!r}")
        else:
            if not np.isfinite(item):
                return None
            code = int(item)
            if code != item:
                raise ValueError(f"Surface ROS model must be an integer or label: {item!r}")
        if code not in SROS_MODEL_IDS:
            raise ValueError(f"Unknown surface ROS model: {item!r}")
        return code

    if raw.dtype.kind in "US":
        for item in np.unique(raw.data[~missing]):
            result[(raw.data == item) & ~missing] = parse(item)
    else:
        # Heterogeneous object arrays are uncommon; preserve their scalar types.
        for index in np.ndindex(raw.shape):
            if not missing[index]:
                code = parse(raw.data[index])
                if code is None:
                    missing[index] = True
                else:
                    result[index] = code
    return mask.array(result, mask=missing)


def calc_sros(isi, sfc, sros_model, sros_param_a, sros_param_b, sros_param_c,
              *, wsv=None, stand_type=None, mc_sa=None) -> np.ndarray:
    """Surface ROS in m/min; wind-based models require wind in km/h."""
    models = normalize_sros_model(sros_model)
    inputs = [mask.asarray(x, dtype=float) for x in
              (isi, sfc, models, sros_param_a, sros_param_b, sros_param_c)]
    values = np.broadcast_arrays(*[x.data for x in inputs])
    index, fuel, codes, a, b, c = values
    invalid = np.zeros(index.shape, dtype=bool)
    for x in inputs[:3]:
        invalid |= np.broadcast_to(mask.getmaskarray(x), index.shape)
    # A masked fitted parameter invalidates only models that consume it.
    for parameter, used_by in zip(inputs[3:], (
            (1, 2, 3, 4, 9, 11, 12, 13, 18, 20),
            (1, 2, 3, 4, 9, 11, 12, 13, 18, 20),
            (1, 2, 3, 11, 12, 13, 18, 20))):
        invalid |= (np.broadcast_to(mask.getmaskarray(parameter), index.shape)
                    & np.isin(codes, used_by))
    result = np.full(index.shape, np.nan)

    def context(value, name, selected):
        if value is None:
            raise ValueError(f"{name} is required for the selected surface ROS model")
        value = mask.asarray(value)
        data = np.broadcast_to(value.data, index.shape)
        invalid[selected] |= np.broadcast_to(mask.getmaskarray(value), index.shape)[selected]
        return data[selected]

    for code in np.unique(codes[~invalid]):
        selected = (codes == code) & ~invalid
        x = index[selected]
        if code in (1, 2, 3, 20):
            result[selected] = a[selected] * (1 - np.exp(-b[selected] * x))**c[selected]
        elif code == 4:
            result[selected] = a[selected] * np.clip(x, 0, 25)**2 + b[selected] * fuel[selected]
        elif code == 9:
            result[selected] = a[selected] * x**2 + b[selected] * np.sqrt(fuel[selected])
        elif code in (11, 12, 13, 18):
            offset = 13 if code in (12, 13) else 10
            value = (a[selected] * x + offset) * (1 - np.exp(-b[selected] * x))**c[selected]
            if code == 18:
                stand = context(stand_type, "stand_type", selected)
                value = np.maximum(value + 2.69568 * (stand == 2)
                                   - .76090 * np.isin(stand, [1, 3]), 0)
            result[selected] = value
        elif code in (16, 17):
            wind = context(wsv, "wsv", selected)
            moisture = context(mc_sa, "mc_sa", selected)
            scale, power, decay = {16: (.39813, 1.91399, .31551),
                                   17: (.29629, 1.69839, .23260)}[code]
            result[selected] = scale * wind**power * np.exp(-decay * moisture)
        elif code == 19:
            result[selected] = .11771 * x
        elif code == 21:
            result[selected] = .2 * context(wsv, "wsv", selected)
    return mask.masked_invalid(mask.array(result, mask=invalid))


def calc_bros(bisi, sfc, sros_model, sros_param_a, sros_param_b, sros_param_c,
              *, stand_type=None) -> np.ndarray:
    """Backing ROS; wind-only models have no defined backing extension."""
    models = normalize_sros_model(sros_model)
    unsupported = np.isin(models.data, [16, 17, 21])
    # Mask unsupported entries before dispatch so missing wind context is not used.
    supported = mask.array(models.data, mask=mask.getmaskarray(models) | unsupported)
    return calc_sros(bisi, sfc, supported, sros_param_a, sros_param_b, sros_param_c,
                     stand_type=stand_type)


def calc_isf(
        isz: np.ndarray,
        sf: np.ndarray,
        sfc: np.ndarray,
        sros_model: np.ndarray,
        sros_param_a: np.ndarray,
        sros_param_b: np.ndarray,
        sros_param_c: np.ndarray
) -> np.ndarray:
    """
    Calculate Initial Spread Index with slope and wind.

    Supports root-finding for complex model forms.

    :param isz: ISI with no slope/wind
    :param sf: Slope factor
    :param sfc: Surface Fuel Consumption
    :param sros_model: SROS model code
    :param sros_param_a: Parameter a for SROS equation
    :param sros_param_b: Parameter b for SROS equation
    :param sros_param_c: Parameter c for SROS equation
    :return: ISF value
    """
    isf = np.full_like(isz, np.nan, dtype=np.float64)

    # Terrain inversion is defined only for the original Python model set.
    supported = np.isin(mask.asarray(sros_model).compressed(), [1, 2, 3, 4, 12, 13, 20])
    if not np.all(supported):
        raise ValueError("Selected surface model has no terrain inversion")
    selected = np.isin(sros_model, [1, 2, 3, 20])
    if np.any(selected):
        a, b, c = (p[selected] for p in (sros_param_a, sros_param_b, sros_param_c))
        rsz = a * (1 - np.exp(-b * isz[selected]))**c
        rsf = rsz * sf[selected]
        with np.errstate(invalid="ignore", divide="ignore"):
            isf[selected] = mask.where((rsf < a) & (rsf > 0),
                -np.log(1 - (rsf / a)**(1 / c)) / b, mask.masked)

    selected = sros_model == 4
    if np.any(selected):
        a, b = sros_param_a[selected], sros_param_b[selected]
        rsz = a * mask.clip(isz[selected], 0, 25)**2 + b * sfc[selected]
        rsf = rsz * sf[selected]
        with np.errstate(invalid="ignore"):
            target = (rsf - b * sfc[selected]) / a
            isf[selected] = mask.where(target >= 0, np.sqrt(target), mask.masked)

    # Root-finding models (form c) [12, 13]
    model_list = [12, 13]
    mask_form_c = np.isin(sros_model, model_list)
    if np.any(mask_form_c):
        def solve_isf(rsf_target, _a, _b, _c):
            """
            Invert  rsf = (a*x + 13) * (1 - exp(-b*x))^c  for x, given rsf.

            Uses Newton-Raphson with analytic derivative and a bisection
            guard to guarantee convergence.  Typically converges in 6–10
            iterations vs. ~60 for pure bisection.
            """
            rsf_target = np.asarray(mask.array(rsf_target).filled(np.nan), dtype=np.float64).ravel()
            _a = np.asarray(mask.array(_a).filled(np.nan), dtype=np.float64).ravel()
            _b = np.asarray(mask.array(_b).filled(np.nan), dtype=np.float64).ravel()
            _c = np.asarray(mask.array(_c).filled(np.nan), dtype=np.float64).ravel()

            if _a.size == 1:
                _a = np.broadcast_to(_a, rsf_target.shape)
            if _b.size == 1:
                _b = np.broadcast_to(_b, rsf_target.shape)
            if _c.size == 1:
                _c = np.broadcast_to(_c, rsf_target.shape)

            roots = np.full_like(rsf_target, np.nan, dtype=np.float64)

            valid = (
                np.isfinite(rsf_target) & np.isfinite(_a) & np.isfinite(_b) & np.isfinite(_c) &
                (rsf_target >= 0) & (_a > 0) & (_b > 0) & (_c > 0)
            )
            if not np.any(valid):
                return mask.masked_array(roots, mask=np.isnan(roots))

            r = rsf_target[valid]
            a = _a[valid]
            b = _b[valid]
            c = _c[valid]

            def forward(x):
                q = np.clip(1.0 - np.exp(-b * x), 0.0, 1.0)
                return (a * x + 13.0) * np.power(q, c)

            def forward_deriv(x):
                """Compute f(x) and f'(x) together to avoid redundant exp()."""
                e = np.exp(-b * x)
                q = np.clip(1.0 - e, 1e-30, 1.0)  # small floor avoids 0^(c-1)
                qc = np.power(q, c)
                lin = a * x + 13.0
                f = lin * qc
                # f'(x) = a * q^c  +  (a*x + 13) * c * q^(c-1) * b * e
                fp = a * qc + lin * c * np.power(q, c - 1.0) * b * e
                return f, fp

            # --- Bracket: lo=0, hi expanded until f(hi) >= r ---
            lo = np.zeros_like(r)
            hi = np.maximum(25.0, r / np.maximum(a, 1e-9) + 1.0)
            for _ in range(20):
                f_hi = forward(hi) - r
                need_expand = f_hi < 0
                if not np.any(need_expand):
                    break
                hi[need_expand] *= 2.0

            # --- Hybrid Newton-Raphson / bisection ---
            # Newton gives quadratic convergence in well-behaved regions.
            # For very small RSF targets the function is extremely flat
            # near x=0 (derivative ≈ 0), so Newton can overshoot; we
            # always tighten the bracket and fall back to bisection when
            # Newton makes no progress or escapes.
            x = 0.5 * (lo + hi)
            for _ in range(50):
                # Convergence: bracket width relative to position
                width = hi - lo
                converged = width < 1e-12 * (1.0 + np.abs(x))
                if np.all(converged):
                    break

                f_x, fp_x = forward_deriv(x)
                residual = f_x - r

                # Tighten bracket first (always, regardless of Newton)
                go_left = residual >= 0
                hi[go_left] = x[go_left]
                lo[~go_left] = x[~go_left]

                # Attempt Newton step
                newton_ok = np.abs(fp_x) > 1e-30
                x_new = np.where(newton_ok,
                                 x - residual / np.where(newton_ok, fp_x, 1.0),
                                 0.5 * (lo + hi))

                # Fall back to bisection if Newton escapes bracket
                escaped = (x_new <= lo) | (x_new >= hi) | ~np.isfinite(x_new)
                x_new[escaped] = 0.5 * (lo[escaped] + hi[escaped])

                x = x_new

            roots[valid] = np.where(np.isfinite(x) & (x >= 0), x, np.nan)
            return mask.masked_array(roots, mask=np.isnan(roots))

        param_a_c = sros_param_a[mask_form_c]
        param_b_c = sros_param_b[mask_form_c]
        param_c_c = sros_param_c[mask_form_c]
        agg_rsz = ((param_a_c * isz[mask_form_c] + 13) *
                   np.power(1 - np.exp(-param_b_c * isz[mask_form_c]), param_c_c))
        rsf = agg_rsz * sf[mask_form_c]
        isf[mask_form_c] = solve_isf(rsf, param_a_c, param_b_c, param_c_c)

    return isf


# ============================================================================
# CROWN RATE OF SPREAD (CROS) CALCULATIONS
# ============================================================================

def calc_cros_a(
        wsv: np.ndarray,
        cbd: np.ndarray,
        mc_sa: np.ndarray,
        cros_model: np.ndarray,
        cros_param_b1: np.ndarray,
        cros_param_b2: np.ndarray,
        cros_param_b3: np.ndarray,
        cros_param_b4: np.ndarray
) -> np.ndarray:
    """
    Calculate Active Crown Fire Rate of Spread (m/min).

    Supports two models:
    - Model 1: Cruz et al. (2005)
    - Model 2: Alexander and Cruz (2019)

    :param wsv: Effective wind speed (m/min)
    :param cbd: Canopy Bulk Density (kg/m^3)
    :param mc_sa: Moisture Content Spread Available
    :param cros_model: CROS model code
    :param cros_param_b1: Parameter b1
    :param cros_param_b2: Parameter b2
    :param cros_param_b3: Parameter b3
    :param cros_param_b4: Parameter b4
    :return: Active Crown Fire Rate of Spread (m/min)
    """
    cros_a = np.full_like(wsv, np.nan, dtype=np.float64)

    # Model 1: Cruz et al. (2005)
    mask_model1 = cros_model == 1
    if np.any(mask_model1):
        effm_mod = -0.4812 + 3.8842 * np.log(mc_sa[mask_model1])
        cros_a[mask_model1] = (
            cros_param_b1[mask_model1] *
            np.power(wsv[mask_model1], cros_param_b2[mask_model1]) *
            np.power(cbd[mask_model1], cros_param_b3[mask_model1]) *
            np.exp(-cros_param_b4[mask_model1] * effm_mod)
        )

    # Model 2: Alexander and Cruz (2019)
    mask_model2 = cros_model == 2
    if np.any(mask_model2):
        cros_a[mask_model2] = 0.084 * wsv[mask_model2] * 1000 / 60

    mask_model3 = cros_model == 3
    if np.any(mask_model3):
        cros_a[mask_model3] = 0.1 * wsv[mask_model3] * 1000 / 60

    invalid = (mask.getmaskarray(wsv) | mask.getmaskarray(cbd)
               | mask.getmaskarray(mc_sa) | mask.getmaskarray(cros_model))
    return mask.masked_invalid(mask.array(cros_a, mask=invalid))


def calc_cros_p(cros_a: np.ndarray, cac: np.ndarray) -> np.ndarray:
    """
    Calculate Passive Crown Fire Rate of Spread (m/min).

    :param cros_a: Active Crown Fire Rate of Spread (m/min)
    :param cac: Criterion for Active Crowning
    :return: Passive Crown Fire Rate of Spread (m/min)
    """
    return cros_a * np.exp(-cac)


def calc_cros(cros_a: np.ndarray, cros_p: np.ndarray, cac: np.ndarray) -> np.ndarray:
    """
    Calculate final Crown Fire Rate of Spread (m/min).

    Selects between active and passive based on CAC value.

    :param cros_a: Active Crown Fire Rate of Spread (m/min)
    :param cros_p: Passive Crown Fire Rate of Spread (m/min)
    :param cac: Criterion for Active Crowning
    :return: Crown Fire Rate of Spread (m/min)
    """
    return mask.where(cac >= 1, cros_a, cros_p)


def calc_ros_smooth(sros, cros_p, cros_a, cfo_prob, cac, *, wind_axis=None) -> np.ndarray:
    """R composite smoothing, with explicit scenario grouping.

    None treats every element as a separate single-wind scenario. An integer
    axis groups winds; the passive-phase decision never crosses other axes.
    """
    arrays = [mask.asarray(x, dtype=float) for x in (sros, cros_p, cros_a, cfo_prob, cac)]
    values = np.broadcast_arrays(*[x.data for x in arrays])
    invalid = np.zeros(values[0].shape, dtype=bool)
    for x in arrays:
        invalid |= np.broadcast_to(mask.getmaskarray(x), invalid.shape)
    surface, passive_ros, active_ros, probability, criterion = values
    invalid |= ~np.isfinite(surface + passive_ros + active_ros + probability + criterion)
    passive = (probability >= .5) & (criterion < 1) & ~invalid
    if wind_axis is None:
        has_passive = passive
    else:
        if isinstance(wind_axis, (bool, np.bool_)) or not isinstance(wind_axis, (int, np.integer)):
            raise TypeError("wind_axis must be an integer or None")
        if not -surface.ndim <= wind_axis < surface.ndim:
            raise ValueError("wind_axis is outside the input dimensions")
        has_passive = np.any(passive, axis=wind_axis, keepdims=True)
    target = np.where(has_passive, passive_ros, active_ros)
    blended = surface * (1 - probability) + target * probability
    active = (probability >= .5) & (criterion >= 1)
    composite = np.where(has_passive & active, active_ros, blended)
    return mask.array(composite, mask=invalid)


def calc_cros_a_smooth(sros: np.ndarray, cros_a: np.ndarray, cfo_prob: np.ndarray) -> np.ndarray:
    """
    Calculate smoothed Active Crown Fire Rate of Spread.

    :param sros: Surface Fire Rate of Spread (m/min)
    :param cros_a: Active Crown Fire Rate of Spread (m/min)
    :param cfo_prob: Crown Fire Occurrence probability
    :return: Smoothed Active Crown Fire Rate of Spread (m/min)
    """
    return (sros * (1.0 - cfo_prob)) + (cros_a * cfo_prob)


def calc_cros_p_smooth(sros: np.ndarray, cros_p: np.ndarray, cfo_prob: np.ndarray) -> np.ndarray:
    """
    Calculate smoothed Passive Crown Fire Rate of Spread.

    :param sros: Surface Fire Rate of Spread (m/min)
    :param cros_p: Passive Crown Fire Rate of Spread (m/min)
    :param cfo_prob: Crown Fire Occurrence probability
    :return: Smoothed Passive Crown Fire Rate of Spread (m/min)
    """
    return (sros * (1.0 - cfo_prob)) + (cros_p * cfo_prob)


def calc_cros_smooth(cros_a_smooth: np.ndarray, cros_p_smooth: np.ndarray, cac: np.ndarray) -> np.ndarray:
    """
    Calculate smoothed Crown Fire Rate of Spread.

    :param cros_a_smooth: Smoothed Active Crown Fire Rate of Spread (m/min)
    :param cros_p_smooth: Smoothed Passive Crown Fire Rate of Spread (m/min)
    :param cac: Criterion for Active Crowning
    :return: Smoothed Crown Fire Rate of Spread (m/min)
    """
    return mask.where(cac >= 1, cros_a_smooth, cros_p_smooth)


def calc_hros(sros: np.ndarray, cros: np.ndarray, cfo_prob: np.ndarray) -> np.ndarray:
    """
    Calculate Head Fire Rate of Spread (m/min).

    Selects between surface and crown based on CFO probability.

    :param sros: Surface Fire Rate of Spread (m/min)
    :param cros: Crown Fire Rate of Spread (m/min)
    :param cfo_prob: Crown Fire Occurrence probability
    :return: Head Fire Rate of Spread (m/min)
    """
    return mask.where(cfo_prob >= 0.5, cros, sros)


def calc_hros_smooth(sros_smooth: np.ndarray, cros_smooth: np.ndarray, cfo_prob: np.ndarray) -> np.ndarray:
    """
    Calculate smoothed Head Fire Rate of Spread (m/min).

    :param sros_smooth: Smoothed Surface Fire Rate of Spread (m/min)
    :param cros_smooth: Smoothed Crown Fire Rate of Spread (m/min)
    :param cfo_prob: Crown Fire Occurrence probability
    :return: Smoothed Head Fire Rate of Spread (m/min)
    """
    return mask.where(cfo_prob >= 0.5, cros_smooth, sros_smooth)


# ============================================================================
# CROWN FIRE OCCURRENCE (CFO) CALCULATIONS
# ============================================================================

def calc_logit(
        wsv: np.ndarray,
        fsg: np.ndarray,
        mc_sa: np.ndarray,
        sfc: np.ndarray,
        cfo_model: np.ndarray,
        cfi_param_b0: np.ndarray,
        cfi_param_b1: np.ndarray,
        cfi_param_b2: np.ndarray,
        cfi_param_b3: np.ndarray,
        cfi_param_b4: np.ndarray,
        cfi_param_b5: np.ndarray
) -> np.ndarray:
    """
    Calculate the logit for crown fire occurrence.

    Supports multiple model types with different parameter configurations.

    :param wsv: Effective wind speed (m/min)
    :param fsg: Fire Spread Gradient
    :param mc_sa: Moisture Content Spread Available
    :param sfc: Surface Fuel Consumption
    :param cfo_model: CFO model code
    :param cfi_param_b0: Crown Fire Occurrence parameter 0
    :param cfi_param_b1: Crown Fire Occurrence parameter 1
    :param cfi_param_b2: Crown Fire Occurrence parameter 2
    :param cfi_param_b3: Crown Fire Occurrence parameter 3
    :param cfi_param_b4: Crown Fire Occurrence parameter 4
    :param cfi_param_b5: Crown Fire Occurrence parameter 5
    :return: Logit value
    """
    logit = np.full_like(wsv, np.nan, dtype=np.float64)

    # Models 1, 2, 4, 5
    mask_other = np.isin(cfo_model, [1, 2, 4, 5])
    if np.any(mask_other):
        logit_vals = (
            cfi_param_b0[mask_other] +
            cfi_param_b1[mask_other] * wsv[mask_other] +
            cfi_param_b2[mask_other] * np.power(fsg[mask_other], 1.5) +
            cfi_param_b3[mask_other] * mc_sa[mask_other] * wsv[mask_other] +
            cfi_param_b4[mask_other] * np.log(sfc[mask_other])
        )
        logit[mask_other] = logit_vals

    # Models 3 and 10: SFC-dependent models
    sfc_lt1_mask = (sfc < 1.0)
    sfc_lt2_mask = ~sfc_lt1_mask & (sfc < 2.0)
    sfc_ge2_mask = (sfc >= 2.0)

    # Model 3
    mask_model3 = cfo_model == 3
    if np.any(mask_model3):
        sfc0 = np.zeros_like(sfc[mask_model3])
        sfc1 = np.zeros_like(sfc[mask_model3])
        sfc0[sfc_lt2_mask[mask_model3]] = 1
        sfc1[sfc_ge2_mask[mask_model3]] = 1

        logit_vals = (
            cfi_param_b0[mask_model3] +
            cfi_param_b1[mask_model3] * wsv[mask_model3] +
            cfi_param_b2[mask_model3] * np.power(fsg[mask_model3], 1.5) +
            cfi_param_b3[mask_model3] * mc_sa[mask_model3] * wsv[mask_model3] +
            cfi_param_b4[mask_model3] * sfc0 +
            cfi_param_b5[mask_model3] * sfc1
        )
        logit[mask_model3] = logit_vals

    # Model 10 (CFIS)
    mask_model10 = cfo_model == 10
    if np.any(mask_model10):
        sfc0 = np.zeros_like(sfc[mask_model10])
        sfc1 = np.zeros_like(sfc[mask_model10])
        sfc0[sfc_lt1_mask[mask_model10]] = 1
        sfc1[sfc_lt2_mask[mask_model10]] = 1

        logit_vals = (
            cfi_param_b0[mask_model10] +
            cfi_param_b1[mask_model10] * wsv[mask_model10] +
            cfi_param_b2[mask_model10] * fsg[mask_model10] +
            cfi_param_b3[mask_model10] * sfc0 +
            cfi_param_b4[mask_model10] * sfc1 +
            cfi_param_b5[mask_model10] * mc_sa[mask_model10]
        )
        logit[mask_model10] = logit_vals

    return logit.astype(np.float64)


def calc_cfo_prob(logit: np.ndarray) -> np.ndarray:
    """
    Calculate the probability of crown fire occurrence.

    :param logit: Logit value
    :return: Crown Fire Occurrence probability (0-1)
    """
    return mask.where(
        np.isfinite(logit),
        mask.exp(logit) / (1.0 + mask.exp(logit)),
        mask.masked
    )


# ============================================================================
# FIRE TYPE DETERMINATION
# ============================================================================

def calc_fire_type(cfo_prob: np.ndarray, cac: np.ndarray) -> np.ndarray:
    """
    Determine fire type based on CFO probability and CAC.

    Fire types:
    - 1: Surface Fire (cfo_prob < 0.5)
    - 2: Passive Crown Fire (cfo_prob >= 0.5 and cac < 1)
    - 3: Active Crown Fire (cfo_prob >= 0.5 and cac >= 1)

    :param cfo_prob: Crown Fire Occurrence probability
    :param cac: Criterion for Active Crowning
    :return: Fire type array (1, 2, or 3)
    """
    fire_type = np.empty(cfo_prob.shape, dtype=object)

    mask_surface = cfo_prob < 0.5
    mask_passive = ~mask_surface & (cac < 1)
    mask_active = ~mask_surface & ~mask_passive

    fire_type[mask_surface] = 1  # Surface Fire
    fire_type[mask_passive] = 2  # Passive Crown Fire
    fire_type[mask_active] = 3   # Active Crown Fire

    return fire_type
