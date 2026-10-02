import importlib
import pathlib
import re

import fuel_analyst

VENDOR_DIR = pathlib.Path(fuel_analyst.__file__).parent / '_vendor' / 'conpyro'


def test_every_vendored_directory_is_a_package():
    directories = [VENDOR_DIR, *[p for p in VENDOR_DIR.rglob('*') if p.is_dir() and p.name != '__pycache__']]
    assert VENDOR_DIR.exists()
    for directory in directories:
        assert (directory / '__init__.py').exists(), directory


def test_no_absolute_src_conpyro_imports():
    offenders = [str(p) for p in VENDOR_DIR.rglob('*.py') if 'from src.conpyro' in p.read_text(encoding='utf-8')]
    assert VENDOR_DIR.exists()
    assert offenders == []


def test_tests_and_build_artifacts_are_not_vendored():
    assert VENDOR_DIR.exists()
    assert not (VENDOR_DIR / 'tests').exists()
    assert not list(VENDOR_DIR.rglob('*.csv'))


def test_upstream_provenance_file_records_commit():
    text = (VENDOR_DIR / 'UPSTREAM.md').read_text(encoding='utf-8')
    assert 'https://github.com/gagreene/conpyro' in text
    assert re.search(r'Upstream commit: [0-9a-f]{40}', text)
    assert 'MIT' in text


def test_vendored_conpyro_imports_from_package_path():
    module = importlib.import_module('fuel_analyst._vendor.conpyro')
    assert module.ConPyro is not None
    assert pathlib.Path(module.__file__).is_relative_to(pathlib.Path(fuel_analyst.__file__).parent / '_vendor')
