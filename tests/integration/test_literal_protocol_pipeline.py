from pathlib import Path
import shutil

import numpy as np
import pandas as pd
import pytest

from fuel_analyst.fuel_analyst import fuel_analyst


@pytest.mark.integration
@pytest.mark.parametrize('kind', ['csv', 'excel'])
def test_literal_protocol_labels_reach_expansion_and_model_inputs(tmp_path, kind):
    source = Path(__file__).resolve().parents[2] / 'examples/data/Survey123_Data'
    inputs = tmp_path / 'inputs'
    shutil.copytree(source, inputs)
    folder = inputs / '3_Trees'
    parents = pd.read_csv(folder / 'survey_0.csv')
    labels = ['001', 'NA'] + ['001'] * (len(parents) - 2)
    parents['sampling_protocol'] = labels
    parents['tree_large_present'] = 'Y'
    parents['tree_small_present'] = 'Y'
    parents['sapling_present'] = 'N'
    parents['lgtree_plot_radius'] = 11.28
    parents['smtree_plot_radius'] = 3.99
    parents['sapling_plot_radius'] = 3.99
    original = pd.read_csv(folder / 'tree_plot_2.csv')
    template = original.loc[original.tree_status.eq('L') & original.tree_dbh.notna()].iloc[0]
    rows = []
    for index, parent in enumerate(parents.GlobalID.iloc[:2]):
        row = template.copy()
        row.update(pd.Series({'GlobalID': f'literal-{index}', 'ParentGlobalID': parent,
                              'tree_species': 'FDI', 'tree_status': 'L', 'tree_dbh': 10.,
                              'tree_ht': 10., 'tree_cbh': 2., 'tree_dcbh': 1.,
                              'tree_dcy_class_cnfr': 1, 'tree_dcy_class_brdlf': np.nan,
                              'tree_ht_class': 2}))
        rows.append(row)
    tables = {'survey_0': parents, 'tree_plot_2': pd.DataFrame(rows),
              'sapling_1': pd.read_csv(folder / 'sapling_1.csv').iloc[:0]}
    if kind == 'csv':
        for name, frame in tables.items():
            frame.to_csv(folder / f'{name}.csv', index=False)
    else:
        with pd.ExcelWriter(folder / 'trees.xlsx') as writer:
            for name, frame in tables.items():
                frame.to_excel(writer, sheet_name=name, index=False)
        for path in folder.glob('*.csv'):
            path.unlink()
    output = tmp_path / 'output'
    settings = {'protocol_column': 'sampling_protocol',
                'protocol_overrides': {'001': {'large_tree_min': 9.}, 'NA': {}}}
    fuel_analyst(str(inputs), str(output), 'Byram', tree_sampling_params=settings,
                 gen_conpyro_df=True, gen_fofem_consume_df=True, gen_fofem_gui_app_tree_df=True)
    exported = pd.read_csv(output / '3_Trees/survey_0.csv', dtype={'sampling_protocol': str}, keep_default_na=False)
    assert exported.set_index('GlobalID').loc[parents.GlobalID, 'sampling_protocol'].tolist() == labels
    ids = exported.set_index('GlobalID').loc[parents.GlobalID.iloc[:2], 'unique_id'].tolist()
    trees = pd.read_csv(output / 'master_tree_df.csv').set_index('unique_id')
    # A 10 cm stem uses 400 m2 for the 9 cm protocol and 50 m2 for the default 12.5 cm protocol.
    assert trees.loc[ids, 'dens_ha'].tolist() == [25., 200.]
    conpyro = pd.read_csv(output / 'conpyro_df.csv').set_index('unique_id')
    assert conpyro.loc[ids, 'cfl_ovrstry'].gt(0).all()
    assert conpyro.loc[ids, 'stand_type'].notna().all()
    mortality = pd.read_csv(output / 'fofem_gui_app_tree_mortality_df.csv').set_index('PlotId')
    assert mortality.loc[ids, 'TreeExpansionFactor'].tolist() == pytest.approx([25 / 2.47105, 200 / 2.47105])
    consume = pd.read_csv(output / 'fofem_consume_si_df.csv').set_index('#PlotId')
    assert consume.loc[ids, 'CrownFoliage'].gt(0).all()
    errors = pd.read_csv(output / 'fuelanalyst_errors.csv')
    assert not errors.get('Trees', pd.Series(dtype=str)).fillna('').str.contains('sampling protocol').any()
