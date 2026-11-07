"""Shared moisture handoff for the Python and batch FOFEM emissions backends."""
import logging

import numpy as np
import pandas as pd

from . import fwis_moisture_content as mc


def calc_fuel_moisture_content(df: pd.DataFrame, logger: logging.Logger) -> pd.DataFrame:
    """
    Prepare fire-weather moisture inputs while retaining configured grass duff moisture.

    :param df: Merged fire and consumption rows with moisture and optional surface-type fields.
    :param logger: Calling backend's logger for plot-specific fallback and skip warnings.
    :return: Copy with moisture columns; omit grass rows lacking both modelled and configured
        duff moisture. Log every affected plot without substituting a zero moisture value.
    """
    result = df.copy()
    category = result.get('surface_fuel_type', pd.Series('', index=result.index))
    stand = pd.to_numeric(result.get('stand_type', pd.Series(np.nan, index=result.index)), errors='coerce')
    fallback = (category.isin(['grass_herbs', 'shrubs']) | stand.eq(10)) & result['mc_dmc'].isna()
    configured = pd.to_numeric(result.get('DuffMoisture', pd.Series(np.nan, index=result.index)), errors='coerce')
    invalid = fallback & (~np.isfinite(configured) | configured.lt(0))
    identifiers = result.get('#PlotId', pd.Series(None, index=result.index))
    for plot_id in identifiers.loc[fallback & ~invalid].drop_duplicates():
        logger.warning(
            'Grass-model output has no duff moisture; FOFEM retains the configured '
            'DuffMoisture from the consumption file for these scenarios.',
            extra={'unique_id': plot_id, 'issue_code': 'fofem_grass_duff_moisture_fallback'},
        )
    for plot_id in identifiers.loc[invalid].drop_duplicates():
        logger.warning(
            'FOFEM emissions scenarios skipped: grass-model duff moisture is missing and '
            'the consumption file has no usable configured DuffMoisture.',
            extra={'unique_id': plot_id, 'issue_code': 'fofem_grass_duff_moisture_missing'},
        )
    result['wfl10HourMoisture'] = result['mc_sa']
    result['DuffMoisture'] = result['mc_dmc'].where(~fallback, configured)
    result['wfl1000HourMoisture'] = mc.dc_mc(dc=result['dc'].to_numpy())
    return result.loc[~invalid].copy()
