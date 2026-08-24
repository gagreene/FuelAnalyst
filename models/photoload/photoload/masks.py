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
PIXEL_STEPS = tuple(range(1, 31))
RIDGE_CONNECTION_RADIUS = 2
RIDGE_EXTENSION_STEPS = 12
RIDGE_MINIMUM_SIZE = 3
RIDGE_THRESHOLDS = tuple(value / 1000 for value in range(0, 225, 5))
RIDGE_SIGMAS = range(1, 3)
SATURATION_RIDGE_THRESHOLD = 0.03


def _dense_mat_components(
        source: np.ndarray,
        rgb: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Return the shared dense-mat cleanup components and ridge response.

    :param source: Boolean source mask.
    :param rgb: Source image as an RGB array.
    :return: The shared dense-mat cleanup components and ridge response.
    """
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
    """
    Estimate color distance from pale board pixels.

    :param lab: Image values in CIELAB color space.
    :param saturation: Per-pixel saturation values.
    :param value: Serialized parameter value.
    :param body: Boolean mask identifying the plant body.
    :return: Per-pixel board color distances and the minimum accepted distance.
    """
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
    """
    Identify neutral cross-hatching close to image edges.

    :param chroma: Per-pixel chroma values.
    :param threshold: Threshold applied to the calculated response.
    :return: Boolean mask identifying neutral edge artifacts.
    """
    height, width = chroma.shape
    rows, columns = np.indices((height, width))
    edge_distance = np.minimum.reduce(
        [rows, columns, height - 1 - rows, width - 1 - columns]
    )
    return (edge_distance < EDGE_ARTIFACT_BAND_PIXELS) & (
            chroma < threshold * EDGE_CHROMA_THRESHOLD_FACTOR
    )


def _ensemble_mask(species_code: str, source: np.ndarray, rgb: np.ndarray) -> np.ndarray:
    """
    Return the morphology-group ensemble selection frequency.

    :param species_code: PhotoLoad species code.
    :param source: Boolean source mask.
    :param rgb: Source image as an RGB array.
    :return: The morphology-group ensemble selection frequency.
    """
    if species_code in BROADLEAF_SPECIES:
        return color_support_ensemble(source, rgb)
    if species_code in DENSE_MAT_SPECIES:
        return ridge_rescue_ensemble(source, rgb)
    if species_code in FINE_STRUCTURE_SPECIES:
        return color_support_ensemble(source, rgb)
    raise ValueError(f"No ensemble mask recipe for species code {species_code}")


def _selected_ridges(
        ridge_mask: np.ndarray,
        body: np.ndarray,
        delta_e: np.ndarray,
        delta_e_gate: float,
) -> np.ndarray:
    """
    Retain plant-colored ridge pixels grown from an existing body.

    :param ridge_mask: Boolean mask of candidate ridge pixels.
    :param body: Boolean mask identifying the plant body.
    :param delta_e: Per-pixel color distance from the board.
    :param delta_e_gate: Minimum color distance required for ridge rescue.
    :return: Boolean mask of ridge pixels eligible for plant recovery.
    """
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
    """
    Return the three retained source-mask variations.

    :param rgb: Source image as an RGB array.
    :param chroma_threshold: Chroma threshold used to initialize the source mask.
    :return: The three retained source-mask variations.
    """
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


def color_support_ensemble(
        source: np.ndarray,
        rgb: np.ndarray,
        steps: tuple[int, ...] = PIXEL_STEPS,
) -> np.ndarray:
    """
    Average seeded color-support masks across the full growth range.

    :param source: Boolean source mask.
    :param rgb: Source image as an RGB array.
    :param steps: Growth steps included in the calculation.
    :return: Per-pixel selection frequency across the requested growth steps.
    """
    if not steps or min(steps) < 1 or tuple(sorted(set(steps))) != steps:
        raise ValueError("Color-support ensemble steps must be unique increasing positives")
    lab = rgb2lab(rgb)
    selected = source & (
            (lab[:, :, 0] < 70) | (lab[:, :, 1] < 0) | (lab[:, :, 2] > 25)
    )
    accumulator = np.zeros(source.shape, dtype=np.float64)
    step_index = 0
    for iteration in range(1, steps[-1] + 1):
        selected = ndimage.binary_dilation(selected) & source
        if iteration == steps[step_index]:
            accumulator += selected
            step_index += 1
            if step_index == len(steps):
                break
    return accumulator / len(steps)


def color_support_stabilization_step(source: np.ndarray, rgb: np.ndarray) -> int:
    """
    Return the final seeded-growth step that changes the selected mask.

    :param source: Boolean source mask.
    :param rgb: Source image as an RGB array.
    :return: The final seeded-growth step that changes the selected mask.
    """
    lab = rgb2lab(rgb)
    selected = source & (
            (lab[:, :, 0] < 70) | (lab[:, :, 1] < 0) | (lab[:, :, 2] > 25)
    )
    for step in range(1, source.size + 1):
        grown = ndimage.binary_dilation(selected) & source
        if np.array_equal(grown, selected):
            return step - 1
        selected = grown
    raise RuntimeError("Seeded color-support growth did not stabilize")


def color_support_sweep(
        source: np.ndarray,
        rgb: np.ndarray,
        steps: tuple[int, ...] = PIXEL_STEPS,
) -> dict[int, np.ndarray]:
    """
    Return seeded color-support masks while growing the seeds only once.

    :param source: Boolean source mask.
    :param rgb: Source image as an RGB array.
    :param steps: Growth steps included in the calculation.
    :return: Seeded color-support masks while growing the seeds only once.
    """
    if not steps or min(steps) < 1 or tuple(sorted(set(steps))) != steps:
        raise ValueError("Color-support sweep steps must be unique increasing positives")
    lab = rgb2lab(rgb)
    selected = source & (
            (lab[:, :, 0] < 70) | (lab[:, :, 1] < 0) | (lab[:, :, 2] > 25)
    )
    masks: dict[int, np.ndarray] = {}
    step_index = 0
    for iteration in range(1, steps[-1] + 1):
        selected = ndimage.binary_dilation(selected) & source
        if iteration == steps[step_index]:
            masks[iteration] = selected.copy()
            step_index += 1
            if step_index == len(steps):
                break
    return masks


def generate_masks(
        raw_root: Path,
        source_root: Path,
        frequency_root: Path,
        biomass_by_folder: dict[str, list[float]],
) -> list[dict[str, object]]:
    """
    Write source/ensemble masks and return objective cover records.

    :param raw_root: Directory containing extracted PhotoLoad images.
    :param source_root: Directory containing source-mask images.
    :param frequency_root: Directory containing ensemble selection-frequency images.
    :param biomass_by_folder: Biomass values keyed by PhotoLoad species folder.
    :return: Objective-cover records for the generated species masks.
    """
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
            selected = _ensemble_mask(species_code, source, rgb)
            relative = Path(species_dir.name) / f"{image_path.stem}.png"
            (source_root / relative.parent).mkdir(parents=True, exist_ok=True)
            (frequency_root / relative.parent).mkdir(parents=True, exist_ok=True)
            Image.fromarray(source.astype(np.uint8) * 255).save(source_root / relative)
            Image.fromarray(np.rint(selected * 65535).astype(np.uint16)).save(
                frequency_root / relative
            )
            records.append(
                {
                    "folder": species_dir.name,
                    "kg_m2": float(image_path.stem.split("_")[0]),
                    "objective_pct_cover": float(100 * selected.mean()),
                    "selected_model": (
                        "broadleaf_ensemble_1_30px"
                        if species_code in BROADLEAF_SPECIES
                        else "dense_mat_ensemble_0.000_0.220"
                        if species_code in DENSE_MAT_SPECIES
                        else "fine_structure_ensemble_1_30px"
                    ),
                }
            )
    return records


def grow_color_support(
        source: np.ndarray,
        rgb: np.ndarray,
        steps: int,
) -> np.ndarray:
    """
    Grow strong plant-color seeds through a source mask for N pixels.

    :param source: Boolean source mask.
    :param rgb: Source image as an RGB array.
    :param steps: Growth steps included in the calculation.
    :return: Boolean color-support mask after the requested growth steps.
    """
    if steps < 0:
        raise ValueError("Color-support growth steps cannot be negative")
    lab = rgb2lab(rgb)
    selected = source & (
            (lab[:, :, 0] < 70) | (lab[:, :, 1] < 0) | (lab[:, :, 2] > 25)
    )
    for _ in range(steps):
        selected = ndimage.binary_dilation(selected) & source
    return selected


def maximum_eligible_ridge_response(source: np.ndarray, rgb: np.ndarray) -> float:
    """
    Return the largest ridge response among pixels eligible for rescue.

    :param source: Boolean source mask.
    :param rgb: Source image as an RGB array.
    :return: The largest ridge response among pixels eligible for rescue.
    """
    _, neutral_removed, ridge, eligible = _dense_mat_components(source, rgb)
    responses = ridge[neutral_removed & eligible]
    return float(responses.max()) if responses.size else 0.0


def ridge_rescue_ensemble(
        source: np.ndarray,
        rgb: np.ndarray,
        thresholds: tuple[float, ...] = RIDGE_THRESHOLDS,
) -> np.ndarray:
    """
    Average dense-mat masks across the full ridge-response range.

    :param source: Boolean source mask.
    :param rgb: Source image as an RGB array.
    :param thresholds: Response thresholds included in the calculation.
    :return: Per-pixel selection frequency across the ridge thresholds.
    """
    if not thresholds or min(thresholds) < 0 or tuple(sorted(set(thresholds))) != thresholds:
        raise ValueError("Ridge thresholds must be unique increasing nonnegative values")
    cleaned, neutral_removed, ridge, eligible = _dense_mat_components(source, rgb)
    rescuable = neutral_removed & eligible
    accumulator = np.zeros(source.shape, dtype=np.float64)
    for threshold in thresholds:
        accumulator += cleaned | (rescuable & (ridge > threshold))
    return accumulator / len(thresholds)


def ridge_rescue_mask(
        source: np.ndarray,
        rgb: np.ndarray,
        threshold: float,
) -> np.ndarray:
    """
    Return dense-mat cleanup with neutral blade pixels rescued by ridges.

    :param source: Boolean source mask.
    :param rgb: Source image as an RGB array.
    :param threshold: Threshold applied to the calculated response.
    :return: Dense-mat cleanup with neutral blade pixels rescued by ridges.
    """
    cleaned, neutral_removed, ridge, eligible = _dense_mat_components(source, rgb)
    blade_rescue = neutral_removed & (ridge > threshold) & eligible
    return cleaned | blade_rescue


def ridge_rescue_sweep(
        source: np.ndarray,
        rgb: np.ndarray,
        thresholds: tuple[float, ...] = RIDGE_THRESHOLDS,
) -> dict[float, np.ndarray]:
    """
    Return ridge-rescue masks from one calculation of shared components.

    :param source: Boolean source mask.
    :param rgb: Source image as an RGB array.
    :param thresholds: Response thresholds included in the calculation.
    :return: Ridge-rescue masks from one calculation of shared components.
    """
    if not thresholds or min(thresholds) < 0 or tuple(sorted(set(thresholds))) != thresholds:
        raise ValueError("Ridge thresholds must be unique increasing nonnegative values")
    cleaned, neutral_removed, ridge, eligible = _dense_mat_components(source, rgb)
    rescuable = neutral_removed & eligible
    return {
        threshold: cleaned | (rescuable & (ridge > threshold))
        for threshold in thresholds
    }


def source_mask_variations(
        rgb: np.ndarray,
        chroma_threshold: float,
) -> dict[str, np.ndarray]:
    """
    Return CIELAB, refined+saturation, and refined+saturation+dark masks.

    :param rgb: Source image as an RGB array.
    :param chroma_threshold: Chroma threshold used to initialize the source mask.
    :return: CIELAB, refined+saturation, and refined+saturation+dark masks.
    """
    return _source_masks(rgb, chroma_threshold)
