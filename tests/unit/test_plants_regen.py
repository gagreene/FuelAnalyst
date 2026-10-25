import logging
import os

import numpy as np
import pandas as pd
import pytest

from fuel_analyst.components import error_handling, helper
from fuel_analyst.components.plants_regen import (
    _PHOTOLOAD_CODES,
    _calc_pc_flammable,
    _calc_plants_fccs_fofem_attributes,
    _get_dom_substrate,
    _get_photoload_biomass,
    _process_regen,
    _process_top_five_spp,
)

from fuel_calculation_fixtures import _depth_frame




def test_calc_pc_flammable_computes_survey123_formula():
    df = pd.DataFrame({'unique_id': ['A'], 'pc_rock': [10.0], 'pc_mineral_soil': [20.0]})
    result, keep = _calc_pc_flammable(df)
    assert result.loc[0, 'pc_nonflammable'] == 30.0
    assert result.loc[0, 'pc_flammable'] == 70.0
    assert keep == ['pc_nonflammable', 'pc_flammable']


def test_calc_pc_flammable_defaults_to_fully_flammable_when_columns_are_missing(caplog):
    df = pd.DataFrame({'unique_id': ['A'], 'other_col': [1]})
    with caplog.at_level(logging.INFO, logger='fuel_analyst.components.plants_regen'):
        result, _ = _calc_pc_flammable(df)
    assert result.loc[0, 'pc_nonflammable'] == 0.0
    assert result.loc[0, 'pc_flammable'] == 100.0
    assert 'No pc_rock or pc_mineral_soil cover provided' in caplog.records[0].message


def test_calc_pc_flammable_defaults_to_fully_flammable_when_no_data_provided(caplog):
    df = pd.DataFrame({'unique_id': ['A'], 'pc_rock': [np.nan], 'pc_mineral_soil': [np.nan]})
    with caplog.at_level(logging.INFO, logger='fuel_analyst.components.plants_regen'):
        result, _ = _calc_pc_flammable(df)
    assert result.loc[0, 'pc_nonflammable'] == 0.0
    assert result.loc[0, 'pc_flammable'] == 100.0
    assert len(caplog.records) == 1
    assert 'No pc_rock or pc_mineral_soil cover provided' in caplog.records[0].message
    assert caplog.records[0].unique_id == 'A'


def test_calc_pc_flammable_defaults_to_fully_flammable_when_result_out_of_range(caplog):
    df = pd.DataFrame({'unique_id': ['A'], 'pc_rock': [60.0], 'pc_mineral_soil': [60.0]})
    with caplog.at_level(logging.INFO, logger='fuel_analyst.components.plants_regen'):
        result, _ = _calc_pc_flammable(df)
    assert result.loc[0, 'pc_nonflammable'] == 0.0
    assert result.loc[0, 'pc_flammable'] == 100.0
    assert 'outside the valid 0-100 range' in caplog.records[0].message


def test_calc_pc_flammable_handles_missing_unique_id_column(caplog):
    df = pd.DataFrame({'pc_rock': [np.nan], 'pc_mineral_soil': [np.nan]})
    with caplog.at_level(logging.INFO, logger='fuel_analyst.components.plants_regen'):
        result, _ = _calc_pc_flammable(df)
    assert result.loc[0, 'pc_flammable'] == 100.0
    assert len(caplog.records) == 1
    assert caplog.records[0].unique_id == 0


def test_calc_pc_flammable_treats_one_missing_value_as_zero(caplog):
    df = pd.DataFrame({'unique_id': ['A'], 'pc_rock': [5.0], 'pc_mineral_soil': [np.nan]})
    with caplog.at_level(logging.INFO, logger='fuel_analyst.components.plants_regen'):
        result, _ = _calc_pc_flammable(df)
    assert result.loc[0, 'pc_nonflammable'] == 5.0
    assert result.loc[0, 'pc_flammable'] == 95.0
    assert caplog.records == []


def test_calc_plants_fccs_fofem_attributes_aggregates_duplicate_shrubs():
    row = {'dom_substrate': 'SL'}
    for i in range(1, 6):
        row[f'pc_species_{i}_label'] = None
        row[f'pc_species_{i}_plCode'] = None
        row[f'pc_species_{i}_pct'] = 0
    row.update({
        'pc_species_1_label': 'Shrub', 'pc_species_1_plCode': 'ARTR', 'pc_species_1_pct': 60,
        'pc_species_2_label': 'Shrub', 'pc_species_2_plCode': 'ARTR', 'pc_species_2_pct': 20,
        'pc_species_3_label': 'Shrub', 'pc_species_3_plCode': 'VAGL', 'pc_species_3_pct': 20,
    })
    result, keep = _calc_plants_fccs_fofem_attributes(pd.DataFrame([row]))
    assert result.loc[0, 'fccs_shrub_species'] == 'ARTR:80.0 | VAGL:20.0'
    assert result.loc[0, 'fofem_shrub_group'] == 'Sagebrush'
    assert keep == ['fofem_shrub_group']


@pytest.mark.parametrize(
    ('covers', 'height', 'expected'),
    [
        ([0, 0, 0, 60], 1.0, 'SL'),
        ([0, 0, 0, 60], 2.0, 'ST'),
        ([60, 0, 0, 0], 0.0, 'BY'),
        ([0, 60, 0, 0], 0.0, 'HG'),
        ([0, 0, 60, 0], 0.0, 'HF'),
        ([0, 30, 30, 0], 0.0, 'HE'),
    ],
)
def test_get_dom_substrate_rules(covers, height, expected):
    df = pd.DataFrame([dict(zip(
        ['bryoid_pct_total', 'grass_pct_total', 'herb_forb_pct_total', 'shrubs_pct_total'], covers
    )) | {'shrubs_ht_avg': height}])
    result, keep = _get_dom_substrate(df)
    assert result.loc[0, 'dom_substrate'] == expected
    assert keep == ['dom_substrate']


@pytest.mark.parametrize(
    'code',
    ['AMAL', 'ARLA', 'CARU', 'FESC', 'MARE', 'SYAL', 'VAGL', 'VASC', 'XETE'],
)
def test_get_photoload_biomass_models_pass_through_origin(code):
    assert _get_photoload_biomass(code, 0, 20) == pytest.approx(0)


def test_get_photoload_biomass_scales_with_height_and_handles_special_codes():
    reference_biomass = _get_photoload_biomass('VAGL', 20, 35.56)
    assert _get_photoload_biomass('VAGL', 20, 71.12) == pytest.approx(2 * reference_biomass)
    assert _get_photoload_biomass('MOSS', 50, 10) == 0
    assert _get_photoload_biomass('TREE', 50, 10) == 0
    assert np.isnan(_get_photoload_biomass('UNKNOWN', 20, 10))


@pytest.mark.parametrize(
    ('code', 'reference_height', 'expected'),
    [
        ('AMAL', 35.56, 0.0690181 * (np.exp(0.0240242 * 50) - 1)),
        ('ARLA', 30.48, 0.0005745 * np.power(50, 1.16228)),
        ('CARU', 20.30, 0.0117766 * (np.exp(0.0379728 * 50) - 1)),
        ('FESC', 30.5, 0.0161917 * (np.exp(0.0330081 * 50) - 1)),
        ('MARE', 10.16, 0.000733871 * np.power(50, 1.16779)),
        ('SYAL', 35.56, 0.00119555 * 50 + 0.0000169686 * np.power(50, 2)),
        ('VAGL', 35.56, 0.398329 * (np.exp(0.0109776 * 50) - 1)),
        ('VASC', 17.78, 0.0025455 * 50),
        ('XETE', 25.4, 0.00366616 * 50),
    ],
)
def test_get_photoload_biomass_uses_final_models(code, reference_height, expected):
    assert _get_photoload_biomass(code, 50, reference_height) == pytest.approx(expected)

def test_process_regen_normalizes_sampled_proportion_and_maps_to_plot():
    plots = pd.DataFrame({'GlobalID': ['p1', 'p2']})
    regen = pd.DataFrame({
        'ParentGlobalID': ['p1', 'p1'],
        'rgn_live_small_cnt': [2.0, 1.0], 'rgn_small_plot_proportion': [0.5, 1.0],
        'rgn_live_tall_cnt': [1.0, 2.0], 'rgn_tall_plot_proportion': [1.0, 0.5],
    })
    result, _, keep = _process_regen(plots, regen)
    assert result['dens_regen_live_small_ha'].tolist() == [500.0, 0.0]
    assert result['dens_regen_live_tall_ha'].tolist() == [500.0, 0.0]
    assert keep == ['dens_regen_live_small_ha', 'dens_regen_live_tall_ha']


@pytest.mark.parametrize(
    ('covers', 'heights', 'species', 'expected'),
    [
        ([50, 20], [10, np.nan], None, 0.1),
        ([50, 20], [10, 100], ['ACCA', None], 0.1),
        ([50, 20], [10, np.inf], None, 0.1),
        ([50, np.inf], [10, 100], None, 0.1),
        ([50, -20], [10, 100], None, 0.1),
        ([50, 20], [10, -100], None, 0.1),
        ([], [], None, np.nan),
        ([20], [0], None, 0.0),
    ],
)
def test_process_top_five_spp_depth_handles_unusable_observations(covers, heights, species, expected):
    # Existing PhotoLoad equations evaluate fractional powers on deliberate negative cover.
    with np.errstate(invalid="ignore"):
        result, _ = _process_top_five_spp(_depth_frame(covers, heights, species))
    if np.isnan(expected):
        assert np.isnan(result.loc[0, 'fuel_bed_depth_m'])
    else:
        assert result.loc[0, 'fuel_bed_depth_m'] == pytest.approx(expected)


def test_process_top_five_spp_depth_ignores_missing_fifth_species():
    result, _ = _process_top_five_spp(_depth_frame([50, 20, 15, 10], [10, 20, 30, 40]))
    assert result.loc[0, 'fuel_bed_depth_m'] == pytest.approx(1750 / 95 / 100)


def test_process_top_five_spp_depth_weights_all_species():
    result, keep = _process_top_five_spp(_depth_frame([50, 20, 15, 10, 5], [10, 20, 30, 40, 100]))
    assert result.loc[0, 'fuel_bed_depth_m'] == pytest.approx(0.225)
    assert keep == ['fuel_bed_depth_m', 'bryoid_kgpm2', 'grass_kgpm2', 'herb_forb_kgpm2', 'shrubs_kgpm2']


# ── Species that are not in plant_photoload.csv ─────────────────────────────────────────────────────────────────────

LOGGER_NAME = 'fuel_analyst.components.plants_regen'


def _species_frame(species, unique_id='plot_1', other=None, other_group=None):
    """Build a one-plot frame with 50% cover and 10 cm height for each listed species code (None leaves a slot empty).

    other is the alternate name entered for species 1 when it is OTHER, and other_group the functional group chosen with
    it; the group column is only present when a group is given, as in an export from an older version of the form."""
    row = {'unique_id': unique_id}
    for index in range(1, 6):
        offset = index - 1
        code = species[offset] if offset < len(species) else None
        row.update({
            f'pc_species_{index}': code,
            f'pc_species_{index}_other': other if (index == 1 and other is not None) else None,
            f'pc_species_{index}_pct': 50.0 if code is not None else np.nan,
            f'pc_species_{index}_ht': 10.0 if code is not None else np.nan,
        })
    if other_group is not None:
        for index in range(1, 6):
            row[f'pc_species_{index}_other_group'] = other_group if index == 1 else None
    return pd.DataFrame([row])


def _species_warnings(caplog, issue_code=None):
    """Return the logged records raised for plant species, optionally only those with one issue code."""
    return [r for r in caplog.records
            if getattr(r, 'issue_code', '').startswith('plant_species')
            and (issue_code is None or r.issue_code == issue_code)]


def test_unlisted_species_is_warned_with_plot_and_issue_code(caplog):
    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        result, _ = _process_top_five_spp(_species_frame(['ZZZZ']))
    records = _species_warnings(caplog, 'plant_species_not_in_table')
    assert len(records) == 1
    assert records[0].unique_id == 'plot_1'
    assert "'ZZZZ'" in records[0].message and 'plant_photoload.csv' in records[0].message
    assert result.loc[0, 'pc_species_kgpm2'] == 0.0


def test_listed_species_is_not_warned(caplog):
    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        _process_top_five_spp(_species_frame(['ACCA', 'VAGL']))
    assert not _species_warnings(caplog)


@pytest.mark.parametrize('code', ['NO_SPP', '', '   ', None])
def test_no_species_values_are_not_warned(code, caplog):
    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        _process_top_five_spp(_species_frame([code]))
    assert not _species_warnings(caplog)


def test_other_species_uses_the_alternate_code_and_warns_only_when_it_is_unlisted(caplog):
    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        _process_top_five_spp(_species_frame(['OTHER'], other='ACCA'))
        assert not _species_warnings(caplog)
        _process_top_five_spp(_species_frame(['OTHER'], other='Fireweed'))
    records = _species_warnings(caplog, 'plant_species_not_in_table')
    assert len(records) == 1 and "'Fireweed'" in records[0].message


@pytest.mark.parametrize('alternate', [None, '', '   '])
def test_other_species_without_an_alternate_code_is_warned(alternate, caplog):
    frame = _species_frame(['OTHER'])
    frame['pc_species_1_other'] = alternate
    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        result, _ = _process_top_five_spp(frame)
    records = _species_warnings(caplog, 'plant_species_other_no_name')
    assert len(records) == 1
    assert records[0].unique_id == 'plot_1'
    assert 'pc_species_1_other' in records[0].message
    assert not _species_warnings(caplog, 'plant_species_not_in_table')
    assert result.loc[0, 'pc_species_kgpm2'] == 0.0


def test_other_species_warning_names_the_slot_and_skips_named_and_non_other_species(caplog):
    frame = _species_frame(['ACCA', 'OTHER', 'OTHER'])
    frame['pc_species_2_other'] = 'VAGL'
    frame['pc_species_3_other'] = None
    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        _process_top_five_spp(frame)
    records = _species_warnings(caplog, 'plant_species_other_no_name')
    assert len(records) == 1 and 'pc_species_3_other' in records[0].message


def test_no_species_adds_nothing_and_its_cover_and_height_are_ignored(caplog):
    # NO_SPP is a form value for no further species. Even if cover and height are entered with it (the form hides them),
    # it adds no biomass and does not count toward fuel bed depth or any group, and it is not warned about.
    frame = _species_frame(['ACCA', 'NO_SPP'])
    frame['pc_species_2_pct'] = 40.0
    frame['pc_species_2_ht'] = 50.0
    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        result, _ = _process_top_five_spp(frame)
    only_listed, _ = _process_top_five_spp(_species_frame(['ACCA']))
    assert result.loc[0, 'pc_species_2_kgpm2'] == 0
    assert result.loc[0, 'pc_species_kgpm2'] == only_listed.loc[0, 'pc_species_kgpm2'] > 0
    assert result.loc[0, 'fuel_bed_depth_m'] == only_listed.loc[0, 'fuel_bed_depth_m']
    for column in ('herb_forb_pct_total', 'herbs_pct_total', 'grass_pct_total', 'shrubs_pct_total', 'bryoid_pct_total'):
        assert result.loc[0, column] == only_listed.loc[0, column]
    assert not _species_warnings(caplog)


def test_no_species_alone_gives_zero_biomass_and_no_fuel_bed_depth():
    result, _ = _process_top_five_spp(_species_frame(['NO_SPP']))
    assert result.loc[0, 'pc_species_kgpm2'] == 0
    assert result.loc[0, 'grass_kgpm2'] == result.loc[0, 'herb_forb_kgpm2'] == result.loc[0, 'shrubs_kgpm2'] == 0
    assert np.isnan(result.loc[0, 'fuel_bed_depth_m'])


# ── OTHER species that are not in the table: estimated from the functional group chosen with them ──────────────────

def _expected_group_mean(group, pct, height):
    """Average, over the species of one group in plant_photoload.csv, of each species' equation, computed from the CSV."""
    table = _species_table()
    codes = table.loc[(table['func_group'] == group) & table['pl_code'].notna(), 'pl_code']
    return float(np.mean([_get_photoload_biomass(code, pct, height) for code in codes]))


@pytest.mark.parametrize('group, total_column', [
    ('Herb/Forb', 'herb_forb_kgpm2'), ('Grass', 'grass_kgpm2'), ('Shrub', 'shrubs_kgpm2'),
])
def test_other_species_not_in_the_table_gets_the_average_of_its_functional_group(group, total_column, caplog):
    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        result, _ = _process_top_five_spp(_species_frame(['OTHER'], other='Fireweed', other_group=group))
    expected = _expected_group_mean(group, 50.0, 10.0)
    assert expected > 0
    assert result.loc[0, 'pc_species_1_kgpm2'] == pytest.approx(expected)
    assert result.loc[0, 'pc_species_kgpm2'] == pytest.approx(expected)
    # it joins the totals of the group the crew chose, and no other group
    assert result.loc[0, total_column] == pytest.approx(expected)
    others = {'herb_forb_kgpm2', 'grass_kgpm2', 'shrubs_kgpm2'} - {total_column}
    assert all(result.loc[0, column] == 0 for column in others)
    assert result.loc[0, 'pc_species_1_label'] == f'[{group}] OTHER - Fireweed'
    estimated = _species_warnings(caplog, 'plant_species_other_estimated')
    assert len(estimated) == 1 and "'Fireweed'" in estimated[0].message and group in estimated[0].message
    assert not _species_warnings(caplog, 'plant_species_not_in_table')


def test_other_species_group_averages_follow_the_species_of_each_group():
    # Grass (FESC, CARU, XETE), herb/forb (almost all ARLA), and shrub (AMAL, SYAL, VAGL, MARE, VASC, ARLA) differ
    means = {g: _expected_group_mean(g, 50.0, 10.0) for g in ('Herb/Forb', 'Grass', 'Shrub')}
    assert len({round(v, 6) for v in means.values()}) == 3
    assert means['Shrub'] > means['Grass'] > means['Herb/Forb'] > 0


def test_other_species_estimates_each_plot_from_its_own_group_and_cover():
    frame = pd.concat([_species_frame(['OTHER'], unique_id='A', other='x', other_group='Grass'),
                       _species_frame(['OTHER'], unique_id='B', other='y', other_group='Shrub')], ignore_index=True)
    frame.loc[1, 'pc_species_1_pct'] = 20.0
    frame.loc[1, 'pc_species_1_ht'] = 40.0
    result, _ = _process_top_five_spp(frame)
    assert result.loc[0, 'pc_species_1_kgpm2'] == pytest.approx(_expected_group_mean('Grass', 50.0, 10.0))
    assert result.loc[1, 'pc_species_1_kgpm2'] == pytest.approx(_expected_group_mean('Shrub', 20.0, 40.0))


def test_other_moss_or_lichen_has_zero_biomass_but_its_cover_counts():
    result, _ = _process_top_five_spp(_species_frame(['OTHER'], other='Fringe moss', other_group='Moss/Lichen'))
    assert result.loc[0, 'pc_species_1_kgpm2'] == 0
    assert result.loc[0, 'bryoid_pct_total'] == 50.0
    assert result.loc[0, 'pc_species_kgpm2'] == 0


def test_other_species_in_the_table_uses_the_table_not_the_group_estimate(caplog):
    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        result, _ = _process_top_five_spp(_species_frame(['OTHER'], other='ACCA', other_group='Shrub'))
    listed, _ = _process_top_five_spp(_species_frame(['ACCA']))
    assert result.loc[0, 'pc_species_1_kgpm2'] == pytest.approx(listed.loc[0, 'pc_species_1_kgpm2'])
    assert result.loc[0, 'herb_forb_kgpm2'] > 0 and result.loc[0, 'shrubs_kgpm2'] == 0
    assert not _species_warnings(caplog)


def test_other_species_with_a_group_but_no_name_is_estimated_and_counts_toward_fuel_bed_depth(caplog):
    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        result, _ = _process_top_five_spp(_species_frame(['OTHER'], other='', other_group='Shrub'))
    assert result.loc[0, 'pc_species_1'] == 'OTHER'
    assert result.loc[0, 'pc_species_1_kgpm2'] == pytest.approx(_expected_group_mean('Shrub', 50.0, 10.0))
    assert result.loc[0, 'pc_species_1_label'] == '[Shrub] OTHER - no name'
    assert result.loc[0, 'fuel_bed_depth_m'] == pytest.approx(0.1)
    estimated = _species_warnings(caplog, 'plant_species_other_estimated')
    assert len(estimated) == 1 and 'with no name' in estimated[0].message
    assert not _species_warnings(caplog, 'plant_species_other_no_name')


def test_other_species_with_no_name_and_no_group_still_cannot_be_estimated(caplog):
    frame = _species_frame(['OTHER'], other='', other_group='')
    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        result, _ = _process_top_five_spp(frame)
    assert result.loc[0, 'pc_species_kgpm2'] == 0
    assert len(_species_warnings(caplog, 'plant_species_other_no_name')) == 1
    assert not _species_warnings(caplog, 'plant_species_other_estimated')


def test_other_species_with_an_unknown_group_is_not_estimated(caplog):
    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        result, _ = _process_top_five_spp(_species_frame(['OTHER'], other='Fireweed', other_group='Orchid'))
    assert result.loc[0, 'pc_species_kgpm2'] == 0
    assert len(_species_warnings(caplog, 'plant_species_not_in_table')) == 1
    assert not _species_warnings(caplog, 'plant_species_other_estimated')


def test_estimated_other_species_reaches_the_error_report(tmp_path):
    error_handling.start_run()
    _process_top_five_spp(_species_frame(['OTHER', 'ACCA'], unique_id='Demo_P03', other='Fireweed', other_group='Herb/Forb'))
    report = tmp_path / 'errors.csv'
    error_handling.write_report(str(report))
    rows = pd.read_csv(report)
    row = rows[rows['unique_id'] == 'Demo_P03']
    assert len(row) == 1
    message = row.iloc[0]['Plants and Regeneration']
    assert '[WARNING]' in message and "'Fireweed'" in message and 'average of the' in message


def test_species_codes_are_case_sensitive(caplog):
    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        _process_top_five_spp(_species_frame(['acca']))
    assert _species_warnings(caplog, 'plant_species_not_in_table')


def test_each_unlisted_species_slot_is_warned_separately(caplog):
    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        _process_top_five_spp(_species_frame(['ZZZZ', 'ACCA', 'YYYY']))
    messages = [r.message for r in _species_warnings(caplog, 'plant_species_not_in_table')]
    assert len(messages) == 2
    assert any("'ZZZZ' (species 1)" in m for m in messages) and any("'YYYY' (species 3)" in m for m in messages)


def test_species_without_a_unique_id_column_is_warned_by_row_index(caplog):
    frame = _species_frame(['ZZZZ']).drop(columns='unique_id')
    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        _process_top_five_spp(frame)
    records = _species_warnings(caplog, 'plant_species_not_in_table')
    assert len(records) == 1 and records[0].unique_id == 0


def test_series_without_an_equation_is_warned(monkeypatch, caplog):
    table = pd.DataFrame({'name': ['ACCA', 'NEWW'],
                          'label': ["[Herb/Forb] ACCA - deer's foot", '[Herb/Forb] NEWW - new species'],
                          'pl_code': ['ARLA', 'ARLX']})
    monkeypatch.setattr(helper, 'get_df', lambda path: table.copy())
    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        _process_top_five_spp(_species_frame(['NEWW']))
    records = _species_warnings(caplog, 'plant_species_no_equation')
    assert len(records) == 1 and "'ARLX'" in records[0].message


def test_unlisted_species_reaches_the_error_report(tmp_path):
    error_handling.start_run()
    _process_top_five_spp(_species_frame(['ZZZZ', 'ACCA'], unique_id='Demo_P01'))
    report = tmp_path / 'errors.csv'
    error_handling.write_report(str(report))
    rows = pd.read_csv(report)
    row = rows[rows['unique_id'] == 'Demo_P01']
    assert len(row) == 1
    assert "'ZZZZ'" in row.iloc[0]['Plants and Regeneration']
    assert '[WARNING]' in row.iloc[0]['Plants and Regeneration']


def test_other_species_without_an_alternate_code_reaches_the_error_report(tmp_path):
    error_handling.start_run()
    frame = _species_frame(['OTHER', 'ACCA'], unique_id='Demo_P02')
    _process_top_five_spp(frame)
    report = tmp_path / 'errors.csv'
    error_handling.write_report(str(report))
    rows = pd.read_csv(report)
    row = rows[rows['unique_id'] == 'Demo_P02']
    assert len(row) == 1
    assert 'pc_species_1_other' in row.iloc[0]['Plants and Regeneration']
    assert '[WARNING]' in row.iloc[0]['Plants and Regeneration']


# ── The species table itself ─────────────────────────────────────────────────────────────────────────────────────────

def _species_table():
    return pd.read_csv(os.path.join(os.path.dirname(helper.__file__), '..', 'supporting_data', 'plant_photoload.csv'))


def test_every_photoload_code_has_a_biomass_equation():
    for code in _PHOTOLOAD_CODES:
        assert np.isfinite(_get_photoload_biomass(code, 20.0, 20.0)), code


_SENTINELS = ['NO_SPP', 'OTHER']      # Survey123 form values that are not species


def _real_species():
    table = _species_table()
    return table[~table['name'].isin(_SENTINELS)]


def test_species_table_names_are_unique_and_complete():
    table = _species_table()
    assert table['name'].is_unique
    assert not table[['name', 'label']].isna().any().any()
    assert not _real_species()['pl_code'].isna().any()


def test_species_table_series_are_valid():
    table = _real_species()
    assert set(table['pl_code']) <= set(_PHOTOLOAD_CODES)
    assert set(table['pl_code_alt'].dropna()) <= set(_PHOTOLOAD_CODES)


def test_species_table_labels_carry_a_functional_group():
    # plants_regen assigns a species to a functional group by searching its label for Moss, Grass, Herb, or Shrub
    labels = _real_species()['label']
    assert labels.str.match(r'^\[(Herb/Forb|Herb|Grass|Shrub|Moss/Lichen|Tree)\] ').all()


# ── The two form values that are not species, and the Survey123 form that uses the table ────────────────────────────

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
PLANTS_FORM_DIR = os.path.join(REPO_ROOT, 'docs', 'survey123', 'survey123_forms', 'CWC Fuels 2 - Plants and Regen')


def test_sentinel_rows_are_in_the_species_table_without_a_series_or_group():
    # The Plants form builds its species list from this file, so without these rows a crew cannot choose them
    table = _species_table().set_index('name')
    for name in _SENTINELS:
        assert name in table.index, name
        assert pd.isna(table.loc[name, 'pl_code']) and pd.isna(table.loc[name, 'func_group']), name
        assert not table.loc[name, 'label'].startswith('['), name   # a label with a group would assign one


def test_the_form_media_copy_of_the_species_table_is_identical():
    packaged = os.path.join(os.path.dirname(helper.__file__), '..', 'supporting_data', 'plant_photoload.csv')
    media = os.path.join(PLANTS_FORM_DIR, 'media', 'plant_photoload.csv')
    if not os.path.exists(media):
        pytest.skip('the Survey123 form files are not in this checkout')
    with open(packaged, 'rb') as a, open(media, 'rb') as b:
        assert a.read() == b.read()


def _form_sheet(name):
    openpyxl = pytest.importorskip('openpyxl')
    path = os.path.join(PLANTS_FORM_DIR, 'CWC Fuels 2 - Plants and Regen.xlsx')
    if not os.path.exists(path):
        pytest.skip('the Survey123 form files are not in this checkout')
    rows = list(openpyxl.load_workbook(path, data_only=True)[name].iter_rows(values_only=True))
    header = [str(h) if h else '' for h in rows[0]]
    return [dict(zip(header, row)) for row in rows[1:] if any(row)]


def test_form_asks_for_a_functional_group_after_each_other_species():
    survey = _form_sheet('survey')
    names = [r['name'] for r in survey]
    for slot in range(1, 6):
        i = names.index(f'pc_species_{slot}_other')
        group = survey[i + 1]
        assert group['name'] == f'pc_species_{slot}_other_group'
        assert group['type'] == 'select_one list_plant_func_group'
        assert group['relevant'] == f"${{pc_species_{slot}}} = 'OTHER'"
        assert group['required'] == 'yes'


def test_form_functional_group_choices_are_the_species_table_groups_except_tree():
    # Survey123 cannot filter a file to unique values, so the choices are written into the form; this keeps them in step.
    # Tree is deliberately not offered: a tree that is not in the list belongs in the tree forms, not the plant cover.
    choices = [r for r in _form_sheet('choices') if r['list_name'] == 'list_plant_func_group']
    assert {r['name'] for r in choices} == set(_species_table()['func_group'].dropna()) - {'Tree'}
    assert all(r['name'] == r['label'] for r in choices)
