import numpy as np
from typing import Union


def ffmc_mc(ffmc: Union[float, np.ndarray], use_precise_values: bool = True) -> Union[float, np.ndarray]:
    """
    Calculate the moisture content (m) from the fine fuel moisture code (ffmc)
    using the method described in Van Wagner (1987).

    :param ffmc: The fine fuel moisture code (ffmc) value(s).
    :return: The moisture content (m) corresponding to the input ffmc value(s).
    """
    # Percentage of Moisture Content (m)
    if use_precise_values:
        # This equation uses a more precise multiplier (~147.27723 instead of 147.2) per Wang et al. (2017)
        ffmc_coeff = 250.0 * 59.5 / 101.0
        return ffmc_coeff * (101 - ffmc) / (59.5 + ffmc)
    else:
        return 147.2 * (101 - ffmc) / (59.5 + ffmc)


def dmc_mc(dmc: Union[float, np.ndarray]) -> Union[float, np.ndarray]:
    """
    Calculate the moisture content (m) from the duff moisture code (dmc)
    using the method described in Van Wagner (1987).

    :param dmc: The duff moisture code (dmc) value(s).
    :return: The moisture content (m) corresponding to the input dmc value(s).
    """
    # Percentage of Moisture Content (m)
    return 20 + np.exp((244.72 - dmc) / 43.43)


def dc_mc(dc: Union[float, np.ndarray]) -> Union[float, np.ndarray]:
    """
    Calculate the moisture content (%) from the drought code (dc)
    using the method described in Van Wagner (1987).

    From Van Wagner (1987):
        In its initial form, the DC was called the Stored Moisture Index (SMI) and was expressed directly
        in 100ths of an inch of water up to a maximum of 800 (i.e., 8 inches of water). To match the style of
        the DMC, the SMI was converted to a logarithmic scale rising with dryness. A brief mathematical
        description of the DC follows, and Turner (1972) gives a complete description.

        The scale of the SMI (the original form of the DC) was 800 units in length, 800 representing
        saturation and zero representing the driest condition normally encountered. The required equation
        for the new logarithmic scale was analogous to the one forming the basis of the DMC. As an
        exponential expression of the moisture equivalent Q, the chosen scale equation is
            D = 400 In (BOO/a)
        where D is the current DC. The constant 400 represents the maximum theoretical moisture content
        of the fuel represented by the DC. As in the DMC, this type of scale permits the addition of daily
        drying increments that are independent of the current value of the DC.

    To determine the proportion of soil moisture content relative to saturation (800 units), we divide the moisture
    equivalent of DC, q, by 800. Multiply this value by 100 to express the soil moisture content as a
    percentage of saturation.

    :param dc: The drought code (dc) value(s).
    :return: The moisture content (m) corresponding to the input dc value(s).
    """
    # DC Moisture Content (q): q = 800 * np.exp(-dc / 400)
    # Proportion of saturation: q_prop = q / 800 = np.exp(-dc / 400)
    # Percentage of saturation: q_percent = 100 * q_prop = 100 * np.exp(-dc / 400)
    return 100 * np.exp(-dc/400)