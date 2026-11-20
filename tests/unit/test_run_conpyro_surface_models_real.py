"""The surface rate of spread models that run_conpyro() documents must behave as documented with the real ConPyro.

The numerical checks use expectations that do not come from the code they test: the values of the previous vendored
ConPyro (upstream 29a2145, FuelAnalyst 0.3.0), which upstream's 0.2.0 renumbering must leave unchanged for the default
model 13 and move from model 20 to model 21 for the legacy mountain pine beetle curve (with FFMC terrain adjustment explicitly enabled), and the documented formula of
model 20 (0.2 times the wind speed in km/h, in m/min). The terrain scaling of models 4, 9c, and 18c and the other
numerical details of the changed models are pinned by upstream's own test suite and are not repeated here.
"""
import numpy as np
import pytest

from real_conpyro_fixtures import WINDS, run, run_conpyro_module  # noqa: F401  (the fixture is used by name)

# Surface and head fire rates of spread (m/min) of the default model 13 for the winds in WINDS, as given by 0.3.0
_DEFAULT_SROS = [0.627, 0.9233, 1.5667, 3.5864, 12.1486]
_DEFAULT_HROS = [0.627, 0.9243, 1.6164, 9.1773, 15.1747]
# Surface rate of spread of the legacy mountain pine beetle curve, which was model 20 in 0.3.0 and is model 21 now
_MPB_SROS = [5.387, 6.2104, 8.3064, 13.8738, 37.4216]
_RUNS_WITH_TERRAIN = [1, 2, 3, 4, 9, 11, 12, 13, 18, 19, 21, '9c', '11c', '18c']
_NEEDS_TERRAIN_OFF = [16, 17, 20, 'r20']


@pytest.mark.parametrize('label, number', [('9c', 9), ('11c', 11), ('18c', 18)])
def test_a_model_label_gives_the_results_of_its_number(run_conpyro_module, tmp_path, label, number):
    (tmp_path / 'label').mkdir()
    (tmp_path / 'number').mkdir()
    by_label = run(run_conpyro_module, tmp_path / 'label', sros_model=label)
    by_number = run(run_conpyro_module, tmp_path / 'number', sros_model=number)
    assert by_label['sros'].tolist() == by_number['sros'].tolist()


@pytest.mark.parametrize('model', _RUNS_WITH_TERRAIN)
def test_every_documented_surface_model_runs_with_terrain_wind_adjustment(run_conpyro_module, tmp_path, model):
    result = run(run_conpyro_module, tmp_path, sros_model=model)
    assert len(result) == len(WINDS)
    assert np.isfinite(result[['sros', 'hros']]).all().all()
    assert (result['sros'] >= 0).all()


def test_ffmc_terrain_default_matches_disabled_and_accepts_enabled_override(run_conpyro_module, tmp_path):
    for name in ['default', 'disabled', 'enabled']:
        (tmp_path / name).mkdir()
    default = run(run_conpyro_module, tmp_path / 'default')
    disabled = run(run_conpyro_module, tmp_path / 'disabled', terrain_ffmc=False)
    enabled = run(run_conpyro_module, tmp_path / 'enabled', terrain_ffmc=True)
    assert default['sros'].tolist() == disabled['sros'].tolist()
    assert not np.allclose(default['sros'], enabled['sros'])
    assert enabled['sros'].tolist() == pytest.approx(_DEFAULT_SROS, abs=5e-4)


@pytest.mark.parametrize('model', [20, 'r20'])
def test_model_20_is_the_wind_heuristic_of_0_2_times_the_wind_speed(run_conpyro_module, tmp_path, model):
    result = run(run_conpyro_module, tmp_path, sros_model=model, terrain_wind=False)
    assert result['sros'].tolist() == pytest.approx([0.2 * ws for ws in WINDS], abs=1e-6)


def test_model_21_is_the_legacy_mountain_pine_beetle_curve_that_was_model_20(run_conpyro_module, tmp_path):
    result = run(run_conpyro_module, tmp_path, sros_model=21, terrain_ffmc=True)
    assert result['sros'].tolist() == pytest.approx(_MPB_SROS, abs=5e-4)


@pytest.mark.parametrize('model', _NEEDS_TERRAIN_OFF)
def test_models_without_a_terrain_wind_extension_run_with_terrain_wind_adjustment_off(run_conpyro_module, tmp_path, model):
    result = run(run_conpyro_module, tmp_path, sros_model=model, terrain_wind=False)
    assert len(result) == len(WINDS)
    assert np.isfinite(result['sros']).all()


@pytest.mark.parametrize('model', _NEEDS_TERRAIN_OFF)
def test_models_without_a_terrain_wind_extension_stop_with_the_documented_error(run_conpyro_module, tmp_path, model):
    with pytest.raises(ValueError, match='no terrain wind extension'):
        run(run_conpyro_module, tmp_path, sros_model=model)


def test_the_default_surface_model_gives_the_results_of_0_3_0(run_conpyro_module, tmp_path):
    result = run(run_conpyro_module, tmp_path, terrain_ffmc=True)
    assert result['sros'].tolist() == pytest.approx(_DEFAULT_SROS, abs=5e-4)
    assert result['hros'].tolist() == pytest.approx(_DEFAULT_HROS, abs=5e-4)
