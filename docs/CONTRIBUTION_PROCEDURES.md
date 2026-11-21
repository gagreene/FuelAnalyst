# Contribution procedures

These procedures apply to changes proposed for FuelAnalyst. The root
[`README.md`](../README.md#contributing) covers the shorter contributor checklist.

## Updating plant_photoload.csv and tree_parameters.csv

Two tables in `src/fuel_analyst/supporting_data/` hold the species lookups: `plant_photoload.csv` (surface
plant species to biomass equations) and `tree_parameters.csv` (tree species to height, biomass, fuel, and FOFEM
parameters). Both are keyed on the species codes recorded in the field. A change to either is a scientific
change as well as a data change. In addition to the steps below, follow the rest of this document: branch from
`pre_release`, open a PR into `pre_release` (see the merge routing), pass the full test suite, and describe the
source and the effect of the change in the PR.

### Adding a plant species

`plant_photoload.csv` also holds two rows that are not species: `NO_SPP` (no further species) and `OTHER` (a species
that is not in the list). The Plants form builds its species choices from this file, so crews can select them only
while the rows are present. Do not remove them. They have no `pl_code` or `func_group`, and their labels carry no
group.

A plant species code that is not in `plant_photoload.csv` adds no biomass to any functional group.
`fuel_analyst()` prints a warning for each affected plot and records it in `fuelanalyst_errors.csv`, in the
Plants and Regeneration column. A species recorded as `OTHER` with no alternate code in `pc_species_N_other` and no
functional group is reported in the same way, since it cannot be identified. An `OTHER` species that is not in the
table but has a functional group is estimated instead, as the average of all table species of that group at its cover
and height, and logs a `plant_species_other_estimated` warning; adding the species to the table replaces the
estimate. To add a species:

1. Add one row to `plant_photoload.csv`:
   - `name`: a unique code, exactly as it is entered in `pc_species_N` or `pc_species_N_other` (codes are
     case-sensitive).
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
   the form must be republished before field crews can select the new species. If the new row has a
   `func_group` value that no other row has, also add it to the `list_plant_func_group` choices on the
   form's `choices` sheet: that list is the unique `func_group` values except `Tree`, which the form offers
   when a crew selects `OTHER`, and a test fails until the two match.
3. Pass the full test suite. `tests/unit/test_plants_regen.py` checks that names are unique, every
   species has a series with an equation and a label that starts with a valid group, that the two
   non-species rows are present, that the form copy is identical, and that the form's functional-group
   choices match the table.
4. State the species and the series chosen in the PR, with the reason. The series is a scientific
   assumption, so describe it as one.

Until a PR is merged, a crew can select `OTHER` and enter the species in `Other Species` and its
functional group, which FuelAnalyst uses to estimate the biomass, or a user can add the row to a local copy of the file.

### Adding a tree species

A tree or sapling species code that is not in `tree_parameters.csv` cannot be calculated, so `fuel_analyst()` leaves
that plot out of the tree calculations, logs an error that names the code and the table it came from, and
continues with the other plots. The error appears in the Trees column of `fuelanalyst_errors.csv`, and the plot's
tree results are empty. When Trees is ticked in `form_select`, that plot also has no row in the ConPyro modelling
input or the FOFEM consumption file, since its canopy fuels were never calculated. A code in `SPECIES_CD_1` to
`SPECIES_CD_6` of the plot table that is not in the file is
reported in the ConPyro Attributes column, and that plot's stand type is empty. To add a species:

1. Add one row to `tree_parameters.csv`. `Species` is the code exactly as it is entered in the forms
   (case-sensitive) and must be unique, and `sppNumCD` is a unique numeric code. The code reads these
   columns, so each needs a value for the new species:
   - `TreeType`: `conifer` or `broadleaf`. This is the only record of whether a species is a conifer, and it
     sets both the tree type and the decay-class table used in the biomass calculation.
   - `Temesgen_M2a`, `Temesgen_M2b`, and `Temesgen_M2c`: the height-diameter model 2 coefficients.
   - The twelve `BIOMASS_CNBE_DBH-HT_B{wood,bark,branches,foliage}{1,2,3}` coefficients: the CNBE tree
     biomass equations.
   - `FOFEM_sppCD` and `FOFEM_BrkThck_Vsp`: the FOFEM species code and bark thickness coefficient.
   - `ConPyro_StandType`: `D`, `P`, or `S`, as in the existing rows.
   - The twelve `SG_*` specific gravity values, `Duff_BD`, and `Litter_BD`.

   The remaining columns (labels, reference text, and coefficient groups for equations the code does not
   call, such as Temesgen model 7, the Cruz crown fuel equations, and the canopy cover equation) are
   informational. Fill them in where the source gives them and name the source in the `*_Ref` columns. Take
   each coefficient from a published equation for the species or its closest relative, and say in the PR
   where every group came from.
2. Add the species to the Survey123 forms: the `list_tree_species` choices of every form that uses it (Plot
   Attributes, Plants and Regeneration, Trees, and Woody Debris), and a row (`Species`, `Species_Label`,
   `Type`) in `docs/survey123/survey123_forms/CWC Fuels 3 - Trees/media/Tree_Types.csv`, which the Trees form
   uses to calculate the tree type. Keep the species lists of the four forms equal and bump the `version` of
   each changed form (`tests/unit/test_survey123_species_lists.py` checks the lists against each other and
   against `tree_parameters.csv`); `FD` and `PL` stay out of every list on purpose, because the forms offer
   the coastal and interior codes (`FDC`, `FDI`, `PLC`, `PLI`), and a shrub (`TreeType` of `shrub`, such as
   `JD` and `JH`) is not a tree: it gets no row in `Tree_Types.csv` and is offered on the Woody Debris form
   only, where its stems add small-diameter woody fuel. The manual-entry forms in
   `docs/survey123/manual_entry_forms/` hold no species list. Republish the forms.
3. Pass the full test suite, and add a test for the new species. The rows `JD`, `JH`, and `DECAYED`
   intentionally have no allometric coefficients (they are shrubs and a decay placeholder), so a check of
   the table must skip them.

### Changing existing values

A corrected coefficient, specific gravity, or series assignment changes the results of every plot with that
species. Give the old and new values and the source in the PR, rerun `examples/run_fuel_analyst_conpyro_demo.py`
to report which example outputs change, and add a line to `docs/RELEASE_NOTES.md`.

## Branches, commits, and pushes

1. Create a focused work branch from its intended PR base under the merge
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

## Merge routing and releases

Version numbers use `MAJOR.MINOR.PATCH` (for example, `1.2.3`). Two branches live
permanently, and neither may ever be deleted:

- `master` holds released code only. Every release tag is on `master`.
- `pre_release` is the integration branch for all work toward the next release,
  whatever its size.

Route every change as follows:

| Change | Work branch starts from | PR target |
| --- | --- | --- |
| Any change toward the next release (fix, feature, documentation, or data) | `pre_release` | `pre_release` |
| Hotfix for a serious defect in released code | `master` (`hotfix/<name>`) | `master` |

Do not classify a change as a patch, minor, or major change when its PR is opened.
The owner chooses the version when the release is promoted, from the combined
changes: anything that alters inputs, forms, results, or documented behavior is at
least a minor release, and only fixes with no such change make a patch release.

### Release notes

A PR on `pre_release` that changes behavior adds its bullet under an `Unreleased`
heading at the top of `docs/RELEASE_NOTES.md` (create the heading if it is absent)
and does not change the package version. Breaking changes, and the action users need
to take, go in a `Breaking changes and action needed` block of the same section.

### Releasing

1. Confirm that `pre_release` holds everything intended for the release and that
   every PR in it has its test record.
2. Open a promotion PR from `pre_release` into `master`. Along with a hotfix PR, it is
   the only PR that changes the version: it bumps `pyproject.toml`, regenerates
   `uv.lock` (see Dependency changes and `uv.lock` below), and renames the `Unreleased`
   heading of `docs/RELEASE_NOTES.md` to the new version. The description of the
   promotion PR carries the test record for the head of `pre_release`.
3. After the owner merges it, run the `Tests` workflow on the full Linux, macOS, and
   Windows matrix before tagging, then create an annotated tag on `master`. Release
   tags use the `vMAJOR.MINOR.PATCH` form (for example, `v1.2.3`) expected by the
   release-tag test workflow.
4. `master` is now one merge commit ahead of `pre_release`: merge `master` back into
   `pre_release` through a PR, so that the two branches stay equal after every release.

### Hotfixes

When a serious defect is found in released code and cannot wait for the next release:

1. Branch `hotfix/<name>` from `master`, fix the defect with a regression test, and
   open a PR into `master`. PRs that are open on `pre_release` are not blocked or
   changed by this.
2. The hotfix PR is its own release: it bumps the patch version, regenerates
   `uv.lock`, and adds a section for the new version to `docs/RELEASE_NOTES.md`. After
   the owner merges it, run the `Tests` workflow and tag, as for any release.
3. Merge `master` back into `pre_release` through a PR. Resolve any conflict with
   unreleased work in that PR, where the author of the fix is best placed to do it;
   the open feature PRs then only need "Update branch". If `pre_release` already
   holds a different fix for the same defect, keep the correct one and say so in the PR.

## Keeping the technical reference current

[`TECHNICAL_REFERENCE.md`](TECHNICAL_REFERENCE.md) documents every configuration setting and default (section 2), every
equation and output variable (section 3), and the `run_conpyro()` workflow (section 4). A change that alters a documented
default, equation, parameter, output column, or message must update this page in the same PR and keep its section, table,
equation, and figure numbering consistent.

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

- Every branch merge requires a PR, including promotions, hotfixes, and the
  merge of `master` back into `pre_release`. Follow the target branch in the
  merge routing above. Do not merge or fast-forward work branches directly into
  either permanent branch.
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

## GitHub Actions test schedule

The GitHub `Tests` workflow runs the full matrix on pushed `v*` release tags
or by deliberate manual dispatch. It does not run automatically on PRs; the only workflow a PR triggers is the
`No AI attribution` check. After
the tag-only workflow reaches `master`, enable the workflow in GitHub so these
triggers work. Keep it disabled while `master` still has a PR trigger. See
[the workflow](../.github/workflows/tests.yml) for its actual triggers and jobs.

Local testing and the checked PR record remain required regardless of whether
GitHub Actions runs. Coding agents must obtain direct permission before pushing
release tags.
