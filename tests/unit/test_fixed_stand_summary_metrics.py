"""Fixed stand-summary metrics are forced to the values in the default dictionaries."""

import copy
from pathlib import Path

import pandas as pd
import pytest

from fuel_analyst.fuel_analyst import (
    _enforce_fixed_stand_summary_metrics,
    default_conpyro_dict,
    default_fofem_consume_dict,
    default_stand_summary_dict,
    default_woody_debris_dict,
    fuel_analyst,
)


_SINGLE_METRIC_ENTRIES = [
    'conpyro_ht_ovrstry_live', 'conpyro_ht_midstry_live', 'conpyro_ht_midstry_dead',
    'conpyro_cbh_ovrstry', 'conpyro_cbh_midstry', 'conpyro_fsg',
]


def _entry(att_source: str, metrics) -> dict:
    return {'att_source': att_source, 'summary': ['live'], 'metrics': metrics, 'units': 'kgpm2'}


def test_cbd_with_none_metrics_is_normalized_to_empty_list() -> None:
    params = {'cbd': {'att_source': 'cbd', 'summary': ['live'], 'metrics': None, 'units': 'kgpm3'}}

    result = _enforce_fixed_stand_summary_metrics(params)

    assert result['cbd']['metrics'] == []


@pytest.mark.parametrize('name', _SINGLE_METRIC_ENTRIES)
@pytest.mark.parametrize('choice', ['min', 'max', 'mean'])
def test_conpyro_single_metric_duplicates_collapse_to_the_choice(name: str, choice: str, caplog) -> None:
    params = {name: _entry('ht', [choice, choice, choice])}

    result = _enforce_fixed_stand_summary_metrics(params)

    assert result[name]['metrics'] == [choice]
    assert not [r for r in caplog.records if getattr(r, 'issue_code', None) == 'single_metric_overridden']


@pytest.mark.parametrize('name', _SINGLE_METRIC_ENTRIES)
@pytest.mark.parametrize('requested', [['min', 'mean'], ['mean', 'min'], [], ['sum'], ['median']])
def test_conpyro_single_metric_entries_fall_back_to_default(name: str, requested: list[str]) -> None:
    params = {name: _entry('ht', requested)}

    result = _enforce_fixed_stand_summary_metrics(params)

    assert result[name]['metrics'] == ['mean']


def test_conpyro_single_metric_override_logs_one_warning(caplog) -> None:
    params = {'conpyro_fsg': _entry('cbh', ['min', 'mean'])}

    _enforce_fixed_stand_summary_metrics(params)

    records = [r for r in caplog.records if getattr(r, 'issue_code', None) == 'single_metric_overridden']
    assert len(records) == 1
    assert "'conpyro_fsg'" in records[0].getMessage()


@pytest.mark.parametrize('name', _SINGLE_METRIC_ENTRIES)
@pytest.mark.parametrize('choice', ['min', 'max', 'mean'])
def test_conpyro_single_metric_valid_choice_is_kept_silently(name: str, choice: str, caplog) -> None:
    params = {name: _entry('ht', [choice])}

    result = _enforce_fixed_stand_summary_metrics(params)

    assert result[name] is params[name]
    assert not [r for r in caplog.records if getattr(r, 'issue_code', None) == 'single_metric_overridden']


def test_correct_entries_are_kept_without_warning(caplog) -> None:
    params = {'cfl': _entry('cfl', ['sum'])}

    result = _enforce_fixed_stand_summary_metrics(params)

    assert result['cfl'] is params['cfl']
    assert not [r for r in caplog.records if getattr(r, 'issue_code', None) == 'fixed_metrics_overridden']


def test_default_conpyro_entries_pass_unchanged() -> None:
    entries = copy.deepcopy(default_conpyro_dict['stand_attributes'])

    result = _enforce_fixed_stand_summary_metrics(entries)

    assert result == entries
    assert all(result[name] is entries[name] for name in entries)


def test_default_stand_summary_cfl_is_sum_only() -> None:
    assert default_stand_summary_dict['cfl']['metrics'] == ['sum']


def test_duplicates_do_not_hide_a_real_override(caplog) -> None:
    params = {'cfl': _entry('cfl', ['mean', 'mean', 'sum'])}

    result = _enforce_fixed_stand_summary_metrics(params)

    assert result['cfl']['metrics'] == ['sum']
    assert len([r for r in caplog.records if getattr(r, 'issue_code', None) == 'fixed_metrics_overridden']) == 1


def test_entry_without_att_source_uses_its_key() -> None:
    params = {'foliage_fofem': {'summary': ['total'], 'metrics': ['mean'], 'units': 'kgpm2'}}

    result = _enforce_fixed_stand_summary_metrics(params)

    assert result['foliage_fofem']['metrics'] == ['sum']


def test_entry_without_metrics_key_is_forced() -> None:
    params = {'dens': {'att_source': 'dens', 'summary': ['live'], 'units': 'tpha'}}

    result = _enforce_fixed_stand_summary_metrics(params)

    assert result['dens']['metrics'] == ['sum']


@pytest.mark.parametrize(
    ('att_source', 'fixed'),
    [
        ('dens', ['sum']), ('ba', ['sum']), ('cfl', ['sum']),
        ('foliage', ['sum']), ('branches', ['sum']), ('wood', ['sum']), ('bark', ['sum']),
        ('cbd', []),
    ],
)
def test_fixed_attribute_metrics_are_forced(att_source: str, fixed: list[str]) -> None:
    params = {'entry': _entry(att_source, ['min', 'max', 'mean', 'sum'])}

    result = _enforce_fixed_stand_summary_metrics(params)

    assert result['entry']['metrics'] == fixed


@pytest.mark.parametrize(('att_source', 'requested', 'fixed'), [
    ('dens', ['sum', 'sum'], ['sum']),
    ('cfl', ['sum', 'sum', 'sum'], ['sum']),
    ('cbd', [], []),
])
def test_fixed_entry_duplicates_collapse_without_a_warning(
        att_source: str, requested: list[str], fixed: list[str], caplog
) -> None:
    params = {'entry': _entry(att_source, requested)}

    result = _enforce_fixed_stand_summary_metrics(params)

    assert result['entry']['metrics'] == fixed
    assert not [r for r in caplog.records if getattr(r, 'issue_code', None) == 'fixed_metrics_overridden']


def test_fixed_rule_wins_over_single_metric_rule() -> None:
    params = {'conpyro_ht_ovrstry_live': _entry('cfl', ['mean'])}

    result = _enforce_fixed_stand_summary_metrics(params)

    assert result['conpyro_ht_ovrstry_live']['metrics'] == ['sum']


@pytest.mark.integration
@pytest.mark.slow
def test_fuel_analyst_enforces_conpyro_and_fofem_overrides_in_a_real_run(tmp_path: Path) -> None:
    """Overrides reach the merged dictionary through conpyro_params and fofem_consume_params."""
    project_root = Path(__file__).resolve().parents[2]
    in_dir = str(project_root / 'examples' / 'data' / 'Survey123_Data')
    common = dict(
        in_dir=in_dir, surface_fire_intensity_model='Byram',
        gen_conpyro_df=True, gen_fofem_consume_df=True,
    )

    default_dir = tmp_path / 'default'
    fuel_analyst(out_dir=str(default_dir), **common)

    conpyro = copy.deepcopy(default_conpyro_dict)
    conpyro['stand_attributes']['conpyro_fsg']['metrics'] = ['min', 'mean']
    conpyro['stand_attributes']['conpyro_cfl_ovrstry']['metrics'] = ['mean']
    fofem = copy.deepcopy(default_fofem_consume_dict)
    fofem['canopy_fuels']['branches_fofem']['metrics'] = ['min']
    stand = copy.deepcopy(default_stand_summary_dict)
    # Same key as a ConPyro entry: the merge replaces it with conpyro_params' entry (existing behaviour).
    stand['conpyro_fsg'] = {**conpyro['stand_attributes']['conpyro_fsg'], 'metrics': ['max']}
    custom_dir = tmp_path / 'custom'
    woody = copy.deepcopy(default_woody_debris_dict)
    stand_before = copy.deepcopy(stand)
    conpyro_before = copy.deepcopy(conpyro)
    fofem_before = copy.deepcopy(fofem)
    woody_before = copy.deepcopy(woody)
    fuel_analyst(
        out_dir=str(custom_dir), stand_summary_params=stand, woody_debris_params=woody,
        conpyro_params=conpyro, fofem_consume_params=fofem, **common,
    )

    # fuel_analyst() must not mutate the dictionaries it was given: merging the ConPyro and FOFEM
    # entries (stand attributes and woody-debris classes) happens on internal copies.
    assert stand == stand_before
    assert conpyro == conpyro_before
    assert fofem == fofem_before
    assert woody == woody_before

    pd.testing.assert_frame_equal(
        pd.read_csv(default_dir / 'conpyro_df.csv', low_memory=False),
        pd.read_csv(custom_dir / 'conpyro_df.csv', low_memory=False),
    )
    pd.testing.assert_frame_equal(
        pd.read_csv(default_dir / 'fofem_consume_si_df.csv', low_memory=False),
        pd.read_csv(custom_dir / 'fofem_consume_si_df.csv', low_memory=False),
    )
    errors = pd.read_csv(custom_dir / 'fuelanalyst_errors.csv', low_memory=False)
    text = ' '.join(errors['Trees'].astype(str))
    assert "'conpyro_fsg'" in text
    assert "'conpyro_cfl_ovrstry'" in text
    assert "'branches_fofem'" in text


@pytest.mark.integration
@pytest.mark.slow
def test_fuel_analyst_forces_cfl_to_sum_and_reports_override(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[2]
    out_dir = tmp_path / 'fuel_analyst'
    params = copy.deepcopy(default_stand_summary_dict)
    params['cfl']['metrics'] = ['min', 'max', 'mean', 'sum']

    fuel_analyst(
        in_dir=str(project_root / 'examples' / 'data' / 'Survey123_Data'),
        out_dir=str(out_dir),
        surface_fire_intensity_model='Byram',
        stand_summary_params=params,
    )

    master = pd.read_csv(out_dir / 'master_fuel_df.csv', low_memory=False)
    cfl_columns = [c for c in master.columns if c.startswith('stand_cfl_')]
    assert cfl_columns
    assert all(c.endswith('_sum') for c in cfl_columns)
    errors = pd.read_csv(out_dir / 'fuelanalyst_errors.csv', low_memory=False)
    assert errors['Trees'].astype(str).str.contains("att_source 'cfl'").any()
    assert params['cfl']['metrics'] == ['min', 'max', 'mean', 'sum']


@pytest.mark.integration
@pytest.mark.slow
def test_fuel_analyst_reused_woody_dictionary_does_not_add_columns_to_a_later_run(tmp_path: Path) -> None:
    """A woody dictionary reused after a ConPyro/FOFEM run must behave like a fresh default."""
    project_root = Path(__file__).resolve().parents[2]
    in_dir = str(project_root / 'examples' / 'data' / 'Survey123_Data')
    woody = copy.deepcopy(default_woody_debris_dict)

    fuel_analyst(
        in_dir=in_dir, out_dir=str(tmp_path / 'with_flags'), surface_fire_intensity_model='Byram',
        woody_debris_params=woody, gen_conpyro_df=True, gen_fofem_consume_df=True,
    )
    fuel_analyst(
        in_dir=in_dir, out_dir=str(tmp_path / 'reused'), surface_fire_intensity_model='Byram',
        woody_debris_params=woody,
    )
    fuel_analyst(
        in_dir=in_dir, out_dir=str(tmp_path / 'fresh'), surface_fire_intensity_model='Byram',
    )

    reused = pd.read_csv(tmp_path / 'reused' / 'master_fuel_df.csv', nrows=0).columns
    fresh = pd.read_csv(tmp_path / 'fresh' / 'master_fuel_df.csv', nrows=0).columns
    assert list(reused) == list(fresh)
    assert list(woody['woody_debris_classes']) == ['canadian', 'us', 'modified']


def test_inputs_and_module_defaults_are_not_mutated() -> None:
    caller = {'cfl': _entry('cfl', ['mean'])}
    caller_before = copy.deepcopy(caller)
    defaults_before = copy.deepcopy(default_stand_summary_dict)

    _enforce_fixed_stand_summary_metrics(caller)
    _enforce_fixed_stand_summary_metrics(default_stand_summary_dict)

    assert caller == caller_before
    assert default_stand_summary_dict == defaults_before


def test_merged_conpyro_and_fofem_entries_are_enforced() -> None:
    merged = copy.deepcopy(default_stand_summary_dict)
    merged.update(copy.deepcopy(default_conpyro_dict['stand_attributes']))
    merged.update(copy.deepcopy(default_fofem_consume_dict['canopy_fuels']))
    merged['conpyro_cfl_ovrstry']['metrics'] = ['sum', 'mean']
    merged['conpyro_cbd_ovrstry']['metrics'] = ['sum']
    merged['branches_fofem']['metrics'] = ['min']

    result = _enforce_fixed_stand_summary_metrics(merged)

    assert result['conpyro_cfl_ovrstry']['metrics'] == ['sum']
    assert result['conpyro_cbd_ovrstry']['metrics'] == []
    assert result['branches_fofem']['metrics'] == ['sum']


@pytest.mark.parametrize('requested', [None, 'sum', 'mean', ('sum',)])
def test_odd_metrics_values_do_not_raise_for_fixed_entries(requested) -> None:
    params = {'dens': {'att_source': 'dens', 'summary': ['live'], 'metrics': requested, 'units': 'tpha'}}

    result = _enforce_fixed_stand_summary_metrics(params)

    # A bare string must become a real list: trees.py iterates `metrics`, and iterating 'sum'
    # would yield 's', 'u', 'm' and silently skip every metric.
    assert result['dens']['metrics'] == ['sum']


@pytest.mark.parametrize('requested', [None, 'mean', 'max', ('min',)])
def test_odd_metrics_values_do_not_raise_for_single_metric_entries(requested) -> None:
    params = {'conpyro_fsg': _entry('cbh', requested)}

    result = _enforce_fixed_stand_summary_metrics(params)

    expected = ['max'] if requested == 'max' else ['min'] if requested == ('min',) else ['mean']
    assert result['conpyro_fsg']['metrics'] == expected


def test_override_logs_one_warning_per_entry(caplog) -> None:
    params = {'cfl': _entry('cfl', ['mean', 'sum', 'sum'])}

    _enforce_fixed_stand_summary_metrics(params)

    records = [r for r in caplog.records if getattr(r, 'issue_code', None) == 'fixed_metrics_overridden']
    assert len(records) == 1
    assert "'cfl'" in records[0].getMessage()
    assert "['sum']" in records[0].getMessage()


def test_renamed_entry_is_enforced_by_att_source() -> None:
    params = {'my_cfl': _entry('cfl', ['mean'])}

    result = _enforce_fixed_stand_summary_metrics(params)

    assert result['my_cfl']['metrics'] == ['sum']


def test_single_metric_rule_does_not_apply_to_stand_summary_entries() -> None:
    params = {'ht': _entry('ht', ['max', 'mean']), 'cbh': _entry('cbh', ['min', 'max', 'mean'])}

    result = _enforce_fixed_stand_summary_metrics(params)

    assert result['ht'] is params['ht']
    assert result['cbh'] is params['cbh']


def test_weighted_attributes_are_not_restricted() -> None:
    params = {'ht': _entry('ht', ['min', 'max', 'mean'])}

    result = _enforce_fixed_stand_summary_metrics(params)

    assert result['ht'] is params['ht']
    assert result['ht']['metrics'] == ['min', 'max', 'mean']
