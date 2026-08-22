# PR Description: Centralized Error-Handling Module

**Title:** feat: centralize error/warning reporting into fuelanalyst_errors.csv

## Summary

FuelAnalyst previously reported data-quality issues (invalid tree-density
inputs, ID mismatches between Survey123 forms, species-composition and
percent-flammable fallbacks, missing weather/soil inputs, etc.) through a mix
of ad hoc `print()` statements and one bespoke per-component CSV
(`3_Trees/tree_processing_issues.csv`). Nothing was collected consistently
across components, several fallbacks fired with zero warning of any kind, and
there was no single place a user could look to see every issue from one run.

This branch replaces all of that with a centralized `error_handling` module.
Every component reports through the standard `logging` module
(`logging.getLogger(__name__)` + `logger.warning(...)`/`logger.error(...)`
with `extra={'unique_id': ..., 'issue_code': ...}`); a collecting handler
gathers everything raised during a run; and `write_report()` pivots it into
one CSV — `fuelanalyst_errors.csv` — with one row per plot that has ≥1
issue, one column per form, and a reserved `General Error` row for issues not
tied to any specific plot. Console output is fully preserved (and in one
place, improved) via a fallback console handler when the host application has
not already configured logging.

Three entry points now write this report: `fuel_analyst()`,
`extract_weather_data()`, and `run_conpyro()`.

## Motivation / gaps closed

Several genuinely silent failure modes were found and fixed along the way,
not just re-plumbed:

- **`fuel_analyst.py`'s ID-mismatch check only checked one direction.** A plot
  present in a child form but missing from Plot Attributes was silently
  merged with no warning at all; only the reverse direction (missing from the
  child form) was ever reported. Both directions are now checked and logged
  independently.
- **`woody_debris.py` had zero warning when a plot's `stand_spp_comp_woody`
  was missing while its siblings had it** — it just silently fell out of the
  tree-data branch. Now logged per plot.
- **`fofem_mortality.py` dropped rows with missing required columns with only
  an aggregate `print()` when *all* columns were absent** — a partial-column
  row (some but not all required fields present) was dropped with zero
  record of why. Now logged per row with the specific missing column named.
- **A real, unrelated bug**: `trees.py`'s fire-behaviour model warned on any
  `surface_fire_intensity_model` value other than `'Thomas'`, including the
  correctly-specified `'Byram'`. Fixed so it only warns when neither valid
  model is specified.
- **A real crash bug found during final review**: `write_report()` raised
  `ValueError` whenever `plot_df` had more than one row per plot (exactly the
  shape `run_conpyro()`'s multi-weather-date results always have), so a real
  multi-date ConPyro run crashed at the very end and wrote no error report at
  all. Fixed by deduplicating on `unique_id` before building the identity
  lookup.

## Changes

### New module
- `src/fuel_analyst/components/error_handling.py` — `get_logger(form)`,
  `start_run()`, `write_report(out_path, plot_df=None)`, a run-guard decorator, a
  `_CollectingHandler`, and a `_ConsoleFormatter` that appends `(plot: <id>)`
  to console lines that carry a `unique_id`, so per-plot detail survives on
  console even though the underlying handler has no formatter of its own by
  default. `start_run()` attaches its own console `StreamHandler` only when
  the `fuel_analyst` logger and its propagation ancestors have no non-null
  handler. This preserves standalone console output after the collector
  suppresses Python's `logging.lastResort`, while respecting an embedding
  application's root/package handlers and avoiding duplicate messages. A
  lone `NullHandler` does not count as an output configuration.
  The run guard now guarantees that both handlers and the prior logger level
  are restored when an entry point raises before writing its report. Report
  row ordering is also type-safe when callers supply a mixture of numeric and
  string identifiers.
- `src/fuel_analyst/components/__init__.py` — registered `error_handling` in
  `__all__`.

### Migrated components (print → logger, one-for-one where console text was
truly a duplicate; preserved where it wasn't)
- `fuel_analyst.py` — writes `fuelanalyst_errors.csv` unconditionally at
  the end of every completed run; logs per-plot warnings for a missing
  selected-form folder and for ID mismatches in both directions. ID mismatch
  detection now uses set-backed membership checks while preserving first-seen
  warning order and suppressing duplicate warnings.
- `plants_regen.py` — `_calc_pc_flammable()`'s fallback logging replaces the
  removed `pc_flammable_note` column.
- `woody_debris.py` — `_resolve_spp_comp_type()`'s fallback logging replaces
  the removed `spp_comp_type_note` column; new logging for the previously
  silent `stand_spp_comp_woody`-missing case.
- `trees.py` — `_log_tree_density_issues()` replaces the old
  `tree_processing_issues.csv` system entirely; messages now include the
  specific failing radius class when relevant (e.g. `lgtree_plot_radius` vs.
  `smtree_plot_radius`) so two distinct failures on the same plot don't
  produce identical, undiagnosable report lines. Console summaries use the
  same `General Error` label as the CSV for unresolved plot IDs and do not
  count that group as a real plot.
- `extract_nrcan_wx.py` — logs missing lat/long (closing a gap from PR #9)
  and missing fire-season dates per plot; writes its own
  `<out_file_name>_errors.csv` alongside `wx_data.csv`.
- `fofem_mortality.py` — logs the per-row required-column dropna gap.
- `fofem_emissions.py` — logs the SoilFamily-missing run-level warning (lands
  on the `General Error` row, no `unique_id` available at that point).
- `run_conpyro.py` — wired as ConPyro's third entry point into
  `start_run()`/`write_report()`, so mortality/emissions warnings raised
  during a ConPyro run are actually captured.

### Tests
- `tests/unit/test_error_handling.py` — core module coverage: identity
  columns, `General Error` row ordering and cell numbering, console output
  during an active run, console plot-ID formatting, exception-safe run
  cleanup, missing-ID normalization, mixed-type identifier ordering, and
  conditional console behavior for root, package, and null handlers.
- `tests/regression/test_error_handling_duplicate_plot_ids.py` — the
  duplicate-`unique_id` crash fix.
- `tests/regression/test_trees_density_issue_logging.py` — the original
  tree-density invalid-radius defect, preserved through the migration.
- `tests/regression/test_fofem_mortality_dropna_gap.py` — the fofem_mortality
  partial-column dropna gap.
- `tests/regression/test_woody_debris_spp_comp_fallback.py` — the
  spp_comp_type fallback and the sibling-plot `stand_spp_comp_woody` gap.
- `tests/unit/test_run_conpyro_helpers.py` — the `run_conpyro()` wiring,
  including a two-weather-date fixture proving the duplicate-`unique_id`
  crash is actually gone on the real code path.
- `tests/unit/test_trees.py` — the radius-class-detail fix, asserting two
  different radius-class failures on the same plot produce distinguishable
  messages.
- `tests/integration/test_survey123_pipeline.py` — asserts
  `fuelanalyst_errors.csv`'s shape end-to-end against the real checked-in
  Survey123 fixture: identity columns present, `unique_id` unique, real
  ID-mismatch and orphan-tree-record warnings actually appear.
- Various other unit-test updates in `test_plants_regen.py`,
  `test_woody_debris.py`, `test_fuel_analyst.py`,
  `test_fofem_emissions_helpers.py`, `test_extract_nrcan_wx.py`.

### Docs
- `README.md` / `QUICK_START.md` — describe `fuelanalyst_errors.csv`
  instead of the removed `3_Trees/tree_processing_issues.csv`.
- `docs/superpowers/plans/2026-08-21-error-handling-module.md` and
  `docs/superpowers/specs/2026-08-21-error-handling-module-design.md` — the
  design spec and implementation plan this branch followed.

## Known follow-ups (not blocking, deliberately out of scope for this branch)

- Two `extract_nrcan_wx.py` migration tests are "documentation tests" that
  re-implement their production code inline rather than exercising
  `_extract_weather()` through a real fixture — real regression coverage for
  those two migrations is a follow-up.
- `docs/CODEBASE.md` (the whole-codebase architecture reference) hasn't been
  updated to mention the new `error_handling` module; `run_conpyro.py`'s and
  `extract_weather_data()`'s own `*_errors.csv` outputs aren't yet documented
  in README/QUICK_START.
- `fofem_gui_emissions.py` (an alternate emissions backend) still uses
  console-only `print()` for a per-plot error, and it runs inside
  `ProcessPoolExecutor` workers — it can't be migrated to this module without
  a queue-based log handler, which needs its own design.
- `_resolve_spp_comp_type()`'s "no source available anywhere" branch still
  logs nothing (only the "wrong declared source, valid fallback exists"
  branch does) — this is upstream of the original NaN duff/litter defect and
  is the highest-value remaining silent gap, but is out of this plan's spec.

## Test plan

- [x] Full suite: `tests/unit`, `tests/integration`, `tests/regression` —
      165 passed, 0 failures (baseline 129 before this branch; +2
      pc_flammable-fix tests already on master, +34 net from this branch)
- [x] Ran the real pipeline against the checked-in
      `examples/data/Survey123_Data` fixture and inspected
      `fuelanalyst_errors.csv` directly to confirm real ID-mismatch and
      orphan-tree-record warnings appear correctly, before writing the
      corresponding assertions.
- [x] Reproduced the `write_report()` duplicate-`unique_id` crash against
      the real `run_conpyro()` with a two-weather-date fixture before
      fixing it, then confirmed the fix resolves it on the same fixture.
- [x] Independent final whole-branch review (separate pass from per-task
      review) found and fixed 1 Critical bug, 3 Important issues, and 6
      bundled minor items; a scoped re-review confirmed every fix landed
      correctly with no new regressions.
