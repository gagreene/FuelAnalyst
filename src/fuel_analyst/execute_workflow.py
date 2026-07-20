## run fuel_analyst

import os

from fuel_analyst import fuel_analyst
from extract_BECType import _load_plots, _extract_BECType, infill_bec_data
from fbp_fuel_type import process_fbp_fuel_type
from extract_nrcan_wx import extract_weather_data
from merge_wx_data import merge_weather_data
from run_conpyro import run_conpyro

from src.fuel_analyst.components import helper, trees, conpyro_attributes, fofem_attributes
from src.fuel_analyst.components import plot_attributes as pa
from src.fuel_analyst.components import plants_regen as pr
from src.fuel_analyst.components import canopy_cover as cc
from src.fuel_analyst.components import woody_debris as wd



# ── Environment detection ────────────────────────────────────────────────────
is_docker = os.path.exists('/.dockerenv')


# ── 1. Fuel Analyst ──────────────────────────────────────────────────────────
if is_docker:
    _in_dir  = os.getenv('DATA_BASE_DIR', '/app/input_data')
    _out_dir = os.getenv('OUTPUT_FuelAnalyst', '/app/output/fuel_analyst')
    os.makedirs(_out_dir, exist_ok=True)
## Else run test 
else:
    examples_dir = helper.get_examples_dir(os.path.dirname(__file__))
    _in_dir = os.path.join(examples_dir, 'data', 'Survey123_Data')
    _out_dir = os.path.join(examples_dir, 'results', 'fuel_analyst')

_surface_fire_intensity_model = 'Byram'
_stand_summary_dict   = None    # Uses default stand summary settings if None
_woody_debris_dict    = None    # Uses default woody debris settings if None
_conpyro_dict         = None    # Uses default ConPyro settings if None
_fofem_consume_dict   = None    # Uses default FOFEM woody debris settings if None
_gen_conpyro_df       = True    # Whether to generate the ConPyro DataFrame
_gen_fofem_tree_df    = True    # Whether to generate the FOFEM tree DataFrame
_gen_fofem_consume_df = True    # Whether to generate the FOFEM consumption DataFrame

fuel_analyst(
    in_dir=_in_dir,
    out_dir=_out_dir,
    surface_fire_intensity_model=_surface_fire_intensity_model,
    stand_summary_params=_stand_summary_dict,
    woody_debris_params=_woody_debris_dict,
    conpyro_params=_conpyro_dict,
    fofem_consume_params=_fofem_consume_dict,
    gen_conpyro_df=_gen_conpyro_df,
    gen_fofem_tree_df=_gen_fofem_tree_df,
    gen_fofem_consume_df=_gen_fofem_consume_df,
)

print('Fuel analyst complete. Proceeding to extract BEC data.')

# ── 2. BEC Type Extraction ───────────────────────────────────────────────────
if is_docker:
    _fuel_analyst_out = os.getenv('OUTPUT_FuelAnalyst', '/app/output/fuel_analyst')
    _BEC_shp_dir      = os.path.join(os.getenv('BEC_DATA_DIR', '/app/BEC_data'), 'VEG_COMP_LYR_R1_POLY_2025.gdb')
    _plot_pts_path    = os.path.join(_fuel_analyst_out, 'conpyro_df.csv')
    _fbp_prep_path    = os.path.join(_fuel_analyst_out, 'fbp_prep_df.csv')
    _fbp_out_path     = os.path.join(_fuel_analyst_out, 'fbp_prep_df_BEC.csv')
    _gpkg_out_path    = '/app/output/plots.gpkg'
else:
    test_dir       = os.path.join(os.path.dirname(__file__), 'tests', 'results', 'fuel_analyst')
    ## local VRI location 
    _BEC_shp_dir   = "C:/Users/ssmithtr/Desktop/CleanTest/BEC_data/VEG_COMP_LYR_R1_POLY_2025.gdb"
    if os.path.isdir(_BEC_shp_dir):
        print('Error: Local version of BC VRI not detected - please adjust')
    _plot_pts_path = os.path.join(test_dir, 'conpyro_df.csv')
    _fbp_prep_path = os.path.join(test_dir, 'fbp_prep_df.csv')
    _fbp_out_path  = os.path.join(test_dir, 'fbp_prep_df_BEC.csv')

_BEC_layer        = 'VEG_COMP_LYR_R1_POLY'
_plot_id_col_name = 'unique_id'
_lat_col_name     = 'lat'
_lon_col_name     = 'long'

plots_gdf = _load_plots(_plot_pts_path, _lat_col_name, _lon_col_name)

bec_info_df = _extract_BECType(
    plots=plots_gdf,
    plot_id_col_name=_plot_id_col_name,
    BEC_shp_dir=_BEC_shp_dir,
    BEC_layer=_BEC_layer,
)

fbp_prep_df_updated = infill_bec_data(
    fbp_prep_path=_fbp_prep_path,
    bec_info_df=bec_info_df,
    plot_id_col=_plot_id_col_name,
)

fbp_prep_df_updated.to_csv(_fbp_out_path, index=False)
print(f'BEC type extraction complete. Results saved to {_fbp_out_path}')


# ── 3. FBP Fuel Typing ───────────────────────────────────────────────────────
if is_docker:
    _fuel_analyst_out = os.getenv('OUTPUT_FuelAnalyst', '/app/output/fuel_analyst')
    _out_dir          = os.getenv('OUTPUT_FBP', '/app/output/fbp_fuel_typing')
    if not os.path.exists(_fuel_analyst_out) or len(os.listdir(_fuel_analyst_out)) == 0:
        print('Files from prior fuel analyst step not found. Please run fuel analyst first.')
    _master_fuel_df_path = os.path.join(_fuel_analyst_out, 'master_fuel_df.csv')
    _conpyro_df_path     = os.path.join(_fuel_analyst_out, 'conpyro_df.csv')
    _fbp_prep_df_path    = os.path.join(_fuel_analyst_out, 'fbp_prep_df_BEC.csv')
else:
    examples_dir = helper.get_examples_dir(os.path.dirname(__file__))
    _out_dir = os.path.join(examples_dir, 'results', 'fbp_fuel_typing')

    # Get stand fire and FOFEM consume csv paths
    _master_fuel_df_path = os.path.join(examples_dir, 'results', 'fuel_analyst', 'master_fuel_df.csv')
    _fbp_prep_df_path = os.path.join(examples_dir, 'data', 'fbp_fuel_typing', 'fbp_prep_df.csv')
    _conpyro_df_path = os.path.join(examples_dir, 'results', 'fuel_analyst', 'conpyro_df.csv')

_season = 'growing'  # Options: 'growing' or 'dormant'

process_fbp_fuel_type(_master_fuel_df_path, _fbp_prep_df_path, _conpyro_df_path, _out_dir, _season)

print('FBP fuel typing complete. Proceeding to weather data extraction.')


# ── 4. Weather Data Extraction ───────────────────────────────────────────────
if is_docker:
    _fuel_analyst_out = os.getenv('OUTPUT_FuelAnalyst', '/app/output/fuel_analyst')
    _wx_data_dir      = os.getenv('NRCAN_DATA_DIR', '/app/nrcan_data')
    _out_dir          = os.getenv('OUTPUT_WX_EXTRACT', '/app/output/wx_extract')
    _plot_pts_path    = os.path.join(_fuel_analyst_out, 'conpyro_df.csv')
else:
    test_dir       = os.path.join(os.path.dirname(__file__), 'tests')
    ## path to local weather data 
    _wx_data_dir   ="D:/_NRCAN_Gridded_FWI_Data"
    # If weather data does not exist print error 
    if os.path.isdir(_wx_data_dir):
        print('Error: NRCAN gridded weather data not found - please specify the correct file location')
    _out_dir       = os.path.join(test_dir, 'results', 'wx_extract')
    _plot_pts_path = os.path.join(test_dir, 'results', 'fuel_analyst', 'conpyro_df.csv')

_out_file_name          = 'wx_data'
_plot_id_col_name       = 'unique_id'
_lat_col_name           = 'lat'    # Decimal degrees, WGS84 (EPSG:4326); reprojected to EPSG:3978 internally
_lon_col_name           = 'long'
_wx_var_list            = ['temp', 'pcp', 'rh', 'ws', 'wd', 'ffmc', 'dmc', 'dc', 'bui', 'isi', 'fwi']
_start_year             = 2005
_end_year               = 2024
_use_bcws_dates         = False  # If True, use BCWS fire season dates based on plot ecodivision
_start_month_day        = 501    # MMDD as integer; required if use_bcws_dates is False
_end_month_day          = 930    # MMDD as integer; required if use_bcws_dates is False
_calculate_percentiles  = True
_percentile_var_list    = ['fwi']

extract_weather_data(
    wx_data_dir=_wx_data_dir,
    out_dir=_out_dir,
    out_file_name=_out_file_name,
    plot_pts_path=_plot_pts_path,
    plot_id_col_name=_plot_id_col_name,
    lat_col_name=_lat_col_name,
    lon_col_name=_lon_col_name,
    wx_var_list=_wx_var_list,
    start_year=_start_year,
    end_year=_end_year,
    use_bcws_dates=_use_bcws_dates,
    start_month_day=_start_month_day,
    end_month_day=_end_month_day,
    calculate_percentiles=_calculate_percentiles,
    percentile_var_list=_percentile_var_list,
)

print('Weather data extraction complete. Proceeding to merge.')


# ── 5. Merge Weather Data ────────────────────────────────────────────────────
if is_docker:
    _fbp_out_dir   = os.getenv('OUTPUT_FBP', '/app/output/fbp_fuel_typing')
    _wx_out_dir    = os.getenv('OUTPUT_WX_EXTRACT', '/app/output/wx_extract')
    _wx_data_path  = os.path.join(_wx_out_dir, 'wx_data.csv')
    _plot_data_path = os.path.join(_fbp_out_dir, 'conpyro_df_fbp.csv')
    _out_path      = os.path.join(_wx_out_dir, 'conpyro_df_wx.csv')
else:
    # Define input and output directories
    examples_dir = helper.get_examples_dir(os.path.dirname(__file__))
    _out_dir = os.path.join(examples_dir, 'results', 'wx_extract')
    _out_file_name = 'wx_data'
    _out_path = os.path.join(_out_dir, _out_file_name)
    _wx_out_dir     = os.path.join(examples_dir, 'results', 'wx_extract')
    _wx_data_path   = os.path.join(_wx_out_dir, 'wx_data.csv')
    _plot_data_path = os.path.join(examples_dir, 'results', 'fbp_fuel_typing', 'conpyro_df_fbp.csv')


_plot_merge_col_name    = 'unique_id'
_wx_merge_col_name      = 'unique_id'   # Set to None to merge all weather data with each plot
_wx_merge_vars          = None
_add_season             = True
_refine_fbp_seasonally  = True
_summer_start           = 615
_fall_start             = 915

merge_weather_data(
    plot_data_path=_plot_data_path,
    plot_merge_col_name=_plot_merge_col_name,
    wx_data_path=_wx_data_path,
    wx_merge_col_name=_wx_merge_col_name,
    wx_merge_vars=_wx_merge_vars,
    out_path=_out_path,
    add_season=_add_season,
    refine_fbp_seasonally=_refine_fbp_seasonally,
    summer_start=_summer_start,
    fall_start=_fall_start,
)

print('Weather merge complete. Proceeding to ConPyro modelling.')


# ── 6. ConPyro Modelling ─────────────────────────────────────────────────────

## set a default fire modeling 
default_fire_modelling_dict = {
    'num_workers': max(1, os.cpu_count()-1),
    'conpyro': {
        'run_model': True,
        'plot_id_col_name': 'unique_id',
        'input_params': {
            'cfo_model': 5,    # Options: 1, 2, 3, 4, 5, 10, or string "use_csv" (assumes cfo_model column in csv)
            'sros_model': 13,  # Options: 1, 2, 3, 4, 12, 13, 20, or string "use_csv" (assumes sros_model column in csv)
            'cros_model': 1,   # Options: 1, 2, or string "use_csv" (assumes cros_model column in csv)
            'process_ladder': False,     # Toggle ladder fuel processing on/off
            'smooth_ros': True,          # Toggle ROS smoothing function on/off
            'model_terrain_effects_on_wind': True,  # Toggle terrain (slope/aspect) effects on wind speed and direction
            'model_terrain_effects_on_ffmc': True,  # Toggle terrain (slope/aspect) effects on FFMC
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
        'emissions_units': 'Imperial',      # Options: 'Imperial' (kgha), 'SI' (kg/ha)
    },
}

if is_docker:
    _fuel_analyst_out    = os.getenv('OUTPUT_FuelAnalyst', '/app/output/fuel_analyst')
    _wx_out_dir          = os.getenv('OUTPUT_WX_EXTRACT', '/app/output/wx_extract')
    _out_dir             = os.getenv('OUTPUT_CONPYRO', '/app/output/conpyro')
    _in_conpyro_csv_path = os.path.join(_wx_out_dir, 'conpyro_df_wx.csv')
    _tree_csv_path       = os.path.join(_fuel_analyst_out, 'master_tree_df.csv')
    _fofem_consume_csv_path = os.path.join(_fuel_analyst_out, 'fofem_consume_df.csv')
else:
    # Define input and output folders
    examples_dir = helper.get_examples_dir(os.path.dirname(__file__))
    _out_dir = os.path.join(examples_dir, 'results', 'conpyro')
    # The ConPyro input dataframe must have weather data attached for ConPyro/FOFEM modelling
    # Required weather columns for ConPyro modelling: 'ws', 'wd', 'ffmc', 'dmc', 'bui', 'temp', 'rh'
    # Required weather columns for FOFEM mortality modelling: 'ws', 'temp'
    _in_dir = os.path.join(examples_dir, 'results', 'wx_extract')
    _in_conpyro_csv_path = os.path.join(_in_dir, 'conpyro_df_wx.csv')
    _tree_csv_path = os.path.join(examples_dir, 'results', 'fuel_analyst', 'master_tree_df.csv')
    _fofem_consume_csv_path = os.path.join(examples_dir, 'results', 'fuel_analyst', 'fofem_consume_df.csv')

_fire_modelling_dict = default_fire_modelling_dict

    # Run ConPyro modelling
run_conpyro(
    out_dir=_out_dir,
    in_conpyro_csv_path=_in_conpyro_csv_path,
    in_tree_csv_path=_tree_csv_path,
    in_fofem_consume_csv_path=_fofem_consume_csv_path,
    fire_modelling_params=_fire_modelling_dict,
)


print('ConPyro modelling complete.')
