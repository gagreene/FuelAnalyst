# -*- coding: utf-8 -*-
"""
Created on Tue May 28, 15:00:00 2025

@author: Gregory A. Greene
"""
__author__ = ['Gregory A. Greene']

import os
import pandas as pd
from typing import Optional

from .components import error_handling
from .components import helper
from .components import plot_attributes as pa
from .components import plants_regen as pr
from .components import trees
from .components import canopy_cover as cc
from .components import woody_debris as wd
from .components import conpyro_attributes
from .components import fofem_attributes
from .components import fofem_units

default_stand_summary_dict = {
    'dens': {
        'att_source': 'dens',  # This could be user specified/adjusted
        'override_field_name': False, # This is fixed as False for stand summaries
        'summary': ['total', 'live', 'dead', 'conifer', 'broadleaf'],  # These are the only options
        'summary_permutation': 'all',  # This is the default (options: 'all', 'exact', 'combined')
        'metrics': ['sum'],  # These options are fixed
        'units': 'tpha',  # This option is fixed
        'classes': {
            'dbh': [0, 5, 7.5, 12.5, float('inf')]
        },
    },
    'ba': {
        'att_source': 'ba',  # This could be user specified/adjusted
        'override_field_name': False, # This is fixed as False for stand summaries
        'summary': ['total', 'live', 'dead', 'conifer', 'broadleaf'],  # These are the only options
        'summary_permutation': 'all',  # This is the default (options: 'all', 'exact', 'combined')
        'metrics': ['sum'],  # These options are fixed
        'units': 'm2pha',  # This option is fixed
        'classes': {
            'dbh': [0, 5, 7.5, 12.5, float('inf')]
        },
    },
    'ht': {
        'att_source': 'ht',  # This could be user specified/adjusted
        'override_field_name': False, # This is fixed as False for stand summaries
        'summary': ['total', 'live', 'dead', 'conifer', 'broadleaf'],  # These are the only options
        'summary_permutation': 'all',  # This is the default (options: 'all', 'exact', 'combined')
        'metrics': ['max', 'mean'],  # These are the only options
        'units': 'm',  # This option is fixed
        'classes': {
            'dbh': [0, 5, float('inf')]
        },
    },
    'cbh': {
        'att_source': 'cbh',  # This could be user specified/adjusted
        'override_field_name': False, # This is fixed as False for stand summaries
        'summary': ['total', 'live', 'conifer', 'broadleaf'],  # These are the only options
        'summary_permutation': 'all',  # This is the default (options: 'all', 'exact', 'combined')
        'metrics': ['min', 'max', 'mean'],  # These are the only options
        'units': 'm',  # This option is fixed
        'classes': {
            'dbh': [0, 5, float('inf')]
        },
    },
    'dcbh': {
        'att_source': 'dcbh',  # This could be user specified/adjusted
        'override_field_name': False, # This is fixed as False for stand summaries
        'summary': ['total', 'live', 'dead', 'conifer', 'broadleaf'],  # These are the only options
        'summary_permutation': 'all',  # This is the default (options: 'all', 'exact', 'combined')
        'metrics': ['min', 'max', 'mean'],  # These are the only options
        'units': 'm',  # This option is fixed
        'classes': {
            'dbh': [0, 5, float('inf')]
        },
    },
    'fsg': {
        'att_source': 'fsg',  # This could be user specified/adjusted
        'override_field_name': False, # This is fixed as False for stand summaries
        'summary': ['total', 'live', 'dead', 'conifer', 'broadleaf'],  # This is the default
        'summary_permutation': 'all',  # This is the default (options: 'all', 'exact', 'combined')
        'metrics': ['min', 'max', 'mean'],  # These are the only options
        'units': 'm',  # This option is fixed
        'classes': {
            'dbh': [0, 5, float('inf')]
        },
    },
    'cfl': {
        'att_source': 'cfl',  # This could be user specified/adjusted
        'override_field_name': False, # This is fixed as False for stand summaries
        'summary': ['live', 'conifer'],  # This is the default
        'summary_permutation': 'all',  # This is the default (options: 'all', 'exact', 'combined')
        'metrics': ['sum'],  # This is the only option
        'units': 'kgpm2',  # This option is fixed
        'classes': {
            'dbh': [0, 5, float('inf')]
        },
    },
    'cbd': {
        'att_source': 'cbd',  # This could be user specified/adjusted
        'override_field_name': False, # This is fixed as False for stand summaries
        'summary': ['live', 'conifer'],  # This is the default
        'summary_permutation': 'all',  # This is the default (options: 'all', 'exact', 'combined')
        'metrics': [],  # This is fixed as empty (no user options)
        'units': 'kgpm3',  # This option is fixed
        'classes': {
            'dbh': [0, 5, float('inf')]
        },
    },
    'foliage': {
        'att_source': 'foliage',  # This could be user specified/adjusted
        'override_field_name': False, # This is fixed as False for stand summaries
        'summary': ['live', 'conifer', 'broadleaf'],  # These are all live trees
        'summary_permutation': 'all',  # This is the default (options: 'all', 'exact', 'combined')
        'metrics': ['sum'],  # This is the only option
        'units': 'kgpm2',  # This option is fixed
        'classes': {
            'dbh': [0, float('inf')]
        },
    },
    'branches': {
        'att_source': 'branches',  # This could be user specified/adjusted
        'override_field_name': False, # This is fixed as False for stand summaries
        'summary': ['live', 'dead', 'conifer', 'broadleaf'],  # These are the only options
        'summary_permutation': 'all',  # This is the default (options: 'all', 'exact', 'combined')
        'metrics': ['sum'],  # This is the only option
        'units': 'kgpm2',  # This option is fixed
        'classes': {
            'dbh': [0, float('inf')]
        },
    },
    'wood': {
        'att_source': 'wood',  # This could be user specified/adjusted
        'override_field_name': False, # This is fixed as False for stand summaries
        'summary': ['live', 'dead', 'conifer', 'broadleaf'],  # These are the only options
        'summary_permutation': 'all',  # This is the default (options: 'all', 'exact', 'combined')
        'metrics': ['sum'],  # This is the only option
        'units': 'kgpm2',  # This option is fixed
        'classes': {
            'dbh': [0, float('inf')]
        },
    },
    'bark': {
        'att_source': 'bark',  # This could be user specified/adjusted
        'override_field_name': False, # This is fixed as False for stand summaries
        'summary': ['live', 'dead', 'conifer', 'broadleaf'],  # These are the only options
        'summary_permutation': 'all',  # This is the default (options: 'all', 'exact', 'combined')
        'metrics': ['sum'],  # This is the only option
        'units': 'kgpm2',  # This option is fixed
        'classes': {
            'dbh': [0, float('inf')]
        },
    },
    'flame_length': {
        'att_source': 'flame_length',  # This could be user specified/adjusted
        'override_field_name': False, # This is fixed as False for stand summaries
        'summary': ['total'],  # This is fixed (no user options)
        'summary_permutation': 'exact',  # This is fixed (no user options)
        'metrics': ['min', 'max', 'mean'],  # These are the only options
        'units': 'm',  # This option is fixed
    },
    'fire_intensity': {
        'att_source': 'fire_intensity',  # This could be user specified/adjusted
        'override_field_name': False, # This is fixed as False for stand summaries
        'summary': ['total'],  # This is fixed (no user options)
        'summary_permutation': 'exact',  # This is fixed (no user options)
        'metrics': ['min', 'max', 'mean'],  # These are the only options
        'units': 'kWpm',  # This option is fixed (no user options)
    },
}

default_woody_debris_dict = {
    'protocol_transect_params': {
        'size_classes': [0.5, 7, 30, float('inf')],  # Default size classes for transects (cm)
        'transect_lengths': [4, 10, 20, 30],  # Default transect lengths (m)
    },
    'woody_debris_classes': {
        'canadian': {
            'process_classes': True,  # Process Canadian woody debris classes (options: True, False)
            'class_extension': 'can',  # Extension for Canadian classes
            'diameter_cutoffs': [0.5, 1, 3, 5, 7],  # Diameter cutoffs for Canadian classes (cm)
            'transect_lengths': [4, 10, 10, 10, 10, 30],  # Transect lengths for Canadian classes (m)
            # Output request for woody fuels
            # Start at upper diameter limit of tallied data for diameter cutoffs
            'output_request': [
                # [output name extension, filter dictionary, diameter cutoffs]
                ['default', {}, [0, 0.5, 1, 3, 5, 7, float('inf')]],
                ['lt7cm', {}, [0, 7]],
            ],  # Output diameter cutoffs for Canadian classes (cm)
        },
        'us': {
            'process_classes': True,  # Process U.S. woody debris classes (options: True, False)
            'class_extension': 'us',  # Extension for U.S. classes
            'diameter_cutoffs': [0.635, 2.54, 7.62],  # Diameter cutoffs for U.S. classes (cm)
            'transect_lengths': [4, 10, 10, 30],  # Transect lengths for U.S. classes (m)
            # Output request for woody fuels
            # At a minimum, diameter cutoffs must start at the upper diameter limit of tallied data
            'output_request': [
                # [output name extension, filter dictionary, diameter cutoffs]
                ['default', {}, [0, 0.635, 2.54, 7.62, float('inf')]],
                ['coarse', {}, [7.62, float('inf')]],
            ],  # Output diameter cutoffs for U.S. classes (cm)
        },
        'modified': {
            'process_classes': True,  # Process modified woody debris classes (options: True, False)
            'class_extension': 'mod',  # Extension for modified classes
            'diameter_cutoffs': [0.5, 1, 2, 3, 4, 5, 6, 7],  # Diameter cutoffs for modified classes (cm)
            'transect_lengths': [4, 10, 10, 10, 10, 10, 10, 10, 30],  # Transect lengths for modified classes (m)
            # Output request for woody fuels
            # Start at upper diameter limit of tallied data for diameter cutoffs
            'output_request': [
                # [output name extension, filter dictionary, diameter cutoffs]
                ['default', {}, [0, 0.5, 1, 2, 3, 4, 5, 6, 7, float('inf')]],
            ],
        },
    },
    'measure_vs_tally_qmd_comparison': True,  # Compare differences (QMD, biomass) between measured and tallied data
}

default_conpyro_dict = {
    'stand_attributes': {  # All attributes must output a single column
        'conpyro_cfl_ovrstry': {  # This name is fixed for ConPyro
            'att_source': 'cfl',  # This is fixed (no user options)
            'override_field_name': True,  # This is fixed (no user options)
            'summary': ['live', 'conifer'],  # This is fixed (no user options)
            'summary_permutation': 'combined',  # This is fixed (no user options)
            'metrics': ['sum'],  # This is fixed (no user options)
            'units': 'kgpm2',  # This option is fixed
            'classes': {
                'dbh': [0, float('inf')]  # All trees
            },
        },
        'conpyro_cbd_ovrstry': {  # This name is fixed for ConPyro
            'att_source': 'cbd',  # This is fixed (no user options)
            'override_field_name': True,  # This is fixed (no user options)
            'summary': ['live', 'conifer'],  # This is fixed (no user options)
            'summary_permutation': 'combined',  # This is fixed (no user options)
            'metrics': [],  # This is fixed as empty (no user options for cbd)
            'units': 'kgpm3',  # This option is fixed for cbd
            'classes': {
                'dbh': [0, float('inf')]  # All trees
            },
        },
        'conpyro_cfl_midstry': {  # This name is fixed for ConPyro
            'att_source': 'cfl',  # This is fixed (no user options)
            'override_field_name': True,  # This is fixed (no user options)
            'summary': ['live', 'conifer'],  # This is fixed (no user options)
            'summary_permutation': 'combined',  # This is fixed (no user options)
            'metrics': ['sum'],  # This is fixed (no user options)
            'units': 'kgpm2',  # This option is fixed
            'classes': {
                'dbh': [0, 0]  # Midstory trees excluded
            },
        },
        'conpyro_cbd_midstry': {  # This name is fixed for ConPyro
            'att_source': 'cbd',  # This is fixed (no user options)
            'override_field_name': True,  # This is fixed (no user options)
            'summary': ['live', 'conifer'],  # This is fixed (no user options)
            'summary_permutation': 'combined',  # This is fixed (no user options)
            'metrics': [],  # This is fixed as empty (no user options for cbd)
            'units': 'kgpm3',  # This option is fixed for cbd
            'classes': {
                'dbh': [0, 0]  # Midstory trees excluded
            },
        },
        'conpyro_dead_branch_fl_midstry': {  # This name is fixed for ConPyro
            'att_source': 'branches',  # This is fixed (no user options)
            'override_field_name': True,  # This is fixed (no user options)
            'summary': ['dead'],  # This is fixed (no user options)
            'summary_permutation': 'combined',  # This is fixed (no user options)
            'metrics': ['sum'],  # This is fixed (no user options)
            'units': 'kgpm2',  # This option is fixed
            'classes': {
                'dbh': [0, 0]  # Midstory trees excluded
            },
        },
        'conpyro_ht_ovrstry_live': {  # This name is fixed for ConPyro
            'att_source': 'ht',  # This is fixed (no user options)
            'override_field_name': True,  # This is fixed (no user options)
            'summary': ['live', 'conifer'],  # These are fixed (no user options)
            'summary_permutation': 'combined',  # This is fixed (no user options)
            'metrics': ['mean'],  # This is the default (options: min, max, mean) - only one option can be used
            'units': 'm',  # This option is fixed
            'classes': {
                'dbh': [0, float('inf')]  # All trees
            },
        },
        'conpyro_ht_midstry_live': {  # This name is fixed for ConPyro
            'att_source': 'ht',  # This is fixed (no user options)
            'override_field_name': True,  # This is fixed (no user options)
            'summary': ['live', 'conifer'],  # These are fixed (no user options)
            'summary_permutation': 'combined',  # This is fixed (no user options)
            'metrics': ['mean'],  # This is the default (options: min, max, mean) - only one option can be used
            'units': 'm',  # This option is fixed
            'classes': {
                'dbh': [0, 0]  # Midstory trees excluded
            },
        },
        'conpyro_ht_midstry_dead': {  # This name is fixed for ConPyro
            'att_source': 'ht',  # This is fixed (no user options)
            'override_field_name': True,  # This is fixed (no user options)
            'summary': ['dead'],  # This is fixed for ht (no user options)
            'summary_permutation': 'combined',  # This is fixed (no user options)
            'metrics': ['mean'],  # This is the default (options: min, max, mean) - only one option can be used
            'units': 'm',  # This option is fixed
            'classes': {
                'dbh': [0, 0]  # Midstory trees excluded
            },
        },
        # """
        # FSG-Based Attributes
        #
        # The available summary options are as follows:
        #
        # att_source: 'cbh'
        # - ['total', 'live'] includes all live trees (conifer + broadleaf)
        # - ['live', 'conifer'] includes all live conifer trees
        # - ['live', 'broadleaf'] includes all live broadleaf trees
        #
        # att_source: 'fsg'
        # - ['live', 'dead'] includes all trees (['total'] alone is not valid with 'combined')
        # - ['live'] includes all live trees
        # - ['dead'] includes all dead trees
        # - ['conifer'] includes all conifer trees
        # - ['broadleaf'] includes all broadleaf trees
        # - ['live', 'conifer'] includes all live conifer trees
        # - ['live', 'broadleaf'] includes all live broadleaf trees
        # - ['dead', 'conifer'] includes all dead conifer trees
        # - ['dead', 'broadleaf'] includes all dead broadleaf trees
        # ""
        'conpyro_cbh_ovrstry': {  # This name is fixed for ConPyro
            'att_source': 'cbh',  # This is fixed (no user options)
            'override_field_name': True,  # This is fixed (no user options)
            'summary': ['live', 'conifer'],  # This is the default (options: see above)
            'summary_permutation': 'combined',  # This is fixed (no user options)
            'metrics': ['mean'],  # This is the default (options: min, max, mean)
            'units': 'm',  # This option is fixed
            'classes': {
                'dbh': [0, float('inf')]  # All trees
            },
        },
        'conpyro_cbh_midstry': {  # This name is fixed for ConPyro
            'att_source': 'cbh',  # This is fixed (no user options)
            'override_field_name': True,  # This is fixed (no user options)
            'summary': ['live', 'conifer'],  # This is the default (options: see above)
            'summary_permutation': 'combined',  # This is fixed (no user options)
            'metrics': ['mean'],  # This is the default (options: min, max, mean)
            'units': 'm',  # This option is fixed
            'classes': {
                'dbh': [0, 0]  # Midstory trees excluded
            },
        },
        'conpyro_fsg': {  # This name is fixed for ConPyro
            'att_source': 'cbh',  # This is default (options: cbh, fsg)
            'override_field_name': True,  # This is fixed (no user options)
            'summary': ['conifer'],  # This is the default (options: see above)
            'summary_permutation': 'combined',  # This is fixed (no user options)
            'metrics': ['mean'],  # This is the default (options: min, max, mean)
            'units': 'm',  # This option is fixed
            'classes': {
                'dbh': [0, float('inf')]  # All trees
            },
        },
    },
    # Vegetative Fuel Load Attributes
    #
    # The available herbaceous fuel load options are as follows:
    # - [] no herbaceous fuels
    # - ['grass'] grasses only
    # - ['herb_forb'] herbs and forbs only
    # - ['grass', 'herb_forb'] grasses, herbs and forbs
    # The available grass fuel load options are as follows:
    # - [] no grass fuels
    # - ['grass'] grass fuels
    # The available shrub fuel load options are as follows:
    # - [] no shrub fuels
    # - ['shrubs'] shrub fuels
    'vegetative_fuel_loads': {
        'herbaceous': ['grass', 'herb_forb'],  # This is default (see options above)
        'grass': ['grass'],  # This is default (see options above)
        'shrub': ['shrubs'],  # This is default (see options above)
    },
    'canopy_cover_attribute': 'cc', # This is default (options: cc, cc_cnfr, cc_brdlf)
    'woody_debris_classes': {
        'conpyro': {
            'process_classes': True,  # Process Canadian woody debris classes
            'class_extension': 'conpyro',  # Extension for Canadian classes
            'diameter_cutoffs': [0.5, 1, 3, 5, 7],  # Diameter cutoffs for Canadian classes (cm)
            'transect_lengths': [4, 10, 10, 10, 10, 30],  # Transect lengths for Canadian classes (m)
            # Output request for woody fuels
            # Start at upper diameter limit of tallied data for diameter cutoffs
            'output_request': [
                # [output name extension, filter dictionary, diameter cutoffs]
                ['lt7cm', {}, [0, 7]],
            ],  # Output diameter cutoffs for Canadian classes (cm)
        },
    },
}

default_fofem_consume_dict = {
    'canopy_fuels': {
        'foliage_fofem': {
            'summary': ['total'],  # This is fixed as total (filtering is done in trees.py)
            'metrics': ['sum'],  # This is fixed as sum (no user options)
            'units': 'kgpm2',  # This option is fixed (no user options)
            'classes': {
                'dbh': []  # This option is fixed (no user options)
            },
        },
        'branches_fofem': {
            'summary': ['total'],  # This is fixed as total (filtering is done in trees.py)
            'metrics': ['sum'],    # This is fixed as sum (no user options)
            'units': 'kgpm2',  # This option is fixed (no user options)
            'classes': {
                'dbh': []  # This option is fixed (no user options)
            },
        },
    },
    'woody_debris_classes': {
        'fofem': {
            'process_classes': True,  # Process U.S. woody debris classes
            'class_extension': 'fofem',  # Extension for U.S. classes
            'diameter_cutoffs': [0.635, 2.54, 7.62],  # Diameter cutoffs for U.S. classes (cm)
            'transect_lengths': [4, 10, 10, 30],  # Transect lengths for U.S. classes (m)
            # Output request for woody fuels
            # At a minimum, diameter cutoffs must start at the upper diameter limit of tallied data
            'output_request': [
                # [output name extension, filter dictionary, diameter cutoffs]
                ['sound', {'woody_decay':'<=3'}, [0, 0.635, 2.54, 7.62, 15.24, 22.86, 50.8, float('inf')]],
                ['rotten', {'woody_decay':'>3'}, [0, 0.635, 2.54, 7.62, 15.24, 22.86, 50.8, float('inf')]],
            ],  # Output diameter cutoffs for U.S. classes (cm)
        },
    },
    'region': 'InteriorWest',  # Default region (Options: InteriorWest, PacificWest, NorthEast, SouthEast)
    'season': 'Summer',  # Default season (Options: Spring, Summer, Fall, Winter)
    'moisture_regime': 'Very Dry',  # Default moisture regime (Options: Wet, Moderate, Dry, VeryDry)
    'soil_heating': {
        'use_soil_heating': False,  # Use soil heating calculations (requires soil family assignments)
    },
    'fofem_processing_units': 'SI',  # Output units/filename for the FOFEM consumption CSV (Options: 'SI', 'Imperial')
}

# Metrics fixed by the default dictionaries, keyed by an entry's resolved att_source.
# Attributes that are BA-weighted (ht, cbh, dcbh, fsg, flame_length, fire_intensity) are not
# listed because their comments describe allowed options rather than a fixed value.
_FIXED_STAND_SUMMARY_METRICS = {
    'dens': ['sum'],
    'ba': ['sum'],
    'cfl': ['sum'],
    'foliage': ['sum'],
    'branches': ['sum'],
    'wood': ['sum'],
    'bark': ['sum'],
    'foliage_fofem': ['sum'],
    'branches_fofem': ['sum'],
    'cbd': [],
}

# ConPyro stand attributes must each produce one column, so these fixed-name entries hold exactly
# one metric chosen from _SINGLE_METRIC_OPTIONS; anything else falls back to the default.
_SINGLE_METRIC_CONPYRO_ENTRIES = (
    'conpyro_ht_ovrstry_live',
    'conpyro_ht_midstry_live',
    'conpyro_ht_midstry_dead',
    'conpyro_cbh_ovrstry',
    'conpyro_cbh_midstry',
    'conpyro_fsg',
)
_SINGLE_METRIC_OPTIONS = ('min', 'max', 'mean')
_SINGLE_METRIC_DEFAULT = ['mean']


def _enforce_fixed_stand_summary_metrics(stand_summary_params: dict) -> dict:
    """
    Replace user-supplied metrics that the default dictionaries mark as fixed.

    Entries are matched by their resolved att_source (the entry key when att_source is
    omitted). The fixed-by-attribute rule wins over the single-metric ConPyro rule. The
    input dictionary and its nested entries are never modified.

    :param stand_summary_params: Stand-summary entries keyed by entry name.
    :return: A new dictionary in which every fixed attribute's metrics equal the fixed list and
        each single-metric ConPyro entry holds exactly one of min, max, or mean. Entries already
        correct are returned unchanged; each override is logged once as a warning with issue
        code 'fixed_metrics_overridden' or 'single_metric_overridden'.
    """
    enforced = dict(stand_summary_params)
    for name, params in stand_summary_params.items():
        requested = params.get('metrics')
        if requested is None:
            requested = []
        elif isinstance(requested, str):
            requested = [requested]
        else:
            # Repeated metrics add nothing (and would otherwise look like several metrics).
            requested = list(dict.fromkeys(requested))
        att = params.get('att_source', name)
        fixed = _FIXED_STAND_SUMMARY_METRICS.get(att)
        if fixed is not None:
            if requested == fixed:
                if params.get('metrics') != fixed:
                    # Same metrics in a non-list form (None, 'sum'); store the list silently.
                    enforced[name] = {**params, 'metrics': list(fixed)}
                continue
            error_handling.get_logger('trees').warning(
                f"Stand summary '{name}' (att_source '{att}') has fixed metrics {fixed}; "
                f"the requested metrics {requested} were replaced.",
                extra={'issue_code': 'fixed_metrics_overridden'}
            )
            enforced[name] = {**params, 'metrics': list(fixed)}
        elif name in _SINGLE_METRIC_CONPYRO_ENTRIES:
            if len(requested) == 1 and requested[0] in _SINGLE_METRIC_OPTIONS:
                if params.get('metrics') != requested:
                    enforced[name] = {**params, 'metrics': requested}
                continue
            error_handling.get_logger('trees').warning(
                f"ConPyro stand attribute '{name}' must have exactly one metric from "
                f"{list(_SINGLE_METRIC_OPTIONS)}; the requested metrics {requested} were "
                f"replaced with {_SINGLE_METRIC_DEFAULT}.",
                extra={'issue_code': 'single_metric_overridden'}
            )
            enforced[name] = {**params, 'metrics': list(_SINGLE_METRIC_DEFAULT)}
    return enforced


def _find_id_mismatches(plot_ids, form_ids) -> tuple[list, list]:
    """
    Return ordered, deduplicated IDs missing from either side of a form merge.

    :param plot_ids: Plot Attribute identifiers in first-seen order.
    :param form_ids: Component-form identifiers in first-seen order.
    :return: IDs missing from the form and IDs missing from Plot Attributes.
    """
    plot_ids = list(plot_ids)
    form_ids = list(form_ids)
    plot_id_set = set(plot_ids)
    form_id_set = set(form_ids)
    missing_from_form = list(dict.fromkeys(
        unique_id for unique_id in plot_ids if unique_id not in form_id_set
    ))
    extra_in_form = list(dict.fromkeys(
        unique_id for unique_id in form_ids if unique_id not in plot_id_set
    ))
    return missing_from_form, extra_in_form


def _validate_stand_summary_permutations(stand_summary_params: dict, out_dir: str) -> None:
    """Report and reject combined stand summaries with no usable tree group.

    :param stand_summary_params: Configured stand attributes and summary modes.
    :param out_dir: Directory for the run's error report.
    :return: None. Writes fuelanalyst_errors.csv before rejecting invalid input.
    """
    invalid_attributes = [
        name for name, params in stand_summary_params.items()
        if params.get('summary_permutation', 'all') == 'combined'
        and not any(part != 'total' for part in params.get('summary', []))
    ]
    if invalid_attributes:
        message = (
            "summary_permutation='combined' requires at least one summary "
            "other than 'total' for: " + ', '.join(invalid_attributes)
        )
        error_handling.get_logger('trees').error(
            message, extra={'issue_code': 'combined_summary_total_only'}
        )
        error_handling.write_report(os.path.join(out_dir, 'fuelanalyst_errors.csv'))
        raise ValueError(message)


@error_handling.run_guard
def fuel_analyst(
        in_dir: str,
        out_dir: str,
        surface_fire_intensity_model: str,
        stand_summary_params: Optional[dict] = None,
        woody_debris_params: Optional[dict] = None,
        conpyro_params: Optional[dict] = None,
        fofem_consume_params: Optional[dict] = None,
        gen_conpyro_df: bool = False,
        gen_fofem_gui_app_tree_df: bool = False,
        gen_fofem_consume_df: bool = False
) -> None:
    """
    Process Survey123 fuel attributes and write the selected result tables.

    :param in_dir: Path to the input folder containing the survey data.
    :param out_dir: Path to the output folder where results will be saved.
    :param surface_fire_intensity_model: Model to use for surface fire intensity calculations.
    :param stand_summary_params: Dictionary containing stand summary parameters.
    :param woody_debris_params: Dictionary containing parameters for woody debris processing.
    :param conpyro_params: Dictionary containing ConPyro parameters.
    :param fofem_consume_params: Dictionary containing FOFEM consumption parameters, including
        'fofem_processing_units' ('SI' or 'Imperial'; defaults to 'SI' when the key is absent,
        for backward compatibility with dictionaries predating this option). Determines both the
        units written into the FOFEM consumption DataFrame and its output filename (see
        fofem_units.consume_filename()).
    :param gen_conpyro_df: Boolean indicating whether to generate the ConPyro DataFrame.
    :param gen_fofem_gui_app_tree_df: Boolean indicating whether to generate the FOFEM GUI app tree mortality DataFrame.
    :param gen_fofem_consume_df: Boolean indicating whether to generate the FOFEM consumption DataFrame.
    :return: None. Every completed run writes master_fuel_df.csv and
        fuelanalyst_errors.csv; model-preparation outputs depend on the generation
        flags.
    """
    # Create the list of forms to process
    form_select_list = ['plants', 'trees', 'cover', 'woody']

    # Create a dictionary to map form names to their respective directory names
    dir_dict = {
        'plot': '1_Plot_Attributes',
        'plants': '2_Plants_Regeneration',
        'trees': '3_Trees',
        'cover': '4_Canopy_Cover',
        'woody': '5_Woody_Debris'
    }

    # Create a dictionary to map form names to their display names
    form_dict = {
        'plot': 'Plot Attributes',
        'plants': 'Plants and Regeneration',
        'trees': 'Trees',
        'cover': 'Canopy Cover',
        'woody': 'Woody Debris'
    }

    if stand_summary_params is None:
        stand_summary_params = default_stand_summary_dict
    # Work on a copy: the ConPyro and FOFEM entries are merged into it below, which must not
    # change the caller's dictionary or the module-level default.
    stand_summary_params = dict(stand_summary_params)

    if woody_debris_params is None:
        woody_debris_params = default_woody_debris_dict
    # Work on copies: the ConPyro and FOFEM woody-debris classes are merged into the nested
    # dictionary below, which must not change the caller's dictionary or the module-level default.
    woody_debris_params = dict(woody_debris_params)
    woody_debris_params['woody_debris_classes'] = dict(woody_debris_params['woody_debris_classes'])

    if conpyro_params is None:
        conpyro_params = default_conpyro_dict

    if fofem_consume_params is None:
        fofem_consume_params = default_fofem_consume_dict

    if gen_conpyro_df:
        # Verify all forms are present for ConPyro generation
        missing_forms = [
            form for form in form_select_list
            if not os.path.exists(os.path.join(in_dir, dir_dict.get(form)))
        ]
        if missing_forms:
            raise FileNotFoundError(
                f'All Survey123 forms are required to generate the ConPyro DataFrame. '
                f'The following forms are missing:\n{missing_forms}.'
            )

        stand_summary_params.update(
            {k: v for k, v in conpyro_params['stand_attributes'].items()}
        )
        woody_debris_params['woody_debris_classes'].update(conpyro_params['woody_debris_classes'])

    if gen_fofem_gui_app_tree_df:
        # Verify Trees is present: gen_fofem_gui_app_tree_df() is built entirely from
        # master_tree_df, which is only produced when the Trees form is processed.
        missing_forms = [
            form for form in ['trees']
            if not os.path.exists(os.path.join(in_dir, dir_dict.get(form)))
        ]
        if missing_forms:
            raise FileNotFoundError(
                f'The Trees form is required to generate the FOFEM GUI app tree mortality '
                f'DataFrame. The following forms are missing:\n{missing_forms}.'
            )

    if gen_fofem_consume_df:
        # Verify Trees, Plants and Regeneration, and Woody Debris are present: crown foliage/
        # branches come from Trees, herb/shrub loads and dom_substrate/fofem_shrub_group come
        # from Plants and Regeneration, and litter/duff/coarse woody loads come from Woody
        # Debris. Canopy Cover is not required by gen_fofem_consumption_df().
        missing_forms = [
            form for form in ['trees', 'plants', 'woody']
            if not os.path.exists(os.path.join(in_dir, dir_dict.get(form)))
        ]
        if missing_forms:
            raise FileNotFoundError(
                f'Trees, Plants and Regeneration, and Woody Debris are all required to generate '
                f'the FOFEM consumption DataFrame. The following forms are missing:\n{missing_forms}.'
            )

        stand_summary_params.update(
            {k: v for k, v in fofem_consume_params['canopy_fuels'].items() if k != 'woody_debris_classes'}
        )
        woody_debris_params['woody_debris_classes'].update(fofem_consume_params['woody_debris_classes'])

    stand_summary_params = _enforce_fixed_stand_summary_metrics(stand_summary_params)
    _validate_stand_summary_permutations(stand_summary_params, out_dir)

    # Generate a list of columns to keep, using all columns in plot_df to begin with
    keep_columns = ['unique_id']
    form_df = None
    master_tree_df = None
    conpyro_df = None
    fbp_prep_df = None
    fofem_tree_df = None
    fofem_consume_df = None
    fofem_processing_units = None

    # Process plot attributes
    plot_df, add_columns = pa.process_plot_attributes(os.path.join(in_dir, dir_dict.get('plot')),
                                                      os.path.join(out_dir, dir_dict.get('plot')))
    keep_columns.extend(add_columns)

    # Process selected forms
    for form in form_select_list:
        # Get the input and output paths for the current form
        in_path = os.path.join(in_dir, dir_dict.get(form))
        out_path = os.path.join(out_dir, dir_dict.get(form))

        # Filter the plot_df for the current form
        mask = plot_df['form_select'].str.contains(form, na=False)

        # Get the unique IDs for the current form
        id_list = plot_df.loc[mask, 'unique_id'].tolist()

        # Check if the input path exists
        if not os.path.exists(in_path):
            if mask.any():
                for missing_id in id_list:
                    error_handling.get_logger(form).warning(
                        f'Input folder for {form_dict[form]} is missing but this plot '
                        f'selected this form; it will have no {form_dict[form]} data.',
                        extra={'unique_id': missing_id, 'issue_code': 'form_folder_missing'},
                    )
            continue

        # Only process the form if there are IDs to process
        if mask.any():
            if form == 'plants':
                form_df, add_columns = pr.process_plants_regen(in_path, out_path)
            elif form == 'trees':
                (form_df, add_columns,
                 master_tree_df) = trees.process_trees(in_path,
                                                       out_path,
                                                       surface_fire_intensity_model,
                                                       stand_summary_params,
                                                       gen_conpyro_df)
            elif form == 'cover':
                form_df, add_columns = cc.process_canopy_cover(in_path, out_path)
            elif form == 'woody':
                form_df, add_columns = wd.process_woody_debris(in_path, out_path, plot_df[mask], woody_debris_params)

            # Add the new columns to the keep_columns list
            keep_columns.extend(add_columns)

            # Verify that all IDs in id_list are present in the form_df, and vice versa
            missing_from_form, extra_in_form = _find_id_mismatches(
                id_list, form_df['unique_id'].values
            )
            if missing_from_form or extra_in_form:
                print(f'\tWarning:')
                for missing_id in missing_from_form:
                    error_handling.get_logger(form).warning(
                        f'Plot is in the Plot Attributes dataset but not in {form_dict[form]}.',
                        extra={'unique_id': missing_id, 'issue_code': 'id_missing_from_form'},
                    )
                for extra_id in extra_in_form:
                    error_handling.get_logger(form).warning(
                        f'Plot is in the {form_dict[form]} dataset but not in Plot Attributes.',
                        extra={'unique_id': extra_id, 'issue_code': 'id_extra_in_form'},
                    )
            else:
                print(f'\tAll IDs from the Plot Attributes dataset are present in the {form} dataset. Merging data.')

            # Drop columns in form_df that are already in plot_df, except for unique_id
            form_df = form_df.drop(
                columns=[col for col in form_df.columns if col in plot_df.columns and col != 'unique_id']
            )

            # Merge the form_df with plot_df based on unique_id
            plot_df = pd.merge(plot_df, form_df, on='unique_id', how='left')

    # ### PROCESS ConPyro DATA
    if gen_conpyro_df:
        conpyro_df, fbp_prep_df = conpyro_attributes.gen_conpyro_df(plot_df, conpyro_params)

    # ### PROCESS FOFEM DATA
    if gen_fofem_gui_app_tree_df:
        fofem_tree_df = fofem_attributes.gen_fofem_gui_app_tree_df(plot_df, master_tree_df)
    if gen_fofem_consume_df:
        fofem_processing_units = fofem_units.validate_fofem_units(
            fofem_consume_params.get('fofem_processing_units', 'SI')
        )
        fofem_consume_df = fofem_attributes.gen_fofem_consumption_df(plot_df, fofem_consume_params)

    # ### PROCESS OUTPUTS
    # Make the out_dir if it does not exist
    os.makedirs(out_dir, exist_ok=True)

    # Save the Master Fuel DataFrame to the output folder if it exists
    if plot_df is not None:
        master_df_path = os.path.join(out_dir, 'master_fuel_df.csv')
        print(f'\n\nSaving the Master Fuel DataFrame to: {master_df_path}')
        plot_df = plot_df[keep_columns]  # Keep only the specified columns
        helper.export_csv(plot_df, master_df_path)

    error_report_path = os.path.join(out_dir, 'fuelanalyst_errors.csv')
    print(f'Saving the Error Report to: {error_report_path}')
    error_handling.write_report(error_report_path, plot_df=plot_df)

    # Save the Master Tree DataFrame to the output folder if it exists
    if master_tree_df is not None:
        master_tree_df_path = os.path.join(out_dir, 'master_tree_df.csv')
        print(f'Saving the Master Tree DataFrame to: {master_tree_df_path}')
        helper.export_csv(master_tree_df, master_tree_df_path)

    # Save the ConPyro DataFrame to the output folder if it exists
    if conpyro_df is not None:
        conpyro_df_path = os.path.join(out_dir, 'conpyro_df.csv')
        print(f'Saving the ConPyro DataFrame to: {conpyro_df_path}')
        helper.export_csv(conpyro_df, conpyro_df_path)

    if fbp_prep_df is not None:
        fbp_df_path = os.path.join(out_dir, 'fbp_prep_df.csv')
        print(f'Saving the FBP Prep DataFrame to: {fbp_df_path}')
        helper.export_csv(fbp_prep_df, fbp_df_path)

    # Save the FOFEM GUI App Tree Mortality DataFrame to the output folder if it exists
    if fofem_tree_df is not None:
        fofem_tree_df_path = os.path.join(out_dir, 'fofem_gui_app_tree_mortality_df.csv')
        print(f'Saving the FOFEM GUI App Tree Mortality DataFrame to: {fofem_tree_df_path}')
        helper.export_csv(fofem_tree_df, fofem_tree_df_path)

    # Save the FOFEM Consumption DataFrame to the output folder if it exists
    if fofem_consume_df is not None:
        fofem_consume_df_path = os.path.join(out_dir, fofem_units.consume_filename(fofem_processing_units))
        print(f'Saving the FOFEM Consumption DataFrame to: {fofem_consume_df_path}')
        helper.export_csv(fofem_consume_df, fofem_consume_df_path)

    return


# Test routine for Fuel Analyst
if __name__ == '__main__':
    # Define input and output folders
    examples_dir = helper.get_examples_dir(os.path.dirname(__file__))
    _in_dir = os.path.join(examples_dir, 'data', 'Survey123_Data')
    _out_dir = os.path.join(examples_dir, 'results', 'fuel_analyst')
    _surface_fire_intensity_model = 'Byram'
    _stand_summary_dict = None      # Uses default stand summary settings if None
    _woody_debris_dict = None       # Uses default woody debris settings if None
    _conpyro_dict = None            # Uses default ConPyro settings if None
    _fofem_consume_dict = None      # Uses default FOFEM woody debris settings if None
    _gen_conpyro_df = True          # Whether to generate the ConPyro DataFrame
    _gen_fofem_gui_app_tree_df = False  # Whether to generate the FOFEM GUI app tree mortality DataFrame
    _gen_fofem_consume_df = True    # Whether to generate the FOFEM consumption DataFrame

    # Run the main fuel_analyst function
    fuel_analyst(in_dir=_in_dir,
                 out_dir=_out_dir,
                 surface_fire_intensity_model=_surface_fire_intensity_model,
                 stand_summary_params=_stand_summary_dict,
                 woody_debris_params=_woody_debris_dict,
                 conpyro_params=_conpyro_dict,
                 fofem_consume_params=_fofem_consume_dict,
                 gen_conpyro_df=_gen_conpyro_df,
                 gen_fofem_gui_app_tree_df=_gen_fofem_gui_app_tree_df,
                 gen_fofem_consume_df=_gen_fofem_consume_df)
