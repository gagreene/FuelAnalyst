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
