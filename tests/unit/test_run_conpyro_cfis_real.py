"""The real vendored ConPyro must run the CFIS crown fire initiation model (cfo_model 10) through run_conpyro().

The other CFIS tests replace ConPyro with a stub, so they cannot see a failure inside it. After the vendored ConPyro was
refreshed to upstream 6086a4f, every CFIS run with array inputs failed with 'assignment destination is read-only'.
The helpers (and why run_conpyro is imported lazily) are in real_conpyro_fixtures.py.
"""
import numpy as np

from real_conpyro_fixtures import WINDS, run, run_conpyro_module  # noqa: F401  (the fixture is used by name)


def test_run_conpyro_runs_the_cfis_model_on_array_inputs(run_conpyro_module, tmp_path):
    result = run(run_conpyro_module, tmp_path, cfo_model=10)
    assert len(result) == len(WINDS)
    assert np.isfinite(result['hros']).all()
    assert set(result['fire_type']) <= {1, 2, 3}


def test_run_conpyro_runs_a_mix_of_cfis_and_other_crown_fire_models(run_conpyro_module, tmp_path):
    result = run(run_conpyro_module, tmp_path, cfo_model='use_csv', cfo_models=[10, 5, 10, 5, 10])
    assert len(result) == len(WINDS)
    assert np.isfinite(result['hros']).all()
