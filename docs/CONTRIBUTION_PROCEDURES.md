# Contribution procedures

These procedures apply to changes proposed for FuelAnalyst. The root
[`README.md`](../README.md#contributing) covers the shorter contributor checklist.

## Branches, commits, and pushes

1. Create a focused work branch from its intended PR base under the versioned
   routing below. Keep unrelated edits, generated results, temporary files,
   and local reference data out of the change. Check the staged diff before
   committing.
2. Use commits that describe the actual change. Do not add AI authorship or
   attribution statements to commit messages, PR titles, or PR descriptions.
   All commits must be verified and authored by a human. The `No AI attribution`
   workflow checks every PR's title, description, and commit messages and fails
   on any such statement, so a PR cannot merge until it is removed. Install the
   matching local check with `bash scripts/install_git_hooks.sh`, which rejects
   the commit before it exists.
3. Coding agents must obtain the user's **direct permission** before creating
   or amending any commit. They must obtain **separate direct permission** before
   pushing a commit, branch, or tag. Permission to edit, test, stage, prepare a
   PR, or continue work does not grant permission to commit or push. Do not
   automate commits or pushes without explicit user authorization for each action.

## Versioned merge routing

Version numbers use `MAJOR.MINOR.PATCH` (for example, `1.2.3`). Route every
versioned change as follows:

| Change for the next version | Work branch starts from | PR target |
| --- | --- | --- |
| Major or minor version change | `pre_release` | `pre_release` |
| Patch version change | `master` | `master` |

Create `pre_release` before the first major or minor PR if it does not yet
exist; do not target `master` as a substitute. Patch changes go only to
`master`. When the major or minor release is ready, the repository owner
reviews a PR from `pre_release` into `master` and merges it. This promotion
requires a PR just like every other branch merge. Release tags use the
`vMAJOR.MINOR.PATCH` form (for example, `v1.2.3`) expected by the release-tag
test workflow. No version tag exists yet.

## Local tests before every PR merge

Run the full default test suite locally against the **latest PR commit** before
merging. Set up an environment with the test dependencies and the optional
packages needed for test collection. One route is:

```shell
python -m pip install -e ".[test,photoload,fofem]"
python -m pytest -vv
```

Or reproduce the locked environment with uv:

```shell
uv sync --locked --extra test --extra photoload --extra fofem --group dev
uv run --no-sync pytest -vv
```

`photoload` supplies `scikit-image`, which the PhotoLoad tests import during
collection. ConPyro is vendored in the package, so nothing extra is needed for
ConPyro integration. If a change affects the optional FOFEM 6.9.4 batch
runtime, run the relevant opt-in integration tests on a supported host and
report their result. Document any skips, failures, or unavailable platform
checks; a failed full suite does not satisfy the passing-test checkbox below.

Rerun the suite after changes to the PR branch. Record the command, Python
version, operating system, latest commit SHA, and pass/skip counts in the PR
description. Do not treat a run against an earlier commit as validation of the
current PR head.

## Dependency changes and `uv.lock`

- `pyproject.toml` is the only hand-edited dependency declaration. `uv.lock` is generated: never
  edit it.
- After any dependency change, run `uv lock`, commit both files, and confirm `uv lock --check`
  passes. Record the check in the PR description. The `Tests` workflow also runs a `lock-check`
  job on tags and manual dispatch.
- To update one package: `uv lock --upgrade-package <name>`. To refresh everything:
  `uv lock --upgrade`. Then run the full suite and review the lock diff: changed versions, added or
  removed packages, and sources (every third-party package must come from `https://pypi.org/simple`;
  no Git, path, or private-index sources; only FuelAnalyst itself is recorded as the editable
  project `.`).
- A numerical change after an upgrade is scientific behavior, not a tooling update. Review it as
  such before merging.
- The locked environment supports Windows and Linux (x86_64) on Python 3.11 through 3.14, and
  **macOS 15 or newer on Apple Silicon**. Intel macOS is not supported. These limits apply to the
  lock only; installing the package with pip is not affected.
- The minimum-dependency floor job is separate from the lock. It installs with
  `uv pip install --resolution lowest-direct`, which resolves every direct dependency to the lowest
  version its `>=` bound in `pyproject.toml` allows, so there is no second list of floors to keep
  in sync: change a floor in `pyproject.toml` and the job tests the new one. Raise a floor only
  after confirming the exact version installs on every supported Python and OS.
- `uv pip` ignores `UV_PROJECT_ENVIRONMENT`. Pass `--python <environment>/python` when using it so
  it cannot change another environment.

## Pull requests and merge review

- Every branch merge requires a PR. Follow the target branch in the versioned
  routing above. Do not merge or fast-forward work branches directly into
  either target.
- Every PR description must include this checkbox and the test record:

  ```markdown
  - [ ] Full default test suite passed locally against this PR's latest commit.

  Commit SHA:
  Python / OS:
  Command:
  Result (passed / skipped):
  Additional opt-in tests or limitations:
  ```

- Check the box only after the full default suite passes on the latest commit.
  If tests were not run or did not pass, leave it unchecked and explain why.
  **Do not merge a PR while the box is unchecked.** Reviewers must verify the
  recorded SHA and results before merging.
- Describe changes to scientific assumptions, units, schemas, and regression
  risks in the PR. Add or update tests for FuelAnalyst-owned behavior; avoid
  tests that merely repeat behavior owned by external dependencies.

The checkbox is currently a reviewer-enforced rule, not a GitHub-required
status check. A checked box records the author's local test result; it does not
replace review of the test output or prove that other operating systems passed.

## Adding a plant species

`plants_regen` converts each recorded surface plant species to biomass through
`src/fuel_analyst/supporting_data/plant_photoload.csv`. A species code that is not in the table adds
no biomass to any functional group. `fuel_analyst()` prints a warning for each affected plot and
records it in `fuelanalyst_errors.csv`, in the Plants and Regeneration column. To add a species,
open a patch PR (see the versioned merge routing above) that does the following:

1. Add one row to `plant_photoload.csv`:
   - `name`: a unique code, exactly as it is entered in `pc_species_N` or `pc_species_N_other`
     (codes are case-sensitive).
   - `label`: `[Group] CODE - common name`. The group must be `Herb/Forb`, `Grass`, `Shrub`, or
     `Moss/Lichen`. `plants_regen` reads the functional group from this text, not from `func_group`.
   - `pl_code`: the PhotoLoad series whose equation estimates the biomass: `AMAL`, `MARE`, `SYAL`,
     `VAGL`, `VASC`, `ARLA`, `CARU`, `FESC`, or `XETE`, or `MOSS` or `TREE` for zero biomass. Use
     the series of the closest listed species in growth form, starting with the same genus.
   - `scientific_name`, `func_group`, `pl_code_alt` (an alternative series considered), `other_name`,
     and `notes` are informational. Complete them for the new row.
2. Copy the file unchanged to
   `docs/survey123/survey123_forms/CWC Fuels 2 - Plants and Regen/media/plant_photoload.csv`. The
   Survey123 form builds its species list from that copy, so the two files must stay identical, and
   the form must be republished before field crews can select the new species.
3. Pass the full test suite. `tests/unit/test_plants_regen.py` checks that names are unique, every
   series has an equation, and every label starts with a valid group.
4. State the species and the series chosen in the PR, with the reason. The series is a scientific
   assumption, so describe it as one.

Until a PR is merged, a user can enter the species under a listed code of similar growth form, or
add the row to a local copy of the file.

## GitHub Actions test schedule

The GitHub `Tests` workflow runs the full matrix on pushed `v*` release tags
or by deliberate manual dispatch. It does not run automatically on PRs. After
the tag-only workflow reaches `master`, enable the workflow in GitHub so these
triggers work. Keep it disabled while `master` still has a PR trigger. See
[the workflow](../.github/workflows/tests.yml) for its actual triggers and jobs.

Local testing and the checked PR record remain required regardless of whether
GitHub Actions runs. Coding agents must obtain direct permission before pushing
release tags.
