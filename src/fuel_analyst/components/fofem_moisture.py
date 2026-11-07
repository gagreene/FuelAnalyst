"""Shared weather-derived duff moisture for ConPyro and FOFEM emissions."""
import logging

import numpy as np
import pandas as pd

from . import fwis_moisture_content as mc


def _grass_rows(df: pd.DataFrame) -> pd.Series:
    """
    Identify grass/herb and shrub-proxy scenarios, including numeric grass stand codes.

    :param df: Fire results with optional surface_fuel_type and stand_type columns.
    :return: Boolean mask aligned with the input rows.
    """
    category = df.get('surface_fuel_type', pd.Series('', index=df.index))
    stand = pd.to_numeric(df.get('stand_type', pd.Series(np.nan, index=df.index)), errors='coerce')
    return (category.isin(['grass_herbs', 'shrubs']) | stand.eq(10)).fillna(False)


def calc_fuel_moisture_content(df: pd.DataFrame, logger: logging.Logger) -> pd.DataFrame:
    """
    Prepare emissions moisture from model outputs and weather DMC.

    :param df: Merged fire and consumption rows with moisture and optional surface-type fields.
    :param logger: Calling backend's logger for plot-specific missing-weather warnings.
    :return: Copy with moisture columns; omit grass/shrub rows without usable mc_dmc or
        weather DMC. Configured consumption-file moisture is never substituted for them.
    """
    result = derive_grass_duff_moisture(df)
    moisture = pd.to_numeric(result['mc_dmc'], errors='coerce').astype(float)
    invalid = _grass_rows(result) & (~np.isfinite(moisture) | moisture.lt(0))
    identifiers = result.get('#PlotId', pd.Series(None, index=result.index))
    for plot_id in identifiers.loc[invalid].drop_duplicates():
        logger.warning(
            'FOFEM emissions scenarios skipped: grass/shrub mc_dmc is missing and weather '
            'DMC is missing or invalid. Supply weather DMC and regenerate the fire results.',
            extra={'unique_id': plot_id, 'issue_code': 'fofem_grass_duff_moisture_missing'},
        )
    result['wfl10HourMoisture'] = result['mc_sa']
    result['DuffMoisture'] = result['mc_dmc']
    result['wfl1000HourMoisture'] = mc.dc_mc(dc=result['dc'].to_numpy())
    return result.loc[~invalid].copy()


def derive_grass_duff_moisture(df: pd.DataFrame) -> pd.DataFrame:
    """
    Complete grass and shrub-proxy mc_dmc from weather using the existing DMC conversion.

    :param df: Fire results with mc_dmc and optional weather dmc and surface-type columns.
    :return: Copy with missing grass/shrub mc_dmc calculated from finite nonnegative DMC,
        bounded to 10-200 as in ConPyro's forest moisture path. Existing values are preserved.
    """
    result = df.copy()
    if 'mc_dmc' not in result:
        return result
    moisture = pd.to_numeric(result['mc_dmc'], errors='coerce').astype(float)
    missing = ~np.isfinite(moisture) | moisture.lt(0)
    dmc = pd.to_numeric(result.get('dmc', pd.Series(np.nan, index=result.index)), errors='coerce').astype(float)
    use_weather = _grass_rows(result) & missing & np.isfinite(dmc) & dmc.ge(0)
    result['mc_dmc'] = moisture
    result.loc[use_weather, 'mc_dmc'] = mc.dmc_mc(dmc.loc[use_weather].clip(10, 200).to_numpy(dtype=float))
    return result
