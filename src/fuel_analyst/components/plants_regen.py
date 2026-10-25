# -*- coding: utf-8 -*-
"""
Created on Tue May 27, 9:35:00 2025

@author: Gregory A. Greene
"""
__author__ = ['Gregory A. Greene']

import logging
import os
import pandas as pd
import numpy as np

from . import helper, table_reader

logger = logging.getLogger(__name__)

#: Value the Survey123 form records when a plot has no surface plant species.
_NO_SPECIES_CODE = 'NO_SPP'
_OTHER_SPECIES_CODE = 'OTHER'
_NOT_SPECIES = (_NO_SPECIES_CODE, _OTHER_SPECIES_CODE)    # table rows that are Survey123 form values, not species
#: PhotoLoad series that _get_photoload_biomass() can evaluate (MOSS and TREE give zero biomass).
_PHOTOLOAD_CODES = ('AMAL', 'ARLA', 'CARU', 'FESC', 'MARE', 'MOSS', 'SYAL', 'TREE', 'VAGL', 'VASC', 'XETE')


def _calc_pc_flammable(df: pd.DataFrame) -> tuple[pd.DataFrame, list]:
    """
    Calculates percent nonflammable and flammable ground cover for each plot.

    Replicates the calculation performed by the Survey123 form itself (CWC Fuels 2 - Plants
    and Regen.xlsx): pc_nonflammable = pc_rock + pc_mineral_soil, and
    pc_flammable = 100 - pc_nonflammable. Missing pc_rock or pc_mineral_soil values are treated
    as 0% cover of that substrate type. Falls back to a fully flammable default
    (pc_flammable = 100, pc_nonflammable = 0) when pc_rock and pc_mineral_soil are both missing,
    or when the calculated pc_nonflammable falls outside the valid 0-100 range.

    :param df: DataFrame containing 'pc_rock' and 'pc_mineral_soil' percent cover columns.
    :return: Updated DataFrame with 'pc_nonflammable' and 'pc_flammable' columns, and a list
        of columns to keep.
    """
    print('\tCalculating percent flammable substrate cover')

    pc_rock = pd.to_numeric(df['pc_rock'], errors='coerce') if 'pc_rock' in df.columns \
        else pd.Series(np.nan, index=df.index)
    pc_mineral_soil = pd.to_numeric(df['pc_mineral_soil'], errors='coerce') if 'pc_mineral_soil' in df.columns \
        else pd.Series(np.nan, index=df.index)
    no_data_provided = pc_rock.isnull() & pc_mineral_soil.isnull()

    # Missing rock or mineral soil cover is treated as 0% cover of that substrate type
    df['pc_nonflammable'] = pc_rock.fillna(0) + pc_mineral_soil.fillna(0)
    df['pc_flammable'] = 100 - df['pc_nonflammable']

    # Fall back to fully flammable when no nonflammable cover was provided, or the
    # calculated percentage falls outside the valid 0-100 range
    out_of_range = (df['pc_nonflammable'] < 0) | (df['pc_nonflammable'] > 100)
    fallback_mask = no_data_provided | out_of_range

    for idx in df.index[no_data_provided]:
        logger.info(
            'No pc_rock or pc_mineral_soil cover provided; pc_flammable defaulted to 100.',
            extra={
                'unique_id': df.loc[idx, 'unique_id'] if 'unique_id' in df.columns else idx,
                'issue_code': 'pc_flammable_no_data',
            },
        )
    for idx in df.index[out_of_range & ~no_data_provided]:
        logger.info(
            'Calculated pc_nonflammable outside the valid 0-100 range; pc_flammable defaulted to 100.',
            extra={
                'unique_id': df.loc[idx, 'unique_id'] if 'unique_id' in df.columns else idx,
                'issue_code': 'pc_flammable_out_of_range',
            },
        )

    df.loc[fallback_mask, 'pc_nonflammable'] = 0.0
    df.loc[fallback_mask, 'pc_flammable'] = 100.0

    return df, ['pc_nonflammable', 'pc_flammable']


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
        """
        Summarize row-level plant composition for FCCS or FOFEM output.

        :param row: Plant-composition record containing species codes and cover values.
        :param shrub_only: Whether to exclude non-shrub species.
        :param fofem_shrub_group: Whether to aggregate FOFEM shrub functional groups.
        :return: Formatted relative species composition or FOFEM shrub group.
        """
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
            bryo_dom,  # Bryoid dominant
            herbs_dom,  # Herbs/forbs dominant
            grass_dom,  # Grasses dominate
            herbs_grass_dom & (herbs_ratio > 0.5),  # Herbs/forbs > 50% and dominate over grass
            herbs_grass_dom & (grass_ratio > 0.5),  # Grasses > 50% and dominate over herbs
            herbs_grass_dom,  # Herbs + grass > 50% but neither dominates
            dom_shrubs  # Initial dominant substrate is shrubs
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
    """
    Estimate plant biomass from the final objective-cover PhotoLoad models.

    The fitted cover-to-biomass equations are constrained through the origin.
    Biomass is then scaled by the observed plant height relative to the
    reference height used for the corresponding PhotoLoad series.

    :param photoload_code: PhotoLoad species or functional-group code.
    :param pct_cover: Observed plant cover as a percentage.
    :param height: Observed plant height in centimetres.
    :return: Estimated biomass in kilograms per square metre, or NaN for an unknown code.
    """
    photoload_dict = {
        'AMAL': (height / 35.56) * 0.0690181 * (np.exp(0.0240242 * pct_cover) - 1),
        'MARE': (height / 10.16) * 0.000733871 * np.power(pct_cover, 1.16779),
        'SYAL': (height / 35.56) * (
                0.00119555 * pct_cover + 0.0000169686 * np.power(pct_cover, 2)
        ),
        'VAGL': (height / 35.56) * 0.398329 * (np.exp(0.0109776 * pct_cover) - 1),
        'VASC': (height / 17.78) * 0.0025455 * pct_cover,
        'ARLA': (height / 30.48) * 0.0005745 * np.power(pct_cover, 1.16228),
        'CARU': (height / 20.30) * 0.0117766 * (np.exp(0.0379728 * pct_cover) - 1),
        'FESC': (height / 30.5) * 0.0161917 * (np.exp(0.0330081 * pct_cover) - 1),
        'XETE': (height / 25.4) * 0.00366616 * pct_cover,
        'MOSS': 0,
        'TREE': 0
    }

    return photoload_dict.get(photoload_code, np.nan)


def _group_mean_biomass(table_df: pd.DataFrame, group: str, pct_cover, height):
    """
    Average biomass of the species of one functional group of plant_photoload.csv at a given cover and height.

    Each species of the group is evaluated with its own PhotoLoad series equation (so a series that many species use
    counts once per species), and the biomass values are averaged. A group of mosses and lichens has no biomass
    equations and averages to zero.

    :param table_df: Species table with func_group and pl_code columns.
    :param group: Functional group name, as in the func_group column (for example 'Herb/Forb').
    :param pct_cover: Observed cover as a percentage, scalar or array.
    :param height: Observed height in centimetres, scalar or array.
    :return: Average biomass in kilograms per square metre, as an array aligned with the inputs.
    """
    series = table_df.loc[(table_df['func_group'] == group) & table_df['pl_code'].notna(), 'pl_code'].value_counts()
    total = np.zeros(np.shape(pct_cover), dtype=float)
    for code, count in series.items():
        total = total + count * np.asarray(_get_photoload_biomass(code, pct_cover, height), dtype=float)
    return total / series.sum()


def _log_other_species_estimated(
        df: pd.DataFrame,
        species_number: int,
        estimated: pd.Series,
        name: pd.Series,
        group: pd.Series,
        group_sizes: dict
) -> None:
    """
    Log a warning for each plot whose OTHER species was estimated from the average of its functional group.

    A species recorded as OTHER that is not in plant_photoload.csv has no series equation, so its biomass is the
    average of the species of the functional group the crew chose, at its cover and height. The warning tells the user
    how the value was obtained and that adding the species to the table replaces the estimate. The warnings are
    collected by error_handling for the error report.

    :param df: DataFrame with the species cover and height columns.
    :param species_number: Position of the species within the plot (1 to 5).
    :param estimated: Boolean Series that is True for the rows estimated from a group average.
    :param name: Series of the alternate species names entered with OTHER (blank when none was entered).
    :param group: Series of the functional groups chosen with OTHER.
    :param group_sizes: Number of species of each functional group in plant_photoload.csv.
    :return: None. Writes warnings to the module logger, keyed by unique_id when that column exists.
    """
    for idx in df.index[estimated]:
        entered = name[idx] if isinstance(name[idx], str) and name[idx].strip() else None
        who = f"'{entered}'" if entered else 'with no name'
        logger.warning(
            f"Plant species {species_number} is recorded as OTHER {who}, which is not in plant_photoload.csv, so its "
            f"biomass is the average of the {group_sizes[group[idx]]} {group[idx]} species of the table at its cover "
            "and height. Add the species to plant_photoload.csv to replace this estimate.",
            extra={
                'unique_id': df.loc[idx, 'unique_id'] if 'unique_id' in df.columns else idx,
                'issue_code': 'plant_species_other_estimated',
            },
        )


def _log_other_species_without_name(df: pd.DataFrame, species_number: int, skip: pd.Series | None = None) -> None:
    """
    Log a warning for each plot whose species is recorded as OTHER with no alternate code.

    A species recorded as OTHER is identified by the code entered in pc_species_N_other. When that entry is empty and no
    functional group was chosen either, the species cannot be identified or estimated, so it adds no biomass to any
    functional group. This must run before OTHER is replaced by the alternate code, which would erase the record. The
    warnings are collected by error_handling for the error report.

    :param df: DataFrame with the species code (pc_species_N) and its alternate code (pc_species_N_other).
    :param species_number: Position of the species within the plot (1 to 5).
    :param skip: Optional boolean Series that is True for rows to leave out (rows estimated from a functional group).
    :return: None. Writes warnings to the module logger, keyed by unique_id when that column exists.
    """
    other_col = f'pc_species_{species_number}_other'
    if other_col not in df.columns:
        return
    alternate = df[other_col]
    no_alternate = alternate.isna() | (alternate.astype(str).str.strip() == '')
    unnamed = (df[f'pc_species_{species_number}'] == 'OTHER') & no_alternate
    if skip is not None:
        unnamed = unnamed & ~skip

    for idx in df.index[unnamed]:
        logger.warning(
            f"Plant species {species_number} is recorded as OTHER with no alternate code in {other_col}, so it adds "
            "no biomass to any functional group.",
            extra={
                'unique_id': df.loc[idx, 'unique_id'] if 'unique_id' in df.columns else idx,
                'issue_code': 'plant_species_other_no_name',
            },
        )


def _log_species_table_issues(df: pd.DataFrame, species_number: int, skip: pd.Series | None = None) -> None:
    """
    Log a warning for each plot whose recorded species cannot be converted to biomass.

    A species is reported when its code is not in plant_photoload.csv (it then adds no biomass to any functional
    group) or when its table entry names a PhotoLoad series that has no biomass equation. The Survey123 value
    'NO_SPP' and empty entries are not reported. The warnings are collected by error_handling for the error report.

    :param df: DataFrame with the species code (pc_species_N) and its PhotoLoad series (pc_species_N_plCode).
    :param species_number: Position of the species within the plot (1 to 5).
    :param skip: Optional boolean Series that is True for rows to leave out (OTHER species estimated from a group).
    :return: None. Writes warnings to the module logger, keyed by unique_id when that column exists.
    """
    code_col = f'pc_species_{species_number}'
    series_col = f'pc_species_{species_number}_plCode'
    code = df[code_col]
    recorded = code.notna() & (code.astype(str).str.strip() != '') & (code != _NO_SPECIES_CODE)
    if skip is not None:
        recorded = recorded & ~skip
    unlisted = recorded & df[series_col].isna()
    no_equation = recorded & df[series_col].notna() & ~df[series_col].isin(_PHOTOLOAD_CODES)

    for idx in df.index[unlisted]:
        logger.warning(
            f"Plant species '{code[idx]}' (species {species_number}) is not in plant_photoload.csv (codes are "
            "case-sensitive), so it adds no biomass to any functional group.",
            extra={
                'unique_id': df.loc[idx, 'unique_id'] if 'unique_id' in df.columns else idx,
                'issue_code': 'plant_species_not_in_table',
            },
        )
    for idx in df.index[no_equation]:
        logger.warning(
            f"Plant species '{code[idx]}' (species {species_number}) lists PhotoLoad series "
            f"'{df.loc[idx, series_col]}' in plant_photoload.csv, which has no biomass equation.",
            extra={
                'unique_id': df.loc[idx, 'unique_id'] if 'unique_id' in df.columns else idx,
                'issue_code': 'plant_species_no_equation',
            },
        )


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
    Calculate species biomass and cover-weighted plant heights per plot.

    Add species PhotoLoad codes, biomass, and labels, together with biomass,
    cover, and height summaries for moss/bryophyte, grass, herb/forb, and shrub groups. A species recorded as
    'NO_SPP' (no further species) contributes zero biomass and no cover or height. A species recorded as 'OTHER'
    that is not in the table is estimated from the functional group chosen with it (pc_species_N_other_group): its
    biomass is the average, over the species of that group in the table, of each species' equation at the recorded
    cover and height, and the species counts in that group.
    Fuel-bed depth weights valid recorded species by cover after normalization; missing
    or nonfinite heights/covers and negative heights are excluded from both sums.
    A measured zero height contributes zero; no usable species yields missing depth.

    :param df: DataFrame containing plant species, percent cover, and height data.
    :return: Updated DataFrame with calculated plant group attributes and species-level metrics,
        and a list of columns to keep.
    """
    print(f'\tProcessing data for plants')
    # Assign plant PhotoLoad CSV to dataframe
    plant_photoload_df = helper.get_df(
        os.path.join(os.path.dirname(__file__), '../supporting_data', 'plant_photoload.csv')
    )
    plant_photoload_df.set_index('name', inplace=True)

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
    pl_code_map = plant_photoload_df['pl_code'].to_dict()
    label_map = plant_photoload_df['label'].to_dict()
    species_names = set(plant_photoload_df.index) - set(_NOT_SPECIES)
    group_sizes = (plant_photoload_df['func_group'].value_counts().to_dict()
                   if 'func_group' in plant_photoload_df.columns else {})

    fuel_bed_ht_wtd = pd.Series(0.0, index=df.index)
    fuel_bed_pct_total = pd.Series(0.0, index=df.index)

    # Cycle through the top 5 plant species
    for x in range(1, 6):
        print(f'\t\tProcessing species {x}')
        # A species recorded as OTHER is identified by the alternate name entered with it. If that name is not in the
        # table (or no name was entered) and a functional group was chosen, its biomass is estimated from that group
        other = df[f'pc_species_{x}'] == _OTHER_SPECIES_CODE
        alt_name = df[f'pc_species_{x}_other'] if f'pc_species_{x}_other' in df.columns else pd.Series(np.nan, index=df.index)
        alt_group = (df[f'pc_species_{x}_other_group'].astype('string').str.strip()
                     if f'pc_species_{x}_other_group' in df.columns else pd.Series(pd.NA, index=df.index, dtype='string'))
        estimated = (other & ~alt_name.isin(species_names)
                     & alt_group.isin([g for g in group_sizes if pd.notna(g)])).fillna(False).astype(bool)
        no_name = alt_name.isna() | (alt_name.astype(str).str.strip() == '')

        # Assign alternate code if species classified as OTHER (an OTHER that cannot be identified or estimated with no
        # alternate code is logged first). An estimated species with no name keeps OTHER as its code.
        _log_other_species_without_name(df, x, skip=estimated)
        df[f'pc_species_{x}'] = np.where(
            other,
            np.where(estimated & no_name, _OTHER_SPECIES_CODE, alt_name),
            df[f'pc_species_{x}']
        )

        # NO_SPP means there is no further species: it adds no biomass, and any cover or height entered with it is
        # ignored, so it cannot count toward the fuel bed depth or any group total
        no_species = df[f'pc_species_{x}'] == _NO_SPECIES_CODE
        df.loc[no_species, [f'pc_species_{x}_pct', f'pc_species_{x}_ht']] = np.nan

        # Change plants with 0 percent or 0 cm height values to 1 percent
        mask = (df[f'pc_species_{x}'].notnull()) & (
                (df[f'pc_species_{x}_pct'] == 0) | (df[f'pc_species_{x}_ht'] == 0)
        )
        df.loc[mask, f'pc_species_{x}_pct'] = 1

        # Get the Photoload species code for each species
        df[f'pc_species_{x}_plCode'] = df[f'pc_species_{x}'].map(pl_code_map)
        _log_species_table_issues(df, x, skip=estimated)
        df[f'pc_species_{x}_kgpm2'] = df.apply(
            lambda y: _get_photoload_biomass(
                y[f'pc_species_{x}_plCode'],
                y[f'pc_species_{x}_pct'],
                y[f'pc_species_{x}_ht']
            ) if pd.notnull(y[f'pc_species_{x}_plCode']) else 0,
            axis=1
        )

        # Estimate an OTHER species that is not in the table from the average of its functional group
        _log_other_species_estimated(df, x, estimated, alt_name, alt_group, group_sizes)
        if estimated.any():
            df[f'pc_species_{x}_kgpm2'] = df[f'pc_species_{x}_kgpm2'].astype(float)
        for group in alt_group[estimated].unique():
            rows = estimated & (alt_group == group)
            df.loc[rows, f'pc_species_{x}_kgpm2'] = _group_mean_biomass(
                plant_photoload_df, group, df.loc[rows, f'pc_species_{x}_pct'].to_numpy(dtype=float),
                df.loc[rows, f'pc_species_{x}_ht'].to_numpy(dtype=float)
            )

        # Add species biomass to total surface plant biomass
        df['pc_species_kgpm2'] += df[f'pc_species_{x}_kgpm2']

        # Get species labels
        df[f'pc_species_{x}_label'] = df[f'pc_species_{x}'].map(label_map)
        # The chosen functional group puts an estimated OTHER species into its group totals, which read the label
        df.loc[estimated, f'pc_species_{x}_label'] = (
            '[' + alt_group[estimated] + '] OTHER - ' + alt_name[estimated].where(~no_name[estimated], 'no name').astype(str)
        )

        # PROCESS ALL PLANTS FOR FUEL BED DEPTH (i.e., Height only)
        # Accumulate valid cover-weighted heights for fuel-bed depth.
        species_cover = df[f'pc_species_{x}_pct']
        species_height = df[f'pc_species_{x}_ht']
        valid_depth = (
            df[f'pc_species_{x}'].notna() &
            np.isfinite(species_cover) & (species_cover > 0) &
            np.isfinite(species_height) & (species_height >= 0)
        )
        fuel_bed_ht_wtd += (species_cover * species_height).where(valid_depth, 0)
        fuel_bed_pct_total += species_cover.where(valid_depth, 0)
        df['fuel_bed_ht_wtd'] = fuel_bed_ht_wtd
        df['fuel_bed_pct_total'] = fuel_bed_pct_total

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
    df['fuel_bed_depth_m'] = df['fuel_bed_ht_wtd'] / df['fuel_bed_pct_total'].replace(0, np.nan) / 100
    df['bryoid_ht_avg'] = (df['bryoid_ht_wtd'] / df['bryoid_pct_total']) / 100
    df['grass_ht_avg'] = (df['grass_ht_wtd'] / df['grass_pct_total']) / 100
    df['herb_forb_ht_avg'] = (df['herb_forb_ht_wtd'] / df['herb_forb_pct_total']) / 100
    df['herbs_ht_avg'] = (df['herbs_ht_wtd'] / df['herbs_pct_total']) / 100
    df['shrubs_ht_avg'] = (df['shrubs_ht_wtd'] / df['shrubs_pct_total']) / 100

    keep_columns = [
        'fuel_bed_depth_m', 'bryoid_kgpm2', 'grass_kgpm2', 'herb_forb_kgpm2', 'shrubs_kgpm2',
    ]

    return df, keep_columns


def process_plants_regen(in_folder: 'str | table_reader.FormSource', out_folder: str) -> tuple[pd.DataFrame, list]:
    """
    Get the plant and tree regeneration data from a CSV file and return as an updated DataFrame.

    :param in_folder: Path to the form folder of input tables, or a resolved FormSource.
    :param out_folder: Path to the folder where output CSV files will be saved.
    :return: DataFrame with processed tree attributes, and a list of columns to keep.
    """
    print('\nProcessing Plant and Regeneration data')
    in_folder = table_reader.ensure_form_source(in_folder)

    keep_columns = []

    # ### PROCESS PLOT DATA
    # Get plot dataframe
    df = table_reader.read_table(in_folder, 'survey_0')
    # Generate a unique ID for each plot
    df = helper.get_unique_id(df)
    # Calculate percent flammable/nonflammable substrate cover
    df, add_columns = _calc_pc_flammable(df)
    keep_columns.extend(add_columns)

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
    regen_df = table_reader.read_table(in_folder, 'regeneration_1')

    # ### MERGE PLANT AND REGENERATION DATA
    # Calculate regeneration attributes
    df, regen_df, add_columns = _process_regen(df, regen_df)
    keep_columns.extend(add_columns)

    # ### SAVE DATASETS TO OUTPUT FOLDER
    os.makedirs(out_folder, exist_ok=True)
    helper.export_csv(df, os.path.join(out_folder, 'survey_0.csv'))
    helper.export_csv(regen_df, os.path.join(out_folder, 'regeneration_1.csv'))

    return df, keep_columns
