"""Generate evidence for the retained PhotoLoad source mask and range bounds."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from PIL import Image
from skimage.color import rgb2lab
from skimage.filters import threshold_otsu

EXPERIMENT_ROOT = Path(__file__).resolve().parent
MODEL_ROOT = EXPERIMENT_ROOT.parent
sys.path.insert(0, str(MODEL_ROOT))

from photoload.extraction import extract_images  # noqa: E402
from photoload.masks import (  # noqa: E402
    DENSE_MAT_SPECIES,
    PIXEL_STEPS,
    RIDGE_THRESHOLDS,
    color_support_stabilization_step,
    maximum_eligible_ridge_response,
    source_mask_variations,
)
from photoload.workflow import CALIBRATION_CSV  # noqa: E402

DEFAULT_OUTPUT_DIR = MODEL_ROOT / ".work" / "range_experiment"
DEFAULT_PDF = (
        MODEL_ROOT.parents[1]
        / "docs"
        / "reference"
        / "rmrs_gtr190_Kean_and_Dickinson_2007.pdf"
)
RIDGE_INCREMENT = 0.005
SOURCE_LABELS = {
    "variation_1_cielab": "1. CIELAB",
    "variation_2_refined_saturation": "2. Refined + saturation ridges",
    "variation_3_refined_saturation_dark": "3. Refined + saturation + dark ridges",
}


def _calculate_metrics(frame: pd.DataFrame) -> dict[str, float | int]:
    """Summarize agreement with analyst cover as a comparison guide."""
    error = frame["objective_pct_cover"] - frame["analyst_pct_cover"]
    reference = frame["analyst_pct_cover"].to_numpy(dtype=float)
    estimate = frame["objective_pct_cover"].to_numpy(dtype=float)
    covariance = np.mean((reference - reference.mean()) * (estimate - estimate.mean()))
    denominator = reference.var() + estimate.var() + (reference.mean() - estimate.mean()) ** 2
    concordance = float(2 * covariance / denominator) if denominator else math.nan
    return {
        "n_images": len(frame),
        "bias_pct_points": float(error.mean()),
        "mae_pct_points": float(error.abs().mean()),
        "rmse_pct_points": float(np.sqrt(np.mean(np.square(error)))),
        "max_ae_pct_points": float(error.abs().max()),
        "ccc": concordance,
    }


def _create_panel(
        records: list[dict[str, object]],
        methods: list[tuple[str, str]],
        output_path: Path,
        title: str,
) -> None:
    """Create one low-to-high biomass source-mask comparison panel."""
    records.sort(key=lambda record: float(record["kg_m2"]))
    column_count = len(methods) + 1
    figure, axes = plt.subplots(
        len(records),
        column_count,
        figsize=(2.5 * column_count, 2.5 * len(records)),
        squeeze=False,
    )
    for row_index, record in enumerate(records):
        rgb = np.asarray(record["rgb"])
        axes[row_index, 0].imshow(rgb)
        axes[row_index, 0].set_ylabel(
            f"{float(record['kg_m2']):.3f} kg/m²\n"
            f"Analyst={float(record['analyst_pct_cover']):.1f}%",
            fontsize=8,
        )
        if row_index == 0:
            axes[row_index, 0].set_title("Original", fontsize=9)
        for column_index, (method, label) in enumerate(methods, start=1):
            mask = np.asarray(record[method])
            axes[row_index, column_index].imshow(_isolate_plant(rgb, mask))
            heading = f"Cover={100 * mask.mean():.1f}%"
            if row_index == 0:
                heading = f"{label}\n{heading}"
            axes[row_index, column_index].set_title(heading, fontsize=8)
        for axis in axes[row_index]:
            axis.set_xticks([])
            axis.set_yticks([])
    figure.suptitle(
        f"{title}\nLowest biomass at top; highest biomass at bottom",
        fontsize=14,
        y=0.998,
    )
    figure.subplots_adjust(top=0.955, bottom=0.01, left=0.08, right=0.998, hspace=0.24)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=140)
    plt.close(figure)


def _image_records(
        folder_data: pd.DataFrame,
        raw_root: Path,
) -> tuple[list[dict[str, object]], float]:
    """Load one species series and its lowest-image CIELAB threshold."""
    folder = str(folder_data.iloc[0]["folder"])
    records: list[dict[str, object]] = []
    for row in folder_data.sort_values("kg_m2").itertuples(index=False):
        stem = f"{row.kg_m2:.3f}_kgm2"
        rgb = np.asarray(Image.open(raw_root / folder / f"{stem}.jpg").convert("RGB"))
        records.append(
            {
                "rgb": rgb,
                "kg_m2": float(row.kg_m2),
                "analyst_pct_cover": float(row.analyst_pct_cover),
            }
        )
    lowest_lab = rgb2lab(np.asarray(records[0]["rgb"]))
    threshold = float(
        threshold_otsu(np.hypot(lowest_lab[:, :, 1], lowest_lab[:, :, 2]))
    )
    return records, threshold


def _isolate_plant(rgb: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Blend selected original pixels with a white background."""
    weight = np.asarray(mask, dtype=np.float64)[:, :, np.newaxis]
    return np.rint(rgb * weight + 255 * (1 - weight)).astype(np.uint8)


def _run_range_bounds(data: pd.DataFrame, raw_root: Path, output_dir: Path) -> dict[str, object]:
    """Measure seeded-mask stabilization and eligible ridge-response maxima."""
    pixel_rows: list[dict[str, object]] = []
    ridge_rows: list[dict[str, object]] = []
    for folder, folder_data in data.groupby("folder", sort=False):
        species_code = folder.split("_", 1)[0]
        records, threshold = _image_records(folder_data, raw_root)
        for record in records:
            rgb = np.asarray(record["rgb"])
            source = source_mask_variations(rgb, threshold)[
                "variation_3_refined_saturation_dark"
            ]
            common = {
                "species_code": species_code,
                "folder": folder,
                "kg_m2": record["kg_m2"],
            }
            if species_code in DENSE_MAT_SPECIES:
                ridge_rows.append(
                    {
                        **common,
                        "maximum_eligible_ridge_response": maximum_eligible_ridge_response(
                            source, rgb
                        ),
                    }
                )
            else:
                pixel_rows.append(
                    {
                        **common,
                        "last_changing_growth_step_px": color_support_stabilization_step(
                            source, rgb
                        ),
                    }
                )

    bounds_dir = output_dir / "02_parameter_bound_derivation"
    bounds_dir.mkdir(parents=True, exist_ok=True)
    pixel_data = pd.DataFrame(pixel_rows)
    ridge_data = pd.DataFrame(ridge_rows)
    pixel_data.to_csv(bounds_dir / "seeded_growth_last_change.csv", index=False)
    ridge_data.to_csv(
        bounds_dir / "eligible_ridge_response_maxima.csv", index=False
    )

    pixel_maximum = int(pixel_data["last_changing_growth_step_px"].max())
    ridge_maximum = float(ridge_data["maximum_eligible_ridge_response"].max())
    ridge_upper_bound = math.ceil(ridge_maximum / RIDGE_INCREMENT) * RIDGE_INCREMENT

    figure, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    axes[0].scatter(
        np.arange(len(pixel_data)),
        pixel_data["last_changing_growth_step_px"],
        s=18,
    )
    axes[0].axhline(pixel_maximum, color="black", linestyle="--", linewidth=1)
    axes[0].set(
        title="Seeded-growth stabilization",
        xlabel="Calibration photograph",
        ylabel="Last changing step (px)",
    )
    axes[1].scatter(
        np.arange(len(ridge_data)), ridge_data["maximum_eligible_ridge_response"], s=22
    )
    axes[1].axhline(ridge_upper_bound, color="black", linestyle="--", linewidth=1)
    axes[1].set(title="Eligible ridge-response maxima", xlabel="Dense-mat photograph", ylabel="Sato response")
    figure.tight_layout()
    figure.savefig(bounds_dir / "parameter_bound_diagnostics.png", dpi=160)
    plt.close(figure)

    return {
        "pixel_lower_bound": min(PIXEL_STEPS),
        "maximum_observed_last_changing_growth_step_px": pixel_maximum,
        "production_pixel_upper_bound": max(PIXEL_STEPS),
        "ridge_lower_bound": min(RIDGE_THRESHOLDS),
        "maximum_observed_eligible_ridge_response": ridge_maximum,
        "ridge_increment": RIDGE_INCREMENT,
        "production_ridge_upper_bound": max(RIDGE_THRESHOLDS),
        "calculated_ridge_upper_bound": ridge_upper_bound,
    }


def _run_source_comparison(
        data: pd.DataFrame,
        raw_root: Path,
        output_dir: Path,
) -> pd.DataFrame:
    """Generate Step 1 panels containing the three retained source variations."""
    rows: list[dict[str, object]] = []
    methods = list(SOURCE_LABELS.items())
    for folder, folder_data in data.groupby("folder", sort=False):
        species_code = folder.split("_", 1)[0]
        records, threshold = _image_records(folder_data, raw_root)
        for record in records:
            masks = source_mask_variations(np.asarray(record["rgb"]), threshold)
            record.update(masks)
            for method, mask in masks.items():
                rows.append(
                    {
                        "method": method,
                        "species_code": species_code,
                        "folder": folder,
                        "kg_m2": record["kg_m2"],
                        "objective_pct_cover": float(100 * mask.mean()),
                        "analyst_pct_cover": record["analyst_pct_cover"],
                    }
                )
        _create_panel(
            records,
            methods,
            output_dir / "01_source_mask_evaluation" / "panels" / f"{folder}.png",
            f"{folder} — Step 1 source-mask comparison",
        )
    return pd.DataFrame(rows)


def _write_results(
        bounds: dict[str, object],
        source_results: pd.DataFrame,
        output_dir: Path,
) -> None:
    """Write source-mask summaries, bound evidence, and the run manifest."""
    source_dir = output_dir / "01_source_mask_evaluation"
    source_results.to_csv(source_dir / "source_mask_cover_by_image.csv", index=False)
    summaries = [
        {"method": method, "species_code": species_code, **_calculate_metrics(frame)}
        for (method, species_code), frame in source_results.groupby(
            ["method", "species_code"], sort=False
        )
    ]
    pd.DataFrame(summaries).to_csv(
        source_dir / "source_mask_agreement_summary.csv", index=False
    )
    manifest = {
        "purpose": "PhotoLoad source-mask and production-range evidence",
        "step_1": list(SOURCE_LABELS),
        "step_2": bounds,
        "production_pixel_steps": list(PIXEL_STEPS),
        "production_ridge_thresholds": list(RIDGE_THRESHOLDS),
        "analyst_cover_role": "comparison guide, not ground truth or training target",
    }
    (output_dir / "range_experiment_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    """Parse command-line arguments and run the retained experiment."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    args = parser.parse_args()
    run_experiments(args.pdf, args.output_dir)


def run_experiments(pdf_path: Path, output_dir: Path) -> None:
    """Extract images and generate source-mask and range-bound evidence."""
    output_dir = output_dir.resolve()
    data = pd.read_csv(CALIBRATION_CSV)
    biomass_by_folder = {
        folder: sorted(frame["kg_m2"].astype(float).tolist())
        for folder, frame in data.groupby("folder", sort=False)
    }
    raw_root = output_dir / "00_extracted_images"
    extract_images(pdf_path.resolve(), raw_root, biomass_by_folder)
    source_results = _run_source_comparison(data, raw_root, output_dir)
    bounds = _run_range_bounds(data, raw_root, output_dir)
    _write_results(bounds, source_results, output_dir)


if __name__ == "__main__":
    main()
