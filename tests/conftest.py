from pathlib import Path
import sys


_TESTS_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _TESTS_DIR.parent
_SRC_ROOT = _PROJECT_ROOT / 'src'

for _path in (_TESTS_DIR, _PROJECT_ROOT, _SRC_ROOT):
    if _path.is_dir():
        path_str = str(_path)
        if path_str not in sys.path:
            sys.path.insert(0, path_str)
