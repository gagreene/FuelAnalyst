import fuel_analyst
from fuel_analyst import components


def test_package_lazy_api_exposes_documented_entry_points():
    # Call __getattr__ directly because importing the same-named submodule can
    # legitimately populate package.fuel_analyst with the module object.
    assert callable(fuel_analyst.__getattr__('fuel_analyst'))
    assert callable(fuel_analyst.__getattr__('process_fbp_fuel_type'))
    assert 'fuel_analyst' in dir(fuel_analyst)


def test_component_lazy_api_loads_fuelanalyst_modules():
    assert components.helper.__name__.endswith('.helper')
    assert components.woody_debris.__name__.endswith('.woody_debris')
    assert 'trees' in dir(components)
