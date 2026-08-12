"""Orchestrate the frozen PhotoLoad workflow and its reproducibility checks."""

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
from .masks import generate_masks


MODEL_ROOT = Path(__file__).resolve().parents[1]
CALIBRATION_CSV = MODEL_ROOT / "data" / "paper_calibration.csv"


def _create_species_panels(
    data: pd.DataFrame,
    raw_root: Path,
    selected_root: Path,
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
            mask = np.asarray(Image.open(selected_root / folder / f"{stem}.png")) > 0
            isolated = np.full_like(rgb, 255)
            isolated[mask] = rgb[mask]
            axes[row_index, 0].imshow(rgb)
            axes[row_index, 1].imshow(isolated)
            axes[row_index, 0].set_ylabel(
                f"{row.kg_m2:.3f} kg/m²\nAnalyst={row.analyst_pct_cover:.1f}%",
                fontsize=9,
            )
            axes[row_index, 1].set_title(
                f"Final cover={row.objective_pct_cover:.1f}%", fontsize=9
            )
            if row_index == 0:
                axes[row_index, 0].set_title("Original", fontsize=11)
                axes[row_index, 1].set_title("Final selected mask", fontsize=11)
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


def _load_calibration() -> pd.DataFrame:
    """Load and validate the frozen paper calibration table."""
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


def run_workflow(pdf_path: Path, output_dir: Path) -> None:
    """Run extraction, final masking, model fitting, and paper-output checks."""
    pdf_path = pdf_path.resolve()
    output_dir = output_dir.resolve()
    data = _load_calibration()
    biomass_by_folder = {
        folder: sorted(folder_data["kg_m2"].astype(float).tolist())
        for folder, folder_data in data.groupby("folder", sort=False)
    }
    raw_root = output_dir / "01_extracted_images"
    source_root = output_dir / "02_source_masks"
    selected_root = output_dir / "03_selected_masks"
    cover_dir = output_dir / "04_objective_cover"
    model_dir = output_dir / "05_biomass_models"
    panel_dir = output_dir / "06_species_panels"
    extract_images(pdf_path, raw_root, biomass_by_folder)
    measured = pd.DataFrame(
        generate_masks(raw_root, source_root, selected_root, biomass_by_folder)
    )
    results = data.merge(measured, on=["folder", "kg_m2"], validate="one_to_one")
    if not (results["selected_model_x"] == results["selected_model_y"]).all():
        raise RuntimeError("Generated mask recipe does not match frozen calibration metadata")
    results = results.drop(columns=["selected_model_y"]).rename(
        columns={"selected_model_x": "selected_model"}
    )
    results["cover_difference_from_reference"] = (
        results["objective_pct_cover"] - results["reference_objective_pct_cover"]
    )
    maximum_difference = float(results["cover_difference_from_reference"].abs().max())
    if maximum_difference > 1e-9:
        raise RuntimeError(
            "Generated objective cover does not reproduce the frozen paper results; "
            f"maximum difference={maximum_difference:.12g} percentage points"
        )
    cover_dir.mkdir(parents=True, exist_ok=True)
    results.to_csv(cover_dir / "selected_objective_pct_cover.csv", index=False)
    selected = fit_models(results, model_dir)
    _create_species_panels(results, raw_root, selected_root, panel_dir)
    manifest = {
        "workflow": "FuelAnalyst paper PhotoLoad workflow",
        "source_pdf": str(pdf_path),
        "source_pdf_sha256": _sha256(pdf_path),
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
