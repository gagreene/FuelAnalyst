# FuelAnalyst tests

The test suite uses three behavioral tiers:

```text
tests/
├── unit/          Fast, isolated tests for functions and components
├── integration/   Tests spanning multiple FuelAnalyst components
├── regression/    Tests that preserve behavior for previously fixed defects
├── manual/        Smoke-test scripts for the FOFEM 6.9.4 runtime (run by hand, not by pytest)
├── test_data/     Small, version-controlled inputs and golden outputs
├── results/       Generated test output (ignored by Git)
└── utils/         Shared assertions and test helpers
```

Install FuelAnalyst with its test dependencies:

```shell
python -m pip install -e ".[test,photoload]"
```

Run the complete suite:

```shell
python -m pytest -vv
```

The GitHub `Tests` workflow runs the suite on Python 3.11 to 3.14 on Windows, macOS, and Linux, plus
minimum-dependency, FOFEM, lock-check, and clean-wheel jobs. It runs on `v*` tags or by manual dispatch, not on
pull requests (a PR runs only the "No AI attribution" workflow). The eight tests that run the official FOFEM
6.9.4 executable are opt-in on Windows: set `FUEL_ANALYST_RUN_FOFEM694_TESTS=1`.

Run one tier or omit slow tests:

```shell
python -m pytest tests/unit -vv
python -m pytest tests/integration -vv
python -m pytest tests/regression -vv
python -m pytest -m "not slow" -vv
```

Integration and regression tests are also registered as pytest markers, so
they can be selected with `-m integration` or `-m regression`.

Tests should use pytest's `tmp_path` fixture for disposable output. Only stable,
reviewable fixtures and golden outputs belong in `test_data`; runtime artifacts
belong in `results`.
