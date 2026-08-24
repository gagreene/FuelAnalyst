"""Run the production PhotoLoad workflow used for the FuelAnalyst paper."""

from __future__ import annotations

import argparse
from pathlib import Path

from photoload import run_workflow


MODEL_ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = MODEL_ROOT / ".work"
DEFAULT_PDF = (
    MODEL_ROOT.parents[1]
    / "docs"
    / "reference"
    / "rmrs_gtr190_Kean_and_Dickinson_2007.pdf"
)


def main() -> None:
    """
    Parse command-line arguments and run the production workflow.

    :return: None. Runs the production workflow with the parsed paths.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output root (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--pdf",
        type=Path,
        default=DEFAULT_PDF,
        help=f"Source PhotoLoad PDF (default: {DEFAULT_PDF})",
    )
    args = parser.parse_args()
    run_workflow(pdf_path=args.pdf, output_dir=args.output_dir)


if __name__ == "__main__":
    main()
