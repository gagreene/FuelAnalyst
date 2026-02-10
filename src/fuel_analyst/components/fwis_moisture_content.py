import numpy as np


def ffmc_mc(ffmc: float | np.ndarray, use_precise_values: bool = True) -> float | np.ndarray:
    """
    Calculate the moisture content (m) from the fine fuel moisture code (ffmc)
    using the method described in Van Wagner (1987).

    :param ffmc: The fine fuel moisture code (ffmc) value(s).
    :return: The moisture content (m) corresponding to the input ffmc value(s).
    """

    # Moisture Content (m)
    if use_precise_values:
        # This equation uses a more precise multiplier (~147.27723 instead of 147.2) per Wang et al. (2017)
        ffmc_coeff = 250.0 * 59.5 / 101.0
        return ffmc_coeff * (101 - ffmc0) / (59.5 + ffmc0)
    else:
        return 147.2 * (101 - ffmc0) / (59.5 + ffmc0)


def dmc_mc(dmc: float | np.ndarray) -> float | np.ndarray:
    """
    Calculate the moisture content (m) from the duff moisture code (dmc)
    using the method described in Van Wagner (1987).

    :param dmc: The duff moisture code (dmc) value(s).
    :return: The moisture content (m) corresponding to the input dmc value(s).
    """

    # Moisture Content (m)
    return 20 + np.exp((244.72 - dmc) / 43.43)


def dc_mc(dc: float | np.ndarray) -> float | np.ndarray:
    """
    Calculate the moisture content (m) from the drought code (dc)
    using the method described in Van Wagner (1987).

    :param dc: The drought code (dc) value(s).
    :return: The moisture content (m) corresponding to the input dc value(s).
    """

    # DC moisture Content (q)
    return 800 / np.exp(dc / 400)
