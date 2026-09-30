"""Retrieve the published PhotoLoad report used by the model workflows."""

from __future__ import annotations

import shutil
from pathlib import Path
from urllib.request import urlopen

from .workflow import _validate_source_pdf


SOURCE_PDF_URL = "https://research.fs.usda.gov/download/treesearch/26755.pdf"


def download_source_pdf(destination: Path) -> Path:
    """Download and verify the published PhotoLoad report.

    :param destination: Local path for the downloaded PDF.
    :return: Path to the verified PDF written at destination.
    """
    try:
        with urlopen(SOURCE_PDF_URL, timeout=60) as response:
            with destination.open("wb") as output:
                shutil.copyfileobj(response, output)
        _validate_source_pdf(destination)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return destination
