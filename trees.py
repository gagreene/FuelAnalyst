# -*- coding: utf-8 -*-
"""
Created on Tue May 27, 15:30:00 2025

@author: Gregory A. Greene
"""
__author__ = ['Gregory A. Greene, map.n.trowel@gmail.com']

import os
import pandas as pd
import numpy as np
from datetime import datetime as dt
import helper


# GENERAL LIST OF CONIFER SPECIES IN BC
conifer_list = [
    'B', 'BA', 'BB', 'BG', 'BL', 'BN',
    'C', 'CE', 'CH', 'CW',
    'F', 'FD', 'FDC', 'FDI',
    'H', 'HM', 'HW', 'HX', 'HXM',
    'J', 'JR',
    'L', 'LA', 'LS', 'LT', 'LW',
    'P', 'PA', 'PF', 'PJ', 'PL', 'PLC', 'PLI', 'PP', 'PR', 'PW', 'PX', 'PXJ', 'PY',
    'S', 'SA', 'SB', 'SE', 'SR', 'SS', 'SW', 'SX', 'SXB', 'SXE', 'SXL', 'SXS', 'SXW', 'SXX',
    'T', 'TW',
    'Y', 'YC',
    'UNK', 'XC', 'ZC'
]


# VARIABLES FOR BIOMASS MODELING
tree_component_list = ['wood', 'bark', 'branches', 'foliage']
tree_component_index_dict = {
    'wood': 0,
    'bark': 1,
    'branches': 2,
    'foliage': 3
}

tree_conifer_decay_class_dict = {
    1: [1, 1, 1, 1],
    2: [1, 1, 1, 1],
    3: [1, 1, 1, 0],
    4: [0.95, 0.75, 0.5, 0],
    5: [0.80, 0.5, 0, 0],
    6: [0.66, 0.25, 0, 0],
    7: [0.5, 0.1, 0, 0],
    8: [0.33, 0.05, 0, 0],
    9: [0.05, 0, 0, 0]
}

tree_broadleaf_decay_class_dict = {
    1: [1, 1, 1, 1],
    2: [1, 1, 1, 1],
    3: [1, 1, 1, 0],
    4: [0.95, 0.75, 0.5, 0],
    5: [0.66, 0.25, 0, 0],
    6: [0.05, 0, 0, 0]
}


def _get_temesgen_tree_height(model: int,
                              param_df: pd.DataFrame,
                              spp: str,
                              dbh: float,
                              bal: float = None,
                              sph=None,
                              ba=None):
    """
    Calculates tree height using the Temesgen height model (Model 2 or 7).

    :param model: Integer, 2 or 7, specifying which Temesgen model to use.
    :param param_df: DataFrame containing species-specific model parameters.
    :param spp: Species code (string) for the target ttree.
    :param dbh: Diameter at Breast Height of the target tree (cm).
    :param bal: Total basal area of trees larger than the target tree in stand (m^2/ha), required for Model 7.
    :param sph: Total number of trees per hectare in stand, required for Model 7.
    :param ba: Total basal area per hectare in stand (m^2/ha), required for Model 7.
    :return: Estimated tree height (m) or np.nan if 'model' is invalid.
    """
    if model == 2:
        # Temesgen Model 2: Height = 1.3 + a * (1 - exp(-b * dbh^c))
        return 1.3 + param_df.loc[spp, 'Temesgen_M2a'] * \
               (1 - np.exp(-param_df.loc[spp, 'Temesgen_M2b'] * np.power(dbh, param_df.loc[spp, 'Temesgen_M2c'])))
    elif model == 7:
        # Temesgen Model 7: Height = 1.3 + a * (1 - exp(-b * dbh^c))
        # a and c are functions of bal, sph, and ba
        a = param_df.loc[spp, 'Temesgen_M7a1'] + \
            param_df.loc[spp, 'Temesgen_M7a2'] * bal + \
            param_df.loc[spp, 'Temesgen_M7a3'] * sph + \
            param_df.loc[spp, 'Temesgen_M7a4'] * ba
        c = param_df.loc[spp, 'Temesgen_M7a5'] + \
            param_df.loc[spp, 'Temesgen_M7a6'] * bal
        return 1.3 + a * (1 - np.exp(-param_df.loc[spp, 'Temesgen_M7b'] * np.power(dbh, c)))
    else:
        # If incorrect model number entered, return np.nan
        return np.nan


def _calc_plot_multipliers(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate multipliers for tree data based on plot radii.

    :param df: DataFrame containing plot attributes.
    :return: DataFrame with multipliers added.
    """
    # Calculate plot-level multipliers for tree data
    def get_multiplier(radius, small, large):
        return np.where(radius == small, 100 if small == 5.64 else 25,
                        np.where(pd.isnull(radius), np.nan, large))

    df['plot_lgtree_mult'] = get_multiplier(df.lgtree_plot_radius, 11.28, 50)
    df['plot_smtree_mult'] = get_multiplier(df.smtree_plot_radius, 5.64, 200)
    df['plot_sapling_mult'] = get_multiplier(df.sapling_plot_radius, 5.64, 200)

    return df


def _calc_tree_dbh_classes(tree_df: pd.DataFrame) -> pd.DataFrame:
    """
    Assigns DBH (Diameter at Breast Height) class labels to each tree based on its DBH value.

    Classes:
        - '1D': DBH >= 30 cm
        - '1M': 12.5 cm <= DBH < 30 cm
        - '2' : 7.5 cm <= DBH < 12.5 cm
        - '3' : DBH < 7.5 cm

    :param tree_df: DataFrame containing individual tree data with a 'tree_dbh' column.
    :return: DataFrame with a new 'tree_dbh_class' column.
    """
    # Assign DBH class based on DBH value
    tree_df['tree_dbh_class'] = np.select([
        (tree_df.tree_dbh >= 30),
        ((tree_df.tree_dbh >= 12.5) & (tree_df.tree_dbh < 30)),
        ((tree_df.tree_dbh >= 7.5) & (tree_df.tree_dbh < 12.5)),
        (tree_df.tree_dbh < 7.5),
    ], ['1D', '1M', '2', '3'])

    return tree_df


def _calc_tree_decay_classes(tree_df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate the combined decay class for each tree based on conifer and broadleaf decay classes.

    The function sums the values of 'tree_dcy_class_cnfr' and 'tree_dcy_class_brdlf' for each row.
    If the sum is 0, it is replaced with NaN, indicating no decay class is assigned.

    :param tree_df: DataFrame containing individual tree data with conifer and broadleaf decay class columns.
    :return: DataFrame with a new 'tree_dcy_class' column representing the combined decay class.
    """
    # Calculate decay class for conifer and broadleaf trees by summing their respective columns
    # Replace 0 with NaN to indicate missing or unassigned decay class
    tree_df['tree_dcy_class'] = tree_df[
        ['tree_dcy_class_cnfr', 'tree_dcy_class_brdlf']
    ].sum(axis=1).replace(0, np.nan)

    return tree_df


def _calc_tree_type(tree_df: pd.DataFrame, tree_params_df: pd.DataFrame) -> pd.DataFrame:
    """
    Assigns tree type (e.g., conifer or broadleaf) to each tree in the DataFrame
    based on species codes and a parameter DataFrame.

    :param tree_df: DataFrame containing individual tree data, including species codes.
    :param tree_params_df: DataFrame containing species parameters, including 'TreeType'.
    :return: Updated tree_df with a new 'tree_type' column.
    """
    # Create a mapping from species code to tree type
    tree_type_map = tree_params_df['TreeType'].to_dict()
    # Map tree species to their type and assign to new column
    tree_df['tree_type'] = tree_df['tree_species'].map(tree_type_map)

    return tree_df


def _calc_tree_density(df: pd.DataFrame, tree_df: pd.DataFrame) -> pd.DataFrame:
    """
    Assigns tree density multipliers to each tree based on its DBH class.

    For each tree:
    - If DBH >= 12.5 cm, use the large tree multiplier.
    - If 5 cm <= DBH < 12.5 cm, use the small tree multiplier.
    - If DBH < 5 cm, use the sapling multiplier.

    :param df: DataFrame containing plot-level multipliers.
    :param tree_df: DataFrame containing individual tree data, including DBH.
    :return: Updated tree_df with a new 'tree_dens' column for tree density multiplier.
    """
    # Assign density multiplier based on DBH class
    tree_df['tree_dens_ha'] = np.where(
        tree_df.tree_dbh >= 12.5,
        tree_df.ParentGlobalID.map(df.set_index('GlobalID')['plot_lgtree_mult'].to_dict()),
        np.where(
            (tree_df.tree_dbh >= 5) & (tree_df.tree_dbh < 12.5),
            tree_df.ParentGlobalID.map(df.set_index('GlobalID')['plot_smtree_mult'].to_dict()),
            tree_df.ParentGlobalID.map(df.set_index('GlobalID')['plot_sapling_mult'].to_dict()),
        )
    )

    return tree_df


def _calc_tree_basal_area(tree_df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate the basal area and weighted basal area for each tree.

    :param tree_df: DataFrame containing individual tree data, including DBH and density.
    :return: DataFrame with 'tree_ba' (basal area in m^2) and 'tree_ba_wtd' (density-weighted basal area) columns added.
    """
    # Calculate basal area (m^2) for each tree: BA = π * (DBH/200)^2
    tree_df['tree_ba'] = np.pi * np.power(tree_df.tree_dbh / 200, 2)
    # Calculate weighted basal area: tree density * basal area
    tree_df['tree_ba_wtd'] = tree_df['tree_dens_ha'] * tree_df['tree_ba']

    return tree_df


def _calc_tree_missing_heights(tree_df: pd.DataFrame, tree_params_df: pd.DataFrame) -> pd.DataFrame:
    """
    Model and assign tree heights for trees in the DataFrame using the Temesgen height model.
    Heights are estimated for live trees missing height values and for all dead trees.

    :param tree_df: DataFrame containing individual tree data.
    :param tree_params_df: DataFrame containing tree species parameters for height modeling.
    :return: Updated DataFrame with modeled tree heights.
    """
    # Function to model height using Temesgen Model 2 for a given row
    def model_height(row):
        if row['tree_species'] in spp_set:
            return _get_temesgen_tree_height(2, tree_params_df, row['tree_species'], row['tree_dbh'])
        return np.nan

    # Set of valid species codes present in the data
    spp_set = set(tree_df['tree_species'].dropna())

    # Mask for trees missing heights (decay class conifer < 6 or broadleaf < 5, and valid DBH)
    mask_missing = (
        (tree_df['tree_dens_ha'] > 0) &
        (
            (tree_df['tree_dcy_class_cnfr'] < 6) |
            (tree_df['tree_dcy_class_brdlf'] < 5)
        ) &
        tree_df['tree_ht'].isnull() &
        tree_df['tree_dbh'].notnull()
    )
    # Assign modeled heights to live trees missing height values
    tree_df.loc[mask_missing, 'tree_ht'] = tree_df[mask_missing].apply(model_height, axis=1)

    # Mask for dead trees (decay class conifer >= 6 or broadleaf >= 5, and valid DBH)
    mask_dead = (
        (
            (tree_df['tree_dcy_class_cnfr'] >= 6) |
            (tree_df['tree_dcy_class_brdlf'] >= 5)
        ) &
        tree_df['tree_dbh'].notnull()
    )
    # Initialize modeled height column for dead trees
    tree_df['tree_ht_modeled'] = 0
    # Assign modeled heights to dead trees
    tree_df.loc[mask_dead, 'tree_ht_modeled'] = tree_df[mask_dead].apply(model_height, axis=1)

    return tree_df


def _calc_tree_fsg(tree_df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculates the fuel strata gap (FSG) for each tree in the DataFrame.

    The FSG is the vertical distance between the top of the surface fuel bed and the base of the tree crown.
    The calculation depends on tree status (live or dead), crown base height (CBH), dead crown base height (DCBH),
    and the height of the fuel bed. The result is stored in the 'tree_fsg' column.

    Rules:
        - If the tree is dead or has no fuel bed height, FSG is NaN.
        - For live trees:
            - If CBH < DCBH and (CBH - fuel bed height) > 0, FSG = CBH - fuel bed height.
            - If DCBH < CBH and (DCBH - fuel bed height) > 0, FSG = DCBH - fuel bed height.
            - If the fuel bed is above either CBH or DCBH, FSG = 0.

    :param tree_df: DataFrame containing tree attributes, including status, CBH, DCBH, and fuel bed height.
    :return: Updated DataFrame with a new 'tree_fsg' column.
    """
    # Mask for dead trees or missing fuel bed height
    is_dead_or_no_fuel_bed = (tree_df['tree_status'] == 'D') | (tree_df['tree_fuel_bed_ht'].isnull())

    # Mask for live trees where CBH < DCBH and CBH is above the fuel bed
    cbh_gt_dcbh = (
        (tree_df['tree_status'] == 'L') &
        (tree_df['tree_cbh'] < tree_df['tree_dcbh']) &
        ((tree_df['tree_cbh'] - tree_df['tree_fuel_bed_ht']) > 0)
    )

    # Mask for live trees where DCBH < CBH and DCBH is above the fuel bed
    dcbh_gt_cbh = (
        (tree_df['tree_status'] == 'L') &
        (tree_df['tree_dcbh'] < tree_df['tree_cbh']) &
        ((tree_df['tree_dcbh'] - tree_df['tree_fuel_bed_ht']) > 0)
    )

    # Mask for live trees where the fuel bed is above either CBH or DCBH
    fuel_bed_above_crown = (
        (tree_df['tree_status'] == 'L') &
        (
            (tree_df['tree_fuel_bed_ht'] > tree_df['tree_cbh']) |
            (tree_df['tree_fuel_bed_ht'] > tree_df['tree_dcbh'])
        )
    )

    # Assign FSG values based on the above conditions
    tree_df['tree_fsg'] = np.select(
        condlist=[is_dead_or_no_fuel_bed, cbh_gt_dcbh, dcbh_gt_cbh, fuel_bed_above_crown],
        choicelist=[
            np.nan,
            tree_df['tree_cbh'] - tree_df['tree_fuel_bed_ht'],
            tree_df['tree_dcbh'] - tree_df['tree_fuel_bed_ht'],
            0
        ]
    )
    return tree_df


def _calc_tree_crwn_dpth(tree_df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculates the crown depth for each tree and adds it as a new column 'tree_crwn_dpth'.

    Crown depth is defined as the difference between tree height and crown base height (CBH)
    for live trees where height exceeds CBH. For all other cases, the value is set to NaN.

    :param tree_df: DataFrame containing individual tree data, including 'tree_status', 'tree_ht', and 'tree_cbh'.
    :return: DataFrame with a new 'tree_crwn_dpth' column.
    """
    # Calculate crown depth for live trees where height > CBH; otherwise, set as NaN
    tree_df['tree_crwn_dpth'] = np.where(
        (tree_df['tree_status'] == 'L') & (tree_df['tree_ht'] > tree_df['tree_cbh']),
        tree_df['tree_ht'] - tree_df['tree_cbh'],
        np.nan
    )
    return tree_df


def _calc_tree_crown_fuels(tree_df: pd.DataFrame, tree_params_df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculates canopy fuel load and bulk density for live conifer trees using allometric equations.

    For each conifer species present, computes:

    Crown fuel load (CFL) using Canadian National Biomass Equations (CNBE)
        - Equations per Ung et al. (2008) and Lambert et al. (2005), using DBH and height.

    Canopy bulk density (CBD), calculated as CFL divided by crown depth.

    Initializes output columns to zero and only processes live trees with valid DBH, height, and density.
    Results are stored in new columns for each tree.

    :param tree_df: DataFrame with individual tree data, including DBH, height, and status.
    :param tree_params_df: DataFrame with species-specific allometric parameters.
    :return: Updated tree_df with canopy fuel and bulk density columns.
    """
    # Calculate crown depth for live trees
    tree_df['tree_crwn_dpth'] = np.where(
        (tree_df.tree_status == 'L') & (tree_df.tree_ht > tree_df.tree_cbh),
        tree_df.tree_ht - tree_df.tree_cbh,
        np.nan
    )
    # Initialize columns
    for col in ['tree_cfl_cnbe', 'tree_cbd_cnbe']:
        tree_df[col] = 0

    # Only process conifer species present in the DataFrame
    spp_set = set(tree_df['tree_species'].dropna())
    for spp in spp_set:
        # Generate a mask for the current species
        spp_mask = (tree_df['tree_species'] == spp) & \
                   (tree_df['tree_status'] == 'L') & \
                   (tree_df['tree_dbh'] > 0) & \
                   (tree_df['tree_ht'] > 0)

        # Calculate CFL (CNBE Model)
        tree_df.loc[spp_mask, 'tree_cfl_cnbe'] = (
            tree_params_df.loc[spp, 'BIOMASS_CNBE_DBH-HT_Bfoliage1'] *
            tree_df.loc[spp_mask, 'tree_dbh'] ** tree_params_df.loc[spp, 'BIOMASS_CNBE_DBH-HT_Bfoliage2'] *
            tree_df.loc[spp_mask, 'tree_ht'] ** tree_params_df.loc[spp, 'BIOMASS_CNBE_DBH-HT_Bfoliage3']
        )
        tree_df.loc[spp_mask, 'tree_cfl_cnbe_ha'] = (
            tree_df.loc[spp_mask, 'tree_dens_ha'] * tree_df.loc[spp_mask, 'tree_cfl_cnbe']
        )
        # Calculate CBD (CNBE Model)
        cbd_mask = spp_mask & (tree_df['tree_crwn_dpth'] > 0)
        tree_df.loc[cbd_mask, 'tree_cbd_cnbe'] = (
            tree_df.loc[cbd_mask, 'tree_cfl_cnbe'] / tree_df.loc[cbd_mask, 'tree_crwn_dpth']
        )
        tree_df.loc[cbd_mask, 'tree_cbd_cnbe_ha'] = (
            tree_df.loc[spp_mask, 'tree_dens_ha'] * tree_df.loc[spp_mask, 'tree_cbd_cnbe']
        )

    return tree_df


def _calc_tree_biomass(tree_df: pd.DataFrame, tree_params_df: pd.DataFrame) -> pd.DataFrame:
    # Initialize columns
    for col in ['tree_wood_cnbe', 'tree_bark_cnbe', 'tree_branches_cnbe', 'tree_foliage_cnbe']:
        tree_df[col] = 0

    sppList = [n for n in tree_df['tree_species'].unique() if not pd.isnull(n)]

    # Assign combined decay class once
    tree_df['tree_dcy_class'] = np.where(
        tree_df.tree_type == 'conifer',
        tree_df.tree_dcy_class_cnfr,
        np.where(tree_df.tree_type == 'broadleaf', tree_df.tree_dcy_class_brdlf, np.nan)
    )

    for spp in sppList:
        decayDict = tree_conifer_decay_class_dict if spp in conifer_list else tree_broadleaf_decay_class_dict
        for component in tree_component_list:
            comp_idx = tree_component_index_dict[component]
            param1 = tree_params_df.loc[spp, f'BIOMASS_CNBE_DBH-HT_B{component}1']
            param2 = tree_params_df.loc[spp, f'BIOMASS_CNBE_DBH-HT_B{component}2']
            param3 = tree_params_df.loc[spp, f'BIOMASS_CNBE_DBH-HT_B{component}3']

            # Mask for live/less decayed trees
            mask_live = (
                (tree_df.tree_species == spp) &
                (tree_df.tree_dcy_class > 0) &
                ((tree_df.tree_dcy_class_cnfr < 6) | (tree_df.tree_dcy_class_brdlf < 5)) &
                (tree_df.tree_dbh > 0) &
                (tree_df.tree_ht > 0)
            )
            # Mask for dead/more decayed trees
            mask_dead = (
                (tree_df.tree_species == spp) &
                (tree_df.tree_dcy_class > 0) &
                ((tree_df.tree_dcy_class_cnfr >= 6) | (tree_df.tree_dcy_class_brdlf >= 5)) &
                (tree_df.tree_dbh > 0) &
                (tree_df.tree_ht > 0)
            )

            # Calculate biomass per ha for live/less decayed
            tree_df.loc[mask_live, f'tree_{component}_cnbe'] = (
                tree_df.loc[mask_live, 'tree_dens_ha'] *
                decayDict.get(tree_df.loc[mask_live, 'tree_dcy_class']).apply(lambda x: x[comp_idx]) *
                param1 *
                tree_df.loc[mask_live, 'tree_dbh'] ** param2 *
                tree_df.loc[mask_live, 'tree_ht'] ** param3
            )

            # Calculate biomass per ha for dead/more decayed
            tree_df.loc[mask_dead, f'tree_{component}_cnbe'] = (
                tree_df.loc[mask_dead, 'tree_dens_ha'] *
                decayDict.get(tree_df.loc[mask_dead, 'tree_dcy_class']).apply(lambda x: x[comp_idx]) *
                param1 *
                tree_df.loc[mask_dead, 'tree_dbh'] ** param2 *
                tree_df.loc[mask_dead, 'tree_ht_modeled'] ** param3
            )

    return tree_df


def _calc_stand_density(df: pd.DataFrame, tree_df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculates stand-level tree density metrics for all trees, live/dead, and by tree type (conifer/broadleaf).
    Adds columns to the plot-level DataFrame for each density metric.

    :param df: DataFrame containing plot-level data (must include 'GlobalID' and 'trees_present').
    :param tree_df: DataFrame containing individual tree data
        (must include 'ParentGlobalID', 'tree_dens_ha', 'tree_status', 'tree_type').
    :return: Updated plot-level DataFrame with stand density columns.
    """
    # Create boolean masks for tree status and type
    mask_live = tree_df.tree_status == 'L'
    mask_dead = tree_df.tree_status == 'D'
    mask_cnfr = tree_df.tree_type == 'conifer'
    mask_brdlf = tree_df.tree_type == 'broadleaf'
    mask_cnfr_live = mask_cnfr & mask_live
    mask_cnfr_dead = mask_cnfr & mask_dead
    mask_brdlf_live = mask_brdlf & mask_live
    mask_brdlf_dead = mask_brdlf & mask_dead

    # Calculate total stand density (all trees)
    df['stand_dens'] = df.GlobalID.map(tree_df.groupby('ParentGlobalID')['tree_dens_ha'].sum())
    # Set stand density to 0 if no trees are present
    df['stand_dens'] = np.where(df.trees_present == 'N', 0, df.stand_dens)
    df['stand_dens'].fillna(0, inplace=True)
    # Calculate stand density for live and dead trees
    df['stand_dens_live'] = df.GlobalID.map(tree_df[mask_live].groupby('ParentGlobalID')['tree_dens_ha'].sum())
    df['stand_dens_dead'] = df.GlobalID.map(tree_df[mask_dead].groupby('ParentGlobalID')['tree_dens_ha'].sum())
    # Calculate stand density for live/dead conifers and broadleaf trees
    df['stand_dens_cnfr_live'] = df.GlobalID.map(tree_df[mask_cnfr_live].groupby('ParentGlobalID')['tree_dens_ha'].sum())
    df['stand_dens_cnfr_dead'] = df.GlobalID.map(tree_df[mask_cnfr_dead].groupby('ParentGlobalID')['tree_dens_ha'].sum())
    df['stand_dens_brdlf_live'] = df.GlobalID.map(tree_df[mask_brdlf_live].groupby('ParentGlobalID')['tree_dens_ha'].sum())
    df['stand_dens_brdlf_dead'] = df.GlobalID.map(tree_df[mask_brdlf_dead].groupby('ParentGlobalID')['tree_dens_ha'].sum())

    return df


def _calc_stand_basal_area(df: pd.DataFrame, tree_df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculates stand-level basal area metrics for all trees, live/dead, and by tree type (conifer/broadleaf).
    Adds columns to the plot-level DataFrame for each basal area metric.

    :param df: DataFrame containing plot-level data (must include 'GlobalID').
    :param tree_df: DataFrame containing individual tree data
        (must include 'ParentGlobalID', 'tree_ba_wtd', 'tree_status', 'tree_type').
    :return: Updated plot-level DataFrame with stand basal area columns.
    """
    # Masks for tree types and status
    mask_live = tree_df.tree_status == 'L'
    mask_dead = tree_df.tree_status == 'D'
    mask_cnfr = tree_df.tree_type == 'conifer'
    mask_brdlf = tree_df.tree_type == 'broadleaf'
    mask_cnfr_live = mask_cnfr & mask_live
    mask_cnfr_dead = mask_cnfr & mask_dead
    mask_brdlf_live = mask_brdlf & mask_live
    mask_brdlf_dead = mask_brdlf & mask_dead

    # Calculate total stand basal area (all trees)
    df['stand_ba'] = df.GlobalID.map(tree_df.groupby('ParentGlobalID')['tree_ba_wtd'].sum())
    # Calculate basal area for live and dead trees
    df['stand_ba_live'] = df.GlobalID.map(tree_df[mask_live].groupby('ParentGlobalID')['tree_ba_wtd'].sum())
    df['stand_ba_dead'] = df.GlobalID.map(tree_df[mask_dead].groupby('ParentGlobalID')['tree_ba_wtd'].sum())
    # Calculate basal area for live/dead conifers and broadleaf trees
    df['stand_ba_cnfr_live'] = df.GlobalID.map(tree_df[mask_cnfr_live].groupby('ParentGlobalID')['tree_ba_wtd'].sum())
    df['stand_ba_cnfr_dead'] = df.GlobalID.map(tree_df[mask_cnfr_dead].groupby('ParentGlobalID')['tree_ba_wtd'].sum())
    df['stand_ba_brdlf_live'] = df.GlobalID.map(tree_df[mask_brdlf_live].groupby('ParentGlobalID')['tree_ba_wtd'].sum())
    df['stand_ba_brdlf_dead'] = df.GlobalID.map(tree_df[mask_brdlf_dead].groupby('ParentGlobalID')['tree_ba_wtd'].sum())

    return df


def process_trees(in_folder: str, out_folder: str) -> pd.DataFrame:
    """
    Get the tree data from CSV files and return as an updated DataFrame.

    :param in_folder: Path to the folder containing the input CSV files.
    :param out_folder: Path to the folder where output CSV files will be saved.
    :return: DataFrame with processed tree attributes.
    """
    print('Processing Tree data')

    # ### PROCESS PLOT-LEVEL ATTRIBUTES
    # Get plot dataframe
    df = helper.get_df(os.path.join(in_folder, 'survey_0.csv'))
    # Generate a unique ID for each plot
    df['year'] = df['_date'].apply(lambda y: dt.strptime(y, '%m/%d/%Y %I:%M:%S %p').year)
    df['uniqueID'] = df[['treatment_area', 'treatment_unit', 'treatment_unit_other', 'plot_id',
                             'treatment_type', 'year']].apply(lambda x: ''.join(x.astype(str)), axis=1)
    df = _calc_plot_multipliers(df)

    # ### PROCESS INDIVIDUAL TREE ATTRIBUTES
    # Get tree dataframe
    tree_df = helper.get_df(os.path.join(in_folder, 'tree_plot_1.csv'))
    # Load tree parameters and set index
    tree_params_df = helper.get_df(os.path.join(r'.\Support_Data\tree_parameters.csv')).set_index('Species')
    # Calculate tree attributes
    tree_df = _calc_tree_dbh_classes(tree_df)
    tree_df = _calc_tree_decay_classes(tree_df)
    tree_df = _calc_tree_type(tree_df, tree_params_df)
    tree_df = _calc_tree_density(df, tree_df)
    tree_df = _calc_tree_basal_area(tree_df)
    tree_df = _calc_tree_missing_heights(tree_df, tree_params_df)
    tree_df = _calc_tree_fsg(tree_df)
    tree_df = _calc_tree_crwn_dpth(tree_df)
    tree_df = _calc_tree_crown_fuels(tree_df, tree_params_df)
    tree_df = _calc_tree_biomass(tree_df, tree_params_df)

    # ### PROCESS STAND_LEVEL (PER HA) TREE ATTRIBUTES
    df = _calc_stand_density(df, tree_df)
    df = _calc_stand_basal_area(df, tree_df)

    # ### SAVE DATASETS TO OUTPUT FOLDER
    os.makedirs(out_folder, exist_ok=True)
    helper.export_csv(df, os.path.join(out_folder, 'survey_0.csv'))
    helper.export_csv(tree_df, os.path.join(out_folder, 'tree_plot_1.csv'))

    return df
