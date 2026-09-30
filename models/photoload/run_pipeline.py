"""Run the production PhotoLoad workflow used for the FuelAnalyst paper."""

from __future__ import annotations

import argparse
from pathlib import Path
from tempfile import TemporaryDirectory

from photoload import run_workflow
from photoload.source_pdf import download_source_pdf


MODEL_ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = MODEL_ROOT / ".work"


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
        help="Local PhotoLoad PDF (default: download from the US Forest Service)",
    )
    args = parser.parse_args()
    with TemporaryDirectory() as temporary_dir:
        pdf_path = args.pdf or download_source_pdf(
            Path(temporary_dir) / "rmrs_gtr190_Keane_and_Dickinson_2007.pdf"
        )
        run_workflow(pdf_path=pdf_path, output_dir=args.output_dir)


if __name__ == "__main__":
    main()
