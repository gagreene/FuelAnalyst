"""
ConPyro Calculation Equations

Created on Thu Oct 16, 11:45:00 2025

@author: Gregory A. Greene
"""

__author__ = ["Gregory A. Greene"]

import numpy as np
from numpy import ma as mask

from . import cheney_eqs, grass_eqs

# ============================================================================
# MODEL PARAMETER DICTIONARIES
# ============================================================================

# Canadian Conifer Pyrometrics (CCP) Crown Fire Occurrence parameters
CFO_PARAMS_DICT = {
    1: (
        -3.0923,
        1.2611,
        -0.39518,
        -0.06588,
        2.8324,
        None,
    ),  # Perrakis et al. (2023) model 7
    2: (
        -2.4341,
        1.0449,
        -0.37591,
        -0.04869,
        2.1943,
        None,
    ),  # Perrakis et al. (2023) model 8
    3: (
        -4.6830,
        1.3156,
        -0.41448,
        -0.06632,
        1.6792,
        3.2814,
    ),  # Perrakis et al. (2023) model 9
    4: (
        -4.0204,
        1.3514,
        -0.43355,
        -0.06881,
        2.8906,
        None,
    ),  # Perrakis et al. (2023) model 10
    5: (
        -3.5550,
        1.4407,
        -0.53211,
        -0.07019,
        2.4897,
        None,
    ),  # Perrakis et al. (2023) model 11
    10: (
        4.236,
        0.357,
        -0.71,
        -4.613,
        -1.856,
        -0.331,
        None,
    ),  # CFIS Crown Fire Occurrence model
}

# Surface Fire Rate of Spread parameters
SROS_PARAMS_DICT = {
    # model: (a, b, c, d, e); unused parameters are None.
    # Existing a/b/c meanings are retained. For oblique-asymptote models,
    # a is the paper's fixed m=0.15; intercepts remain 10 (AGG) or 13 (BOCON).
    # Model 18 uses d/e for the paper's PPDF/DECID offsets.
    # Wind models use a * wind**b * exp(c * moisture), including signed c.
    1: (25, 0.035177, 1.9875, None, None),
    2: (30, 0.0232, 1.6, None, None),
    3: (30, 0.08, 3, None, None),
    4: (0.015822, 0.344379, None, None, None),
    9: (0.01473, 0.59430, None, None, None),  # Paper/R 9c
    11: (0.15, 0.06680, 2.20254, None, None),  # Paper/R 11c
    12: (0.15, 0.12832, 5.24622, None, None),  # Standard ISI
    13: (0.15, 0.09661, 3.84172, None, None),  # Stand-adjusted ISI
    16: (0.39813, 1.91399, -0.31551, None, None),  # mcFFMC
    17: (0.29629, 1.69839, -0.23260, None, None),  # mcSA
    18: (0.15, 0.07207, 2.28189, 2.69568, -0.76090),  # Paper/R 18c
    19: (0.11771, None, None, None, None),  # Stand-adjusted ISI
    21: (120, 0.02751, 1.7, None, None),  # Gray-stage MPB
    30: (190, 0.0310, 1.4, None, None),  # FBP O1a, ST-X-3 Eq. 36 / Table 6
    31: (250, 0.0350, 1.7, None, None),  # FBP O1b, ST-X-3 Eq. 36 / Table 6
}

# Crown Fire Rate of Spread parameters
CROS_PARAMS_DICT = {1: (11.02, 0.9, 0.19, 0.17)}

# ============================================================================
# BASIC CALCULATIONS
# ============================================================================


def calc_ff(mc_sa: np.ndarray) -> np.ndarray:
    """
    Calculate the FFMC function of the ISI equation.

    :param mc_sa: Surface Fuel Moisture Content (%)
    :return: FFMC function value
    """
    return (91.9 * np.exp(-0.1386 * mc_sa)) * (
        1 + (np.power(mc_sa, 5.31) / (4.93 * np.power(10, 7)))
    )


def calc_fw(wsv: np.ndarray) -> np.ndarray:
    """
    Calculate the Wind function of the ISI equation.

    :param wsv: Effective 10-m open wind speed (km/h)
    :return: Wind function value
    """
    return mask.where(
        wsv > 40,
        12 * (1 - np.exp(-0.0818 * (np.maximum(wsv, 40) - 28))),
        np.exp(0.05039 * np.minimum(wsv, 40)),
    )


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
    Calculate the dimensionless backing-fire wind function.

    :param wsv: Effective 10-m open wind speed (km/h)
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
    return mask.where(slope < 70, np.exp(3.533 * np.power((slope / 100), 1.2)), 10)


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


def calc_sfi(hros: np.ndarray, sfc: np.ndarray, *, heat_yield=None) -> np.ndarray:
    """
    Calculate Surface Fire Intensity (kW/m).

    :param hros: Head Fire Rate of Spread (m/min)
    :param sfc: Surface Fuel Consumption (kg/m^2)
    :param heat_yield: Optional kJ/kg; None preserves original arithmetic/dtype.
    :return: Surface Fire Intensity (kW/m)
    """
    if heat_yield is None:
        return 300 * hros * sfc
    return (mask.asarray(heat_yield) / 60.) * hros * sfc


def calc_hfi(hros: np.ndarray, tfc: np.ndarray, *, sfc=None, cfc=None, heat_yield=None) -> np.ndarray:
    """
    Calculate Head Fire Intensity (kW/m).

    :param hros: Head Fire Rate of Spread (m/min)
    :param tfc: Total Fuel Consumption (kg/m^2)
    :param sfc: Surface consumption, required with a custom heat yield.
    :param cfc: Crown consumption, required with a custom heat yield; never
        recovered by subtracting surface consumption from the total.
    :param heat_yield: Surface kJ/kg; crowns retain 18,000. None preserves the
        original total-consumption expression, including its dtype.
        Custom heat follows NumPy promotion: a float64 heat_yield array with
        float32 inputs returns float64.
    :return: Head Fire Intensity (kW/m)
    """
    if heat_yield is None:
        return mask.where(hros >= 0, 300 * hros * tfc, np.nan)
    if sfc is None or cfc is None:
        raise ValueError('sfc and cfc are required to split surface/crown heat yield')
    return mask.where(hros >= 0, hros * (mask.asarray(heat_yield) / 60. * sfc + 300 * cfc), np.nan)


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
    accel_param = mask.where(
        variable_accel_mask,
        0.115 - 18.8 * np.power(cfb, 2.5) * np.exp(-8 * cfb),
        accel_param,
    )
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
    ws: np.ndarray, wd: np.ndarray, isf: np.ndarray, ff: np.ndarray, aspect: np.ndarray
) -> tuple:
    """
    Calculate the effective wind speed (wsv) and the net effective wind direction (raz).

    :param ws: 10-m open wind speed (km/h)
    :param wd: Direction the wind blows toward (degrees clockwise from north)
    :param isf: Slope-equivalent Initial Spread Index at zero ambient wind
    :param ff: FFMC function
    :param aspect: Upslope direction (degrees clockwise from north)
    :return: Effective wind speed in km/h and spread azimuth in degrees.
        Calm or cancelling vectors retain wd as a deterministic fallback.
    """
    # Calculate the slope equivalent wind speed (for lower wind speeds)
    with np.errstate(divide="ignore", invalid="ignore"):
        wse1 = (1 / 0.05039) * np.log(isf / (0.208 * ff))
        wse2 = mask.where(
            isf < (0.999 * 2.496 * ff),
            28 - (1 / 0.0818) * np.log(1 - (isf / (2.496 * ff))),
            112.45,
        )
        wse = mask.maximum(mask.where(wse1 <= 40, wse1, wse2), 0)

    # Calculate vector magnitude in x and y directions
    wsx = (ws * np.sin(np.radians(wd))) + (wse * np.sin(np.radians(aspect)))
    wsy = (ws * np.cos(np.radians(wd))) + (wse * np.cos(np.radians(aspect)))
    wsv = mask.masked_invalid(np.hypot(wsx, wsy), copy=False)
    # Clipping/capping intermediate values must not hide invalid source inputs.
    invalid = mask.getmaskarray(wsv).copy()
    for value in (ws, wd, isf, ff, aspect):
        invalid |= np.broadcast_to(
            mask.getmaskarray(value) | ~np.isfinite(mask.getdata(value)), wsv.shape
        )
    wsv = mask.array(wsv, mask=invalid, copy=False)
    calm = wsv <= 1e-12 * mask.maximum(1, np.abs(ws) + np.abs(wse))
    wsv = mask.where(calm, 0, wsv)

    # Calculate the net effective wind direction (RAZ)
    raz = mask.where(calm, wd % 360, np.degrees(np.arctan2(wsx, wsy)) % 360)

    return wsv, raz


# ============================================================================
# SURFACE RATE OF SPREAD (SROS) CALCULATIONS
# ============================================================================

GRASS_SROS_IDS = (30, 31)
CHENEY_SROS_IDS = cheney_eqs.CHENEY_SROS_IDS
SROS_MODEL_IDS = frozenset((1, 2, 3, 4, 9, 11, 12, 13, 16, 17, 18, 19, 20, 21, 30, 31, 32, 33, 34))
SROS_ALIASES = {"9c": 9, "11c": 11, "18c": 18, "r20": 20,
                "cheney_natural": 32, "cheney_grazed": 33, "cheney_eaten_out": 34}


def calc_sros(
    isi: np.ndarray,
    sfc: np.ndarray,
    sros_model: np.ndarray,
    sros_param_a: np.ndarray | None,
    sros_param_b: np.ndarray | None,
    sros_param_c: np.ndarray | None,
    sros_param_d: np.ndarray | None = None,
    sros_param_e: np.ndarray | None = None,
    *,
    wsv: np.ndarray | None = None,
    stand_type: np.ndarray | None = None,
    mc_sa: np.ndarray | None = None,
    mc_ffmc: np.ndarray | None = None,
    gcf: np.ndarray | None = None,
    temp: np.ndarray | None = None,
    rh: np.ndarray | None = None,
    cheney_mf_override: np.ndarray | None = None,
    _cheney_mf: np.ndarray | None = None,
) -> np.ndarray:
    """Surface ROS in m/min; model 16 needs mc_ffmc, model 17 needs mc_sa.

    Wind is in km/h and moisture is percent. Omitted d/e use the model 18c
    registry offsets for compatibility with existing six-argument callers.
    Unused coefficient slots can be supplied as None or NaN.
    The caller supplies standard ISI for 12/18c/30/31 and stand-adjusted ISI for
    9c/11c/13/19; this function does not infer the basis of the supplied index.

    :param isi: Dimensionless head-fire Initial Spread Index. Use standard ISI
        for models 12/18c/30/31 and stand-adjusted ISI for 9c/11c/13/19. Required as a
        shape/mask input even for legacy wind-based models that do not use its
        value. Cheney 32–34 uses its shape only and ignores the unused ISI mask.
    :param sfc: Surface fuel consumption in kg/m². Used numerically by models
        4 and 9c; also participates in output broadcasting and input masking
        except for O1 (30/31), which does not consume its value or mask.
    :param sros_model: Model ID or label, scalar or array. Labels 9c, 11c and
        18c map to IDs 9, 11 and 18. Model 20 (alias r20) is the wind heuristic;
        model 21 is the gray-stage MPB model; 30/O1a and 31/O1b are FBP grass.
    :param sros_param_a: Model-specific coefficient: asymptote amplitude for
        1/2/3/21, squared-ISI coefficient for 4/9c, oblique-asymptote slope for
        11c/12/13/18c, wind scale for 16/17, or linear ISI coefficient for 19.
    :param sros_param_b: Exponential ISI rate for 1/2/3/11c/12/13/18c/21,
        SFC-term coefficient for 4/9c, or wind exponent for 16/17. Unused by 19/20.
    :param sros_param_c: Curve exponent for 1/2/3/11c/12/13/18c/21, or signed
        moisture coefficient for 16/17 in exp(c * moisture). Unused by 4/9c/19/20.
    :param sros_param_d: Model 18c's additive PPDF offset in m/min, applied to
        stand code 2 only. Defaults to the model 18c registry value when None.
    :param sros_param_e: Model 18c's additive deciduous/mixedwood offset in
        m/min, applied to stand codes 1/3 only. Defaults to the registry when None.
    :param wsv: Wind speed in km/h, required by models 16/17/20/32–34. Broadcastable
        to the shape established by the positional inputs. Cheney consumes
        nonnegative effective WSV with no finite upper cap.
    :param stand_type: Numeric stand codes, required by 18c: 1 deciduous,
        2 Douglas-fir/PPDF, 3 mixedwood, 4 pine, 5 spruce. Broadcastable to output.
    :param mc_sa: Stand-adjusted fine fuel moisture content in percent,
        required by model 17. Broadcastable to output.
    :param gcf: Percent curing, required for O1a/O1b and Cheney. Missing consumed
        values remain masked. O1 finite <=0 becomes 0.1 and >100 becomes 95;
        Cheney curing outside 20–100 becomes NaN with a warning.
    :param mc_ffmc: FFMC-derived fine fuel moisture content in percent,
        required by model 16. Broadcastable to output.
    :param temp: Celsius temperature for Cheney AM60 moisture.
    :param rh: Percent RH for Cheney AM60, clipped 0–100 with a warning.
    :param cheney_mf_override: Optional standing moisture (%), taking precedence
        per cell; missing cells use AM60. Shared Mf clips 2–24 with a warning.
    :param _cheney_mf: Internal class-supplied normalized moisture, avoiding
        repeated weather normalization. Not a public initializer input.
    :return: Masked array of head-fire surface ROS in m/min. Positional inputs
        broadcast together; masks on fitted coefficients affect only models and
        stands that use them. Consumed nonfinite coefficients are masked before
        flooring; nonfinite results are masked. Model 18c is floored
        at zero; model 4 retains its ISI cap of 25.
    :raises ValueError: If a model is unknown, required context is missing,
        or input shapes cannot broadcast as required.
    """
    models = normalize_sros_model(sros_model)
    inputs = [
        mask.asarray(x, dtype=float)
        for x in (
            isi,
            sfc,
            models,
            sros_param_a,
            sros_param_b,
            sros_param_c,
            SROS_PARAMS_DICT[18][3] if sros_param_d is None else sros_param_d,
            SROS_PARAMS_DICT[18][4] if sros_param_e is None else sros_param_e,
        )
    ]
    values = np.broadcast_arrays(*[x.data for x in inputs])
    index, fuel, codes, a, b, c, d, e = values
    invalid = np.zeros(index.shape, dtype=bool)
    for position, x in enumerate(inputs[:3]):
        missing = np.broadcast_to(mask.getmaskarray(x), index.shape)
        if position == 0:
            missing = missing & ~np.isin(codes, CHENEY_SROS_IDS)
        if position == 1:
            missing = missing & ~np.isin(codes, GRASS_SROS_IDS + CHENEY_SROS_IDS)
        invalid |= missing
    # A masked/nonfinite fitted parameter invalidates only cells that consume it.
    for parameter, used_by, stand_codes in zip(
        inputs[3:],
        (
            (1, 2, 3, 4, 9, 11, 12, 13, 16, 17, 18, 19, 21, 30, 31),
            (1, 2, 3, 4, 9, 11, 12, 13, 16, 17, 18, 21, 30, 31),
            (1, 2, 3, 11, 12, 13, 16, 17, 18, 21, 30, 31),
            (18,),
            (18,),
        ),
        (None, None, None, (2,), (1, 3)),
    ):
        parameter_invalid = ~np.isfinite(parameter.data)
        if parameter.mask is not mask.nomask:
            parameter_invalid |= mask.getmaskarray(parameter)
        if not np.any(parameter_invalid):
            continue
        consumes = np.isin(codes, used_by)
        if stand_codes is not None:
            if not np.any(consumes):
                continue
            if stand_type is None:
                continue  # The model 18 branch reports missing stand context.
            stands = np.broadcast_to(mask.asarray(stand_type).data, index.shape)
            consumes &= np.isin(stands, stand_codes)
        invalid |= np.broadcast_to(parameter_invalid, index.shape) & consumes
    result = np.full(index.shape, np.nan)
    all_cheney = np.isin(codes, CHENEY_SROS_IDS) & ~invalid
    if np.any(all_cheney):
        def cheney_context(value):
            return None if value is None else np.broadcast_to(mask.asarray(value, dtype=float).filled(np.nan), index.shape)[all_cheney]
        if wsv is None or gcf is None:
            raise ValueError('wsv and gcf are required for Cheney surface spread')
        moisture = (cheney_context(_cheney_mf) if _cheney_mf is not None else
                    cheney_eqs.calc_cheney_moisture(cheney_context(temp), cheney_context(rh), cheney_context(cheney_mf_override)))
        # One Cheney batch keeps wind validation and warnings aggregated rather
        # than repeating normalization for each selected model.
        result[all_cheney] = cheney_eqs.calc_cheney_sros(
            cheney_context(wsv), moisture, cheney_context(gcf), codes[all_cheney])

    def context(value, name, selected):
        if value is None:
            raise ValueError(f"{name} is required for the selected surface ROS model")
        value = mask.asarray(value)
        data = np.broadcast_to(value.data, index.shape)
        invalid[selected] |= np.broadcast_to(mask.getmaskarray(value), index.shape)[
            selected
        ]
        return data[selected]

    for code in np.unique(codes[~invalid & ~all_cheney]):
        selected = (codes == code) & ~invalid
        x = index[selected]
        if code in (1, 2, 3, 21):
            result[selected] = (
                a[selected] * (1 - np.exp(-b[selected] * x)) ** c[selected]
            )
        elif code == 4:
            result[selected] = (
                a[selected] * np.clip(x, 0, 25) ** 2 + b[selected] * fuel[selected]
            )
        elif code == 9:
            result[selected] = a[selected] * x**2 + b[selected] * np.sqrt(
                fuel[selected]
            )
        elif code in (11, 12, 13, 18):
            offset = 13 if code in (12, 13) else 10
            value = (a[selected] * x + offset) * (1 - np.exp(-b[selected] * x)) ** c[
                selected
            ]
            if code == 18:
                stand = context(stand_type, "stand_type", selected)
                for parameter, indicator in (
                    (d, stand == 2),
                    (e, np.isin(stand, [1, 3])),
                ):
                    if np.any(indicator):
                        value[indicator] += parameter[selected][indicator]
                value = np.maximum(value, 0)
            result[selected] = value
        elif code in (16, 17):
            wind = context(wsv, "wsv", selected)
            moisture = (
                context(mc_ffmc, "mc_ffmc", selected)
                if code == 16
                else context(mc_sa, "mc_sa", selected)
            )
            result[selected] = (
                a[selected] * wind ** b[selected] * np.exp(c[selected] * moisture)
            )
        elif code == 19:
            result[selected] = a[selected] * x
        elif code == 20:
            result[selected] = 0.2 * context(wsv, "wsv", selected)
        elif code in GRASS_SROS_IDS:
            curing = context(None if gcf is None else grass_eqs.calc_grass_curing_factor(gcf),
                             "gcf", selected)
            result[selected] = curing * a[selected] * (1 - np.exp(-b[selected] * x)) ** c[selected]
    return mask.masked_invalid(mask.array(result, mask=invalid))


def calc_bros(
    bisi: np.ndarray,
    sfc: np.ndarray,
    sros_model: np.ndarray,
    sros_param_a: np.ndarray | None,
    sros_param_b: np.ndarray | None,
    sros_param_c: np.ndarray | None,
    sros_param_d: np.ndarray | None = None,
    sros_param_e: np.ndarray | None = None,
    *,
    wsv: np.ndarray | None = None,
    surface_ros: np.ndarray | None = None,
    stand_type: np.ndarray | None = None,
    gcf: np.ndarray | None = None,
    temp: np.ndarray | None = None,
    rh: np.ndarray | None = None,
    cheney_mf_override: np.ndarray | None = None,
    _cheney_mf: np.ndarray | None = None,
) -> np.ndarray:
    """Calculate backing surface ROS in m/min using a backing spread index.

    Models 16, 17 and 20 have no defined backing extension and return masked
    entries. Other models use the same equations and coefficients as calc_sros.
    Unused coefficient slots can be supplied as None or NaN.

    :param bisi: Dimensionless backing Initial Spread Index. Calculate from
        mcFFMC for models 12/18c and mcSA for 9c/11c/13/19.
    :param sfc: Surface fuel consumption in kg/m², used by models 4/9c.
        Also participates in output broadcasting and input masking.
    :param sros_model: Model ID or label, scalar or array, as in calc_sros.
        Model 21 selects MPB; model 20 and alias r20 have masked backing outputs.
    :param sros_param_a: Asymptote amplitude for 1/2/3/21, squared-ISI
        coefficient for 4/9c, asymptote slope for 11c/12/13/18c, or linear
        coefficient for 19. Unused for models without a backing extension.
    :param sros_param_b: Exponential ISI rate for 1/2/3/11c/12/13/18c/21,
        or SFC-term coefficient for 4/9c. Unused by 19 and unsupported models.
    :param sros_param_c: Curve exponent for 1/2/3/11c/12/13/18c/21.
        Unused by 4/9c/19 and models without a backing extension.
    :param sros_param_d: Model 18c's additive PPDF offset in m/min for stand
        code 2. None selects the registry default.
    :param sros_param_e: Model 18c's additive deciduous/mixedwood offset in
        m/min for stand codes 1/3. None selects the registry default.
    :param stand_type: Numeric stand codes, required by 18c: 1 deciduous,
        2 Douglas-fir/PPDF, 3 mixedwood, 4 pine, 5 spruce. Broadcastable to output.
    :param wsv: Effective wind in km/h, required for Cheney focal-ellipse
        backing. Pass zero explicitly for calm conditions; unused otherwise.
        Must broadcast to the output grid established by positional inputs.
    :param surface_ros: Optional precomputed head surface ROS from calc_sros,
        in m/min, for Cheney backing. This bypasses head/weather recomputation.
        Negative values become missing with a counted warning. Do not supply
        crown-composite HROS. It must come from the same calculation and per-cell
        WSV, and broadcast to the grid established by positional inputs. This
        association cannot be verified without recomputing the head. Unused by
        other backing equations.
    :param temp: Celsius temperature for Cheney AM60 moisture when not overridden.
    :param rh: Percent relative humidity for Cheney AM60.
    :param cheney_mf_override: Optional standing moisture (%) overriding AM60.
    :param _cheney_mf: Internal normalized class moisture shared with head spread.
        Cheney backing uses its head rate and selected ellipse, not backing ISI.
    :return: Masked array of backing surface ROS in m/min. Positional inputs
        broadcast together. Coefficient masks/nonfinite values apply only where consumed;
        unsupported models and nonfinite results are masked.
    :raises ValueError: If a model is unknown, required stand context is
        missing, or input shapes cannot broadcast as required.
    """
    models = normalize_sros_model(sros_model)
    unsupported = np.isin(models.data, [16, 17, 20])
    # Mask unsupported entries before dispatch so missing wind context is not used.
    cheney_selected = np.isin(models.data, CHENEY_SROS_IDS) & ~mask.getmaskarray(models)
    if np.any(cheney_selected) and wsv is None:
        raise ValueError('wsv is required for Cheney backing spread; pass 0 explicitly for calm')
    supported = mask.array(models.data, mask=mask.getmaskarray(models) | unsupported | cheney_selected)
    result = calc_sros(
        bisi,
        sfc,
        supported,
        sros_param_a,
        sros_param_b,
        sros_param_c,
        sros_param_d,
        sros_param_e,
        stand_type=stand_type,
        gcf=gcf,
    )
    if np.any(cheney_selected):
        shape = result.shape
        selected = np.broadcast_to(cheney_selected, shape)
        def selected_context(value):
            return None if value is None else np.broadcast_to(mask.asarray(value, dtype=float).filled(np.nan), shape)[selected]
        if surface_ros is not None:
            backing = cheney_eqs.calc_cheney_bros_from_surface_ros(
                selected_context(surface_ros), selected_context(wsv))
        else:
            mf = (selected_context(_cheney_mf) if _cheney_mf is not None else
                  cheney_eqs.calc_cheney_moisture(selected_context(temp), selected_context(rh), selected_context(cheney_mf_override)))
            if gcf is None:
                raise ValueError('gcf is required for Cheney backing spread')
            backing = cheney_eqs.calc_cheney_bros(
                mf, selected_context(gcf), wsv=selected_context(wsv),
                model=np.broadcast_to(models.data, shape)[selected])
        result[selected] = mask.masked_invalid(backing)
    return result


def calc_isf(
    isz: np.ndarray,
    sf: np.ndarray,
    sfc: np.ndarray,
    sros_model: np.ndarray,
    sros_param_a: np.ndarray,
    sros_param_b: np.ndarray,
    sros_param_c: np.ndarray,
    sros_param_d: np.ndarray | None = None,
    sros_param_e: np.ndarray | None = None,
    *,
    stand_type: np.ndarray | None = None,
) -> np.ndarray:
    """
    Calculate Initial Spread Index with slope and wind.

    Supports root-finding for complex model forms.

    :param isz: ISI with no slope/wind
    :param sf: Slope factor
    :param sfc: Surface Fuel Consumption; retained for compatibility, unused
        by the base-only model 4/9c slope inverses.
    :param sros_model: SROS model code
    :param sros_param_a: Parameter a for SROS equation
    :param sros_param_b: Parameter b for SROS equation
    :param sros_param_c: Parameter c for SROS equation
    Model 18c uses a ConPyro-specific base-only slope convention: invert
    SF * g(ISZ), then apply the unscaled stand offset and zero floor in the
    forward ROS equation. All stand categories therefore share the inverse.
    Model 4 likewise leaves its SFC term unscaled: ISF=clip(ISZ,0,25)*sqrt(SF),
    masked when it exceeds 25. Its SFC coefficient remains in forward ROS only.
    Model 9c uses ISF=ISZ*sqrt(SF), leaving b*sqrt(SFC) unscaled in forward ROS.
    Its equivalent wind is independent of moisture and SFC; unlike model 4,
    model 9c has no ISI-25 cap. These are ConPyro-only terrain conventions.

    :param sros_param_d: Accepted for compatibility; unused by the slope inverse.
        The PPDF offset is applied only in forward ROS calculations.
    :param sros_param_e: Accepted for compatibility; unused by the slope inverse.
        The deciduous offset is applied only in forward ROS calculations.
    :param stand_type: Accepted for compatibility; unused by the slope inverse.
        Forward model 18c still requires numeric stand context.
    :return: ISF value
    """
    isf = mask.masked_all(np.shape(isz), dtype=np.float64)
    model_codes = mask.getdata(sros_model)
    valid_model = ~mask.getmaskarray(sros_model)

    # Wind-only models have no zero-wind slope-equivalent inverse.
    supported = np.isin(
        mask.asarray(sros_model).compressed(), [1, 2, 3, 4, 9, 11, 12, 13, 18, 19, 21, 30, 31]
    )
    if not np.all(supported):
        raise ValueError("Selected surface model has no terrain inversion")
    selected = np.isin(model_codes, [1, 2, 3, 21, 30, 31]) & valid_model
    if np.any(selected):
        # Boolean indexing owns these arrays; masking cannot mutate caller inputs.
        a, b, c, baseline, slope_factor = (
            mask.masked_invalid(value[selected], copy=False)
            for value in (sros_param_a, sros_param_b, sros_param_c, isz, sf)
        )
        with np.errstate(invalid="ignore", divide="ignore", over="ignore"):
            rsz = a * (1 - np.exp(-b * baseline)) ** c
            rsf = mask.masked_invalid(rsz * slope_factor, copy=False)
            # GLC-X-10 (2009), Eqs. 41a/b: finite inverse at saturation.
            isf[selected] = -mask.log(mask.maximum(1 - (rsf / a) ** (1 / c), 0.01)) / b

    selected = (model_codes == 4) & valid_model
    if np.any(selected):
        a = sros_param_a[selected]
        with np.errstate(invalid="ignore", divide="ignore"):
            # ConPyro base-only convention: a cancels, while b*SFC is unscaled.
            # Retain validation/masking of the base coefficient defining the curve.
            baseline = mask.clip(isz[selected], 0, 25)
            multiplier = np.sqrt(sf[selected])
            inverse = baseline * multiplier
            # Forward model 4 is capped at ISI 25: larger targets are unreachable.
            # Compare in baseline space to avoid roundoff masking exact cap points.
            isf[selected] = mask.where(
                np.isfinite(a)
                & (a > 0)
                & (inverse >= 0)
                & (baseline <= 25 / multiplier),
                mask.minimum(inverse, 25),
                mask.masked,
            )

    selected = (model_codes == 9) & valid_model
    if np.any(selected):
        a, baseline, slope_factor = (
            mask.masked_invalid(value[selected], copy=False)
            for value in (sros_param_a, isz, sf)
        )
        with np.errstate(invalid="ignore", over="ignore"):
            # Invert SF*a*ISZ² + b*sqrt(SFC); the additive term stays unscaled.
            inverse = mask.masked_invalid(baseline * mask.sqrt(slope_factor))
            isf[selected] = mask.where((a > 0) & (inverse >= 0), inverse, mask.masked)

    selected = (model_codes == 19) & valid_model
    if np.any(selected):
        a = sros_param_a[selected]
        with np.errstate(invalid="ignore", divide="ignore"):
            isf[selected] = a * isz[selected] * sf[selected] / a

    # Oblique-asymptote models share the same monotone numerical inverse.
    model_list = [11, 12, 13, 18]
    mask_form_c = np.isin(model_codes, model_list) & valid_model
    if np.any(mask_form_c):

        def solve_isf(rsf_target, _a, _b, _c, _intercept):
            """
            Invert rsf = (a*x + intercept) * (1 - exp(-b*x))^c.

            Uses Newton-Raphson with analytic derivative and a bisection
            guard to guarantee convergence.  Typically converges in 6–10
            iterations vs. ~60 for pure bisection.
            """
            rsf_target = np.asarray(
                mask.array(rsf_target).filled(np.nan), dtype=np.float64
            ).ravel()
            _a = np.asarray(mask.array(_a).filled(np.nan), dtype=np.float64).ravel()
            _b = np.asarray(mask.array(_b).filled(np.nan), dtype=np.float64).ravel()
            _c = np.asarray(mask.array(_c).filled(np.nan), dtype=np.float64).ravel()
            _intercept = np.asarray(_intercept, dtype=np.float64).ravel()

            if _a.size == 1:
                _a = np.broadcast_to(_a, rsf_target.shape)
            if _b.size == 1:
                _b = np.broadcast_to(_b, rsf_target.shape)
            if _c.size == 1:
                _c = np.broadcast_to(_c, rsf_target.shape)

            roots = np.full_like(rsf_target, np.nan, dtype=np.float64)

            valid = (
                np.isfinite(rsf_target)
                & np.isfinite(_a)
                & np.isfinite(_b)
                & np.isfinite(_c)
                & (rsf_target >= 0)
                & (_a > 0)
                & (_b > 0)
                & (_c > 0)
            )
            if not np.any(valid):
                return mask.masked_array(roots, mask=np.isnan(roots))

            r = rsf_target[valid]
            a = _a[valid]
            b = _b[valid]
            c = _c[valid]
            intercept = _intercept[valid]

            def forward(x):
                q = np.clip(1.0 - np.exp(-b * x), 0.0, 1.0)
                return (a * x + intercept) * np.power(q, c)

            def forward_deriv(x):
                """Compute f(x) and f'(x) together to avoid redundant exp()."""
                e = np.exp(-b * x)
                q = np.clip(1.0 - e, 1e-30, 1.0)  # small floor avoids 0^(c-1)
                qc = np.power(q, c)
                lin = a * x + intercept
                f = lin * qc
                # f'(x) = a*q^c + (a*x + intercept)*c*q^(c-1)*b*e
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
                x_new = np.where(
                    newton_ok,
                    x - residual / np.where(newton_ok, fp_x, 1.0),
                    0.5 * (lo + hi),
                )

                # Fall back to bisection if Newton escapes bracket
                escaped = (x_new <= lo) | (x_new >= hi) | ~np.isfinite(x_new)
                x_new[escaped] = 0.5 * (lo[escaped] + hi[escaped])

                x = x_new

            roots[valid] = np.where(
                r == 0, 0, np.where(np.isfinite(x) & (x >= 0), x, np.nan)
            )
            return mask.masked_array(roots, mask=np.isnan(roots))

        param_a_c = sros_param_a[mask_form_c]
        param_b_c = sros_param_b[mask_form_c]
        param_c_c = sros_param_c[mask_form_c]
        selected_codes = model_codes[mask_form_c]
        intercept = np.where(np.isin(selected_codes, [12, 13]), 13.0, 10.0)
        base_rsz = (param_a_c * isz[mask_form_c] + intercept) * np.power(
            1 - np.exp(-param_b_c * isz[mask_form_c]), param_c_c
        )
        # ConPyro 18c decision: slope scales only g(ISZ), not the stand offset.
        # The unchanged forward equation adds d/e and applies its zero floor.
        rsf = base_rsz * sf[mask_form_c]
        isf[mask_form_c] = solve_isf(rsf, param_a_c, param_b_c, param_c_c, intercept)

    return mask.masked_invalid(isf)


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
            if label in ('o1a', 'o1b'):
                return 30 if label == 'o1a' else 31
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
                raise ValueError(
                    f"Surface ROS model must be an integer or label: {item!r}"
                )
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
    cros_param_b4: np.ndarray,
) -> np.ndarray:
    """
    Calculate Active Crown Fire Rate of Spread (m/min).

    Supports two models:
    - Model 1: Cruz et al. (2005)
    - Model 2: Alexander and Cruz (2019)

    :param wsv: Effective wind speed (km/h)
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
            cros_param_b1[mask_model1]
            * np.power(wsv[mask_model1], cros_param_b2[mask_model1])
            * np.power(cbd[mask_model1], cros_param_b3[mask_model1])
            * np.exp(-cros_param_b4[mask_model1] * effm_mod)
        )

    # Model 2: Alexander and Cruz (2019)
    mask_model2 = cros_model == 2
    if np.any(mask_model2):
        cros_a[mask_model2] = 0.084 * wsv[mask_model2] * 1000 / 60

    mask_model3 = cros_model == 3
    if np.any(mask_model3):
        cros_a[mask_model3] = 0.1 * wsv[mask_model3] * 1000 / 60

    invalid = (
        mask.getmaskarray(wsv)
        | mask.getmaskarray(cbd)
        | mask.getmaskarray(mc_sa)
        | mask.getmaskarray(cros_model)
    )
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


def calc_ros_smooth(
    sros, cros_p, cros_a, cfo_prob, cac, *, wind_axis=None
) -> np.ndarray:
    """R composite smoothing, with explicit scenario grouping.

    None treats every element as a separate single-wind scenario. An integer
    axis groups winds; the passive-phase decision never crosses other axes.
    """
    arrays = [
        mask.asarray(x, dtype=float) for x in (sros, cros_p, cros_a, cfo_prob, cac)
    ]
    values = np.broadcast_arrays(*[x.data for x in arrays])
    invalid = np.zeros(values[0].shape, dtype=bool)
    for x in arrays:
        invalid |= np.broadcast_to(mask.getmaskarray(x), invalid.shape)
    surface, passive_ros, active_ros, probability, criterion = values
    invalid |= ~np.isfinite(
        surface + passive_ros + active_ros + probability + criterion
    )
    passive = (probability >= 0.5) & (criterion < 1) & ~invalid
    if wind_axis is None:
        has_passive = passive
    else:
        if isinstance(wind_axis, (bool, np.bool_)) or not isinstance(
            wind_axis, (int, np.integer)
        ):
            raise TypeError("wind_axis must be an integer or None")
        if not -surface.ndim <= wind_axis < surface.ndim:
            raise ValueError("wind_axis is outside the input dimensions")
        has_passive = np.any(passive, axis=wind_axis, keepdims=True)
    target = np.where(has_passive, passive_ros, active_ros)
    blended = surface * (1 - probability) + target * probability
    active = (probability >= 0.5) & (criterion >= 1)
    composite = np.where(has_passive & active, active_ros, blended)
    return mask.array(composite, mask=invalid)


def calc_cros_a_smooth(
    sros: np.ndarray, cros_a: np.ndarray, cfo_prob: np.ndarray
) -> np.ndarray:
    """
    Calculate smoothed Active Crown Fire Rate of Spread.

    :param sros: Surface Fire Rate of Spread (m/min)
    :param cros_a: Active Crown Fire Rate of Spread (m/min)
    :param cfo_prob: Crown Fire Occurrence probability
    :return: Smoothed Active Crown Fire Rate of Spread (m/min)
    """
    return (sros * (1.0 - cfo_prob)) + (cros_a * cfo_prob)


def calc_cros_p_smooth(
    sros: np.ndarray, cros_p: np.ndarray, cfo_prob: np.ndarray
) -> np.ndarray:
    """
    Calculate smoothed Passive Crown Fire Rate of Spread.

    :param sros: Surface Fire Rate of Spread (m/min)
    :param cros_p: Passive Crown Fire Rate of Spread (m/min)
    :param cfo_prob: Crown Fire Occurrence probability
    :return: Smoothed Passive Crown Fire Rate of Spread (m/min)
    """
    return (sros * (1.0 - cfo_prob)) + (cros_p * cfo_prob)


def calc_cros_smooth(
    cros_a_smooth: np.ndarray, cros_p_smooth: np.ndarray, cac: np.ndarray
) -> np.ndarray:
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


def calc_hros_smooth(
    sros_smooth: np.ndarray, cros_smooth: np.ndarray, cfo_prob: np.ndarray
) -> np.ndarray:
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
    cfi_param_b5: np.ndarray,
) -> np.ndarray:
    """
    Calculate the logit for crown fire occurrence.

    Supports multiple model types with different parameter configurations.
    Masks propagate from every consumed input; hidden values are not evaluated.
    An unused b5 mask does not affect models 1, 2, 4 or 5. Entirely plain inputs
    retain plain ndarray output; consumed missing entries propagate to the output mask.

    :param wsv: Effective wind speed (km/h)
    :param fsg: Fuel Strata Gap (m)
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

    def broadcast_operand(value):
        raw = mask.asarray(value)
        if raw.shape == logit.shape:
            return value
        data = np.broadcast_to(raw.data, logit.shape)
        if mask.isMaskedArray(value):
            return mask.array(data, mask=np.broadcast_to(mask.getmaskarray(raw), logit.shape))
        return data

    # Models 1, 2, 4, 5
    codes = mask.getdata(cfo_model)
    known = np.isin(codes, [1, 2, 3, 4, 5, 10])
    missing = np.broadcast_to(mask.getmaskarray(cfo_model), logit.shape).copy()
    for value in (wsv, fsg, mc_sa, sfc, cfi_param_b0, cfi_param_b1,
                  cfi_param_b2, cfi_param_b3, cfi_param_b4):
        if mask.isMaskedArray(value) and np.any(value.mask):
            missing |= mask.getmaskarray(value) & known
    uses_b5 = np.isin(codes, [3, 10]) & ~missing
    if np.any(uses_b5) and mask.isMaskedArray(cfi_param_b5):
        missing |= uses_b5 & mask.getmaskarray(cfi_param_b5)
    visible = ~missing
    # Broadcast only operands used by visible model calculations. In particular,
    # an unused b5 must not impose shape or payload requirements on the result.
    if np.any(known & visible):
        (wsv, fsg, mc_sa, sfc, cfi_param_b0, cfi_param_b1, cfi_param_b2,
         cfi_param_b3, cfi_param_b4) = (
            broadcast_operand(value) for value in
            (wsv, fsg, mc_sa, sfc, cfi_param_b0, cfi_param_b1, cfi_param_b2,
             cfi_param_b3, cfi_param_b4))
        if np.any(uses_b5 & visible):
            cfi_param_b5 = broadcast_operand(cfi_param_b5)
    mask_other = np.isin(mask.getdata(cfo_model), [1, 2, 4, 5]) & visible
    if np.any(mask_other):
        logit_vals = (
            cfi_param_b0[mask_other]
            + cfi_param_b1[mask_other] * wsv[mask_other]
            + cfi_param_b2[mask_other] * np.power(fsg[mask_other], 1.5)
            + cfi_param_b3[mask_other] * mc_sa[mask_other] * wsv[mask_other]
            + cfi_param_b4[mask_other] * np.log(sfc[mask_other])
        )
        logit[mask_other] = logit_vals

    # Model 3
    mask_model3 = (mask.getdata(cfo_model) == 3) & visible
    if np.any(mask_model3):
        selected_sfc = sfc[mask_model3]
        sfc0 = np.zeros_like(selected_sfc)
        sfc1 = np.zeros_like(selected_sfc)
        sfc0[(selected_sfc >= 1.0) & (selected_sfc < 2.0)] = 1
        sfc1[selected_sfc >= 2.0] = 1

        logit_vals = (
            cfi_param_b0[mask_model3]
            + cfi_param_b1[mask_model3] * wsv[mask_model3]
            + cfi_param_b2[mask_model3] * np.power(fsg[mask_model3], 1.5)
            + cfi_param_b3[mask_model3] * mc_sa[mask_model3] * wsv[mask_model3]
            + cfi_param_b4[mask_model3] * sfc0
            + cfi_param_b5[mask_model3] * sfc1
        )
        logit[mask_model3] = logit_vals

    # Model 10 (CFIS)
    mask_model10 = (mask.getdata(cfo_model) == 10) & visible
    if np.any(mask_model10):
        selected_sfc = sfc[mask_model10]
        sfc0 = np.zeros_like(selected_sfc)
        sfc1 = np.zeros_like(selected_sfc)
        sfc0[selected_sfc < 1.0] = 1
        sfc1[(selected_sfc >= 1.0) & (selected_sfc < 2.0)] = 1

        logit_vals = (
            cfi_param_b0[mask_model10]
            + cfi_param_b1[mask_model10] * wsv[mask_model10]
            + cfi_param_b2[mask_model10] * fsg[mask_model10]
            + cfi_param_b3[mask_model10] * sfc0
            + cfi_param_b4[mask_model10] * sfc1
            + cfi_param_b5[mask_model10] * mc_sa[mask_model10]
        )
        logit[mask_model10] = logit_vals

    result = logit.astype(np.float64)
    if np.any(missing):
        result = mask.array(result, mask=mask.getmaskarray(result) | missing)
    return result


def calc_cfo_prob(logit: np.ndarray) -> np.ndarray:
    """
    Calculate the probability of crown fire occurrence.

    :param logit: Logit value
    :return: Crown Fire Occurrence probability (0-1)
    """
    raw = mask.asarray(logit)
    if raw.dtype.kind != 'f':
        # Integer exp can use float16; unsigned negation can wrap. Neither
        # is suitable for evaluating a logistic probability.
        raw = raw.astype(np.float64)
    dtype = raw.dtype
    exponent_limit = np.log(np.finfo(dtype).max)
    # log(max) can round to an exponent whose exponential is already infinite.
    # Probe one scalar, stepping back only when needed; retain all finite values.
    with np.errstate(over='ignore'):
        if not np.isfinite(np.exp(exponent_limit)):
            exponent_limit = np.nextafter(exponent_limit, dtype.type(-np.inf))
    if (not np.any(raw.mask) and np.all(np.isfinite(raw.data))
            and np.all(raw.data <= exponent_limit)):
        # Preserve legacy scalar/array dtype promotion and nomask representation,
        # without gathered copies or full-size result/mask buffers on this path.
        exponential = mask.exp(raw)
        return mask.where(np.isfinite(raw), exponential / (1.0 + exponential), mask.masked)

    valid = ~mask.getmaskarray(raw) & np.isfinite(raw.data)
    large = valid & (raw.data > exponent_limit)
    safe = mask.array(np.where(valid & ~large, raw.data, dtype.type(0)), mask=raw.mask)
    exponential = mask.exp(safe)
    # Keep the original expression for dtype, mask representation and the zero
    # payload beneath missing outputs. Never evaluate hidden extreme logits.
    result = mask.where(np.isfinite(raw), exponential / (1.0 + exponential), mask.masked)
    if np.any(large):
        result[large] = 1.0 / (1.0 + mask.exp(-raw.data[large]))
    return result


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
    fire_type[mask_active] = 3  # Active Crown Fire

    return fire_type
