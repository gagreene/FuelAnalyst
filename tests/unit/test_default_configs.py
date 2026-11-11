import importlib
import os
from pathlib import Path
import subprocess
import sys

import pytest

from fuel_analyst.components import _default_configs as defaults


def _fresh_import(code):
    environment = os.environ.copy()
    environment['PYTHONPATH'] = str(Path(__file__).resolve().parents[2] / 'src')
    result = subprocess.run([sys.executable, '-c', code], env=environment,
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(('cpu_count', 'expected'), [(None, 1), (1, 1), (8, 7)])
def test_cpu_count_fallback_in_fresh_process(cpu_count, expected):
    _fresh_import(
        f'import os; os.cpu_count = lambda: {cpu_count!r}; '
        'from fuel_analyst.components._default_configs import default_fire_modelling_dict; '
        f'assert default_fire_modelling_dict["num_workers"] == {expected}'
    )


def test_defaults_import_does_not_load_numeric_or_model_dependencies():
    _fresh_import(
        'import sys; import fuel_analyst.components._default_configs; '
        'assert not {"pandas", "numpy", "pyfofem", "fuel_analyst.fuel_analyst", '
        '"fuel_analyst.run_conpyro"}.intersection(sys.modules)'
    )


def test_ffmc_terrain_effects_default_to_false():
    assert defaults.default_fire_modelling_dict['conpyro']['input_params']['model_terrain_effects_on_ffmc'] is False


def test_public_default_names_reexport_the_shared_objects():
    api = importlib.import_module('fuel_analyst.fuel_analyst')
    for name in ['default_stand_summary_dict', 'default_woody_debris_dict',
                 'default_conpyro_dict', 'default_fofem_consume_dict', 'default_tree_sampling_dict']:
        assert getattr(api, name) is getattr(defaults, name)
    runner = importlib.import_module('fuel_analyst.run_conpyro')
    assert runner.default_fire_modelling_dict is defaults.default_fire_modelling_dict
    gui = importlib.import_module('fuel_analyst.components.fofem_gui_emissions')
    assert gui.default_season_start_dict is defaults.default_season_start_dict


def test_pyfofem_season_default_reexports_shared_object():
    pytest.importorskip('pyfofem')
    emissions = importlib.import_module('fuel_analyst.components.fofem_emissions')
    assert emissions.default_season_start_dict is defaults.default_season_start_dict


def test_sampling_component_does_not_import_pipeline_to_resolve_defaults():
    _fresh_import(
        'import sys; from fuel_analyst.components.tree_sampling import normalize_tree_sampling_params; '
        'assert normalize_tree_sampling_params(None)["dbh_thresholds_cm"]["large_tree_min"] == 12.5; '
        'assert "fuel_analyst.fuel_analyst" not in sys.modules'
    )