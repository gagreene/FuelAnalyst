"""FuelAnalyst component modules."""

from importlib import import_module

__all__ = [
	'canopy_cover',
	'conpyro_attributes',
	'fofem_attributes',
	'fofem_emissions',
	'fofem_gui_emissions',
	'fofem_mortality',
	'fwis_moisture_content',
	'helper',
	'plants_regen',
	'plot_attributes',
	'trees',
	'woody_debris',
]


def __getattr__(name: str):
	"""Load component modules on demand."""
	if name not in __all__:
		raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
	return import_module(f'.{name}', __name__)


def __dir__() -> list[str]:
	return sorted(__all__)

