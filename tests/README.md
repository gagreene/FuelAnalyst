# FuelAnalyst tests

The test suite uses three behavioral tiers:

```text
tests/
├── unit/          Fast, isolated tests for functions and components
├── integration/   Tests spanning multiple FuelAnalyst components
├── regression/    Tests that preserve behavior for previously fixed defects
├── test_data/     Small, version-controlled inputs and golden outputs
├── results/       Generated test output (ignored by Git)
└── utils/         Shared assertions and test helpers
```

Install FuelAnalyst with its test dependencies:

```shell
python -m pip install -e ".[test]"
```

Run the complete suite:

```shell
python -m pytest -vv
```

GitHub Actions runs this command on Python 3.12 after installing the `test` and
`photoload` extras.

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
