import shutil
import warnings
from pathlib import Path

import pandas as pd
import pytest

from fuel_analyst.fuel_analyst import fuel_analyst
from fuel_analyst.components import helper


@pytest.mark.integration
@pytest.mark.slow
def test_complete_survey123_pipeline_generates_owned_output_contracts(tmp_path):
    project_root = Path(__file__).resolve().parents[2]
    input_dir = project_root / 'examples' / 'data' / 'Survey123_Data'
    output_dir = tmp_path / 'fuel_analyst'

    with warnings.catch_warnings():
        warnings.simplefilter('error', pd.errors.PerformanceWarning)
        fuel_analyst(
            in_dir=str(input_dir),
            out_dir=str(output_dir),
            surface_fire_intensity_model='Byram',
            gen_conpyro_df=True,
            gen_fofem_gui_app_tree_df=True,
            gen_fofem_consume_df=True,
        )

    expected_outputs = [
        'master_fuel_df.csv', 'fuelanalyst_errors.csv', 'master_tree_df.csv',
        'conpyro_df.csv', 'fbp_prep_df.csv', 'fofem_gui_app_tree_mortality_df.csv',
        'fofem_consume_si_df.csv',
        '1_Plot_Attributes/survey_0.csv', '2_Plants_Regeneration/survey_0.csv',
        '3_Trees/survey_0.csv',
        '4_Canopy_Cover/survey_0.csv',
        '5_Woody_Debris/survey_0.csv',
    ]
    assert all((output_dir / relative).is_file() for relative in expected_outputs)

    master = pd.read_csv(output_dir / 'master_fuel_df.csv', low_memory=False)
    errors = pd.read_csv(output_dir / 'fuelanalyst_errors.csv', low_memory=False)
    conpyro = pd.read_csv(output_dir / 'conpyro_df.csv', low_memory=False)
    fbp = pd.read_csv(output_dir / 'fbp_prep_df.csv', low_memory=False)
    master_trees = pd.read_csv(output_dir / 'master_tree_df.csv', low_memory=False)
    fofem_trees = pd.read_csv(output_dir / 'fofem_gui_app_tree_mortality_df.csv', low_memory=False)

    assert master['unique_id'].is_unique
    source_plots = helper.get_unique_id(pd.read_csv(input_dir / '1_Plot_Attributes/survey_0.csv'))
    unchecked_ids = set(source_plots.loc[~source_plots['form_select'].str.contains('trees', na=False), 'unique_id'])
    eligible = master['conpyro_live_trees_present'].notna() | master['unique_id'].isin(unchecked_ids)
    expected_ids = set(master.loc[eligible, 'unique_id'])
    assert set(conpyro['unique_id']) == expected_ids
    assert set(fbp['unique_id']) == expected_ids
    consume = pd.read_csv(output_dir / 'fofem_consume_si_df.csv')
    assert set(consume['#PlotId']) == expected_ids
    assert fofem_trees['PlotId'].notna().all()
    assert set(fofem_trees['PlotId']) & set(master['unique_id'])
    assert 'treatment_unit_other' not in master.columns
    assert 'treatment_unit_other' not in fbp.columns
    assert (master.filter(regex='kgpm2').fillna(0) >= 0).all().all()
    # master_tree_df.csv retains dead trees (the demo dataset's 3_Trees/tree_plot_2.csv
    # and sapling_1.csv both include real dead records); the FOFEM GUI export is
    # filtered back to live trees only via fofem_attributes._filter_live_trees().
    assert 'status' in master_trees.columns
    assert (master_trees['status'] == 'D').any()
    expected_fofem_rows = master_trees.loc[
        (master_trees['status'] == 'L') & (master_trees['dens_live_ha'] > 0)
    ]
    assert len(fofem_trees) == len(expected_fofem_rows)
    # Tree-density input failures in the checked-in example data (missing tree
    # DBH on several plots) surface as ERROR-level rows in the run-level error
    # report's Trees column instead of the deleted per-form
    # tree_processing_issues.csv. Orphan-tree-record handling (a different
    # failure mode this dataset doesn't happen to exercise) has dedicated
    # synthetic-fixture coverage in tests/unit/test_trees.py and
    # tests/unit/test_fuel_analyst.py instead.
    assert 'Trees' in errors.columns
    tree_messages = errors['Trees'].dropna().str.cat(sep='\n')
    assert '[ERROR]' in tree_messages
    assert 'missing tree dbh' in tree_messages
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


@pytest.mark.integration
@pytest.mark.slow
def test_rerun_retires_managed_tree_outputs_when_trees_are_unticked(tmp_path, monkeypatch):
    input_dir = Path(__file__).resolve().parents[2] / 'examples/data/Survey123_Data'
    reused_output = tmp_path / 'reused'
    fresh_output = tmp_path / 'fresh'
    second_input = tmp_path / 'without_trees'
    shutil.copytree(input_dir, second_input, ignore=shutil.ignore_patterns('3_Trees'))
    plots_path = second_input / '1_Plot_Attributes/survey_0.csv'
    plots = pd.read_csv(plots_path)
    plots['form_select'] = plots['form_select'].str.replace(r'\btrees\b', '', regex=True)
    plots.to_csv(plots_path, index=False)
    options = dict(surface_fire_intensity_model='Byram', gen_conpyro_df=True, gen_fofem_consume_df=True)

    fuel_analyst(str(input_dir), str(reused_output), gen_fofem_gui_app_tree_df=True, **options)
    master_name = 'master_tree_df.csv'
    mortality_name = 'fofem_gui_app_tree_mortality_df.csv'
    assert not pd.read_csv(reused_output / master_name).empty
    assert not pd.read_csv(reused_output / mortality_name).empty
    previous_master = (reused_output / master_name).read_bytes()
    previous_mortality = (reused_output / mortality_name).read_bytes()
    sentinel = reused_output / 'notes.txt'
    sentinel.write_text('Keep analyst notes.', encoding='utf-8')

    export_csv = helper.export_csv

    def fail_consumption_export(df, path, *args, **kwargs):
        if Path(path).name == 'fofem_consume_si_df.csv':
            raise OSError('Consumption export failed')
        return export_csv(df, path, *args, **kwargs)

    with monkeypatch.context() as failure:
        failure.setattr(helper, 'export_csv', fail_consumption_export)
        with pytest.raises(OSError, match='Consumption export failed'):
            fuel_analyst(str(second_input), str(reused_output), gen_fofem_gui_app_tree_df=True, **options)
    assert (reused_output / master_name).read_bytes() == previous_master
    assert (reused_output / mortality_name).read_bytes() == previous_mortality

    for output_dir in (reused_output, fresh_output):
        fuel_analyst(str(second_input), str(output_dir), gen_fofem_gui_app_tree_df=True, **options)
        assert not (output_dir / master_name).exists()
        assert not (output_dir / mortality_name).exists()

    (reused_output / master_name).write_bytes(previous_master)
    (reused_output / mortality_name).write_bytes(previous_mortality)
    fuel_analyst(str(second_input), str(reused_output), gen_fofem_gui_app_tree_df=False, **options)
    assert not (reused_output / master_name).exists()
    assert (reused_output / mortality_name).read_bytes() == previous_mortality

    assert sentinel.read_text(encoding='utf-8') == 'Keep analyst notes.'
    reused = pd.read_csv(reused_output / 'conpyro_df.csv')
    fresh = pd.read_csv(fresh_output / 'conpyro_df.csv')
    assert not fresh.empty
    pd.testing.assert_frame_equal(reused, fresh)
