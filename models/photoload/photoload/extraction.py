"""Extract and crop the 81 PhotoLoad calibration photographs."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pymupdf as fitz
import numpy as np
from PIL import Image


SPECIES_PAGES = {
    25: "AMAL_Amelanchier_alnifolia",
    26: "MARE_Berberis_repens",
    27: "SYAL_Symphoricarpos_albus",
    28: "VAGL_Vaccinium_globulare",
    29: "VASC_Vaccinium_scoparium",
    30: "ARLA_Arnica_latifolia",
    31: "CARU_Calamagrostis_rubescens",
    32: "FESC_Festuca_scabrella",
    33: "XETE_Xerophyllum_tenax",
}
SYAL_REORDER_FIX = {
    0.08: 0.15,
    0.10: 0.08,
    0.12: 0.10,
    0.15: 0.12,
}


def _apply_syal_reorder(species_dir: Path) -> None:
    """Apply the defined post-export SYAL sequence correction."""
    corrected = {
        new_biomass: Image.open(species_dir / f"{old_biomass:.3f}_kgm2.jpg").copy()
        for old_biomass, new_biomass in SYAL_REORDER_FIX.items()
    }
    for new_biomass, image in corrected.items():
        image.save(species_dir / f"{new_biomass:.3f}_kgm2.jpg", quality=95)


def _crop_line(gray_panel: np.ndarray, side: str, offset: int) -> np.ndarray:
    """Return one line at an offset from a panel edge."""
    if side == "left":
        return gray_panel[:, offset]
    if side == "right":
        return gray_panel[:, -1 - offset]
    if side == "top":
        return gray_panel[offset, :]
    return gray_panel[-1 - offset, :]


def _detect_boundaries(
    array: np.ndarray,
    axis: int,
    minimum_gap: int,
) -> list[tuple[int, int]]:
    """Return sufficiently wide near-white gap runs along an axis."""
    gap_indices = np.where(array.mean(axis=axis) > 250)[0]
    return [run for run in _find_runs(gap_indices) if run[1] - run[0] >= minimum_gap]


def _detect_board_edge_trim(
    gray_panel: np.ndarray,
    side: str,
    search_window: int = 4,
    lookahead: int = 4,
    jump_threshold: float = 15,
) -> int:
    """Return pixels to remove from one physical board edge."""
    values = [
        _crop_line(gray_panel, side, offset).mean()
        for offset in range(search_window)
    ]
    reference = np.mean(
        [
            _crop_line(gray_panel, side, offset).mean()
            for offset in range(search_window, search_window + lookahead)
        ]
    )
    minimum_index = int(np.argmin(values))
    return minimum_index + 1 if reference - values[minimum_index] > jump_threshold else 0


def _find_runs(indices: np.ndarray) -> list[tuple[int, int]]:
    """Group consecutive integer indices into inclusive runs."""
    if len(indices) == 0:
        return []
    runs: list[tuple[int, int]] = []
    start = previous = int(indices[0])
    for value in indices[1:]:
        value = int(value)
        if value != previous + 1:
            runs.append((start, previous))
            start = value
        previous = value
    runs.append((start, previous))
    return runs


def _find_square_box(
    gray: np.ndarray,
    row_top: int,
    row_bottom: int,
    column_left: int,
    column_right: int,
) -> tuple[int, int, int, int]:
    """Locate the interior of the printed square surrounding one photograph."""
    block = gray[row_top:row_bottom, column_left:column_right]
    dark = block < 100
    height, width = block.shape
    row_runs = np.array([_maximum_run(dark[row, :]) for row in range(height)])
    row_groups = _find_runs(np.where(row_runs > 0.85 * width)[0])
    square_top = row_groups[0][1] + 1
    square_bottom = row_groups[1][0]

    square_block = block[row_groups[0][0] : row_groups[1][1] + 1, :]
    column_runs = np.array(
        [_maximum_run(square_block[:, column] < 100) for column in range(width)]
    )
    edge = min(40, width // 4)
    square_left = int(np.argmax(column_runs[:edge])) + 1
    square_right = width - edge + int(np.argmax(column_runs[-edge:]))
    return (
        column_left + square_left,
        row_top + square_top,
        column_left + square_right,
        row_top + square_bottom,
    )


def _get_grid_bounds(
    gray: np.ndarray,
) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """Return the three column and three row bounds on an appendix page."""
    height, width = gray.shape
    column_gaps = _detect_boundaries(gray, axis=0, minimum_gap=10)
    row_gaps = _detect_boundaries(gray, axis=1, minimum_gap=10)
    interior_columns = [gap for gap in column_gaps if gap[0] > 5 and gap[1] < width - 5]
    interior_rows = [gap for gap in row_gaps if gap[0] > 5 and gap[1] < height - 5]
    left = column_gaps[0][1] + 1 if column_gaps and column_gaps[0][0] <= 5 else 0
    right = (
        column_gaps[-1][0] - 1
        if column_gaps and column_gaps[-1][1] >= width - 5
        else width - 1
    )
    column_bounds = [left]
    for gap in interior_columns:
        column_bounds.extend(gap)
    column_bounds.append(right)
    columns = [
        (column_bounds[index], column_bounds[index + 1])
        for index in range(0, len(column_bounds), 2)
    ]

    bottom = row_gaps[-1][0] - 1 if row_gaps[-1][1] >= height - 5 else height - 1
    first_separator, second_separator = [
        gap for gap in interior_rows if gap[1] - gap[0] >= 15
    ][-2:]
    row_two_top = first_separator[1] + 1
    row_two_bottom = second_separator[0] - 1
    row_height = row_two_bottom - row_two_top
    rows = [
        (first_separator[0] - 1 - row_height, first_separator[0] - 1),
        (row_two_top, row_two_bottom),
        (second_separator[1] + 1, bottom),
    ]
    return columns, rows


def _line_mean(
    gray: np.ndarray,
    box: tuple[int, int, int, int],
    side: str,
    offset: int,
) -> float:
    """Return the mean of one line inside a rectangular box."""
    left, top, right, bottom = box
    if side == "left":
        return float(gray[top:bottom, left + offset : left + offset + 1].mean())
    if side == "right":
        return float(gray[top:bottom, right - 1 - offset : right - offset].mean())
    if side == "top":
        return float(gray[top + offset : top + offset + 1, left:right].mean())
    return float(gray[bottom - 1 - offset : bottom - offset, left:right].mean())


def _maximum_run(values: np.ndarray) -> int:
    """Return the longest consecutive true run."""
    best = current = 0
    for value in values:
        current = current + 1 if value else 0
        best = max(best, current)
    return best


def _trim_one_edge(
    gray: np.ndarray,
    box: tuple[int, int, int, int],
    side: str,
    maximum_trim: int = 8,
    recovery_threshold: float = 200,
    lookahead: int = 6,
) -> int:
    """Return the antialiased printed-border width on one edge."""
    trim = 0
    for _ in range(maximum_trim):
        if _line_mean(gray, box, side, trim) >= recovery_threshold:
            break
        future = [
            _line_mean(gray, box, side, trim + offset)
            for offset in range(1, lookahead + 1)
        ]
        if not any(mean >= recovery_threshold for mean in future):
            break
        trim += 1
    return trim


def _trim_to_content(
    gray: np.ndarray,
    box: tuple[int, int, int, int],
) -> tuple[int, int, int, int]:
    """Remove residual printed-border antialiasing independently per edge."""
    left, top, right, bottom = box
    left += _trim_one_edge(gray, (left, top, right, bottom), "left")
    right -= _trim_one_edge(gray, (left, top, right, bottom), "right")
    top += _trim_one_edge(gray, (left, top, right, bottom), "top")
    bottom -= _trim_one_edge(gray, (left, top, right, bottom), "bottom")
    return left, top, right, bottom


def _trimmed_board_image(image: Image.Image) -> Image.Image:
    """Remove a locally contrasting physical board edge from each side."""
    gray = np.asarray(image.convert("L"), dtype=float)
    left = _detect_board_edge_trim(gray, "left")
    right = _detect_board_edge_trim(gray, "right")
    top = _detect_board_edge_trim(gray, "top")
    bottom = _detect_board_edge_trim(gray, "bottom")
    width, height = image.size
    return image.crop((left, top, width - right, height - bottom))


def extract_images(
    pdf_path: Path,
    output_dir: Path,
    biomass_by_folder: dict[str, list[float]],
) -> None:
    """Extract all nine species series from the source PhotoLoad PDF."""
    if not pdf_path.is_file():
        raise FileNotFoundError(f"PhotoLoad PDF not found: {pdf_path}")
    output_dir.mkdir(parents=True, exist_ok=True)
    with fitz.open(pdf_path) as document:
        for page_index, folder in SPECIES_PAGES.items():
            page_images = document[page_index].get_images(full=True)
            source = document.extract_image(page_images[0][0])
            image = Image.open(BytesIO(source["image"]))
            gray = np.asarray(image.convert("L"))
            columns, rows = _get_grid_bounds(gray)
            if len(columns) != 3 or len(rows) != 3:
                raise ValueError(f"Expected a 3 x 3 image grid for {folder}")
            biomass_values = biomass_by_folder[folder]
            species_dir = output_dir / folder
            species_dir.mkdir(parents=True, exist_ok=True)
            for panel_index, ((row_top, row_bottom), (column_left, column_right)) in enumerate(
                (row, column) for row in rows for column in columns
            ):
                box = _find_square_box(
                    gray, row_top, row_bottom, column_left, column_right
                )
                panel = _trimmed_board_image(image.crop(_trim_to_content(gray, box)))
                filename = f"{biomass_values[panel_index]:.3f}_kgm2.jpg"
                panel.convert("RGB").save(species_dir / filename, quality=95)
            if folder == "SYAL_Symphoricarpos_albus":
                _apply_syal_reorder(species_dir)
