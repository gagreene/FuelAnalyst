# Linux/Wine validation instructions (for an AI agent)

## Context

FuelAnalyst's `model_select='fof_gui'` emissions backend
(`src/fuel_analyst/components/fofem_gui_emissions.py`) shells out to the official USDA Forest
Service FOFEM 6.9.4 batch executable, `runfofem.exe` - a Windows x64 binary, tracked at
`src/fuel_analyst/supporting_data/fofem_694/runfofem.exe`. This was integrated and merged into
`master` (PR #37) with only Windows validated. `development/plans/2026-09-29-runfofem-wheel-integration.md`'s
final section, "Final step: Linux/Wine validation", was deliberately deferred until a Linux
host was available - that host is what you are running on now.

FuelAnalyst deliberately does not bundle the Microsoft Visual C++ runtime DLLs
(`msvcp140.dll`, `vcruntime140.dll`, `vcruntime140_1.dll`) anywhere - not in the source bundle,
not in either Python wheel. On Windows this is a documented, separately-installed
prerequisite. Under Wine, the equivalent is provisioning the Windows VC++ runtime inside the
Wine prefix, typically via `winetricks vcrun2022`. **Do not claim Linux/Wine support until
this succeeds for real** - that is the whole point of this validation.

You are on branch `test/linux-wine-runfofem-validation` (created from `master` at commit
`2bc493b`). Read `AGENTS.md` at the repository root before making any code changes: it governs
commit permission, function ordering, and docstring conventions, and it is binding here too.

## What "validating this" means, concretely

There are two layers to validate, in order:

1. **The EXE itself runs correctly under Wine.** This does not touch FuelAnalyst's Python code
   at all - it is a raw, direct invocation of `runfofem.exe`, in an isolated Wine prefix, both
   before and after installing the VC++ runtime. A script that automates this is provided:
   `tests/manual/fofem694_linux_wine_smoke.sh`.
2. **FuelAnalyst's own Python code can invoke that EXE correctly on Linux**, i.e.
   `subprocess.run([exe_path, ...])` in `fofem_gui_emissions._run_runfofem()` actually reaches
   Wine and runs the executable, without any FuelAnalyst code change. This depends on the
   Linux distribution having registered Wine as a `binfmt_misc` handler for Windows PE
   executables (Debian/Ubuntu's `wine-binfmt` package does this automatically when `wine` is
   installed via the distro's package manager). **This is a genuinely open question** - nobody
   has verified it in this project yet. Your job includes finding out and reporting it clearly,
   not silently patching around it if it doesn't work (see "If it doesn't work" below).

## Step 1: Record your environment

Before anything else, record:
- Linux distribution and version (`cat /etc/os-release`).
- Wine version (`wine --version`).
- Whether `winetricks` is installed (`winetricks --version`); if not, install it
  (`sudo apt install wine winetricks` on Debian/Ubuntu, or your distro's equivalent).
- Whether `wine-binfmt` (or your distro's equivalent Wine `binfmt_misc` registration package)
  is installed, and whether `.exe` files are registered with `binfmt_misc`:
  `cat /proc/sys/fs/binfmt_misc/DOSWin` or `update-binfmts --display wine` (exact path/name
  varies by distro - report what you find).

## Step 2: Raw EXE-level Wine smoke test

Run:
```bash
bash tests/manual/fofem694_linux_wine_smoke.sh --include-mortality
```

This script (read its header comment for full details):
- Creates a **fresh** Wine prefix (win64) in a temp directory.
- Runs a consumption-mode batch call **before** installing the VC++ runtime and expects it to
  fail (this documents the "before" state the plan asks for).
- Installs the runtime via `winetricks -q vcrun2022`.
- Re-runs consumption, soil, and mortality batch calls and checks exit codes, output file
  shape, and that no real batch errors were reported (only the standard preamble) - using the
  same input format (including the three required `#EFG-*` switches) and expected column
  counts already verified against this exact bundled EXE on Windows.

Record the full console output. If any case fails, do not modify the script's expectations to
make it pass - investigate first, the same way `docs/CODEBASE.md`'s "Verify Before
Implementing Review Feedback" pattern describes for this repository generally: confirm whether
the failure is a genuine Wine/runtime problem (report it) or a mistake in the script itself
(only then propose a fix, and say so explicitly in your report).

## Step 3: FuelAnalyst-level validation (the open question)

Set up a Python environment with FuelAnalyst installed from this checkout
(`pip install -e ".[fofem]"` is enough - you do not need the full `[all]` extras for this).
Point `FUEL_ANALYST_FOFEM_DIR` at the same bundle used above
(`src/fuel_analyst/supporting_data/fofem_694`, or the `app` directory the smoke script created
if you kept it with `--keep`), using the **same Wine prefix** you already provisioned with
`vcrun2022` (`export WINEPREFIX=...` before running Python, matching whatever prefix path you
used in Step 2).

Then run FuelAnalyst's opt-in real-EXE test suite:
```bash
FUEL_ANALYST_RUN_FOFEM694_TESTS=1 python -m pytest tests/integration/test_fofem694_official_batch.py -v
```

Note: this test file currently gates on `sys.platform == 'win32'` (see its own top-of-file
`pytestmark`), so on Linux every test in it will report **skipped**, not run, even with the
env var set. That gate exists because nobody had validated Linux support yet. Do **not** just
remove the gate to force the tests to run - first confirm whether `_run_runfofem()`'s
`subprocess.run([exe_path, ...])` actually reaches Wine transparently on your host (via
`binfmt_misc`, see Step 1), by testing it directly:

```python
import subprocess
result = subprocess.run(['/absolute/path/to/runfofem.exe'], capture_output=True, text=True)
print(result.returncode, result.stdout, result.stderr)
```

If this executes the Windows binary (even if it exits non-zero for lack of arguments - that
still proves execution happened, as opposed to `FileNotFoundError`/`OSError: [Errno 8] Exec
format error`, which means the kernel tried and failed to run it as a native Linux binary),
Linux support works with **no FuelAnalyst code change** - report that clearly, and only then
is it reasonable to temporarily loosen the test file's `win32` gate locally to run the real
suite and confirm end to end, before reverting that gate change (do not commit a loosened
gate without the user's explicit say-so; see "If it doesn't work" below for why).

## If it doesn't work

Two distinct failure modes are possible, and they need different responses:

- **`winetricks vcrun2022` fails to install, or `runfofem.exe` still fails after installing
  it.** This is the scenario the plan explicitly anticipated: *"if runtime provisioning is
  unreliable, reconsider app-local DLLs as a separate packaging decision."* Report the exact
  error. Do not silently re-add the DLLs to the bundle or either wheel - that is a packaging
  decision for the user to make, not something to reverse unilaterally.
- **The raw EXE runs fine under Wine directly, but FuelAnalyst's own `subprocess.run()` call
  cannot reach it** (e.g. `binfmt_misc` isn't registered on this host, or isn't a portable
  enough mechanism to guarantee on other users' machines). The fix would be to have
  `_run_runfofem()` detect non-Windows platforms and invoke `['wine', exe_path, ...]` instead
  of `[exe_path, ...]`. **Propose this in your report; do not implement and commit it without
  asking the user first** - per `AGENTS.md`'s Version Control Permissions section (also
  reiterated in the repository's `.claude/CLAUDE.md`), no commit happens without the user's
  direct permission, and a change to a code path this central deserves their sign-off, not just
  yours.

## Reporting back

Whatever you find, write it up in `tests/manual/fofem694_linux_wine_validation_results.md`
(create it; it does not exist yet) with:
- Your recorded environment (Step 1).
- The full smoke-test output (Step 2), pass/fail per case, and the exact pre-provisioning
  failure text.
- Whether `subprocess.run([exe_path, ...])` reaches Wine transparently on this host (Step 3),
  and if you ran the real opt-in suite with a temporarily loosened gate, its result - but
  revert the gate loosening before finishing, and say so explicitly in the results file.
- A clear verdict: does Linux/Wine support work today, with no code change; does it need the
  `wine`-prefix code change described above; or does it not work at all (and why).

Stage the results file and the smoke script (if you touched it) explicitly by name - do not
`git add -A`/`git add .`. **Do not commit, and do not push, without the user's explicit
permission for each**, exactly as `AGENTS.md` requires. Report what is ready and wait to be
told to commit.
