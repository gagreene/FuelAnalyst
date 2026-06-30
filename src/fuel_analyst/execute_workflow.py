
## run fuel_analyst
import os
from fuel_analyst import fuel_analyst
from extract_BECType import _load_plots
from extract_BECType import _extract_BECType
from extract_BECType import _infill_bec_data
from fbp_fuel_type import process_fbp_fuel_type
from extract_nrcan_wx import extract_weather_data
### determine environment (docker or local)
is_docker = os.path.exists('/.dockerenv')

if is_docker:
    # Docker environment
    _in_dir = os.getenv('DATA_BASE_DIR', '/app/input_data')
    _out_dir = os.getenv('OUTPUT_FuelAnalyst', '/app/output/fuel_analyst')

    # Verify output directory exists and check contents
    os.makedirs(_out_dir, exist_ok=True)
    list_files = os.listdir(_out_dir)
    if len(list_files) == 0:
        print('Note that you have to manually edit fbp_data_prep.csv after running this script')
else:
    # Non-Docker (local) environment
    test_dir = os.path.join(os.path.dirname(__file__), 'tests')
    _in_dir = os.path.join(test_dir, 'test_data', 'Survey123_Data')
    _out_dir = os.path.join(test_dir, 'results', 'fuel_analyst')


_surface_fire_intensity_model = 'Byram'
_stand_summary_dict = None      # Uses default stand summary settings if None
_woody_debris_dict = None       # Uses default woody debris settings if None
_conpyro_dict = None            # Uses default ConPyro settings if None
_fofem_consume_dict = None      # Uses default FOFEM woody debris settings if None
_gen_conpyro_df = True          # Whether to generate the ConPyro DataFrame
_gen_fofem_tree_df = True       # Whether to generate the FOFEM tree DataFrame
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
             gen_fofem_tree_df=_gen_fofem_tree_df,
             gen_fofem_consume_df=_gen_fofem_consume_df)

print('fuel analyst run, proceeeding to extract necessary BEC data')

if is_docker:
    _BEC_shp_dir = os.path.join(os.getenv('BEC_DATA_DIR', '/app/BEC_data'), 'VEG_COMP_LYR_R1_POLY_2025.gdb')
    _plot_pts_path = os.path.join('OUTPUT_FuelAnalyst', '/app/output/fuel_analyst', 'conpyro_df.csv')
    _fbp_prep_path = os.path.join('OUTPUT_FuelAnalyst', '/app/output/fuel_analyst', 'fbp_prep_df.csv')
    _fbp_out_path = os.path.join('OUTPUT_FBP', '/app/output/fuel_analyst/fbp_prep_df_BEC.csv')  
    _gpkg_out_path = os.path.join('/app/output/plots.gpkg') 
else:
    _BEC_shp_dir = r'I:/_Weather_Data/NRCAN_FWIS_Database/VEG_COMP_LYR_R1_POLY_2025.gdb'
    test_dir = os.path.join(os.path.dirname(__file__), 'tests', 'results', 'fuel_analyst')
    _plot_pts_path = os.path.join(test_dir, 'conpyro_df.csv')
    _fbp_prep_path = os.path.join(test_dir, 'fbp_prep_df.csv')
    _fbp_out_path = os.path.join(test_dir, 'fbp_prep_df_BEC.csv')

_BEC_layer = 'VEG_COMP_LYR_R1_POLY'
_plot_id_col_name = 'unique_id'
_lat_col_name = 'lat'
_lon_col_name = 'long'

plots_gdf = _load_plots(_plot_pts_path, _lat_col_name, _lon_col_name)

bec_info_df = _extract_BECType(
    plots=plots_gdf,
    plot_id_col_name=_plot_id_col_name,
    BEC_shp_dir=_BEC_shp_dir,
    BEC_layer=_BEC_layer
)

fbp_prep_df_updated = infill_bec_data(
    fbp_prep_path=_fbp_prep_path,
    bec_info_df=bec_info_df,
    plot_id_col=_plot_id_col_name
)

fbp_prep_df_updated.to_csv(_fbp_out_path, index=False)
print(f'BEC type extraction complete. Results saved to {_fbp_out_path}')


## run fuel typing algorithm 

   # Define the environment as "dockerized" or not 

if is_docker:
    # Docker environment file paths 
    test_dir = os.getenv('DATA_BASE_DIR', '/app/input_data')
    _out_dir = os.getenv('OUTPUT_FBP', '/app/output/fbp_fuel_typing')
    _prior_file = os.getenv('OUTPUT_FuelAnalyst', '/app/output/fuel_analyst')
    if not os.path.exists(_prior_file) or len(os.listdir(_prior_file)) == 0:
        print('Files created in prior fuel analyst steps not found. Please run fuel analyst first to generate the necessary files for FBP fuel typing.')
    if os.path.exists(_prior_file) and len(os.listdir(_prior_file)) > 0:
        _master_fuel_df_path = os.path.join('OUTPUT_FuelAnalyst', '/app/output/fuel_analyst', 'master_fuel_df.csv')
        _conpyro_df_path = os.path.join(_prior_file,'conpyro_df.csv')
        _fbp_prep_df_path = os.path.join('OUTPUT_FuelAnalyst', '/app/output/fuel_analyst', 'fbp_prep_df_BEC.csv')
## Non-Docker Environment
else:
    # Local Windows development (follow the instructions)
    # Define input folder 
    test_dir = r'C:\Users\ssmithtr\Desktop\SiteModels\FuelAnalyst_test_data\test_data_LLCF-WBFN_2026-04-14'
    ## define output folder 
    _out_dir = os.path.join(test_dir, 'results', 'fbp_fuel_typing')
    _master_fuel_df_path = os.path.join(test_dir, 'results', 'fuel_analyst', 'master_fuel_df.csv')
    _fbp_prep_df_path = os.path.join(test_dir, 'test_data', 'fbp_fuel_typing', 'fbp_prep_df.csv')
    _conpyro_df_path = os.path.join(test_dir, 'results', 'fuel_analyst', 'conpyro_df.csv')

# define growing season type
_season = 'growing'  # Options: 'growing' or 'dormant'

# Run FBP fuel type processing
process_fbp_fuel_type(_master_fuel_df_path, _fbp_prep_df_path, _conpyro_df_path, _out_dir, _season)


## fuel types assigned now running weather data 
if is_docker:
    # Docker environment file paths 
    _wx_data_dir = os.getenv('NRCAN_DATA_DIR', '/app/nrcan_data')
    test_dir = os.getenv('DATA_BASE_DIR', '/app/input_data')
    _out_dir =  os.getenv('OUTPUT_WX_EXTRACT', 'app/output/wx_extract')
    _plot_pts_path = os.path.join('OUTPUT_FuelAnalyst', '/app/output/fuel_analyst', 'conpyro_df.csv')
## Non-Docker Environment
else:
    # Local Windows development (follow the instructions)
        # Define input and output directories
    _wx_data_dir = r'I:/_Weather_Data/NRCAN_FWIS_Database'  # Parent directory containing NRCAN gridded weather data
    test_dir = os.path.join(os.path.dirname(__file__), 'tests')
    _out_dir = os.path.join(test_dir, 'results', 'wx_extract')
    _plot_pts_path = os.path.join(test_dir, 'results', 'fuel_analyst', 'conpyro_df.csv')

_out_file_name = f'wx_data'
_plot_id_col_name = 'unique_id'
_lat_col_name = 'lat'  # Always decimal degrees, WGS84 (EPSG:4326) for input CSV; will be reprojected to EPSG:3978
_lon_col_name = 'long'  # Always decimal degrees, WGS84 (EPSG:4326) for input CSV; will be reprojected to EPSG:3978
_wx_var_list = ['temp', 'pcp', 'rh', 'ws', 'wd', 'ffmc', 'dmc', 'dc', 'bui', 'isi', 'fwi']
_start_year = 2005
_end_year = 2024
_use_bcws_dates = False  # If true, determine in-season dates based on BCWS fire season dates and plot ecodivision
_start_month_day = 501  # MMDD as integer; required if use_bcws_dates is False
_end_month_day = 930  # MMDD as integer; required if use_bcws_dates is False
_calculate_percentiles = True
_percentile_var_list = ['fwi']

# Extract weather data and save results
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


## merging weather data 
if is_docker:
    # Docker environment file paths 
    _wx_data_dir = os.getenv('NRCAN_DATA_DIR', '/app/weather_data')
    test_dir = os.getenv('DATA_BASE_DIR', '/app/input_data')
    _out_dir =  os.getenv('OUTPUT_WX_EXTRACT', 'app/output/wx_extract')
    # Extracted weather data here (defined in extract_nrcan_wx.py)
    _out_file_name = 'wx_data'
    _wx_data_path = os.path.join(_out_dir, f'{_out_file_name}.csv')
    ## Merging with plot data 
    _plot_data_loc = os.getenv('OUTPUT_FBP', 'app/ouput/fpb_fuel_typing')
    _plot_data_path = os.path.join(_plot_data_loc, 'conpyro_df_fbp.csv')
    # output stored 
    _out_path = os.path.join(_out_dir, f'conpyro_df_wx.csv')
## Non-Docker Environment
else:
    # Local Windows development (follow the instructions)
    # Define input and output directories
    test_dir = os.path.join(os.path.dirname(__file__), 'tests')
    _out_dir = os.path.join(test_dir, 'results', 'wx_extract')
    _out_file_name = 'wx_data'
    _plot_data_path = os.path.join(test_dir, 'results', 'fbp_fuel_typing', 'conpyro_df_fbp.csv')
    _wx_data_path = os.path.join(_out_dir, f'{_out_file_name}.csv')

## Define arguments for script
_plot_merge_col_name = 'unique_id'
_wx_merge_col_name = 'unique_id'  # Assign as None to merge all weather data with each plot
_wx_merge_vars = None
_add_season = True
_refine_fbp_seasonally = True
_summer_start = 615
_fall_start = 915

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
    fall_start=_fall_start
)



## run conpyro 
if is_docker:
    # Docker environment file paths 
    test_dir = os.getenv('DATA_BASE_DIR', '/app/input_data')
    _out_dir =  os.getenv('OUTPUT_CONPYRO', 'app/output/conpyro')
    _in_dir = os.getenv('OUTPUT_WX_EXTRACT', '/app/output/wx_extract')
    _in_conpyro_csv_path  =  os.path.join(_in_dir, 'conpyro_df_wx.csv')
    _tree_csv_path = os.path.join('OUTPUT_FuelAnalyst', '/app/output/fuel_analyst', 'master_tree_df.csv')
    _fofem_consume_csv_path = os.path.join('OUTPUT_FuelAnalyst', '/app/output/fuel_analyst', 'fofem_consume_df.csv')
## Non-Docker Environment
else:
    # Local Windows development (follow the instructions)
    # Define input and output folders
    test_dir = os.path.join(os.path.dirname(__file__), 'tests')
    _out_dir = os.path.join(test_dir, 'results', 'conpyro')
    # The ConPyro input dataframe must have weather data attached for ConPyro/FOFEM modelling
    # Required weather columns for ConPyro modelling: 'ws', 'wd', 'ffmc', 'dmc', 'bui', 'temp', 'rh'
    # Required weather columns for FOFEM mortality modelling: 'ws', 'temp'
    _in_dir = os.path.join(test_dir, 'results', 'wx_extract')
    _in_conpyro_csv_path = os.path.join(_in_dir, 'conpyro_df_wx.csv')
    _tree_csv_path = os.path.join(test_dir, 'results', 'fuel_analyst', 'master_tree_df.csv')
    _fofem_consume_csv_path = os.path.join(test_dir, 'results', 'fuel_analyst', 'fofem_consume_df.csv')


_fire_modelling_dict = None

# Run ConPyro modelling
run_conpyro(
    out_dir=_out_dir,
    in_conpyro_csv_path=_in_conpyro_csv_path,
    in_tree_csv_path=_tree_csv_path,
    in_fofem_consume_csv_path=_fofem_consume_csv_path,
    fire_modelling_params=_fire_modelling_dict,
)