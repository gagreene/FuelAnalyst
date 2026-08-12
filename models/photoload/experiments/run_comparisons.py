"""Generate the retained PhotoLoad method-review panels."""

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
    BROADLEAF_SPECIES,
    DENSE_MAT_SPECIES,
    FINE_STRUCTURE_SPECIES,
    grow_color_support,
    ridge_rescue_mask,
    source_mask_variations,
)
from photoload.workflow import CALIBRATION_CSV  # noqa: E402


DEFAULT_OUTPUT_DIR = MODEL_ROOT / ".work" / "experiments"
DEFAULT_PDF = MODEL_ROOT.parents[1] / "docs" / "reference" / "rmrs_gtr190.pdf"
HISTORICAL_PIXEL_STEPS = (2, 4, 6, 8, 12)
HISTORICAL_RIDGE_THRESHOLDS = (0.045, 0.055, 0.070)
PIXEL_STEPS = tuple(range(2, 13))
RIDGE_THRESHOLDS = tuple(value / 1000 for value in range(10, 100, 5))
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
    """Create one low-to-high biomass comparison panel."""
    records.sort(key=lambda record: float(record["kg_m2"]))
    column_count = len(methods) + 1
    figure, axes = plt.subplots(
        len(records),
        column_count,
        figsize=(3.0 * column_count, 3.0 * len(records)),
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
            mask = np.asarray(record[method], dtype=bool)
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
    figure.subplots_adjust(
        top=0.955,
        bottom=0.01,
        left=max(0.035, 0.32 / column_count),
        right=0.998,
        hspace=0.24,
        wspace=0.06,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=160)
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
    """Place selected original pixels on a white background."""
    isolated = np.full_like(rgb, 255)
    isolated[mask] = rgb[mask]
    return isolated


def _run_dense_sweep(
    data: pd.DataFrame,
    raw_root: Path,
    output_dir: Path,
    result_rows: list[dict[str, object]],
) -> None:
    """Generate the expanded-cleanup and comprehensive ridge-rescue panels."""
    methods = [
        ("source", "Variation 3"),
        ("expanded", "Expanded cleanup (no rescue)"),
        *[
            (
                f"ridge_{threshold:.3f}",
                f"Ridge {threshold:.3f}"
                + (" — current" if np.isclose(threshold, 0.045) else ""),
            )
            for threshold in RIDGE_THRESHOLDS
        ],
    ]
    for folder, folder_data in data.groupby("folder", sort=False):
        species_code = folder.split("_", 1)[0]
        if species_code not in DENSE_MAT_SPECIES:
            continue
        records, threshold = _image_records(folder_data, raw_root)
        calibration_biomass = min(float(record["kg_m2"]) for record in records)
        for record in records:
            rgb = np.asarray(record["rgb"])
            source = source_mask_variations(rgb, threshold)[
                "variation_3_refined_saturation_dark"
            ]
            record["source"] = source
            record["expanded"] = ridge_rescue_mask(source, rgb, math.inf)
            candidates = {
                f"ridge_{ridge_threshold:.3f}": ridge_rescue_mask(
                    source, rgb, ridge_threshold
                )
                for ridge_threshold in RIDGE_THRESHOLDS
            }
            record.update(candidates)
            for method, _ in methods:
                mask = np.asarray(record[method], dtype=bool)
                result_rows.append(
                    {
                        "stage": "02_group_sweeps",
                        "group": "dense_mat",
                        "method": method,
                        "species_code": species_code,
                        "folder": folder,
                        "kg_m2": record["kg_m2"],
                        "is_calibration": record["kg_m2"] == calibration_biomass,
                        "objective_pct_cover": float(100 * mask.mean()),
                        "analyst_pct_cover": record["analyst_pct_cover"],
                    }
                )
        _create_panel(
            records,
            methods,
            output_dir / "02_group_sweeps" / "dense_mat" / "panels" / f"{folder}.png",
            f"{folder} — dense-mat ridge-rescue sweep",
        )


def _run_pixel_sweeps(
    data: pd.DataFrame,
    raw_root: Path,
    output_dir: Path,
    result_rows: list[dict[str, object]],
) -> None:
    """Generate comprehensive color-support panels for both pixel groups."""
    group_definitions = (
        ("broadleaf", BROADLEAF_SPECIES, 2),
        ("fine_structure", FINE_STRUCTURE_SPECIES, 4),
    )
    for group, species_codes, current_selection in group_definitions:
        methods = [
            ("source", "Variation 3"),
            *[
                (
                    f"seeded_{steps}px",
                    f"Seeded {steps}px"
                    + (" — current" if steps == current_selection else ""),
                )
                for steps in PIXEL_STEPS
            ],
        ]
        for folder, folder_data in data.groupby("folder", sort=False):
            species_code = folder.split("_", 1)[0]
            if species_code not in species_codes:
                continue
            records, threshold = _image_records(folder_data, raw_root)
            calibration_biomass = min(float(record["kg_m2"]) for record in records)
            for record in records:
                rgb = np.asarray(record["rgb"])
                source = source_mask_variations(rgb, threshold)[
                    "variation_3_refined_saturation_dark"
                ]
                record["source"] = source
                record.update(
                    {
                        f"seeded_{steps}px": grow_color_support(source, rgb, steps)
                        for steps in PIXEL_STEPS
                    }
                )
                for method, _ in methods:
                    mask = np.asarray(record[method], dtype=bool)
                    result_rows.append(
                        {
                            "stage": "02_group_sweeps",
                            "group": group,
                            "method": method,
                            "species_code": species_code,
                            "folder": folder,
                            "kg_m2": record["kg_m2"],
                            "is_calibration": record["kg_m2"] == calibration_biomass,
                            "objective_pct_cover": float(100 * mask.mean()),
                            "analyst_pct_cover": record["analyst_pct_cover"],
                        }
                    )
            _create_panel(
                records,
                methods,
                output_dir / "02_group_sweeps" / group / "panels" / f"{folder}.png",
                f"{folder} — {group.replace('_', ' ')} color-support sweep",
            )


def _run_source_comparison(
    data: pd.DataFrame,
    raw_root: Path,
    output_dir: Path,
    result_rows: list[dict[str, object]],
) -> None:
    """Generate Step 1 panels containing the three retained source variations."""
    methods = list(SOURCE_LABELS.items())
    for folder, folder_data in data.groupby("folder", sort=False):
        species_code = folder.split("_", 1)[0]
        records, threshold = _image_records(folder_data, raw_root)
        calibration_biomass = min(float(record["kg_m2"]) for record in records)
        for record in records:
            masks = source_mask_variations(np.asarray(record["rgb"]), threshold)
            record.update(masks)
            for method, mask in masks.items():
                result_rows.append(
                    {
                        "stage": "01_source_comparison",
                        "group": "all_species",
                        "method": method,
                        "species_code": species_code,
                        "folder": folder,
                        "kg_m2": record["kg_m2"],
                        "is_calibration": record["kg_m2"] == calibration_biomass,
                        "objective_pct_cover": float(100 * mask.mean()),
                        "analyst_pct_cover": record["analyst_pct_cover"],
                    }
                )
        _create_panel(
            records,
            methods,
            output_dir / "01_source_comparison" / "panels" / f"{folder}.png",
            f"{folder} — Step 1 source-mask comparison",
        )


def _write_results(result_rows: list[dict[str, object]], output_dir: Path) -> None:
    """Write per-image cover, comparison summaries, and the run manifest."""
    results = pd.DataFrame(result_rows)
    results.to_csv(output_dir / "per_image_cover.csv", index=False)
    summaries: list[dict[str, object]] = []
    for (stage, group, method, species_code), frame in results.groupby(
        ["stage", "group", "method", "species_code"], sort=False
    ):
        for subset_name, subset in (
            ("all_images", frame),
            ("validation_only", frame.loc[~frame["is_calibration"]]),
        ):
            summaries.append(
                {
                    "stage": stage,
                    "group": group,
                    "method": method,
                    "species_code": species_code,
                    "evaluation_subset": subset_name,
                    **_calculate_metrics(subset),
                }
            )
    pd.DataFrame(summaries).to_csv(output_dir / "method_summary.csv", index=False)
    manifest = {
        "purpose": "Visual evidence for the retained PhotoLoad method-selection steps",
        "step_1": list(SOURCE_LABELS),
        "step_2_pixel_steps": list(PIXEL_STEPS),
        "step_2_ridge_thresholds": list(RIDGE_THRESHOLDS),
        "historically_reviewed_pixel_steps": list(HISTORICAL_PIXEL_STEPS),
        "historically_reviewed_ridge_thresholds": list(HISTORICAL_RIDGE_THRESHOLDS),
        "current_selections": {
            "broadleaf": "seeded_2px",
            "fine_structure": "seeded_4px",
            "dense_mat": "ridge_0.045",
        },
        "panel_order": "lowest biomass at top; highest biomass at bottom",
        "analyst_cover_role": "comparison guide, not ground truth or training target",
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    """Parse command-line arguments and run the retained comparisons."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    args = parser.parse_args()
    run_experiments(args.pdf, args.output_dir)


def run_experiments(pdf_path: Path, output_dir: Path) -> None:
    """Extract images and generate the two retained method-review stages."""
    output_dir = output_dir.resolve()
    data = pd.read_csv(CALIBRATION_CSV)
    biomass_by_folder = {
        folder: sorted(frame["kg_m2"].astype(float).tolist())
        for folder, frame in data.groupby("folder", sort=False)
    }
    raw_root = output_dir / "00_extracted_images"
    extract_images(pdf_path.resolve(), raw_root, biomass_by_folder)
    result_rows: list[dict[str, object]] = []
    _run_source_comparison(data, raw_root, output_dir, result_rows)
    _run_pixel_sweeps(data, raw_root, output_dir, result_rows)
    _run_dense_sweep(data, raw_root, output_dir, result_rows)
    _write_results(result_rows, output_dir)


if __name__ == "__main__":
    main()
