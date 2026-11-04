from copy import deepcopy
import importlib
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from fuel_analyst.components import tree_sampling as sampling


def test_component_defaults_follow_public_configuration(monkeypatch):
    api = importlib.import_module('fuel_analyst.fuel_analyst')
    configured = deepcopy(api.default_tree_sampling_dict)
    configured['dbh_thresholds_cm']['large_tree_min'] = 9.0
    monkeypatch.setattr(api, 'default_tree_sampling_dict', configured)
    result = sampling.normalize_tree_sampling_params(None)
    assert result['dbh_thresholds_cm']['large_tree_min'] == 9.0
    result['dbh_thresholds_cm']['small_tree_min'] = 0
    assert configured['dbh_thresholds_cm']['small_tree_min'] == 5.0


def test_component_imports_before_entry_point_without_cycle():
    environment = os.environ.copy()
    environment['PYTHONPATH'] = str(Path(__file__).resolve().parents[2] / 'src')
    result = subprocess.run(
        [sys.executable, '-c',
         'from fuel_analyst.components.tree_sampling import normalize_tree_sampling_params; '
         'assert normalize_tree_sampling_params(None)["dbh_thresholds_cm"]["large_tree_min"] == 12.5; '
         'from fuel_analyst.fuel_analyst import default_tree_sampling_dict; '
         'assert normalize_tree_sampling_params(None) == default_tree_sampling_dict'],
        env=environment, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('params', [
    [], False, {'typo': 1}, {'dbh_thresholds_cm': None},
    {'dbh_thresholds_cm': {'typo': 9}},
    *[{'dbh_thresholds_cm': {'large_tree_min': value}} for value in
      [True, np.bool_(False), '9', None, np.nan, np.inf, complex(9), -1, 0, 5]],
    {'dbh_thresholds_cm': {'small_tree_min': -1}},
    {'protocol_column': ''}, {'protocol_column': 1}, {'protocol_column': 'protocol'},
    {'protocol_overrides': {'NFI': {}}}, {'protocol_overrides': None},
    {'protocol_column': 'protocol', 'protocol_overrides': {'': {}}},
    {'protocol_column': 'protocol', 'protocol_overrides': {1: {}}},
    {'protocol_column': 'protocol', 'protocol_overrides': {'NFI': None}},
    {'protocol_column': 'protocol', 'protocol_overrides': {'NFI': {'small_tree_min': 15}}},
    {'protocol_column': 'protocol', 'protocol_overrides': {'NFI': {'large_tree_min': 5}}},
    {'protocol_column': 'protocol', 'protocol_overrides': {'NFI': {'typo': 9}}},
])
def test_configuration_errors_are_fatal(params):
    with pytest.raises(sampling.TreeSamplingError) as error:
        sampling.normalize_tree_sampling_params(params)
    assert isinstance(error.value, ValueError)
    assert error.value.issue_code == 'tree_sampling_invalid_config'


def test_defaults_and_nested_overrides_are_independent():
    original = {'protocol_column': 'protocol', 'protocol_overrides': {'CWC': {}, 'NFI': {'large_tree_min': 9}}}
    snapshot = deepcopy(original)
    normalized = sampling.normalize_tree_sampling_params(original)
    repeated = sampling.normalize_tree_sampling_params(normalized)
    assert normalized == repeated
    assert normalized['protocol_overrides']['CWC'] == {'small_tree_min': 5, 'large_tree_min': 12.5}
    assert normalized['protocol_overrides']['NFI'] == {'small_tree_min': 5, 'large_tree_min': 9}
    normalized['protocol_overrides']['NFI']['small_tree_min'] = 0
    assert repeated['protocol_overrides']['NFI']['small_tree_min'] == 5
    assert original == snapshot
    assert sampling.normalize_tree_sampling_params({}) == sampling.normalize_tree_sampling_params(None)
    api = importlib.import_module('fuel_analyst.fuel_analyst')
    assert api.default_tree_sampling_dict['protocol_overrides'] == {}


@pytest.mark.parametrize('value', [np.float64(9.05), np.int64(9), 9.05, 9])
def test_numeric_scalars_and_precision_are_preserved(value):
    result = sampling.normalize_tree_sampling_params({'dbh_thresholds_cm': {'large_tree_min': value}})
    assert result['dbh_thresholds_cm']['large_tree_min'] == value


def test_public_default_and_early_error_report(tmp_path):
    api = importlib.import_module('fuel_analyst.fuel_analyst')
    normalized = sampling.normalize_tree_sampling_params(None)
    assert normalized == api.default_tree_sampling_dict
    assert normalized is not api.default_tree_sampling_dict
    assert normalized['dbh_thresholds_cm'] is not api.default_tree_sampling_dict['dbh_thresholds_cm']
    out = tmp_path / 'out'
    with pytest.raises(sampling.TreeSamplingError):
        api.fuel_analyst(str(tmp_path/'nonexistent'), str(out), 'Byram', tree_sampling_params={'typo': 1})
    report = pd.read_csv(out/'fuelanalyst_errors.csv')
    assert report['Trees'].str.contains('tree sampling', case=False).any()
    assert not (out/'1_Plot_Attributes').exists()


def test_resolver_keeps_order_and_marks_bad_labels_without_raising():
    settings = {'protocol_column': 'protocol', 'protocol_overrides': {'CWC': {}, 'NFI': {'large_tree_min': 9}}}
    plots = pd.DataFrame({'protocol': ['NFI', 'CWC', 'nfi', '', None, 1, ['NFI'], 'NFI ']}, index=[7, 3, 2, 8, 9, 11, 12, 13])
    result = sampling.resolve_tree_sampling_thresholds(plots, settings)
    assert result.index.tolist() == plots.index.tolist()
    assert result.large_tree_min.iloc[:2].tolist() == [9, 12.5]
    assert result.sampling_issue_code.iloc[:2].eq('').all()
    assert result.large_tree_min.iloc[2:].isna().all()
    assert result.sampling_issue_code.iloc[2:].eq('tree_sampling_invalid_protocol').all()
    missing = sampling.resolve_tree_sampling_thresholds(pd.DataFrame(index=[4, 1]), settings)
    assert missing.large_tree_min.isna().all()
    empty = sampling.resolve_tree_sampling_thresholds(pd.DataFrame(), settings)
    assert empty.empty and list(empty) == ['small_tree_min', 'large_tree_min', 'sampling_issue_code']
    base = sampling.resolve_tree_sampling_thresholds(plots, None)
    assert base.large_tree_min.eq(12.5).all()
    assert base.sampling_issue_code.eq('').all()