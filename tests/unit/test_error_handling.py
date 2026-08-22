import logging

import pandas as pd
import pytest

from fuel_analyst.components import error_handling


def test_get_logger_returns_dotted_component_logger_name():
    logger = error_handling.get_logger('woody')
    assert logger.name == 'fuel_analyst.components.woody_debris'


def test_get_logger_unknown_form_raises_key_error():
    with pytest.raises(KeyError):
        error_handling.get_logger('not_a_form')


def test_start_run_write_report_pivots_by_plot_and_form(tmp_path):
    error_handling.start_run()
    logger_trees = error_handling.get_logger('trees')
    logger_woody = error_handling.get_logger('woody')

    logger_trees.warning('Tree issue for plot A', extra={'unique_id': 'A'})
    logger_woody.error('Woody issue for plot A', extra={'unique_id': 'A'})
    logger_trees.info('Tree issue for plot B', extra={'unique_id': 'B'})

    out_path = tmp_path / 'errors.csv'
    error_handling.write_report(str(out_path), plot_df=None)

    result = pd.read_csv(out_path, keep_default_na=False)
    row_a = result.loc[result['unique_id'] == 'A'].iloc[0]
    row_b = result.loc[result['unique_id'] == 'B'].iloc[0]
    assert row_a['Trees'] == '1. [WARNING] Tree issue for plot A'
    assert row_a['Woody Debris'] == '1. [ERROR] Woody issue for plot A'
    assert row_b['Trees'] == '1. [INFO] Tree issue for plot B'
    assert row_b['Woody Debris'] == ''


def test_write_report_without_start_run_raises():
    with pytest.raises(RuntimeError):
        error_handling.write_report('unused.csv')


def test_identity_columns_populated_from_plot_df(tmp_path):
    error_handling.start_run()
    error_handling.get_logger('woody').warning('issue', extra={'unique_id': 'A'})
    plot_df = pd.DataFrame({
        'unique_id': ['A', 'B'],
        'treatment_area': ['Area1', 'Area2'],
        'treatment_unit': ['U1', 'U2'],
        'treatment_type': ['Pre', 'Pre'],
        'plot_id': [1, 2],
    })
    out_path = tmp_path / 'errors.csv'
    error_handling.write_report(str(out_path), plot_df=plot_df)

    result = pd.read_csv(out_path, keep_default_na=False)
    assert len(result) == 1  # plot B had zero issues and is omitted
    assert result.loc[0, 'treatment_area'] == 'Area1'
    assert result.loc[0, 'plot_id'] == 1


def test_general_error_row_has_blank_identity_and_sorts_first(tmp_path):
    error_handling.start_run()
    error_handling.get_logger('trees').warning('plot-level issue', extra={'unique_id': 'Z'})
    error_handling.get_logger('trees').warning('run-level issue')  # no unique_id
    plot_df = pd.DataFrame({'unique_id': ['Z'], 'treatment_area': ['Area1']})
    out_path = tmp_path / 'errors.csv'
    error_handling.write_report(str(out_path), plot_df=plot_df)

    result = pd.read_csv(out_path, keep_default_na=False)
    assert result.loc[0, 'unique_id'] == 'General Error'
    assert result.loc[0, 'treatment_area'] == ''
    assert result.loc[1, 'unique_id'] == 'Z'
    assert result.loc[1, 'treatment_area'] == 'Area1'


def test_identity_columns_omitted_entirely_when_plot_df_lacks_them(tmp_path):
    """extract_nrcan_wx.py/run_conpyro.py pass a plot_df with no treatment_*/plot_id
    columns at all - the report should have no identity columns, not blank ones."""
    error_handling.start_run()
    error_handling.get_logger('trees').warning('issue', extra={'unique_id': 'A'})
    plot_df = pd.DataFrame({'unique_id': ['A']})
    out_path = tmp_path / 'errors.csv'
    error_handling.write_report(str(out_path), plot_df=plot_df)

    result = pd.read_csv(out_path, keep_default_na=False)
    assert list(result.columns) == ['unique_id', 'Trees']


def test_write_report_restores_previous_logger_level(tmp_path):
    root_logger = logging.getLogger('fuel_analyst')
    original_level = root_logger.level
    try:
        root_logger.setLevel(logging.ERROR)
        error_handling.start_run()
        assert root_logger.level == logging.INFO
        error_handling.write_report(str(tmp_path / 'errors.csv'), plot_df=None)
        assert root_logger.level == logging.ERROR
    finally:
        root_logger.setLevel(original_level)


def test_multiple_issues_per_cell_are_numbered_in_order(tmp_path):
    error_handling.start_run()
    logger = error_handling.get_logger('woody')
    logger.warning('first issue', extra={'unique_id': 'A'})
    logger.error('second issue', extra={'unique_id': 'A'})
    out_path = tmp_path / 'errors.csv'
    error_handling.write_report(str(out_path), plot_df=None)

    result = pd.read_csv(out_path, keep_default_na=False)
    assert result.loc[0, 'Woody Debris'] == (
        '1. [WARNING] first issue\n2. [ERROR] second issue'
    )


def test_logger_calls_reach_console_during_active_run(capsys, tmp_path):
    """Verify that logger calls made during start_run/write_report
    actually reach stdout, not just the collecting handler."""
    error_handling.start_run()
    logger = error_handling.get_logger('trees')
    logger.warning('test warning message during run', extra={'unique_id': 'A'})
    error_handling.write_report(str(tmp_path / 'errors.csv'), plot_df=None)

    captured = capsys.readouterr()
    assert 'test warning message during run' in captured.out
