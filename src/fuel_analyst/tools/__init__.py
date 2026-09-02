"""FuelAnalyst tool modules."""

from importlib import import_module

__all__ = ['extract_nrcan_wx', 'fbp_fuel_type', 'merge_wx_data']


def __getattr__(name: str):
    """
    Load tool modules on demand.

    :param name: Tool-module name to load.
    :return: Imported tool module.
    """
    if name not in __all__:
        raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
    return import_module(f'.{name}', __name__)


def __dir__() -> list[str]:
    """
    Return the sorted tool-module names exposed by this package.

    :return: Sorted list of tool-module names.
    """
    return sorted(__all__)
