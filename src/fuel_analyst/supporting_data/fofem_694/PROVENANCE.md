# FOFEM 6.9.4 batch runtime provenance

- Upstream source: https://www.alturassolutions.com/SpatialFOFEM/runfofem.zip
- Retrieved: 2026-09-29
- Upstream ZIP SHA-256: 2cdceb8967741a3a6276dcd0f4f6241d762cba38176aca43469ec5bac3818f92
- Selected file SHA-256 (this bundle):
  - runfofem.exe: e882761635c8efc9e29cbd0f776d489a3452218e9a37cd26aa29fa49608907c7
  - README.txt: 7f19a54cbe2ba6b5f374116944ef54bfc545f8c0a66c608324c4929035e687be
  - doc/LICENSE: fd61f309ce986b2cce266588dfbed12c3f9e584f3fd4081b9393b7f516d4c379
  - doc/Runfofem_User_Guide.pdf: 8f6e646436d6c1a704de512b939573c43d490d3fe4a1004d81bd2cded8d1e8b7
  - Emission_Factors.csv: c3d55f741673c3de8e0bfb5b1d062a23a5cf7aa251962222baaeaa6ec230aecd (FuelAnalyst's own tested copy - one
    trailing space removed at byte offset 3156 relative to upstream's copy of this file, which
    otherwise causes a Python warning; not overwritten by this script)
  - fof_spp.csv: 238dbf71f3ef7b874be452221982113dbb8067ffcfd84e7d9773ab10f2ed7f67 (byte-identical to upstream's share/fofem/fof_spp.csv)

runfofem.exe, fof_spp.csv, README.txt, and doc/ are copied byte-for-byte from the upstream ZIP by
scripts/update_fofem_694_runtime.sh. doc/LICENSE states the software was developed by federal
employees as part of official duties and is public domain; it is not the same license as
FuelAnalyst's own MIT-licensed code (see the repository root LICENSE file). The upstream
README.txt requests a citation for data derived from runfofem output.

The three Microsoft Visual C++ runtime DLLs previously bundled here (msvcp140.dll,
vcruntime140.dll, vcruntime140_1.dll) have been removed. The upstream ZIP contains no DLLs at
all. The Microsoft Visual C++ Redistributable is a documented, separately-installed Windows
prerequisite for running runfofem.exe - see docs/CODEBASE.md.

Regenerate this file by rerunning `scripts/update_fofem_694_runtime.sh` from the repository root. The
runtime wheel copies these selected files from this bundle during its build.
