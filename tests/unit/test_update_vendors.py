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


def _make_workspace(tmp_path):
    """
    Create a repository layout holding a copy of the script under scripts/ and no BC submodule.

    :param tmp_path: pytest temporary directory.
    :return: Path of the fake repository root.
    """
    root = tmp_path / 'repo'
    (root / 'src' / 'fuel_analyst' / '_vendor').mkdir(parents=True)
    (root / 'scripts').mkdir()
    shutil.copy(SCRIPT, root / 'scripts' / 'update_vendors.sh')
    return root


def test_conpyro_refresh_runs_without_the_bc_submodule(tmp_path):
    root = _make_workspace(tmp_path)
    clone = tmp_path / 'conpyro_clone'
    clone.mkdir()
    sha = _make_conpyro_clone(clone)
    elsewhere = tmp_path / 'elsewhere'
    elsewhere.mkdir()

    # Absolute script path, caller's working directory outside the repository: the script must
    # find the repository root from its own location, not from the caller's cwd.
    result = subprocess.run(
        [BASH, (root / 'scripts' / 'update_vendors.sh').as_posix()], cwd=elsewhere,
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
        [BASH, 'scripts/update_vendors.sh'], cwd=root, capture_output=True, text=True,
        env={**os.environ, 'CONPYRO_SRC': clone.as_posix()},
    )

    assert result.returncode != 0
    assert 'uncommitted changes' in result.stderr
    assert not (root / 'src' / 'fuel_analyst' / '_vendor' / 'conpyro').exists()
