"""Cheney (1998) grass spread with Cruz (2015b) curing, in m/min.

See docs/reference/cheney_cruz/REFERENCE.md for source discrepancies and the
owner-selected backing, clipping and heat-yield extensions. Missing inputs are
NaN; masked arrays are accepted without reading their masked payloads.
"""

import warnings

import numpy as np
from numpy import ma

CHENEY_SROS_IDS = (32, 33, 34)
# Cheney et al. 1998 Eqs 18–22 supply the published branches; 0.715 is Eq21,
# not Cruz2020 A4's 0.705. The model-34 low branch is a separate Spark extension:
# proj1/proj1.xml, build 1.1.2.52703, commented eaten-out coefficients 0.027/0.1045.
# Source hash and the owner decision are in docs/reference/cheney_cruz/REFERENCE.md.
LOW_BASES = {32: 0.054, 33: 0.054, 34: 0.027}
LOW_SLOPES = {32: 0.269, 33: 0.209, 34: 0.1045}
HIGH_BASES = {32: 1.4, 33: 1.1, 34: 0.55}
HIGH_SCALES = {32: 0.838, 33: 0.715, 34: 0.357}
WIND_JOIN = 5.0
WIND_EXPONENT = 0.844
# Spark proj1 grass script: literal km/h to m/s rounding, then m/min.
SPARK_KMH_TO_MMIN = 0.2778 * 60.0
# Spark proj1/proj1.xml CSIRO grassland ellipse, build 1.1.2.52703;
# source hash in REFERENCE.md. The same script sets LBR=1 below 5 km/h.
LBR_SCALE = 1.1
LBR_EXPONENT = 0.464
# Cheney1998 Eqs14–16, reproduced in Cruz2020 A6.
MOISTURE_EXPONENT = -0.108
MOISTURE_JOIN = 12.0
MOISTURE_WIND_JOIN = 10.0
# Cheney 1998 Eqs. 15/16: low/high-wind linear moisture forms.
MOISTURE_LOW_INTERCEPT = 0.684
MOISTURE_LOW_LOSS = 0.0342
MOISTURE_HIGH_INTERCEPT = 0.547
MOISTURE_HIGH_LOSS = 0.0228
# Cruz 2020 A2, after Cheney 1989 / McArthur 1960.
AM60_INTERCEPT = 9.58
AM60_TEMP_LOSS = 0.205
AM60_RH_GAIN = 0.138
# Noble, Bary and Gill 1980 Mark 3, reproduced in Cruz 2020 A1.
GFDI_PARAMETERS = (2.0, -23.6, 5.01, 0.0281, 0.226, 0.633)
# Cruz2015b Eq4 (Cruz2020 A7 rounds103.989 to103.99).
CURING_PARAMETERS = (1.036, 103.989, 0.0996, 20.0)
# Cheney1998 Eq17, comparison only; never selected by the class.
OLD_CURING_PARAMETERS = (1.120, 59.2, 0.124, 50.0)
# Alexander1982 low heat, Van Wagner1972b moisture correction; no radiation term.
LOW_HEAT = 18700.0
MOISTURE_HEAT_LOSS = 24.0


def _clip(value, lower, upper, name):
    result = numeric_or_nan(value).copy()
    invalid = np.isfinite(result) & ((result < lower) | (result > upper))
    _warn(invalid, name, f"clipped to {lower:g}–{upper:g}")
    return np.clip(result, lower, upper)


def numeric_or_nan(value):
    """Return float values with missing/nonfinite entries as NaN.

    Convert visible entries only; masked object payloads are never interpreted.
    The input is not modified.
    """
    raw = ma.asarray(value)
    visible = ~ma.getmaskarray(raw)
    result = np.full(raw.shape, np.nan)
    result[visible] = raw.data[visible]
    return np.where(np.isfinite(result), result, np.nan)


def normalize_cheney_mf(mf):
    """Clip standing dead-fuel moisture to 2–24%, with a counted warning."""
    return _clip(mf, 2, 24, "Mf")


def normalize_cheney_curing(gcf):
    """Accept curing in 20–100%; otherwise return NaN and a counted warning."""
    return _range(gcf, 20, 100, "curing")


def _range(value, lower, upper, name):
    result = numeric_or_nan(value).copy()
    invalid = np.isfinite(result) & ((result < lower) | (result > upper))
    _warn(invalid, name, f"outside {lower:g}–{upper:g}; returning NaN")
    return np.where(invalid, np.nan, result)


def _warn(invalid, name, action):
    count = int(np.count_nonzero(invalid))
    if count:
        warnings.warn(f"{name}: {count} cell(s) {action}", UserWarning, stacklevel=3)


def calc_am60(temp, rh):
    """Standing dead grass moisture, percent, by AM60 (A. McArthur's 1960 table
    as fitted by Cheney et al. 1989; Cruz 2020 A2).

    RH clips0–100 and calculated Mf clips 2–24, with counted warnings. Temperature
    is Celsius. Missing values propagate; original inputs are not modified.
    """
    return calc_cheney_moisture(temp, rh)


def calc_cheney_bros(mf, gcf, *, wsv, model):
    """Spark focal-ellipse backing in m/min, derived from the same head rate.

    LBR is 1 below 5 km/h, otherwise 1.1*WSV**0.464. Thus head and back are
    exactly equal below 5; the source discontinuity at 5 is retained. Wind
    and model are required explicitly; pass 0 for calm conditions. There is
    no finite upper wind cap. This wrapper computes the head internally and
    equals calc_cheney_sros(wsv, mf, gcf, model) * calc_cheney_backing_ratio(wsv).
    If the head already exists, reuse the ratio or the surface-ROS helper,
    passing the same per-cell WSV that produced the surface head rate.
    This is not the Figure 2 regression.
    """
    wind, moisture, curing, codes = _spread_inputs(wsv, mf, gcf, model)
    head = _head_from_inputs(wind, moisture, curing, codes)
    return head * _backing_ratio_from_validated_wind(wind)


def calc_cheney_backing_ratio(wsv):
    """Return Spark's focal-ellipse backing/head ratio at effective WSV.

    WSV is nonnegative km/h, with no effective-wind upper cap. Negative
    values return NaN with a counted warning; missing/masked values stay
    missing. Multiply an existing surface head rate by this ratio to reuse it.
    """
    wind = _nonnegative_wind(wsv, "WSV")
    return _backing_ratio_from_validated_wind(wind)


def calc_cheney_bros_from_surface_ros(surface_ros, wsv):
    """Reuse nonnegative surface head ROS and its matching per-cell WSV.

    Inputs broadcast together. They must come from the same calculation;
    this geometry helper cannot verify that association. Do not pass crown-
    composite HROS. Invalid negatives return NaN with counted warnings.
    Wind warnings retain the historical U10 prefix of the ROS functions.
    """
    head, wind = np.broadcast_arrays(
        _range(surface_ros, 0, np.inf, "surface_ros"), _nonnegative_wind(wsv, "U10"))
    return head * _backing_ratio_from_validated_wind(wind)


def _backing_ratio_from_validated_wind(wind):
    """Evaluate focal geometry for normalized nonnegative wind or NaN."""
    length = np.where(wind < WIND_JOIN, 1.0, LBR_SCALE * wind**LBR_EXPONENT)
    eccentricity = np.sqrt(np.maximum(0.0, 1.0 - length**-2))
    # Rationalized (1-e)/(1+e) avoids cancellation in elongated ellipses.
    ratio = 1.0 / (length**2 * (1.0 + eccentricity)**2)
    return ratio


def calc_cheney_curing_coefficient(gcf):
    """Cruz2015b Eq4: replacement for Cheney's assumed curing sigmoid.

    Fit to13 paired burns at Wangaratta/Wendouree, with propagation treatments
    at42–76% curing and fully cured controls. Sustainability burns spread at21–30%,
    but fitted spread data below40% are absent. Cheney's assumed function
    underpredicted curing (MAE.23, MAPE80%); Cruz's fit gives MAE.03/MAPE18%.
    Spread is roughly10–2 times faster at50–80% curing. Neither curve is
    renormalized at100%. Applicable mainly to senescing temperate grassland;
    regrowth below85%, tropical grass and fire-danger use remain uncertain.
    Wheat validation is fully cured only. Accept20–100%; otherwise NaN/warning.
    """
    curing = normalize_cheney_curing(gcf)
    a, b, rate, origin = CURING_PARAMETERS
    return a / (1 + b * np.exp(-rate * (curing - origin)))


def calc_cheney_curing_coefficient_1998(gcf):
    """Cheney1998 Eq17 for comparison only, valid50–100% curing.

    This assumed sigmoid underpredicted the Cruz2015b curing observations
    (MAE.23, MAPE80%). No selector or class option uses this older function.
    """
    curing = _range(gcf, 50, 100, "curing")
    a, b, rate, origin = OLD_CURING_PARAMETERS
    return a / (1 + b * np.exp(-rate * (curing - origin)))


def calc_cheney_heat_yield(mf):
    """Low net heat in kJ/kg from already normalized standing moisture (%).

    Alexander1982:18700 already excludes water of reaction; subtract24kJ/kg
    per moisture percentage point. No additional1263 or radiation reduction.
    """
    return LOW_HEAT - MOISTURE_HEAT_LOSS * numeric_or_nan(mf)


def calc_cheney_moisture(temp=None, rh=None, cheney_mf_override=None):
    """Normalize shared Mf once for head/backing/heat, with cellwise override.

    Missing/masked/nonfinite override entries fall back to AM60. Absent weather
    raises only where fallback is needed; masked weather returns NaN. CFIS
    requirements are independent and remain enforced by the class.
    """
    arrays = [
        numeric_or_nan(value) for value in (temp, rh, cheney_mf_override) if value is not None
    ]
    shape = (
        np.broadcast_shapes(*(np.shape(value) for value in arrays)) if arrays else ()
    )
    override = (
        np.full(shape, np.nan)
        if cheney_mf_override is None
        else np.broadcast_to(numeric_or_nan(cheney_mf_override), shape)
    )
    needed = ~np.isfinite(override)
    if np.any(needed) and (temp is None or rh is None):
        raise ValueError(
            "temp and rh are required for Cheney moisture without an override"
        )
    calculated = np.full(shape, np.nan)
    if np.any(needed):
        temperature = np.broadcast_to(numeric_or_nan(temp), shape)
        humidity = _clip(
            np.where(needed, np.broadcast_to(numeric_or_nan(rh), shape), np.nan), 0, 100, "rh"
        )
        # Cruz2020 A2, after Cheney1989's parameterization of McArthur1960.
        calculated = (
            AM60_INTERCEPT - AM60_TEMP_LOSS * temperature + AM60_RH_GAIN * humidity
        )
    return _clip(np.where(needed, calculated, override), 2, 24, "Mf")


def calc_cheney_moisture_coefficient(mf, wsv):
    """Cheney1998 Eqs14–16; retain rounded branch jumps and zero floor."""
    moisture, wind = np.broadcast_arrays(_clip(mf, 2, 24, "Mf"), numeric_or_nan(wsv))
    coefficient = np.where(
        moisture <= MOISTURE_JOIN,
        np.exp(MOISTURE_EXPONENT * moisture),
        np.where(
            wind <= MOISTURE_WIND_JOIN,
            MOISTURE_LOW_INTERCEPT - MOISTURE_LOW_LOSS * moisture,
            MOISTURE_HIGH_INTERCEPT - MOISTURE_HIGH_LOSS * moisture,
        ),
    )
    # Wind selects the wet-fuel branch; a missing wind cannot select "high".
    required_missing = (moisture > MOISTURE_JOIN) & ~np.isfinite(wind)
    return np.where(required_missing, np.nan, np.maximum(coefficient, 0.0))


def _spread_inputs(wsv, mf, gcf, model):
    return np.broadcast_arrays(
        normalize_cheney_effective_wind(wsv, model),
        _clip(mf, 2, 24, "Mf"),
        calc_cheney_curing_coefficient(gcf),
        np.asarray(model),
    )


def calc_cheney_sros(wsv, mf, gcf, model):
    """Spark grass head spread in m/min for 32 natural, 33 grazed, 34 eaten-out.

    Wind is effective WSV in km/h. Mf clips 2–24%; curing outside 20–100%
    and negative WSV return NaN/warnings. There is no finite upper wind cap;
    the output of calc_cheney_wsv_raz chains directly into this function.
    Numerical acceptance does not establish calibration at arbitrary winds.
    Model 34's low branch is the selected Spark eaten-out extension.
    """
    return _head_from_inputs(*_spread_inputs(wsv, mf, gcf, model))


def _head_from_inputs(wind, moisture, curing, codes):
    base = np.full(wind.shape, np.nan)
    for code in CHENEY_SROS_IDS:
        selected = codes == code
        high = selected & (wind >= WIND_JOIN)
        base[high] = (
            HIGH_BASES[code]
            + HIGH_SCALES[code] * (wind[high] - WIND_JOIN) ** WIND_EXPONENT
        )
        low = selected & (wind < WIND_JOIN)
        base[low] = LOW_BASES[code] + LOW_SLOPES[code] * wind[low]
    return (
        base
        * calc_cheney_moisture_coefficient(moisture, wind)
        * curing
        * SPARK_KMH_TO_MMIN
    )


def calc_gfdi(temp, rh, wsv, gcf):
    """Noble et al. (1980) Mark 3 GFDI, reproduced in Cruz 2020 A1.

    These sources give no application limits; values outside the McArthur
    meter's fitted range are extrapolations. Validate only the input domain:
    nonnegative wind with no upper limit, RH clipped to 0–100%, curing 0–100%
    with zero returning the equation's limit of zero, and unrestricted finite
    temperature. Invalid wind/curing yields NaN with counted warnings; missing
    inputs propagate. Never evaluate the logarithm for zero curing.
    """
    temperature, humidity, wind, curing = np.broadcast_arrays(
        numeric_or_nan(temp),
        _clip(rh, 0, 100, "rh"),
        _nonnegative_wind(wsv, "U10"),
        _range(gcf, 0, 100, "curing"),
    )
    scale, intercept, curing_gain, temperature_gain, humidity_loss, wind_gain = (
        GFDI_PARAMETERS
    )
    valid = (np.isfinite(temperature) & np.isfinite(humidity)
             & np.isfinite(wind) & np.isfinite(curing))
    result = np.full(temperature.shape, np.nan)
    result[valid & (curing == 0)] = 0.
    positive = valid & (curing > 0)
    result[positive] = scale * np.exp(
        intercept
        + curing_gain * np.log(curing[positive])
        + temperature_gain * temperature[positive]
        - humidity_loss * np.sqrt(humidity[positive])
        + wind_gain * np.sqrt(wind[positive])
    )
    return result


def normalize_cheney_wind(wsv, model):
    """Normalize ambient or effective wind and preserve masked missingness.

    Nonnegative finite wind has no upper cap. Negative wind returns NaN with
    a counted warning, retaining the historical U10 prefix for ROS callers.
    Only visible model selectors are validated; hidden payloads are ignored.
    """
    selectors = ma.asarray(model)
    wind, codes, selector_mask = np.broadcast_arrays(
        numeric_or_nan(wsv), selectors.data, ma.getmaskarray(selectors))
    if np.any(~np.isin(codes[~selector_mask], CHENEY_SROS_IDS)):
        raise ValueError("Unknown Cheney model; use 32, 33, 34")
    wind = np.where(selector_mask, np.nan, wind)
    return _nonnegative_wind(wind, "U10")


# Ambient and effective wind share exactly the same domain policy.
normalize_cheney_effective_wind = normalize_cheney_wind


def _nonnegative_wind(value, label):
    wind = numeric_or_nan(value)
    outside = np.isfinite(wind) & (wind < 0)
    _warn(outside, label, "outside wind application domain; returning NaN")
    return np.where(outside, np.nan, wind)
