"""Regression coverage for Survey123 exports without manual species records."""

from fuel_analyst.components.woody_debris import (
    _add_spp_comp_type,
    _load_manual_spp_comp,
)


def test_missing_manual_species_repeat_keeps_composition_schema(tmp_path):
    composition = _add_spp_comp_type(_load_manual_spp_comp(str(tmp_path)))

    assert composition.empty
    assert list(composition.columns) == [
        'ParentGlobalID',
        'spp_comp_code',
        'spp_comp_percent',
        'spp_comp_type',
    ]
