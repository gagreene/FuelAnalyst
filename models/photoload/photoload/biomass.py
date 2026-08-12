"""Fit and document the frozen origin-constrained PhotoLoad biomass models."""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Callable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.optimize import curve_fit


SPECIES_ORDER = (
    "Amelanchier alnifolia",
    "Berberis repens",
    "Symphoricarpos albus",
    "Vaccinium globulare",
    "Vaccinium scoparium",
    "Arnica latifolia",
    "Calamagrostis rubescens",
    "Festuca scabrella",
    "Xerophyllum tenax",
)


def _equation(model: str, parameters: np.ndarray) -> str:
    """Format one equation, where x is cover and y is biomass."""
    if model == "linear_origin":
        return f"y = {parameters[0]:.6g}x"
    if model == "power":
        return f"y = {parameters[0]:.6g} x^{parameters[1]:.6g}"
    if model == "quadratic_origin":
        return f"y = {parameters[0]:.6g}x + {parameters[1]:.6g}x²"
    if model == "saturating":
        return f"y = {parameters[0]:.6g}(1 - exp(-{parameters[1]:.6g}x))"
    if model == "shifted_exponential":
        return f"y = {parameters[0]:.6g}(exp({parameters[1]:.6g}x) - 1)"
    raise ValueError(f"Unknown model: {model}")


def _guess_linear_origin(x: np.ndarray, y: np.ndarray) -> list[float]:
    """Return a least-squares slope through the origin."""
    return [float(np.sum(x * y) / np.sum(x**2))]


def _guess_power(x: np.ndarray, y: np.ndarray) -> list[float]:
    """Return a log-linear starting value for the power model."""
    slope, intercept = np.polyfit(np.log(x), np.log(np.clip(y, 1e-6, None)), 1)
    return [float(np.exp(intercept)), float(slope)]


def _guess_quadratic_origin(x: np.ndarray, y: np.ndarray) -> list[float]:
    """Start the quadratic at the through-origin linear solution."""
    return [float(np.sum(x * y) / np.sum(x**2)), 0.0]


def _guess_saturating(x: np.ndarray, y: np.ndarray) -> list[float]:
    """Return stable starting values for the saturating model."""
    return [float(np.max(y)) * 1.2, 0.05]


def _guess_shifted_exponential(x: np.ndarray, y: np.ndarray) -> list[float]:
    """Return starting values for the shifted exponential model."""
    exponent = 0.02
    basis = np.expm1(exponent * x)
    scale = np.sum(basis * y) / np.sum(basis**2)
    return [float(max(scale, 1e-6)), exponent]


def _linear_origin(x: np.ndarray, scale: float) -> np.ndarray:
    """Return a linear-through-origin prediction."""
    return scale * x


def _loocv_rmse(model: str, x: np.ndarray, y: np.ndarray) -> tuple[float, int]:
    """Return leave-one-out prediction RMSE and failed-fold count."""
    function, _, guess, requires_positive_x = MODELS[model]
    if requires_positive_x and np.any(x <= 0):
        return np.nan, 0
    squared_errors: list[float] = []
    failures = 0
    for index in range(len(x)):
        x_train = np.delete(x, index)
        y_train = np.delete(y, index)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                parameters, _ = curve_fit(
                    function,
                    x_train,
                    y_train,
                    p0=guess(x_train, y_train),
                    maxfev=50000,
                )
            prediction = function(np.array([x[index]]), *parameters)[0]
            if not np.isfinite(prediction):
                raise ValueError("Non-finite prediction")
        except (FloatingPointError, RuntimeError, ValueError):
            failures += 1
            continue
        squared_errors.append(float((y[index] - prediction) ** 2))
    return (
        float(np.sqrt(np.mean(squared_errors))) if squared_errors else np.nan,
        failures,
    )


def _parameters(value: str) -> np.ndarray:
    """Parse semicolon-delimited fitted parameters."""
    return np.asarray([float(item) for item in value.split(";")], dtype=float)


def _power(x: np.ndarray, scale: float, exponent: float) -> np.ndarray:
    """Return an origin-constrained power prediction."""
    return scale * np.power(x, exponent)


def _quadratic_origin(x: np.ndarray, linear: float, quadratic: float) -> np.ndarray:
    """Return a no-intercept quadratic prediction."""
    return linear * x + quadratic * x**2


def _r_squared(y: np.ndarray, prediction: np.ndarray) -> float:
    """Return the coefficient of determination."""
    return float(
        1 - np.sum(np.square(y - prediction)) / np.sum(np.square(y - y.mean()))
    )


def _saturating(x: np.ndarray, asymptote: float, rate: float) -> np.ndarray:
    """Return an origin-constrained asymptotic prediction."""
    return asymptote * (1 - np.exp(-rate * x))


def _score_fit(rss: float, n: int, parameter_count: int) -> tuple[float, float, float]:
    """Return AIC, small-sample AICc, and BIC."""
    effective_parameters = parameter_count + 1
    rss = max(rss, 1e-12)
    aic = n * np.log(rss / n) + 2 * effective_parameters
    denominator = n - effective_parameters - 1
    aicc = (
        aic
        + 2
        * effective_parameters
        * (effective_parameters + 1)
        / denominator
        if denominator > 0
        else np.inf
    )
    bic = n * np.log(rss / n) + effective_parameters * np.log(n)
    return float(aic), float(aicc), float(bic)


def _shifted_exponential(x: np.ndarray, scale: float, rate: float) -> np.ndarray:
    """Return an exponential shifted to cross the origin."""
    return scale * np.expm1(rate * x)


Model = tuple[Callable[..., np.ndarray], int, Callable[..., list[float]], bool]
MODELS: dict[str, Model] = {
    "linear_origin": (_linear_origin, 1, _guess_linear_origin, False),
    "power": (_power, 2, _guess_power, True),
    "quadratic_origin": (_quadratic_origin, 2, _guess_quadratic_origin, False),
    "saturating": (_saturating, 2, _guess_saturating, False),
    "shifted_exponential": (
        _shifted_exponential,
        2,
        _guess_shifted_exponential,
        False,
    ),
}

DOCUMENTED_SELECTIONS = {
    "Amelanchier alnifolia": {
        "model": "shifted_exponential",
        "basis": (
            "Shifted exponential selected by multi-indicator review: it best "
            "represents the pronounced positive curvature and has the lowest fitted "
            "and LOOCV RMSE, the highest R-squared, and the strongest AICc, AIC, and "
            "BIC support. The model is monotonic and nonnegative over the observed domain."
        ),
    },
    "Berberis repens": {
        "model": "power",
        "basis": (
            "Power selected by multi-indicator review: it captures the modest positive "
            "curvature, removes the systematic low-to-high residual progression of the "
            "linear model, and has the best AICc, fitted RMSE, and R-squared. Its LOOCV "
            "RMSE is also marginally the lowest, and the fitted curve is monotonic and nonnegative."
        ),
    },
    "Symphoricarpos albus": {
        "model": "quadratic_origin",
        "basis": (
            "Quadratic selected by multi-indicator review: it preserves the origin "
            "constraint, follows the visible curvature, and improves LOOCV RMSE, fitted "
            "RMSE, R-squared, and AIC relative to the linear AICc winner. Its delta AICc "
            "is 2.69, which is not decisive evidence against it at n=9."
        ),
    },
    "Vaccinium globulare": {
        "model": "shifted_exponential",
        "basis": (
            "Shifted exponential selected by multi-indicator review: it and the quadratic "
            "are effectively tied visually and statistically, but the shifted exponential "
            "has marginally better AICc, AIC, BIC, fitted RMSE, R-squared, and LOOCV RMSE. "
            "Both have two parameters; selection uncertainty and extrapolation beyond the "
            "observed cover range must therefore be acknowledged."
        ),
    },
    "Vaccinium scoparium": {
        "model": "linear_origin",
        "basis": (
            "Linear-through-origin selected by multi-indicator review: it has the strongest "
            "AICc support and lowest LOOCV RMSE, is physically valid, and uses only one "
            "parameter. Curved candidates improve the in-sample fit only slightly while "
            "worsening predictive error and adding unsupported complexity."
        ),
    },
    "Arnica latifolia": {
        "model": "power",
        "basis": (
            "Power selected by multi-indicator review: it follows the modest positive "
            "curvature and has the lowest fitted and LOOCV RMSE, the highest R-squared, "
            "and the strongest AICc, AIC, and BIC support. The fitted relationship is "
            "monotonic and nonnegative."
        ),
    },
    "Calamagrostis rubescens": {
        "model": "shifted_exponential",
        "basis": (
            "Shifted exponential selected by multi-indicator review: it best captures the "
            "strong convex rise caused by cover saturation and has the lowest fitted and "
            "LOOCV RMSE, highest R-squared, and best AICc, AIC, and BIC. The quadratic is "
            "physically invalid at low positive cover because its fitted linear coefficient "
            "is negative. Uncertainty remains high because this is the weakest species fit."
        ),
    },
    "Festuca scabrella": {
        "model": "shifted_exponential",
        "basis": (
            "Shifted exponential selected by multi-indicator review: it follows the observed "
            "convex relationship and outperforms the alternatives on fitted RMSE, LOOCV "
            "RMSE, R-squared, AICc, AIC, and BIC. The quadratic is physically invalid at low "
            "positive cover because its fitted linear coefficient is negative."
        ),
    },
    "Xerophyllum tenax": {
        "model": "linear_origin",
        "basis": (
            "Linear-through-origin selected by multi-indicator review: it has the best AICc "
            "and ties the effectively linear shifted exponential for lowest LOOCV RMSE while "
            "using one fewer parameter. Curved models improve in-sample fit modestly but "
            "worsen prediction, so parsimony and stability favor the linear model."
        ),
    },
}


def _write_model_results(data: pd.DataFrame, output_dir: Path) -> pd.DataFrame:
    """Fit candidates, apply explicit selections, and write final reports."""
    output_dir.mkdir(parents=True, exist_ok=True)
    all_results: list[dict[str, object]] = []
    for species in SPECIES_ORDER:
        species_data = data.loc[data["species"] == species].sort_values("kg_m2")
        x = species_data["objective_pct_cover"].to_numpy(dtype=float)
        y = species_data["kg_m2"].to_numpy(dtype=float)
        for model, (function, parameter_count, guess, requires_positive_x) in MODELS.items():
            if requires_positive_x and np.any(x <= 0):
                continue
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                parameters, _ = curve_fit(
                    function, x, y, p0=guess(x, y), maxfev=50000
                )
            prediction = function(x, *parameters)
            rss = float(np.sum(np.square(y - prediction)))
            aic, aicc, bic = _score_fit(rss, len(x), parameter_count)
            loocv_rmse, failed_folds = _loocv_rmse(model, x, y)
            all_results.append(
                {
                    "species": species,
                    "model": model,
                    "n": len(x),
                    "params": ";".join(f"{value:.9g}" for value in parameters),
                    "equation": _equation(model, parameters),
                    "r2": _r_squared(y, prediction),
                    "rmse_kg_m2": float(np.sqrt(rss / len(x))),
                    "aic": aic,
                    "aicc": aicc,
                    "bic": bic,
                    "loocv_rmse_kg_m2": loocv_rmse,
                    "loocv_failed": failed_folds,
                }
            )
    candidates = pd.DataFrame(all_results)
    candidates.to_csv(output_dir / "all_candidate_statistics.csv", index=False)
    selected_rows: list[pd.Series] = []
    for species in SPECIES_ORDER:
        species_candidates = candidates.loc[candidates["species"] == species]
        decision = DOCUMENTED_SELECTIONS[species]
        selected = species_candidates.loc[
            species_candidates["model"] == decision["model"]
        ].iloc[0].copy()
        selected["selection_basis"] = decision["basis"]
        selected["minimum_aicc_model"] = species_candidates.loc[
            species_candidates["aicc"].idxmin(), "model"
        ]
        selected["minimum_loocv_model"] = species_candidates.loc[
            species_candidates["loocv_rmse_kg_m2"].idxmin(), "model"
        ]
        selected["delta_aicc"] = selected["aicc"] - species_candidates["aicc"].min()
        selected_rows.append(selected)
    selected = pd.DataFrame(selected_rows)
    selected.to_csv(output_dir / "selected_model_summary.csv", index=False)
    _write_overview(data, selected, output_dir)
    _write_readme(selected, output_dir)
    return selected


def _write_overview(data: pd.DataFrame, selected: pd.DataFrame, output_dir: Path) -> None:
    """Write the nine-species final-model overview."""
    figure, axes = plt.subplots(3, 3, figsize=(14, 12))
    for axis, species in zip(axes.flat, SPECIES_ORDER):
        species_data = data.loc[data["species"] == species]
        winner = selected.loc[selected["species"] == species].iloc[0]
        x = species_data["objective_pct_cover"].to_numpy(dtype=float)
        y = species_data["kg_m2"].to_numpy(dtype=float)
        curve_x = np.linspace(0, x.max() * 1.05, 300)
        function = MODELS[str(winner["model"])][0]
        parameters = _parameters(str(winner["params"]))
        axis.scatter(x, y, color="black", s=28, zorder=3)
        axis.scatter([0], [0], marker="+", s=60, color="black")
        axis.plot(curve_x, function(curve_x, *parameters), linewidth=2)
        axis.set_title(species, fontsize=10, fontstyle="italic")
        axis.text(
            0.03,
            0.97,
            f"{winner['model']}\nR²={winner['r2']:.3f}; ΔAICc={winner['delta_aicc']:.2f}\n"
            f"LOOCV RMSE={winner['loocv_rmse_kg_m2']:.4f}",
            transform=axis.transAxes,
            va="top",
            fontsize=8,
            bbox={"facecolor": "white", "alpha": 0.8, "edgecolor": "none"},
        )
        axis.set_xlabel("Objective percent cover (%)", fontsize=8)
        axis.set_ylabel("Biomass (kg/m²)", fontsize=8)
        axis.grid(alpha=0.2)
    figure.suptitle("Final multi-indicator PhotoLoad biomass models", fontsize=16)
    figure.tight_layout(rect=(0, 0, 1, 0.97))
    figure.savefig(output_dir / "selected_models_overview.png", dpi=200)
    plt.close(figure)


def _write_readme(selected: pd.DataFrame, output_dir: Path) -> None:
    """Write the explicit multi-criteria rationale for all nine species."""
    lines = [
        "# Final PhotoLoad biomass models",
        "",
        "Every candidate is constrained to pass through `(0, 0)`. Selection considered ",
        "physical validity, residual shape, LOOCV RMSE, AICc/AIC/BIC, fitted RMSE, ",
        "R-squared, and parsimony. No weighted composite score or automatic AICc ",
        "fallback is used.",
        "",
    ]
    for _, row in selected.iterrows():
        lines.extend(
            [
                f"## {row['species']} — `{row['model']}`",
                "",
                str(row["selection_basis"]),
                "",
                f"Equation: `{row['equation']}`. Parameters: `{row['params']}`. "
                f"R²={row['r2']:.4f}; "
                f"fitted RMSE={row['rmse_kg_m2']:.5f} kg/m²; "
                f"LOOCV RMSE={row['loocv_rmse_kg_m2']:.5f} kg/m²; "
                f"ΔAICc={row['delta_aicc']:.2f}.",
                "",
            ]
        )
    (output_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")


def fit_models(data: pd.DataFrame, output_dir: Path) -> pd.DataFrame:
    """Fit candidates, apply explicit selections, and write final reports."""
    return _write_model_results(data, output_dir)
