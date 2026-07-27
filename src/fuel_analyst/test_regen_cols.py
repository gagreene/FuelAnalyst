"""Schema checks for the raw Survey123 CSVs the plants/regen-processing pipeline reads.

plants_regen.py accesses many raw column names by hard-coded string (e.g.
df[f'pc_species_{x}_pct'] and df[f'pc_species_{x}_ht'] in _process_top_five_spp,
or regen_df['rgn_live_small_cnt'] in _process_regen) before any of those columns
are computed. A renamed or mistyped header in a Survey123 export (e.g.
'rgn_live_small_count' instead of 'rgn_live_small_cnt') then surfaces as a
KeyError deep in the pipeline instead of a clear message.

regen_cols_test checks the raw files directly against the column names
plants_regen.py requires, so a bad export fails fast with the exact missing
column names.

Note: not named test_regen_cols, so pytest's default `python_functions = test_*`
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

# 2_Plants_Regeneration/survey_0*.csv (the plants-form plot-level record) -- read in
# process_plants_regen, then _process_top_five_spp (df[f'pc_species_{x}...']) and
# _process_regen (df.GlobalID.map(...)).
REQUIRED_PLANTS_PLOT_COLUMNS = UNIQUE_ID_COLUMNS | {'GlobalID'} | {
    col
    for i in range(1, 6)
    for col in (f'pc_species_{i}', f'pc_species_{i}_other', f'pc_species_{i}_pct', f'pc_species_{i}_ht')
}

# 2_Plants_Regeneration/regeneration_1*.csv (regeneration counts by plot) -- read in
# process_plants_regen, then plants_regen._process_regen (grouped by ParentGlobalID).
REQUIRED_REGEN_COLUMNS = {
    'ParentGlobalID',
    'rgn_live_small_cnt', 'rgn_small_plot_proportion',
    'rgn_live_tall_cnt', 'rgn_tall_plot_proportion',
}


def _first_csv(dir_path: str, prefix: str) -> str:
    matches = sorted(f for f in os.listdir(dir_path) if f.startswith(prefix) and f.endswith('.csv'))
    if not matches:
        raise FileNotFoundError(f"No '{prefix}*.csv' found in {dir_path}")
    return os.path.join(dir_path, matches[0])


def _missing_columns(path: str, required: set) -> list:
    return helper.get_missing_df_columns(helper.get_df(path), sorted(required))


def regen_cols_test(in_dir: str | None = None) -> None:
    """Assert every raw plants/regen CSV under in_dir has the columns plants_regen.py expects.

    in_dir defaults to DATA_BASE_DIR (the same env var the pipeline itself reads at runtime),
    falling back to the repo's bundled example data so this still runs with no env configured.
    """
    in_dir = in_dir or os.getenv(
        'DATA_BASE_DIR',
        os.path.join(helper.get_examples_dir(os.path.dirname(__file__)), 'data', 'Survey123_Data'),
    )

    plants_dir = os.path.join(in_dir, DIR_DICT['plants'])

    checks = {
        'plants survey_0': (_first_csv(plants_dir, 'survey_0'), REQUIRED_PLANTS_PLOT_COLUMNS),
        'regeneration_1': (_first_csv(plants_dir, 'regeneration_1'), REQUIRED_REGEN_COLUMNS),
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
    regen_cols_test()
    print('regen_cols_test passed.')
