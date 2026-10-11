# -*- coding: utf-8 -*-
"""
Created on Tue May 29, 8:30:00 2025

@author: Gregory A. Greene
"""
__author__ = ['Gregory A. Greene']

import numbers
import os
import numpy as np
import pandas as pd
from dateutil import parser

from ..components import helper
from .._vendor import bcwft2018 as bcwft

# BCWFT2018's verifyInputs() only accepts str or None for these fields - unlike several other
# fields it also accepts a bare NaN float for (e.g. BCLCS_LEVEL_1..5, INVENTORY_STANDARD_CD).
# A plot recording fewer than 6 tallied species (the common case) gets a genuine NaN for the
# unused SPECIES_CD_x ranks from trees.py's _calc_stand_type(); an unvegetated/unforested plot
# can leave even SPECIES_CD_1 as NaN. Left uncoerced, that NaN reaches verifyInputs() untouched
# and raises TypeError.
_SPECIES_CD_FIELDS = [f'SPECIES_CD_{x}' for x in range(1, 7)]

# conpyro_attributes.py's _prep_fbp_df() intentionally leaves these as pd.NA placeholders for
# the user to fill in manually (e.g. from BC VRI/BEC-zone GIS layers) before calling
# process_fbp_fuel_type() - FuelAnalyst has no access to that external data itself.
#
# COAST_INTERIOR_CD and BEC_ZONE_CODE/BEC_SUBZONE are more than type-checked by BCWFT2018: its
# decision tree branches on 'if self.COAST_INTERIOR_CD == "C": ... else: # "I"' throughout, so
# any value other than the exact string 'C' silently becomes 'interior', and BEC_ZONE_CODE/
# BEC_SUBZONE feed further branch/lookup logic keyed on the vendored becZones/becSubzones
# lists. A typo or unrecognized code is never rejected by BCWFT2018 itself - it just produces a
# silently wrong fuel type. PROJ_AGE_1 has the same problem for live stands: BCWFT2018 branches
# on 'if self.PROJ_AGE_1 < 60: ... elif self.PROJ_AGE_1 <= 99: ... else: # > 99' - both
# comparisons are False for a NaN age, so a missing age for a live stand silently falls into
# the "over 99 years old" branch instead of raising anything.
_REQUIRED_STRING_FIELDS = ['COAST_INTERIOR_CD', 'BEC_ZONE_CODE', 'BEC_SUBZONE']
_REQUIRED_NUMERIC_FIELDS = ['PROJ_AGE_1']
_COAST_INTERIOR_DOMAIN = ('C', 'I')


def _calc_fbp_fuel_type(df: pd.DataFrame, season: str = 'Growing') -> pd.DataFrame:
    """
    Calculate CFFBPS fuel types with the BCWFT2018 fuel-typing algorithm.

    :param df: DataFrame containing the fields required by BCWFT2018.
    :param season: Season used for seasonal fuel-type assignments. Case-insensitive; normalized
        to the lowercase 'growing'/'dormant' BCWFT2018's own verifyInputs() requires.
    :raises ValueError: If a required live-density column is missing entirely, any plot has an
        ambiguous missing live-tree density (see _validate_live_density()), or any plot is
        missing a required user-supplied field (see _validate_user_supplied_fbp_fields()).
    :return: DataFrame containing calculated fuel types and modifiers.
    """
    # BCWFT2018's verifyInputs() only accepts the exact lowercase strings 'growing'/'dormant',
    # but this function's own default and process_fbp_fuel_type()'s docstring both use
    # 'Growing'/'Dormant' - normalize here so either casing works instead of crashing.
    season = str(season).strip().lower()

    print('Calculating CFFBPS Fuel Types using BCWFT2018 fuel typing algorithm')
    bc_fuel_type = bcwft.FuelTyping()
    field_list = bc_fuel_type.fldList
    field_dtype = bc_fuel_type.fldDTypes
    field_dict = {field_list[i]: field_dtype[i] for i in range(len(field_list))}

    # Assign data types to columns
    fbp_df = df.copy()

    fbp_df['year'] = fbp_df['_date'].apply(lambda y: parser.parse(y).year)
    fbp_df['BCWFT_rowRef'] = 0
    fbp_df['FuelType'] = ''
    fbp_df['FT_Modifier'] = 0
    fbp_df['INVENTORY_STANDARD_CD'] = 'F'
    fbp_df['NON_PRODUCTIVE_CD'] = 64
    fbp_df['BCLCS_LEVEL_1'] = 'V'

    # A plot with no live-tree records maps to NaN, not 0, in stand_dens_tpha_live_sum (trees.py's
    # groupby-based summary has no live-tree group to map back). _validate_live_density() confirms
    # that NaN really means "all dead" using the total/dead density summaries before treating it
    # the same as an exact zero, and raises for an uncorroborated NaN (ambiguous input, not a
    # confirmed no-live-tree stand) before it reaches BCWFT2018.
    no_live_trees = _validate_live_density(fbp_df)

    fbp_df['BCLCS_LEVEL_2'] = np.where(
        no_live_trees,
        'N',
        np.where(fbp_df.cc < 10, 'N', 'T')
    )
    fbp_df['BCLCS_LEVEL_3'] = 'U'
    fbp_df['LAND_COVER_CLASS_CD_1'] = np.where(
        fbp_df.BCLCS_LEVEL_2 == 'T',
        np.where(fbp_df.stand_pct_cnfr_live > 75,
                 'TC',
                 np.where(fbp_df.stand_pct_brdlf_live > 75, 'TB', 'TM')),
        fbp_df.dom_substrate
    )
    fbp_df['BCLCS_LEVEL_4'] = fbp_df.LAND_COVER_CLASS_CD_1
    fbp_df['BCLCS_LEVEL_5'] = np.where(
        fbp_df.cc < 10,
        None,
        np.where(fbp_df.cc <= 25, 'SP', np.where(fbp_df.cc <= 60, 'OP', 'DE'))
    )
    if not 'EARLIEST_NONLOGGING_DIST_TYPE' in fbp_df.columns:
        fbp_df['EARLIEST_NONLOGGING_DIST_TYPE'] = np.where(
            fbp_df.treatment_type.str.contains('burn|fire', case=False),
            'B',
            ''
        )
    fbp_df['CROWN_CLOSURE'] = fbp_df.cc

    # Assign stand age to 0 if no live trees. Create the column first if it is absent
    # entirely, so a completely missing PROJ_AGE_1 column defaults cleanly for a no-live-tree
    # stand instead of raising AttributeError before validation gets a chance to run.
    if 'PROJ_AGE_1' not in fbp_df.columns:
        fbp_df['PROJ_AGE_1'] = pd.Series([None] * len(fbp_df), index=fbp_df.index, dtype=object)
    fbp_df['PROJ_AGE_1'] = np.where(no_live_trees, 0, fbp_df['PROJ_AGE_1'])
    # BCWFT2018's getStocking() treats NaN as supplied (it checks `is not None`) and adds it to
    # dead stems, silently producing a NaN stocking value - normalize a confirmed no-live-tree
    # stand's live density to numeric 0 so stocking is computed from the recorded dead stems.
    fbp_df['VRI_LIVE_STEMS_PER_HA'] = fbp_df['stand_dens_tpha_live_sum'].mask(no_live_trees, 0)
    fbp_df['VRI_DEAD_STEMS_PER_HA'] = fbp_df.stand_dens_tpha_dead_sum
    fbp_df['STAND_PERCENTAGE_DEAD'] = 100 * fbp_df.stand_ba_m2pha_dead_sum / fbp_df.stand_ba_m2pha_sum

    # Normalize whitespace/casing on the user-supplied geographic fields, then validate all
    # required user-supplied fields, only after PROJ_AGE_1's own defaulting above - a stand
    # with no live trees legitimately defaults PROJ_AGE_1 to 0 regardless of its original
    # value, so validating the raw input first would wrongly reject an unfilled PROJ_AGE_1
    # that the defaulting logic was always going to fix anyway.
    fbp_df = _normalize_user_supplied_fbp_fields(fbp_df)
    _validate_user_supplied_fbp_fields(fbp_df, bc_fuel_type)

    # Filter columns to only those needed for fuel typing
    fbp_df = fbp_df.reindex(columns=['unique_id'] + field_list)

    # Normalize date columns (timezone-naive, timezone-aware, or string) before casting
    fbp_df = _coerce_datetime_columns(fbp_df, field_dict)

    # Replace missing species codes with None before casting; excluded from the astype()
    # call below since casting 'None' to 'str' would turn it into the literal text 'None'
    fbp_df = _coerce_missing_species_codes(fbp_df)
    non_species_field_dict = {k: v for k, v in field_dict.items() if k not in _SPECIES_CD_FIELDS}

    # Ensure correct data types
    fbp_df = fbp_df.astype(non_species_field_dict)

    # Convert dataframe to list containing only the rows needed for fbp fuel typing
    dfList = fbp_df.reindex(columns=['unique_id'] + field_list).values.tolist()

    for row in dfList:
        fuelData = bc_fuel_type.getFuelType(season, *row[4:])
        if fuelData is not None:
            # Get bcwft line reference number (row[0]), fuel type code (row[1]), and fuel type modifier (row[2])
            row[1], row[2], row[3] = fuelData
            # Remove dash from fuel type code
            row[2] = row[2].replace('-', '')
        else:
            row[1], row[2], row[3] = np.nan, 'NoMatchingFuelType_ERROR', np.nan

    ft_df = pd.DataFrame(dfList, columns=['unique_id'] + field_list)

    # Add new columns in ft_df to the original dataframe
    df = df.merge(ft_df[['unique_id', 'FuelType', 'FT_Modifier']], on='unique_id', how='left')
    df = df.rename(columns={'FuelType': 'fbp_fuel_type', 'FT_Modifier': 'fuel_type_modifier'})

    return df


def _coerce_datetime_columns(df: pd.DataFrame, field_dict: dict) -> pd.DataFrame:
    """
    Coerce columns BCWFT2018 expects as datetime64[ns] to a timezone-naive dtype.

    Accepts timezone-naive datetimes, timezone-aware datetimes (e.g., columns
    sourced from a GeoPackage), and string dates, so any of these date
    formats can be passed through to BCWFT2018 without a dtype-cast error.

    :param df: DataFrame containing columns to coerce.
    :param field_dict: Mapping of column name to the dtype string BCWFT2018 expects.
    :return: Copy of df with datetime-typed columns coerced to timezone-naive
        datetime64[ns]; other columns are unchanged.
    """
    df = df.copy()
    for field, dtype in field_dict.items():
        if field in df.columns and str(dtype).startswith('datetime64'):
            df[field] = (
                pd.to_datetime(df[field], errors='coerce', utc=True)
                .dt.tz_localize(None)
                .astype('datetime64[ns]')
            )
    return df


def _coerce_missing_species_codes(df: pd.DataFrame) -> pd.DataFrame:
    """
    Replace missing (NaN) SPECIES_CD_1..SPECIES_CD_6 values with None.

    BCWFT2018's verifyInputs() only accepts str or None for these fields, not a bare NaN
    float. Must run before the general field_dict-driven astype() cast in
    _calc_fbp_fuel_type(): casting a column to 'str' converts both NaN and None into the
    literal strings 'nan'/'None' rather than leaving None alone, so these columns are
    coerced here and then excluded from that later cast.

    :param df: DataFrame containing zero or more of the SPECIES_CD_1..SPECIES_CD_6 columns.
    :return: Copy of df with NaN replaced by None in those columns; other columns unchanged.
    """
    df = df.copy()
    present_cols = [col for col in _SPECIES_CD_FIELDS if col in df.columns]
    # Cast to object first: .where(..., None) on a float64 column (the common case - a rank
    # with zero non-null values across every row, e.g. no plot has a 6th species) coerces the
    # replacement None back into NaN to match the column's existing float dtype, silently
    # undoing the fix.
    df[present_cols] = df[present_cols].astype(object)
    df[present_cols] = df[present_cols].where(df[present_cols].notna(), None)
    return df


def _is_valid_stand_age(value) -> bool:
    """
    Check whether a PROJ_AGE_1 value is a valid, non-negative, finite real number.

    Excludes bool explicitly, since Python's bool subclasses int and would otherwise pass an
    isinstance(value, (int, float)) check. Checks pd.isna() before anything else, since
    np.isfinite(pd.NA) returns pd.NA (not a plain bool) rather than raising, which would make
    a direct boolean check on its result ambiguous.

    :param value: Candidate PROJ_AGE_1 value from a single row.
    :return: True if value is a real number (excluding bool), finite, and >= 0; False otherwise.
    """
    if pd.isna(value):
        return False
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        return False
    return bool(np.isfinite(float(value)) and value >= 0)


def _no_live_trees(
        live_density: pd.Series,
        total_density: pd.Series,
        dead_density: pd.Series,
) -> pd.Series:
    """
    Identify stands affirmatively known to have no live trees.

    An absent live group from the tree stand-summary aggregation maps to NaN. Total density and
    dead density must both be present and equal before that NaN is interpreted as an all-dead
    stand; otherwise it remains missing data.

    On a pandas nullable dtype (e.g. 'Float64'), live_density.eq(0) returns pd.NA rather than
    False wherever live_density itself is NA, which would otherwise make the returned mask a
    three-state Boolean: np.where() raises TypeError on an indeterminate value, and (were this
    mask used directly to decide ambiguity) a nullable-dtype NA could silently bypass
    _validate_live_density()'s .any() check instead of raising. fillna(False) on both operands
    keeps this an ordinary two-state Boolean Series regardless of input dtype.

    :param live_density: Per-plot summed live-tree density in stems per hectare.
    :param total_density: Per-plot summed total tree density in stems per hectare.
    :param dead_density: Per-plot summed dead-tree density in stems per hectare.
    :return: Boolean Series that is true for an exact live-density zero or a corroborated
        all-dead stand.
    """
    confirmed_all_dead = (
        live_density.isna()
        & total_density.notna()
        & dead_density.notna()
        & total_density.eq(dead_density)
    )
    return live_density.eq(0).fillna(False) | confirmed_all_dead.fillna(False)


def _normalize_user_supplied_fbp_fields(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize whitespace and casing on the user-supplied geographic code fields.

    COAST_INTERIOR_CD and BEC_ZONE_CODE are normalized to uppercase (matching BCWFT2018's own
    'C'/'I' branch checks and its becZones domain); BEC_SUBZONE is normalized to lowercase
    (matching its becSubzones domain). Only real string values are touched - missing
    (None/pd.NA/NaN) and non-string values are left as-is so
    _validate_user_supplied_fbp_fields() can report them accurately. Never maps an alias or
    unknown value to a valid code; a typo remains a typo after normalization, only its
    whitespace and casing change.

    :param df: DataFrame containing zero or more of COAST_INTERIOR_CD/BEC_ZONE_CODE/BEC_SUBZONE.
    :return: Copy of df with those columns' string values stripped and case-normalized;
        other columns and non-string values are unchanged.
    """
    df = df.copy()

    def _normalize(value, upper: bool):
        """
        Strip and case-normalize a single candidate geographic-code value.

        :param value: Candidate cell value; only real strings are transformed.
        :param upper: True to uppercase the stripped string, False to lowercase it.
        :return: The normalized string, or value unchanged if it is not a string.
        """
        if not isinstance(value, str):
            return value
        stripped = value.strip()
        return stripped.upper() if upper else stripped.lower()

    for field in ('COAST_INTERIOR_CD', 'BEC_ZONE_CODE'):
        if field in df.columns:
            df[field] = df[field].apply(_normalize, upper=True)
    if 'BEC_SUBZONE' in df.columns:
        df['BEC_SUBZONE'] = df['BEC_SUBZONE'].apply(_normalize, upper=False)
    return df


def _validate_live_density(df: pd.DataFrame) -> pd.Series:
    """
    Validate the columns needed to classify live-tree density, then reject a missing live-tree
    density that is not corroborated as a confirmed all-dead stand.

    Column presence is checked here, before _no_live_trees() is called, rather than letting
    _calc_fbp_fuel_type() access these columns directly: stand_dens_tpha_sum is a dependency this
    validation introduces, and accessing it - or unique_id, needed to name affected plots -
    directly on a DataFrame missing the column would otherwise raise a raw KeyError instead of
    the same clear, upfront ValueError this module's other required-field validation already
    uses.

    A missing stand_dens_tpha_live_sum value is not by itself proof of zero live trees - the same
    NaN can arise from a plot with no tree records, unjoined identifiers, missing/unrecognized
    tree statuses, or other unavailable upstream values. Only _no_live_trees()'s corroborated
    all-dead condition may treat a missing live density as zero; every other missing value is
    ambiguous input and must be rejected before it reaches BCWFT2018's per-plot processing, where
    it would otherwise silently produce a NaN stocking calculation.

    :param df: DataFrame expected to contain 'unique_id', 'stand_dens_tpha_live_sum',
        'stand_dens_tpha_sum', and 'stand_dens_tpha_dead_sum'.
    :raises ValueError: If any of those columns are missing entirely, naming every missing
        column; or if any plot has a missing live density without corroborating total/dead
        evidence of an all-dead stand, naming every affected unique_id value.
    :return: Boolean Series from _no_live_trees(), true for an exact live-density zero or a
        corroborated all-dead stand.
    """
    required_columns = [
        'unique_id', 'stand_dens_tpha_live_sum', 'stand_dens_tpha_sum', 'stand_dens_tpha_dead_sum',
    ]
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        raise ValueError(
            'fbp_prep_df is missing required column(s) needed to classify live-tree density: '
            f'{missing_columns}.'
        )

    no_live_trees = _no_live_trees(
        df['stand_dens_tpha_live_sum'], df['stand_dens_tpha_sum'], df['stand_dens_tpha_dead_sum'],
    )
    ambiguous = df['stand_dens_tpha_live_sum'].isna() & ~no_live_trees
    if ambiguous.any():
        affected = df.loc[ambiguous, 'unique_id'].tolist()
        raise ValueError(
            'fbp_prep_df has plot(s) with a missing stand_dens_tpha_live_sum value that is not '
            'corroborated as a confirmed all-dead stand by equal, populated '
            'stand_dens_tpha_sum/stand_dens_tpha_dead_sum values. A missing live density alone '
            f'is not proof of zero live trees. Affected unique_id(s): {affected}.'
        )
    return no_live_trees


def _validate_user_supplied_fbp_fields(df: pd.DataFrame, bc_fuel_type: bcwft.FuelTyping) -> None:
    """
    Raise a clear, upfront error for every plot with a missing or invalid manually-supplied
    field, instead of letting BCWFT2018 raise a cryptic error, or silently pick a wrong branch,
    for the first affected plot deep inside the per-plot loop.

    COAST_INTERIOR_CD must be exactly 'C' or 'I'; BEC_ZONE_CODE and BEC_SUBZONE must be members
    of BCWFT2018's own bc_fuel_type.becZones/becSubzones domains (not a hand-copied duplicate of
    those lists, so this can never drift from the vendored implementation); values are checked
    after _normalize_user_supplied_fbp_fields() has already stripped whitespace and normalized
    casing. PROJ_AGE_1 must be a non-negative, finite real number (see _is_valid_stand_age()) -
    checked after _calc_fbp_fuel_type()'s own no-live-tree default has already run, so a
    genuinely unfilled age is only rejected for stands that actually have live trees.

    These are all user-supplied fields (see conpyro_attributes.py's _prep_fbp_df()), not
    something FuelAnalyst itself can compute, so an invalid value here always means the user's
    own fill-in step missed a plot or contains a typo - it is never a FuelAnalyst bug to fix by
    coercion, unlike the missing species codes _calc_fbp_fuel_type() also handles.

    :param df: DataFrame with 'unique_id' and the fields BCWFT2018 requires already merged in.
    :param bc_fuel_type: An already-constructed bcwft.FuelTyping() instance, reused here for its
        becZones/becSubzones domains rather than constructing a second instance.
    :raises ValueError: If 'unique_id' itself is absent, or if any plot has a missing/invalid
        value for a required field - naming every affected field, its affected unique_id
        values, and (where a value is present but invalid) the value itself.
    :return: None.
    """
    if 'unique_id' not in df.columns:
        raise ValueError("fbp_prep_df is missing the required 'unique_id' identity column.")

    string_domains = {
        'COAST_INTERIOR_CD': _COAST_INTERIOR_DOMAIN,
        'BEC_ZONE_CODE': tuple(bc_fuel_type.becZones),
        'BEC_SUBZONE': tuple(bc_fuel_type.becSubzones),
    }

    problems = {}
    for field, domain in string_domains.items():
        if field not in df.columns:
            problems[field] = 'column is missing entirely'
            continue
        invalid_mask = ~df[field].apply(lambda value, dom=domain: isinstance(value, str) and value in dom)
        if invalid_mask.any():
            problems[field] = dict(zip(df.loc[invalid_mask, 'unique_id'], df.loc[invalid_mask, field]))

    for field in _REQUIRED_NUMERIC_FIELDS:
        if field not in df.columns:
            problems[field] = 'column is missing entirely'
            continue
        invalid_mask = ~df[field].apply(_is_valid_stand_age)
        if invalid_mask.any():
            problems[field] = dict(zip(df.loc[invalid_mask, 'unique_id'], df.loc[invalid_mask, field]))

    if problems:
        details = '; '.join(f'{field}: {affected}' for field, affected in problems.items())
        raise ValueError(
            'fbp_prep_df has unfilled or invalid user-supplied field(s) required by BCWFT2018 '
            '(fill these in manually from BC VRI/BEC-zone GIS data before calling '
            f'process_fbp_fuel_type()): {details}.'
        )


def process_fbp_fuel_type(
        master_fuel_df_path: str,
        fbp_prep_df_path: str,
        conpyro_df_path: str,
        out_dir: str,
        season: str
) -> None:
    """
    Calculate the FBP fuel type for each plot in the DataFrame using the BCWFT2018 fuel typing system.

    :param master_fuel_df_path: Path to the master fuel DataFrame CSV file.
    :param fbp_prep_df_path: Path to the FBP preparation DataFrame CSV file.
    :param conpyro_df_path: Path to the ConPyro DataFrame CSV file to be updated with FBP fuel types.
    :param out_dir: Directory to save the updated ConPyro DataFrame CSV file with FBP fuel types.
    :param season: Season for fuel typing ('Growing' or 'Dormant'). Case-insensitive.
    :return: None. Writes an updated ConPyro CSV with an `_fbp` filename suffix.
    """
    # Columns to drop from the FBP preparation DataFrame
    fbp_drop_columns = [
        '_date',
        'treatment_area', 'treatment_unit', 'treatment_type',
        'plot_id', 'SPECIES_CD_1'
    ]
    fbp_rename_columns = {
        'BEC_Zone': 'BEC_ZONE_CODE',
        'BEC_Subzone': 'BEC_SUBZONE',
        'SPECIES_CD_1_max_age': 'PROJ_AGE_1',
        'recent_clearcut_date_10_yrs': 'HARVEST_DATE',
        'recent_fire_date_11_yrs': 'EARLIEST_NONLOGGING_DIST_DATE',
    }

    # Load the master fuel DataFrame and the FBP preparation DataFrame
    master_fuel_df = pd.read_csv(master_fuel_df_path)
    fbp_prep_df = (pd.read_csv(fbp_prep_df_path)
                   .drop(columns=fbp_drop_columns)
                   .rename(columns=fbp_rename_columns))
    # fbp_fuel_type is text; an empty placeholder column would otherwise be read as floating-point missing values
    conpyro_df = pd.read_csv(conpyro_df_path, dtype={'fbp_fuel_type': 'string'})

    # Merge the two dataframes on 'unique_id' to get all necessary attributes
    fuel_type_df = master_fuel_df.merge(fbp_prep_df, on='unique_id', how='left')
    fuel_type_df['_date'] = fuel_type_df['_date'].astype(str)

    # Calculate FBP fuel type
    fuel_type_df = _calc_fbp_fuel_type(fuel_type_df, season)

    print('Assigning FBP fuel types to ConPyro DataFrame')
    # Assign FBP fuel types to conpyro_df based on unique_id
    conpyro_df = conpyro_df.merge(
        fuel_type_df[['unique_id', 'fbp_fuel_type']].rename(columns={'fbp_fuel_type': 'fbp_fuel_type_new'}),
        on='unique_id',
        how='left'
    )
    # Retain existing fbp_fuel_type values in conpyro_df if present (only replace empty values)
    conpyro_df['fbp_fuel_type'] = conpyro_df['fbp_fuel_type'].combine_first(conpyro_df['fbp_fuel_type_new'])
    conpyro_df = conpyro_df.drop(columns=['fbp_fuel_type_new'])

    # Replace conpyro_df with updated DataFrame
    print('Saving updated ConPyro DataFrame with FBP fuel types')
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, os.path.basename(conpyro_df_path).replace('.csv', '_fbp.csv'))
    helper.export_csv(conpyro_df, out_path)

    return


# Test routine for calculating FBP fuel types
if __name__ == '__main__':
    # Define input and output folders
    examples_dir = helper.get_examples_dir(os.path.dirname(__file__))
    _out_dir = os.path.join(examples_dir, 'results', 'fbp_fuel_typing')

    # Get stand fire and FOFEM consume csv paths
    _master_fuel_df_path = os.path.join(examples_dir, 'results', 'fuel_analyst', 'master_fuel_df.csv')
    _fbp_prep_df_path = os.path.join(examples_dir, 'data', 'fbp_fuel_typing', 'fbp_prep_df.csv')
    _conpyro_df_path = os.path.join(examples_dir, 'results', 'fuel_analyst', 'conpyro_df.csv')
    _season = 'growing'  # Options: 'growing' or 'dormant'

    # Run FBP fuel type processing
    process_fbp_fuel_type(_master_fuel_df_path, _fbp_prep_df_path, _conpyro_df_path, _out_dir, _season)
