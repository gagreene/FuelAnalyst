# -*- coding: utf-8 -*-
"""
Test that the Newton-Raphson ISF solver produces results matching
the original bisection solver to within floating-point tolerance.

Covers models 12 and 13 across a broad range of ISZ, slope-factor,
and parameter values.
"""

import unittest
import numpy as np
from numpy import ma as mask
from fuel_analyst._vendor.conpyro.components.equations.conpyro_eqs import calc_isf


# ============================================================================
# Reference implementation: the ORIGINAL bisection solver (verbatim copy)
# ============================================================================

def _calc_isf_bisection_reference(isz, sf, sfc, sros_model,
                                   sros_param_a, sros_param_b, sros_param_c):
    """Pure-bisection calc_isf for models 12/13 — the OLD implementation."""
    isf = np.full_like(isz, np.nan, dtype=np.float64)

    model_list = [12, 13]
    mask_form_c = np.isin(sros_model, model_list)
    if not np.any(mask_form_c):
        return isf

    def solve_isf(rsf_target, _a, _b, _c):
        rsf_target = np.asarray(mask.array(rsf_target).filled(np.nan), dtype=np.float64).ravel()
        _a = np.asarray(mask.array(_a).filled(np.nan), dtype=np.float64).ravel()
        _b = np.asarray(mask.array(_b).filled(np.nan), dtype=np.float64).ravel()
        _c = np.asarray(mask.array(_c).filled(np.nan), dtype=np.float64).ravel()

        if _a.size == 1:
            _a = np.broadcast_to(_a, rsf_target.shape)
        if _b.size == 1:
            _b = np.broadcast_to(_b, rsf_target.shape)
        if _c.size == 1:
            _c = np.broadcast_to(_c, rsf_target.shape)

        roots = np.full_like(rsf_target, np.nan, dtype=np.float64)
        valid = (
            np.isfinite(rsf_target) & np.isfinite(_a) & np.isfinite(_b) & np.isfinite(_c) &
            (rsf_target >= 0) & (_a > 0) & (_b > 0) & (_c > 0)
        )
        if not np.any(valid):
            return mask.masked_array(roots, mask=np.isnan(roots))

        r = rsf_target[valid]
        a = _a[valid]
        b = _b[valid]
        c = _c[valid]

        def forward(x):
            q = np.clip(1.0 - np.exp(-b * x), 0.0, 1.0)
            return (a * x + 13.0) * np.power(q, c)

        lo = np.zeros_like(r)
        hi = np.maximum(25.0, r / np.maximum(a, 1e-9) + 1.0)

        for _ in range(20):
            f_hi = forward(hi) - r
            need_expand = f_hi < 0
            if not np.any(need_expand):
                break
            hi[need_expand] *= 2.0

        for _ in range(40):
            mid = 0.5 * (lo + hi)
            f_mid = forward(mid) - r
            go_left = f_mid >= 0
            hi[go_left] = mid[go_left]
            lo[~go_left] = mid[~go_left]

        roots_valid = 0.5 * (lo + hi)
        roots[valid] = np.where(np.isfinite(roots_valid) & (roots_valid >= 0), roots_valid, np.nan)
        return mask.masked_array(roots, mask=np.isnan(roots))

    param_a_c = sros_param_a[mask_form_c]
    param_b_c = sros_param_b[mask_form_c]
    param_c_c = sros_param_c[mask_form_c]
    agg_rsz = ((param_a_c * isz[mask_form_c] + 13) *
               np.power(1 - np.exp(-param_b_c * isz[mask_form_c]), param_c_c))
    rsf = agg_rsz * sf[mask_form_c]
    isf[mask_form_c] = solve_isf(rsf, param_a_c, param_b_c, param_c_c)

    return isf


# ============================================================================
# Tests
# ============================================================================

class TestCalcIsfNewtonVsBisection(unittest.TestCase):
    """Verify Newton-Raphson solver matches the original bisection solver."""

    # Model 12 parameters
    _A12 = 0.15
    _B12 = 0.128
    _C12 = 5.25

    # Model 13 parameters
    _A13 = 0.15
    _B13 = 0.101379
    _C13 = 4.164469

    def _make_inputs(self, isz_values, sf_values, model_code):
        """Build aligned arrays for a single model code."""
        isz = np.asarray(isz_values, dtype=np.float64)
        sf = np.asarray(sf_values, dtype=np.float64)
        n = isz.size
        sros_model = np.full(n, model_code, dtype=np.int8)
        if model_code == 12:
            a, b, c = self._A12, self._B12, self._C12
        else:
            a, b, c = self._A13, self._B13, self._C13
        sros_param_a = np.full(n, a, dtype=np.float64)
        sros_param_b = np.full(n, b, dtype=np.float64)
        sros_param_c = np.full(n, c, dtype=np.float64)
        sfc = np.ones(n, dtype=np.float64)  # not used by form c
        return isz, sf, sfc, sros_model, sros_param_a, sros_param_b, sros_param_c

    def _run_both(self, isz_values, sf_values, model_code):
        """Run both solvers on identical inputs and return both results."""
        args = self._make_inputs(isz_values, sf_values, model_code)
        isf_new = calc_isf(*args)
        isf_old = _calc_isf_bisection_reference(*args)
        return isf_new, isf_old

    # ------------------------------------------------------------------
    # Model 12
    # ------------------------------------------------------------------

    def test_model12_uniform_slope_factor(self):
        """Model 12: ISZ range with sf=1 (inversion should recover ISZ)."""
        isz_vals = [0.5, 1.0, 2.0, 5.0, 10.0, 15.0, 20.0, 30.0, 50.0]
        sf_vals = [1.0] * len(isz_vals)
        isf_new, isf_old = self._run_both(isz_vals, sf_vals, 12)
        np.testing.assert_allclose(isf_new, isf_old, rtol=1e-6, atol=1e-8,
                                   err_msg="Model 12, sf=1: Newton vs bisection mismatch")

    def test_model12_varying_slope_factors(self):
        """Model 12: range of slope factors (1–10)."""
        isz_vals = [1.0, 5.0, 10.0, 20.0, 30.0, 50.0]
        sf_vals = [1.0, 2.0, 3.0, 5.0, 8.0, 10.0]
        isf_new, isf_old = self._run_both(isz_vals, sf_vals, 12)
        np.testing.assert_allclose(isf_new, isf_old, rtol=1e-6, atol=1e-8,
                                   err_msg="Model 12, varying sf: Newton vs bisection mismatch")

    def test_model12_small_isz(self):
        """Model 12: very small ISZ values (near-zero forward)."""
        isz_vals = [0.01, 0.05, 0.1, 0.2]
        sf_vals = [1.5, 2.0, 3.0, 5.0]
        isf_new, isf_old = self._run_both(isz_vals, sf_vals, 12)
        np.testing.assert_allclose(isf_new, isf_old, rtol=1e-5, atol=1e-7,
                                   err_msg="Model 12, small ISZ: Newton vs bisection mismatch")

    def test_model12_large_isz(self):
        """Model 12: large ISZ values."""
        isz_vals = [50.0, 75.0, 100.0, 150.0]
        sf_vals = [2.0, 3.0, 5.0, 8.0]
        isf_new, isf_old = self._run_both(isz_vals, sf_vals, 12)
        np.testing.assert_allclose(isf_new, isf_old, rtol=1e-6, atol=1e-8,
                                   err_msg="Model 12, large ISZ: Newton vs bisection mismatch")

    # ------------------------------------------------------------------
    # Model 13
    # ------------------------------------------------------------------

    def test_model13_uniform_slope_factor(self):
        """Model 13: ISZ range with sf=1."""
        isz_vals = [0.5, 1.0, 2.0, 5.0, 10.0, 15.0, 20.0, 30.0, 50.0]
        sf_vals = [1.0] * len(isz_vals)
        isf_new, isf_old = self._run_both(isz_vals, sf_vals, 13)
        np.testing.assert_allclose(isf_new, isf_old, rtol=1e-6, atol=1e-8,
                                   err_msg="Model 13, sf=1: Newton vs bisection mismatch")

    def test_model13_varying_slope_factors(self):
        """Model 13: range of slope factors."""
        isz_vals = [1.0, 5.0, 10.0, 20.0, 30.0, 50.0]
        sf_vals = [1.0, 2.0, 3.0, 5.0, 8.0, 10.0]
        isf_new, isf_old = self._run_both(isz_vals, sf_vals, 13)
        np.testing.assert_allclose(isf_new, isf_old, rtol=1e-6, atol=1e-8,
                                   err_msg="Model 13, varying sf: Newton vs bisection mismatch")

    def test_model13_small_isz(self):
        """Model 13: very small ISZ values."""
        isz_vals = [0.01, 0.05, 0.1, 0.2]
        sf_vals = [1.5, 2.0, 3.0, 5.0]
        isf_new, isf_old = self._run_both(isz_vals, sf_vals, 13)
        np.testing.assert_allclose(isf_new, isf_old, rtol=1e-5, atol=1e-7,
                                   err_msg="Model 13, small ISZ: Newton vs bisection mismatch")

    # ------------------------------------------------------------------
    # Mixed models
    # ------------------------------------------------------------------

    def test_mixed_models_12_and_13(self):
        """Array with mixed model 12 and 13 elements."""
        isz = np.array([1.0, 5.0, 10.0, 20.0, 3.0, 15.0], dtype=np.float64)
        sf = np.array([2.0, 3.0, 1.5, 4.0, 2.5, 6.0], dtype=np.float64)
        sros_model = np.array([12, 13, 12, 13, 12, 13], dtype=np.int8)
        sfc = np.ones(6, dtype=np.float64)

        sros_param_a = np.where(sros_model == 12, self._A12, self._A13).astype(np.float64)
        sros_param_b = np.where(sros_model == 12, self._B12, self._B13).astype(np.float64)
        sros_param_c = np.where(sros_model == 12, self._C12, self._C13).astype(np.float64)

        isf_new = calc_isf(isz, sf, sfc, sros_model, sros_param_a, sros_param_b, sros_param_c)
        isf_old = _calc_isf_bisection_reference(isz, sf, sfc, sros_model,
                                                 sros_param_a, sros_param_b, sros_param_c)
        np.testing.assert_allclose(isf_new, isf_old, rtol=1e-6, atol=1e-8,
                                   err_msg="Mixed 12/13: Newton vs bisection mismatch")

    # ------------------------------------------------------------------
    # 2-D arrays (raster-like)
    # ------------------------------------------------------------------

    def test_2d_raster_like_input(self):
        """2-D array input simulating a small raster tile."""
        rng = np.random.default_rng(42)
        shape = (50, 50)
        isz = rng.uniform(0.1, 40.0, size=shape)
        sf = rng.uniform(1.0, 10.0, size=shape)
        model_choices = rng.choice([12, 13], size=shape)
        sros_model = model_choices.astype(np.int8)
        sfc = np.ones(shape, dtype=np.float64)

        sros_param_a = np.where(sros_model == 12, self._A12, self._A13).astype(np.float64)
        sros_param_b = np.where(sros_model == 12, self._B12, self._B13).astype(np.float64)
        sros_param_c = np.where(sros_model == 12, self._C12, self._C13).astype(np.float64)

        isf_new = calc_isf(isz, sf, sfc, sros_model, sros_param_a, sros_param_b, sros_param_c)
        isf_old = _calc_isf_bisection_reference(isz, sf, sfc, sros_model,
                                                 sros_param_a, sros_param_b, sros_param_c)

        # Both should be finite and non-negative
        self.assertTrue(np.all(np.isfinite(isf_new)), "New solver produced non-finite values")
        self.assertTrue(np.all(isf_new >= 0), "New solver produced negative values")

        np.testing.assert_allclose(isf_new, isf_old, rtol=1e-6, atol=1e-8,
                                   err_msg="2-D raster: Newton vs bisection mismatch")

    # ------------------------------------------------------------------
    # Inversion accuracy: forward(isf) should recover rsf
    # ------------------------------------------------------------------

    def test_forward_roundtrip_model12(self):
        """Verify forward(solve(rsf)) ≈ rsf for model 12."""
        isz_vals = np.array([1.0, 5.0, 10.0, 25.0, 50.0])
        sf_vals = np.array([2.0, 3.0, 5.0, 4.0, 8.0])
        args = self._make_inputs(isz_vals, sf_vals, 12)
        isf_result = calc_isf(*args)

        # Compute forward: rsf_recovered = f(isf_result)
        a, b, c = self._A12, self._B12, self._C12
        q = np.clip(1.0 - np.exp(-b * isf_result), 0.0, 1.0)
        rsf_recovered = (a * isf_result + 13.0) * np.power(q, c)

        # Original rsf
        agg_rsz = (a * isz_vals + 13.0) * np.power(
            np.clip(1.0 - np.exp(-b * isz_vals), 0.0, 1.0), c)
        rsf_original = agg_rsz * sf_vals

        np.testing.assert_allclose(rsf_recovered, rsf_original, rtol=1e-8, atol=1e-10,
                                   err_msg="Model 12 forward roundtrip failed")


if __name__ == '__main__':
    unittest.main()



