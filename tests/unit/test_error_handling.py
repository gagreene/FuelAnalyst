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
