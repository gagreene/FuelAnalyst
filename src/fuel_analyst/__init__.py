"""FuelAnalyst public API."""

from importlib import import_module
from typing import TYPE_CHECKING

__all__ = [
	'fuel_analyst',
	'extract_weather_data',
	'process_fbp_fuel_type',
	'merge_weather_data',
	'run_conpyro',
]

_API_MAP = {
	'fuel_analyst': ('fuel_analyst', 'fuel_analyst'),
	'extract_weather_data': ('extract_nrcan_wx', 'extract_weather_data'),
	'process_fbp_fuel_type': ('fbp_fuel_type', 'process_fbp_fuel_type'),
	'merge_weather_data': ('merge_wx_data', 'merge_weather_data'),
	'run_conpyro': ('run_conpyro', 'run_conpyro'),
}

if TYPE_CHECKING:
	from .fuel_analyst import fuel_analyst
	from .extract_nrcan_wx import extract_weather_data
	from .fbp_fuel_type import process_fbp_fuel_type
	from .merge_wx_data import merge_weather_data
	from .run_conpyro import run_conpyro


def __getattr__(name: str):
    """
    Lazily load public API callables on first access.

    :param name: Public attribute name to load.
    :return: Requested public API callable.
    """
    if name not in _API_MAP:
        raise AttributeError(f'module {__name__!r} has no attribute {name!r}')

    module_name, attr_name = _API_MAP[name]
    module = import_module(f'.{module_name}', __name__)
    return getattr(module, attr_name)


def __dir__() -> list[str]:
    """
    Return the sorted public API names exposed by this package.

    :return: Sorted list of public API names.
    """
    return sorted(__all__)



