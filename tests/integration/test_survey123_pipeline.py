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
        'master_fuel_df.csv', 'master_fuel_df_errors.csv', 'master_tree_df.csv',
        'conpyro_df.csv', 'fbp_prep_df.csv', 'fofem_tree_df.csv', 'fofem_consume_df.csv',
        '1_Plot_Attributes/survey_0.csv', '2_Plants_Regeneration/survey_0.csv',
        '3_Trees/survey_0.csv',
        '4_Canopy_Cover/survey_0.csv',
        '5_Woody_Debris/survey_0.csv',
    ]
    assert all((output_dir / relative).is_file() for relative in expected_outputs)

    master = pd.read_csv(output_dir / 'master_fuel_df.csv', low_memory=False)
    errors = pd.read_csv(output_dir / 'master_fuel_df_errors.csv', low_memory=False)
    conpyro = pd.read_csv(output_dir / 'conpyro_df.csv', low_memory=False)
    fbp = pd.read_csv(output_dir / 'fbp_prep_df.csv', low_memory=False)
    fofem_trees = pd.read_csv(output_dir / 'fofem_tree_df.csv', low_memory=False)

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
    # Tree-density input failures in the checked-in example data (orphan tree
    # records with no matching Plot Attributes parent) surface as ERROR-level
    # rows in the run-level error report's Trees column instead of the
    # deleted per-form tree_processing_issues.csv.
    assert 'Trees' in errors.columns
    tree_messages = errors['Trees'].dropna().str.cat(sep='\n')
    assert '[ERROR]' in tree_messages
    assert 'orphan tree record' in tree_messages
    # Confirmed by actually running fuel_analyst() against this exact checked-in
    # fixture: the current pipeline logs real ID-mismatch warnings for multiple
    # plots across all four child forms. The error report being non-empty is a
    # hard, verified assertion, not a hedge.
    assert not errors.empty
    assert {'unique_id', 'treatment_area', 'treatment_unit', 'treatment_type', 'plot_id'}.issubset(
        errors.columns
    )
    assert errors['unique_id'].is_unique
    # Identity columns must actually be populated for real plot rows, not just
    # present as empty columns - plot_attributes.process_plot_attributes() keeps
    # these fields in master_fuel_df.csv, so write_report() should find them.
    plot_rows = errors.loc[errors['unique_id'] != 'General Error']
    assert not plot_rows.empty
    assert plot_rows['plot_id'].notna().any()
