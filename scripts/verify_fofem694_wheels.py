#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Build and verify the main fuel-analyst wheel and the optional
fuel-analyst-fofem694-runtime wheel from a clean checkout, without downloading FOFEM assets.

Confirms: the main wheel is platform-independent (py3-none-any) and contains no Windows
binary; the runtime wheel is tagged py3-none-win_amd64 specifically (fails loudly on an
accidental py3-none-any build); the runtime wheel's runfofem.exe/README.txt/doc/ files match
the pinned upstream hashes recorded in PROVENANCE.md; the deliberate one-byte
Emission_Factors.csv exception is present and nothing else differs; no NOTICE file and no
Microsoft Visual C++ runtime DLL exist in either wheel.

Run from the repository root:
    python scripts/verify_fofem694_wheels.py
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_PKG_DIR = REPO_ROOT / 'packages' / 'fofem694-runtime'
SOURCE_BUNDLE_DIR = REPO_ROOT / 'src' / 'fuel_analyst' / 'supporting_data' / 'fofem_694'
RUNTIME_SOURCE_DIR = RUNTIME_PKG_DIR / 'src' / 'fuel_analyst_fofem694_runtime'
RUNTIME_ASSETS = (
    'runfofem.exe', 'Emission_Factors.csv', 'fof_spp.csv', 'README.txt',
    'PROVENANCE.md', 'doc/LICENSE', 'doc/Runfofem_User_Guide.pdf',
)

_FORBIDDEN_DLLS = {'msvcp140.dll', 'vcruntime140.dll', 'vcruntime140_1.dll'}

# Pinned upstream hashes - see scripts/update_fofem_694_runtime.sh and PROVENANCE.md.
EXPECTED_HASHES = {
    'runfofem.exe': 'e882761635c8efc9e29cbd0f776d489a3452218e9a37cd26aa29fa49608907c7',
    'README.txt': '7f19a54cbe2ba6b5f374116944ef54bfc545f8c0a66c608324c4929035e687be',
    'doc/LICENSE': 'fd61f309ce986b2cce266588dfbed12c3f9e584f3fd4081b9393b7f516d4c379',
    'doc/Runfofem_User_Guide.pdf': '8f6e646436d6c1a704de512b939573c43d490d3fe4a1004d81bd2cded8d1e8b7',
}
EXPECTED_EMISSION_FACTORS_SHA256 = 'c3d55f741673c3de8e0bfb5b1d062a23a5cf7aa251962222baaeaa6ec230aecd'
EXPECTED_FOF_SPP_SHA256 = '238dbf71f3ef7b874be452221982113dbb8067ffcfd84e7d9773ab10f2ed7f67'

_FAILURES: list[str] = []


def _build_wheel(project_dir: Path, out_dir: Path) -> Path:
    """
    Build one wheel with `python -m build --wheel`.

    Neither project's pyproject.toml or setup.cfg fetches anything from the network as part
    of building the wheel itself - both are pure local source trees with no runtime download
    step. `build`'s own default isolated build environment may use pip's local wheel cache
    (or the network, if that cache is cold) purely to obtain its own build-time tooling
    (setuptools/wheel); that is a property of the `build` tool's own bootstrapping, not of
    either FuelAnalyst project being built, and is unrelated to the "do not download FOFEM
    assets at install/build/run time" requirement this script otherwise verifies.

    :param project_dir: Directory containing the project's pyproject.toml.
    :param out_dir: Directory to write the built wheel into.
    :return: Path to the built .whl file.
    """
    subprocess.run(
        [sys.executable, '-m', 'build', '--wheel', '--outdir', str(out_dir)],
        cwd=project_dir, check=True,
    )
    wheels = sorted(out_dir.glob('*.whl'))
    if not wheels:
        raise RuntimeError(f'No wheel produced in {out_dir}')
    return wheels[-1]


def _fail(message: str) -> None:
    """
    Record one verification failure and print it immediately.

    :param message: Description of the failed check.
    :return: None.
    """
    print(f'FAIL: {message}')
    _FAILURES.append(message)


def _ok(message: str) -> None:
    """
    Print one passed check.

    :param message: Description of the passed check.
    :return: None.
    """
    print(f'  ok: {message}')


def _sha256(data: bytes) -> str:
    """
    Compute the SHA-256 hex digest of a byte string.

    :param data: Raw bytes.
    :return: Lowercase hex digest.
    """
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    """
    Run both wheel builds and all verification checks, printing a final pass/fail summary.

    :return: Process exit code (0 if every check passed, 1 otherwise).
    """
    verify_source_bundle()
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp)
        verify_main_wheel(out_dir)
        verify_runtime_wheel(out_dir)

    print()
    if _FAILURES:
        print(f'{len(_FAILURES)} check(s) FAILED:')
        for failure in _FAILURES:
            print(f'  - {failure}')
        return 1
    print('All checks passed.')
    return 0


def verify_main_wheel(out_dir: Path) -> None:
    """
    Build the main fuel-analyst wheel and verify it is platform-independent with no Windows
    binary and no runfofem.exe.

    :param out_dir: Directory to build into.
    :return: None.
    """
    print('\n=== Main fuel-analyst wheel ===')
    whl_path = _build_wheel(REPO_ROOT, out_dir)
    print(f'Built: {whl_path.name}')
    if '-py3-none-any' not in whl_path.name:
        _fail(f'main wheel is not tagged py3-none-any: {whl_path.name}')
    else:
        _ok('tagged py3-none-any (platform independent)')

    with zipfile.ZipFile(whl_path) as z:
        names = z.namelist()
    exes = [n for n in names if n.lower().endswith('.exe')]
    dlls = [n for n in names if n.lower().endswith('.dll')]
    if exes:
        _fail(f'main wheel contains Windows executable(s): {exes}')
    else:
        _ok('no .exe files in main wheel')
    if dlls:
        _fail(f'main wheel contains DLL(s): {dlls}')
    else:
        _ok('no .dll files in main wheel')


def verify_runtime_wheel(out_dir: Path) -> None:
    """
    Build the fuel-analyst-fofem694-runtime wheel and verify its tag, contents, and hashes.

    :param out_dir: Directory to build into.
    :return: None.
    """
    print('\n=== fuel-analyst-fofem694-runtime wheel ===')
    whl_path = _build_wheel(RUNTIME_PKG_DIR, out_dir)
    print(f'Built: {whl_path.name}')
    if '-py3-none-win_amd64' not in whl_path.name:
        _fail(f'runtime wheel is NOT tagged py3-none-win_amd64 (got {whl_path.name}) - '
              f'refusing an accidental py3-none-any runtime wheel')
    else:
        _ok('tagged py3-none-win_amd64')

    with zipfile.ZipFile(whl_path) as z:
        names = z.namelist()
        contents = {n: z.read(n) for n in names if not n.endswith('/')}

    def _pkg_path(rel: str) -> str:
        return f'fuel_analyst_fofem694_runtime/{rel}'

    dlls = [n for n in names if Path(n).name.lower() in _FORBIDDEN_DLLS]
    if dlls:
        _fail(f'runtime wheel contains a Microsoft VC++ DLL: {dlls}')
    else:
        _ok('no Microsoft VC++ runtime DLLs present')

    notices = [n for n in names if Path(n).name == 'NOTICE']
    if notices:
        _fail(f'runtime wheel contains a NOTICE file (should be removed): {notices}')
    else:
        _ok('no NOTICE file present')

    for rel, expected_hash in EXPECTED_HASHES.items():
        key = _pkg_path(rel)
        if key not in contents:
            _fail(f'runtime wheel is missing expected file: {key}')
            continue
        actual_hash = _sha256(contents[key])
        if actual_hash != expected_hash:
            _fail(f'{rel} hash mismatch: expected {expected_hash}, got {actual_hash}')
        else:
            _ok(f'{rel} matches pinned upstream hash byte-for-byte')

    ef_key = _pkg_path('Emission_Factors.csv')
    if ef_key not in contents:
        _fail(f'runtime wheel is missing {ef_key}')
    else:
        actual = _sha256(contents[ef_key])
        if actual != EXPECTED_EMISSION_FACTORS_SHA256:
            _fail(f'Emission_Factors.csv does not match the tested, space-removed hash: {actual}')
        else:
            _ok('Emission_Factors.csv matches FuelAnalyst\'s tested (space-removed) hash')

    spp_key = _pkg_path('fof_spp.csv')
    if spp_key not in contents:
        _fail(f'runtime wheel is missing {spp_key}')
    else:
        actual = _sha256(contents[spp_key])
        if actual != EXPECTED_FOF_SPP_SHA256:
            _fail(f'fof_spp.csv hash mismatch: {actual}')
        else:
            _ok('fof_spp.csv matches expected hash (byte-identical to upstream fof_spp.csv)')

    provenance_key = _pkg_path('PROVENANCE.md')
    if provenance_key not in contents:
        _fail(f'runtime wheel is missing {provenance_key}')
    else:
        _ok('PROVENANCE.md present')


def verify_source_bundle() -> None:
    """Verify that every runtime asset is tracked once, in the source bundle.

    :return: None. Records failures if a clean Git checkout would lack an asset or if the
        wheel project holds a duplicate source copy.
    """
    print('\n=== Tracked source bundle ===')
    for relative_path in RUNTIME_ASSETS:
        source = SOURCE_BUNDLE_DIR / relative_path
        if not source.is_file():
            _fail(f'source bundle is missing {source}')
            continue
        tracked = subprocess.run(
            ['git', 'ls-files', '--error-unmatch', '--', str(source.relative_to(REPO_ROOT))],
            cwd=REPO_ROOT, capture_output=True, text=True,
        )
        if tracked.returncode != 0:
            _fail(f'source bundle asset is not tracked by Git: {source}')
        else:
            _ok(f'tracked: {relative_path}')
        duplicate = RUNTIME_SOURCE_DIR / relative_path
        if duplicate.exists():
            _fail(f'runtime project contains a duplicate source asset: {duplicate}')


if __name__ == '__main__':
    sys.exit(main())
