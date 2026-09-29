# fuel-analyst-fofem694-runtime

The official USDA Forest Service FOFEM 6.9.4 batch runtime (`runfofem.exe`), packaged so
[FuelAnalyst](https://github.com/gagreene/FuelAnalyst)'s `model_select='fof_gui'` emissions
backend can use it from a normal `pip install`, without a separate FOFEM installation.

**Windows x64 only.** This distribution's wheel is tagged `py3-none-win_amd64` deliberately -
installing it anywhere else will fail. On Linux and macOS, use FuelAnalyst's other emissions
backend (`model_select='pyfofem'`, the `fuel-analyst[fofem]` extra), which works cross-platform.

## Prerequisite: Microsoft Visual C++ Redistributable

`runfofem.exe` requires the Microsoft Visual C++ Redistributable (x64) to be installed
separately on the host machine. This package does not bundle it and cannot install it for
you. If it is missing, `runfofem.exe` will fail to start; see FuelAnalyst's `docs/CODEBASE.md`
for the exact failure mode and where to obtain the redistributable.

## What is bundled

- `runfofem.exe` - the official batch executable, copied byte-for-byte from the upstream ZIP.
- `Emission_Factors.csv` - FuelAnalyst's own tested copy (one trailing space removed relative
  to upstream's copy of this file, which otherwise causes a Python warning; see
  `PROVENANCE.md`).
- `fof_spp.csv` - byte-identical to upstream's `share/fofem/fof_spp.csv`.
- `README.txt` and `doc/` (`LICENSE`, `Runfofem_User_Guide.pdf`) - preserved byte-for-byte at
  their original relative paths, per the upstream README's own request. `doc/LICENSE` states
  the software was developed by federal employees as part of official duties and is public
  domain - a different license than FuelAnalyst's own MIT-licensed code (see the root
  `fuel-analyst` package's `LICENSE` file).
- `PROVENANCE.md` - source URL, retrieval date, and file hashes for this bundle.

No Microsoft Visual C++ runtime DLLs are bundled; see the prerequisite note above.

## Provenance and updates

FuelAnalyst's `update_fofem_694_runtime.sh` maintains the tracked source bundle from the
exact pinned upstream ZIP. This wheel's build copies its seven runtime assets from that
bundle, so it must be built from a FuelAnalyst repository checkout. Neither the wheel build
nor installation downloads FOFEM files. The runtime project's source distribution is not a
standalone release artifact. See `PROVENANCE.md` for the exact hashes of the bundled files.
