import logging
from io import StringIO

import pandas as pd
import pytest

from fuel_analyst.components import error_handling


def test_console_output_appends_plot_id_when_record_carries_one(capsys, monkeypatch, tmp_path):
    """The console formatter must preserve extra={'unique_id': ...} identity."""
    monkeypatch.setattr(error_handling, '_has_output_handler', lambda logger: False)
    error_handling.start_run()
    error_handling.get_logger('trees').warning(
        'radius problem', extra={'unique_id': 'plot-42', 'issue_code': 'missing_plot_radius'}
    )
    error_handling.write_report(str(tmp_path / 'errors.csv'), plot_df=None)

    captured = capsys.readouterr()
    assert 'plot-42' in captured.out
    assert 'radius problem (plot: plot-42)' in captured.out


def test_console_output_omits_plot_suffix_when_record_has_no_unique_id(capsys, monkeypatch, tmp_path):
    """A run-level record must print the bare message, with no plot suffix."""
    monkeypatch.setattr(error_handling, '_has_output_handler', lambda logger: False)
    error_handling.start_run()
    error_handling.get_logger('trees').warning('run level problem')
    error_handling.write_report(str(tmp_path / 'errors.csv'), plot_df=None)

    captured = capsys.readouterr()
    assert 'run level problem' in captured.out
    assert '(plot:' not in captured.out


def test_general_error_row_has_blank_identity_and_sorts_first(tmp_path):
    error_handling.start_run()
    error_handling.get_logger('trees').warning('plot-level issue', extra={'unique_id': 'Z'})
    error_handling.get_logger('trees').warning('run-level issue')
    plot_df = pd.DataFrame({'unique_id': ['Z'], 'treatment_area': ['Area1']})
    out_path = tmp_path / 'errors.csv'
    error_handling.write_report(str(out_path), plot_df=plot_df)

    result = pd.read_csv(out_path, keep_default_na=False)
    assert result.loc[0, 'unique_id'] == 'General Error'
    assert result.loc[0, 'treatment_area'] == ''
    assert result.loc[1, 'unique_id'] == 'Z'
    assert result.loc[1, 'treatment_area'] == 'Area1'


def test_get_logger_returns_dotted_component_logger_name():
    logger = error_handling.get_logger('woody')
    assert logger.name == 'fuel_analyst.components.woody_debris'


def test_get_logger_unknown_form_raises_key_error():
    with pytest.raises(KeyError):
        error_handling.get_logger('not_a_form')


def test_identity_columns_omitted_entirely_when_plot_df_lacks_them(tmp_path):
    """Weather and ConPyro reports should omit unavailable identity columns."""
    error_handling.start_run()
    error_handling.get_logger('trees').warning('issue', extra={'unique_id': 'A'})
    plot_df = pd.DataFrame({'unique_id': ['A']})
    out_path = tmp_path / 'errors.csv'
    error_handling.write_report(str(out_path), plot_df=plot_df)

    result = pd.read_csv(out_path, keep_default_na=False)
    assert list(result.columns) == ['unique_id', 'Trees']


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
    assert len(result) == 1
    assert result.loc[0, 'treatment_area'] == 'Area1'
    assert result.loc[0, 'plot_id'] == 1


def test_known_non_form_loggers_use_stable_display_names(tmp_path):
    error_handling.start_run()
    logging.getLogger('fuel_analyst.tools.extract_nrcan_wx').warning(
        'weather issue', extra={'unique_id': 'A'}
    )
    logging.getLogger('fuel_analyst.components.fofem_emissions').warning(
        'emissions issue', extra={'unique_id': 'A'}
    )
    logging.getLogger('fuel_analyst.components.fofem_mortality').warning(
        'mortality issue', extra={'unique_id': 'A'}
    )
    out_path = tmp_path / 'errors.csv'
    error_handling.write_report(str(out_path), plot_df=None)

    result = pd.read_csv(out_path, keep_default_na=False)
    assert 'NRCAN Weather' in result.columns
    assert 'FOFEM Emissions' in result.columns
    assert 'FOFEM Mortality' in result.columns


def test_logger_calls_reach_console_during_active_run(capsys, monkeypatch, tmp_path):
    monkeypatch.setattr(error_handling, '_has_output_handler', lambda logger: False)
    error_handling.start_run()
    error_handling.get_logger('trees').warning(
        'test warning message during run', extra={'unique_id': 'A'}
    )
    error_handling.write_report(str(tmp_path / 'errors.csv'), plot_df=None)

    captured = capsys.readouterr()
    assert 'test warning message during run' in captured.out


def test_mixed_type_unique_ids_write_without_sorting_error(tmp_path):
    error_handling.start_run()
    logger = error_handling.get_logger('trees')
    logger.warning('numeric ID', extra={'unique_id': 2})
    logger.warning('string ID', extra={'unique_id': '10'})
    logger.warning('unresolved ID', extra={'unique_id': pd.NA})
    out_path = tmp_path / 'errors.csv'
    error_handling.write_report(str(out_path), plot_df=None)

    result = pd.read_csv(out_path, keep_default_na=False)
    assert result.loc[0, 'unique_id'] == 'General Error'
    assert set(result.loc[1:, 'unique_id'].astype(str)) == {'2', '10'}


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


def test_normalize_unique_id_maps_missing_values_to_general_error():
    assert error_handling.normalize_unique_id(None) == error_handling.GENERAL_ERROR_ROW
    assert error_handling.normalize_unique_id(pd.NA) == error_handling.GENERAL_ERROR_ROW
    assert error_handling.normalize_unique_id(float('nan')) == error_handling.GENERAL_ERROR_ROW
    assert error_handling.normalize_unique_id('plot-1') == 'plot-1'


def test_null_handler_does_not_suppress_fallback_console_output(capsys, tmp_path):
    package_logger = logging.getLogger('fuel_analyst')
    original_propagate = package_logger.propagate
    null_handler = logging.NullHandler()
    package_logger.addHandler(null_handler)
    package_logger.propagate = False
    try:
        error_handling.start_run()
        error_handling.get_logger('trees').warning('null-handler fallback probe')
        error_handling.write_report(str(tmp_path / 'errors.csv'), plot_df=None)
    finally:
        package_logger.removeHandler(null_handler)
        package_logger.propagate = original_propagate

    assert 'null-handler fallback probe' in capsys.readouterr().out


def test_preconfigured_package_handler_prevents_duplicate_console_output(tmp_path):
    package_logger = logging.getLogger('fuel_analyst')
    stream = StringIO()
    external_handler = logging.StreamHandler(stream)
    package_logger.addHandler(external_handler)
    try:
        error_handling.start_run()
        assert error_handling._console_handler is None
        error_handling.get_logger('trees').warning('package-handler probe')
        error_handling.write_report(str(tmp_path / 'errors.csv'), plot_df=None)
        assert external_handler in package_logger.handlers
    finally:
        package_logger.removeHandler(external_handler)

    matching_lines = [line for line in stream.getvalue().splitlines() if 'package-handler probe' in line]
    assert matching_lines == ['package-handler probe']


def test_preconfigured_root_handler_prevents_duplicate_console_output(tmp_path):
    root_logger = logging.getLogger()
    stream = StringIO()
    external_handler = logging.StreamHandler(stream)
    root_logger.addHandler(external_handler)
    try:
        error_handling.start_run()
        assert error_handling._console_handler is None
        error_handling.get_logger('trees').warning('root-handler probe')
        error_handling.write_report(str(tmp_path / 'errors.csv'), plot_df=None)
        assert external_handler in root_logger.handlers
    finally:
        root_logger.removeHandler(external_handler)

    matching_lines = [line for line in stream.getvalue().splitlines() if 'root-handler probe' in line]
    assert matching_lines == ['root-handler probe']


def test_run_guard_restores_handlers_and_level_after_exception():
    root_logger = logging.getLogger('fuel_analyst')
    original_handlers = list(root_logger.handlers)
    original_level = root_logger.level

    @error_handling.run_guard
    def fail_during_run():
        error_handling.get_logger('trees').warning('failure before report')
        raise ValueError('expected failure')

    with pytest.raises(ValueError, match='expected failure'):
        fail_during_run()

    assert root_logger.handlers == original_handlers
    assert root_logger.level == original_level


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


def test_unknown_logger_names_remain_fully_qualified_and_distinct(tmp_path):
    error_handling.start_run()
    logging.getLogger('fuel_analyst.alpha.shared').warning(
        'alpha issue', extra={'unique_id': 'A'}
    )
    logging.getLogger('fuel_analyst.beta.shared').warning(
        'beta issue', extra={'unique_id': 'A'}
    )
    out_path = tmp_path / 'errors.csv'
    error_handling.write_report(str(out_path), plot_df=None)

    result = pd.read_csv(out_path, keep_default_na=False)
    assert 'fuel_analyst.alpha.shared' in result.columns
    assert 'fuel_analyst.beta.shared' in result.columns
    assert 'shared' not in result.columns
    assert result.loc[0, 'fuel_analyst.alpha.shared'] == '1. [WARNING] alpha issue'
    assert result.loc[0, 'fuel_analyst.beta.shared'] == '1. [WARNING] beta issue'


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


def test_write_report_without_start_run_raises():
    with pytest.raises(RuntimeError):
        error_handling.write_report('unused.csv')
