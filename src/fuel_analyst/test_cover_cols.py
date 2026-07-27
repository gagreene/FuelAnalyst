"""Schema checks for the raw Survey123 CSVs the canopy-cover-processing pipeline reads.

canopy_cover.py accesses many raw column names by hard-coded string (e.g.
transect_df['cc_transect'] and transect_df[f'cc_{i}'] in _process_transect_data,
or df['GlobalID'] in _process_cc_data) before any of those columns are computed.
A renamed or mistyped header in a Survey123 export (e.g. 'cc_02' instead of
'cc_2') then surfaces as a KeyError deep in the pipeline instead of a clear
message.

cover_cols_test checks the raw files directly against the column names
canopy_cover.py requires, so a bad export fails fast with the exact missing
column names.

Note: not named test_cover_cols, so pytest's default `python_functions = test_*`
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

# 4_Canopy_Cover/survey_0*.csv (the cover-form plot-level record) -- read in
# process_canopy_cover, then helper.get_unique_id and canopy_cover._process_cc_data
# (df['GlobalID'].map(...)).
REQUIRED_COVER_PLOT_COLUMNS = UNIQUE_ID_COLUMNS | {'GlobalID'}

# 4_Canopy_Cover/canopy_cover_1*.csv (transect-level cover reads) -- read in
# process_canopy_cover, then canopy_cover._process_transect_data and
# _process_cc_data (grouped by ParentGlobalID).
REQUIRED_COVER_TRANSECT_COLUMNS = {'ParentGlobalID', 'cc_transect'} | {
    f'cc_{i}' for i in range(2, 32, 2)
}


def _first_csv(dir_path: str, prefix: str) -> str:
    matches = sorted(f for f in os.listdir(dir_path) if f.startswith(prefix) and f.endswith('.csv'))
    if not matches:
        raise FileNotFoundError(f"No '{prefix}*.csv' found in {dir_path}")
    return os.path.join(dir_path, matches[0])


def _missing_columns(path: str, required: set) -> list:
    return helper.get_missing_df_columns(helper.get_df(path), sorted(required))


def cover_cols_test(in_dir: str | None = None) -> None:
    """Assert every raw canopy-cover CSV under in_dir has the columns canopy_cover.py expects.

    in_dir defaults to DATA_BASE_DIR (the same env var the pipeline itself reads at runtime),
    falling back to the repo's bundled example data so this still runs with no env configured.
    """
    in_dir = in_dir or os.getenv(
        'DATA_BASE_DIR',
        os.path.join(helper.get_examples_dir(os.path.dirname(__file__)), 'data', 'Survey123_Data'),
    )

    cover_dir = os.path.join(in_dir, DIR_DICT['cover'])

    checks = {
        'cover survey_0': (_first_csv(cover_dir, 'survey_0'), REQUIRED_COVER_PLOT_COLUMNS),
        'canopy_cover_1': (_first_csv(cover_dir, 'canopy_cover_1'), REQUIRED_COVER_TRANSECT_COLUMNS),
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
    cover_cols_test()
    print('cover_cols_test passed.')
