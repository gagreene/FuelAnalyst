import pytest

from fuel_analyst.fuel_analyst import fuel_analyst


def test_fuel_analyst_requires_all_forms_for_conpyro(tmp_path):
    (tmp_path / 'input').mkdir()
    with pytest.raises(FileNotFoundError, match='All Survey123 forms'):
        fuel_analyst(
            str(tmp_path / 'input'), str(tmp_path / 'output'), 'Byram', gen_conpyro_df=True
        )
