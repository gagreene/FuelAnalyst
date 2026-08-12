"""Generate the final selected PhotoLoad image masks."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage
from skimage.color import rgb2gray, rgb2lab
from skimage.filters import meijering, sato, threshold_otsu
from skimage.morphology import disk, remove_small_objects


BODY_EDGE_THRESHOLD_FACTOR = 1.08
BOARD_DELTA_E_MINIMUM = 6.0
BROADLEAF_SPECIES = {"AMAL", "ARLA", "MARE", "SYAL", "VAGL"}
DARK_RIDGE_THRESHOLD = 0.03
DENSE_MAT_SPECIES = {"CARU", "FESC"}
EDGE_ARTIFACT_BAND_PIXELS = 20
EDGE_CHROMA_THRESHOLD_FACTOR = 0.75
FINE_STRUCTURE_SPECIES = {"VASC", "XETE"}
LOCAL_WINDOW_SIZE = 15
RIDGE_CONNECTION_RADIUS = 2
RIDGE_EXTENSION_STEPS = 12
RIDGE_MINIMUM_SIZE = 3
RIDGE_RESCUE_THRESHOLD = 0.045
RIDGE_SIGMAS = range(1, 3)
SATURATION_RIDGE_THRESHOLD = 0.03


def _dense_mat_components(
    source: np.ndarray,
    rgb: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return the shared dense-mat cleanup components and ridge response."""
    lab = rgb2lab(rgb)
    lightness = lab[:, :, 0]
    yellow_blue = lab[:, :, 2]
    local_source = ndimage.uniform_filter(
        source.astype(float), size=LOCAL_WINDOW_SIZE, mode="constant"
    )
    dark_recovery = (~source) & (lightness < 50) & (local_source > 0.40)
    neutral_removed = source & (lightness > 64) & (yellow_blue < 18)
    cleaned = (source & ~neutral_removed) | dark_recovery
    gray = rgb2gray(rgb)
    ridge = np.maximum(
        sato(gray, sigmas=(1, 2, 3), black_ridges=True),
        sato(gray, sigmas=(1, 2, 3), black_ridges=False),
    )
    local_cleaned = ndimage.uniform_filter(
        cleaned.astype(float), size=LOCAL_WINDOW_SIZE, mode="constant"
    )
    connected_to_plant = ndimage.binary_dilation(cleaned, iterations=2)
    return cleaned, neutral_removed, ridge, connected_to_plant & (local_cleaned > 0.20)


def _distance_from_board(
    lab: np.ndarray,
    saturation: np.ndarray,
    value: np.ndarray,
    body: np.ndarray,
) -> tuple[np.ndarray, float]:
    """Estimate color distance from pale board pixels."""
    board_seed = (saturation < 0.12) & (value > 0.75) & ~body
    if board_seed.sum() < 100:
        board_seed = ~body
    board_color = np.median(lab[board_seed], axis=0)
    delta_e = np.linalg.norm(lab - board_color, axis=2)
    gate = max(
        BOARD_DELTA_E_MINIMUM,
        float(np.percentile(delta_e[board_seed], 99)),
    )
    return delta_e, gate


def _edge_artifact_mask(chroma: np.ndarray, threshold: float) -> np.ndarray:
    """Identify neutral cross-hatching close to image edges."""
    height, width = chroma.shape
    rows, columns = np.indices((height, width))
    edge_distance = np.minimum.reduce(
        [rows, columns, height - 1 - rows, width - 1 - columns]
    )
    return (edge_distance < EDGE_ARTIFACT_BAND_PIXELS) & (
        chroma < threshold * EDGE_CHROMA_THRESHOLD_FACTOR
    )


def _selected_mask(species_code: str, source: np.ndarray, rgb: np.ndarray) -> np.ndarray:
    """Apply the selected morphology-group recipe."""
    if species_code in BROADLEAF_SPECIES:
        return grow_color_support(source, rgb, steps=2)
    if species_code in DENSE_MAT_SPECIES:
        return ridge_rescue_mask(source, rgb, RIDGE_RESCUE_THRESHOLD)
    if species_code in FINE_STRUCTURE_SPECIES:
        return grow_color_support(source, rgb, steps=4)
    raise ValueError(f"No selected mask recipe for species code {species_code}")


def _selected_ridges(
    ridge_mask: np.ndarray,
    body: np.ndarray,
    delta_e: np.ndarray,
    delta_e_gate: float,
) -> np.ndarray:
    """Retain plant-colored ridge pixels grown from an existing body."""
    candidate = ridge_mask & ~body & (delta_e > delta_e_gate)
    candidate = remove_small_objects(candidate, min_size=RIDGE_MINIMUM_SIZE)
    connection_zone = ndimage.binary_dilation(
        body, structure=disk(RIDGE_CONNECTION_RADIUS)
    )
    selected = candidate & connection_zone
    for _ in range(RIDGE_EXTENSION_STEPS):
        selected = ndimage.binary_dilation(selected, structure=disk(1)) & candidate
    return selected


def _source_masks(
    rgb: np.ndarray,
    chroma_threshold: float,
) -> dict[str, np.ndarray]:
    """Return the three retained source-mask variations."""
    lab = rgb2lab(rgb)
    chroma = np.hypot(lab[:, :, 1], lab[:, :, 2])
    hsv = np.asarray(Image.fromarray(rgb).convert("HSV"), dtype=float)
    saturation = hsv[:, :, 1] / 255.0
    value = hsv[:, :, 2] / 255.0
    body = chroma > chroma_threshold
    refined = ndimage.binary_erosion(body, structure=disk(1)) | (
        body & (chroma > chroma_threshold * BODY_EDGE_THRESHOLD_FACTOR)
    )
    delta_e, delta_e_gate = _distance_from_board(lab, saturation, value, body)
    edge_artifact = _edge_artifact_mask(chroma, chroma_threshold)
    saturation_ridges = (
        meijering(saturation, black_ridges=False, sigmas=RIDGE_SIGMAS)
        > SATURATION_RIDGE_THRESHOLD
    )
    connected_saturation = _selected_ridges(
        saturation_ridges & ~edge_artifact,
        refined,
        delta_e,
        delta_e_gate,
    )
    dark_ridges = (
        meijering(lab[:, :, 0] / 100.0, black_ridges=True, sigmas=RIDGE_SIGMAS)
        > DARK_RIDGE_THRESHOLD
    )
    connected_dark = _selected_ridges(
        dark_ridges & ~edge_artifact,
        refined | connected_saturation,
        delta_e,
        delta_e_gate,
    )
    return {
        "variation_1_cielab": body,
        "variation_2_refined_saturation": refined | connected_saturation,
        "variation_3_refined_saturation_dark": (
            refined | connected_saturation | connected_dark
        ),
    }


def generate_masks(
    raw_root: Path,
    source_root: Path,
    selected_root: Path,
    biomass_by_folder: dict[str, list[float]],
) -> list[dict[str, object]]:
    """Write source/final masks and return objective cover records."""
    records: list[dict[str, object]] = []
    for folder, biomass_values in biomass_by_folder.items():
        species_dir = raw_root / folder
        species_code = folder.split("_", 1)[0]
        image_paths = [
            species_dir / f"{biomass:.3f}_kgm2.jpg" for biomass in biomass_values
        ]
        lowest_rgb = np.asarray(Image.open(image_paths[0]).convert("RGB"))
        lowest_lab = rgb2lab(lowest_rgb)
        threshold = float(
            threshold_otsu(np.hypot(lowest_lab[:, :, 1], lowest_lab[:, :, 2]))
        )
        for image_path in image_paths:
            rgb = np.asarray(Image.open(image_path).convert("RGB"))
            source = source_mask_variations(rgb, threshold)[
                "variation_3_refined_saturation_dark"
            ]
            selected = _selected_mask(species_code, source, rgb)
            relative = Path(species_dir.name) / f"{image_path.stem}.png"
            (source_root / relative.parent).mkdir(parents=True, exist_ok=True)
            (selected_root / relative.parent).mkdir(parents=True, exist_ok=True)
            Image.fromarray(source.astype(np.uint8) * 255).save(source_root / relative)
            Image.fromarray(selected.astype(np.uint8) * 255).save(selected_root / relative)
            records.append(
                {
                    "folder": species_dir.name,
                    "kg_m2": float(image_path.stem.split("_")[0]),
                    "objective_pct_cover": float(100 * selected.mean()),
                    "selected_model": (
                        "broadleaf_2px"
                        if species_code in BROADLEAF_SPECIES
                        else "dense_mat_ridge_0.045"
                        if species_code in DENSE_MAT_SPECIES
                        else "fine_structure_4px"
                    ),
                }
            )
    return records


def grow_color_support(
    source: np.ndarray,
    rgb: np.ndarray,
    steps: int,
) -> np.ndarray:
    """Grow strong plant-color seeds through a source mask for N pixels."""
    if steps < 0:
        raise ValueError("Color-support growth steps cannot be negative")
    lab = rgb2lab(rgb)
    selected = source & (
        (lab[:, :, 0] < 70) | (lab[:, :, 1] < 0) | (lab[:, :, 2] > 25)
    )
    for _ in range(steps):
        selected = ndimage.binary_dilation(selected) & source
    return selected


def ridge_rescue_mask(
    source: np.ndarray,
    rgb: np.ndarray,
    threshold: float,
) -> np.ndarray:
    """Return dense-mat cleanup with neutral blade pixels rescued by ridges."""
    cleaned, neutral_removed, ridge, eligible = _dense_mat_components(source, rgb)
    blade_rescue = neutral_removed & (ridge > threshold) & eligible
    return cleaned | blade_rescue


def source_mask_variations(
    rgb: np.ndarray,
    chroma_threshold: float,
) -> dict[str, np.ndarray]:
    """Return CIELAB, refined+saturation, and refined+saturation+dark masks."""
    return _source_masks(rgb, chroma_threshold)
