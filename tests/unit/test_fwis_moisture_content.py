import numpy as np
import pytest

from fuel_analyst.components.fwis_moisture_content import dc_mc, dmc_mc, ffmc_mc


def test_ffmc_moisture_content_is_zero_at_code_101():
    assert ffmc_mc(101) == pytest.approx(0)
    assert ffmc_mc(101, use_precise_values=False) == pytest.approx(0)


def test_ffmc_accepts_arrays_and_decreases_with_code():
    result = ffmc_mc(np.array([70.0, 80.0, 90.0]))
    assert result.shape == (3,)
    assert np.all(np.diff(result) < 0)


def test_dmc_matches_documented_equation():
    assert dmc_mc(244.72) == pytest.approx(21.0)


def test_dc_reports_percent_saturation():
    assert dc_mc(0) == pytest.approx(100.0)
    assert dc_mc(400) == pytest.approx(100 / np.e)
