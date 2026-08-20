"""Tests for the production PhotoLoad paper workflow."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from PIL import Image

from models.photoload.experiments.run_range_experiment import (
    SOURCE_LABELS,
)
from models.photoload.photoload.biomass import (
    DOCUMENTED_SELECTIONS,
    MODELS,
    SPECIES_ORDER,
)
from models.photoload.photoload.extraction import (
    SYAL_REORDER_FIX,
    _apply_syal_reorder,
)
from models.photoload.photoload.masks import (
    PIXEL_STEPS,
    RIDGE_THRESHOLDS,
    color_support_ensemble,
    color_support_sweep,
    grow_color_support,
    ridge_rescue_ensemble,
    ridge_rescue_mask,
    ridge_rescue_sweep,
)
from models.photoload.photoload.workflow import (
    CALIBRATION_CSV,
    EXPECTED_SOURCE_PDF_SHA256,
    _sha256,
    _validate_source_pdf,
    run_workflow,
)


def test_all_candidate_models_cross_origin() -> None:
    """Every fitted form must enforce zero biomass at zero cover."""
    for function, parameter_count, _, _ in MODELS.values():
        parameters = [1.0] * parameter_count
        assert function(np.array([0.0]), *parameters)[0] == 0.0


def test_apply_syal_reorder_copies_sources_before_overwriting(tmp_path: Path) -> None:
    """The cyclic rename must preserve pixels and release every source file."""
    expected_colors: dict[float, tuple[int, int, int]] = {}
    for index, (old_biomass, new_biomass) in enumerate(SYAL_REORDER_FIX.items()):
        color = (20 + 40 * index, 30 + 30 * index, 40 + 20 * index)
        Image.new("RGB", (8, 8), color).save(
            tmp_path / f"{old_biomass:.3f}_kgm2.jpg",
            quality=100,
            subsampling=0,
        )
        expected_colors[new_biomass] = color

    _apply_syal_reorder(tmp_path)

    for new_biomass, expected_color in expected_colors.items():
        output_path = tmp_path / f"{new_biomass:.3f}_kgm2.jpg"
        with Image.open(output_path) as image:
            actual_color = image.convert("RGB").getpixel((0, 0))
        assert actual_color == pytest.approx(expected_color, abs=2)


def test_calibration_table_is_complete_and_unique() -> None:
    """The reference dataset must contain one row for each of the 81 images."""
    calibration = pd.read_csv(CALIBRATION_CSV)
    assert len(calibration) == 81
    assert calibration["species"].nunique() == 9
    assert not calibration.duplicated(["folder", "kg_m2"]).any()


def test_documented_selection_exists_for_every_species() -> None:
    """Multi-criteria selection must remain explicit for all nine species."""
    assert set(DOCUMENTED_SELECTIONS) == set(SPECIES_ORDER)
    assert all(selection["basis"] for selection in DOCUMENTED_SELECTIONS.values())
    assert all(
        selection["model"] in MODELS
        for selection in DOCUMENTED_SELECTIONS.values()
    )
    assert DOCUMENTED_SELECTIONS["Symphoricarpos albus"]["model"] == "quadratic_origin"


def test_ensemble_masks_equal_the_mean_of_parameter_masks() -> None:
    """Optimized ensemble functions must reproduce explicit mask averaging."""
    rows, columns = np.indices((15, 15))
    rgb = np.stack(
        [
            40 + rows * 8,
            30 + columns * 9,
            20 + ((rows + columns) % 10) * 12,
        ],
        axis=2,
    ).astype(np.uint8)
    source = np.ones((15, 15), dtype=bool)
    pixel_steps = (1, 2, 3)
    ridge_thresholds = (0.0, 0.05, 0.10)
    expected_pixels = np.mean(
        [grow_color_support(source, rgb, steps) for steps in pixel_steps], axis=0
    )
    expected_ridges = np.mean(
        [ridge_rescue_mask(source, rgb, value) for value in ridge_thresholds],
        axis=0,
    )
    assert np.array_equal(
        color_support_ensemble(source, rgb, pixel_steps), expected_pixels
    )
    assert np.array_equal(
        ridge_rescue_ensemble(source, rgb, ridge_thresholds), expected_ridges
    )
    assert all(
        np.array_equal(mask, expected)
        for mask, expected in zip(
            color_support_sweep(source, rgb, pixel_steps).values(),
            [grow_color_support(source, rgb, steps) for steps in pixel_steps],
        )
    )
    assert all(
        np.array_equal(mask, expected)
        for mask, expected in zip(
            ridge_rescue_sweep(source, rgb, ridge_thresholds).values(),
            [ridge_rescue_mask(source, rgb, value) for value in ridge_thresholds],
        )
    )


def test_experiment_grid_contains_requested_comparisons() -> None:
    """The experiment must contain both stages and complete ensemble ranges."""
    assert tuple(SOURCE_LABELS) == (
        "variation_1_cielab",
        "variation_2_refined_saturation",
        "variation_3_refined_saturation_dark",
    )
    assert PIXEL_STEPS == tuple(range(1, 31))
    assert RIDGE_THRESHOLDS == tuple(value / 1000 for value in range(0, 225, 5))


def test_run_workflow_rejects_unexpected_pdf_before_writing(tmp_path: Path) -> None:
    """A different PDF must fail before extraction or output begins."""
    pdf_path = tmp_path / "unexpected.pdf"
    output_dir = tmp_path / "output"
    pdf_path.write_bytes(b"not the production PhotoLoad report")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        run_workflow(pdf_path, output_dir)
    assert not output_dir.exists()


def test_source_pdf_digest_matches_documented_value() -> None:
    """The stored report must match the exact production input."""
    repository_root = Path(__file__).resolve().parents[2]
    pdf_path = (
        repository_root
        / "docs"
        / "reference"
        / "rmrs_gtr190_Kean_and_Dickinson_2007.pdf"
    )
    assert _sha256(pdf_path) == EXPECTED_SOURCE_PDF_SHA256
    assert _validate_source_pdf(pdf_path) == EXPECTED_SOURCE_PDF_SHA256


def test_source_pdf_is_stored_at_the_documented_location() -> None:
    """The production workflow's default source report must be in the repo."""
    repository_root = Path(__file__).resolve().parents[2]
    assert (
            repository_root
            / "docs"
            / "reference"
            / "rmrs_gtr190_Kean_and_Dickinson_2007.pdf"
    ).is_file()
