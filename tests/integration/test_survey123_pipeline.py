from pathlib import Path

import pandas as pd
import pytest

from fuel_analyst.fuel_analyst import fuel_analyst


@pytest.mark.integration
@pytest.mark.slow
def test_complete_survey123_pipeline_generates_owned_output_contracts(tmp_path):
    project_root = Path(__file__).resolve().parents[2]
    input_dir = project_root / 'examples' / 'data' / 'Survey123_Data'
    output_dir = tmp_path / 'fuel_analyst'

    fuel_analyst(
        in_dir=str(input_dir),
        out_dir=str(output_dir),
        surface_fire_intensity_model='Byram',
        gen_conpyro_df=True,
        gen_fofem_tree_df=True,
        gen_fofem_consume_df=True,
    )

    expected_outputs = [
        'master_fuel_df.csv', 'master_tree_df.csv', 'conpyro_df.csv',
        'fbp_prep_df.csv', 'fofem_tree_df.csv', 'fofem_consume_df.csv',
        '1_Plot_Attributes/survey_0.csv', '2_Plants_Regeneration/survey_0.csv',
        '3_Trees/survey_0.csv', '3_Trees/tree_processing_issues.csv',
        '4_Canopy_Cover/survey_0.csv',
        '5_Woody_Debris/survey_0.csv',
    ]
    assert all((output_dir / relative).is_file() for relative in expected_outputs)

    master = pd.read_csv(output_dir / 'master_fuel_df.csv', low_memory=False)
    conpyro = pd.read_csv(output_dir / 'conpyro_df.csv', low_memory=False)
    fbp = pd.read_csv(output_dir / 'fbp_prep_df.csv', low_memory=False)
    fofem_trees = pd.read_csv(output_dir / 'fofem_tree_df.csv', low_memory=False)
    tree_plots = pd.read_csv(output_dir / '3_Trees/survey_0.csv', low_memory=False)
    tree_issues = pd.read_csv(
        output_dir / '3_Trees/tree_processing_issues.csv', low_memory=False
    )

    assert master['unique_id'].is_unique
    assert set(conpyro['unique_id']) == set(master['unique_id'])
    assert set(fbp['unique_id']) == set(master['unique_id'])
    # The checked-in child forms contain documented orphan IDs. They are
    # retained in detailed outputs while the pipeline prints mismatch warnings.
    assert fofem_trees['# PlotId'].notna().all()
    assert set(fofem_trees['# PlotId']) & set(master['unique_id'])
    assert 'treatment_unit_other' not in master.columns
    assert 'treatment_unit_other' not in fbp.columns
    assert (master.filter(regex='kgpm2').fillna(0) >= 0).all().all()
    assert {
        'tree_density_complete', 'tree_density_issue_count',
        'tree_density_failed_records', 'tree_density_failed_stems',
        'tree_density_failed_classes', 'tree_density_issues',
    }.issubset(tree_plots.columns)
    assert {
        'issue_id', 'plot_global_id', 'issue_code', 'action_taken',
        'results_partial', 'message',
    }.issubset(tree_issues.columns)
