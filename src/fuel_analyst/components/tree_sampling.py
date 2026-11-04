"""Validate tree sampling settings and resolve thresholds for eligible parents."""
from copy import deepcopy
from numbers import Real

import numpy as np
import pandas as pd


class TreeSamplingError(ValueError):
    """An invalid tree sampling dictionary, rather than a plot measurement error."""

    issue_code = 'tree_sampling_invalid_config'


def _validate_thresholds(values: dict, base: dict, location: str) -> dict:
    """
    Merge and validate one pair of DBH thresholds.

    :param values: Partial thresholds supplied by the caller.
    :param base: Thresholds inherited by unspecified keys.
    :param location: Configuration path used in error messages.
    :return: Independent effective thresholds expressed in centimetres.
    """
    if not isinstance(values, dict):
        raise TreeSamplingError(f'Invalid tree sampling {location}: expected a dictionary.')
    unknown = set(values) - set(base)
    if unknown:
        raise TreeSamplingError(f'Invalid tree sampling {location}: unknown keys {list(unknown)!r}.')
    result = {**base, **values}
    for name, value in result.items():
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
            raise TreeSamplingError(f'Invalid tree sampling {location}.{name}: expected a finite real number.')
        try:
            numeric = float(value)
        except (OverflowError, ValueError):
            numeric = np.inf
        if not np.isfinite(numeric):
            raise TreeSamplingError(f'Invalid tree sampling {location}.{name}: expected a finite real number.')
        result[name] = numeric
    if not 0 <= result['small_tree_min'] < result['large_tree_min']:
        raise TreeSamplingError(
            f'Invalid tree sampling {location}: require 0 <= small_tree_min < large_tree_min.'
        )
    return result


def normalize_tree_sampling_params(params: dict | None) -> dict:
    """
    Validate and deep-copy global and per-protocol tree sampling settings.

    :param params: Partial settings, or None for defaults declared in fuel_analyst.py.
    :return: Independent normalized settings; invalid dictionaries raise TreeSamplingError.
    """
    # Resolve at call time: the entry-point module imports this validator during initialization.
    from ..fuel_analyst import default_tree_sampling_dict

    if params is None:
        params = {}
    if not isinstance(params, dict):
        raise TreeSamplingError('Invalid tree sampling settings: expected a dictionary.')
    unknown = set(params) - set(default_tree_sampling_dict)
    if unknown:
        raise TreeSamplingError(f'Invalid tree sampling settings: unknown keys {list(unknown)!r}.')
    result = deepcopy(default_tree_sampling_dict)
    supplied = deepcopy(params)
    result['dbh_thresholds_cm'] = _validate_thresholds(
        supplied.get('dbh_thresholds_cm', {}), result['dbh_thresholds_cm'], 'dbh_thresholds_cm'
    )
    column = supplied.get('protocol_column', result['protocol_column'])
    if column is not None and (not isinstance(column, str) or not column.strip()):
        raise TreeSamplingError('Invalid tree sampling protocol_column: expected None or a nonblank string.')
    overrides = supplied.get('protocol_overrides', result['protocol_overrides'])
    if not isinstance(overrides, dict):
        raise TreeSamplingError('Invalid tree sampling protocol_overrides: expected a dictionary.')
    if (column is None and overrides) or (column is not None and not overrides):
        raise TreeSamplingError('Invalid tree sampling: protocol_column and registered protocol_overrides are required together.')
    result['protocol_overrides'] = {}
    for label, values in overrides.items():
        if not isinstance(label, str) or not label.strip():
            raise TreeSamplingError('Invalid tree sampling protocol_overrides: labels must be nonblank strings.')
        result['protocol_overrides'][label] = _validate_thresholds(
            values, result['dbh_thresholds_cm'], f'protocol_overrides[{label!r}]'
        )
    result['protocol_column'] = column
    return result


def resolve_tree_sampling_thresholds(plots: pd.DataFrame, params: dict | None) -> pd.DataFrame:
    """
    Resolve sampling thresholds for an already filtered set of eligible parents.

    :param plots: Eligible parent records; preserve their order and index.
    :param params: Global thresholds and optional registered protocol overrides.
    :return: Threshold columns and sampling_issue_code; invalid plot labels yield
        missing thresholds without raising. Dictionary errors still raise.
    """
    settings = normalize_tree_sampling_params(params)
    column = settings['protocol_column']
    rows = []
    for _, plot in plots.iterrows():
        thresholds = settings['dbh_thresholds_cm']
        issue = ''
        if column is not None:
            label = plot.get(column)
            if isinstance(label, str) and label in settings['protocol_overrides']:
                thresholds = settings['protocol_overrides'][label]
            else:
                thresholds = {'small_tree_min': np.nan, 'large_tree_min': np.nan}
                issue = 'tree_sampling_invalid_protocol'
        rows.append({**thresholds, 'sampling_issue_code': issue})
    return pd.DataFrame(
        rows, index=plots.index,
        columns=['small_tree_min', 'large_tree_min', 'sampling_issue_code'],
    )