"""Derive duff moisture and validate the inputs shared by FOFEM emissions backends."""
import logging

import numpy as np
import pandas as pd

from . import fwis_moisture_content as mc


def _open_fuel_rows(df: pd.DataFrame) -> pd.Series:
    """
    Identify grass/herb, shrub-proxy, and wheat scenarios.

    :param df: Fire results with optional surface_fuel_type and stand_type columns.
    :return: Boolean mask aligned with the input rows.
    """
    category = df.get('surface_fuel_type', pd.Series('', index=df.index))
    stand = df.get('stand_type', pd.Series(np.nan, index=df.index))
    codes = pd.to_numeric(stand, errors='coerce')
    names = stand.astype('string').str.upper()
    return (category.isin(['grass_herbs', 'shrubs']) | codes.isin([10, 20, 21, 22])
            | names.isin(['WHEAT_UNHARVESTED', 'WHEAT_HARVESTED', 'WHEAT_BALED']))


def calc_fuel_moisture_content(df: pd.DataFrame, logger: logging.Logger) -> pd.DataFrame:
    """
    Prepare and validate FOFEM moisture for burning scenarios.

    :param df: Merged burning fire and consumption rows with modelled moisture and weather DC.
    :param logger: Calling backend's logger for plot-specific moisture warnings.
    :return: Copy with the final moisture percentages for rows within the FOFEM 6.9.4 limits.
    """
    result = derive_grass_duff_moisture(df)
    duff = result['mc_dmc']
    ten_hour = pd.to_numeric(result['mc_sa'], errors='coerce').astype(float)
    dc = pd.to_numeric(result['dc'], errors='coerce').astype(float)
    valid_dc = np.isfinite(dc) & dc.ge(0)
    thousand_hour = pd.Series(mc.dc_mc(dc.where(valid_dc).to_numpy()), index=result.index)

    valid_duff_percent = duff.between(10, 197.2)
    # Burnup divides in single precision and compares the fraction to double-precision limits.
    duff_fraction = (duff.where(valid_duff_percent).astype(np.float32) / np.float32(100)).astype(float)
    valid_duff = valid_duff_percent & duff_fraction.between(0.1, 1.972)
    valid_ten_hour = ten_hour.between(3, 298)
    valid_thousand_hour = valid_dc & thousand_hour.between(1, 300)

    checks = (
        (valid_duff, 'fofem_duff_moisture_invalid',
         'DuffMoisture must be finite and within 10-197.2%, and its converted Burnup fraction must be within '
         '0.1-1.972. Check mc_dmc or the weather DMC used to derive it.'),
        (valid_ten_hour, 'fofem_10h_moisture_invalid',
         'Final 10-hour moisture (mc_sa) must be finite and within 3-298%. Check the modelled moisture or '
         'the supplied fire results.'),
        (valid_thousand_hour, 'fofem_1000h_moisture_invalid',
         'Weather DC must be finite and nonnegative and must yield 1000-hour moisture within 1-300%.'),
    )
    identifiers = result.get('#PlotId', pd.Series(None, index=result.index))
    for valid, issue_code, message in checks:
        for plot_id in identifiers.loc[~valid].drop_duplicates():
            logger.warning('FOFEM emissions skipped for affected scenarios. %s', message,
                           extra={'unique_id': plot_id, 'issue_code': issue_code})

    result['DuffMoisture'] = duff
    result['wfl10HourMoisture'] = ten_hour
    result['wfl1000HourMoisture'] = thousand_hour
    return result.loc[valid_duff & valid_ten_hour & valid_thousand_hour].copy()


def derive_grass_duff_moisture(df: pd.DataFrame) -> pd.DataFrame:
    """
    Complete open-fuel mc_dmc from weather using the existing DMC conversion.

    :param df: Fire results with mc_dmc and optional weather dmc and surface-type columns.
    :return: Copy with missing or nonfinite grass/herb, shrub-proxy, or wheat mc_dmc calculated
        from finite nonnegative DMC, bounded to 10-200 as in ConPyro's forest moisture path.
        Existing finite values are preserved.
    """
    result = df.copy()
    if 'mc_dmc' not in result:
        return result
    moisture = pd.to_numeric(result['mc_dmc'], errors='coerce').astype(float)
    missing = ~np.isfinite(moisture)
    dmc = pd.to_numeric(result.get('dmc', pd.Series(np.nan, index=result.index)), errors='coerce').astype(float)
    use_weather = _open_fuel_rows(result) & missing & np.isfinite(dmc) & dmc.ge(0)
    result['mc_dmc'] = moisture
    result.loc[use_weather, 'mc_dmc'] = mc.dmc_mc(dmc.loc[use_weather].clip(10, 200).to_numpy(dtype=float))
    return result
