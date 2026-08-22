# Error Handling Module — Design Spec

Date: 2026-08-21
Status: Approved by user (2026-08-21). Next step: writing-plans produces an implementation plan;
Codex reviews that plan (not this spec) before implementation begins.

## 1. Motivation

FuelAnalyst currently reports data-quality problems inconsistently:

- Most components (`fuel_analyst.py`, `extract_nrcan_wx.py`, `woody_debris.py`, `plants_regen.py`,
  `fofem_mortality.py`, `fofem_emissions.py`) only `print()` warnings to console. Nothing is
  captured to a file, so a warning seen during a batch run is lost once the console scrolls past it.
- `trees.py` has one working, centralized, structured issue log
  (`_gen_tree_processing_issues()` / `_add_tree_processing_status()`, added in commit `06794a3`),
  writing `3_Trees/tree_processing_issues.csv` plus rollup columns into `master_fuel_df.csv`. It
  is the only component with this capability, and it is bespoke to tree-density validation.
- Two new inline per-column notes were added this session: `pc_flammable_note`
  (`plants_regen.py`) and `spp_comp_type_note` (`woody_debris.py`). These are per-plot text notes
  on a single column, not centralized, and not visible without opening `master_fuel_df.csv` and
  finding the right column.
- `extract_nrcan_wx.py`'s missing-lat/long check (PR #9, commit `977add6`, Sarah Smith-Tripp)
  only prints to console today, despite its commit message implying a CSV output exists.

Goal: one centralized module that every component reports into, giving the user a single,
readable, per-plot view of every data-quality issue encountered during a run — without changing
when or why an issue is detected.

## 2. Goals / Non-goals

**Goals**
- Every currently-console-only warning becomes visible in a structured, saved output.
- Console output is preserved exactly as it exists today — nothing goes silent.
- A single developer-facing API (`logging.getLogger(...)` + calling `.info`/`.warning`/`.error`)
  replaces all bespoke reporting mechanisms (`trees.py`'s issue builder, the new inline note
  columns), with no function signature changes required anywhere in the codebase.
- The final output is one CSV per pipeline run: one row per plot with ≥1 issue, plus a reserved
  `General Error` row for issues with no associated plot, one column per form, each cell a
  numbered list of issues for that form. Plots with zero issues across all forms do not appear.
- `extract_nrcan_wx.py` (a separate entry point, not called from `fuel_analyst()`) gets its own
  equivalent report using the same underlying mechanism.

**Non-goals**
- Hard `raise ValueError`/`FileNotFoundError` pre-flight checks (missing CRS, missing required
  columns in `run_conpyro.py`, `merge_wx_data.py`, `fofem_emissions.py`) stay as exceptions. They
  abort the run before any plot is processed, so there is no partial per-plot report to write
  into. Converting these to soft/continuable errors is out of scope.
- No change to *when* or *why* an issue is detected — this is a reporting-layer change only.
- No new severity taxonomy beyond the three standard logging levels used here (INFO/WARNING/ERROR).
- No configurability of the output path/filename in v1 (hardcoded alongside existing outputs,
  matching how `master_fuel_df.csv`'s path is already hardcoded).

## 3. Architecture

### 3.1 New module: `src/fuel_analyst/components/error_handling.py`

Located under `components/` (not top-level) so it follows the existing Import Pattern
documented in `CLAUDE.md`: components use `from . import error_handling`, and top-level modules
(`fuel_analyst.py`, `extract_nrcan_wx.py`) use `from .components import error_handling` — the
same pattern already used for `helper`.

Responsibilities:
1. **`start_run() -> None`** — creates and attaches a fresh in-memory collecting
   `logging.Handler` to the `fuel_analyst` logger namespace, and raises that namespace's
   effective level to `INFO` (loggers otherwise default to the root logger's `WARNING`
   threshold, which would silently discard every `.info(...)` fallback-note call before it
   ever reached the handler). It also attaches a plain `logging.StreamHandler(sys.stdout)`
   alongside the collecting handler. This second handler is required, not decorative:
   attaching *any* handler to a logger causes Python's `Logger.callHandlers()` to count it
   and skip `logging.lastResort` — the fallback that otherwise prints unconfigured
   `WARNING`+ calls to console. Without this second handler, every migrated `logger.*(...)`
   call would go completely silent on the console for the entire duration of a run (verified
   empirically during implementation) — the opposite of Goal 1 (console output must not
   regress). `sys.stdout` is used deliberately, matching where every existing `print(...)`
   call in this codebase already writes; the default `StreamHandler()` target is `stderr` and
   would silently move this output to a different stream. Called once at the very top of every pipeline entry point:
   `fuel_analyst()`, `extract_weather_data()`, and `run_conpyro()` (see §5.1 — FOFEM
   mortality/emissions are invoked from `run_conpyro()`, a third entry point, not from the
   other two). `start_run()` also saves the logger namespace's prior level and restores it in
   `write_report()`, so collection is scoped to the active run rather than permanently raising
   the level. Because the handler is created fresh per call and nothing is attached otherwise,
   a bare unit test that never calls `start_run()` never accumulates anything. One documented
   exception: if an entry point raises *between* `start_run()` and `write_report()` (e.g. a
   pre-flight validation error), the handler stays attached until the next `start_run()` call
   removes it — see the implementation plan's "accepted limitation" note for why this is not
   fixed with `try`/`finally`.
2. **`write_report(out_path: str, plot_df: pd.DataFrame = None) -> None`** — pivots everything
   the handler collected during the run into the wide CSV (see §4) and writes it, then
   detaches the handler. `plot_df`, when supplied, provides the identity columns
   (`treatment_area`/`treatment_unit`/`treatment_type`/`plot_id`) by `unique_id`; only the
   identity columns actually present in `plot_df` are included in the output, so a caller
   without those columns (e.g. `extract_weather_data()`'s plot list) naturally gets a report
   with just `unique_id` plus per-form columns rather than always-blank identity columns.
3. **`get_logger(form: str) -> logging.Logger`** — returns the canonical logger for a given form
   name, for callers (chiefly `fuel_analyst.py`) that need to report an issue *about* a form from
   outside that form's own module (e.g., a missing-folder warning detected in the orchestrator).
   Components reporting about themselves just use `logging.getLogger(__name__)` directly; the
   collecting handler maps both to the same form via a name → display-name lookup table.

### 3.2 Logger naming → form mapping

| Logger name | Form (CSV column) |
|---|---|
| `fuel_analyst.components.plot_attributes` | Plot Attributes |
| `fuel_analyst.components.plants_regen` | Plants and Regeneration |
| `fuel_analyst.components.trees` | Trees |
| `fuel_analyst.components.canopy_cover` | Canopy Cover |
| `fuel_analyst.components.woody_debris` | Woody Debris |

Each component's existing `logging.getLogger(__name__)` already resolves to one of these dotted
names for free, since `__name__` inside `src/fuel_analyst/components/trees.py` *is*
`fuel_analyst.components.trees`. No per-call form argument needed for components reporting on
themselves.

`fuel_analyst.py`'s own warnings (missing form folder, ID mismatches between forms) are about a
*specific form*, even though the code lives in the orchestrator — these call
`error_handling.get_logger('woody')` (etc.) rather than `logging.getLogger(__name__)`, so they
land in the correct form's column rather than a generic "pipeline" column.

### 3.3 Structured fields via `extra`

Every call site passes plot identity through the standard `extra={...}` mechanism, e.g.:

```python
logger.warning(
    "Declared spp_comp_type 'tree_data' had no matching species composition data; "
    "used 'transect_data' instead.",
    extra={'unique_id': plot_id, 'issue_code': 'spp_comp_type_fallback'},
)
```

The collecting handler reads `record.unique_id`, `record.levelname`, and the logger's form
mapping off each `LogRecord` as it fires. `issue_code` is captured for potential future
filtering/analysis but is not surfaced as its own CSV column in v1 (kept out to match the
approved wide-format shape exactly; can be added later without breaking the schema).

When a warning currently applies to a *list* of plot IDs (e.g., `fuel_analyst.py`'s ID-mismatch
warnings), the call site loops and emits one `logger.warning(...)` per affected `unique_id`, so
each plot gets its own row in the final pivot rather than one row listing every affected plot.

### 3.4 Severity mapping

| Current pattern | New level |
|---|---|
| `pc_flammable_note` / `spp_comp_type_note` style fallback-applied notes | `logger.info(...)` |
| Existing `print('Warning: ...')` sites | `logger.warning(...)` |
| `trees.py` tree-density issues where `results_partial=True` today (a record's density got zeroed) | `logger.error(...)` |
| `trees.py` tree-density issues where `results_partial=False` today (flagged but nothing affected) | `logger.warning(...)` |

## 4. Output CSV shape

One file per `fuel_analyst()` run, written alongside `master_fuel_df.csv` (e.g.
`master_fuel_df_errors.csv`):

| unique_id | treatment_area | treatment_unit | treatment_type | plot_id | Plot Attributes | Plants and Regeneration | Trees | Canopy Cover | Woody Debris |
|---|---|---|---|---|---|---|---|---|---|
| `General Error` | | | | | (run-level issues for this form) | ... | ... | ... | ... |
| *(one row per plot with ≥1 issue)* | | | | | | | | | |

- **`General Error` row.** A reserved first row (sorted to appear above every plot row) holding
  issues with no associated `unique_id` — e.g., `fofem_mortality.py`'s "no required columns
  found", `trees.py`'s fireline-model fallback. Same numbering/severity-prefix formatting as any
  plot cell, just keyed to this sentinel row instead of a real plot. This replaces the "excluded
  from the CSV" handling in an earlier draft of this spec (see §6) — every issue collected during
  the run now lands somewhere in this one file, run-level or per-plot.
- One row per plot with ≥1 issue anywhere; plots with zero issues across all forms are omitted
  entirely.
- Each form cell is empty if that plot (or `General Error`) had no issues in that form; otherwise
  a numbered, newline-joined list, severity-prefixed:
  `1. [WARNING] Declared spp_comp_type 'tree_data' had no matching data; used 'transect_data' instead.\n2. [ERROR] Missing plot radius for lgtree class.`
  CSV supports embedded newlines inside a quoted field; Excel renders this as a wrapped
  multi-line cell.
- Identifying columns (`treatment_area`, `treatment_unit`, `treatment_type`, `plot_id`) are
  pulled from `plot_df` by `unique_id` where available. Only the identity columns actually
  present in the `plot_df` passed to `write_report()` are included in the output at all — a
  caller whose plot list has none of these columns gets a report with no identity columns,
  not always-blank ones. On the `General Error` row, any included identity columns are blank.
  Edge case: if a form reports a plot ID that never appeared in Plot Attributes at all (the
  reverse ID-mismatch case), those columns are blank for that row since there is no Plot
  Attributes record to pull them from.

`extract_nrcan_wx.py` and `run_conpyro.py` (see §5.1) each get an equivalent, separate report
using the same `start_run()`/`write_report()` calls, written alongside their own existing
outputs. Since neither passes a `plot_df` with `treatment_area`/`treatment_unit`/
`treatment_type`/`plot_id` columns, their reports naturally collapse to `unique_id` plus one
issues column per distinct form encountered — no special-casing needed in the writer, because
both the identity columns and the form columns are computed dynamically from what was actually
collected during that run.

## 5. Migration map

| File | Current mechanism | Becomes |
|---|---|---|
| `trees.py`: `_gen_tree_processing_issues()`, `_add_tree_processing_status()`, `tree_processing_issues.csv`, `tree_density_*` rollup columns | Bespoke DataFrame-building + dedicated CSV | Deleted. Replaced with `logger.warning(...)`/`logger.error(...)` calls at each existing detection point (invalid radius, invalid DBH, invalid sapling counts, ambiguous/orphan parent IDs). Existing console summary block (lines 2043-2049) stays, repointed at the new report path. |
| `plants_regen.py`: `_calc_pc_flammable()`, `pc_flammable_note` column | Inline per-column note | `logger.info(...)` at each fallback branch (no rock/mineral-soil data, out-of-range calculated value). `pc_flammable_note` column removed. |
| `woody_debris.py`: `_resolve_spp_comp_type()`, `spp_comp_type_note` column | Inline per-column note | `logger.info(...)` when a fallback fires. `spp_comp_type_note` column removed. |
| `woody_debris.py`: "stand_spp_comp_woody column not found" (no plots have tree-derived species comp at all) | `print(...)` | `logger.warning(...)` with no `extra` — lands on the `General Error` row (Woody Debris column). |
| `fuel_analyst.py`: missing form folder but plots selected it | `print(...)` listing affected plot IDs | `error_handling.get_logger(form).warning(...)` once per affected `unique_id`. |
| `fuel_analyst.py`: ID mismatches between Plot Attributes and a form | `print(...)` listing both ID lists | `error_handling.get_logger(form).warning(...)` once per affected `unique_id`, both directions. |
| `extract_nrcan_wx.py`: missing lat/long | `print(...)` listing skipped plot IDs | `logger.warning(...)` once per skipped plot. Closes the gap flagged for Sarah Smith-Tripp's check. |
| `extract_nrcan_wx.py`: missing fire season dates | `print(...)` | `logger.warning(...)` once per affected plot. |
| `fofem_mortality.py` / `fofem_emissions.py` run-level warnings (no `unique_id` available) | `print(...)` | `logger.warning(...)` with no `extra` — lands on the `General Error` row. |

### 5.1 `run_conpyro.py` is a third pipeline entry point

`fofem_mortality.process_mortality()` and `fofem_emissions.process_emissions()` are not called
from `fuel_analyst()` or `extract_weather_data()` at all — they are invoked from
`run_conpyro.py`'s `run_conpyro()` (via `_model_fofem_mortality()`/`_model_fofem_emissions()`),
a third, independent top-level entry point. Migrating their `print(...)` calls to
`logger.warning(...)` only fixes console-output parity; without `run_conpyro()` also calling
`error_handling.start_run()` near its top (after `os.makedirs(out_dir, exist_ok=True)`) and
`error_handling.write_report(...)` before it returns, those warnings would never reach any
saved output, contradicting this spec's core goal (§2, Goals, first bullet). `run_conpyro()`
gets its own report (e.g. `run_conpyro_errors.csv`, alongside its `conpyro_df.csv`-equivalent
outputs) using the same mechanism as the other two entry points.

**New per-plot logging (not a migration — these plots currently produce no warning of any kind):**

| File | Currently-silent gap found during design review (2026-08-21) | New logging |
|---|---|---|
| `woody_debris.py`: `_merge_spp_comp()`, "tree data" branch | `valid_data = plot_df['stand_spp_comp_woody'].notna()` is a per-row mask; when `valid_data.any()` is True (at least one plot has tree-derived species comp), `valid_rows = plot_df[valid_data]` silently excludes any individual plot where the value is NaN — that plot then falls back to another `spp_comp_type` source downstream with no record of why. `unique_id` is directly in scope via `plot_df`. | `logger.info(...)` per excluded plot, e.g. "No tree-derived species composition for this plot; falling back to another spp_comp_type source." Effectively explains the *cause* behind `spp_comp_type`'s fallback for that specific plot. |
| `fofem_mortality.py`, the `dropna(subset=filtered_required_cols)` call immediately above the existing warning | The printed warning only fires when *no* required columns exist at all; the `dropna()` call itself silently drops any individual plot row with a NaN in a required column even when most columns exist. `unique_id`/`plot_id_col_name` is available in `plot_fire_df` right before this call. | `logger.warning(...)` per dropped plot, naming which required column(s) were missing for that row, before the drop occurs. |

## 6. Run-level warnings with no associated plot

A few existing warnings aren't about any specific plot (e.g., `fofem_mortality.py`'s "None of
the required columns were found in plot_fire_df", `fofem_emissions.py`'s missing SoilFamily
column, `trees.py`'s invalid-fire-model fallback). These call `logger.warning(...)` exactly as
before (console output unchanged) with no `unique_id` in `extra`; `write_report()` places them on
the reserved `General Error` row (§4) rather than a real plot row.

### 6.1 Related finding, folded into scope

While reviewing `trees.py`'s fireline-model check (line ~1229) to confirm it was genuinely
run-level (it is — driven by a single string parameter, not a DataFrame column), a pre-existing
bug surfaced: the check is written as `else` (i.e., "not Thomas"), so it prints "Invalid surface
fireline intensity model specified. Using Byram (1959) as default." even when the caller
correctly passes `'Byram'` — a false-positive warning on valid input, unrelated to this module's
design. **Decided (2026-08-21):** fix this alongside converting the print to
`logger.warning(...)` on the same line — the condition should only fire when
`surface_fire_intensity_model` is neither `'Byram'` nor `'Thomas'`, so a correctly-specified
`'Byram'` no longer produces a false-positive warning.

## 7. Testing strategy

Unit tests construct `LogRecord`s directly (or call component functions with a handler attached
in the test) and assert the pivoted CSV shape: multiple issues per cell, correct numbering,
correct severity prefixes, plots with zero issues excluded, identifying columns populated/blank
correctly for the reverse-ID-mismatch edge case, and records with no `unique_id` landing on the
`General Error` row rather than being dropped. Since nothing is attached unless a test explicitly
calls `start_run()`, all of the currently-passing unit/regression tests that call component
functions directly (e.g., `_resolve_spp_comp_type`) remain unaffected and require no new fixtures.

The two newly-discovered silent per-plot gaps (§5, "New per-plot logging") should each get a
regression test reproducing the specific silent-drop scenario found during design review, per
`tests/regression/README.md`.

A migrated regression test should replace the removed `trees.py` issue-report tests, reproducing
at least one of the original confirmed tree-density defects through the new logger-based path,
per `tests/regression/README.md`.
