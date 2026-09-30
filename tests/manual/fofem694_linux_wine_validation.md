# Linux/Wine validation instructions (for an AI agent)

## Context

FuelAnalyst's `model_select='fof_gui'` emissions backend
(`src/fuel_analyst/components/fofem_gui_emissions.py`) shells out to the official USDA Forest
Service FOFEM 6.9.4 batch executable, `runfofem.exe` - a Windows x64 binary, tracked at
`src/fuel_analyst/supporting_data/fofem_694/runfofem.exe`. This was integrated and merged into
`master` (PR #37) with only Windows validated at the time.

**Linux/Wine support has since been implemented and validated once already**, on this same
branch (`test/linux-wine-runfofem-validation`), commit `19cfbfd`: on that host (Ubuntu 24.04.5,
Wine 9.0), a raw `binfmt_misc` check found no active Wine handler registered, so
`_run_runfofem()` now explicitly prepends `wine` to the command on Linux (and only passes the
Windows-only `subprocess.CREATE_NO_WINDOW` constant on Windows). All 8 real opt-in integration
tests and 33/33 targeted unit tests passed there. Read the full prior report first:
`tests/manual/fofem694_linux_wine_validation_results.md` - it explains what was tried, what
failed initially (a smoke-script `FOFEM_DATA` setup bug, unrelated to Wine/DLLs), and how it
was fixed.

**This round's job is narrower: confirm the same, already-implemented approach also works for
real on a different distribution/version** (you were given an Ubuntu 26 host). No FuelAnalyst
code change is expected this time - the Wine-prefix invocation is already in place and merged
onto this branch. If it turns out this host genuinely needs something different, that is a real
new finding to report (see "If it doesn't work"), not something to silently patch around.

Read `AGENTS.md` at the repository root before making any code changes: it governs commit
permission, function ordering, and docstring conventions, and it is binding here too.

## Step 1: Record your environment

- Linux distribution and version (`cat /etc/os-release`).
- Wine version (`wine --version`) and winetricks version (`winetricks --version`); install both
  if missing (`sudo apt install wine winetricks` on Debian/Ubuntu, or your distro's
  equivalent).
- Whether `.exe` files are registered with `binfmt_misc` on this host
  (`update-binfmts --display wine`, or `cat /proc/sys/fs/binfmt_misc/DOSWin` - exact name
  varies by distro). This is informational only this round: `_run_runfofem()` no longer
  depends on it, since it invokes `wine` explicitly.

Note any version differences from the prior run (Ubuntu 24.04.5, Wine 9.0, winetricks
20240105-2) - a newer winetricks in particular may no longer hit the SHA-256 mismatch warning
the prior report recorded during `vcrun2022` provisioning; if so, note that it's resolved.

## Step 2: Raw EXE-level Wine smoke test

```bash
bash tests/manual/fofem694_linux_wine_smoke.sh --include-mortality --keep
```

This script (read its header comment for full details) creates a fresh Wine prefix, runs a
consumption-mode batch call before installing the VC++ runtime (expected to fail), provisions
it via `winetricks -q vcrun2022`, then re-runs consumption/soil/mortality cases and checks exit
codes, output shape, and that no real batch errors were reported. Expected results, already
verified on both Windows and the prior Linux host: consumption `80,74,80` columns, soil
`86,80,86` columns, mortality succeeds. If any case fails here, investigate before assuming a
Wine/runtime problem - the prior round's own initial failure turned out to be a script setup
bug (missing `FOFEM_DATA`), not Wine or the VC++ runtime; that specific bug is already fixed,
but treat any *new* failure with the same "diagnose before you conclude" discipline described
in `docs/CODEBASE.md`'s "Verify Before Implementing Review Feedback" section.

## Step 3: FuelAnalyst-level validation

Install FuelAnalyst from this checkout (`pip install -e ".[fofem,test]"` is enough) into an
isolated location if you don't want to touch a pre-existing environment (the prior round used
`pip install --target ... --no-deps` into a scratch directory - see its report for the exact
approach). With the same Wine prefix from Step 2 (`WINEPREFIX`, `WINEARCH=win64`) and
`FUEL_ANALYST_FOFEM_DIR` pointed at the smoke script's kept `app` directory (or the tracked
`src/fuel_analyst/supporting_data/fofem_694` bundle), run:

```bash
FUEL_ANALYST_RUN_FOFEM694_TESTS=1 python -m pytest tests/integration/test_fofem694_official_batch.py tests/unit/test_fofem_gui_emissions.py -v
```

The integration test file's `pytestmark` still gates on `sys.platform == 'win32'` (unchanged
from before - confirmed by `git diff` against commit `19cfbfd`), so by default every test in it
will report **skipped** on Linux, not run. The prior round handled this by temporarily editing
that file's gate to check only the opt-in env var, running the suite, then restoring the
original file via a shell `EXIT` trap and confirming with `git diff` that no change remained.
Do the same here: **the loosened gate must not be committed**, only used transiently to prove
the real suite passes.

## If it doesn't work

- **`winetricks vcrun2022` fails, or `runfofem.exe` still fails after installing it, on this
  distro specifically.** Report the exact error and how it differs from the prior host's
  result. Do not silently re-add the VC++ DLLs to the bundle or either wheel - that packaging
  decision belongs to the user.
- **The already-implemented `wine`-prefixed invocation doesn't work here for some
  distro-specific reason** (e.g. a different Wine build behaves differently, a different
  `PATH`/environment assumption doesn't hold). Report exactly what differs and propose a fix if
  you have one - **do not implement or commit a further code change without asking the user
  first**, per `AGENTS.md`'s Version Control Permissions section (also reiterated in the
  repository's `.claude/CLAUDE.md`): no commit happens without the user's direct permission.

## Reporting back

`tests/manual/fofem694_linux_wine_validation_results.md` already exists (from the Ubuntu
24.04.5 round). **Append a new, clearly dated and distro-labeled section to the end of it -
do not overwrite or remove the existing Ubuntu 24.04.5 results.** Include:
- Your recorded environment (Step 1), and how it differs from the prior run.
- The full smoke-test output (Step 2).
- The real opt-in suite's result (Step 3), and confirmation the gate loosening was reverted
  (`git diff` showing no change to `tests/integration/test_fofem694_official_batch.py`).
- A clear verdict for this specific distro/version.

Stage the results file and any other touched files explicitly by name - do not
`git add -A`/`git add .`. **Do not commit, and do not push, without the user's explicit
permission for each**, exactly as `AGENTS.md` requires. Report what is ready and wait to be
told to commit.
