import logging
import warnings

import numpy as np
import pandas as pd
import pytest

from fuel_analyst.components.woody_debris import (
    _add_spp_comp_type,
    _assign_spp_comp_id_col,
    _calc_plot_duff_litter_biomass,
    _calc_plot_duff_litter_depths,
    _calc_plot_t2_azimuth,
    _calc_plot_tsct_slope_correction,
    _calc_plot_tsct_total_slope_correction,
    _calc_plot_woody_debris,
    _calc_spp_comp_duff_litter_bulk_density,
    _calc_spp_comp_specific_gravity,
    _calc_tallied_woody_biomass,
    _calc_tallied_woody_counts,
    _calc_woody_corrected_tsct_lengths,
    _calc_woody_diam_cm,
    _calc_woody_species,
    _calc_woody_volume,
    _calc_woody_weight,
    _concat_spp_comp_frames,
    _prefix_compare_columns,
    _resolve_spp_comp_type,
)

from fuel_calculation_fixtures import _sloped_tally_frames


def _make_duff_litter_frames(plot_df):
    df = pd.DataFrame({
        'unique_id': ['A', 'B'],
        'spp_comp_type': ['transect_data', 'transect_data'],
        'stand_duff_depth_cm': [2.0, 2.0],
        'stand_litter_depth_cm': [1.0, 1.0],
    })
    spp_comp_df = pd.DataFrame({
        'unique_id': ['A', 'B'],
        'spp_comp_type': ['transect_data', 'transect_data'],
        'stand_duff_bd_kgpm3': [50.0, 50.0],
        'stand_litter_bd_kgpm3': [30.0, 30.0],
    })
    return plot_df, df, spp_comp_df




def test_calc_plot_duff_litter_biomass_defaults_missing_plot_when_column_present():
    # Plot A has a real pc_flammable value; plot B is missing from plot_df entirely.
    plot_df = pd.DataFrame({'unique_id': ['A'], 'pc_flammable': [80.0]})
    result, keep = _calc_plot_duff_litter_biomass(*_make_duff_litter_frames(plot_df))
    assert keep == ['ffl_duff_kgpm2', 'ffl_litter_kgpm2']
    assert result.loc[0, 'ffl_duff_kgpm2'] == pytest.approx(0.8)
    assert result.loc[1, 'ffl_duff_kgpm2'] == pytest.approx(1.0)


def test_calc_plot_duff_litter_biomass_defaults_to_fully_flammable_when_column_missing():
    plot_df = pd.DataFrame({'unique_id': ['A', 'B']})  # no pc_flammable column at all
    result, keep = _calc_plot_duff_litter_biomass(*_make_duff_litter_frames(plot_df))
    assert keep == ['ffl_duff_kgpm2', 'ffl_litter_kgpm2']
    assert result.loc[0, 'ffl_duff_kgpm2'] == pytest.approx(1.0)
    assert result.loc[0, 'ffl_litter_kgpm2'] == pytest.approx(0.3)
    assert result.loc[1, 'ffl_duff_kgpm2'] == pytest.approx(1.0)
    assert result.loc[1, 'ffl_litter_kgpm2'] == pytest.approx(0.3)


def test_calc_plot_duff_litter_biomass_scales_by_flammable_percent():
    plot_df = pd.DataFrame({'unique_id': ['A', 'B'], 'pc_flammable': [80.0, 50.0]})
    result, keep = _calc_plot_duff_litter_biomass(*_make_duff_litter_frames(plot_df))
    assert keep == ['ffl_duff_kgpm2', 'ffl_litter_kgpm2']
    assert result.loc[0, 'ffl_duff_kgpm2'] == pytest.approx(0.8)
    assert result.loc[0, 'ffl_litter_kgpm2'] == pytest.approx(0.24)
    assert result.loc[1, 'ffl_duff_kgpm2'] == pytest.approx(0.5)
    assert result.loc[1, 'ffl_litter_kgpm2'] == pytest.approx(0.15)


def test_calc_plot_duff_litter_depths_coerces_values_and_averages():
    df = pd.DataFrame({
        't1_duff_75': ['2'], 't1_duff_225': [4],
        't1_litter_75': ['bad'], 't1_litter_225': [6],
    })
    result, keep = _calc_plot_duff_litter_depths(df)
    assert result.loc[0, 'stand_duff_depth_cm'] == 3
    assert result.loc[0, 'stand_litter_depth_cm'] == 6
    assert keep == ['stand_duff_depth_cm', 'stand_litter_depth_cm']


def test_calc_plot_t2_azimuth_wraps_at_360():
    result = _calc_plot_t2_azimuth(pd.DataFrame({'t1_azimuth': [0, 300]}))
    assert result['t2_azimuth'].tolist() == [90, 30]


def test_calc_plot_woody_debris_replaces_pre_existing_output_column():
    df = pd.DataFrame({
        'GlobalID': ['p1'],
        'woody_kgpm2_test_default_5': ['stale'],
    })
    woody_merged_df = pd.DataFrame({
        'ParentGlobalID': ['p1'],
        'woody_diam_cm': [2.0],
        'woody_mass_kgpm2': [0.3],
    })
    params = {
        'woody_debris_classes': {
            'test': {
                'process_classes': True,
                'class_extension': 'test',
                'diameter_cutoffs': [100],
                'output_request': [
                    ['default', {}, [0, 5]],
                ],
            },
        },
    }

    result, keep_columns = _calc_plot_woody_debris(df, woody_merged_df, params)

    assert list(result.columns) == ['GlobalID', 'woody_kgpm2_test_default_5']
    assert result.columns.tolist().count('woody_kgpm2_test_default_5') == 1
    assert result.loc[0, 'woody_kgpm2_test_default_5'] == pytest.approx(0.3)
    assert keep_columns == ['woody_kgpm2_test_default_5']


@pytest.mark.parametrize(('first', 'second'), [(100.0, 100.0), (0.0, 100.0), (100.0, np.nan)])
def test_calc_tallied_woody_biomass_comparison_paths_convert_volume_once(first, second):
    result, keep = _calc_tallied_woody_biomass(*_sloped_tally_frames(first, second))
    for method in ['vanwagner', 'calculated']:
        mass = f'compare_woody_kgpm2_{method}_test_3'
        volume = f'compare_woody_volume_{method}_test_3'
        assert result.loc[0, mass] == pytest.approx(0.6 * result.loc[0, volume] / 10)
        assert mass in keep


@pytest.mark.parametrize('compare', [False, True])
@pytest.mark.parametrize(('first', 'second'), [(100.0, 100.0), (0.0, 100.0), (100.0, np.nan)])
def test_calc_tallied_woody_biomass_converts_corrected_volume_once(first, second, compare):
    result, keep = _calc_tallied_woody_biomass(*_sloped_tally_frames(first, second, compare))
    assert result.loc[0, 'woody_kgpm2_test_1'] == pytest.approx(0.5 * result.loc[0, 'woody_volume_test_1'] / 10)
    assert 'woody_kgpm2_test_1' in keep
    assert any(col.startswith('compare_woody_kgpm2') for col in result) == compare


def test_calc_tallied_woody_biomass_does_not_double_prefix_reprocessed_columns():
    df = pd.DataFrame({
        'GlobalID': ['p1'],
        'num_transects': [2],
        't1_slope_cor': [1.0],
        't2_slope_cor': [1.0],
        'tsct_slope_cor': [1.0],
        'woody_tally_count': [4.0],
        'woody_sg_1cm': [0.5],
        'woody_sg_3cm': [0.6],
        'compare_woody_count_test_1': ['stale'],
        'compare_woody_qmd_vanwagner_test_1': ['stale'],
    })
    pieces = pd.DataFrame({
        'ParentGlobalID': ['p1'],
        'woody_diam_cm': [2.0],
        'woody_diamSquared': [4.0],
    })
    params = {
        'measure_vs_tally_qmd_comparison': True,
        'woody_debris_classes': {
            'test': {
                'process_classes': True,
                'class_extension': 'test',
                'diameter_cutoffs': [1, 3],
                'transect_lengths': [4, 10, 30],
            },
        },
    }

    result, _ = _calc_tallied_woody_biomass(df, pieces, params)

    assert not any(column.startswith('compare_compare_') for column in result.columns)
    assert result.columns.tolist().count('compare_woody_count_test_1') == 1
    assert result.columns.tolist().count('compare_woody_qmd_vanwagner_test_1') == 1


def test_calc_tallied_woody_biomass_drops_stale_compare_columns_when_toggled_off():
    df = pd.DataFrame({
        'GlobalID': ['p1'],
        'num_transects': [2],
        't1_slope_cor': [1.0],
        't2_slope_cor': [1.0],
        'tsct_slope_cor': [1.0],
        'woody_tally_count': [4.0],
        'woody_sg_1cm': [0.5],
        'woody_sg_3cm': [0.6],
        'compare_woody_count_test_1': ['stale'],
        'compare_woody_qmd_vanwagner_test_1': ['stale'],
        'compare_woody_kgpm2_vanwagner_test_3': ['stale'],
    })
    pieces = pd.DataFrame({
        'ParentGlobalID': ['p1'],
        'woody_diam_cm': [2.0],
        'woody_diamSquared': [4.0],
    })
    params = {
        'measure_vs_tally_qmd_comparison': False,
        'woody_debris_classes': {
            'test': {
                'process_classes': True,
                'class_extension': 'test',
                'diameter_cutoffs': [1, 3],
                'transect_lengths': [4, 10, 30],
            },
        },
    }

    result, keep_columns = _calc_tallied_woody_biomass(df, pieces, params)

    assert not any(column.startswith('compare_') for column in result.columns)
    assert keep_columns == ['woody_kgpm2_test_1']


def test_calc_tallied_woody_biomass_replaces_pre_existing_output_columns():
    df = pd.DataFrame({
        'GlobalID': ['p1'],
        'num_transects': [2],
        't1_slope_cor': [1.0],
        't2_slope_cor': [1.0],
        'tsct_slope_cor': [1.0],
        'woody_tally_count': [4.0],
        'woody_sg_1cm': [0.5],
        'woody_sg_3cm': [0.6],
        'tsct_length_max_test': ['stale'],
        'woody_kgpm2_test_1': ['stale'],
    })
    pieces = pd.DataFrame({
        'ParentGlobalID': ['p1'],
        'woody_diam_cm': [2.0],
        'woody_diamSquared': [4.0],
    })
    params = {
        'measure_vs_tally_qmd_comparison': False,
        'woody_debris_classes': {
            'test': {
                'process_classes': True,
                'class_extension': 'test',
                'diameter_cutoffs': [1, 3],
                'transect_lengths': [4, 10, 30],
            },
        },
    }

    result, keep_columns = _calc_tallied_woody_biomass(df, pieces, params)

    assert result.columns.tolist().count('tsct_length_max_test') == 1
    assert result.columns.tolist().count('woody_kgpm2_test_1') == 1
    assert result.loc[0, 'woody_kgpm2_test_1'] == pytest.approx(0.0027059681182720645)
    assert list(result.columns[:len(df.columns)]) == list(df.columns)


def test_calc_tallied_woody_biomass_scales_linearly_with_slope_factor():
    flat, _ = _calc_tallied_woody_biomass(*_sloped_tally_frames(0.0, 0.0))
    sloped, _ = _calc_tallied_woody_biomass(*_sloped_tally_frames())
    factor = np.sqrt(1 + (np.pi / 4) ** 2)
    assert sloped.loc[0, 'compare_woody_qmd_vanwagner_test_1'] == flat.loc[0, 'compare_woody_qmd_vanwagner_test_1']
    for column in ['woody_volume_test_1', 'woody_kgpm2_test_1']:
        assert sloped.loc[0, column] / flat.loc[0, column] == pytest.approx(factor)


def test_calc_woody_corrected_lengths_maps_plot_values_and_diameter_bins():
    plots = pd.DataFrame({'GlobalID': ['p1'], 'num_transects': [2], 'tsct_slope_cor': [2.0]})
    pieces = pd.DataFrame({'ParentGlobalID': ['p1', 'p1'], 'woody_diam_cm': [0.5, 5.0]})
    params = {'protocol_transect_params': {'size_classes': [1, 10], 'transect_lengths': [4, 20]}}
    result = _calc_woody_corrected_tsct_lengths(plots, pieces, params)
    assert result['tsct_length'].tolist() == [8.0, 40.0]
    assert result['tsct_length_cor'].tolist() == [4.0, 20.0]


def test_calc_woody_weight_matches_tallied_conversion():
    result, _ = _calc_tallied_woody_biomass(*_sloped_tally_frames())
    measured = _calc_woody_weight(pd.DataFrame({
        'woody_sg': [0.5], 'woody_volume_m3pha': result['woody_volume_test_1'],
    }))
    assert measured.loc[0, 'woody_mass_kgpm2'] == pytest.approx(result.loc[0, 'woody_kgpm2_test_1'])


def test_concat_spp_comp_frames_preserves_schema_without_future_warning():
    existing = pd.DataFrame(columns=['spp_comp_code', 'spp_comp_percent', 'metadata'])
    incoming = pd.DataFrame({
        'spp_comp_code': ['FDI'],
        'spp_comp_percent': [100.0],
    })

    with warnings.catch_warnings():
        warnings.filterwarnings(
            'error',
            category=FutureWarning,
            message='.*DataFrame concatenation with empty or all-NA entries.*',
        )
        result = _concat_spp_comp_frames(existing, incoming)

    assert list(result.columns) == ['spp_comp_code', 'spp_comp_percent', 'metadata']
    assert result.loc[0, 'spp_comp_percent'] == 100.0
    assert result['spp_comp_percent'].dtype == incoming['spp_comp_percent'].dtype
    assert result['metadata'].isna().all()


def test_prefix_compare_columns_does_not_double_prefix_already_prefixed_columns():
    df = pd.DataFrame({
        'compare_woody_count_test_1': [3],
        'compare_woody_qmd_vanwagner_test_1': [2.0],
        'other': [1],
    })
    result = _prefix_compare_columns(df, enabled=True)
    assert list(result.columns) == list(df.columns)


def test_prefix_compare_columns_drops_stale_columns_when_disabled():
    df = pd.DataFrame({
        'compare_woody_count_test_1': ['stale'],
        'compare_woody_qmd_vanwagner_test_1': ['stale'],
        'compare_woody_kgpm2_vanwagner_test_3': ['stale'],
        'woody_count_test_1': [5],
        'other': [1],
    })
    result = _prefix_compare_columns(df, enabled=False)
    assert list(result.columns) == ['woody_count_test_1', 'other']


def test_prefix_compare_columns_overwrites_stale_destination_without_duplicating():
    df = pd.DataFrame({
        'compare_woody_count_test_1': ['stale'],
        'woody_count_test_1': [7],
    })
    result = _prefix_compare_columns(df, enabled=True)
    assert result.columns.tolist().count('compare_woody_count_test_1') == 1
    assert result.loc[0, 'compare_woody_count_test_1'] == 7


def test_prefix_compare_columns_renames_fresh_columns():
    df = pd.DataFrame({'woody_count_test_1': [5], 'qmd_vanwagner_test_1': [2.0], 'other': [1]})
    result = _prefix_compare_columns(df, enabled=True)
    assert list(result.columns) == ['compare_woody_count_test_1', 'compare_qmd_vanwagner_test_1', 'other']


def test_resolve_spp_comp_type_falls_back_when_declared_source_has_no_data(caplog):
    df = pd.DataFrame({'unique_id': ['A'], 'spp_comp_type': ['tree_data']})
    spp_comp_df = pd.DataFrame({
        'unique_id': ['A'],
        'spp_comp_type': ['transect_data'],
        'spp_comp_code': ['FDI'],
    })
    with caplog.at_level(logging.INFO, logger='fuel_analyst.components.woody_debris'):
        result, keep = _resolve_spp_comp_type(df, spp_comp_df)
    assert keep == ['spp_comp_type_declared']
    assert result.loc[0, 'spp_comp_type'] == 'transect_data'
    assert result.loc[0, 'spp_comp_type_declared'] == 'tree_data'
    assert len(caplog.records) == 1
    assert 'tree_data' in caplog.records[0].message
    assert 'transect_data' in caplog.records[0].message
    assert caplog.records[0].unique_id == 'A'


def test_resolve_spp_comp_type_keeps_declared_source_when_available(caplog):
    df = pd.DataFrame({'unique_id': ['A'], 'spp_comp_type': ['transect_data']})
    spp_comp_df = pd.DataFrame({
        'unique_id': ['A'],
        'spp_comp_type': ['transect_data'],
        'spp_comp_code': ['FDI'],
    })
    with caplog.at_level(logging.INFO, logger='fuel_analyst.components.woody_debris'):
        result, _ = _resolve_spp_comp_type(df, spp_comp_df)
    assert result.loc[0, 'spp_comp_type'] == 'transect_data'
    assert caplog.records == []


def test_resolve_spp_comp_type_leaves_declared_when_no_source_available(caplog):
    df = pd.DataFrame({'unique_id': ['A'], 'spp_comp_type': ['tree_data']})
    spp_comp_df = pd.DataFrame({'unique_id': [], 'spp_comp_type': [], 'spp_comp_code': []})
    with caplog.at_level(logging.INFO, logger='fuel_analyst.components.woody_debris'):
        result, _ = _resolve_spp_comp_type(df, spp_comp_df)
    assert result.loc[0, 'spp_comp_type'] == 'tree_data'
    assert caplog.records == []


def test_species_composition_metadata_helpers():
    plots = pd.DataFrame({'GlobalID': ['parent'], 'unique_id': ['plot-1']})
    spp = pd.DataFrame({'ParentGlobalID': ['parent']})
    result = _add_spp_comp_type(_assign_spp_comp_id_col(plots, spp))
    assert result.loc[0, 'unique_id'] == 'plot-1'
    assert result.loc[0, 'spp_comp_type'] == 'manual_entry'

def test_species_composition_parameters_are_weighted_and_unknown_species_fall_back():
    from fuel_analyst.components.woody_debris import bulk_density_map, specific_gravity_map

    parameter_names = {item[1] for item in bulk_density_map + specific_gravity_map}
    params = pd.DataFrame(
        [{name: 10.0 for name in parameter_names}, {name: 20.0 for name in parameter_names}],
        index=['FDI', 'UNK'],
    )
    spp = pd.DataFrame({'spp_comp_code': ['FDI', 'MISSING'], 'spp_comp_percent': [25.0, 50.0]})
    result = _calc_spp_comp_specific_gravity(_calc_spp_comp_duff_litter_bulk_density(spp, params), params)
    assert result.loc[0, 'stand_duff_bd_kgpm3'] == pytest.approx(2.5)
    assert result.loc[1, 'stand_duff_bd_kgpm3'] == pytest.approx(10.0)
    assert result.loc[0, 'woody_sg_1cm'] == pytest.approx(2.5)
    assert result.loc[1, 'woody_sg_1cm'] == pytest.approx(10.0)


def test_tallied_woody_counts_sum_both_ends_of_both_transects():
    df = pd.DataFrame({
        't1_woody_tally_0to2': [1], 't1_woody_tally_28to30': [2],
        't2_woody_tally_0to2': [3], 't2_woody_tally_28to30': [4],
    })
    assert _calc_tallied_woody_counts(df).loc[0, 'woody_tally_count'] == 10


def test_tallied_woody_fragmentation_contract_preserves_outputs_without_warning():
    df = pd.DataFrame({
        'GlobalID': ['p1'],
        'num_transects': [2],
        't1_slope_cor': [1.0],
        't2_slope_cor': [1.0],
        'tsct_slope_cor': [1.0],
        'woody_tally_count': [4.0],
        'woody_sg_1cm': [0.5],
        'woody_sg_3cm': [0.6],
    })
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', pd.errors.PerformanceWarning)
        for index in range(110):
            df[f'padding_{index}'] = index
    input_column_count = len(df.columns)

    pieces = pd.DataFrame({
        'ParentGlobalID': ['p1'],
        'woody_diam_cm': [2.0],
        'woody_diamSquared': [4.0],
    })
    params = {
        'measure_vs_tally_qmd_comparison': True,
        'woody_debris_classes': {
            'test': {
                'process_classes': True,
                'class_extension': 'test',
                'diameter_cutoffs': [1, 3],
                'transect_lengths': [4, 10, 30],
            },
        },
    }

    with warnings.catch_warnings():
        warnings.simplefilter('error', pd.errors.PerformanceWarning)
        result, keep_columns = _calc_tallied_woody_biomass(df, pieces, params)

    generated_columns = list(result.columns[input_column_count:])
    assert generated_columns == [
        'tsct_length_total_test_4',
        'tsct_length_total_test_10',
        'tsct_length_total_test_30',
        'tsct_length_max_test',
        't1_length_cor_test_4',
        't2_length_cor_test_4',
        'tsct_length_cor_test_4',
        't1_length_cor_test_10',
        't2_length_cor_test_10',
        'tsct_length_cor_test_10',
        't1_length_cor_test_30',
        't2_length_cor_test_30',
        'tsct_length_cor_test_30',
        'compare_woody_count_test_1',
        'compare_woody_count_test_3',
        'compare_woody_qmd_vanwagner_test_1',
        'compare_woody_qmd_vanwagner_test_3',
        'compare_woody_diamSquared_sum_test_3',
        'compare_woody_qmd_calculated_test_3',
        'woody_volume_test_1',
        'woody_kgpm2_test_1',
        'compare_woody_volume_vanwagner_test_3',
        'compare_woody_kgpm2_vanwagner_test_3',
        'compare_woody_volume_calculated_test_3',
        'compare_woody_kgpm2_calculated_test_3',
    ]
    assert keep_columns == [
        'woody_kgpm2_test_1',
        'compare_woody_count_test_1',
        'compare_woody_count_test_3',
        'compare_woody_qmd_vanwagner_test_1',
        'compare_woody_qmd_vanwagner_test_3',
        'compare_woody_qmd_calculated_test_3',
        'compare_woody_kgpm2_vanwagner_test_3',
        'compare_woody_kgpm2_calculated_test_3',
    ]
    assert result.loc[0, 'woody_kgpm2_test_1'] == pytest.approx(0.0027059681182720645)
    assert result.loc[0, 'compare_woody_qmd_calculated_test_3'] == pytest.approx(2.0)
    assert result.loc[0, 'compare_woody_kgpm2_calculated_test_3'] == pytest.approx(
        0.014804406601634037
    )

    params['measure_vs_tally_qmd_comparison'] = False
    with warnings.catch_warnings():
        warnings.simplefilter('error', pd.errors.PerformanceWarning)
        result_without_comparison, keep_without_comparison = _calc_tallied_woody_biomass(
            df,
            pieces,
            params
        )

    assert keep_without_comparison == ['woody_kgpm2_test_1']
    assert not any(column.startswith('compare_') for column in result_without_comparison)


def test_transect_slope_and_total_corrections():
    df = pd.DataFrame({
        't1_slope_units': ['degrees'], 't1_slope': [45.0],
        't2_slope_units': ['percent'], 't2_slope': [0.0], 'num_transects': [2],
    })
    df = _calc_plot_tsct_slope_correction(df)
    result = _calc_plot_tsct_total_slope_correction(
        df, {'protocol_transect_params': {'transect_lengths': [10]}}
    )
    assert result.loc[0, 't1_slope_pct'] == pytest.approx(100)
    assert result.loc[0, 't2_slope_cor'] == pytest.approx(1)
    assert result.loc[0, 'tsct_length_10m_cor'] > 10


def test_woody_piece_geometry_species_volume_and_weight():
    df = pd.DataFrame({
        'woody_diam': [25.0, 100.0], 'woody_decay': [2, 4],
        'woody_species': ['FDI', 'PLI'], 'tsct_length_cor': [10.0, 20.0],
        'woody_sg': [0.5, 0.4],
    })
    result = _calc_woody_weight(_calc_woody_volume(_calc_woody_species(_calc_woody_diam_cm(df))))
    assert result['woody_diam_cm'].tolist() == [2.5, 10.0]
    assert result['woody_species_adj'].tolist() == ['FDI', 'DECAYED']
    assert result.loc[0, 'woody_volume_m3pha'] == pytest.approx((np.pi ** 2 / 8) / 10 * 2.5 ** 2)
    assert result.loc[0, 'woody_mass_kgpm2'] == pytest.approx(
        0.5 * result.loc[0, 'woody_volume_m3pha'] / 10
    )
