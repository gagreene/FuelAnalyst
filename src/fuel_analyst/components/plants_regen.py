# -*- coding: utf-8 -*-
"""
Created on Tue May 27, 9:35:00 2025

@author: Gregory A. Greene
"""
__author__ = ['Gregory A. Greene, map.n.trowel@gmail.com']

import os
import pandas as pd
import numpy as np

try:
    # Relative import for module usage
    from . import helper
except ImportError:
    # Absolute import for script usage
    import helper


def _calc_plants_fccs_fofem_attributes(df: pd.DataFrame) -> tuple[pd.DataFrame, list]:
    """
    Aggregates shrub species composition for each plot where the dominant substrate is shrubland.
    For each row, identifies up to five shrub species, sums percent cover for duplicate species codes,
    and formats the result for FCCS and FOFEM input. Adds columns for FCCS species, FCCS shrub species,
    and FOFEM shrub species groupings.

    :param df: DataFrame containing plant species, percent cover, and dominant substrate data.
    :return: Tuple of updated DataFrame and a list of columns to keep.
    """

    def _fccs_fofem_species(row, shrub_only=False, fofem_shrub_group=False):
        # Collect species codes and percent cover for up to five species
        species = []
        total_pct = 0
        sagebrush_pct = 0
        for i in range(1, 6):
            label = row.get(f'pc_species_{i}_label', '')
            pl_code = row.get(f'pc_species_{i}_plCode', '')
            pct = row.get(f'pc_species_{i}_pct', 0)
            # Only include shrubs if shrub_only is True
            if pd.notnull(label) and (not shrub_only or 'Shrub' in label):
                if pd.notnull(pl_code) and pd.notnull(pct):
                    species.append((pl_code, float(pct)))
                    total_pct += float(pct)
                    # Track sagebrush percent cover for FOFEM grouping
                    if shrub_only and fofem_shrub_group and pl_code in ['ARFR', 'ARTR']:
                        sagebrush_pct += float(pct)
        # Aggregate percent cover by species code, convert to relative percent
        agg = {}
        for pl_code, pct in species:
            rel_pct = pct / total_pct * 100 if total_pct > 0 else 0
            agg[pl_code] = agg.get(pl_code, 0) + rel_pct
        # For FOFEM, group as Sagebrush or ShrubGroup
        if shrub_only and fofem_shrub_group:
            return 'Sagebrush' if sagebrush_pct > 50 else 'ShrubGroup'
        # Format output string for FCCS/FOFEM
        return ' | '.join(f'{k}:{v:.1f}' for k, v in agg.items())

    # FCCS species composition for all surface plant species
    df['fccs_spl_species'] = df.apply(lambda row: _fccs_fofem_species(row), axis=1)
    # FCCS shrub species composition for shrub-dominated plots
    df['fccs_shrub_species'] = df.apply(
        lambda row: _fccs_fofem_species(row, shrub_only=True)
        if row['dom_substrate'] in ['SL', 'ST'] else '', axis=1
    )
    # FOFEM shrub species grouping for shrub-dominated plots
    df['fofem_shrub_group'] = df.apply(
        lambda row: _fccs_fofem_species(row, shrub_only=True, fofem_shrub_group=True)
        if row['dom_substrate'] in ['SL', 'ST'] else '', axis=1
    )

    return df, ['fofem_shrub_group']


def _get_dom_substrate(df: pd.DataFrame) -> tuple[pd.DataFrame, list]:
    """
    Determines the dominant substrate type for each row in the DataFrame based on percent cover
    and other plant attribute columns. Adds 'dom_sub' and 'dom_substrate' columns to the DataFrame.

    :param df: DataFrame containing plant cover and height data.
    :return: pd.DataFrame: Updated DataFrame with dominant substrate column.
    """
    # List of substrate percent cover columns to consider
    substrate_list = ['bryoid_pct_total', 'grass_pct_total', 'herb_forb_pct_total', 'shrubs_pct_total']
    # Mapping from substrate column to code
    substrate_dict = {
        'bryoid_pct_total': 'BY',
        'grass_pct_total': 'HG',
        'herb_forb_pct_total': 'HF',
        'shrubs_pct_total': 'shrubs'
    }
    # Assign initial dominant substrate code based on max percent cover
    df['dom_sub'] = df[substrate_list].apply(lambda y: substrate_dict.get(y.idxmax()), axis=1)

    # Precompute boolean masks and values for substrate logic
    shrubs_dom = df['shrubs_pct_total'].gt(50)
    tall_shrubs = df['shrubs_ht_avg'] >= 2
    bryo_dom = df['bryoid_pct_total'].gt(50)
    herbs_dom = df['herb_forb_pct_total'].gt(50)
    grass_dom = df['grass_pct_total'].gt(50)
    herbs_grass_sum = df['herb_forb_pct_total'] + df['grass_pct_total']
    herbs_grass_dom = herbs_grass_sum > 50
    herbs_ratio = df['herb_forb_pct_total'] / herbs_grass_sum.replace(0, np.nan)
    grass_ratio = df['grass_pct_total'] / herbs_grass_sum.replace(0, np.nan)
    dom_shrubs = df['dom_sub'] == 'shrubs'

    # Assign final dominant substrate class based on rules and conditions
    df['dom_substrate'] = np.select(
        [
            shrubs_dom,  # Shrubs dominant
            bryo_dom,    # Bryoid dominant
            herbs_dom,   # Herbs/forbs dominant
            grass_dom,   # Grasses dominate
            herbs_grass_dom & (herbs_ratio > 0.5),  # Herbs/forbs > 50% and dominate over grass
            herbs_grass_dom & (grass_ratio > 0.5),  # Grasses > 50% and dominate over herbs
            herbs_grass_dom,  # Herbs + grass > 50% but neither dominates
            dom_shrubs       # Initial dominant substrate is shrubs
        ],
        [
            np.where(tall_shrubs, 'ST', 'SL'),  # Tall or low shrubland
            'BY',  # Bryoids (no distinction between mosses and lichens)
            'HF',  # Herb - Forbs
            'HG',  # Herb - Graminoids
            'HF',  # Herb - Forbs
            'HG',  # Herb - Graminoids
            'HE',  # Herbaceous (no distinction between forbs and graminoids)
            np.where(tall_shrubs, 'ST', 'SL')  # Tall or low shrubland based on regeneration height
        ],
        default=df['dom_sub']
    )
    return df, ['dom_substrate']


def _get_photoload_biomass(photoload_code: str, pct_cover: float, height: float):
    photoload_dict = {
        'AMAL': (height / 35.56) * 0.0148 * np.exp(0.0454 * pct_cover),
        'MARE': (height / 10.16) * 0.0013 * pct_cover,  # USED TO BE BERE
        'SYAL': (height / 35.56) * 0.0107 * np.exp(0.0442 * pct_cover),
        'VAGL': (height / 35.56) * 0.0052 * pct_cover,
        'VASC': (height / 17.78) * 0.0135 * np.exp(0.035 * pct_cover),
        'ARLA': (height / 30.48) * 0.001 * pct_cover,
        'CARU': (height / 20.30) * 0.0194 * np.exp(0.0282 * pct_cover),
        'FESC': (height / 30.5) * 0.0188 * np.exp(0.0298 * pct_cover),
        'XETE': (height / 25.4) * 0.0154 * np.exp(0.0444 * pct_cover),
        'MOSS': 0,
        'TREE': 0
    }

    return photoload_dict.get(photoload_code, np.nan)


def _process_regen(df: pd.DataFrame, regen_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, list]:
    """
    Calculates stand-level (per hectare) regeneration metrics for small and tall, live and dead trees,
    and adds these as new columns to the main DataFrame.

    Small regen <= 30cm Height; Tall regen: 30cm < Height < 1.3 m

    :param df: DataFrame containing plot-level plant data.
    :param regen_df: DataFrame containing regeneration counts by plot.
    :return: Updated DataFrame with regeneration density columns (per hectare).
    """
    print('\tProcessing data for tree regeneration')
    # Multiplier to convert plot counts to per hectare values (for 5.64m radius plot)
    plot_multiplier = 100

    regen_df['rgn_live_small_cnt'] /= regen_df['rgn_small_plot_proportion']
    regen_df['rgn_live_tall_cnt'] /= regen_df['rgn_tall_plot_proportion']

    # Aggregate regeneration counts by plot (ParentGlobalID), summing each count type
    regen_sums = regen_df.groupby('ParentGlobalID').agg({
        'rgn_live_small_cnt': 'sum',
        'rgn_live_tall_cnt': 'sum',
    }).mul(plot_multiplier)  # Convert to per hectare

    # Initialize columns to keep in the master DataFrame
    keep_columns = []

    # Map aggregated regeneration counts to main DataFrame and normalize by number of plots
    for col in ['rgn_live_small_cnt', 'rgn_live_tall_cnt']:
        new_col = col.replace('rgn_', 'dens_regen_').replace('_cnt', '_ha')
        df[new_col] = df.GlobalID.map(regen_sums[col])
        df[new_col] = df[new_col].fillna(0)  # Fill missing values with 0
        # Add the new columns to the keep_columns list
        keep_columns.append(new_col)

    return df, regen_df, keep_columns


def _process_top_five_spp(df: pd.DataFrame) -> tuple[pd.DataFrame, list]:
    """
    Processes the top five plant species per plot, calculating biomass, percent cover, and height-weighted metrics
    for different plant functional groups (moss/bryophyte, grass, herb/forb, shrub). Adds columns for each group
    and for each species, including Photoload codes, biomass, and labels. Returns the updated DataFrame.

    :param df: DataFrame containing plant species, percent cover, and height data.
    :return: Updated DataFrame with calculated plant group attributes and species-level metrics,
        and a list of columns to keep.
    """
    print(f'\tProcessing data for plants')
    # Assign plant PhotoLoad CSV to dataframe
    plant_photoload_df = helper.get_df(
        os.path.join(os.path.dirname(__file__), '../supporting_data', 'plant_photoload.csv')
    )
    plant_photoload_df.set_index('Code', inplace=True)

    # Initialize columns for plant species data
    df['pc_species_kgpm2'] = 0.0
    df['bryoid_kgpm2'] = 0.0
    df['bryoid_pct_total'] = 0.0
    df['bryoid_ht_wtd'] = 0.0
    df['grass_kgpm2'] = 0.0
    df['grass_pct_total'] = 0.0
    df['grass_ht_wtd'] = 0.0
    df['herb_forb_kgpm2'] = 0.0
    df['herb_forb_pct_total'] = 0.0
    df['herb_forb_ht_wtd'] = 0.0
    df['herbs_kgpm2'] = 0.0
    df['herbs_pct_total'] = 0.0
    df['herbs_ht_wtd'] = 0.0
    df['shrubs_kgpm2'] = 0.0
    df['shrubs_ht_wtd'] = 0.0
    df['shrubs_pct_total'] = 0.0

    # Get the plant Photoload codes and labels
    pl_code_map = plant_photoload_df['PL_Code'].to_dict()
    label_map = plant_photoload_df['Label'].to_dict()

    # Cycle through the top 5 plant species
    for x in range(1, 6):
        print(f'\t\tProcessing species {x}')
        # Assign alternate code if species classified as OTHER
        df[f'pc_species_{x}'] = np.where(
            df[f'pc_species_{x}'] == 'OTHER',
            df[f'pc_species_{x}_other'],
            df[f'pc_species_{x}']
        )

        # Change plants with 0 percent or 0 cm height values to 1 percent
        mask = (df[f'pc_species_{x}'].notnull()) & (
            (df[f'pc_species_{x}_pct'] == 0) | (df[f'pc_species_{x}_ht'] == 0)
        )
        df.loc[mask, f'pc_species_{x}_pct'] = 1

        # Get the Photoload species code for each species
        df[f'pc_species_{x}_plCode'] = df[f'pc_species_{x}'].map(pl_code_map)
        df[f'pc_species_{x}_kgpm2'] = df.apply(
            lambda y: _get_photoload_biomass(
                y[f'pc_species_{x}_plCode'],
                y[f'pc_species_{x}_pct'],
                y[f'pc_species_{x}_ht']
            ) if pd.notnull(y[f'pc_species_{x}_plCode']) else 0,
            axis=1
        )

        # Add species biomass to total surface plant biomass
        df['pc_species_kgpm2'] += df[f'pc_species_{x}_kgpm2']

        # Get species labels
        df[f'pc_species_{x}_label'] = df[f'pc_species_{x}'].map(label_map)

        # PROCESS ALL PLANTS FOR FUEL BED DEPTH (i.e., Height only)
        # Get plant height weighted by percent cover for all species (for calculating dominant substrate)
        df['fuel_bed_ht_wtd'] = df[f'pc_species_{x}_pct'] * df[f'pc_species_{x}_ht']
        df['fuel_bed_pct_total'] = df[f'pc_species_{x}_pct']

        # PROCESS MOSS/BRYOPHYTE
        # Generate a mask for species that are mosses or bryophytes
        moss_bryo_mask = df[f'pc_species_{x}_label'].str.contains('Moss', na=False)
        # Get total biomass of moss/bryophyte species
        df['bryoid_kgpm2'] += np.where(moss_bryo_mask, 0, 0)  # Mosses currently have no Photoload biomass equations
        # Get total percent cover of moss/bryophyte species
        df['bryoid_pct_total'] += np.where(moss_bryo_mask, df[f'pc_species_{x}_pct'], 0)
        # Get moss/bryophyte height weighted by percent cover
        df['bryoid_ht_wtd'] += np.where(moss_bryo_mask, df[f'pc_species_{x}_pct'] * df[f'pc_species_{x}_ht'], 0)

        # PROCESS GRASS
        # Generate a mask for species that are grasses/graminoids
        grass_mask = df[f'pc_species_{x}_label'].str.contains('Grass', na=False)
        # Get total biomass of grass species
        df['grass_kgpm2'] += np.where(grass_mask, df[f'pc_species_{x}_kgpm2'], 0)
        # Get grass percent cover
        df['grass_pct_total'] += np.where(grass_mask, df[f'pc_species_{x}_pct'], 0)
        # Get grass height weighted by percent cover
        df['grass_ht_wtd'] += np.where(grass_mask, df[f'pc_species_{x}_pct'] * df[f'pc_species_{x}_ht'], 0)

        # PROCESS HERBS & FORBS
        # Generate a mask for species that are herbs or forbs
        herb_forb_mask = df[f'pc_species_{x}_label'].str.contains('Herb', na=False)
        # Get total biomass of herb & forb species
        df['herb_forb_kgpm2'] += np.where(herb_forb_mask, df[f'pc_species_{x}_kgpm2'], 0)
        # Get herb & forb percent cover
        df['herb_forb_pct_total'] += np.where(herb_forb_mask, df[f'pc_species_{x}_pct'], 0)
        # Get herb & forb height weighted by percent cover
        df['herb_forb_ht_wtd'] += np.where(herb_forb_mask, df[f'pc_species_{x}_pct'] * df[f'pc_species_{x}_ht'], 0)

        # PROCESS ALL HERBACEOUS PLANTS
        # Generate a mask for species that are herbs or grasses
        herb_mask = df[f'pc_species_{x}_label'].str.contains('Herb|Grass', na=False)
        # Get total biomass of herb species (+ grass)
        df['herbs_kgpm2'] += np.where(herb_mask, df[f'pc_species_{x}_kgpm2'], 0)
        # Get herb percent cover
        df['herbs_pct_total'] += np.where(herb_mask, df[f'pc_species_{x}_pct'], 0)
        # Get herb height weighted by percent cover
        df['herbs_ht_wtd'] += np.where(herb_mask, df[f'pc_species_{x}_pct'] * df[f'pc_species_{x}_ht'], 0)

        # PROCESS SHRUBS
        # Generate a mask for species that are shrubs
        shrub_mask = df[f'pc_species_{x}_label'].str.contains('Shrub', na=False)
        # Get total biomass of shrub species
        df['shrubs_kgpm2'] += np.where(shrub_mask, df[f'pc_species_{x}_kgpm2'], 0)
        # Get shrub percent cover
        df['shrubs_pct_total'] += np.where(shrub_mask, df[f'pc_species_{x}_pct'], 0)
        # Get shrub height weighted by percent cover
        df['shrubs_ht_wtd'] += np.where(shrub_mask, df[f'pc_species_{x}_pct'] * df[f'pc_species_{x}_ht'], 0)

    # Get average height of all fuels, grass, herbs/forbs, all herbaceous plants (grass + herbs/forbs), and shrubs (m)
    df['fuel_bed_depth_m'] = df['fuel_bed_ht_wtd'] / df['fuel_bed_pct_total'] / 100
    df['bryoid_ht_avg'] = (df['bryoid_ht_wtd'] / df['bryoid_pct_total']) / 100
    df['grass_ht_avg'] = (df['grass_ht_wtd'] / df['grass_pct_total']) / 100
    df['herb_forb_ht_avg'] = (df['herb_forb_ht_wtd'] / df['herb_forb_pct_total']) / 100
    df['herbs_ht_avg'] = (df['herbs_ht_wtd'] / df['herbs_pct_total']) / 100
    df['shrubs_ht_avg'] = (df['shrubs_ht_wtd'] / df['shrubs_pct_total']) / 100

    keep_columns = [
        'fuel_bed_depth_m', 'bryoid_kgpm2', 'grass_kgpm2', 'herb_forb_kgpm2', 'shrubs_kgpm2',
    ]

    return df, keep_columns


def process_plants_regen(in_folder: str, out_folder: str) -> tuple[pd.DataFrame, list]:
    """
    Get the plant and tree regeneration data from a CSV file and return as an updated DataFrame.

    :param in_folder: Path to the folder containing the input CSV files.
    :param out_folder: Path to the folder where output CSV files will be saved.
    :return: DataFrame with processed tree attributes, and a list of columns to keep.
    """
    print('\nProcessing Plant and Regeneration data')

    keep_columns = []

    # ### PROCESS PLOT DATA
    # Get plot dataframe
    df = helper.get_df(os.path.join(in_folder, 'survey_0.csv'))
    # Generate a unique ID for each plot
    df = helper.get_unique_id(df)

    # ### PROCESS PLANT DATA
    # Calculate plant attributes
    df, add_columns = _process_top_five_spp(df)
    keep_columns.extend(add_columns)
    df, add_columns = _get_dom_substrate(df)
    keep_columns.extend(add_columns)
    df, add_columns = _calc_plants_fccs_fofem_attributes(df)
    keep_columns.extend(add_columns)

    # ### PROCESS REGENERATION DATA
    # Get regen dataframe
    regen_df = helper.get_df(os.path.join(in_folder, 'regeneration_1.csv'))

    # ### MERGE PLANT AND REGENERATION DATA
    # Calculate regeneration attributes
    df, regen_df, add_columns = _process_regen(df, regen_df)
    keep_columns.extend(add_columns)

    # ### SAVE DATASETS TO OUTPUT FOLDER
    os.makedirs(out_folder, exist_ok=True)
    helper.export_csv(df, os.path.join(out_folder, 'survey_0.csv'))
    helper.export_csv(regen_df, os.path.join(out_folder, 'regeneration_1.csv'))

    return df, keep_columns
