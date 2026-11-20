"""
Verifies the published pyfofem-fire-effects PyPI distribution against real FuelAnalyst
mortality/emissions wrapper call sites.

Every other pyfofem-touching test module in this repo registers a fake
sys.modules['pyfofem'] at collection time (see fofem_emissions.py's/fofem_mortality.py's own
tests), and once fuel_analyst.components.fofem_emissions/fofem_mortality import that fake,
Python's module cache keeps them bound to it for the rest of the process - regardless of
which order pytest happens to collect files in. _reload_real_pyfofem_bindings() purges those
cache entries and re-imports fresh before every test here, so this file always observes the
real installed package even when run as part of the full suite.
"""
import importlib.metadata
import os
import sys
import tomllib
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from packaging.requirements import Requirement

from fuel_analyst.components import fofem_units
from real_conpyro_fixtures import ROW, make_params, run_conpyro_module  # noqa: F401

pytestmark = pytest.mark.integration

try:
    importlib.metadata.version('pyfofem-fire-effects')
    _PYFOFEM_INSTALLED = True
except importlib.metadata.PackageNotFoundError:
    _PYFOFEM_INSTALLED = False

_BOTH_BACKENDS_REQUIRED = pytest.mark.skipif(
    not (_PYFOFEM_INSTALLED and sys.platform == 'win32' and os.environ.get('FUEL_ANALYST_RUN_FOFEM694_TESTS') == '1'),
    reason='requires installed PyFOFEM and opt-in Windows FOFEM 6.9.4 tests',
)

_CONSUME_ROW = {
    '#PlotId': 'p1',
    'Litter': 1.0, 'Duff': 2.0, 'DuffDepth': 3.0, 'Herbaceous': 0.5, 'Shrub': 0.1,
    'CrownFoliage': 0.4, 'CrownBranch': 0.5,
    'Region': 'InteriorWest', 'CoverGroup': 'GrassGroup', 'FuelCategory': 'Natural',
    'DuffMoisture': 20, 'wfl10HourMoisture': 6, 'wfl1000HourMoisture': 10,
    'wfl1Hour': 0.1, 'wfl10Hour': 0.2, 'wfl100Hour': 0.3,
    'wfl3_6S': 0.1, 'wfl6_9S': 0.1, 'wfl9_20S': 0.1, 'wfl20plusS': 0.1,
    'wfl3_6R': 0.1, 'wfl6_9R': 0.1, 'wfl9_20R': 0.1, 'wfl20plusR': 0.1,
    'fuel_bed_depth_m': 0.25,
}
_GUI_CONSUME_FIELDS = {
    'Season': 'Summer', 'remove_hereafter': None,
    'LitterLoad_ConsumEq1': -1, 'PctDuff_ConsumEq2': -1, 'DuffDepth_ConsumEq3': -1,
    'MSE_ConsumEq4': -1, 'Herb_ConsumEq5': -1, 'Shrub_ConsumEq6': -1,
}
_FIRE_ROW = {
    'unique_id': 'p1', 'wx_date': 20250615, 'hfi': 1500.0, 'flame_res_time_sec': 60.0,
    'flame_depth_m': 2.5,
    'instand_ws_mps': 2.0, 'temp': 20.0, 'mc_sa': 10.0, 'mc_dmc': 20.0, 'dc': 100.0, 'cfb': 0.1,
}


def _declared_pyfofem_specifier():
    """
    Read the fofem extra's pyfofem-fire-effects version specifier from pyproject.toml,
    so this test always validates against the single declared source of truth (currently
    ==0.1.2) instead of a hardcoded string that could drift from it.

    :return: packaging.specifiers.SpecifierSet for the declared pyfofem-fire-effects requirement.
    """
    pyproject_path = Path(__file__).resolve().parents[2] / 'pyproject.toml'
    with open(pyproject_path, 'rb') as f:
        pyproject = tomllib.load(f)
    fofem_reqs = pyproject['project']['optional-dependencies']['fofem']
    req = next(Requirement(r) for r in fofem_reqs if r.startswith('pyfofem-fire-effects'))
    return req.specifier


def _pyfofem_distribution_owns_file(file_path):
    """
    Check whether the installed pyfofem-fire-effects distribution's own RECORD/files metadata
    claims the given file, so an adjacent editable source checkout - which has no such
    distribution-owned files - is rejected without relying on any directory-name convention
    like 'site-packages'.

    :param file_path: Absolute path of the imported module file to check.
    :return: True if the resolved path matches one of the distribution's declared files.
    """
    distribution = importlib.metadata.distribution('pyfofem-fire-effects')
    if not distribution.files:
        return False
    resolved = Path(file_path).resolve()
    owned = {Path(entry.locate()).resolve() for entry in distribution.files}
    return resolved in owned


def _reload_real_pyfofem_bindings():
    """
    Purge any fake 'pyfofem' left in sys.modules by another test module's collection-time
    stub and re-import fuel_analyst's pyfofem-touching components fresh, so they rebind
    against the real installed distribution regardless of collection order.

    :return: (fofem_emissions module, fofem_mortality module), freshly reimported.
    """
    stale = [
        name for name in sys.modules
        if name == 'pyfofem' or name.startswith('pyfofem.')
        or name in ('fuel_analyst.components.fofem_emissions', 'fuel_analyst.components.fofem_mortality')
    ]
    for name in stale:
        del sys.modules[name]
    import fuel_analyst.components.fofem_emissions as fofem_emissions
    import fuel_analyst.components.fofem_mortality as fofem_mortality
    return fofem_emissions, fofem_mortality


@pytest.mark.windows_fofem694
@_BOTH_BACKENDS_REQUIRED
def test_both_backends_apply_moisture_limits_to_conpyro_results(run_conpyro_module, tmp_path, caplog):
    module = run_conpyro_module
    _reload_real_pyfofem_bindings()
    forest = dict(ROW, unique_id='P15 forest', sros_model=13, surface_fuel_type='forest')
    grass = dict(ROW, unique_id='P15 O-1b', sros_model=31, stand_type=10, surface_fuel_type='grass_herbs',
                 canopy_cover=0., ht_ovrstry_live=0., cbh_ovrstry=0., fsg=0., cbd_ovrstry=0., cfl_ovrstry=0.)
    cheney = dict(grass, unique_id='P15 Cheney', sros_model=32)
    wheat = dict(grass, unique_id='P15 wheat', sros_model=32, stand_type='WHEAT_BALED', surface_fuel_type=None)
    inputs = pd.DataFrame([
        dict(forest, time=1100, ffmc=98.), dict(forest, time=1200, dmc=15.), dict(forest, time=1300, dmc=None),
        dict(grass, time=1100, ffmc=98.), dict(grass, time=1200, dmc=15.), dict(grass, time=1300),
        dict(cheney, time=1100, ffmc=None), dict(cheney, time=1200), dict(wheat, time=1100, dmc=15.),
    ])
    source = tmp_path / 'weather.csv'
    inputs.to_csv(source, index=False)
    settings = make_params(module, sros_model='use_csv', terrain_wind=False, terrain_ffmc=False)
    settings['conpyro']['input_params'].update(time='use_csv', grass_curing=90)
    module.run_conpyro(str(tmp_path / 'fire'), str(source), fire_modelling_params=settings)

    keys = ['unique_id', 'time']
    fire_path = tmp_path / 'fire/fire_behavior/conpyro_results.csv'
    fire = pd.read_csv(fire_path).set_index(keys).sort_index()
    assert len(fire) == len(inputs)
    assert (fire['fire_type'] > 0).all()
    assert (fire['hfi'] > 0).all()
    assert fire.loc[('P15 O-1b', 1100), 'mc_sa'] == pytest.approx(2.805281)
    assert fire.loc[('P15 forest', 1100), 'mc_sa'] == pytest.approx(4.997120)
    assert fire.loc[[('P15 forest', 1200), ('P15 O-1b', 1200), ('P15 wheat', 1100)], 'mc_dmc'].tolist() == pytest.approx(
        [218.230653] * 3
    )
    assert fire.loc[('P15 O-1b', 1300), ['mc_sa', 'mc_dmc']].tolist() == pytest.approx([8.440790, 165.292276])
    assert pd.isna(fire.loc[('P15 forest', 1300), 'mc_dmc'])
    assert pd.isna(fire.loc[('P15 Cheney', 1100), 'mc_sa'])
    # Simulate reloading an earlier fire CSV without the wheat duff derivation.
    reloaded = fire.copy()
    reloaded.loc[('P15 wheat', 1100), 'mc_dmc'] = np.nan
    reloaded.reset_index().to_csv(fire_path, index=False)

    consume_csv = tmp_path / fofem_units.consume_filename('SI')
    pd.DataFrame([
        {**_CONSUME_ROW, **_GUI_CONSUME_FIELDS, '#PlotId': plot} for plot in inputs['unique_id'].unique()
    ]).to_csv(consume_csv, index=False)
    accepted = {('P15 forest', 1100), ('P15 O-1b', 1300), ('P15 Cheney', 1200)}
    reported = []
    settings['conpyro']['run_model'] = False
    for backend in ('pyfofem', 'fof_gui'):
        caplog.clear()
        settings['fofem_emissions'].update(run_model=True, model_select=backend, emissions_units='SI')
        output = tmp_path / backend
        module.run_conpyro(
            str(output), str(fire_path), in_fofem_consume_csv_path=str(consume_csv), fire_modelling_params=settings,
        )
        result = pd.read_csv(output / 'conpyro_emissions_results.csv').set_index(keys).sort_index()
        pd.testing.assert_frame_equal(result[['hfi', 'mc_sa', 'mc_dmc']], fire[['hfi', 'mc_sa', 'mc_dmc']])
        assert set(result['DufCon_kgpm2'].dropna().index) == accepted
        if backend == 'pyfofem':
            assert result['BurnupError'].dropna().tolist() == [0.] * len(accepted)
        else:
            assert 'fofem_gui_error' not in result
        sent = pd.read_csv(output / 'fofem_emissions/fofem_emissions_results.csv')
        assert set(sent[['#PlotId', 'time']].itertuples(index=False, name=None)) == accepted
        warnings = sorted((r.unique_id, r.issue_code, r.getMessage()) for r in caplog.records if r.levelname == 'WARNING')
        assert {(plot, code) for plot, code, _ in warnings} == {
            ('P15 forest', 'fofem_duff_moisture_invalid'), ('P15 O-1b', 'fofem_duff_moisture_invalid'),
            ('P15 wheat', 'fofem_duff_moisture_invalid'), ('P15 O-1b', 'fofem_10h_moisture_invalid'),
            ('P15 Cheney', 'fofem_10h_moisture_invalid'),
        }
        assert len(warnings) == 5
        reported.append(warnings)
    assert reported[0] == reported[1]


@pytest.mark.skipif(not _PYFOFEM_INSTALLED, reason='pyfofem-fire-effects is not installed (optional fofem extra)')
def test_installed_distribution_is_the_pypi_wheel():
    """The active pyfofem import must resolve to an installed pyfofem-fire-effects wheel."""
    fofem_emissions, _ = _reload_real_pyfofem_bindings()

    version = importlib.metadata.version('pyfofem-fire-effects')
    specifier = _declared_pyfofem_specifier()
    assert specifier.contains(version), (
        f'installed pyfofem-fire-effects=={version} does not satisfy the declared range '
        f'{specifier} in pyproject.toml (an adjacent editable checkout can report an '
        f'out-of-range version, e.g. 0.1.0)'
    )

    pyfofem_file = fofem_emissions.fofem.__file__
    assert _pyfofem_distribution_owns_file(pyfofem_file), (
        f'{pyfofem_file} is not one of the files recorded by the installed '
        f'pyfofem-fire-effects distribution - this indicates an adjacent editable source '
        f'checkout is shadowing the published wheel, not the wheel itself'
    )

    import pyfofem
    for name in (
            'DEFAULT_CONSUMPTION_VARS', 'EXPANDED_CONSUMPTION_VARS',
            'TOTAL_DURATION_CONSUMED_VARS', 'SOIL_HEAT_VARS', 'EQUATION_VARS', 'ERROR_VARS',
    ):
        assert hasattr(pyfofem, name), f'pyfofem package is missing expected export: {name}'


@pytest.mark.skipif(not _PYFOFEM_INSTALLED, reason='pyfofem-fire-effects is not installed (optional fofem extra)')
def test_process_emissions_real_pyfofem_wheel_produces_expected_schema(tmp_path):
    """process_emissions() against the real installed wheel, not a monkeypatched stand-in."""
    fofem_emissions, _ = _reload_real_pyfofem_bindings()

    consume_csv = tmp_path / fofem_units.consume_filename('SI')
    pd.DataFrame([_CONSUME_ROW]).to_csv(consume_csv, index=False)
    fire_csv = tmp_path / 'fire.csv'
    pd.DataFrame([_FIRE_ROW]).to_csv(fire_csv, index=False)
    out_dir = tmp_path / 'out'

    result = fofem_emissions.process_emissions(
        plot_wx_fire_csv_path=str(fire_csv),
        plot_id_col_name='unique_id',
        fofem_consume_csv_path=str(consume_csv),
        out_dir=str(out_dir),
        emissions_units='SI',
        return_df=True,
    )

    assert len(result) == 1
    assert 'LitPre_kgpm2' in result.columns
    assert 'FlaDur_sec' in result.columns
    assert 'BurnupError' in result.columns
    assert result['BurnupError'].iloc[0] == 0
    assert (out_dir / 'fofem_emissions_results.csv').is_file()


@pytest.mark.skipif(not _PYFOFEM_INSTALLED, reason='pyfofem-fire-effects is not installed (optional fofem extra)')
def test_process_mortality_real_pyfofem_wheel_produces_expected_schema(tmp_path):
    """process_mortality() against the real installed wheel's run_fofem_mortality/mort_crnsch."""
    _, fofem_mortality = _reload_real_pyfofem_bindings()

    plot_dir = tmp_path / 'in'
    plot_dir.mkdir()
    plot_csv = plot_dir / 'plot_fire.csv'
    pd.DataFrame({
        'unique_id': ['p1'], 'wx_date': [20250615], 'hfi': [1500.0], 'fire_type': ['surface'],
        'temp': [20.0], 'instand_ws_mps': [2.0],
        'canopy_cover': [50.0], 'ht_ovrstry_live': [20.0], 'fsg': [1.0], 'ws': [3.0],
    }).to_csv(plot_csv, index=False)

    tree_csv = plot_dir / 'trees.csv'
    pd.DataFrame({
        'unique_id': ['p1', 'p1'], 'status': ['L', 'L'], 'dens_live_ha': [10.0, 10.0],
        'spp': ['FD', 'FD'], 'dbh': [30.0, 25.0], 'ht': [20.0, 18.0],
        'crown_depth': [5.0, 4.0], 'bark_thick': [1.5, 1.2], 'ba_live_ha': [1.0, 2.0],
    }).to_csv(tree_csv, index=False)

    merged_tree_df, plot_fire_df = fofem_mortality.process_mortality(
        plot_wx_fire_csv_path=str(plot_csv),
        fofem_tree_csv_path=str(tree_csv),
        out_dir=str(tmp_path / 'out'),
        return_dfs=True,
    )

    assert 'mortality_crnsch_prop' in merged_tree_df.columns
    assert 'prob_mortality_crnsch_prop' in merged_tree_df.columns
    probs = merged_tree_df['prob_mortality_crnsch_prop'].to_numpy()
    assert np.all((probs >= 0.0) & (probs <= 1.0))
    assert 'tree_dead_ba_crnsch_m2pha' in plot_fire_df.columns
    assert (tmp_path / 'out' / 'fofem_tree_mortality_results.csv').is_file()


@pytest.mark.skipif(not _PYFOFEM_INSTALLED, reason='pyfofem-fire-effects is not installed (optional fofem extra)')
def test_pyfofem_burnup_threshold_uses_areal_intensity(tmp_path):
    fofem_emissions, _ = _reload_real_pyfofem_bindings()
    consume_csv = tmp_path / fofem_units.consume_filename('SI')
    pd.DataFrame([_CONSUME_ROW]).to_csv(consume_csv, index=False)
    fire_csv = tmp_path / 'fire.csv'
    pd.DataFrame([
        dict(_FIRE_ROW, hfi=99.75, flame_depth_m=2.5, wx_date=20250615),
        dict(_FIRE_ROW, hfi=100.25, flame_depth_m=2.5, wx_date=20250616),
    ]).to_csv(fire_csv, index=False)

    result = fofem_emissions.process_emissions(
        plot_wx_fire_csv_path=str(fire_csv), plot_id_col_name='unique_id',
        fofem_consume_csv_path=str(consume_csv), out_dir=str(tmp_path / 'out'), return_df=True,
    )

    assert result['burnup_ign_intensity_kWpm2'].tolist() == pytest.approx([39.9, 40.1])
    assert result['BurnupError'].tolist() == [10, 0]


@pytest.mark.windows_fofem694
@_BOTH_BACKENDS_REQUIRED
def test_wheat_and_grass_duff_consumption_match_across_backends(tmp_path):
    from fuel_analyst.components import fofem_gui_emissions

    fofem_emissions, _ = _reload_real_pyfofem_bindings()
    consume_csv = tmp_path / fofem_units.consume_filename('SI')
    pd.DataFrame([
        {**_CONSUME_ROW, **_GUI_CONSUME_FIELDS, '#PlotId': plot} for plot in ('grass', 'wheat')
    ]).to_csv(consume_csv, index=False)
    fire_csv = tmp_path / 'fire.csv'
    pd.DataFrame([
        dict(_FIRE_ROW, unique_id='grass', stand_type=10, dmc=28.493, mc_dmc=np.nan),
        dict(_FIRE_ROW, unique_id='wheat', stand_type=20, dmc=28.493, mc_dmc=np.nan),
    ]).to_csv(fire_csv, index=False)

    backend_loads = {}
    for backend, expected in [(fofem_emissions, 0.265710), (fofem_gui_emissions, 0.266763)]:
        result = backend.process_emissions(
            str(fire_csv), 'unique_id', str(consume_csv), str(tmp_path / backend.__name__), return_df=True,
        ).set_index('#PlotId')
        assert result['DuffMoisture'].tolist() == pytest.approx([165.292276] * 2)
        grass, wheat = result.loc[['grass', 'wheat'], 'DufCon_kgpm2']
        assert grass == pytest.approx(expected, rel=1e-3, abs=1e-8)
        assert wheat == pytest.approx(grass, rel=1e-3, abs=1e-8)
        backend_loads[backend] = [grass, wheat]

    assert backend_loads[fofem_gui_emissions] == pytest.approx(
        backend_loads[fofem_emissions], rel=1e-3, abs=0.005 / fofem_units.LOAD_CONV_FACTOR,
    )
