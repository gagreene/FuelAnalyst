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
    _calc_spp_comp_duff_litter_bulk_density,
    _calc_spp_comp_specific_gravity,
    _calc_tallied_woody_counts,
    _calc_woody_corrected_tsct_lengths,
    _calc_woody_diam_cm,
    _calc_woody_species,
    _calc_woody_volume,
    _calc_woody_weight,
    _concat_spp_comp_frames,
)


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


def test_calc_plot_duff_litter_biomass_scales_by_flammable_percent():
    plot_df = pd.DataFrame({'unique_id': ['A', 'B'], 'pc_flammable': [80.0, 50.0]})
    result, keep = _calc_plot_duff_litter_biomass(*_make_duff_litter_frames(plot_df))
    assert keep == ['ffl_duff_kgpm2', 'ffl_litter_kgpm2']
    assert result.loc[0, 'ffl_duff_kgpm2'] == pytest.approx(0.8)
    assert result.loc[0, 'ffl_litter_kgpm2'] == pytest.approx(0.24)
    assert result.loc[1, 'ffl_duff_kgpm2'] == pytest.approx(0.5)
    assert result.loc[1, 'ffl_litter_kgpm2'] == pytest.approx(0.15)


def test_calc_plot_duff_litter_biomass_defaults_to_fully_flammable_when_column_missing():
    plot_df = pd.DataFrame({'unique_id': ['A', 'B']})  # no pc_flammable column at all
    result, keep = _calc_plot_duff_litter_biomass(*_make_duff_litter_frames(plot_df))
    assert keep == ['ffl_duff_kgpm2', 'ffl_litter_kgpm2']
    assert result.loc[0, 'ffl_duff_kgpm2'] == pytest.approx(1.0)
    assert result.loc[0, 'ffl_litter_kgpm2'] == pytest.approx(0.3)
    assert result.loc[1, 'ffl_duff_kgpm2'] == pytest.approx(1.0)
    assert result.loc[1, 'ffl_litter_kgpm2'] == pytest.approx(0.3)


def test_calc_plot_duff_litter_biomass_defaults_missing_plot_when_column_present():
    # Plot A has a real pc_flammable value; plot B is missing from plot_df entirely.
    plot_df = pd.DataFrame({'unique_id': ['A'], 'pc_flammable': [80.0]})
    result, keep = _calc_plot_duff_litter_biomass(*_make_duff_litter_frames(plot_df))
    assert keep == ['ffl_duff_kgpm2', 'ffl_litter_kgpm2']
    assert result.loc[0, 'ffl_duff_kgpm2'] == pytest.approx(0.8)
    assert result.loc[1, 'ffl_duff_kgpm2'] == pytest.approx(1.0)


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


def test_species_composition_metadata_helpers():
    plots = pd.DataFrame({'GlobalID': ['parent'], 'unique_id': ['plot-1']})
    spp = pd.DataFrame({'ParentGlobalID': ['parent']})
    result = _add_spp_comp_type(_assign_spp_comp_id_col(plots, spp))
    assert result.loc[0, 'unique_id'] == 'plot-1'
    assert result.loc[0, 'spp_comp_type'] == 'manual_entry'


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


def test_calc_woody_corrected_lengths_maps_plot_values_and_diameter_bins():
    plots = pd.DataFrame({'GlobalID': ['p1'], 'num_transects': [2], 'tsct_slope_cor': [2.0]})
    pieces = pd.DataFrame({'ParentGlobalID': ['p1', 'p1'], 'woody_diam_cm': [0.5, 5.0]})
    params = {'protocol_transect_params': {'size_classes': [1, 10], 'transect_lengths': [4, 20]}}
    result = _calc_woody_corrected_tsct_lengths(plots, pieces, params)
    assert result['tsct_length'].tolist() == [8.0, 40.0]
    assert result['tsct_length_cor'].tolist() == [4.0, 20.0]


def test_tallied_woody_counts_sum_both_ends_of_both_transects():
    df = pd.DataFrame({
        't1_woody_tally_0to2': [1], 't1_woody_tally_28to30': [2],
        't2_woody_tally_0to2': [3], 't2_woody_tally_28to30': [4],
    })
    assert _calc_tallied_woody_counts(df).loc[0, 'woody_tally_count'] == 10


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
