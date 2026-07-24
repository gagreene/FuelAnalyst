"""Schema checks for the raw Survey123 CSVs the tree-processing pipeline reads.

trees.py and data_clean.py access many raw column names by hard-coded string
(e.g. tree_df['tree_bark_char_high'] in trees._round_tree_data, or
df['lgtree_plot_radius'] in trees._round_plot_data / _calc_plot_multipliers)
before any of those columns are computed. A renamed or mistyped header in a
Survey123 export (e.g. 'tree_bark_char' instead of 'tree_bark_char_high') then
surfaces as a KeyError deep in the pipeline instead of a clear message.

tree_cols_test checks the raw files directly against the column names
trees.py/data_clean.py require, so a bad export fails fast with the exact
missing column names.

Note: not named test_tree_cols, so pytest's default `python_functions = test_*`
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

# 1_Plot_Attributes/survey_0*.csv -- read in plot_attributes_read.
REQUIRED_PLOT_COLUMNS = UNIQUE_ID_COLUMNS | {
    'GlobalID', 'x', 'y', 'plot_elevation', 'plot_slope_units', 'plot_slope', 'plot_aspect',
}

# 3_Trees/survey_0*.csv (the trees-form plot-level record) -- read in
# subplot_data, then trees._round_plot_data / trees._calc_plot_multipliers.
REQUIRED_TREES_PLOT_COLUMNS = UNIQUE_ID_COLUMNS | {
    'GlobalID', 'lgtree_plot_radius', 'smtree_plot_radius', 'sapling_plot_radius',
}

# 3_Trees/tree_plot*.csv (individual tree records) -- read in tree_data_read,
# then trees._round_tree_data and the per-tree attribute chain.
REQUIRED_TREE_PLOT_COLUMNS = {
    'GlobalID', 'ParentGlobalID', 'tree_species', 'tree_type', 'tree_status',
    'tree_dcy_class_cnfr', 'tree_dcy_class_brdlf', 'tree_crwn_broken_top', 'tree_ht_class',
    'tree_dbh', 'tree_ht', 'tree_cbh', 'tree_dcbh', 'tree_fuel_bed_ht',
    'tree_bark_char_high', 'tree_bark_char_low', 'tree_bark_char_azim',
    'tree_crwn_discolor_prcnt', 'tree_crwn_discolor', 'tree_crwn_consumed',
    'tree_basal_char', 'tree_basal_depth_of_burn',
}

# 3_Trees/sapling*.csv -- read in tree_data_read, then trees._calc_sapling_*
# and trees._merge_saplings_to_trees.
REQUIRED_SAPLING_COLUMNS = {
    'GlobalID', 'ParentGlobalID', 'sapling_species',
    'sapling_live_count', 'sapling_live_dbh', 'sapling_live_ht', 'sapling_live_cbh',
    'sapling_dead_count', 'sapling_dead_dbh', 'sapling_dead_ht',
}


def _first_csv(dir_path: str, prefix: str) -> str:
    matches = sorted(f for f in os.listdir(dir_path) if f.startswith(prefix) and f.endswith('.csv'))
    if not matches:
        raise FileNotFoundError(f"No '{prefix}*.csv' found in {dir_path}")
    return os.path.join(dir_path, matches[0])


def _missing_columns(path: str, required: set) -> list:
    return helper.get_missing_df_columns(helper.get_df(path), sorted(required))


def tree_cols_test(in_dir: str | None = None) -> None:
    """Assert every raw tree-related CSV under in_dir has the columns trees.py/data_clean.py expect.

    in_dir defaults to DATA_BASE_DIR (the same env var the pipeline itself reads at runtime),
    falling back to the repo's bundled example data so this still runs with no env configured.
    """
    in_dir = in_dir or os.getenv(
        'DATA_BASE_DIR',
        os.path.join(helper.get_examples_dir(os.path.dirname(__file__)), 'data', 'Survey123_Data'),
    )

    plot_dir = os.path.join(in_dir, DIR_DICT['plot'])
    trees_dir = os.path.join(in_dir, DIR_DICT['trees'])

    checks = {
        'plot survey_0': (_first_csv(plot_dir, 'survey_0'), REQUIRED_PLOT_COLUMNS),
        'trees survey_0': (_first_csv(trees_dir, 'survey_0'), REQUIRED_TREES_PLOT_COLUMNS),
        'tree_plot': (_first_csv(trees_dir, 'tree_plot'), REQUIRED_TREE_PLOT_COLUMNS),
        'sapling': (_first_csv(trees_dir, 'sapling'), REQUIRED_SAPLING_COLUMNS),
    }

    problems = {
        label: missing
        for label, (path, required) in checks.items()
        if (missing := _missing_columns(path, required))
    }

    assert not problems, 'Missing expected column(s):\n' + '\n'.join(
        f'  {label}: {missing}' for label, missing in problems.items()
    )


if __name__ == '__main__':
    tree_cols_test()
    print('tree_cols_test passed.')
