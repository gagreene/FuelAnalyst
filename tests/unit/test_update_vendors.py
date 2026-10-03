import os
import pathlib
import shutil
import subprocess

import pytest

import fuel_analyst

REPO_ROOT = pathlib.Path(fuel_analyst.__file__).parents[2]
SCRIPT = REPO_ROOT / 'scripts' / 'update_vendors.sh'
BASH = shutil.which('bash')

pytestmark = pytest.mark.skipif(BASH is None, reason='bash is not available')


def _git(cwd, *args):
    """
    Run a git command in a throwaway repository with a fixed identity.

    :param cwd: Directory to run git in.
    :param args: git arguments.
    :return: Stripped standard output.
    """
    return subprocess.run(
        ['git', '-c', 'user.name=t', '-c', 'user.email=t@example.invalid', *args],
        cwd=cwd, check=True, capture_output=True, text=True,
    ).stdout.strip()


def _make_conpyro_clone(path):
    """
    Create a minimal committed ConPyro-like repository.

    :param path: Directory for the fake upstream clone.
    :return: The clone's HEAD commit SHA.
    """
    (path / 'src' / 'conpyro' / 'tests').mkdir(parents=True)
    (path / 'src' / 'conpyro' / '__init__.py').write_text('', encoding='utf-8')
    (path / 'src' / 'conpyro' / 'tests' / 'test_x.py').write_text('', encoding='utf-8')
    _git(path, 'init', '-q')
    _git(path, 'add', '-A')
    _git(path, 'commit', '-q', '-m', 'fake upstream')
    return _git(path, 'rev-parse', 'HEAD')


def _make_bc_clone(path):
    """
    Create a minimal committed BC fuel-typing-like repository.

    :param path: Directory for the fake upstream clone.
    :return: The clone's short HEAD commit SHA.
    """
    (path / 'bcwft2018.py').write_text('X = 1\n', encoding='utf-8')
    _git(path, 'init', '-q')
    _git(path, 'add', '-A')
    _git(path, 'commit', '-q', '-m', 'fake upstream')
    return _git(path, 'rev-parse', '--short', 'HEAD')


def _make_workspace(tmp_path):
    """
    Create a repository layout holding a copy of the script under scripts/.

    :param tmp_path: pytest temporary directory.
    :return: Path of the fake repository root.
    """
    root = tmp_path / 'repo'
    (root / 'src' / 'fuel_analyst' / '_vendor').mkdir(parents=True)
    (root / 'scripts').mkdir()
    shutil.copy(SCRIPT, root / 'scripts' / 'update_vendors.sh')
    return root


def test_conpyro_local_clone_refresh_skips_bc(tmp_path):
    root = _make_workspace(tmp_path)
    clone = tmp_path / 'conpyro_clone'
    clone.mkdir()
    sha = _make_conpyro_clone(clone)
    elsewhere = tmp_path / 'elsewhere'
    elsewhere.mkdir()

    # Absolute script path, caller's working directory outside the repository: the script must
    # find the repository root from its own location, not from the caller's cwd.
    result = subprocess.run(
        [BASH, (root / 'scripts' / 'update_vendors.sh').as_posix(), '--only', 'conpyro'], cwd=elsewhere,
        capture_output=True, text=True,
        env={**os.environ, 'CONPYRO_SRC': clone.as_posix()},
    )

    vendored = root / 'src' / 'fuel_analyst' / '_vendor' / 'conpyro'
    assert result.returncode == 0, result.stderr
    assert (vendored / '__init__.py').exists()
    assert not (vendored / 'tests').exists()
    assert sha in (vendored / 'UPSTREAM.md').read_text(encoding='utf-8')
    assert not (root / 'src' / 'fuel_analyst' / '_vendor' / 'bcwft2018.py').exists()


def test_conpyro_refresh_rejects_a_dirty_clone(tmp_path):
    root = _make_workspace(tmp_path)
    clone = tmp_path / 'conpyro_clone'
    clone.mkdir()
    _make_conpyro_clone(clone)
    (clone / 'src' / 'conpyro' / 'dirty.py').write_text('x = 1\n', encoding='utf-8')

    result = subprocess.run(
        [BASH, 'scripts/update_vendors.sh', '--only', 'conpyro'], cwd=root, capture_output=True, text=True,
        env={**os.environ, 'CONPYRO_SRC': clone.as_posix()},
    )

    assert result.returncode != 0
    assert 'uncommitted changes' in result.stderr
    assert not (root / 'src' / 'fuel_analyst' / '_vendor' / 'conpyro').exists()


def test_bc_local_clone_refresh_skips_conpyro(tmp_path):
    root = _make_workspace(tmp_path)
    clone = tmp_path / 'bc_clone'
    clone.mkdir()
    sha = _make_bc_clone(clone)

    result = subprocess.run(
        [BASH, 'scripts/update_vendors.sh', '--only', 'bc'], cwd=root, capture_output=True, text=True,
        env={**os.environ, 'BC_SRC': clone.as_posix()},
    )

    vendored = root / 'src' / 'fuel_analyst' / '_vendor' / 'bcwft2018.py'
    assert result.returncode == 0, result.stderr
    text = vendored.read_text(encoding='utf-8')
    assert f'# Upstream commit: {sha}' in text
    assert text.endswith('X = 1\n')
    assert not (root / 'src' / 'fuel_analyst' / '_vendor' / 'conpyro').exists()


def test_bc_refresh_rejects_a_dirty_clone(tmp_path):
    root = _make_workspace(tmp_path)
    clone = tmp_path / 'bc_clone'
    clone.mkdir()
    _make_bc_clone(clone)
    (clone / 'dirty.py').write_text('x = 1\n', encoding='utf-8')

    result = subprocess.run(
        [BASH, 'scripts/update_vendors.sh', '--only', 'bc'], cwd=root, capture_output=True, text=True,
        env={**os.environ, 'BC_SRC': clone.as_posix()},
    )

    assert result.returncode != 0
    assert 'uncommitted changes' in result.stderr
    assert not (root / 'src' / 'fuel_analyst' / '_vendor' / 'bcwft2018.py').exists()


def test_default_run_clones_both_upstreams_and_cleans_up(tmp_path):
    root = _make_workspace(tmp_path)
    bc = tmp_path / 'bc_upstream'
    conpyro = tmp_path / 'conpyro_upstream'
    bc.mkdir()
    conpyro.mkdir()
    bc_sha = _make_bc_clone(bc)
    conpyro_sha = _make_conpyro_clone(conpyro)
    tmpdir = tmp_path / 'tmp'
    tmpdir.mkdir()

    result = subprocess.run(
        [BASH, 'scripts/update_vendors.sh'], cwd=root, capture_output=True, text=True,
        env={
            **os.environ, 'BC_URL': bc.as_uri(), 'CONPYRO_URL': conpyro.as_uri(),
            'TMPDIR': tmpdir.as_posix(),
        },
    )

    vendor = root / 'src' / 'fuel_analyst' / '_vendor'
    assert result.returncode == 0, result.stderr
    assert f'# Upstream commit: {bc_sha}' in (vendor / 'bcwft2018.py').read_text(encoding='utf-8')
    assert conpyro_sha in (vendor / 'conpyro' / 'UPSTREAM.md').read_text(encoding='utf-8')
    assert not (vendor / 'conpyro' / 'tests').exists()
    assert list(tmpdir.iterdir()) == []


def test_only_flag_limits_a_cloning_run_to_one_source(tmp_path):
    root = _make_workspace(tmp_path)
    conpyro = tmp_path / 'conpyro_upstream'
    conpyro.mkdir()
    _make_conpyro_clone(conpyro)

    result = subprocess.run(
        [BASH, 'scripts/update_vendors.sh', '--only', 'conpyro'], cwd=root, capture_output=True,
        text=True, env={**os.environ, 'CONPYRO_URL': conpyro.as_uri(), 'BC_URL': 'file:///missing'},
    )

    assert result.returncode == 0, result.stderr
    assert (root / 'src' / 'fuel_analyst' / '_vendor' / 'conpyro' / '__init__.py').exists()
    assert not (root / 'src' / 'fuel_analyst' / '_vendor' / 'bcwft2018.py').exists()


def test_unreachable_upstream_fails_without_touching_vendored_files(tmp_path):
    root = _make_workspace(tmp_path)

    result = subprocess.run(
        [BASH, 'scripts/update_vendors.sh', '--only', 'bc'], cwd=root, capture_output=True,
        text=True, env={**os.environ, 'BC_URL': (tmp_path / 'nowhere').as_uri()},
    )

    assert result.returncode != 0
    assert 'Could not clone' in result.stderr
    assert not (root / 'src' / 'fuel_analyst' / '_vendor' / 'bcwft2018.py').exists()


def test_unknown_arguments_are_rejected(tmp_path):
    root = _make_workspace(tmp_path)

    result = subprocess.run(
        [BASH, 'scripts/update_vendors.sh', '--only', 'flame'], cwd=root, capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "expects 'bc' or 'conpyro'" in result.stderr


def test_failed_refresh_keeps_the_existing_vendored_copy(tmp_path):
    root = _make_workspace(tmp_path)
    vendor = root / 'src' / 'fuel_analyst' / '_vendor'
    (vendor / 'conpyro').mkdir()
    (vendor / 'conpyro' / 'old.py').write_text('OLD = 1\n', encoding='utf-8')
    (vendor / 'bcwft2018.py').write_text('OLD = 1\n', encoding='utf-8')
    nowhere = (tmp_path / 'nowhere').as_uri()

    result = subprocess.run(
        [BASH, 'scripts/update_vendors.sh'], cwd=root, capture_output=True, text=True,
        env={**os.environ, 'BC_URL': nowhere, 'CONPYRO_URL': nowhere},
    )

    assert result.returncode == 1
    assert (vendor / 'conpyro' / 'old.py').read_text(encoding='utf-8') == 'OLD = 1\n'
    assert (vendor / 'bcwft2018.py').read_text(encoding='utf-8') == 'OLD = 1\n'
    assert 'existing vendored copies were left unchanged' in result.stderr


def test_one_failing_source_does_not_block_the_other(tmp_path):
    root = _make_workspace(tmp_path)
    vendor = root / 'src' / 'fuel_analyst' / '_vendor'
    (vendor / 'bcwft2018.py').write_text('OLD = 1\n', encoding='utf-8')
    conpyro = tmp_path / 'conpyro_upstream'
    conpyro.mkdir()
    sha = _make_conpyro_clone(conpyro)

    result = subprocess.run(
        [BASH, 'scripts/update_vendors.sh'], cwd=root, capture_output=True, text=True,
        env={
            **os.environ, 'BC_URL': (tmp_path / 'nowhere').as_uri(),
            'CONPYRO_URL': conpyro.as_uri(),
        },
    )

    assert result.returncode == 1
    assert (vendor / 'bcwft2018.py').read_text(encoding='utf-8') == 'OLD = 1\n'
    assert sha in (vendor / 'conpyro' / 'UPSTREAM.md').read_text(encoding='utf-8')
    assert 'Refresh failed for: bcwft2018' in result.stderr

