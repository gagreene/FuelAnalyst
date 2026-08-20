"""Orchestrate the production PhotoLoad workflow and its reproducibility checks."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from PIL import Image

from .biomass import fit_models
from .extraction import extract_images
from .masks import (
    DENSE_MAT_SPECIES,
    PIXEL_STEPS,
    RIDGE_THRESHOLDS,
    color_support_sweep,
    generate_masks,
    ridge_rescue_sweep,
)

MODEL_ROOT = Path(__file__).resolve().parents[1]
CALIBRATION_CSV = MODEL_ROOT / "data" / "paper_calibration.csv"
EXPECTED_SOURCE_PDF_SHA256 = (
    "14eaeb69784e3f26dee23a67686fad9c86e50099aaca60bcc079f687d1c313c2"
)
PANEL_PAGE_SIZE = 8


def _create_parameter_panel(
        records: list[dict[str, object]],
        methods: list[tuple[str, str]],
        output_path: Path,
        title: str,
) -> None:
    """Render one page of complete-range production masks."""
    column_count = len(methods) + 1
    figure, axes = plt.subplots(
        len(records),
        column_count,
        figsize=(1.75 * column_count, 1.75 * len(records)),
        squeeze=False,
    )
    for row_index, record in enumerate(records):
        rgb = np.asarray(record["rgb"])
        axes[row_index, 0].imshow(rgb)
        axes[row_index, 0].set_ylabel(
            f"{float(record['kg_m2']):.3f} kg/m²\n"
            f"Analyst={float(record['analyst_pct_cover']):.1f}%",
            fontsize=7,
        )
        if row_index == 0:
            axes[row_index, 0].set_title("Original", fontsize=8)
        for column_index, (method, label) in enumerate(methods, start=1):
            mask = np.asarray(record[method])
            axes[row_index, column_index].imshow(_isolate_plant(rgb, mask))
            heading = f"{100 * mask.mean():.1f}%"
            if row_index == 0:
                heading = f"{label}\n{heading}"
            axes[row_index, column_index].set_title(heading, fontsize=7)
        for axis in axes[row_index]:
            axis.set_xticks([])
            axis.set_yticks([])
    figure.suptitle(title, fontsize=11, y=0.998)
    figure.subplots_adjust(
        top=0.955, bottom=0.01, left=0.055, right=0.998, hspace=0.22, wspace=0.04
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=120)
    plt.close(figure)


def _create_parameter_panel_pages(
        records: list[dict[str, object]],
        fixed_methods: list[tuple[str, str]],
        swept_methods: list[tuple[str, str]],
        output_path: Path,
        title: str,
) -> None:
    """Paginate every parameter-specific mask in the production range."""
    page_count = int(np.ceil(len(swept_methods) / PANEL_PAGE_SIZE))
    for page_index in range(page_count):
        start = page_index * PANEL_PAGE_SIZE
        methods = fixed_methods + swept_methods[start: start + PANEL_PAGE_SIZE]
        page_path = output_path.with_name(
            f"{output_path.stem}_page_{page_index + 1:02d}{output_path.suffix}"
        )
        _create_parameter_panel(
            records,
            methods,
            page_path,
            f"{title} — page {page_index + 1} of {page_count}",
        )


def _create_parameter_panels(
        data: pd.DataFrame,
        frequency_root: Path,
        raw_root: Path,
        source_root: Path,
        output_dir: Path,
) -> None:
    """Write complete production-range panels for all nine species."""
    for folder, folder_data in data.groupby("folder", sort=False):
        species_code = folder.split("_", 1)[0]
        records: list[dict[str, object]] = []
        for row in folder_data.sort_values("kg_m2").itertuples(index=False):
            stem = f"{row.kg_m2:.3f}_kgm2"
            rgb = np.asarray(Image.open(raw_root / folder / f"{stem}.jpg").convert("RGB"))
            source = np.asarray(
                Image.open(source_root / folder / f"{stem}.png"), dtype=np.uint8
            ).astype(bool)
            ensemble = np.asarray(
                Image.open(frequency_root / folder / f"{stem}.png"), dtype=np.float64
            ) / 65535.0
            record: dict[str, object] = {
                "analyst_pct_cover": float(row.analyst_pct_cover),
                "ensemble": ensemble,
                "kg_m2": float(row.kg_m2),
                "rgb": rgb,
                "source": source,
            }
            if species_code in DENSE_MAT_SPECIES:
                sweep = ridge_rescue_sweep(source, rgb)
                record.update(
                    {f"ridge_{threshold:.3f}": mask for threshold, mask in sweep.items()}
                )
            else:
                sweep = color_support_sweep(source, rgb)
                record.update({f"seeded_{step}px": mask for step, mask in sweep.items()})
            records.append(record)

        fixed_methods = [("source", "Source mask"), ("ensemble", "Ensemble mean")]
        if species_code in DENSE_MAT_SPECIES:
            swept_methods = [
                (f"ridge_{threshold:.3f}", f"Ridge {threshold:.3f}")
                for threshold in RIDGE_THRESHOLDS
            ]
        else:
            swept_methods = [
                (f"seeded_{step}px", f"Seeded {step}px") for step in PIXEL_STEPS
            ]
        _create_parameter_panel_pages(
            records,
            fixed_methods,
            swept_methods,
            output_dir / f"{folder}.png",
            f"{folder} — complete production ensemble",
        )


def _create_species_panels(
        data: pd.DataFrame,
        frequency_root: Path,
        raw_root: Path,
        output_dir: Path,
) -> None:
    """Write original-versus-final panels for all nine species."""
    output_dir.mkdir(parents=True, exist_ok=True)
    for folder, folder_data in data.groupby("folder", sort=False):
        ordered = folder_data.sort_values("kg_m2")
        figure, axes = plt.subplots(len(ordered), 2, figsize=(8, 3.35 * len(ordered)))
        for row_index, row in enumerate(ordered.itertuples(index=False)):
            stem = f"{row.kg_m2:.3f}_kgm2"
            rgb = np.asarray(Image.open(raw_root / folder / f"{stem}.jpg").convert("RGB"))
            selection_frequency = np.asarray(
                Image.open(frequency_root / folder / f"{stem}.png"), dtype=np.float64
            ) / 65535.0
            weight = selection_frequency[:, :, np.newaxis]
            isolated = np.rint(rgb * weight + 255 * (1 - weight)).astype(np.uint8)
            axes[row_index, 0].imshow(rgb)
            axes[row_index, 1].imshow(isolated)
            axes[row_index, 0].set_ylabel(
                f"{row.kg_m2:.3f} kg/m²\nAnalyst={row.analyst_pct_cover:.1f}%",
                fontsize=9,
            )
            axes[row_index, 1].set_title(
                f"Ensemble cover={row.objective_pct_cover:.1f}%", fontsize=9
            )
            if row_index == 0:
                axes[row_index, 0].set_title("Original", fontsize=11)
                axes[row_index, 1].set_title("Ensemble selection frequency", fontsize=11)
            for axis in axes[row_index]:
                axis.set_xticks([])
                axis.set_yticks([])
        species = str(ordered.iloc[0]["species"])
        method = str(ordered.iloc[0]["selected_model"])
        figure.suptitle(
            f"{folder.split('_', 1)[0]} — {species}\n{method}",
            fontsize=14,
            y=0.997,
        )
        figure.subplots_adjust(
            top=0.955, bottom=0.01, left=0.15, right=0.98, hspace=0.25
        )
        figure.savefig(output_dir / f"{folder}_original_vs_final.png", dpi=200)
        plt.close(figure)


def _isolate_plant(rgb: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Blend selected original pixels with a white background."""
    weight = np.asarray(mask, dtype=np.float64)[:, :, np.newaxis]
    return np.rint(rgb * weight + 255 * (1 - weight)).astype(np.uint8)


def _load_calibration() -> pd.DataFrame:
    """Load and validate the versioned reference calibration table."""
    data = pd.read_csv(CALIBRATION_CSV)
    required = {
        "species",
        "folder",
        "group",
        "kg_m2",
        "analyst_pct_cover",
        "reference_objective_pct_cover",
        "selected_model",
    }
    missing = required - set(data.columns)
    if missing:
        raise ValueError(f"Calibration table is missing columns: {sorted(missing)}")
    if len(data) != 81 or data.duplicated(["folder", "kg_m2"]).any():
        raise ValueError("Calibration table must contain 81 unique folder/biomass rows")
    return data


def _sha256(path: Path) -> str:
    """Return a file's SHA-256 digest."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _validate_source_pdf(pdf_path: Path) -> str:
    """Return the digest when the source PDF matches the versioned reference."""
    if not pdf_path.is_file():
        raise FileNotFoundError(f"PhotoLoad PDF not found: {pdf_path}")
    actual_digest = _sha256(pdf_path)
    if actual_digest != EXPECTED_SOURCE_PDF_SHA256:
        raise ValueError(
            "PhotoLoad PDF SHA-256 mismatch: "
            f"expected {EXPECTED_SOURCE_PDF_SHA256}, got {actual_digest}"
        )
    return actual_digest


def run_workflow(pdf_path: Path, output_dir: Path) -> None:
    """Run extraction, final masking, model fitting, and paper-output checks."""
    pdf_path = pdf_path.resolve()
    output_dir = output_dir.resolve()
    source_pdf_sha256 = _validate_source_pdf(pdf_path)
    data = _load_calibration()
    biomass_by_folder = {
        folder: sorted(folder_data["kg_m2"].astype(float).tolist())
        for folder, folder_data in data.groupby("folder", sort=False)
    }
    raw_root = output_dir / "01_extracted_images"
    source_root = output_dir / "02_source_masks"
    frequency_root = output_dir / "03_ensemble_frequency"
    cover_dir = output_dir / "04_objective_cover"
    model_dir = output_dir / "05_biomass_models"
    panel_dir = output_dir / "06_species_panels"
    parameter_panel_dir = output_dir / "07_parameter_panels"
    extract_images(pdf_path, raw_root, biomass_by_folder)
    measured = pd.DataFrame(
        generate_masks(raw_root, source_root, frequency_root, biomass_by_folder)
    )
    results = data.merge(measured, on=["folder", "kg_m2"], validate="one_to_one")
    if not (results["selected_model_x"] == results["selected_model_y"]).all():
        raise RuntimeError(
            "Generated mask recipe does not match reference calibration metadata"
        )
    results = results.drop(columns=["selected_model_y"]).rename(
        columns={"selected_model_x": "selected_model"}
    )
    results["cover_difference_from_reference"] = (
            results["objective_pct_cover"] - results["reference_objective_pct_cover"]
    )
    maximum_difference = float(results["cover_difference_from_reference"].abs().max())
    if maximum_difference > 1e-9:
        raise RuntimeError(
            "Generated objective cover does not reproduce the reference results; "
            f"maximum difference={maximum_difference:.12g} percentage points"
        )
    cover_dir.mkdir(parents=True, exist_ok=True)
    results.to_csv(cover_dir / "ensemble_objective_pct_cover.csv", index=False)
    selected = fit_models(results, model_dir)
    _create_species_panels(results, frequency_root, raw_root, panel_dir)
    _create_parameter_panels(
        results, frequency_root, raw_root, source_root, parameter_panel_dir
    )
    manifest = {
        "cover_ensemble": {
            "broadleaf_and_fine_structure_pixel_steps": list(PIXEL_STEPS),
            "dense_mat_ridge_thresholds": list(RIDGE_THRESHOLDS),
            "formulation": "unweighted arithmetic mean across all masks",
        },
        "workflow": "FuelAnalyst paper PhotoLoad workflow",
        "source_pdf": str(pdf_path),
        "source_pdf_sha256": source_pdf_sha256,
        "calibration_table": str(CALIBRATION_CSV),
        "n_images": len(results),
        "n_species": results["species"].nunique(),
        "maximum_cover_difference_from_reference_pct_points": maximum_difference,
        "selected_models": dict(zip(selected["species"], selected["model"])),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
