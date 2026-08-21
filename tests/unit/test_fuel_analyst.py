import logging

import pandas as pd
import pytest

from fuel_analyst.fuel_analyst import fuel_analyst


def test_fuel_analyst_requires_all_forms_for_conpyro(tmp_path):
    (tmp_path / 'input').mkdir()
    with pytest.raises(FileNotFoundError, match='All Survey123 forms'):
        fuel_analyst(
            str(tmp_path / 'input'), str(tmp_path / 'output'), 'Byram', gen_conpyro_df=True
        )


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
