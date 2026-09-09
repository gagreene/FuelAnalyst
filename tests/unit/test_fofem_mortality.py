import logging
import sys
import types

import numpy as np
import pandas as pd
import pytest

from fuel_analyst.components.fofem_mortality import filter_live_trees

_ISSUE_CODE = 'fofem_mortality_missing_status_column'


def test_filter_live_trees_keeps_only_live_positive_density_rows():
    tree_df = pd.DataFrame({
        'unique_id': ['p1', 'p1', 'p1'],
        'status': ['L', 'D', 'L'],
        'dens_live_ha': [2.47105, 0.0, 0.0],
    })
    logger = logging.getLogger('fuel_analyst.components.fofem_mortality')
    result = filter_live_trees(tree_df, logger, _ISSUE_CODE)
    assert result['status'].tolist() == ['L']
    assert result['dens_live_ha'].tolist() == [2.47105]


def test_filter_live_trees_missing_status_logs_and_falls_back(caplog):
    tree_df = pd.DataFrame({
        'unique_id': ['p1', 'p1'],
        'dens_live_ha': [2.47105, 0.0],
    })
    logger = logging.getLogger('fuel_analyst.components.fofem_mortality')
    with caplog.at_level(logging.ERROR, logger='fuel_analyst.components.fofem_mortality'):
        result = filter_live_trees(tree_df, logger, _ISSUE_CODE)

    assert result['dens_live_ha'].tolist() == [2.47105]
    matching = [r for r in caplog.records if getattr(r, 'issue_code', None) == _ISSUE_CODE]
    assert len(matching) == 1


def test_process_mortality_writes_unit_qualified_final_columns(tmp_path, monkeypatch):
    """The final rename map applies to both returned DataFrames and both written CSVs."""
    fake_package = types.ModuleType('pyfofem')
    fake_package.pyfofem = types.SimpleNamespace(
        run_fofem_mortality=lambda mort_function, params: np.array([0.9, 0.1])
    )
    monkeypatch.setitem(sys.modules, 'pyfofem', fake_package)

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

    from fuel_analyst.components.fofem_mortality import process_mortality

    merged_tree_df, plot_fire_df = process_mortality(
        plot_wx_fire_csv_path=str(plot_csv),
        fofem_tree_csv_path=str(tree_csv),
        out_dir=str(tmp_path / 'out'),
        return_dfs=True,
    )

    for df in (merged_tree_df, plot_fire_df):
        for old_name in ('mortality_crnsch', 'prob_mortality_crnsch', 'tree_dead_ba_crnsch'):
            assert old_name not in df.columns

    assert 'mortality_crnsch_prop' in merged_tree_df.columns
    assert 'prob_mortality_crnsch_prop' in merged_tree_df.columns
    assert merged_tree_df['prob_mortality_crnsch_prop'].tolist() == pytest.approx([0.9, 0.1])
    assert merged_tree_df['tree_dead_crnsch'].tolist() == [1, 0]
    # Tree 1 (prob 0.9 -> dead) contributes its ba_live_ha (1.0) to the killed total.
    assert merged_tree_df['tree_dead_ba_crnsch_m2pha'].tolist() == pytest.approx([1.0, 0.0])
    assert plot_fire_df['tree_dead_ba_crnsch_m2pha'].tolist() == pytest.approx([1.0])
    assert plot_fire_df['prop_dead_ba_crnsch'].tolist() == pytest.approx([1.0 / 3.0])

    tree_csv_out = pd.read_csv(tmp_path / 'out' / 'fofem_tree_mortality_results.csv')
    severity_csv_out = pd.read_csv(tmp_path / 'out' / 'fofem_severity_results.csv')
    assert 'tree_dead_ba_crnsch_m2pha' in tree_csv_out.columns
    assert 'mortality_crnsch_prop' in tree_csv_out.columns
    assert 'tree_dead_ba_crnsch_m2pha' in severity_csv_out.columns
    assert 'tree_dead_ba_crnsch' not in tree_csv_out.columns
    assert 'tree_dead_ba_crnsch' not in severity_csv_out.columns
