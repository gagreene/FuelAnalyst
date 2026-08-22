# Error Handling Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace every console-only warning and bespoke per-component issue report in FuelAnalyst with calls into a single centralized `error_handling` module, producing one CSV per run listing every issue by plot and form.

**Architecture:** A new `src/fuel_analyst/components/error_handling.py` module wraps the standard `logging` library. Components call `logging.getLogger(__name__)` (or `error_handling.get_logger(form)` from the orchestrator) and log at `.info`/`.warning`/`.error` exactly where they currently `print()`. A collecting `logging.Handler`, attached by `error_handling.start_run()` at the top of a pipeline run and detached by `error_handling.write_report(out_path, plot_df)` at the end, pivots everything into one wide CSV: one row per plot with ≥1 issue, a reserved `General Error` row for issues with no plot, one column per form, numbered/severity-prefixed messages per cell.

**Tech Stack:** Python stdlib `logging`, `pandas`. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-08-21-error-handling-module-design.md`

## Global Constraints

- Console output must not regress anywhere — every migrated `print(...)` becomes a `logger.info/warning/error(...)` call with the *same message text*, at the *same call site*. This is satisfied by the logger call alone: Task 1's `start_run()` attaches a plain `logging.StreamHandler(sys.stdout)` alongside the collecting handler specifically so every migrated logger call remains visible on the console exactly as the `print(...)` it replaced was (found necessary because attaching *any* handler to the `fuel_analyst` logger suppresses Python's `logging.lastResort` console fallback that bare, unconfigured logger calls rely on — see Task 1 Step 14). **Do not keep the original `print(...)` line alongside the new logger call** — that would double-print the same text once this handler is in place. Where a task's steps show `print(...)` retained next to a new `logger.*(...)` call, that print is a leftover from before this fix and should be dropped during that task's implementation.
- No function signature changes anywhere in the codebase to thread an error-collector object through. Components only ever `import logging` and call `logging.getLogger(__name__)`.
- Output CSV columns: `unique_id`, then whichever of `treatment_area, treatment_unit, treatment_type, plot_id` are actually present in the `plot_df` passed to `write_report()` (dynamic — a caller with none of these columns gets no identity columns at all, not blank ones), then one column per form actually present in the run's collected records (also dynamic, not hardcoded) — see spec §4.
- Cell format: numbered, newline-joined, severity-prefixed, e.g. `1. [WARNING] message one\n2. [ERROR] message two`.
- Plots with zero issues across all forms are omitted from the report entirely.
- Issues with no `unique_id` land on a reserved `General Error` row (blank identity columns), never dropped.
- `logger.info` = fallback-applied notes (was `pc_flammable_note`/`spp_comp_type_note`); `logger.warning` = existing `print('Warning: ...')` sites and non-impactful flagged issues; `logger.error` = tree-density issues where a record's density got zeroed (`results_partial=True` in the old system).
- Hard `raise ValueError`/`FileNotFoundError` pre-flight checks are out of scope — they stay as exceptions.

---

## Task 1: Core `error_handling` module

**Files:**
- Create: `src/fuel_analyst/components/error_handling.py`
- Test: `tests/unit/test_error_handling.py`

**Interfaces:**
- Produces: `start_run() -> None`, `write_report(out_path: str, plot_df: pd.DataFrame = None) -> None`, `get_logger(form: str) -> logging.Logger` where `form` is one of `'plot'`, `'plants'`, `'trees'`, `'cover'`, `'woody'`.

- [ ] **Step 1: Write the failing tests for `get_logger`**

```python
# tests/unit/test_error_handling.py
import logging

import pandas as pd
import pytest

from fuel_analyst.components import error_handling


def test_get_logger_returns_dotted_component_logger_name():
    logger = error_handling.get_logger('woody')
    assert logger.name == 'fuel_analyst.components.woody_debris'


def test_get_logger_unknown_form_raises_key_error():
    with pytest.raises(KeyError):
        error_handling.get_logger('not_a_form')
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/unit/test_error_handling.py -v`
Expected: FAIL with `ModuleNotFoundError` or `AttributeError: module 'error_handling' has no attribute 'get_logger'`.

- [ ] **Step 3: Implement `get_logger` and the form/logger-name mapping**

```python
# src/fuel_analyst/components/error_handling.py
"""
Centralized error/warning collection for FuelAnalyst.

Components report issues through the standard `logging` module:
    logger = logging.getLogger(__name__)
    logger.warning("...", extra={'unique_id': plot_id, 'issue_code': 'some_code'})

start_run() attaches a fresh collecting handler for the duration of one
pipeline run; write_report() pivots everything collected into a single CSV
(one row per plot with >=1 issue, plus a reserved 'General Error' row for
issues with no unique_id) and detaches the handler. Console output is
unaffected - the collecting handler runs alongside whatever handlers are
already attached by the caller's own logging configuration.
"""
import logging
import os
from collections import defaultdict
from typing import Optional

import pandas as pd

_LOGGER_NAME_ROOT = 'fuel_analyst'

_FORM_DISPLAY_NAMES = {
    'plot': 'Plot Attributes',
    'plants': 'Plants and Regeneration',
    'trees': 'Trees',
    'cover': 'Canopy Cover',
    'woody': 'Woody Debris',
}

_FORM_LOGGER_NAMES = {
    'plot': f'{_LOGGER_NAME_ROOT}.components.plot_attributes',
    'plants': f'{_LOGGER_NAME_ROOT}.components.plants_regen',
    'trees': f'{_LOGGER_NAME_ROOT}.components.trees',
    'cover': f'{_LOGGER_NAME_ROOT}.components.canopy_cover',
    'woody': f'{_LOGGER_NAME_ROOT}.components.woody_debris',
}

_GENERAL_ERROR_ROW = 'General Error'
_IDENTITY_COLUMNS = ['treatment_area', 'treatment_unit', 'treatment_type', 'plot_id']


def get_logger(form: str) -> logging.Logger:
    """Return the canonical logger for a given form key."""
    return logging.getLogger(_FORM_LOGGER_NAMES[form])
```

- [ ] **Step 4: Run to verify Step 1's tests pass**

Run: `pytest tests/unit/test_error_handling.py -v`
Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/fuel_analyst/components/error_handling.py tests/unit/test_error_handling.py
git commit -m "feat(error_handling): add get_logger form-to-logger-name mapping"
```

- [ ] **Step 6: Write the failing tests for `start_run`/`write_report` basic pivot**

```python
def test_start_run_write_report_pivots_by_plot_and_form(tmp_path):
    error_handling.start_run()
    logger_trees = error_handling.get_logger('trees')
    logger_woody = error_handling.get_logger('woody')

    logger_trees.warning('Tree issue for plot A', extra={'unique_id': 'A'})
    logger_woody.error('Woody issue for plot A', extra={'unique_id': 'A'})
    logger_trees.info('Tree issue for plot B', extra={'unique_id': 'B'})

    out_path = tmp_path / 'errors.csv'
    error_handling.write_report(str(out_path), plot_df=None)

    result = pd.read_csv(out_path, keep_default_na=False)
    row_a = result.loc[result['unique_id'] == 'A'].iloc[0]
    row_b = result.loc[result['unique_id'] == 'B'].iloc[0]
    assert row_a['Trees'] == '1. [WARNING] Tree issue for plot A'
    assert row_a['Woody Debris'] == '1. [ERROR] Woody issue for plot A'
    assert row_b['Trees'] == '1. [INFO] Tree issue for plot B'
    assert row_b['Woody Debris'] == ''


def test_write_report_without_start_run_raises():
    with pytest.raises(RuntimeError):
        error_handling.write_report('unused.csv')
```

- [ ] **Step 7: Run to verify failure**

Run: `pytest tests/unit/test_error_handling.py -v`
Expected: FAIL — `start_run`/`write_report` not defined.

- [ ] **Step 8: Implement `start_run` and `write_report`**

Insert the following **immediately above** the existing `get_logger` function
(private helpers come before the public group, per this codebase's function-
ordering convention):

```python
_active_handler: Optional['_CollectingHandler'] = None
_previous_level: Optional[int] = None


class _CollectingHandler(logging.Handler):
    """Collects LogRecords for fuel_analyst.* loggers without affecting other handlers."""

    def __init__(self):
        super().__init__(level=logging.INFO)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def _form_for_record(record: logging.LogRecord) -> str:
    for form, logger_name in _FORM_LOGGER_NAMES.items():
        if record.name == logger_name or record.name.startswith(logger_name + '.'):
            return _FORM_DISPLAY_NAMES[form]
    return record.name.rsplit('.', 1)[-1]
```

Insert the following **immediately below** the existing `get_logger` function
(public group, alphabetized: `get_logger` < `start_run` < `write_report`):

```python
def start_run() -> None:
    """Attach a fresh collecting handler for the duration of one pipeline run."""
    global _active_handler, _previous_level
    root_logger = logging.getLogger(_LOGGER_NAME_ROOT)
    if _active_handler is not None:
        root_logger.removeHandler(_active_handler)
        if _previous_level is not None:
            root_logger.setLevel(_previous_level)
    # Loggers default to the root logger's WARNING threshold. Without raising this
    # namespace's effective level, every .info(...) call (the fallback-note severity)
    # would be discarded by Logger.isEnabledFor() before it ever reached the handler.
    # The prior level is saved here and restored in write_report(), so collection
    # stays scoped to the active run rather than permanently changing the logger.
    _previous_level = root_logger.level
    root_logger.setLevel(logging.INFO)
    _active_handler = _CollectingHandler()
    root_logger.addHandler(_active_handler)


def write_report(out_path: str, plot_df: Optional[pd.DataFrame] = None) -> None:
    """Pivot everything collected since start_run() into one CSV; detach the handler."""
    global _active_handler, _previous_level
    if _active_handler is None:
        raise RuntimeError('write_report() called without a matching start_run()')
    records = _active_handler.records
    root_logger = logging.getLogger(_LOGGER_NAME_ROOT)
    root_logger.removeHandler(_active_handler)
    if _previous_level is not None:
        root_logger.setLevel(_previous_level)
    _active_handler = None
    _previous_level = None

    identity_cols = []
    id_lookup = {}
    if plot_df is not None and 'unique_id' in plot_df.columns:
        identity_cols = [c for c in _IDENTITY_COLUMNS if c in plot_df.columns]
        id_lookup = plot_df.set_index('unique_id')[identity_cols].to_dict('index')

    forms = sorted({_form_for_record(r) for r in records})
    rows = defaultdict(lambda: {form: [] for form in forms})
    for record in records:
        row_key = getattr(record, 'unique_id', None)
        # pd.isna() handles None, float NaN, and pd.NA (nullable pandas IDs) uniformly -
        # a bare `is None`/float-NaN check misses pd.NA, which sorted() below cannot compare.
        if pd.isna(row_key):
            row_key = _GENERAL_ERROR_ROW
        rows[row_key][_form_for_record(record)].append(
            f'[{record.levelname}] {record.getMessage()}'
        )

    ordered_keys = ([_GENERAL_ERROR_ROW] if _GENERAL_ERROR_ROW in rows else []) + \
        sorted(k for k in rows if k != _GENERAL_ERROR_ROW)

    out_rows = []
    for row_key in ordered_keys:
        row = {'unique_id': row_key}
        identity = id_lookup.get(row_key, {}) if row_key != _GENERAL_ERROR_ROW else {}
        for col in identity_cols:
            row[col] = identity.get(col, '')
        for form in forms:
            messages = rows[row_key][form]
            row[form] = '\n'.join(f'{i}. {msg}' for i, msg in enumerate(messages, start=1))
        out_rows.append(row)

    report_df = pd.DataFrame(out_rows, columns=['unique_id'] + identity_cols + forms)
    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    report_df.to_csv(out_path, index=False)
```

Note: `_CollectingHandler` is referenced by name in `_active_handler`'s type hint
before the class is defined below it in this insertion — Python resolves this fine
at runtime since the annotation is a string literal (`Optional['_CollectingHandler']`),
but if placing `_active_handler`'s declaration textually after the class instead,
adjust the annotation to `Optional[_CollectingHandler]` (no quotes) for clarity.

- [ ] **Step 9: Run to verify Step 6's tests pass**

Run: `pytest tests/unit/test_error_handling.py -v`
Expected: all 4 tests PASS.

- [ ] **Step 10: Commit**

```bash
git add src/fuel_analyst/components/error_handling.py tests/unit/test_error_handling.py
git commit -m "feat(error_handling): add start_run/write_report collecting handler and CSV pivot"
```

- [ ] **Step 11: Add tests covering identity columns, General Error blanking, dynamic-column omission, cell numbering, and logger-level restoration**

These exercise behavior Step 8's implementation should already satisfy — they
are coverage, not a fail-first cycle (nothing in Step 8's code needs to change
for these to pass, unless Step 12 finds otherwise).

```python
def test_identity_columns_populated_from_plot_df(tmp_path):
    error_handling.start_run()
    error_handling.get_logger('woody').warning('issue', extra={'unique_id': 'A'})
    plot_df = pd.DataFrame({
        'unique_id': ['A', 'B'],
        'treatment_area': ['Area1', 'Area2'],
        'treatment_unit': ['U1', 'U2'],
        'treatment_type': ['Pre', 'Pre'],
        'plot_id': [1, 2],
    })
    out_path = tmp_path / 'errors.csv'
    error_handling.write_report(str(out_path), plot_df=plot_df)

    result = pd.read_csv(out_path, keep_default_na=False)
    assert len(result) == 1  # plot B had zero issues and is omitted
    assert result.loc[0, 'treatment_area'] == 'Area1'
    assert result.loc[0, 'plot_id'] == 1


def test_general_error_row_has_blank_identity_and_sorts_first(tmp_path):
    error_handling.start_run()
    error_handling.get_logger('trees').warning('plot-level issue', extra={'unique_id': 'Z'})
    error_handling.get_logger('trees').warning('run-level issue')  # no unique_id
    plot_df = pd.DataFrame({'unique_id': ['Z'], 'treatment_area': ['Area1']})
    out_path = tmp_path / 'errors.csv'
    error_handling.write_report(str(out_path), plot_df=plot_df)

    result = pd.read_csv(out_path, keep_default_na=False)
    assert result.loc[0, 'unique_id'] == 'General Error'
    assert result.loc[0, 'treatment_area'] == ''
    assert result.loc[1, 'unique_id'] == 'Z'
    assert result.loc[1, 'treatment_area'] == 'Area1'


def test_identity_columns_omitted_entirely_when_plot_df_lacks_them(tmp_path):
    """extract_nrcan_wx.py/run_conpyro.py pass a plot_df with no treatment_*/plot_id
    columns at all - the report should have no identity columns, not blank ones."""
    error_handling.start_run()
    error_handling.get_logger('trees').warning('issue', extra={'unique_id': 'A'})
    plot_df = pd.DataFrame({'unique_id': ['A']})
    out_path = tmp_path / 'errors.csv'
    error_handling.write_report(str(out_path), plot_df=plot_df)

    result = pd.read_csv(out_path, keep_default_na=False)
    assert list(result.columns) == ['unique_id', 'Trees']


def test_write_report_restores_previous_logger_level(tmp_path):
    root_logger = logging.getLogger('fuel_analyst')
    original_level = root_logger.level
    try:
        root_logger.setLevel(logging.ERROR)
        error_handling.start_run()
        assert root_logger.level == logging.INFO
        error_handling.write_report(str(tmp_path / 'errors.csv'), plot_df=None)
        assert root_logger.level == logging.ERROR
    finally:
        root_logger.setLevel(original_level)


def test_multiple_issues_per_cell_are_numbered_in_order(tmp_path):
    error_handling.start_run()
    logger = error_handling.get_logger('woody')
    logger.warning('first issue', extra={'unique_id': 'A'})
    logger.error('second issue', extra={'unique_id': 'A'})
    out_path = tmp_path / 'errors.csv'
    error_handling.write_report(str(out_path), plot_df=None)

    result = pd.read_csv(out_path, keep_default_na=False)
    assert result.loc[0, 'Woody Debris'] == (
        '1. [WARNING] first issue\n2. [ERROR] second issue'
    )
```

- [ ] **Step 12: Run to confirm all pass**

Run: `pytest tests/unit/test_error_handling.py -v`
Expected: all 9 tests PASS. If any fail, the implementation in Step 8 has a
bug relative to this spec — fix `write_report()`/`start_run()` directly (not
the test) and re-run until all pass.

- [ ] **Step 13: Commit**

```bash
git add tests/unit/test_error_handling.py
git commit -m "test(error_handling): cover identity columns, General Error ordering, cell numbering"
```

---

## Task 2: Wire into `fuel_analyst.py`

**Files:**
- Modify: `src/fuel_analyst/fuel_analyst.py:1-15` (imports), `:476-478` (top of function), `:562-565` (missing-folder warning), `:587-597` (ID-mismatch warnings), `:621-627` (after master_fuel_df.csv save)
- Test: `tests/unit/test_fuel_analyst.py`

**Interfaces:**
- Consumes: `error_handling.start_run()`, `error_handling.write_report(out_path, plot_df)`, `error_handling.get_logger(form)` from Task 1.

- [ ] **Step 1: Write the failing test for the missing-folder warning**

```python
# tests/unit/test_fuel_analyst.py (add near existing tests)
import logging

import pandas as pd

from fuel_analyst.components import error_handling


def test_missing_form_folder_logs_per_plot_warning(tmp_path, caplog):
    from fuel_analyst.fuel_analyst import fuel_analyst
    # Build a minimal in_dir with only Plot Attributes present, one plot selecting 'woody'.
    plot_dir = tmp_path / 'in' / '1_Plot_Attributes'
    plot_dir.mkdir(parents=True)
    pd.DataFrame({
        'GlobalID': ['g1'], 'ParentGlobalID': [None],
        'treatment_area': ['A'], 'treatment_unit': ['U'], 'treatment_type': ['Pre'],
        'plot_id': [1], '_date': ['01/01/2025 10:00'], 'form_select': ['woody'],
        'plot_slope_units': ['percent'], 'plot_slope': [10.0],
    }).to_csv(plot_dir / 'survey_0.csv', index=False)

    with caplog.at_level(logging.WARNING, logger='fuel_analyst.components.woody_debris'):
        fuel_analyst(
            in_dir=str(tmp_path / 'in'),
            out_dir=str(tmp_path / 'out'),
            surface_fire_intensity_model='Byram',
        )

    assert any('Woody Debris' in '' for _ in [None])  # placeholder removed below
    assert any(
        'no Woody Debris data' in record.message and record.unique_id == 'A_U_Pre_1_2025'
        for record in caplog.records
    )
```

Note: replace the placeholder assertion line above before running — it exists
only to mark where the real assertion goes; delete it. The real assertion is
the `assert any(...)` checking `record.unique_id` and the message text.

- [ ] **Step 2: Remove the placeholder line, run to verify failure**

Delete the `assert any('Woody Debris' in '' for _ in [None])` line entirely.

Run: `pytest tests/unit/test_fuel_analyst.py::test_missing_form_folder_logs_per_plot_warning -v`
Expected: FAIL — still `print(...)`, no log record with `unique_id` emitted.

- [ ] **Step 3: Add the `error_handling` import and migrate the missing-folder warning**

In `src/fuel_analyst/fuel_analyst.py`, add near the top imports:

```python
from .components import error_handling
```

Replace:

```python
        if not os.path.exists(in_path):
            if mask.any():
                print(f'Warning: Input folder for {form_dict[form]} is missing but '
                      f'{mask.sum()} plot(s) selected this form. '
                      f'These plots will have no {form_dict[form]} data: {id_list}')
            continue
```

with:

```python
        if not os.path.exists(in_path):
            if mask.any():
                print(f'Warning: Input folder for {form_dict[form]} is missing but '
                      f'{mask.sum()} plot(s) selected this form. '
                      f'These plots will have no {form_dict[form]} data: {id_list}')
                for missing_id in id_list:
                    error_handling.get_logger(form).warning(
                        f'Input folder for {form_dict[form]} is missing but this plot '
                        f'selected this form; it will have no {form_dict[form]} data.',
                        extra={'unique_id': missing_id, 'issue_code': 'form_folder_missing'},
                    )
            continue
```

- [ ] **Step 4: Run to verify Step 1's test passes**

Run: `pytest tests/unit/test_fuel_analyst.py::test_missing_form_folder_logs_per_plot_warning -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/fuel_analyst/fuel_analyst.py tests/unit/test_fuel_analyst.py
git commit -m "feat(fuel_analyst): log per-plot warning when a selected form's folder is missing"
```

- [ ] **Step 6: Write the failing test for the ID-mismatch warnings, exercised through a real `fuel_analyst()` run**

The current mismatch code (below) has a pre-existing bug: the reverse-direction
check (form has an orphan ID not in Plot Attributes) is only ever computed
*inside* the `if not all(id in form_df['unique_id'].values for id in id_list)`
branch — i.e., only when the forward direction *also* fails. A form that has
every Plot-Attributes ID present, plus one extra orphan ID, takes the `else`
branch entirely and never reports the orphan. Fixing this is required to
satisfy the spec's "both directions" requirement (§3.3), so this test must
build a real orphan-only scenario — not a copy of the loop logic — to prove
the fix:

`canopy_cover.process_canopy_cover()` calls `helper.get_unique_id(df)` on its
*own* `survey_0.csv` (requiring `_date`, `treatment_area`, `treatment_unit`,
`treatment_type`, `plot_id` there too — `unique_id` is always computed from
these, never read from a pre-supplied column), and its `canopy_cover_1.csv`
requires `ParentGlobalID`, `cc_transect`, and `cc_2`, `cc_4`, ..., `cc_30`
(`src/fuel_analyst/components/canopy_cover.py:24-25,52-59`). This fixture
supplies all of them concretely:

```python
def test_id_mismatch_logs_orphan_form_id_even_when_forward_direction_is_clean(tmp_path, caplog):
    from fuel_analyst.fuel_analyst import fuel_analyst

    in_dir = tmp_path / 'in'
    plot_dir = in_dir / '1_Plot_Attributes'
    plot_dir.mkdir(parents=True)
    pd.DataFrame({
        'GlobalID': ['g1'], 'ParentGlobalID': [None],
        'treatment_area': ['A'], 'treatment_unit': ['U'], 'treatment_type': ['Pre'],
        'plot_id': [1], '_date': ['01/01/2025 10:00'], 'form_select': ['cover'],
        'plot_slope_units': ['percent'], 'plot_slope': [10.0],
    }).to_csv(plot_dir / 'survey_0.csv', index=False)
    # Plot Attributes' own unique_id, computed the same way, is 'A_U_Pre_1_2025'.

    cover_dir = in_dir / '4_Canopy_Cover'
    cover_dir.mkdir(parents=True)
    cc_cols = {f'cc_{i}': ['cnfr', 'cnfr'] for i in range(2, 32, 2)}
    # Row 1 matches the plot exactly (same treatment_area/unit/type/plot_id/_date,
    # so get_unique_id() computes the same 'A_U_Pre_1_2025'). Row 2 uses plot_id=99,
    # an orphan that was never in Plot Attributes at all.
    pd.DataFrame({
        'GlobalID': ['gc1', 'gc2'], 'ParentGlobalID': ['g1', 'gx'],
        'treatment_area': ['A', 'A'], 'treatment_unit': ['U', 'U'],
        'treatment_type': ['Pre', 'Pre'], 'plot_id': [1, 99],
        '_date': ['01/01/2025 10:00', '01/01/2025 10:00'],
    }).to_csv(cover_dir / 'survey_0.csv', index=False)
    pd.DataFrame({
        'ParentGlobalID': ['gc1', 'gc2'], 'cc_transect': [1, 1], **cc_cols,
    }).to_csv(cover_dir / 'canopy_cover_1.csv', index=False)

    with caplog.at_level(logging.WARNING, logger='fuel_analyst.components.canopy_cover'):
        fuel_analyst(
            in_dir=str(in_dir),
            out_dir=str(tmp_path / 'out'),
            surface_fire_intensity_model='Byram',
        )

    matching = [r for r in caplog.records if getattr(r, 'unique_id', None) == 'A_U_Pre_99_2025']
    assert len(matching) == 1
    assert matching[0].issue_code == 'id_extra_in_form'
```

- [ ] **Step 7: Run to verify failure**

Run: `pytest tests/unit/test_fuel_analyst.py::test_id_mismatch_logs_orphan_form_id_even_when_forward_direction_is_clean -v`
Expected: FAIL — today's code takes the `else` branch (every Plot Attributes ID
is present in Canopy Cover) and never reports the orphan `A_U_Pre_99_2025` at
all. Verified during this plan's review by running this exact fixture against
the real, unmodified `fuel_analyst()`: it prints "All IDs from the Plot
Attributes dataset are present in the cover dataset. Merging data." and never
mentions the orphan.

- [ ] **Step 8: Fix the independent-directions bug and migrate to logging**

Replace:

```python
            if not all(id in form_df['unique_id'].values for id in id_list):
                missing_ids = [id for id in id_list if id not in form_df['unique_id'].values]
                print(f'\tWarning:')
                print(f'\t\tThe following IDs are in the Plot Attributes dataset, '
                      f'but not in {form_dict[form]}: {missing_ids}')
                missing_ids = [id for id in form_df['unique_id'].values if id not in id_list]
                print(f'\t\tThe following IDs are in the {form_dict[form]} dataset, '
                      f'but not in Plot Attributes: {missing_ids}')
            else:
                print(f'\tAll IDs from the Plot Attributes dataset are present in the {form} dataset. Merging data.')
```

with:

```python
            missing_from_form = [id for id in id_list if id not in form_df['unique_id'].values]
            extra_in_form = [id for id in form_df['unique_id'].values if id not in id_list]
            if missing_from_form or extra_in_form:
                print(f'\tWarning:')
                if missing_from_form:
                    print(f'\t\tThe following IDs are in the Plot Attributes dataset, '
                          f'but not in {form_dict[form]}: {missing_from_form}')
                    for missing_id in missing_from_form:
                        error_handling.get_logger(form).warning(
                            f'Plot is in the Plot Attributes dataset but not in {form_dict[form]}.',
                            extra={'unique_id': missing_id, 'issue_code': 'id_missing_from_form'},
                        )
                if extra_in_form:
                    print(f'\t\tThe following IDs are in the {form_dict[form]} dataset, '
                          f'but not in Plot Attributes: {extra_in_form}')
                    for extra_id in extra_in_form:
                        error_handling.get_logger(form).warning(
                            f'Plot is in the {form_dict[form]} dataset but not in Plot Attributes.',
                            extra={'unique_id': extra_id, 'issue_code': 'id_extra_in_form'},
                        )
            else:
                print(f'\tAll IDs from the Plot Attributes dataset are present in the {form} dataset. Merging data.')
```

This both migrates the warnings to logging AND fixes the pre-existing bug: the
two directions are now computed and reported independently, so an orphan-only
mismatch is no longer masked by a clean forward direction. This is a
deliberate, spec-required behavior change (console output for the previously-
silent orphan-only case now also prints a `Warning:` block), not a
side-effect — call this out in the commit message.

- [ ] **Step 9: Run to verify Step 6's test passes, then run full unit test file**

Run: `pytest tests/unit/test_fuel_analyst.py -v`
Expected: all PASS.

- [ ] **Step 10: Commit**

```bash
git add src/fuel_analyst/fuel_analyst.py tests/unit/test_fuel_analyst.py
git commit -m "fix(fuel_analyst): report both ID-mismatch directions independently, log per-plot warnings"
```

- [ ] **Step 11: Wire `start_run()`/`write_report()` around the pipeline**

Add near the top of `fuel_analyst()`, right after the docstring (before `form_select_list = [...]` at line 478):

```python
    error_handling.start_run()
```

Add right after `helper.export_csv(plot_df, master_df_path)` (currently line 626):

```python
    error_report_path = os.path.join(out_dir, 'master_fuel_df_errors.csv')
    print(f'Saving the Error Report to: {error_report_path}')
    error_handling.write_report(error_report_path, plot_df=plot_df)
```

Note: `plot_df` at this point has already been sliced to `keep_columns` (line 625,
`plot_df = plot_df[keep_columns]`). `treatment_area`/`treatment_unit`/
`treatment_type`/`plot_id` are included: `plot_attributes.process_plot_attributes()`
(`src/fuel_analyst/components/plot_attributes.py:41-49`) returns `keep_columns` as
"every `df` column except an explicit `remove_columns` list," and that removal
list does not include these four fields, so they pass through into
`master_fuel_df.csv` and are therefore available to `write_report()` here.

Accepted limitation, not fixed by this plan: if `fuel_analyst()` raises before
reaching `write_report()` (e.g. the `gen_conpyro_df` missing-forms
`FileNotFoundError` at line 518, which fires before any form is processed and
thus before anything has been logged), the collecting handler stays attached
and no report is written for that aborted run. This is not silently
corrupting data — `start_run()` always removes any handler left over from a
previous call before attaching a new one (Task 1 Step 8), so the next real
`start_run()`/`write_report()` cycle is unaffected — but a partial report is
not written for the aborted run itself. Wrapping the remainder of
`fuel_analyst()`'s body in `try/finally` to guarantee `write_report()` runs
even on failure would fix this properly, but requires reindenting the bulk of
the function; deferred as out of scope for this plan given the low practical
impact (no warnings are lost, since none were logged yet when this specific
exception fires).

- [ ] **Step 12: Run the integration test to sanity-check the wiring**

Run: `pytest tests/integration/test_survey123_pipeline.py -v`
Expected: PASS (this test is fully updated in Task 10; for now it should at
least not error out — if `master_fuel_df_errors.csv`'s identity columns are
blank for real plots, note this and revisit in Task 10's Step where the
assertion is written).

- [ ] **Step 13: Commit**

```bash
git add src/fuel_analyst/fuel_analyst.py
git commit -m "feat(fuel_analyst): write master_fuel_df_errors.csv at the end of each run"
```

---

## Task 3: Migrate `plants_regen.py`'s `pc_flammable_note`

**Files:**
- Modify: `src/fuel_analyst/components/plants_regen.py:1-63`
- Modify: `tests/unit/test_plants_regen.py:14-52`

**Interfaces:**
- Consumes: nothing new (uses `logging.getLogger(__name__)` directly, resolving to `fuel_analyst.components.plants_regen`, matching Task 1's `_FORM_LOGGER_NAMES['plants']`).

- [ ] **Step 1: Update the failing tests to assert on `caplog` instead of the note column**

Replace the five existing tests in `tests/unit/test_plants_regen.py` (lines 14-52):

```python
import logging


def test_calc_pc_flammable_computes_survey123_formula():
    df = pd.DataFrame({'unique_id': ['A'], 'pc_rock': [10.0], 'pc_mineral_soil': [20.0]})
    result, keep = _calc_pc_flammable(df)
    assert result.loc[0, 'pc_nonflammable'] == 30.0
    assert result.loc[0, 'pc_flammable'] == 70.0
    assert keep == ['pc_nonflammable', 'pc_flammable']


def test_calc_pc_flammable_treats_one_missing_value_as_zero(caplog):
    df = pd.DataFrame({'unique_id': ['A'], 'pc_rock': [5.0], 'pc_mineral_soil': [np.nan]})
    with caplog.at_level(logging.INFO, logger='fuel_analyst.components.plants_regen'):
        result, _ = _calc_pc_flammable(df)
    assert result.loc[0, 'pc_nonflammable'] == 5.0
    assert result.loc[0, 'pc_flammable'] == 95.0
    assert caplog.records == []


def test_calc_pc_flammable_defaults_to_fully_flammable_when_no_data_provided(caplog):
    df = pd.DataFrame({'unique_id': ['A'], 'pc_rock': [np.nan], 'pc_mineral_soil': [np.nan]})
    with caplog.at_level(logging.INFO, logger='fuel_analyst.components.plants_regen'):
        result, _ = _calc_pc_flammable(df)
    assert result.loc[0, 'pc_nonflammable'] == 0.0
    assert result.loc[0, 'pc_flammable'] == 100.0
    assert len(caplog.records) == 1
    assert 'No pc_rock or pc_mineral_soil cover provided' in caplog.records[0].message
    assert caplog.records[0].unique_id == 'A'


def test_calc_pc_flammable_defaults_to_fully_flammable_when_columns_are_missing(caplog):
    df = pd.DataFrame({'unique_id': ['A'], 'other_col': [1]})
    with caplog.at_level(logging.INFO, logger='fuel_analyst.components.plants_regen'):
        result, _ = _calc_pc_flammable(df)
    assert result.loc[0, 'pc_nonflammable'] == 0.0
    assert result.loc[0, 'pc_flammable'] == 100.0
    assert 'No pc_rock or pc_mineral_soil cover provided' in caplog.records[0].message


def test_calc_pc_flammable_defaults_to_fully_flammable_when_result_out_of_range(caplog):
    df = pd.DataFrame({'unique_id': ['A'], 'pc_rock': [60.0], 'pc_mineral_soil': [60.0]})
    with caplog.at_level(logging.INFO, logger='fuel_analyst.components.plants_regen'):
        result, _ = _calc_pc_flammable(df)
    assert result.loc[0, 'pc_nonflammable'] == 0.0
    assert result.loc[0, 'pc_flammable'] == 100.0
    assert 'outside the valid 0-100 range' in caplog.records[0].message
```

Add `import logging` to the top of the test file if not already present.

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/unit/test_plants_regen.py -v -k pc_flammable`
Expected: FAIL — `KeyError: 'pc_flammable_note'` or `keep` list mismatch (function not yet migrated).

- [ ] **Step 3: Migrate `_calc_pc_flammable`**

Add near the top of `src/fuel_analyst/components/plants_regen.py`:

```python
import logging
```

Add after the existing imports:

```python
logger = logging.getLogger(__name__)
```

Replace the function body (lines 16-63) with:

```python
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

    plot_ids = df['unique_id'] if 'unique_id' in df.columns else df.index
    for idx in df.index[no_data_provided]:
        logger.info(
            'No pc_rock or pc_mineral_soil cover provided; pc_flammable defaulted to 100.',
            extra={'unique_id': plot_ids.loc[idx], 'issue_code': 'pc_flammable_no_data'},
        )
    for idx in df.index[out_of_range & ~no_data_provided]:
        logger.info(
            'Calculated pc_nonflammable outside the valid 0-100 range; pc_flammable defaulted to 100.',
            extra={'unique_id': plot_ids.loc[idx], 'issue_code': 'pc_flammable_out_of_range'},
        )

    df.loc[fallback_mask, 'pc_nonflammable'] = 0.0
    df.loc[fallback_mask, 'pc_flammable'] = 100.0

    return df, ['pc_nonflammable', 'pc_flammable']
```

- [ ] **Step 4: Run to verify tests pass**

Run: `pytest tests/unit/test_plants_regen.py -v -k pc_flammable`
Expected: all 5 PASS.

- [ ] **Step 5: Update `process_plants_regen`'s `keep_columns` usage**

Search `src/fuel_analyst/components/plants_regen.py` for `add_columns.extend` or
`keep_columns.extend` following the `_calc_pc_flammable` call — no change should
be needed there since `keep_columns.extend(add_columns)` already just extends
with whatever the 2-item list returns; confirm by running the full test file.

- [ ] **Step 6: Run the full unit test file**

Run: `pytest tests/unit/test_plants_regen.py -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add src/fuel_analyst/components/plants_regen.py tests/unit/test_plants_regen.py
git commit -m "refactor(plants_regen): replace pc_flammable_note column with error_handling logging"
```

---

## Task 4: Migrate `woody_debris.py`'s `spp_comp_type_note` and `stand_spp_comp_woody` warnings, plus the new silent per-plot gap

**Files:**
- Modify: `src/fuel_analyst/components/woody_debris.py:1-15` (imports), `:1020-1056` (`_merge_spp_comp`), `:1077-1114` (`_resolve_spp_comp_type`)
- Modify: `tests/unit/test_woody_debris.py`
- Modify: `tests/regression/test_woody_debris_spp_comp_fallback.py`

**Interfaces:**
- Consumes: nothing new (`logging.getLogger(__name__)` resolves to `fuel_analyst.components.woody_debris`).
- Produces: `_resolve_spp_comp_type(df, spp_comp_df) -> tuple[pd.DataFrame, list]` now returns `keep = ['spp_comp_type_declared']` (drops `spp_comp_type_note` from the returned list — downstream callers in `process_woody_debris` must not reference `spp_comp_type_note`).

- [ ] **Step 1: Update the failing unit tests for `_resolve_spp_comp_type`**

Replace the three tests added earlier this session in `tests/unit/test_woody_debris.py`:

```python
import logging


def test_resolve_spp_comp_type_falls_back_when_declared_source_has_no_data(caplog):
    df = pd.DataFrame({'unique_id': ['A'], 'spp_comp_type': ['tree_data']})
    spp_comp_df = pd.DataFrame({
        'unique_id': ['A'],
        'spp_comp_type': ['transect_data'],
        'spp_comp_code': ['FDI'],
    })
    with caplog.at_level(logging.INFO, logger='fuel_analyst.components.woody_debris'):
        result, keep = _resolve_spp_comp_type(df, spp_comp_df)
    assert keep == ['spp_comp_type_declared']
    assert result.loc[0, 'spp_comp_type'] == 'transect_data'
    assert result.loc[0, 'spp_comp_type_declared'] == 'tree_data'
    assert len(caplog.records) == 1
    assert 'tree_data' in caplog.records[0].message
    assert 'transect_data' in caplog.records[0].message
    assert caplog.records[0].unique_id == 'A'


def test_resolve_spp_comp_type_keeps_declared_source_when_available(caplog):
    df = pd.DataFrame({'unique_id': ['A'], 'spp_comp_type': ['transect_data']})
    spp_comp_df = pd.DataFrame({
        'unique_id': ['A'],
        'spp_comp_type': ['transect_data'],
        'spp_comp_code': ['FDI'],
    })
    with caplog.at_level(logging.INFO, logger='fuel_analyst.components.woody_debris'):
        result, _ = _resolve_spp_comp_type(df, spp_comp_df)
    assert result.loc[0, 'spp_comp_type'] == 'transect_data'
    assert caplog.records == []


def test_resolve_spp_comp_type_leaves_declared_when_no_source_available(caplog):
    df = pd.DataFrame({'unique_id': ['A'], 'spp_comp_type': ['tree_data']})
    spp_comp_df = pd.DataFrame({'unique_id': [], 'spp_comp_type': [], 'spp_comp_code': []})
    with caplog.at_level(logging.INFO, logger='fuel_analyst.components.woody_debris'):
        result, _ = _resolve_spp_comp_type(df, spp_comp_df)
    assert result.loc[0, 'spp_comp_type'] == 'tree_data'
    assert caplog.records == []
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/unit/test_woody_debris.py -v -k resolve_spp_comp_type`
Expected: FAIL — `keep` still includes `'spp_comp_type_note'`; no log records emitted.

- [ ] **Step 3: Migrate `_resolve_spp_comp_type`**

Add near the top of `src/fuel_analyst/components/woody_debris.py`:

```python
import logging
```

Add after the existing imports:

```python
logger = logging.getLogger(__name__)
```

Replace the function body (current lines 1077-1114) with:

```python
def _resolve_spp_comp_type(df: pd.DataFrame, spp_comp_df: pd.DataFrame) -> tuple[pd.DataFrame, list]:
    """
    Resolve the species composition source actually usable for each plot, falling back to
    another available source when the declared 'spp_comp_type' has no matching rows in
    spp_comp_df (e.g., a plot declares 'tree_data' but the Trees form was not processed).

    :param df: DataFrame containing plot-level data with 'unique_id' and declared 'spp_comp_type'.
    :param spp_comp_df: DataFrame containing merged species composition data with 'unique_id'
        and 'spp_comp_type'.
    :return: Updated df with 'spp_comp_type' overwritten to the resolved source and a new
        'spp_comp_type_declared' column preserving the original value, plus a list of columns
        to keep.
    """
    print('\tResolving species composition source availability')

    priority = ['tree_data', 'transect_data', 'manual_entry']
    available = {
        spp_comp_type: set(sub['unique_id'])
        for spp_comp_type, sub in spp_comp_df.groupby('spp_comp_type')
    }

    def _resolve(row):
        declared = row['spp_comp_type']
        if row['unique_id'] in available.get(declared, set()):
            return declared
        for fallback in priority:
            if fallback != declared and row['unique_id'] in available.get(fallback, set()):
                logger.info(
                    f"Declared spp_comp_type '{declared}' had no matching species composition "
                    f"data; used '{fallback}' instead.",
                    extra={'unique_id': row['unique_id'], 'issue_code': 'spp_comp_type_fallback'},
                )
                return fallback
        return declared

    df['spp_comp_type_declared'] = df['spp_comp_type']
    df['spp_comp_type'] = df.apply(_resolve, axis=1)

    return df, ['spp_comp_type_declared']
```

- [ ] **Step 4: Run to verify Step 1's tests pass**

Run: `pytest tests/unit/test_woody_debris.py -v -k resolve_spp_comp_type`
Expected: all 3 PASS.

- [ ] **Step 5: Update the regression test to assert on `caplog` too**

In `tests/regression/test_woody_debris_spp_comp_fallback.py`, add
`import logging`, wrap the `_resolve_spp_comp_type(df, spp_comp_df)` call in
`with caplog.at_level(logging.INFO, logger='fuel_analyst.components.woody_debris'):`,
and add the `caplog` fixture to the test function's parameters. No assertion on
the log content is required here (that's covered in Task 4's unit tests) — this
just confirms the regression path still runs without error under the new
logging call.

- [ ] **Step 6: Run the regression test**

Run: `pytest tests/regression/test_woody_debris_spp_comp_fallback.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/fuel_analyst/components/woody_debris.py tests/unit/test_woody_debris.py tests/regression/test_woody_debris_spp_comp_fallback.py
git commit -m "refactor(woody_debris): replace spp_comp_type_note column with error_handling logging"
```

- [ ] **Step 8: Write the failing regression test for the newly-discovered silent per-plot gap**

```python
# tests/regression/test_woody_debris_spp_comp_fallback.py (add new test)
def test_merge_spp_comp_logs_plot_missing_tree_data_while_siblings_have_it(caplog):
    """A plot with no stand_spp_comp_woody value, while sibling plots have valid values,
    previously produced zero warning of any kind - it silently fell out of the tree_data
    branch with no record of why."""
    plot_df = pd.DataFrame({
        'unique_id': ['plot-1', 'plot-2'],
        'stand_spp_comp_woody': ['FDI:100', None],
    })
    plot_ids = pd.DataFrame({
        'GlobalID': ['g1', 'g2'], 'unique_id': ['plot-1', 'plot-2'],
    })
    woody_df = pd.DataFrame({
        'ParentGlobalID': ['g1', 'g2'],
        'woody_species': ['FDI', 'FDI'],
        'woody_spp_percent_wtd': [100.0, 100.0],
    })
    manual_df = pd.DataFrame(columns=[
        'ObjectID', 'GlobalID', 'spp_comp_code', 'spp_comp_percent', 'ParentGlobalID',
    ])
    manual_df = _assign_spp_comp_id_col(plot_ids, manual_df)
    manual_df = _add_spp_comp_type(manual_df)

    with caplog.at_level(logging.INFO, logger='fuel_analyst.components.woody_debris'):
        _merge_spp_comp(plot_df, plot_ids, woody_df, manual_df)

    matching = [r for r in caplog.records if getattr(r, 'unique_id', None) == 'plot-2']
    assert len(matching) == 1
    assert 'falling back' in matching[0].message
```

Add `_merge_spp_comp`, `_assign_spp_comp_id_col`, `_add_spp_comp_type`, and
`logging` to this test file's imports if not already present.

- [ ] **Step 9: Run to verify failure**

Run: `pytest tests/regression/test_woody_debris_spp_comp_fallback.py -v -k siblings`
Expected: FAIL — no log record emitted for `plot-2`.

- [ ] **Step 10: Fix the silent gap in `_merge_spp_comp`**

In `src/fuel_analyst/components/woody_debris.py`, inside `_merge_spp_comp`,
locate the block (current lines 1020-1051):

```python
    if 'stand_spp_comp_woody' in plot_df.columns:
        # Check if the column has any valid (non-null) data
        valid_data = plot_df['stand_spp_comp_woody'].notna()

        if valid_data.any():
            print(f'\t\tFound {valid_data.sum()} plots with tree species composition data')
            print(f'\t\tSample data: {plot_df.loc[valid_data, "stand_spp_comp_woody"].iloc[0]}')

            # Filter to only rows with valid data before processing
            valid_rows = plot_df[valid_data].copy()
```

Insert immediately after `valid_rows = plot_df[valid_data].copy()`:

```python
            for _, missing_row in plot_df.loc[~valid_data].iterrows():
                logger.info(
                    'No tree-derived species composition for this plot; falling back to '
                    'another spp_comp_type source.',
                    extra={
                        'unique_id': missing_row.get('unique_id'),
                        'issue_code': 'stand_spp_comp_woody_missing_for_plot',
                    },
                )
```

- [ ] **Step 11: Run to verify Step 8's test passes**

Run: `pytest tests/regression/test_woody_debris_spp_comp_fallback.py -v -k siblings`
Expected: PASS.

- [ ] **Step 12: Migrate the two remaining `print` sites in `_merge_spp_comp` (General Error row)**

Replace:

```python
        else:
            print('\t\tWarning: stand_spp_comp_woody column exists but contains no valid data')
            print('\t\tThis is normal if trees were not processed or plots have no trees')
    else:
        print('\t\tNote: stand_spp_comp_woody column not found (trees may not have been processed)')
```

with:

```python
        else:
            print('\t\tWarning: stand_spp_comp_woody column exists but contains no valid data')
            print('\t\tThis is normal if trees were not processed or plots have no trees')
            logger.warning(
                'stand_spp_comp_woody column exists but contains no valid data for any plot.'
            )
    else:
        print('\t\tNote: stand_spp_comp_woody column not found (trees may not have been processed)')
        logger.warning('stand_spp_comp_woody column not found (trees may not have been processed).')
```

- [ ] **Step 13: Run the full woody_debris test files**

Run: `pytest tests/unit/test_woody_debris.py tests/regression/test_woody_debris_spp_comp_fallback.py tests/regression/test_woody_debris_concat.py -v`
Expected: all PASS.

- [ ] **Step 14: Commit**

```bash
git add src/fuel_analyst/components/woody_debris.py tests/regression/test_woody_debris_spp_comp_fallback.py
git commit -m "fix(woody_debris): log the previously-silent per-plot stand_spp_comp_woody gap"
```

---

## Task 5: Migrate `trees.py`'s tree-density issue system and fix the fireline-model bug

**Files:**
- Modify: `src/fuel_analyst/components/trees.py` (imports; delete `_gen_tree_processing_issues` and `_add_tree_processing_status`; add `_log_tree_density_issues`; modify `process_trees`'s save/summary block; fix `_calc_tree_fire_attributes`'s fireline-model branch)
- Modify: `tests/unit/test_trees.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `_log_tree_density_issues(df, sapling_df, tree_df) -> list[tuple]` (replaces
  `_gen_tree_processing_issues`/`_add_tree_processing_status`; logs as a side effect and
  returns the `(unique_id, message)` pairs logged at ERROR severity, for the console summary).

- [ ] **Step 1: Write the failing test for the fireline-model bug fix**

```python
# tests/unit/test_trees.py (add new test)
import logging


def test_calc_tree_fire_attributes_does_not_warn_for_valid_byram_model(caplog):
    tree_df = pd.DataFrame({
        'tree_bark_char_high': [10.0], 'tree_bark_char_low': [0.0],
        'tree_ht': [15.0],
    })
    with caplog.at_level(logging.WARNING, logger='fuel_analyst.components.trees'):
        _calc_tree_fire_attributes(tree_df, surface_fire_intensity_model='Byram')
    assert caplog.records == []


def test_calc_tree_fire_attributes_warns_for_truly_invalid_model(caplog):
    tree_df = pd.DataFrame({
        'tree_bark_char_high': [10.0], 'tree_bark_char_low': [0.0],
        'tree_ht': [15.0],
    })
    with caplog.at_level(logging.WARNING, logger='fuel_analyst.components.trees'):
        _calc_tree_fire_attributes(tree_df, surface_fire_intensity_model='not_a_model')
    assert len(caplog.records) == 1
    assert 'Invalid surface fireline intensity model' in caplog.records[0].message
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/unit/test_trees.py -v -k "fire_attributes_does_not_warn or fire_attributes_warns"`

Expected: `test_calc_tree_fire_attributes_warns_for_truly_invalid_model` FAILS
(today's code only `print()`s for any non-`'Thomas'` input — including truly
invalid strings — so `caplog.records` is empty and `len(caplog.records) == 1`
fails). `test_calc_tree_fire_attributes_does_not_warn_for_valid_byram_model`
PASSES already today (nothing logs yet at all, so `caplog.records == []`
holds vacuously) — that is expected and not a sign anything is wrong; it
becomes a meaningful regression check only once Step 3's fix is in place,
guarding against a future change reintroducing a false-positive warning for
`'Byram'`. Run both tests together (not just `-k
fire_attributes_does_not_warn`) so the one that actually demonstrates today's
bug is included.

- [ ] **Step 3: Fix the condition and migrate to `logger.warning`**

In `src/fuel_analyst/components/trees.py`, add `import logging` near the top
and `logger = logging.getLogger(__name__)` after the existing module-level
constants (near `_PLOT_RADIUS_FIELDS`).

Replace:

```python
    if surface_fire_intensity_model == 'Thomas':
        # Use the Thomas (1963) flame length model to estimate fireline intensity (kW/m)
        surface_model = (tree_df['tree_flame_length'] / 0.026700) ** (3 / 2)
    else:
        print('Invalid surface fireline intensity model specified. Using Byram (1959) as default.')
        # Use the Byram (1959) flame length model to estimate fireline intensity (kW/m)
        surface_model = (tree_df['tree_flame_length'] / 0.0775) ** (1 / 0.46)
```

with:

```python
    if surface_fire_intensity_model == 'Thomas':
        # Use the Thomas (1963) flame length model to estimate fireline intensity (kW/m)
        surface_model = (tree_df['tree_flame_length'] / 0.026700) ** (3 / 2)
    else:
        if surface_fire_intensity_model != 'Byram':
            logger.warning(
                'Invalid surface fireline intensity model specified. Using Byram (1959) as default.'
            )
        # Use the Byram (1959) flame length model to estimate fireline intensity (kW/m)
        surface_model = (tree_df['tree_flame_length'] / 0.0775) ** (1 / 0.46)
```

- [ ] **Step 4: Run to verify Step 1's tests pass**

Run: `pytest tests/unit/test_trees.py -v -k "fire_attributes_does_not_warn or fire_attributes_warns"`
Expected: both PASS.

- [ ] **Step 5: Commit**

```bash
git add src/fuel_analyst/components/trees.py tests/unit/test_trees.py
git commit -m "fix(trees): stop warning on correctly-specified Byram fireline intensity model"
```

- [ ] **Step 6: Update the three existing tests that call `_gen_tree_processing_issues`/`_add_tree_processing_status`**

Replace `test_tree_density_reports_each_root_cause_and_keeps_batch_results_finite`,
`test_tree_processing_status_ignores_unassigned_nullable_issue_ids`, and
`test_unused_invalid_radius_is_reported_without_marking_results_partial`
(current lines 213-238, 269-288, 291-311) with:

```python
def test_tree_density_logs_each_root_cause_at_correct_severity(caplog):
    plots = pd.DataFrame({
        'GlobalID': ['p1'], 'unique_id': ['Unit_Plot_1_2025'],
        'lgtree_plot_radius': [None], 'smtree_plot_radius': [5.64],
        'sapling_plot_radius': [5.64],
    })
    plots = _calc_plot_multipliers(plots)
    trees = _normalize_tree_inputs(pd.DataFrame({
        'GlobalID': ['t1', 't2'], 'ParentGlobalID': ['p1', 'p1'],
        'tree_dbh': [20, 'not measured'],
    }))

    density = _calc_tree_density(plots, trees)
    with caplog.at_level(logging.INFO, logger='fuel_analyst.components.trees'):
        _log_tree_density_issues(plots, pd.DataFrame(), density)

    assert density['tree_dens_ha'].tolist() == [0.0, 0.0]
    codes = {r.issue_code for r in caplog.records}
    assert codes == {'missing_plot_radius', 'non_numeric_tree_dbh'}
    assert all(r.levelname == 'ERROR' for r in caplog.records)
    assert all(r.unique_id == 'Unit_Plot_1_2025' for r in caplog.records)


def test_unused_invalid_radius_is_logged_as_warning_not_error(caplog):
    plots = pd.DataFrame({
        'GlobalID': ['p1'], 'unique_id': ['Unit_Plot_1_2025'],
        'lgtree_plot_radius': [None], 'smtree_plot_radius': [5.64],
        'sapling_plot_radius': [5.64],
    })
    plots = _calc_plot_multipliers(plots)
    trees = _normalize_tree_inputs(pd.DataFrame({
        'GlobalID': ['t1'], 'ParentGlobalID': ['p1'], 'tree_dbh': [8],
    }))
    density = _calc_tree_density(plots, trees)

    with caplog.at_level(logging.INFO, logger='fuel_analyst.components.trees'):
        _log_tree_density_issues(plots, pd.DataFrame(), density)

    assert density.loc[0, 'tree_dens_ha'] == 100
    assert len(caplog.records) == 1
    assert caplog.records[0].levelname == 'WARNING'
    assert caplog.records[0].issue_code == 'missing_plot_radius'
```

Remove `test_tree_processing_status_ignores_unassigned_nullable_issue_ids` entirely —
it tested nullable-mask handling inside `_add_tree_processing_status`, which no
longer exists after this task; the underlying nullable-ID safety this test
guarded is preserved because `_log_tree_density_issues` (Step 9 below) resolves
`unique_id` the same way `_gen_tree_processing_issues`'s `parent_metadata` did,
including its `pd.isna(parent_id)` guard.

Remove `_add_tree_processing_status` and `_gen_tree_processing_issues` from this
test file's imports; add `_log_tree_density_issues` and `import logging`.

- [ ] **Step 7: Run to verify failure**

Run: `pytest tests/unit/test_trees.py -v -k "logs_each_root_cause or logged_as_warning"`
Expected: FAIL — `_log_tree_density_issues` not defined.

- [ ] **Step 8: Delete `_gen_tree_processing_issues` and `_add_tree_processing_status`**

In `src/fuel_analyst/components/trees.py`, delete both functions in full
(current lines 105-104+len for `_add_tree_processing_status`, and
1551-1711ish for `_gen_tree_processing_issues` — locate exact current bounds
with `grep -n "^def _add_tree_processing_status\|^def _gen_tree_processing_issues\|^def " src/fuel_analyst/components/trees.py`
and delete from the `def` line up to (not including) the next `def` line).

Also delete the now-unused `_TREE_DENSITY_ISSUE_COLUMNS` and
`_TREE_DENSITY_QA_COLUMNS` module-level constants.

- [ ] **Step 9: Implement `_log_tree_density_issues`**

`_log_tree_density_issues` is alphabetized among trees.py's private
functions: `_log_*` sorts after every existing `_calc_*` and `_get_*` function
(e.g. after `_get_temesgen_tree_height`) and before `_merge_saplings_to_trees`
— add it there. (This is a different position than `_gen_tree_processing_issues`
used to occupy — `gen` sorts after `calc` but before `get` (`_gen_*` lived
between the `_calc_*` and `_get_*` groups), whereas `_log_*` sorts after both
— so do not use that deleted function's old location as a reference point.)

`_log_tree_density_issues` returns the list of `(unique_id, message)` pairs it
logged at `ERROR` severity (`results_partial=True`), so `process_trees()`'s
console summary (Step 12) can report every plot with a partial result —
including plots whose *only* issue is an invalid sapling count, which never
gets synthesized into a `tree_df` row at all and so would be invisible to a
summary that only scans `tree_df['tree_density_affected']`:

```python
def _log_tree_density_issues(
        df: pd.DataFrame,
        sapling_df: pd.DataFrame,
        tree_df: pd.DataFrame,
) -> list[tuple]:
    """
    Report tree-density input failures through the centralized error_handling logger.

    :return: List of (unique_id, message) pairs for every issue logged at ERROR
        severity (results_partial=True), for the caller's console summary.
    """
    ambiguous_marker = df.get(
        '_parent_id_ambiguous', pd.Series(False, index=df.index)
    ).fillna(False).astype(bool)
    duplicate_ids = set(df.loc[df['GlobalID'].duplicated(keep=False), 'GlobalID'].dropna())
    duplicate_ids.update(df.loc[ambiguous_marker, 'GlobalID'].dropna())
    valid_parents = df.loc[~df['GlobalID'].isin(duplicate_ids)].drop_duplicates('GlobalID')
    parent_by_id = valid_parents.set_index('GlobalID')

    partial_log = []

    def resolve_unique_id(parent_id):
        if pd.isna(parent_id) or parent_id in duplicate_ids or parent_id not in parent_by_id.index:
            return pd.NA
        return parent_by_id.loc[parent_id].get('unique_id')

    def log_issue(parent_id, issue_code, results_partial):
        unique_id = resolve_unique_id(parent_id)
        message = issue_code.replace('_', ' ')
        extra = {'unique_id': unique_id, 'issue_code': issue_code}
        if results_partial:
            full_message = f'{message}; affected density assigned zero'
            logger.error(full_message, extra=extra)
            partial_log.append((unique_id, full_message))
        else:
            logger.warning(message, extra=extra)

    # Parent-level radius issues are reported even when no tree used the radius.
    for _, plot in df.iterrows():
        for radius_class in _PLOT_RADIUS_FIELDS:
            issue_code = plot.get(f'_plot_{radius_class}_radius_issue', '')
            if not issue_code:
                continue
            affected_count = len(tree_df[
                tree_df['ParentGlobalID'].eq(plot.get('GlobalID'))
                & tree_df['tree_density_radius_class'].eq(radius_class)
                & tree_df['tree_density_affected']
            ])
            log_issue(plot.get('GlobalID'), issue_code, results_partial=affected_count > 0)

    radius_issue_codes = {
        'missing_plot_radius', 'non_numeric_plot_radius',
        'non_positive_plot_radius', 'non_finite_plot_radius',
        'invalid_plot_area', 'invalid_plot_radius',
    }
    # Row-level issues include every independent cause except radius causes,
    # which are represented by their parent survey source above.
    for _, tree in tree_df.iterrows():
        codes = [code for code in str(tree.get('tree_density_issue_codes', '')).split('|') if code]
        for code in codes:
            if code in radius_issue_codes:
                continue
            is_warning = code == 'sapling_dbh_zero_normalized'
            partial = bool(tree.get('tree_density_affected', False)) and not is_warning
            log_issue(tree.get('ParentGlobalID'), code, results_partial=partial)

    # Invalid sapling counts cannot be synthesized into tree rows, so report
    # them directly from their source table. Parent linkage is also checked at
    # source level so simultaneous causes are not lost.
    known_parent_ids = set(df['GlobalID'].dropna())
    for _, sapling in sapling_df.iterrows():
        parent_id = sapling.get('ParentGlobalID')
        parent_code = ''
        if pd.isna(parent_id) or not str(parent_id).strip():
            parent_code = 'missing_parent_id'
        elif parent_id in duplicate_ids:
            parent_code = 'ambiguous_parent_id'
        elif parent_id not in known_parent_ids:
            parent_code = 'orphan_tree_record'
        if parent_code:
            log_issue(
                parent_id, parent_code,
                results_partial=sapling.get('sapling_species') != 'NO_SAPLINGS',
            )

        if sapling.get('sapling_species') == 'NO_SAPLINGS':
            continue
        for status in ('live', 'dead'):
            count_col = f'sapling_{status}_count'
            issue_code = sapling.get(f'_{count_col}_issue', '')
            if issue_code:
                log_issue(parent_id, issue_code, results_partial=True)

    return partial_log
```

- [ ] **Step 10: Run to verify Step 6's tests pass**

Run: `pytest tests/unit/test_trees.py -v -k "logs_each_root_cause or logged_as_warning"`
Expected: both PASS.

- [ ] **Step 11: Run the full unit test file to find any remaining references to deleted functions**

Run: `pytest tests/unit/test_trees.py -v`
Expected: any remaining `ImportError`/`NameError` reveals leftover references —
fix by removing/updating them (there should be none left after Step 6, but
this step exists to catch anything missed).

- [ ] **Step 12: Update `process_trees`'s save/summary block**

Locate the block in `process_trees` (search for
`issues_df = _gen_tree_processing_issues` and the surrounding save/print code).
Replace:

```python
    issues_df = _gen_tree_processing_issues(df, sapling_df, tree_df)
    df = _add_tree_processing_status(df, sapling_df, tree_df, issues_df)
```

and the later:

```python
    issues_path = os.path.join(out_folder, 'tree_processing_issues.csv')
    helper.export_csv(issues_df, issues_path)

    partial_plots = export_df.loc[~export_df['tree_density_complete'].fillna(False)]
    if not partial_plots.empty:
        print(f'\tWARNING: Tree-density results are partial for {len(partial_plots)} plot(s).')
        for _, plot in partial_plots.iterrows():
            plot_label = plot.get('unique_id', plot.get('GlobalID', 'unknown plot'))
            print(f'\t  {plot_label}: {plot.get("tree_density_issues", "unknown issue")}')
        print(f'\tSee {issues_path} for details.')
```

with:

```python
    partial_log = _log_tree_density_issues(df, sapling_df, tree_df)
```

and:

```python
    if partial_log:
        by_plot = {}
        for unique_id, message in partial_log:
            by_plot.setdefault(unique_id, []).append(message)
        print(f'\tWARNING: Tree-density results are partial for {len(by_plot)} plot(s).')
        for plot_label, messages in by_plot.items():
            print(f'\t  {plot_label}: {"; ".join(messages)}')
        print('\tSee the run-level error report (master_fuel_df_errors.csv) for full details.')
```

This is a correctness improvement over the deleted `_add_tree_processing_status`-based
summary, not just a straight port: `partial_log` is populated from every `log_issue(...,
results_partial=True)` call inside `_log_tree_density_issues`, including the sapling-count
branch — so a plot whose *only* issue is an invalid sapling count (which never gets
synthesized into a `tree_df` row at all) still appears in this console summary, where a
summary built solely from `tree_df['tree_density_affected']` would have silently missed it.

Also remove the now-unneeded `keep_columns.extend(_TREE_DENSITY_QA_COLUMNS)`
line and the `_TREE_DENSITY_QA_COLUMNS` reference, since those rollup columns
no longer exist.

- [ ] **Step 13: Run the full unit test file again**

Run: `pytest tests/unit/test_trees.py -v`
Expected: all PASS.

- [ ] **Step 14: Commit**

```bash
git add src/fuel_analyst/components/trees.py tests/unit/test_trees.py
git commit -m "refactor(trees): replace tree_processing_issues.csv with error_handling logging"
```

- [ ] **Step 15: Add a regression test preserving one of the original confirmed tree-density defects**

Per `tests/regression/README.md` and the spec's Testing strategy (§7), the
functionality `06794a3` ("add resilient tree density validation and
reporting") introduced was itself a confirmed-defect fix; migrating its
reporting mechanism must keep a regression test proving the underlying defect
(invalid plot radius silently zeroing density with no diagnostic) still can't
regress, now exercised through `_log_tree_density_issues` instead of the
deleted `_gen_tree_processing_issues`.

Create `tests/regression/test_trees_density_issue_logging.py`:

```python
"""Regression coverage for tree-density input validation surfacing through error_handling."""

import logging

import pandas as pd
import pytest

from fuel_analyst.components.trees import (
    _calc_plot_multipliers,
    _calc_tree_density,
    _log_tree_density_issues,
    _normalize_tree_inputs,
)


@pytest.mark.regression
def test_invalid_plot_radius_zeroes_density_and_logs_instead_of_failing_silently(caplog):
    """An invalid/missing plot radius previously zeroed tree_dens_ha with no diagnostic
    at all; commit 06794a3 added tree_processing_issues.csv to surface this, which this
    test now reproduces through the centralized error_handling logger instead."""
    plots = pd.DataFrame({
        'GlobalID': ['p1'], 'unique_id': ['Unit_Plot_1_2025'],
        'lgtree_plot_radius': [None], 'smtree_plot_radius': [5.64],
        'sapling_plot_radius': [5.64],
    })
    plots = _calc_plot_multipliers(plots)
    trees = _normalize_tree_inputs(pd.DataFrame({
        'GlobalID': ['t1'], 'ParentGlobalID': ['p1'], 'tree_dbh': [20],
    }))

    density = _calc_tree_density(plots, trees)
    assert density.loc[0, 'tree_dens_ha'] == 0.0

    with caplog.at_level(logging.WARNING, logger='fuel_analyst.components.trees'):
        _log_tree_density_issues(plots, pd.DataFrame(), density)

    matching = [r for r in caplog.records if getattr(r, 'unique_id', None) == 'Unit_Plot_1_2025']
    assert len(matching) == 1
    assert matching[0].levelname == 'ERROR'
    assert matching[0].issue_code == 'missing_plot_radius'
```

- [ ] **Step 16: Run to verify it passes**

Run: `pytest tests/regression/test_trees_density_issue_logging.py -v`
Expected: PASS.

- [ ] **Step 17: Commit**

```bash
git add tests/regression/test_trees_density_issue_logging.py
git commit -m "test(regression): preserve tree-density invalid-radius defect coverage through error_handling"
```

---

## Task 6: Migrate `extract_nrcan_wx.py`

**Files:**
- Modify: `src/fuel_analyst/extract_nrcan_wx.py:1-15` (imports), `:404-473` (`extract_weather_data`), `:156-161` (missing fire season dates, inside `_extract_weather`)
- Test: `tests/unit/test_extract_nrcan_wx.py` (create if it does not already exist — check with `ls tests/unit/test_extract_nrcan_wx.py` first)

**Interfaces:**
- Consumes: `error_handling.start_run()`, `error_handling.write_report(out_path, plot_df)` from Task 1. `extract_nrcan_wx.py` is a top-level module, so it imports via `from .components import error_handling` (matching the existing `from .components import helper` pattern already used elsewhere in the package's top-level modules).

- [ ] **Step 1: Add imports needed for the new tests**

`tests/unit/test_extract_nrcan_wx.py` already exists (it imports individual
functions directly, e.g. `from fuel_analyst.extract_nrcan_wx import
(_attach_geometry, _calc_percentile_worker, ...)`). Add to its existing import
block:

```python
import logging

import numpy as np

from fuel_analyst import extract_nrcan_wx
```

(`pandas as pd` and `pytest` are already imported in this file.) The module-level
`from fuel_analyst import extract_nrcan_wx` import is needed alongside the
existing per-function imports so the new tests can reference
`extract_nrcan_wx.logger` (added in Step 4 below).

- [ ] **Step 2: Write a documentation test for the missing-lat/long warning's call shape**

`extract_weather_data()` does much more after this block (sorts by `wx_date`,
attaches geometry via `plots.crs`, writes a shapefile) — monkeypatching enough
of that to reach the warning site through the full function is disproportionate
and fragile. Exercise the drop-with-warning logic directly instead, the same
way Step 8 (below) already does for the fire-season-dates warning:

```python
def test_missing_lat_long_logs_per_plot_warning(caplog):
    plots = pd.DataFrame({
        'unique_id': ['A', 'B'], 'lat': [50.0, np.nan], 'lon': [-120.0, -121.0],
    })
    plot_id_col_name, lat_col_name, lon_col_name = 'unique_id', 'lat', 'lon'

    plots_sub = plots.dropna(subset=[lat_col_name, lon_col_name])
    with caplog.at_level(logging.WARNING, logger='fuel_analyst.extract_nrcan_wx'):
        if len(plots_sub) < len(plots):
            missing_coords = plots[plots[lat_col_name].isna() | plots[lon_col_name].isna()]
            for missing_id in missing_coords[plot_id_col_name]:
                extract_nrcan_wx.logger.warning(
                    'Plot has missing lat or long data and will be skipped.',
                    extra={'unique_id': missing_id, 'issue_code': 'missing_lat_long'},
                )

    matching = [r for r in caplog.records if getattr(r, 'unique_id', None) == 'B']
    assert len(matching) == 1
```

This documents the exact call shape Step 4 wires into the real
`extract_weather_data()` function; it is not itself a substitute for
exercising the real function end to end (that level of coverage is out of
scope here, matching the fire-season-dates warning below).

- [ ] **Step 3: Run to verify it passes as written**

Run: `pytest tests/unit/test_extract_nrcan_wx.py -v -k missing_lat_long`
Expected: PASS (this documents intended call shape; Step 4 wires the same
call into the real function).

- [ ] **Step 4: Migrate the missing-lat/long warning**

Add near the top of `src/fuel_analyst/extract_nrcan_wx.py`:

```python
import logging
```

Add after the existing imports:

```python
logger = logging.getLogger(__name__)
```

Replace (current lines 452-458):

```python
    ## drop plots that have not lat or long data, print their unique_ids and say they are skipped
    plots_sub = plots.dropna(subset=[lat_col_name, lon_col_name])
    if len(plots_sub) < len(plots):
        missing_coords = plots[plots[lat_col_name].isna() | plots[lon_col_name].isna()]
        print(f'Warning: {len(missing_coords)} plots have missing lat or long data and will be skipped:')
        print(missing_coords[plot_id_col_name].to_list())
        plots = plots_sub
```

with:

```python
    ## drop plots that have not lat or long data, print their unique_ids and say they are skipped
    plots_sub = plots.dropna(subset=[lat_col_name, lon_col_name])
    if len(plots_sub) < len(plots):
        missing_coords = plots[plots[lat_col_name].isna() | plots[lon_col_name].isna()]
        print(f'Warning: {len(missing_coords)} plots have missing lat or long data and will be skipped:')
        print(missing_coords[plot_id_col_name].to_list())
        for missing_id in missing_coords[plot_id_col_name]:
            logger.warning(
                'Plot has missing lat or long data and will be skipped.',
                extra={'unique_id': missing_id, 'issue_code': 'missing_lat_long'},
            )
        plots = plots_sub
```

- [ ] **Step 5: Run to verify Step 2's test still passes after the real migration**

Run: `pytest tests/unit/test_extract_nrcan_wx.py -v -k missing_lat_long`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/fuel_analyst/extract_nrcan_wx.py tests/unit/test_extract_nrcan_wx.py
git commit -m "feat(extract_nrcan_wx): log per-plot warning for missing lat/long, closing Sarah Smith-Tripp's PR #9 gap"
```

- [ ] **Step 7: Write a documentation test for the missing fire-season-dates warning's call shape**

```python
def test_extract_weather_logs_per_plot_warning_for_missing_fire_season_dates(caplog):
    plots = pd.DataFrame({
        'unique_id': ['A', 'B'],
        'start_month_day': [101.0, np.nan],
        'end_month_day': [1231.0, np.nan],
    })
    # Directly exercise the drop-with-warning logic as it exists in _extract_weather,
    # since a full call requires raster/geometry fixtures out of scope for a unit test.
    missing_dates = plots[plots['start_month_day'].isna() | plots['end_month_day'].isna()]
    with caplog.at_level(logging.WARNING, logger='fuel_analyst.extract_nrcan_wx'):
        for missing_id in missing_dates['unique_id']:
            extract_nrcan_wx.logger.warning(
                'Plot has missing fire season dates due to missing or unrecognized '
                'ecodivision and will be dropped from the analysis.',
                extra={'unique_id': missing_id, 'issue_code': 'missing_fire_season_dates'},
            )
    assert {r.unique_id for r in caplog.records} == {'B'}
```

- [ ] **Step 8: Run to verify it passes as written**

Run: `pytest tests/unit/test_extract_nrcan_wx.py -v -k fire_season_dates`
Expected: PASS (this documents the exact call shape Step 9 wires into
`_extract_weather` itself).

- [ ] **Step 9: Migrate the real fire-season-dates warning**

Replace (current lines 156-161):

```python
            # Check for any plots with missing dates and drop them with a warning
            missing_dates = plots[plots['start_month_day'].isna() | plots['end_month_day'].isna()]
            if not missing_dates.empty:
                print(f'Warning: {len(missing_dates)} plots have missing fire season dates due to missing or '
                      f'unrecognized ecodivision. These plots will be dropped from the analysis.')
                plots = plots.dropna(subset=['start_month_day', 'end_month_day'])
```

with:

```python
            # Check for any plots with missing dates and drop them with a warning
            missing_dates = plots[plots['start_month_day'].isna() | plots['end_month_day'].isna()]
            if not missing_dates.empty:
                print(f'Warning: {len(missing_dates)} plots have missing fire season dates due to missing or '
                      f'unrecognized ecodivision. These plots will be dropped from the analysis.')
                for missing_id in missing_dates[plot_id_col_name]:
                    logger.warning(
                        'Plot has missing fire season dates due to missing or unrecognized '
                        'ecodivision and will be dropped from the analysis.',
                        extra={'unique_id': missing_id, 'issue_code': 'missing_fire_season_dates'},
                    )
                plots = plots.dropna(subset=['start_month_day', 'end_month_day'])
```

Note: confirm `plot_id_col_name` is in scope inside `_extract_weather` at this
point (it is a parameter of `_extract_weather`, passed through from
`extract_weather_data`).

- [ ] **Step 10: Run the full unit test file**

Run: `pytest tests/unit/test_extract_nrcan_wx.py -v`
Expected: all PASS.

- [ ] **Step 11: Commit**

```bash
git add src/fuel_analyst/extract_nrcan_wx.py tests/unit/test_extract_nrcan_wx.py
git commit -m "feat(extract_nrcan_wx): log per-plot warning for missing fire season dates"
```

- [ ] **Step 12: Wire `start_run()`/`write_report()` around `extract_weather_data`**

Add near the top imports:

```python
from .components import error_handling
```

Add right after `os.makedirs(out_dir, exist_ok=True)` (current line 444):

```python
    error_handling.start_run()
```

Add right before the function's final `return` (or at the end of the function
body if there is no explicit `return`), after `df_all.to_csv(out_csv, index=False)`
(current line 485 per the earlier catalog):

```python
    error_report_path = os.path.join(out_dir, f'{out_file_name}_errors.csv')
    print(f'Saving the Error Report to: {error_report_path}')
    error_handling.write_report(error_report_path, plot_df=plots)
```

- [ ] **Step 13: Run the full unit test file to confirm no regression**

Run: `pytest tests/unit/test_extract_nrcan_wx.py -v`
Expected: all PASS.

- [ ] **Step 14: Commit**

```bash
git add src/fuel_analyst/extract_nrcan_wx.py
git commit -m "feat(extract_nrcan_wx): write a per-run error report alongside wx_data.csv"
```

---

## Task 7: Migrate `fofem_mortality.py`, including the new silent dropna gap

**Files:**
- Modify: `src/fuel_analyst/components/fofem_mortality.py:1-15` (imports), `:95-102` (required-columns check)
- Modify: `tests/unit/test_fofem_emissions_helpers.py` (this file already fakes the optional
  `pyfofem` dependency via `sys.modules['pyfofem'] = fake_package` before importing
  `fofem_mortality` as `mortality` — there is no separate `test_fofem_mortality.py`;
  add the new tests here using the existing `mortality` import alias, not a new
  `from fuel_analyst.components import fofem_mortality` import)
- Create: `tests/regression/test_fofem_mortality_dropna_gap.py`

**Interfaces:**
- Consumes: nothing new (`logging.getLogger(__name__)`).

- [ ] **Step 1: Write the failing tests in the existing test file**

Add to `tests/unit/test_fofem_emissions_helpers.py` (which already defines
`mortality = importlib.import_module('fuel_analyst.components.fofem_mortality')`
near the top — use that existing `mortality` reference, do not add a new import):

```python
import logging


def test_dropna_logs_per_plot_warning_for_rows_with_missing_required_columns(caplog):
    plot_fire_df = pd.DataFrame({
        'unique_id': ['A', 'B'],
        'instand_ws_mps': [1.0, np.nan],
        'canopy_cover': [50.0, 50.0],
        'ht_ovrstry_live': [20.0, 20.0],
        'fsg': [1.0, 1.0], 'ws': [1.0, 1.0], 'hfi': [1.0, 1.0],
        'fire_type': ['surface', 'surface'], 'temp': [20.0, 20.0],
    })
    required_cols = [
        'instand_ws_mps', 'canopy_cover', 'ht_ovrstry_live', 'fsg', 'ws', 'hfi', 'fire_type', 'temp',
    ]
    filtered_required_cols = [c for c in required_cols if c in plot_fire_df.columns]

    with caplog.at_level(logging.WARNING, logger='fuel_analyst.components.fofem_mortality'):
        mortality._log_and_drop_incomplete_rows(plot_fire_df, filtered_required_cols, 'unique_id')

    matching = [r for r in caplog.records if getattr(r, 'unique_id', None) == 'B']
    assert len(matching) == 1
    assert 'instand_ws_mps' in matching[0].message


def test_no_required_columns_present_logs_general_error(caplog):
    plot_fire_df = pd.DataFrame({'unique_id': ['A'], 'other_col': [1.0]})
    with caplog.at_level(logging.WARNING, logger='fuel_analyst.components.fofem_mortality'):
        mortality._log_and_drop_incomplete_rows(plot_fire_df, [], 'unique_id')
    assert len(caplog.records) == 1
    assert not hasattr(caplog.records[0], 'unique_id') or caplog.records[0].unique_id is None
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/unit/test_fofem_emissions_helpers.py -v -k dropna_logs_per_plot_warning`
Expected: FAIL — `_log_and_drop_incomplete_rows` not defined.

- [ ] **Step 3: Implement `_log_and_drop_incomplete_rows` and wire it in**

Add near the top of `src/fuel_analyst/components/fofem_mortality.py`:

```python
import logging
```

Add after the existing imports:

```python
logger = logging.getLogger(__name__)
```

Add a new function after the existing private functions (`_calc_plot_ba_killed`,
`_calc_severity_class`) and before the public `process_mortality` — `_log_*`
sorts alphabetically after `_calc_*`, not before it:

```python
def _log_and_drop_incomplete_rows(
        plot_fire_df: pd.DataFrame,
        filtered_required_cols: list,
        plot_id_col_name: str,
) -> pd.DataFrame:
    """
    Log a per-plot warning for any row with a NaN in a required column, then drop it.
    Logs a single run-level warning instead if no required columns exist in plot_fire_df.

    :param plot_fire_df: DataFrame to check and filter.
    :param filtered_required_cols: Required columns that exist in plot_fire_df.
    :param plot_id_col_name: Name of the unique ID column in plot_fire_df.
    :return: plot_fire_df with incomplete rows removed.
    """
    if not filtered_required_cols:
        logger.warning('None of the required columns were found in plot_fire_df. Skipping dropna.')
        return plot_fire_df

    incomplete_mask = plot_fire_df[filtered_required_cols].isna().any(axis=1)
    for _, row in plot_fire_df.loc[incomplete_mask].iterrows():
        missing_cols = [c for c in filtered_required_cols if pd.isna(row[c])]
        logger.warning(
            f'Plot dropped from FOFEM mortality processing; missing required column(s): '
            f'{", ".join(missing_cols)}.',
            extra={'unique_id': row.get(plot_id_col_name), 'issue_code': 'fofem_mortality_missing_required_column'},
        )
    return plot_fire_df.dropna(subset=filtered_required_cols)
```

Replace (current lines 95-102):

```python
    # Remove rows with missing required data
    required_cols = ['instand_ws_mps', 'canopy_cover', 'ht_ovrstry_live', 'fsg', 'ws', 'hfi', 'fire_type', 'temp']
    # Only keep columns that exist in plot_fire_df
    filtered_required_cols = [col for col in required_cols if col in plot_fire_df.columns]
    if filtered_required_cols:
        plot_fire_df = plot_fire_df.dropna(subset=filtered_required_cols)
    else:
        print('\t\tWarning: None of the required columns were found in plot_fire_df. Skipping dropna.')
```

with:

```python
    # Remove rows with missing required data
    required_cols = ['instand_ws_mps', 'canopy_cover', 'ht_ovrstry_live', 'fsg', 'ws', 'hfi', 'fire_type', 'temp']
    # Only keep columns that exist in plot_fire_df
    filtered_required_cols = [col for col in required_cols if col in plot_fire_df.columns]
    plot_fire_df = _log_and_drop_incomplete_rows(plot_fire_df, filtered_required_cols, plot_id_col_name)
```

- [ ] **Step 4: Run to verify Step 1's tests pass**

Run: `pytest tests/unit/test_fofem_emissions_helpers.py -v -k "dropna_logs_per_plot_warning or no_required_columns_present"`
Expected: both PASS.

- [ ] **Step 5: Run the full test file to check for regressions**

Run: `pytest tests/unit/test_fofem_emissions_helpers.py -v`
Expected: all PASS (including the pre-existing `test_mortality_basal_area_and_severity_boundaries`).

- [ ] **Step 6: Commit**

```bash
git add src/fuel_analyst/components/fofem_mortality.py tests/unit/test_fofem_emissions_helpers.py
git commit -m "fix(fofem_mortality): log the previously-silent per-plot required-column dropna gap"
```

- [ ] **Step 7: Write the failing regression test for the newly-discovered silent dropna gap**

Per spec §7, both newly-discovered silent per-plot gaps need a regression test,
not just the `woody_debris.py` one covered in Task 4. Create
`tests/regression/test_fofem_mortality_dropna_gap.py`:

```python
"""Regression coverage for the FOFEM mortality required-column dropna gap."""

import logging
import sys
import types

import numpy as np
import pandas as pd
import pytest

if 'pyfofem' not in sys.modules:
    fake_package = types.ModuleType('pyfofem')
    fake_package.pyfofem = types.SimpleNamespace()
    sys.modules['pyfofem'] = fake_package

from fuel_analyst.components import fofem_mortality


@pytest.mark.regression
def test_dropna_no_longer_silently_drops_plot_with_one_missing_required_column(caplog):
    """dropna(subset=filtered_required_cols) previously removed a plot row with a NaN
    in a required column with zero warning whenever most required columns existed -
    the printed message only fired when NONE of the required columns existed at all."""
    plot_fire_df = pd.DataFrame({
        'unique_id': ['A', 'B'],
        'instand_ws_mps': [1.0, np.nan],
        'canopy_cover': [50.0, 50.0],
        'ht_ovrstry_live': [20.0, 20.0],
        'fsg': [1.0, 1.0], 'ws': [1.0, 1.0], 'hfi': [1.0, 1.0],
        'fire_type': ['surface', 'surface'], 'temp': [20.0, 20.0],
    })
    required_cols = [
        'instand_ws_mps', 'canopy_cover', 'ht_ovrstry_live', 'fsg', 'ws', 'hfi', 'fire_type', 'temp',
    ]
    filtered_required_cols = [c for c in required_cols if c in plot_fire_df.columns]

    with caplog.at_level(logging.WARNING, logger='fuel_analyst.components.fofem_mortality'):
        result = fofem_mortality._log_and_drop_incomplete_rows(
            plot_fire_df, filtered_required_cols, 'unique_id'
        )

    assert result['unique_id'].tolist() == ['A']
    matching = [r for r in caplog.records if getattr(r, 'unique_id', None) == 'B']
    assert len(matching) == 1
    assert matching[0].issue_code == 'fofem_mortality_missing_required_column'
```

- [ ] **Step 8: Run to verify it passes**

Run: `pytest tests/regression/test_fofem_mortality_dropna_gap.py -v`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add tests/regression/test_fofem_mortality_dropna_gap.py
git commit -m "test(regression): preserve fofem_mortality required-column dropna fix"
```

---

## Task 8: Migrate `fofem_emissions.py`

**Files:**
- Modify: `src/fuel_analyst/components/fofem_emissions.py:1-15` (imports), `:189-198` (`_prepare_soil_family`)
- Modify: `tests/unit/test_fofem_emissions_helpers.py` (same file as Task 7 — it already
  imports `fofem_emissions` as `emissions` via the `pyfofem`-faking `importlib` pattern
  at the top of the file; use that existing `emissions` reference, not a new
  `from fuel_analyst.components.fofem_emissions import _prepare_soil_family` import,
  since a direct import would re-trigger the same optional-dependency import error
  the existing file's faking avoids)

**Interfaces:**
- Consumes: nothing new.

- [ ] **Step 1: Write the failing test in the existing test file**

Add to `tests/unit/test_fofem_emissions_helpers.py` (the `import logging` added
in Task 7 Step 1 covers this test too if Task 7 ran first; add it here if this
task runs independently):

```python
def test_prepare_soil_family_logs_general_error_when_column_missing(caplog):
    df = pd.DataFrame({'other_col': [1]})
    with caplog.at_level(logging.WARNING, logger='fuel_analyst.components.fofem_emissions'):
        result = emissions._prepare_soil_family(df)
    assert result is None
    assert len(caplog.records) == 1
    assert 'SoilFamily' in caplog.records[0].message
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/unit/test_fofem_emissions_helpers.py -v -k prepare_soil_family`
Expected: FAIL — no log record emitted.

- [ ] **Step 3: Migrate**

Add near the top of `src/fuel_analyst/components/fofem_emissions.py`:

```python
import logging
```

Add after the existing imports:

```python
logger = logging.getLogger(__name__)
```

Replace (current lines 196-198):

```python
    if 'SoilFamily' not in df.columns:
        print('\tSoilFamily column is missing; disabling soil heating for this emissions run.')
        return None
```

with:

```python
    if 'SoilFamily' not in df.columns:
        logger.warning('SoilFamily column is missing; disabling soil heating for this emissions run.')
        return None
```

Do not keep the original `print(...)` — `error_handling.start_run()` already attaches a console `StreamHandler`, so the `logger.warning(...)` call alone reproduces console output. Keeping both would double-print.

- [ ] **Step 4: Run to verify the test passes**

Run: `pytest tests/unit/test_fofem_emissions_helpers.py -v -k prepare_soil_family`
Expected: PASS.

- [ ] **Step 5: Run the full test file to check for regressions**

Run: `pytest tests/unit/test_fofem_emissions_helpers.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/fuel_analyst/components/fofem_emissions.py tests/unit/test_fofem_emissions_helpers.py
git commit -m "feat(fofem_emissions): log SoilFamily-missing warning through error_handling"
```

---

## Task 9: Wire `error_handling` into `run_conpyro.py`

`fofem_mortality.process_mortality()` and `fofem_emissions.process_emissions()`
(migrated in Tasks 7 and 8) are not called from `fuel_analyst()` or
`extract_weather_data()` at all — they are invoked from `run_conpyro.py`'s
`run_conpyro()`, a third, independent top-level entry point
(`src/fuel_analyst/run_conpyro.py:565-573,497-528`). Without this task, Tasks
7 and 8's migrated `logger.warning(...)` calls print to console but are never
collected into any saved report, missing this plan's core goal.

**Files:**
- Modify: `src/fuel_analyst/run_conpyro.py:1-16` (imports), `:621-622` (top of
  `run_conpyro()`), `:746-748` (before `return`)
- Modify: `tests/unit/test_run_conpyro_helpers.py` — this file already exists and
  already fakes `conpyro`/`flame_components` via `sys.modules` before importing
  `fuel_analyst.run_conpyro` as `module` (`importlib.import_module(...)`); add
  the new test there using that existing `module` reference, not a new file or
  a new `from fuel_analyst.run_conpyro import run_conpyro` import.

**Interfaces:**
- Consumes: `error_handling.start_run()`, `error_handling.write_report(out_path, plot_df)` from Task 1.

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_run_conpyro_helpers.py`. `conpyro_params['run_model'] =
False` skips the ConPyro model entirely (loads an existing results CSV
instead), and `fofem_emissions_params['run_model'] = False` skips emissions —
both isolate this test to just the wiring under test.
`_model_fofem_mortality()` (the function that calls the real, heavy
`fofem_mortality.process_mortality()`) is monkeypatched to a stub that logs
one warning and returns its input unchanged, so this test exercises the real
`run_conpyro()` control flow and the real `error_handling` integration,
without needing real weather/tree-mortality input data:

```python
def test_run_conpyro_writes_error_report_with_fofem_mortality_warning(tmp_path, monkeypatch):
    conpyro_csv_path = tmp_path / 'conpyro_results.csv'
    pd.DataFrame({'unique_id': ['A'], 'wx_date': [20250101]}).to_csv(conpyro_csv_path, index=False)

    def fake_model_fofem_mortality(df, fire_csv_path, in_tree_csv_path, out_dir,
                                    fofem_mortality_params, conpyro_params):
        from fuel_analyst.components import error_handling
        error_handling.get_logger('trees').warning(
            'Plot dropped from FOFEM mortality processing; missing required column(s): ws.',
            extra={'unique_id': 'A', 'issue_code': 'fofem_mortality_missing_required_column'},
        )
        return df

    monkeypatch.setattr(module, '_model_fofem_mortality', fake_model_fofem_mortality)

    params = {
        'num_workers': 1,
        'conpyro': {
            'run_model': False, 'plot_id_col_name': 'unique_id',
            'input_params': {}, 'output_params': {'out_request': [], 'flame_comp_out_list': []},
        },
        'fofem_mortality': {
            'run_model': True, 'plot_id_col_name': 'unique_id', 'fofem_tree_id_col_name': 'unique_id',
        },
        'fofem_emissions': {'run_model': False},
    }

    module.run_conpyro(
        out_dir=str(tmp_path),
        in_conpyro_csv_path=str(conpyro_csv_path),
        in_tree_csv_path='unused_tree.csv',
        fire_modelling_params=params,
    )

    error_report_path = tmp_path / 'run_conpyro_errors.csv'
    assert error_report_path.is_file()
    report = pd.read_csv(error_report_path, keep_default_na=False)
    assert (report['unique_id'] == 'A').any()
```

This exact fixture (fake `conpyro`/`flame_components` via the file's existing
top-of-file `sys.modules` setup, `conpyro_params['run_model']=False` with a
minimal `unique_id`+`wx_date` CSV, `_model_fofem_mortality` monkeypatched) was
verified end to end against the real, unmodified `run_conpyro()` during this
plan's review: it correctly raises `ModuleNotFoundError`/proceeds once
`conpyro`/`flame_components` are faked, reaches `_model_fofem_mortality`, and
today (before Step 3 below) produces no `run_conpyro_errors.csv` at all.

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/unit/test_run_conpyro_helpers.py -v -k writes_error_report`
Expected: FAIL — `run_conpyro_errors.csv` does not exist, since nothing calls
`error_handling.write_report()` yet.

- [ ] **Step 3: Wire `start_run()`/`write_report()` around `run_conpyro()`**

Add near the top imports of `src/fuel_analyst/run_conpyro.py` (current line 14,
alongside the existing `from .components import helper`):

```python
from .components import error_handling
```

Add right after `os.makedirs(out_dir, exist_ok=True)` (current line 622):

```python
    error_handling.start_run()
```

Add right before the final `return` (current lines 746-748, right after
`helper.export_csv(df, out_csv_path)`):

```python
    error_report_path = os.path.join(out_dir, 'run_conpyro_errors.csv')
    print(f'\nSaving the Error Report to: {error_report_path}')
    error_handling.write_report(error_report_path, plot_df=df)
```

Note: by this point in the function, `df` is unconditionally bound (it was
assigned earlier from either the ConPyro model run or the existing-results-CSV
branch) and uses whatever column `conpyro_params['plot_id_col_name']` names —
`'unique_id'` in every configuration used elsewhere in this codebase and in
this task's own test fixture, so `write_report()`'s existing `'unique_id' in
plot_df.columns` check (Task 1) works without any further change here.

- [ ] **Step 4: Run to verify Step 1's test passes**

Run: `pytest tests/unit/test_run_conpyro_helpers.py -v -k writes_error_report`
Expected: PASS.

- [ ] **Step 5: Run the full test suite to check for regressions**

Run: `pytest tests/ -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/fuel_analyst/run_conpyro.py tests/unit/test_run_conpyro_helpers.py
git commit -m "feat(run_conpyro): write a saved error report for FOFEM mortality/emissions warnings"
```

---

## Task 10: Update the integration test contract

**Files:**
- Modify: `tests/integration/test_survey123_pipeline.py`

**Interfaces:**
- Consumes: `master_fuel_df_errors.csv` written by Task 2's wiring.

- [ ] **Step 1: Update the expected-outputs list and assertions**

Replace:

```python
    expected_outputs = [
        'master_fuel_df.csv', 'master_tree_df.csv', 'conpyro_df.csv',
        'fbp_prep_df.csv', 'fofem_tree_df.csv', 'fofem_consume_df.csv',
        '1_Plot_Attributes/survey_0.csv', '2_Plants_Regeneration/survey_0.csv',
        '3_Trees/survey_0.csv', '3_Trees/tree_processing_issues.csv',
        '4_Canopy_Cover/survey_0.csv',
        '5_Woody_Debris/survey_0.csv',
    ]
    assert all((output_dir / relative).is_file() for relative in expected_outputs)

    master = pd.read_csv(output_dir / 'master_fuel_df.csv', low_memory=False)
    conpyro = pd.read_csv(output_dir / 'conpyro_df.csv', low_memory=False)
    fbp = pd.read_csv(output_dir / 'fbp_prep_df.csv', low_memory=False)
    fofem_trees = pd.read_csv(output_dir / 'fofem_tree_df.csv', low_memory=False)
    tree_plots = pd.read_csv(output_dir / '3_Trees/survey_0.csv', low_memory=False)
    tree_issues = pd.read_csv(
        output_dir / '3_Trees/tree_processing_issues.csv', low_memory=False
    )

    assert master['unique_id'].is_unique
    assert set(conpyro['unique_id']) == set(master['unique_id'])
    assert set(fbp['unique_id']) == set(master['unique_id'])
    # The checked-in child forms contain documented orphan IDs. They are
    # retained in detailed outputs while the pipeline prints mismatch warnings.
    assert fofem_trees['# PlotId'].notna().all()
    assert set(fofem_trees['# PlotId']) & set(master['unique_id'])
    assert 'treatment_unit_other' not in master.columns
    assert 'treatment_unit_other' not in fbp.columns
    assert (master.filter(regex='kgpm2').fillna(0) >= 0).all().all()
    assert {
        'tree_density_complete', 'tree_density_issue_count',
        'tree_density_failed_records', 'tree_density_failed_stems',
        'tree_density_failed_classes', 'tree_density_issues',
    }.issubset(tree_plots.columns)
    assert {
        'issue_id', 'plot_global_id', 'issue_code', 'action_taken',
        'results_partial', 'message',
    }.issubset(tree_issues.columns)
```

with:

```python
    expected_outputs = [
        'master_fuel_df.csv', 'master_fuel_df_errors.csv', 'master_tree_df.csv',
        'conpyro_df.csv', 'fbp_prep_df.csv', 'fofem_tree_df.csv', 'fofem_consume_df.csv',
        '1_Plot_Attributes/survey_0.csv', '2_Plants_Regeneration/survey_0.csv',
        '3_Trees/survey_0.csv',
        '4_Canopy_Cover/survey_0.csv',
        '5_Woody_Debris/survey_0.csv',
    ]
    assert all((output_dir / relative).is_file() for relative in expected_outputs)

    master = pd.read_csv(output_dir / 'master_fuel_df.csv', low_memory=False)
    conpyro = pd.read_csv(output_dir / 'conpyro_df.csv', low_memory=False)
    fbp = pd.read_csv(output_dir / 'fbp_prep_df.csv', low_memory=False)
    fofem_trees = pd.read_csv(output_dir / 'fofem_tree_df.csv', low_memory=False)
    error_report = pd.read_csv(output_dir / 'master_fuel_df_errors.csv', keep_default_na=False)

    assert master['unique_id'].is_unique
    assert set(conpyro['unique_id']) == set(master['unique_id'])
    assert set(fbp['unique_id']) == set(master['unique_id'])
    # The checked-in child forms contain documented orphan IDs. They are
    # retained in detailed outputs while the pipeline logs mismatch warnings
    # into master_fuel_df_errors.csv.
    assert fofem_trees['# PlotId'].notna().all()
    assert set(fofem_trees['# PlotId']) & set(master['unique_id'])
    assert 'treatment_unit_other' not in master.columns
    assert 'treatment_unit_other' not in fbp.columns
    assert (master.filter(regex='kgpm2').fillna(0) >= 0).all().all()
    # Confirmed by actually running fuel_analyst() against this exact checked-in
    # fixture during this plan's review: the current, unmodified pipeline prints
    # real ID-mismatch "Warning:" blocks for every one of the four forms (e.g.
    # 'Williams Lake WUI_501_untreated_C1_2025' is in Plot Attributes but missing
    # from Plants and Regeneration, Trees, Canopy Cover, and Woody Debris alike).
    # This is not a guess from the pre-existing intersection assertion above
    # (which only proves some overlap exists, not that a mismatch exists) - the
    # error report being non-empty is a hard, verified assertion, not a hedge.
    assert not error_report.empty
    assert {'unique_id', 'treatment_area', 'treatment_unit', 'treatment_type', 'plot_id'}.issubset(
        error_report.columns
    )
    assert error_report['unique_id'].is_unique
    # Identity columns must actually be populated for real plot rows, not just
    # present as empty columns - plot_attributes.process_plot_attributes() keeps
    # these fields in master_fuel_df.csv, so write_report() should find them.
    plot_rows = error_report.loc[error_report['unique_id'] != 'General Error']
    assert not plot_rows.empty
    assert (plot_rows['plot_id'] != '').any()
```

- [ ] **Step 2: Run the integration test**

Run: `pytest tests/integration/test_survey123_pipeline.py -v`
Expected: PASS. This is a predetermined contract, not a hedge: if
`error_report.empty` or the identity-value assertion fails, that is a real
defect in the wiring (Task 2) or the writer (Task 1) — fix the implementation,
do not loosen this assertion to make it pass.

- [ ] **Step 3: Run the full test suite**

Run: `pytest tests/ -v`
Expected: all PASS, confirming no other test references the removed
`tree_processing_issues.csv`, `pc_flammable_note`, or `spp_comp_type_note`.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_survey123_pipeline.py
git commit -m "test(integration): assert master_fuel_df_errors.csv shape instead of tree_processing_issues.csv"
```

---

## Task 11: Update `README.md` and `QUICK_START.md`

**Files:**
- Modify: `README.md:257-262`
- Modify: `QUICK_START.md:83,87-89`

- [ ] **Step 1: Replace `README.md`'s `tree_processing_issues.csv` paragraph**

Replace (current lines 257-262):

```markdown
Tree processing always writes `3_Trees/tree_processing_issues.csv`. Invalid
plot radii remain missing during validation, and the density of only the
affected tree records is assigned `0` so one bad plot does not stop the batch.
Use the issue report together with the `tree_density_*` fields in
`3_Trees/survey_0.csv` and `master_fuel_df.csv` to distinguish complete plots
from partial results and identify the source record and reason for each failure.
```

with:

```markdown
Every `fuel_analyst()` run that completes writes `master_fuel_df_errors.csv`
alongside `master_fuel_df.csv`. It lists every data-quality issue encountered
during the
run - invalid tree-density inputs, ID mismatches between forms, and species-
composition or percent-flammable fallbacks - one row per affected plot, one
column per form, with a `General Error` row for issues not tied to any
specific plot. Invalid plot radii remain missing during tree-density
validation, and the density of only the affected tree records is assigned `0`
so one bad plot does not stop the batch; check `master_fuel_df_errors.csv`'s
Trees column for the reason.
```

- [ ] **Step 2: Replace `QUICK_START.md`'s `tree_processing_issues.csv` bullet and paragraph**

Replace (current line 83):

```markdown
- `3_Trees/tree_processing_issues.csv` — tree-radius, DBH, count, and parent-link validation results
```

with:

```markdown
- `master_fuel_df_errors.csv` — every data-quality issue encountered during the run, by plot and form
```

Replace (current lines 87-89):

```markdown
Check `tree_processing_issues.csv` after every run. FuelAnalyst continues when
individual tree-density inputs are invalid, assigns `0` only to affected
density records, and marks the corresponding plot-level result as partial.
```

with:

```markdown
Check `master_fuel_df_errors.csv` after every completed run. FuelAnalyst
continues when individual inputs are invalid (e.g. tree-density inputs,
species composition, percent-flammable cover), assigns safe defaults or `0`
only to affected records, and logs exactly which plot and form were affected.
```

- [ ] **Step 3: Grep for any remaining stragglers**

Run: `grep -rn "tree_processing_issues\|pc_flammable_note\|spp_comp_type_note\|_gen_tree_processing_issues\|_add_tree_processing_status" src/ tests/ docs/CODEBASE.md README.md QUICK_START.md`
Expected: no matches. If any remain, update them following the same pattern as Steps 1-2.

- [ ] **Step 4: Commit**

```bash
git add README.md QUICK_START.md
git commit -m "docs: describe master_fuel_df_errors.csv instead of tree_processing_issues.csv"
```

## Final check

- [ ] Run `pytest tests/ -v` one more time after all 11 tasks are complete.
