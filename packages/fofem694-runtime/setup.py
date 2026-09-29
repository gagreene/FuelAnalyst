"""Build the Windows runtime wheel from FuelAnalyst's tracked FOFEM bundle."""

import shutil
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py


_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_BUNDLE_DIR = _REPOSITORY_ROOT / 'src' / 'fuel_analyst' / 'supporting_data' / 'fofem_694'
_RUNTIME_PACKAGE = 'fuel_analyst_fofem694_runtime'
_RUNTIME_FILES = (
    'runfofem.exe',
    'Emission_Factors.csv',
    'fof_spp.csv',
    'README.txt',
    'PROVENANCE.md',
    'doc/LICENSE',
    'doc/Runfofem_User_Guide.pdf',
)


class BuildRuntimePackage(build_py):
    """Copy the selected runtime assets into the wheel build directory."""

    def run(self) -> None:
        """Build Python files and copy every asset from the tracked source bundle.

        :param self: Active setuptools build command.
        :return: None. Writes the selected FOFEM assets into the wheel build directory.
        """
        super().run()
        destination = Path(self.build_lib) / _RUNTIME_PACKAGE
        for relative_path in _RUNTIME_FILES:
            source = _BUNDLE_DIR / relative_path
            if not source.is_file():
                raise FileNotFoundError(
                    f'Cannot build the FOFEM runtime wheel: missing tracked bundle file '
                    f'{source}. Build from the FuelAnalyst repository checkout.'
                )
            target = destination / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)


setup(cmdclass={'build_py': BuildRuntimePackage})
