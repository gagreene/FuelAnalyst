from pathlib import Path
import shutil

import pandas as pd
import pytest

from fuel_analyst.fuel_analyst import fuel_analyst


def _inputs(tmp_path, conflict=False):
    source = Path(__file__).resolve().parents[2] / 'examples/data/Survey123_Data'
    target = tmp_path / 'inputs'
    shutil.copytree(source, target)
    path = target / '3_Trees/survey_0.csv'
    parents = pd.read_csv(path)
    for field in ('tree_large_present', 'tree_small_present', 'sapling_present'):
        parents[field] = 'N'
    parents.to_csv(path, index=False)
    for table in ('tree_plot_2', 'sapling_1'):
        path = target / f'3_Trees/{table}.csv'
        if conflict and table == 'tree_plot_2':
            frame = pd.read_csv(path).iloc[:1].copy()
            frame['ParentGlobalID'] = parents.GlobalID.iloc[0]
            frame['tree_species'] = 'UNLISTED'
            frame['tree_dbh'] = 'invalid'
            frame.to_csv(path, index=False)
        else:
            path.unlink()
    return target


@pytest.mark.integration
@pytest.mark.parametrize('conflict', [False, True])
def test_confirmed_absence_reaches_model_inputs_without_phantom_trees(tmp_path, conflict):
    source = _inputs(tmp_path, conflict)
    output = tmp_path / 'out'
    fuel_analyst(
        str(source), str(output), 'Byram', gen_conpyro_df=True,
        gen_fofem_consume_df=True, gen_fofem_gui_app_tree_df=True,
    )
    master = pd.read_csv(output / 'master_fuel_df.csv', low_memory=False)
    assert len(master) == 20
    assert master['stand_dens_tpha_live_sum'].eq(0).all()
    assert master['stand_ba_m2pha_live_sum'].eq(0).all()
    assert master['stand_ht_m_live_mean'].isna().all()
    assert pd.read_csv(output / 'master_tree_df.csv').empty
    assert pd.read_csv(output / 'fofem_gui_app_tree_mortality_df.csv').empty
    conpyro = pd.read_csv(output / 'conpyro_df.csv')
    assert len(conpyro) == 20
    assert conpyro[['cfl_ovrstry', 'cfl_midstry']].eq(0).all(axis=None)
    consume = pd.read_csv(output / 'fofem_consume_si_df.csv')
    assert len(consume) == 20
    report = pd.read_csv(output / 'fuelanalyst_errors.csv')
    messages = report.get('Trees', pd.Series(dtype='str')).dropna().astype(str)
    assert not messages.str.contains('not in tree_parameters|radius|sampling protocol').any()
    if conflict:
        assert messages.str.contains('skipped').sum() == 1
    else:
        assert messages.empty
