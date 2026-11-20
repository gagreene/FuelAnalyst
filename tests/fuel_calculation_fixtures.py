"""Shared controlled inputs for fuel-calculation unit and integration tests."""
import numpy as np
import pandas as pd

from fuel_analyst.components.canopy_cover import _process_cc_data, _process_transect_data
from fuel_analyst.components.woody_debris import (
    _calc_plot_tsct_slope_correction,
    _calc_plot_tsct_total_slope_correction,
)


def _depth_frame(covers, heights, species=None):
    row = {}
    for index in range(1, 6):
        offset = index - 1
        row.update({
            f'pc_species_{index}': (species[offset] if species is not None else 'ACCA') if offset < len(covers) else None,
            f'pc_species_{index}_other': None,
            f'pc_species_{index}_pct': float(covers[offset]) if offset < len(covers) else np.nan,
            f'pc_species_{index}_ht': float(heights[offset]) if offset < len(heights) else np.nan,
        })
    return pd.DataFrame([row])


def _make_consumption_input_df():
    """
    Build a minimal plot-level DataFrame with all columns gen_fofem_consumption_df() requires.

    :return: DataFrame with one row of SI-unit source values.
    """
    return pd.DataFrame({
        'unique_id': ['p1'], 'SPECIES_CD_1': ['PY'], 'dom_substrate': ['HG'],
        'form_select': ['trees'], '_tree_parent_present': [True],
        'conpyro_live_trees_present': [True],
        'fofem_shrub_group': [''], 'treatment_type': ['untreated'],
        'ffl_litter_kgpm2': [1.0], 'ffl_duff_kgpm2': [2.0], 'stand_duff_depth_cm': [3.0],
        'woody_kgpm2_fofem_sound_0_635': [0.1], 'woody_kgpm2_fofem_sound_2_54': [0.2],
        'woody_kgpm2_fofem_sound_7_62': [0.3], 'woody_kgpm2_fofem_sound_15_24': [0.4],
        'woody_kgpm2_fofem_sound_22_86': [0.5], 'woody_kgpm2_fofem_sound_50_8': [0.6],
        'woody_kgpm2_fofem_sound_gt50_8': [0.7],
        'woody_kgpm2_fofem_rotten_0_635': [0.1], 'woody_kgpm2_fofem_rotten_2_54': [0.2],
        'woody_kgpm2_fofem_rotten_7_62': [0.8],
        'woody_kgpm2_fofem_rotten_15_24': [0.9], 'woody_kgpm2_fofem_rotten_22_86': [1.0],
        'woody_kgpm2_fofem_rotten_50_8': [1.1], 'woody_kgpm2_fofem_rotten_gt50_8': [1.2],
        'grass_kgpm2': [0.3], 'herbs_kgpm2': [0.5], 'shrubs_kgpm2': [0.1],
        'fuel_bed_depth_m': [0.25],
        'stand_foliage_fofem_kgpm2_sum': [0.4], 'stand_branches_fofem_kgpm2_sum': [0.5],
    })


def _plot_cover(rows):
    columns = ['ParentGlobalID', 'cc_transect'] + [f'cc_{distance}' for distance in range(2, 32, 2)]
    transects = _process_transect_data(pd.DataFrame(rows, columns=columns))
    return _process_cc_data(pd.DataFrame({'GlobalID': ['plot-1']}), transects)


def _sloped_tally_frames(first=100.0, second=100.0, compare=True):
    df = pd.DataFrame({
        'GlobalID': ['p1'], 'num_transects': [1 if np.isnan(second) else 2],
        't1_slope': [first], 't2_slope': [second],
        't1_slope_units': ['percent'], 't2_slope_units': ['percent'],
        'woody_tally_count': [4.0], 'woody_sg_1cm': [0.5], 'woody_sg_3cm': [0.6],
    })
    pieces = pd.DataFrame({'ParentGlobalID': ['p1'], 'woody_diam_cm': [2.0], 'woody_diamSquared': [4.0]})
    params = {
        'protocol_transect_params': {'transect_lengths': [4, 10, 30]},
        'measure_vs_tally_qmd_comparison': compare,
        'woody_debris_classes': {
            'test': {
                'process_classes': True, 'class_extension': 'test',
                'diameter_cutoffs': [1, 3], 'transect_lengths': [4, 10, 30],
                'output_request': [('all', {}, [0, 1, 3])],
            },
        },
    }
    df = _calc_plot_tsct_total_slope_correction(_calc_plot_tsct_slope_correction(df), params)
    return df, pieces, params


def _transect_row(transect, values, parent='plot-1'):
    row = {'ParentGlobalID': parent, 'cc_transect': transect}
    row.update({f'cc_{distance}': value for distance, value in zip(range(2, 32, 2), values)})
    return row
