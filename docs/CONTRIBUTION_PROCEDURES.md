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
   All commits must be verified and authored by a human.
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

`photoload` supplies `scikit-image`, which the PhotoLoad tests import during
collection. Install the local `dependencies/conpyro` checkout when a change
needs ConPyro integration. If a change affects the optional FOFEM 6.9.4 batch
runtime, run the relevant opt-in integration tests on a supported host and
report their result. Document any skips, failures, or unavailable platform
checks; a failed full suite does not satisfy the passing-test checkbox below.

Rerun the suite after changes to the PR branch. Record the command, Python
version, operating system, latest commit SHA, and pass/skip counts in the PR
description. Do not treat a run against an earlier commit as validation of the
current PR head.

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

## GitHub Actions test schedule

The GitHub `Tests` workflow runs the full matrix on pushed `v*` release tags
or by deliberate manual dispatch. It does not run automatically on PRs. After
the tag-only workflow reaches `master`, enable the workflow in GitHub so these
triggers work. Keep it disabled while `master` still has a PR trigger. See
[the workflow](../.github/workflows/tests.yml) for its actual triggers and jobs.

Local testing and the checked PR record remain required regardless of whether
GitHub Actions runs. Coding agents must obtain direct permission before pushing
release tags.
