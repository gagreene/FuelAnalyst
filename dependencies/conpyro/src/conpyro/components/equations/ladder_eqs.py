from datetime import datetime as dt
from typing import Optional, Tuple, Union
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
        return mask.array([data], mask=~np.isfinite([data]))
    elif isinstance(data, mask.MaskedArray):
        # Already masked - return as-is, preserving all existing masks
        return data
    else:
        # Regular array - convert to masked array with invalid values masked
        data_arr = np.asarray(data)
        return mask.array(data_arr, mask=~np.isfinite(data_arr))


def calc_dead_ladder_contributions(
    ht_midstry_dead: Union[int, float, np.ndarray],
    cbh_ovrstry: Union[int, float, np.ndarray],
    dead_branch_fl: Union[int, float, np.ndarray],
    m: float,
) -> Tuple:
    """
    Calculate dead ladder fuel strata gap and scaled surface fuel consumption contribution.

    Calculates the fuel strata gap (FSG) for dead midstory trees (snags assumed < 5 cm DBH)
    and their scaled surface fuel consumption contribution based on the vertical position
    of the snag centroid relative to the overstory canopy base height.

    :param ht_midstry_dead: Mean height of the dead midstory cohort (saplings) (m)
    :param cbh_ovrstry: Live overstory canopy base height (aka LCBH) (m)
    :param dead_branch_fl: Estimated biomass of branches (roundwood) <= 1 cm diameter (kg/m2)
    :param m: Ladder fuel multiplier used to adjust SFC values for vertical heat flux contributions
    :return: Tuple of (fsg_dead_ladder, sfc_dead_ladder)
             fsg_dead_ladder: Fuel strata gap for dead ladder fuels (m)
             sfc_dead_ladder: Scaled surface fuel consumption from dead ladder fuels (kg/m2)
    :raises TypeError: If inputs are not numeric types
    :raises ValueError: If m is not positive or dimensions don't match
    """
    # Ensure all inputs are masked arrays
    ht_midstry_dead = _ensure_masked_array(ht_midstry_dead)
    cbh_ovrstry = _ensure_masked_array(cbh_ovrstry)
    dead_branch_fl = _ensure_masked_array(dead_branch_fl)

    # Validate m parameter
    if not isinstance(m, (int, float)):
        raise TypeError(f"m must be numeric, got {type(m)}")
    if m <= 0:
        raise ValueError(f"m must be positive, got {m}")

    # Validate compatible shapes
    shapes = {ht_midstry_dead.shape, cbh_ovrstry.shape, dead_branch_fl.shape}
    if len(shapes) > 1 and not any(s == (1,) for s in shapes):
        raise ValueError(f"Input arrays must have compatible shapes, got {shapes}")

    # Calculate snag centroid (Cl)
    cl = ht_midstry_dead / 2
    cl = mask.where(cl > cbh_ovrstry, cbh_ovrstry - 0.5, cl)

    # Calculate snag Fuel Strata Gap (fsg_dead_ladder = ZL)
    fsg_dead_ladder = cbh_ovrstry - cl
    fsg_dead_ladder = mask.where(fsg_dead_ladder < 0.5, 0.5, fsg_dead_ladder)

    # Calculate scaled SFC contribution of dead saplings as ladder fuels
    sfc_dead_ladder = mask.power(cbh_ovrstry / fsg_dead_ladder, 1.5) * dead_branch_fl * m
    sfc_dead_ladder = mask.clip(sfc_dead_ladder, None, 3)
    sfc_dead_ladder = mask.round(sfc_dead_ladder, 3)
    return fsg_dead_ladder, sfc_dead_ladder


def calc_fmc(
    lat: Union[int, float, np.ndarray],
    long: Union[int, float, np.ndarray],
    elevation: Union[int, float, np.ndarray],
    wx_date: Optional[int] = None,
    d0: Optional[Union[int, np.ndarray]] = None,
    dj: Optional[Union[int, np.ndarray]] = None,
) -> Tuple:
    """
    Calculate foliar moisture content (FMC) and intermediate values used in FMC equations.

    Estimates foliar moisture content based on geographic location (latitude, longitude, elevation)
    and weather date using the CFFDRS approach. Calculates normalized latitude, date of minimum FMC,
    Julian date, and the number of days between the observation date and minimum FMC date.

    If ``d0`` and ``dj`` are both provided they are used directly; otherwise they are
    derived from ``wx_date`` and geographic position.

    :param lat: Latitude (decimal degrees)
    :param long: Longitude (decimal degrees)
    :param elevation: Elevation (meters)
    :param wx_date: Date of weather observation (YYYYMMDD format). Required when ``d0``
        and/or ``dj`` are not supplied, because they are derived from it.
        May be ``None`` when both ``d0`` and ``dj`` are provided directly.
    :param d0: Date of minimum foliar moisture content (Julian day). If ``None``,
        calculated from ``lat``, ``long``, ``elevation``, and ``wx_date``.
    :param dj: Julian date of the weather observation. If ``None``, calculated
        from ``wx_date``.
    :return: Tuple of (fmc, latn, d0, dj, nd)
             fmc: Foliar moisture content (%)
             latn: Normalized latitude (adjusted for longitude and elevation)
             d0: Date of minimum foliar moisture content
             dj: Julian date of weather observation
             nd: Number of days between Julian date and date of minimum FMC
    :raises TypeError: If inputs are not proper types
    :raises ValueError: If wx_date is missing when needed, or has an invalid format
    """
    # Ensure all numeric inputs are masked arrays
    lat = _ensure_masked_array(lat)
    long = _ensure_masked_array(long)
    elevation = _ensure_masked_array(elevation)

    # Determine whether wx_date is needed: it is required when either d0 or dj
    # must be derived (i.e. not supplied by the caller).
    need_d0 = d0 is None
    need_dj = dj is None

    # Validate wx_date only when it will actually be used, or when provided
    if wx_date is not None:
        if not isinstance(wx_date, int):
            raise TypeError(f"wx_date must be int (YYYYMMDD format), got {type(wx_date)}")
        try:
            date_string = str(wx_date)
            dt.fromisoformat(f'{date_string[:4]}-{date_string[4:6]}-{date_string[6:]}')
        except (ValueError, IndexError) as e:
            raise ValueError(f"wx_date must be formatted as YYYYMMDD, got {wx_date}") from e
    elif need_d0 or need_dj:
        raise ValueError(
            "wx_date is required when d0 and/or dj are not supplied. "
            "Either provide wx_date (YYYYMMDD) or supply both d0 and dj directly."
        )

    # Calculate normalized latitude
    latn = mask.where(
        (elevation is not None) & (elevation > 0),
        43 + (33.7 * np.exp(-0.0351 * (150 - np.abs(long)))),
        46 + (23.4 * np.exp(-0.036 * (150 - np.abs(long)))),
    )

    # D0 calculation — use supplied value or derive from geography
    if d0 is None:
        # Calculate date of minimum foliar moisture content (D0)
        # This value is rounded to mimic the approach used in the cffdrs R package.
        d0 = mask.MaskedArray.round(
            mask.where(
                (elevation is not None) & (elevation > 0),
                142.1 * (lat / latn) + (0.0172 * elevation),
                151 * (lat / latn),
            ),
            0,
        )
    else:
        d0 = _ensure_masked_array(d0)

    # Dj calculation — use supplied value or derive from wx_date
    if dj is None:
        dj = mask.where(
            np.isfinite(latn),
            dt.strptime(str(wx_date), "%Y%m%d").timetuple().tm_yday,
            0,
        )
    else:
        dj = _ensure_masked_array(dj)

    # Number of days between Dj and D0 (ND)
    nd = np.absolute(dj - d0)

    # Calculate foliar moisture content (FMC)
    fmc = mask.where(
        nd < 30,
        85 + (0.0189 * (nd ** 2)),
        mask.where(nd < 50, 32.9 + (3.17 * nd) - (0.0288 * (nd ** 2)), 120),
    )
    return fmc, latn, d0, dj, nd


def calc_total_sfc(
    sfc: Union[int, float, np.ndarray],
    sfc_dead_ladder: Union[int, float, np.ndarray],
    sfc_live_ladder: Union[int, float, np.ndarray],
) -> Union[int, float, np.ndarray]:
    """
    Calculate total surface fuel consumption including ladder fuel contributions.

    Adds dead and live ladder fuel consumption contributions to the base surface fuel consumption.
    Only updates values where the base surface fuel consumption is finite (non-masked).

    :param sfc: Estimated surface fuel consumption from base fuel types (kg/m2)
    :param sfc_dead_ladder: Surface fuel consumption contribution from dead ladder fuels (kg/m2)
    :param sfc_live_ladder: Surface fuel consumption contribution from live ladder fuels (kg/m2)
    :return: Total surface fuel consumption including ladder fuel contributions (kg/m2)
    :raises TypeError: If inputs are not numeric types
    """
    # Preserve masks so masked ladder values do not leak their backing data into totals.
    sfc = _ensure_masked_array(sfc).astype(np.float64)
    sfc_dead_ladder = _ensure_masked_array(sfc_dead_ladder).astype(np.float64)
    sfc_live_ladder = _ensure_masked_array(sfc_live_ladder).astype(np.float64)

    sfc_dead_ladder_filled = sfc_dead_ladder.filled(0)
    sfc_live_ladder_filled = sfc_live_ladder.filled(0)

    # Add dead and live ladder fuel contributions to surface fuel consumption
    return np.where(
        np.isfinite(sfc),
        sfc + sfc_dead_ladder_filled + sfc_live_ladder_filled,
        sfc,
    )


def calc_live_ladder_contributions(
    multiply_cfl: bool,
    cfl_midstry: Union[int, float, np.ndarray],
    cbh_ovrstry: Union[int, float, np.ndarray],
    cbh_midstry: Union[int, float, np.ndarray],
    ht_midstry_live: Union[int, float, np.ndarray],
    fmc: Union[int, float, np.ndarray],
    m: float,
    fsg: Union[int, float, np.ndarray],
    sfc: Union[int, float, np.ndarray],
) -> Tuple:
    """
    Calculate live ladder fuel strata gap and scaled surface fuel consumption contribution.

    Estimates the fuel strata gap (FSG) and surface fuel consumption contribution for live
    midstory trees (saplings > 1.3 m height, < 7.5 cm DBH). Applies foliar moisture content
    adjustment using the Babrauskas (2006) relationship and scales based on vertical position
    relative to the crown centroid.

    :param multiply_cfl: Boolean flag to apply 1.5x multiplier to canopy fuel load if True
    :param cfl_midstry: Midstory canopy fuel load (kg/m2)
    :param cbh_ovrstry: Live overstory canopy base height (aka LCBH) (m)
    :param cbh_midstry: Mean live canopy base height of midstory trees (saplings) (m)
    :param ht_midstry_live: Mean height of live midstory trees (saplings) (m)
    :param fmc: Foliar moisture content of live midstory trees (saplings) (%)
    :param m: Ladder fuel multiplier used to adjust SFC values for vertical heat flux contributions
    :param fsg: Fuel strata gap (m) - distance between fuel layers (must be pre-calculated by caller)
    :param sfc: Estimated surface fuel consumption from base fuel types (kg/m2)
    :return: Tuple of (adjusted_cfl_midstry, fsg_live_ladder, sfc_live_ladder)
             adjusted_cfl_midstry: Midstory canopy fuel load after optional multiplication (kg/m2)
             fsg_live_ladder: Fuel strata gap for live ladder fuels (m)
             sfc_live_ladder: Scaled surface fuel consumption from live ladder fuels (kg/m2)
    :raises TypeError: If inputs are not proper types or multiply_cfl is not boolean
    :raises ValueError: If m is not positive
    """
    # Validate multiply_cfl
    if not isinstance(multiply_cfl, bool):
        raise TypeError(f"multiply_cfl must be bool, got {type(multiply_cfl)}")

    # Validate m parameter
    if not isinstance(m, (int, float)):
        raise TypeError(f"m must be numeric, got {type(m)}")
    if m <= 0:
        raise ValueError(f"m must be positive, got {m}")

    # Ensure all inputs are masked arrays
    cfl_midstry = _ensure_masked_array(cfl_midstry)
    cbh_ovrstry = _ensure_masked_array(cbh_ovrstry)
    cbh_midstry = _ensure_masked_array(cbh_midstry)
    ht_midstry_live = _ensure_masked_array(ht_midstry_live)
    fmc = _ensure_masked_array(fmc)
    fsg = _ensure_masked_array(fsg)
    sfc = _ensure_masked_array(sfc)

    # Enforce FMC range (0-120%)
    fmc = mask.clip(fmc, 0, 120)

    # Double the CFL value if required
    adjusted_cfl_midstry = 1.5 * cfl_midstry if multiply_cfl else cfl_midstry

    # Fuel Strata Gap (FSG)
    fsg_live_ladder = cbh_ovrstry - (cbh_midstry + (ht_midstry_live - cbh_midstry) / 2)
    fsg_live_ladder = mask.where(fsg_live_ladder < 0.5, 0.5, fsg_live_ladder)

    # delta_h = modified FMC value
    # Calculated using Babrauskas (2006) relationship between FMC and effective heat of combustion
    # TODO ==== Make sure Dan explains where "divide by 16" comes from in the Ladder Fuels paper ====
    delta_h = (16.52 - 0.057 * fmc) / 16

    # Calculate sapling false SFC
    sfc_false = mask.round(delta_h * adjusted_cfl_midstry * m, 3)

    # Scale sfc value to crown centroid
    sfc_cc = mask.round(mask.power(fsg / cbh_ovrstry, 1.5) * sfc, 3)

    # Calculate sapling total false SFC (used as SFC input value in CCP)
    sfc_live_ladder = sfc_false + sfc_cc
    sfc_live_ladder = mask.where(sfc_live_ladder > 5, 5, sfc_live_ladder)

    return adjusted_cfl_midstry, fsg_live_ladder, sfc_live_ladder


def calc_min_ladder_fsg(
    fsg: Union[int, float, np.ndarray],
    fsg_live_ladder: Union[int, float, np.ndarray],
    fsg_dead_ladder: Union[int, float, np.ndarray],
) -> Union[int, float, np.ndarray]:
    """
    Calculate the minimum fuel strata gap across all ladder fuel layers.

    Determines the limiting fuel strata gap by selecting the minimum value across
    the base FSG, live ladder FSG, and dead ladder FSG. This minimum value represents
    the smallest vertical distance available for fire progression through the ladder
    fuel layers.

    :param fsg: Base fuel strata gap (m)
    :param fsg_live_ladder: Fuel strata gap for live ladder fuels (m)
    :param fsg_dead_ladder: Fuel strata gap for dead ladder fuels (m)
    :return: Minimum fuel strata gap across all layers (m)
    :raises TypeError: If inputs are not numeric types
    """
    # Ensure inputs are masked arrays
    fsg = _ensure_masked_array(fsg)
    fsg_live_ladder = _ensure_masked_array(fsg_live_ladder)
    fsg_dead_ladder = _ensure_masked_array(fsg_dead_ladder)

    # Calculate minimum FSG and assign as final ladder fuel contribution to overall FSG
    return mask.min([fsg, fsg_live_ladder, fsg_dead_ladder], axis=0)
