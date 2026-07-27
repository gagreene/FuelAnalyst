"""Schema checks for the raw Survey123 CSVs the woody-debris-processing pipeline reads.

woody_debris.py accesses many raw column names by hard-coded string (e.g.
df['t1_azimuth'] in _calc_plot_t2_azimuth, df[f't{tsct}_slope'] in
_calc_plot_tsct_slope_correction, or woody_merged_df['woody_diam'] in
_calc_woody_diam_cm, after transect prefixes are stripped in _get_merged_woody_df)
before any of those columns are computed. A renamed or mistyped header in a
Survey123 export (e.g. 't1_slope_pct' instead of 't1_slope') then surfaces as a
KeyError deep in the pipeline instead of a clear message.

woody_cols_test checks the raw files directly against the column names
woody_debris.py requires, so a bad export fails fast with the exact missing
column names.

Note: not named test_woody_cols, so pytest's default `python_functions = test_*`
setting won't auto-collect it. Add `python_functions = test_* *_test` under
[tool.pytest.ini_options] in pyproject.toml to have pytest discover it, or call
it directly / from a test_*-prefixed wrapper.
"""
import os

from fuel_analyst.components import helper

# dir_dict is duplicated here (rather than imported from data_clean) because
# importing fuel_analyst.data_clean raises at import time outside a Docker
# container (its module-level is_docker guard).
DIR_DICT = {
    'plot': '1_Plot_Attributes',
    'plants': '2_Plants_Regeneration',
    'trees': '3_Trees',
    'cover': '4_Canopy_Cover',
    'woody': '5_Woody_Debris',
}

# Columns every unique_id-bearing survey file must carry (get_unique_id_strip).
UNIQUE_ID_COLUMNS = {'_date', 'treatment_area', 'treatment_unit', 'treatment_type', 'plot_id'}

# 5_Woody_Debris/survey_0*.csv (the woody-debris-form plot-level record) -- read in
# process_woody_debris, then _calc_plot_t2_azimuth (df['t1_azimuth']),
# _calc_plot_tsct_slope_correction (df[f't{tsct}_slope_units'/'_slope']),
# _calc_plot_tsct_total_slope_correction (df['num_transects']),
# _calc_plot_duff_litter_depths (columns matching '_duff_75'/'_duff_225'/'_litter_75'/'_litter_225'),
# and _calc_tallied_woody_counts (df[t{n}_woody_tally_0to2/_28to30]).
REQUIRED_WOODY_PLOT_COLUMNS = UNIQUE_ID_COLUMNS | {
    'GlobalID', 'num_transects', 't1_azimuth',
    't1_slope_units', 't1_slope', 't2_slope_units', 't2_slope',
    't1_woody_tally_0to2', 't1_woody_tally_28to30',
    't2_woody_tally_0to2', 't2_woody_tally_28to30',
    't1_duff_75', 't1_duff_225', 't1_litter_75', 't1_litter_225',
    't2_duff_75', 't2_duff_225', 't2_litter_75', 't2_litter_225',
}

# 5_Woody_Debris/t1_woody_2*.csv and t2_woody_3*.csv (per-transect woody debris
# pieces) -- read in _get_merged_woody_df, which strips the 't1_'/'t2_' prefix
# before _calc_woody_diam_cm (woody_diam), _calc_woody_species (woody_species,
# woody_decay), and _calc_woody_corrected_tsct_lengths/_merge_spp_comp
# (ParentGlobalID) run on the merged frame.
REQUIRED_WOODY_TRANSECT_COLUMNS = {'ParentGlobalID', 'woody_diam', 'woody_species', 'woody_decay'}

# 5_Woody_Debris/spp_comp_manual_1*.csv (manual species composition entries) --
# read in process_woody_debris, then _assign_spp_comp_id_col (ParentGlobalID),
# _calc_spp_comp_duff_litter_bulk_density (spp_comp_code), and
# _calc_spp_comp_specific_gravity (spp_comp_code, spp_comp_percent).
REQUIRED_SPP_COMP_COLUMNS = {'ParentGlobalID', 'spp_comp_code', 'spp_comp_percent'}


def _first_csv(dir_path: str, prefix: str) -> str:
    matches = sorted(f for f in os.listdir(dir_path) if f.startswith(prefix) and f.endswith('.csv'))
    if not matches:
        raise FileNotFoundError(f"No '{prefix}*.csv' found in {dir_path}")
    return os.path.join(dir_path, matches[0])


def _missing_columns(path: str, required: set, prefix: str = '') -> list:
    df = helper.get_df(path)
    if prefix:
        df = df.rename(columns=lambda col: col.replace(prefix, '', 1) if col.startswith(prefix) else col)
    return helper.get_missing_df_columns(df, sorted(required))


def woody_cols_test(in_dir: str | None = None) -> None:
    """Assert every raw woody-debris CSV under in_dir has the columns woody_debris.py expects.

    in_dir defaults to DATA_BASE_DIR (the same env var the pipeline itself reads at runtime),
    falling back to the repo's bundled example data so this still runs with no env configured.
    """
    in_dir = in_dir or os.getenv(
        'DATA_BASE_DIR',
        os.path.join(helper.get_examples_dir(os.path.dirname(__file__)), 'data', 'Survey123_Data'),
    )

    woody_dir = os.path.join(in_dir, DIR_DICT['woody'])

    checks = {
        'woody survey_0': (_first_csv(woody_dir, 'survey_0'), REQUIRED_WOODY_PLOT_COLUMNS, ''),
        't1_woody': (_first_csv(woody_dir, 't1_woody'), REQUIRED_WOODY_TRANSECT_COLUMNS, 't1_'),
        't2_woody': (_first_csv(woody_dir, 't2_woody'), REQUIRED_WOODY_TRANSECT_COLUMNS, 't2_'),
        'spp_comp_manual': (_first_csv(woody_dir, 'spp_comp_manual'), REQUIRED_SPP_COMP_COLUMNS, ''),
    }

    problems = {
        label: missing
        for label, (path, required, prefix) in checks.items()
        if (missing := _missing_columns(path, required, prefix))
    }

    assert not problems, 'Missing expected column(s):\n' + '\n'.join(
        f'  {label}: {missing}' for label, missing in problems.items()
    )


if __name__ == '__main__':
    woody_cols_test()
    print('woody_cols_test passed.')
