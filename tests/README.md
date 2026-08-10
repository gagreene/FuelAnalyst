# FuelAnalyst tests

The test suite follows the same tiered structure used by PyroCell:

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

Run one tier or omit slow tests:

```shell
python -m pytest tests/unit -vv
python -m pytest tests/integration -vv
python -m pytest tests/regression -vv
python -m pytest -m "not slow" -vv
```

Tests should use pytest's `tmp_path` fixture for disposable output. Only stable,
reviewable fixtures and golden outputs belong in `test_data`; runtime artifacts
belong in `results`.
