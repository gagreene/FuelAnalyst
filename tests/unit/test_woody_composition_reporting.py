"""Species-source diagnostics must describe the resolved outcome for each plot."""
import logging

import numpy as np
import pandas as pd
import pytest

from fuel_analyst.components import woody_debris as wd


@pytest.mark.parametrize('tree_values', [('FDI:100', None), (None, None), None])
def test_merge_assembles_available_sources_without_premature_logs(caplog, tree_values):
    plots = pd.DataFrame({'unique_id': ['A', 'B']})
    if tree_values is not None:
        plots['stand_spp_comp_woody'] = tree_values
    parents = pd.DataFrame({'GlobalID': ['gA', 'gB'], 'unique_id': ['A', 'B']})
    pieces = pd.DataFrame({'ParentGlobalID': ['gA', 'gB'], 'woody_species': ['FDI', 'FDI'],
                           'woody_spp_percent_wtd': [100.0, 100.0]})
    manual = pd.DataFrame(columns=['unique_id', 'spp_comp_type', 'spp_comp_code', 'spp_comp_percent'])
    with caplog.at_level(logging.INFO, logger=wd.__name__):
        composition = wd._merge_spp_comp(plots, parents, pieces, manual)
        selected, _ = wd._resolve_spp_comp_type(
            parents.assign(spp_comp_type='transect_data'), composition)
    assert selected['spp_comp_type'].tolist() == ['transect_data', 'transect_data']
    assert caplog.records == []


@pytest.mark.parametrize('measurement', [
    'stand_duff_depth_cm', 'stand_litter_depth_cm', 'woody_tally_count',
    't1_woody_tally_0to2', 't1_woody_tally_28to30',
    't2_woody_tally_0to2', 't2_woody_tally_28to30',
])
def test_missing_source_reports_error_preserves_missing_biomass_and_continues(caplog, measurement):
    plots = pd.DataFrame({'unique_id': ['missing', 'valid'],
                          'spp_comp_type': ['transect_data', 'transect_data'],
                          'stand_duff_depth_cm': [2.0, 2.0],
                          'stand_litter_depth_cm': [1.0, 1.0]})
    plots.loc[0, ['stand_duff_depth_cm', 'stand_litter_depth_cm']] = 0.0
    plots.loc[0, measurement] = 3.0
    composition = pd.DataFrame({'unique_id': ['valid'], 'spp_comp_type': ['transect_data'],
                                'stand_duff_bd_kgpm3': [50.0], 'stand_litter_bd_kgpm3': [30.0]})
    with caplog.at_level(logging.INFO, logger=wd.__name__):
        selected, _ = wd._resolve_spp_comp_type(plots, composition)
    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.levelno == logging.ERROR
    assert record.unique_id == 'missing'
    assert record.issue_code == 'woody_species_composition_unavailable'
    assert 'transect_data' in record.message
    assert 'no usable species composition' in record.message.lower()
    assert 'biomass' in record.message
    result, _ = wd._calc_plot_duff_litter_biomass(pd.DataFrame(), selected, composition)
    assert result.loc[0, ['ffl_duff_kgpm2', 'ffl_litter_kgpm2']].isna().all()
    assert result.loc[1, 'ffl_duff_kgpm2'] == pytest.approx(1.0)
    assert result.loc[1, 'ffl_litter_kgpm2'] == pytest.approx(0.3)


@pytest.mark.parametrize('value', [0.0, np.nan])
def test_missing_source_without_positive_measurements_is_silent(caplog, value):
    plots = pd.DataFrame({'unique_id': ['empty'], 'spp_comp_type': ['tree_data'],
                          'stand_duff_depth_cm': [value], 'stand_litter_depth_cm': [value],
                          'woody_tally_count': [value]})
    composition = pd.DataFrame(columns=['unique_id', 'spp_comp_type'])
    with caplog.at_level(logging.INFO, logger=wd.__name__):
        selected, _ = wd._resolve_spp_comp_type(plots, composition)
    assert selected.loc[0, 'spp_comp_type'] == 'tree_data'
    assert caplog.records == []


@pytest.mark.parametrize('declared', ['tree_data', 'transect_data', 'manual_entry'])
def test_selected_source_takes_precedence_when_all_sources_exist(caplog, declared):
    plots = pd.DataFrame({'unique_id': ['A'], 'spp_comp_type': [declared]})
    composition = pd.DataFrame({'unique_id': ['A'] * 3,
                                'spp_comp_type': ['tree_data', 'transect_data', 'manual_entry']})
    with caplog.at_level(logging.INFO, logger=wd.__name__):
        selected, _ = wd._resolve_spp_comp_type(plots, composition)
    assert selected.loc[0, 'spp_comp_type'] == declared
    assert caplog.records == []

@pytest.mark.parametrize(('declared', 'replacement'), [
    ('tree_data', 'transect_data'), ('tree_data', 'manual_entry'),
    ('transect_data', 'tree_data'), ('transect_data', 'manual_entry'),
    ('manual_entry', 'tree_data'), ('manual_entry', 'transect_data'),
])
def test_successful_fallback_reports_exact_selected_and_replacement_once(caplog, declared, replacement):
    plots = pd.DataFrame({'unique_id': ['A'], 'spp_comp_type': [declared]})
    composition = pd.DataFrame({'unique_id': ['A'], 'spp_comp_type': [replacement]})
    with caplog.at_level(logging.INFO, logger=wd.__name__):
        selected, _ = wd._resolve_spp_comp_type(plots, composition)
    assert selected.loc[0, 'spp_comp_type'] == replacement
    assert selected.loc[0, 'spp_comp_type_declared'] == declared
    assert len(caplog.records) == 1
    assert caplog.records[0].levelno == logging.INFO
    assert caplog.records[0].message == (
        f"Declared spp_comp_type '{declared}' had no matching species composition data; "
        f"used '{replacement}' instead.")


@pytest.mark.parametrize(('declared', 'expected'), [
    ('tree_data', 'transect_data'), ('transect_data', 'tree_data'), ('manual_entry', 'tree_data'),
])
def test_unavailable_selection_uses_existing_fallback_priority(caplog, declared, expected):
    alternatives = [source for source in ['tree_data', 'transect_data', 'manual_entry'] if source != declared]
    plots = pd.DataFrame({'unique_id': ['A'], 'spp_comp_type': [declared]})
    composition = pd.DataFrame({'unique_id': ['A', 'A'], 'spp_comp_type': alternatives[::-1]})
    with caplog.at_level(logging.INFO, logger=wd.__name__):
        selected, _ = wd._resolve_spp_comp_type(plots, composition)
    assert selected.loc[0, 'spp_comp_type'] == expected
    assert len(caplog.records) == 1
