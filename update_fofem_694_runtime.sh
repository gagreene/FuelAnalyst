#!/usr/bin/env bash
# Update the bundled official FOFEM 6.9.4 batch runtime
# (src/fuel_analyst/supporting_data/fofem_694) from its verified upstream ZIP, then mirror the
# same 7 files into packages/fofem694-runtime/src/fuel_analyst_fofem694_runtime/ so the two
# copies never drift apart.
#
# Downloads the exact pinned URL into a temporary location, verifies the ZIP's SHA-256 against
# the pin below before extracting anything, then selects only the runtime files and original
# documentation FuelAnalyst needs: runfofem.exe, README.txt, and doc/ (verbatim, at their
# original relative paths). Deliberately does NOT copy the ZIP's Emission_Factors.csv (see
# EMISSION_FACTORS_KNOWN_DIFF_NOTE below), samples, headers, .lib, SetENV.bat, or temp file,
# and does not copy any Microsoft Visual C++ runtime DLL (none are present upstream anyway;
# the VC++ runtime is a documented, separately-installed Windows prerequisite - see
# docs/CODEBASE.md).
#
# Fails loudly on any upstream ZIP change (a hash mismatch) rather than silently adopting a
# new upstream build. Updating the pin below is a deliberate, reviewed code change, not
# something this script does automatically.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
BUNDLE_DIR="$REPO_ROOT/src/fuel_analyst/supporting_data/fofem_694"
RUNTIME_PKG_DIR="$REPO_ROOT/packages/fofem694-runtime/src/fuel_analyst_fofem694_runtime"

UPSTREAM_URL="https://www.alturassolutions.com/SpatialFOFEM/runfofem.zip"
# Pinned 2026-09-29. Update only after deliberately reviewing the new ZIP's contents (see
# development/plans/2026-09-29-runfofem-wheel-integration.md's "Verified source" section for
# the review this pin's introduction was based on).
EXPECTED_ZIP_SHA256="2cdceb8967741a3a6276dcd0f4f6241d762cba38176aca43469ec5bac3818f92"
# The exact runfofem.exe this pin selects, recorded for the provenance record and for anyone
# diffing a future update against the currently bundled build.
EXPECTED_EXE_SHA256="e882761635c8efc9e29cbd0f776d489a3452218e9a37cd26aa29fa49608907c7"
# FuelAnalyst's own tested Emission_Factors.csv (upstream's copy differs by one deliberately
# removed trailing space at byte offset 3156 - see EMISSION_FACTORS_KNOWN_DIFF_NOTE - and is
# never overwritten by this script).
EXPECTED_EMISSION_FACTORS_SHA256="c3d55f741673c3de8e0bfb5b1d062a23a5cf7aa251962222baaeaa6ec230aecd"
EXPECTED_FOF_SPP_SHA256="238dbf71f3ef7b874be452221982113dbb8067ffcfd84e7d9773ab10f2ed7f67"

WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

echo "Downloading $UPSTREAM_URL ..."
curl -sL -o "$WORKDIR/runfofem.zip" "$UPSTREAM_URL"

actual_zip_sha256="$(sha256sum "$WORKDIR/runfofem.zip" | cut -d' ' -f1)"
if [ "$actual_zip_sha256" != "$EXPECTED_ZIP_SHA256" ]; then
    echo "FATAL: upstream ZIP SHA-256 mismatch." >&2
    echo "  expected: $EXPECTED_ZIP_SHA256" >&2
    echo "  actual:   $actual_zip_sha256" >&2
    echo "The upstream release changed. Review its contents deliberately before updating this" >&2
    echo "script's pin - do not adopt a changed upstream ZIP automatically." >&2
    exit 1
fi
echo "ZIP SHA-256 verified: $actual_zip_sha256"

mkdir -p "$WORKDIR/extracted"
unzip -q -o "$WORKDIR/runfofem.zip" -d "$WORKDIR/extracted"

actual_exe_sha256="$(sha256sum "$WORKDIR/extracted/bin/runfofem.exe" | cut -d' ' -f1)"
if [ "$actual_exe_sha256" != "$EXPECTED_EXE_SHA256" ]; then
    echo "FATAL: extracted runfofem.exe SHA-256 does not match the pin, despite the ZIP" >&2
    echo "itself matching. This should not happen for an identical ZIP; investigate before" >&2
    echo "proceeding." >&2
    exit 1
fi

echo "Selecting runtime files into $BUNDLE_DIR ..."
cp "$WORKDIR/extracted/bin/runfofem.exe" "$BUNDLE_DIR/runfofem.exe"
cp "$WORKDIR/extracted/README.txt" "$BUNDLE_DIR/README.txt"
mkdir -p "$BUNDLE_DIR/doc"
cp "$WORKDIR/extracted/doc/LICENSE" "$BUNDLE_DIR/doc/LICENSE"
cp "$WORKDIR/extracted/doc/Runfofem_User_Guide.pdf" "$BUNDLE_DIR/doc/Runfofem_User_Guide.pdf"

# EMISSION_FACTORS_KNOWN_DIFF_NOTE: FuelAnalyst keeps its own tested, warning-free
# Emission_Factors.csv (one trailing space removed at byte offset 3156 relative to upstream's
# share/fofem/Emission_Factors.csv) rather than overwriting it here. fof_spp.csv is verified
# byte-identical to the bundle's existing FOF_SPP.CSV and is likewise never overwritten by
# this script - both are validated below instead.
actual_emission_factors_sha256="$(sha256sum "$BUNDLE_DIR/Emission_Factors.csv" | cut -d' ' -f1)"
if [ "$actual_emission_factors_sha256" != "$EXPECTED_EMISSION_FACTORS_SHA256" ]; then
    echo "FATAL: bundled Emission_Factors.csv no longer matches its expected, tested hash." >&2
    exit 1
fi
actual_fof_spp_sha256="$(sha256sum "$BUNDLE_DIR/FOF_SPP.CSV" | cut -d' ' -f1)"
if [ "$actual_fof_spp_sha256" != "$EXPECTED_FOF_SPP_SHA256" ]; then
    echo "FATAL: bundled FOF_SPP.CSV no longer matches its expected hash." >&2
    exit 1
fi

cat > "$BUNDLE_DIR/PROVENANCE.md" <<EOF
# FOFEM 6.9.4 batch runtime provenance

- Upstream source: $UPSTREAM_URL
- Retrieved: $(date -u +%Y-%m-%d)
- Upstream ZIP SHA-256: $actual_zip_sha256
- Selected file SHA-256 (this bundle):
  - runfofem.exe: $actual_exe_sha256
  - README.txt: $(sha256sum "$BUNDLE_DIR/README.txt" | cut -d' ' -f1)
  - doc/LICENSE: $(sha256sum "$BUNDLE_DIR/doc/LICENSE" | cut -d' ' -f1)
  - doc/Runfofem_User_Guide.pdf: $(sha256sum "$BUNDLE_DIR/doc/Runfofem_User_Guide.pdf" | cut -d' ' -f1)
  - Emission_Factors.csv: $actual_emission_factors_sha256 (FuelAnalyst's own tested copy - one
    trailing space removed at byte offset 3156 relative to upstream's copy of this file, which
    otherwise causes a Python warning; not overwritten by this script)
  - FOF_SPP.CSV: $actual_fof_spp_sha256 (byte-identical to upstream's share/fofem/fof_spp.csv)

runfofem.exe, README.txt, and doc/ are copied byte-for-byte from the upstream ZIP by
update_fofem_694_runtime.sh. doc/LICENSE states the software was developed by federal
employees as part of official duties and is public domain; it is not the same license as
FuelAnalyst's own MIT-licensed code (see the repository root LICENSE file). The upstream
README.txt requests a citation for data derived from runfofem output.

The three Microsoft Visual C++ runtime DLLs previously bundled here (msvcp140.dll,
vcruntime140.dll, vcruntime140_1.dll) have been removed. The upstream ZIP contains no DLLs at
all. The Microsoft Visual C++ Redistributable is a documented, separately-installed Windows
prerequisite for running runfofem.exe - see docs/CODEBASE.md.

Regenerate this file by rerunning update_fofem_694_runtime.sh from the repository root.
EOF

echo "Mirroring the same 7 files into $RUNTIME_PKG_DIR ..."
mkdir -p "$RUNTIME_PKG_DIR/doc"
cp "$BUNDLE_DIR/runfofem.exe" "$RUNTIME_PKG_DIR/runfofem.exe"
cp "$BUNDLE_DIR/Emission_Factors.csv" "$RUNTIME_PKG_DIR/Emission_Factors.csv"
cp "$BUNDLE_DIR/FOF_SPP.CSV" "$RUNTIME_PKG_DIR/FOF_SPP.CSV"
cp "$BUNDLE_DIR/README.txt" "$RUNTIME_PKG_DIR/README.txt"
cp "$BUNDLE_DIR/PROVENANCE.md" "$RUNTIME_PKG_DIR/PROVENANCE.md"
cp "$BUNDLE_DIR/doc/LICENSE" "$RUNTIME_PKG_DIR/doc/LICENSE"
cp "$BUNDLE_DIR/doc/Runfofem_User_Guide.pdf" "$RUNTIME_PKG_DIR/doc/Runfofem_User_Guide.pdf"

echo
echo "Done. Updated files in $BUNDLE_DIR:"
echo "  runfofem.exe          $actual_exe_sha256"
echo "  README.txt            (verbatim from upstream)"
echo "  doc/LICENSE           (verbatim from upstream)"
echo "  doc/Runfofem_User_Guide.pdf (verbatim from upstream)"
echo "  PROVENANCE.md         (regenerated)"
echo "Unchanged (validated only): Emission_Factors.csv, FOF_SPP.CSV"
echo "Mirrored into $RUNTIME_PKG_DIR"
