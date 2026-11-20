import copy
import logging

import pandas as pd
import pytest

from fuel_analyst import fuel_analyst as fuel_analyst_module
from fuel_analyst.fuel_analyst import _find_id_mismatches, default_fofem_consume_dict, fuel_analyst


def _write_minimal_plot_attributes(in_dir):
    """
    Write the smallest valid single-plot Plot Attributes CSV, no forms selected.

    Also creates empty Trees, Plants and Regeneration, and Woody Debris form directories
    (present but with no plot selecting them) so gen_fofem_consume_df=True's upfront
    form-presence gate passes without exercising real per-form processing - these tests
    stub out gen_fofem_consumption_df() itself and only care about filename/units
    resolution, not real FOFEM inputs.

    :param in_dir: Directory to build the '1_Plot_Attributes/survey_0.csv' fixture under.
    :return: None.
    """
    plot_dir = in_dir / '1_Plot_Attributes'
    plot_dir.mkdir(parents=True)
    pd.DataFrame({
        'GlobalID': ['g1'], 'ParentGlobalID': [None],
        'treatment_area': ['A'], 'treatment_unit': ['U'], 'treatment_type': ['Pre'],
        'plot_id': [1], '_date': ['01/01/2025 10:00'], 'form_select': ['none'],
        'plot_slope_units': ['percent'], 'plot_slope': [10.0],
    }).to_csv(plot_dir / 'survey_0.csv', index=False)
    (in_dir / '2_Plants_Regeneration').mkdir()
    (in_dir / '3_Trees').mkdir()
    (in_dir / '5_Woody_Debris').mkdir()


def test_find_id_mismatches_is_ordered_deduplicated_and_bidirectional():
    missing_from_form, extra_in_form = _find_id_mismatches(
        ['plot-b', 'plot-a', 'plot-b'],
        ['plot-a', 'plot-c', 'plot-c'],
    )

    assert missing_from_form == ['plot-b']
    assert extra_in_form == ['plot-c']


def test_fuel_analyst_requires_all_forms_for_conpyro(tmp_path):
    root_logger = logging.getLogger('fuel_analyst')
    original_handlers = list(root_logger.handlers)
    original_level = root_logger.level
    (tmp_path / 'input').mkdir()
    with pytest.raises(FileNotFoundError, match='Plants and Regeneration, Canopy Cover'):
        fuel_analyst(
            str(tmp_path / 'input'), str(tmp_path / 'output'), 'Byram', gen_conpyro_df=True
        )
    assert root_logger.handlers == original_handlers
    assert root_logger.level == original_level


def test_gui_export_does_not_require_unselected_trees(tmp_path):
    source = tmp_path / 'input'
    _write_minimal_plot_attributes(source)
    (source / '3_Trees').rmdir()  # Empty synthetic directory; Trees was not selected.
    out = tmp_path / 'out'
    fuel_analyst(str(source), str(out), 'Byram', gen_fofem_gui_app_tree_df=True)
    assert pd.read_csv(out / 'fuelanalyst_errors.csv').empty


def test_fuel_analyst_requires_trees_plants_and_woody_for_fofem_consume_df(tmp_path):
    root_logger = logging.getLogger('fuel_analyst')
    original_handlers = list(root_logger.handlers)
    original_level = root_logger.level
    (tmp_path / 'input').mkdir()
    with pytest.raises(
        FileNotFoundError, match='Plants and Regeneration and Woody Debris'
    ):
        fuel_analyst(
            str(tmp_path / 'input'), str(tmp_path / 'output'), 'Byram',
            gen_fofem_consume_df=True,
        )
    assert root_logger.handlers == original_handlers
    assert root_logger.level == original_level


def test_id_mismatch_logs_orphan_form_id_even_when_forward_direction_is_clean(tmp_path, caplog):
    in_dir = tmp_path / 'in'
    plot_dir = in_dir / '1_Plot_Attributes'
    plot_dir.mkdir(parents=True)
    pd.DataFrame({
        'GlobalID': ['g1'], 'ParentGlobalID': [None],
        'treatment_area': ['A'], 'treatment_unit': ['U'], 'treatment_type': ['Pre'],
        'plot_id': [1], '_date': ['01/01/2025 10:00'], 'form_select': ['cover'],
        'plot_slope_units': ['percent'], 'plot_slope': [10.0],
    }).to_csv(plot_dir / 'survey_0.csv', index=False)
    # Plot Attributes' own unique_id, computed the same way, is 'A_U_Pre_1_2025'.

    cover_dir = in_dir / '4_Canopy_Cover'
    cover_dir.mkdir(parents=True)
    cc_cols = {f'cc_{i}': ['cnfr', 'cnfr'] for i in range(2, 32, 2)}
    # Row 1 matches the plot exactly (same treatment_area/unit/type/plot_id/_date,
    # so get_unique_id() computes the same 'A_U_Pre_1_2025'). Row 2 uses plot_id=99,
    # an orphan that was never in Plot Attributes at all.
    pd.DataFrame({
        'GlobalID': ['gc1', 'gc2'], 'ParentGlobalID': ['g1', 'gx'],
        'treatment_area': ['A', 'A'], 'treatment_unit': ['U', 'U'],
        'treatment_type': ['Pre', 'Pre'], 'plot_id': [1, 99],
        '_date': ['01/01/2025 10:00', '01/01/2025 10:00'],
    }).to_csv(cover_dir / 'survey_0.csv', index=False)
    pd.DataFrame({
        'ParentGlobalID': ['gc1', 'gc2'], 'cc_transect': [1, 1], **cc_cols,
    }).to_csv(cover_dir / 'canopy_cover_1.csv', index=False)

    with caplog.at_level(logging.WARNING, logger='fuel_analyst.components.canopy_cover'):
        fuel_analyst(
            in_dir=str(in_dir),
            out_dir=str(tmp_path / 'out'),
            surface_fire_intensity_model='Byram',
        )

    matching = [r for r in caplog.records if getattr(r, 'unique_id', None) == 'A_U_Pre_99_2025']
    assert len(matching) == 1
    assert matching[0].issue_code == 'id_extra_in_form'


def test_missing_form_folder_logs_per_plot_warning(tmp_path, caplog):
    # Build a minimal in_dir with only Plot Attributes present, one plot selecting 'woody'.
    plot_dir = tmp_path / 'in' / '1_Plot_Attributes'
    plot_dir.mkdir(parents=True)
    pd.DataFrame({
        'GlobalID': ['g1'], 'ParentGlobalID': [None],
        'treatment_area': ['A'], 'treatment_unit': ['U'], 'treatment_type': ['Pre'],
        'plot_id': [1], '_date': ['01/01/2025 10:00'], 'form_select': ['woody'],
        'plot_slope_units': ['percent'], 'plot_slope': [10.0],
    }).to_csv(plot_dir / 'survey_0.csv', index=False)

    with caplog.at_level(logging.WARNING, logger='fuel_analyst.components.woody_debris'):
        fuel_analyst(
            in_dir=str(tmp_path / 'in'),
            out_dir=str(tmp_path / 'out'),
            surface_fire_intensity_model='Byram',
        )

    assert any(
        'no Woody Debris data' in record.message and record.unique_id == 'A_U_Pre_1_2025'
        for record in caplog.records
    )


def _write_woody_plot(in_dir):
    plot_dir = in_dir / '1_Plot_Attributes'
    plot_dir.mkdir(parents=True)
    pd.DataFrame({
        'GlobalID': ['g1'], 'ParentGlobalID': [None],
        'treatment_area': ['A'], 'treatment_unit': ['U'], 'treatment_type': ['Pre'],
        'plot_id': [1], '_date': ['01/01/2025 10:00'], 'form_select': ['woody'],
        'plot_slope_units': ['percent'], 'plot_slope': [10.0],
    }).to_csv(plot_dir / 'survey_0.csv', index=False)


def test_a_broken_workbook_in_a_form_no_plot_selected_is_never_opened(tmp_path, caplog):
    _write_woody_plot(tmp_path / 'in')
    trees_dir = tmp_path / 'in' / '3_Trees'
    trees_dir.mkdir()
    (trees_dir / 'broken_EXCEL.xlsx').write_bytes(b'this is not a workbook')

    with caplog.at_level(logging.WARNING, logger='fuel_analyst.components.woody_debris'):
        fuel_analyst(
            in_dir=str(tmp_path / 'in'),
            out_dir=str(tmp_path / 'out'),
            surface_fire_intensity_model='Byram',
        )

    assert any('no Woody Debris data' in record.message for record in caplog.records)


def test_a_selected_form_with_only_a_zipped_download_says_to_unzip_it(tmp_path):
    _write_woody_plot(tmp_path / 'in')
    woody_dir = tmp_path / 'in' / '5_Woody_Debris'
    woody_dir.mkdir()
    (woody_dir / 'S123_abc_FGDB.zip').write_bytes(b'PK')

    with pytest.raises(ValueError, match='Unzip it first'):
        fuel_analyst(
            in_dir=str(tmp_path / 'in'),
            out_dir=str(tmp_path / 'out'),
            surface_fire_intensity_model='Byram',
        )


def _patch_fofem_consumption_generation(monkeypatch):
    """
    Stub gen_fofem_consumption_df() so filename-selection tests don't need real FOFEM inputs.

    :param monkeypatch: pytest monkeypatch fixture.
    :return: None.
    """
    monkeypatch.setattr(
        fuel_analyst_module.fofem_attributes,
        'gen_fofem_consumption_df',
        lambda df, params: pd.DataFrame({'#PlotId': ['A_U_Pre_1_2025']}),
    )


def test_fuel_analyst_writes_si_consume_filename_by_default(tmp_path, monkeypatch):
    _patch_fofem_consumption_generation(monkeypatch)
    _write_minimal_plot_attributes(tmp_path / 'in')

    fuel_analyst(
        in_dir=str(tmp_path / 'in'),
        out_dir=str(tmp_path / 'out'),
        surface_fire_intensity_model='Byram',
        gen_fofem_consume_df=True,
    )

    assert (tmp_path / 'out' / 'fofem_consume_si_df.csv').is_file()
    assert not (tmp_path / 'out' / 'fofem_consume_imperial_df.csv').exists()
    assert not (tmp_path / 'out' / 'fofem_consume_df.csv').exists()


def test_fuel_analyst_writes_imperial_consume_filename_when_configured(tmp_path, monkeypatch):
    _patch_fofem_consumption_generation(monkeypatch)
    _write_minimal_plot_attributes(tmp_path / 'in')
    imperial_params = copy.deepcopy(default_fofem_consume_dict)
    imperial_params['fofem_processing_units'] = 'Imperial'

    fuel_analyst(
        in_dir=str(tmp_path / 'in'),
        out_dir=str(tmp_path / 'out'),
        surface_fire_intensity_model='Byram',
        fofem_consume_params=imperial_params,
        gen_fofem_consume_df=True,
    )

    assert (tmp_path / 'out' / 'fofem_consume_imperial_df.csv').is_file()
    assert not (tmp_path / 'out' / 'fofem_consume_si_df.csv').exists()


def test_fuel_analyst_legacy_consume_dict_without_units_key_defaults_to_si(tmp_path, monkeypatch):
    """A custom fofem_consume_params dict predating fofem_processing_units must still resolve
    to SI in both generation and filename selection, with no KeyError."""
    _patch_fofem_consumption_generation(monkeypatch)
    _write_minimal_plot_attributes(tmp_path / 'in')
    legacy_params = copy.deepcopy(default_fofem_consume_dict)
    del legacy_params['fofem_processing_units']

    fuel_analyst(
        in_dir=str(tmp_path / 'in'),
        out_dir=str(tmp_path / 'out'),
        surface_fire_intensity_model='Byram',
        fofem_consume_params=legacy_params,
        gen_fofem_consume_df=True,
    )

    assert (tmp_path / 'out' / 'fofem_consume_si_df.csv').is_file()
