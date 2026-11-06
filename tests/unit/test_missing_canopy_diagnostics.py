import importlib
import logging

import pandas as pd
import pytest

from fuel_analyst.components import conpyro_attributes, error_handling


@pytest.mark.parametrize('field', ['cc', 'custom_cover'])
def test_missing_cover_is_reported_even_with_live_tree_density(caplog, field):
    frame = pd.DataFrame({
        'unique_id': ['live-plot', 'live-plot', 'zero-cover'],
        field: [float('nan'), float('nan'), 0.],
        'stand_dens_tpha_live_sum': [475., 475., 100.],
    })
    before = frame.copy(deep=True)
    with caplog.at_level(logging.WARNING, logger='fuel_analyst.components.conpyro_attributes'):
        result = conpyro_attributes._calc_stand_density(frame, field)
    assert result.conpyro_density_class.isna().tolist() == [True, True, False]
    assert result.conpyro_density_class.iloc[2] == 'L'
    pd.testing.assert_frame_equal(frame, before)
    records = [r for r in caplog.records if getattr(r, 'issue_code', '') == 'conpyro_missing_canopy_cover']
    assert len(records) == 1 and records[0].unique_id == 'live-plot'
    message = records[0].getMessage()
    assert field in message and 'canopy cover' in message.lower()
    assert 'stand_density' in message and 'trees per hectare' in message


def test_missing_cover_report_retains_plot_identity(tmp_path):
    frame = pd.DataFrame({'unique_id': ['plot-A'], 'plot_id': [843], 'cc': [float('nan')]})
    path = tmp_path / 'fuelanalyst_errors.csv'
    error_handling.start_run()
    try:
        conpyro_attributes._calc_stand_density(frame, 'cc')
    finally:
        error_handling.write_report(str(path), frame)
    report = pd.read_csv(path)
    assert report.unique_id.tolist() == ['plot-A']
    assert report.plot_id.tolist() == [843]
    assert 'canopy cover' in report['ConPyro Attributes'].iloc[0].lower()


def test_missing_cover_without_plot_id_uses_general_error_row(tmp_path):
    frame = pd.DataFrame({'cc': [float('nan'), float('nan')]})
    path = tmp_path / 'fuelanalyst_errors.csv'
    error_handling.start_run()
    try:
        conpyro_attributes._calc_stand_density(frame, 'cc')
    finally:
        error_handling.write_report(str(path))
    report = pd.read_csv(path)
    assert report.unique_id.tolist() == ['General Error']
    assert report['ConPyro Attributes'].iloc[0].count('[WARNING]') == 1


def test_skipped_stand_warning_distinguishes_density_and_type_without_assuming_zero_cover(caplog):
    run_module = importlib.import_module('fuel_analyst.run_conpyro')
    skipped = pd.DataFrame({
        'unique_id': ['A', 'A', 'B', 'C'],
        'stand_density': [None, None, 'L', None],
        'stand_type': ['P', 'P', None, None],
        'canopy_cover': [0., 0., 25., 0.],
    })
    with caplog.at_level(logging.WARNING, logger='fuel_analyst.run_conpyro'):
        run_module._log_skipped_empty_stand_plots(skipped, ['stand_density', 'stand_type'])
    records = {r.unique_id: r.getMessage() for r in caplog.records}
    assert len(caplog.records) == 3
    assert 'canopy-cover class' in records['A'] and 'trees per hectare' in records['A']
    assert 'master_fuel_df.csv' in records['A'] and 'zero' in records['A']
    assert 'has no live overstory' not in records['A']
    assert 'live species composition' in records['B']
    assert 'canopy-cover class' not in records['B']
    assert 'canopy-cover class' in records['C'] and 'live species composition' in records['C']


def test_valid_zero_and_boundary_cover_do_not_warn(caplog):
    frame = pd.DataFrame({'unique_id': ['A', 'B', 'C'], 'cc': [0., 45., 100.]})
    with caplog.at_level(logging.WARNING, logger='fuel_analyst.components.conpyro_attributes'):
        result = conpyro_attributes._calc_stand_density(frame, 'cc')
    assert result.conpyro_density_class.tolist() == ['L', 'L', 'H']
    assert not caplog.records
