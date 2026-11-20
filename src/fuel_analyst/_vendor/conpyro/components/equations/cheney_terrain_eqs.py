"""ConPyro's matched-reference FBP wind/heading extension for Cheney grass.

O1b supplies the ISI shape for 32; O1a supplies it for 33/34. The reference
retains the reviewed exact km/h conversion; forward ROS uses Spark rounding.
Proxy indices stay local: they are not physical FFMC-derived diagnostics.
"""

import numpy as np

from . import cheney_eqs as ch
from . import conpyro_eqs as eq


def calc_cheney_wsv_raz(ws, wd, slope, aspect, mf, gcf, model):
    """Return effective wind (km/h) and spread TO bearing (compass degrees).

    Inputs use wind FROM, downslope aspect and percent grade. Ambient wind
    has no finite upper cap; negative wind is invalid and negative grade means
    flat. Missing consumed inputs propagate per output without reading masked
    payloads. Flat wind does not
    consume aspect/Mf/curing; calm slope does not consume wind direction.
    Valid zero reference spread uses the continuous small-R0 FBP limit.
    Masked model selectors make both outputs missing regardless of payload.
    """
    selectors = np.ma.asarray(model)
    wind, direction, grade, downslope, moisture, curing, codes = np.broadcast_arrays(
        ch.normalize_cheney_wind(ws, selectors), ch.numeric_or_nan(wd),
        ch.numeric_or_nan(slope), ch.numeric_or_nan(aspect), ch.numeric_or_nan(mf),
        ch.numeric_or_nan(gcf), selectors.data,
    )
    grade = np.maximum(grade, 0.0)
    # Cap before the eager exponential branch, including extreme finite input.
    factor = np.asarray(eq.calc_sf(np.minimum(grade, 70.0)))
    speed = np.full(wind.shape, np.nan)
    bearing = np.full(wind.shape, np.nan)
    flat = np.isfinite(wind) & np.isfinite(grade) & (factor == 1)
    speed[flat] = wind[flat]
    flat_bearing = flat & np.isfinite(direction)
    bearing[flat_bearing] = (direction[flat_bearing] + 180) % 360

    sloped = np.isfinite(wind) & np.isfinite(grade) & (factor > 1) & np.isfinite(downslope)
    moisture = ch.normalize_cheney_mf(np.where(sloped, moisture, np.nan))
    curing_factor = ch.calc_cheney_curing_coefficient(np.where(sloped, curing, np.nan))
    valid = sloped & np.isfinite(moisture) & np.isfinite(curing_factor)
    valid &= (wind == 0) | np.isfinite(direction)
    if not np.any(valid):
        return speed, bearing

    natural, shorter = eq.SROS_PARAMS_DICT[31], eq.SROS_PARAMS_DICT[30]
    a, b, c = (np.where(codes[valid] == 32, natural[index], shorter[index]) for index in range(3))
    selected_factor = factor[valid]
    selected_curing = curing_factor[valid]
    intercept = np.select(
        [codes[valid] == code for code in ch.CHENEY_SROS_IDS],
        [ch.LOW_BASES[code] for code in ch.CHENEY_SROS_IDS], default=np.nan)
    zero = (intercept * ch.calc_cheney_moisture_coefficient(moisture[valid], 0.)
            * selected_curing * (1000. / 60.))
    # For R0->0 the inverse ratio tends to SF**(1/c). A unit ISZ is a
    # harmless local reference for the existing vector routine in that limit.
    ff_proxy = np.full(zero.shape, 1. / .208)
    isf_proxy = selected_factor**(1. / c)
    positive = zero > 0
    if np.any(positive):
        def inverse(rate):
            ratio = rate / (a[positive] * selected_curing[positive])
            return -np.log(np.maximum(1. - ratio**(1. / c[positive]), .01)) / b[positive]

        ff_proxy[positive] = inverse(zero[positive]) / .208
        isf_proxy[positive] = inverse(zero[positive] * selected_factor[positive])
    wind_to = (np.where(np.isfinite(direction[valid]), direction[valid], 0.) + 180) % 360
    upslope = (downslope[valid] + 180) % 360
    calculated_speed, calculated_bearing = eq.calc_wsv_raz(
        wind[valid], wind_to, isf_proxy, ff_proxy, upslope)
    speed[valid] = np.ma.filled(calculated_speed, np.nan)
    bearing[valid] = np.ma.filled(calculated_bearing, np.nan)
    return speed, bearing
