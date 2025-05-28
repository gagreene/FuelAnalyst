# -*- coding: utf-8 -*-
"""
Created on Tue May 27, 9:35:00 2025

@author: Gregory A. Greene
"""
__author__ = ['Gregory A. Greene, map.n.trowel@gmail.com']

import os
import pandas as pd
import numpy as np
from datetime import datetime as dt


def _get_df(csv_path: str) -> pd.DataFrame:
    return pd.read_csv(csv_path, header=0, index_col=False)


def _export_csv(df: pd.DataFrame, csv_path: str) -> None:
    if os.path.exists(csv_path):
        os.remove(csv_path)
    df.to_csv(csv_path, sep=',', index=False)
    return


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


def _process_top_five_spp(df: pd.DataFrame) -> pd.DataFrame:
    """
    Processes the top five plant species per plot, calculating biomass, percent cover, and height-weighted metrics
    for different plant functional groups (moss/bryophyte, grass, herb/forb, shrub). Adds columns for each group
    and for each species, including Photoload codes, biomass, and labels. Returns the updated DataFrame.

    :param df: DataFrame containing plant species, percent cover, and height data.
    :return: Updated DataFrame with calculated plant group attributes and species-level metrics.
    """
    # Assign plant PhotoLoad CSV to dataframe
    plant_photoload_df = _get_df(r'.\Supporting_Data\plant_photoload.csv')
    plant_photoload_df.set_index('Code', inplace=True)

    # Initialize columns for plant species data
    df['pc_species_kgpm2'] = 0.0
    df['moss_kgpm2'] = 0.0
    df['grass_kgpm2'] = 0.0
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
        print(f'\tProcessing data for plant species {x}')

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

        # PROCESS MOSS/BRYOPHYTE
        # Generate a mask for species that are mosses or bryophytes
        moss_bryo_mask = df[f'pc_species_{x}_label'].str.contains('Moss', na=False)
        # Get total biomass of moss/bryophyte species
        df['bryoid_kgpm2'] += np.where(moss_bryo_mask, 0, 0)  # Mosses currently have no Photoload biomass equations
        # Get total percent cover of moss/bryophyte species
        df['bryoid_pct_total'] += np.where(moss_bryo_mask, df[f'pc_species_{x}_kgpm2'], 0)

        # PROCESS GRASS
        # Generate a mask for species that are grasses/graminoids
        grass_mask = df[f'pc_species_{x}_label'].str.contains('Grass', na=False)
        # Get total biomass of grass species
        df['grass_kgpm2'] += np.where(grass_mask, df[f'pc_species_{x}_kgpm2'], 0)
        # Get grass percent cover
        df['grass_pct_total'] += np.where(grass_mask, df[f'pc_species_{x}_pct'], 0)

        # PROCESS HERBS & FORBS
        # Generate a mask for species that are herbs or forbs
        herb_forb_mask = df[f'pc_species_{x}_label'].str.contains('Herb', na=False)
        # Get total biomass of herb & fern species
        df['herb_fern_kgpm2'] += np.where(herb_forb_mask, df[f'pc_species_{x}_kgpm2'], 0)
        # Get herb & fern percent cover
        df['herb_fern_pct_total'] += np.where(herb_forb_mask, df[f'pc_species_{x}_pct'], 0)
        # Get herb & fern height weighted by percent cover
        df['herb_fern_ht_wtd'] += np.where(herb_forb_mask, df[f'pc_species_{x}_pct'] * df[f'pc_species_{x}_ht'], 0)

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

    # Get average height of shrubs (m)
    df['shrubs_ht_avg'] = (df['shrubs_ht_wtd'] / df['shrubs_pct_total']) / 100

    return df


def _get_dom_substrate(df: pd.DataFrame) -> pd.DataFrame:
    """
    Determines the dominant substrate type for each row in the DataFrame based on percent cover
    and other plant attribute columns. Adds 'domSub' and 'domSubstrate' columns to the DataFrame.

    :param df: DataFrame containing plant cover and height data.
    :return: pd.DataFrame: Updated DataFrame with dominant substrate column.
    """
    # List of substrate percent cover columns to consider
    substrate_list = ['bryoid_pct_total', 'grass_pct_total', 'herb_fern_pct_total', 'shrubs_pct_total']
    # Mapping from substrate column to code
    substrate_dict = {
        'bryoid_pct_total': 'BY',
        'grass_pct_total': 'HG',
        'herb_fern_pct_total': 'HF',
        'shrubs_pct_total': 'shrubs'
    }
    # Assign initial dominant substrate code based on max percent cover
    df['domSub'] = df[substrate_list].apply(lambda y: substrate_dict.get(y.idxmax()), axis=1)

    # Precompute boolean masks and values for substrate logic
    shrubs_dom = df.shrubs_pct_total.gt(50)
    tall_shrubs = df.shrubs_ht_avg >= 2
    bryo_dom = df.moss_pct_total.gt(50)
    herbs_dom = df.herb_fern_pct_total.gt(50)
    grass_dom = df.grass_pct_total.gt(50)
    herbs_grass_sum = df.herb_fern_pct_total + df.grass_pct_total
    herbs_grass_dom = herbs_grass_sum > 50
    herbs_ratio = df.herb_fern_pct_total / herbs_grass_sum.replace(0, np.nan)
    grass_ratio = df.grass_pct_total / herbs_grass_sum.replace(0, np.nan)
    dom_shrubs = df.domSub == 'shrubs'

    # Assign final dominant substrate class based on rules and conditions
    df['domSubstrate'] = np.select(
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
        default=df.domSub
    )
    return df


def _process_regen(df: pd.DataFrame, regen_df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculates stand-level (per hectare) regeneration metrics for small and tall, live and dead trees,
    and adds these as new columns to the main DataFrame.

    Small regen <= 30cm Height; Tall regen: 30cm < Height < 1.3 m

    :param df: DataFrame containing plot-level plant data.
    :param regen_df: DataFrame containing regeneration counts by plot.
    :return: Updated DataFrame with regeneration density columns (per hectare).
    """
    # Multiplier to convert plot counts to per hectare values (for 5.64m radius plot)
    plot_multiplier = 100

    # Aggregate regeneration counts by plot (ParentGlobalID), summing each count type
    regen_sums = regen_df.groupby('ParentGlobalID').agg({
        'rgn_live_small_cnt': 'sum',
        'rgn_dead_small_cnt': 'sum',
        'rgn_live_tall_cnt': 'sum',
        'rgn_dead_tall_cnt': 'sum'
    }).mul(plot_multiplier)  # Convert to per hectare

    # Map aggregated regeneration counts to main DataFrame and normalize by number of plots
    for col in ['rgn_live_small_cnt', 'rgn_dead_small_cnt', 'rgn_live_tall_cnt', 'rgn_dead_tall_cnt']:
        new_col = col.replace('rgn_', 'dens_regen_').replace('_cnt', '_ha')
        df[new_col] = df.GlobalID.map(regen_sums[col]) / df.num_plots
        df[new_col].fillna(0, inplace=True)  # Fill missing values with 0

    return df


def process_plants_regen(csv_folder: str) -> pd.DataFrame:
    """
    Get the plant and tree regeneration data from a CSV file and return as an updated DataFrame.

    :param csv_folder: Path to the folder containing the plant and regen CSV files.
    """
    print('Processing Plant and Regeneration data')

    # ### PROCESS PLANT DATA
    # Get plant dataframe
    df = _get_df(os.path.join(csv_folder, 'survey_0.csv'))
    # Generate a unique ID for each plot
    df['year'] = df['_date'].apply(lambda y: dt.strptime(y, '%m/%d/%Y %I:%M:%S %p').year)
    df['uniqueID'] = df[['treatment_area', 'treatment_unit', 'treatment_unit_other', 'plot_id',
                             'treatment_type', 'year']].apply(lambda x: ''.join(x.astype(str)), axis=1)
    # Calculate plant attributes
    df = _process_top_five_spp(df)
    df = _get_dom_substrate(df)

    # ### PROCESS REGENERATION DATA
    # Get regen dataframe
    regen_df = _get_df(os.path.join(csv_folder, 'regeneration_1.csv'))

    # ### MERGE PLANT AND REGENERATION DATA
    # Calculate regeneration attributes
    df = _process_regen(df, regen_df)

    return df
