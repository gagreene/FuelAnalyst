import os 
from pyogrio import list_layers



# Define the environment as "dockerized" or not 
is_docker = os.path.exists('/.dockerenv')
if is_docker:
# Docker environment file paths 
    _BEC_shp_loc = os.getenv('BEC_DATA_DIR', '/app/BEC_data')  # Path to BEC shapefile directory (mounted in Docker)

    _BEC_shp_dir = os.path.join(_BEC_shp_loc, 'VEG_COMP_LYR_R1_POLY_2025.gdb')  # Full path to the BEC shapefile
    ## confirm existence of the BEC shapefile and print available layers
    if not os.path.exists(_BEC_shp_dir):
        raise FileNotFoundError(f'BEC shapefile not found at {_BEC_shp_dir}')
    layers = list_layers(_BEC_shp_dir) 
    print("Layers in the BEC shapefile geodatabase:")
    for layer in layers:
        print(layer)

# run 
