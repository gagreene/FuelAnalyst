import unittest

import numpy as np

from src.conpyro.conpyro import ConPyro


class TestConPyroCalcIsfFormC(unittest.TestCase):
    def test_form_c_returns_finite_nonnegative_values(self):
        cp = ConPyro()

        # Minimal state required by calc_isf()
        cp.ref_array = np.zeros((2, 3), dtype=np.float64)
        cp.isz = np.array([[1.0, 5.0, 10.0], [15.0, 20.0, 30.0]], dtype=np.float64)
        cp.sf = np.array([[1.0, 2.0, 3.0], [2.0, 4.0, 5.0]], dtype=np.float64)
        cp.sros_model = np.array([[12, 12, 13], [13, 12, 13]], dtype=np.int8)

        # Pre-set params and flag so calc_isf() does not need get_sros_params().
        cp.sros_param_a = np.array([[0.15, 0.15, 0.15], [0.15, 0.15, 0.15]], dtype=np.float64)
        cp.sros_param_b = np.array([[0.128, 0.128, 0.101379], [0.101379, 0.128, 0.101379]], dtype=np.float64)
        cp.sros_param_c = np.array([[5.25, 5.25, 4.164469], [4.164469, 5.25, 4.164469]], dtype=np.float64)
        cp.sros_params_initialized = True

        # Not used by form-c branch, but used by form-b branch in the same method.
        cp.sfc = np.ones((2, 3), dtype=np.float64)

        cp.calc_isf()

        self.assertEqual(cp.isf.shape, (2, 3))
        self.assertTrue(np.all(np.isfinite(cp.isf)), "Expected finite ISF for valid form-c inputs")
        self.assertTrue(np.all(cp.isf >= 0), "Expected nonnegative ISF for valid form-c inputs")

    def test_form_c_inversion_matches_isz_when_sf_is_one(self):
        cp = ConPyro()

        # If sf == 1, rsf is built directly from isz and inversion should recover isz.
        cp.ref_array = np.zeros((2, 2), dtype=np.float64)
        cp.isz = np.array([[1.0, 5.0], [10.0, 15.0]], dtype=np.float64)
        cp.sf = np.ones((2, 2), dtype=np.float64)
        cp.sros_model = np.array([[12, 13], [12, 13]], dtype=np.int8)

        cp.sros_param_a = np.array([[0.15, 0.15], [0.15, 0.15]], dtype=np.float64)
        cp.sros_param_b = np.array([[0.128, 0.101379], [0.128, 0.101379]], dtype=np.float64)
        cp.sros_param_c = np.array([[5.25, 4.164469], [5.25, 4.164469]], dtype=np.float64)
        cp.sros_params_initialized = True
        cp.sfc = np.ones((2, 2), dtype=np.float64)

        cp.calc_isf()

        np.testing.assert_allclose(cp.isf, cp.isz, rtol=1e-5, atol=1e-5)


if __name__ == '__main__':
    unittest.main()

