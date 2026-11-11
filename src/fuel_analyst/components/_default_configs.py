"""
Default configuration dictionaries for FuelAnalyst.

This module imports nothing from the package. fuel_analyst.py and run_conpyro.py
re-export their public defaults; the emission components re-export the shared
season defaults. Callers pass configuration dictionaries down as arguments.
"""
import os


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
    'sros_model': {'forest': 13, 'grass_herbs': 31, 'shrubs': 31},  # Shrubs use O1b as a temporary proxy
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
            # The default uses the crown base height of live conifers as the fuel strata gap
            # (options: cbh, fsg); use 'fsg' to summarize the tree-level fuel strata gap instead
            'att_source': 'cbh',
            'override_field_name': True,  # This is fixed (no user options)
            'summary': ['live', 'conifer'],  # This is the default (options: see above)
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

default_tree_sampling_dict = {
    'dbh_thresholds_cm': {
        'small_tree_min': 5.0,
        'large_tree_min': 12.5,
    },
    'protocol_column': None,
    'protocol_overrides': {},
}

default_fire_modelling_dict = {
    'num_workers': max(1, (os.cpu_count() or 2) - 1),
    'conpyro': {
        'run_model': True,
        'plot_id_col_name': 'unique_id',
        'input_params': {
            'cfo_model': 5,    # Options: 1, 2, 3, 4, 5, 10, or string "use_csv" (assumes cfo_model column in csv)
            'grass_curing': 60,  # Grass curing percentage passed to ConPyro as gcf
            'sros_model': 'use_csv',  # Options: 1-4, 9, 11, 12, 13, 16-21, 30/31 (O1a/O1b), labels "9c", "11c", "18c", "r20", or "use_csv"
                               # (assumes sros_model column in csv). 16, 17, and 20 need model_terrain_effects_on_wind
                               # False; 21 is the legacy mountain pine beetle curve (it was 20 before ConPyro 0.2.0)
            'cros_model': 1,   # Options: 1, 2, or string "use_csv" (assumes cros_model column in csv)
            'process_ladder': False,     # Toggle ladder fuel processing on/off
            'smooth_ros': True,          # Toggle ROS smoothing function on/off
            'model_terrain_effects_on_wind': True,  # Toggle terrain (slope/aspect) effects on wind speed and direction
            'model_terrain_effects_on_ffmc': False,  # Toggle terrain (slope/aspect) effects on FFMC
            'suppress_messages': True,              # Toggle ConPyro processing messages on/off
            'wx_date': 'use_csv',   # Options: Integer in format YYYYMMDD, or string "use_csv" (default)
                                    #    wx_date used for fine dead fuel and ladder foliar MC calculations
            'fmc': None,            # Options: float, integer, None (default)
                                    #     fmc overrides wx_date for foliar MC calculations
            'season': None,         # Options: None (default), "Sp", "Sp-Su", "T", "Su", "F", "use_csv";
                                    #     season overrides wx_date for fine dead fuel MC calculations
            'time': None,           # Options: Integer in format HHMM, None (default), or string "use_csv"
                                    #     time is only needed for CFIS (cfo_model == 10) to calculate
                                    #     Rothermel dead fuel moisture content at a specific time of day
        },
        'output_params': {
            'out_request': [
                'mc_sa', 'mc_dmc', # Needed for FOFEM emissions modelling
                'fsg', 'cac', 'cfo_prob',
                'sros', 'cros', 'hros', 'bros',
                'sfc', 'cfc', 'tfc',
                'sfi', 'cfi', 'hfi',
                'cfb', 'fire_type'
            ],
            # Leave flame_comp_out_list fixed for the time being - do not let user adjust
            'flame_comp_out_list': [
                'instand_ws', 'flame_length_m', 'flame_tilt', 'flame_height', 'flame_res_time', 'flame_depth'
            ],
        },
    },
    'fofem_mortality': {
        'run_model': True,                      # Switch; Default: True
        'plot_id_col_name': 'unique_id',        # User defined; default: 'unique_id'
        'fofem_tree_id_col_name': 'unique_id',  # User defined; default: 'unique_id'
    },
    'fofem_emissions': {
        'run_model': True,                  # Switch; Default: True
        'model_select': 'pyfofem',          # Options: 'pyfofem', 'fof_gui'; Default: 'pyfofem'
                                            #     pyfofem uses the pyfofem Python package to model emissions
                                            #     fof_gui uses the USFS FOFEM GUI executable to batch model emissions
                                            #        using "legacy" (old) emissions calculation settings
        'plot_id_col_name': 'unique_id',    # User defined; default: 'unique_id'
        'emissions_mode': 'expanded',       # Emissions modelling modes for pyfofem
                                            #     Options: 'legacy', 'default', 'expanded'
        'model_soil_heating': False,        # If True, pass SoilFamily data to pyfofem soil-heating model
        'emissions_units': 'SI',            # Options: 'Imperial', 'SI'. Must match the unit system
                                            #     of in_fofem_consume_csv_path's own filename (see
                                            #     fofem_units.py) - validated against it before any
                                            #     backend runs. Set independently from, and not
                                            #     automatically synced with, fuel_analyst()'s own
                                            #     fofem_processing_units setting (a separate call,
                                            #     possibly a separate process); it is this setting
                                            #     and the consumption file it points to that must
                                            #     agree, not the two dictionaries themselves.
        'force_flame_res_time_limits': True,  # Clip flame_res_time_sec to FOFEM/Burnup's valid range
                                              #     (10-200s) instead of letting Burnup silently drop
                                              #     out-of-range scenarios from the emissions estimate
    },
}

# Dictionary of seasons for each month in the year
default_season_start_dict = {
    'Spring': '0415',
    'Summer': '0615',
    'Fall': '0915',
    'Winter': '1115',
}
