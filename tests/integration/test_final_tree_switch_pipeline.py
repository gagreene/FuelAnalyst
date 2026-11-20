"""Unchecked Trees is a surface-model workflow, even with no Trees directory."""
from pathlib import Path
import shutil

import pandas as pd
import pytest

from fuel_analyst.fuel_analyst import fuel_analyst


@pytest.mark.integration
def test_unchecked_trees_survives_missing_form_and_models_surface_inputs(tmp_path):
    example = Path(__file__).resolve().parents[2] / 'examples/data/Survey123_Data'
    source = tmp_path / 'in'
    source.mkdir()
    for folder in example.iterdir():
        if folder.is_dir() and folder.name != '3_Trees':
            shutil.copytree(folder, source / folder.name)
    path = source / '1_Plot_Attributes/survey_0.csv'
    parents = pd.read_csv(path)
    parents['form_select'] = parents['form_select'].str.replace(r'\btrees\b', '', regex=True).str.strip()
    parents.to_csv(path, index=False)
    out = tmp_path / 'out'
    fuel_analyst(str(source), str(out), 'Byram', gen_conpyro_df=True,
                 gen_fofem_consume_df=True, gen_fofem_gui_app_tree_df=True)
    conpyro = pd.read_csv(out / 'conpyro_df.csv')
    consume = pd.read_csv(out / 'fofem_consume_si_df.csv')
    assert len(conpyro) == len(parents) == len(consume)
    assert conpyro[['cfl_ovrstry', 'cbd_ovrstry', 'cfl_midstry', 'cbd_midstry', 'fsg']].eq(0).all(axis=None)
    assert consume[['CrownFoliage', 'CrownBranch']].eq(0).all(axis=None)
    assert (conpyro['sros_model'].notna() | conpyro['stand_type'].eq(0)).all()
    errors = pd.read_csv(out / 'fuelanalyst_errors.csv')
    assert not errors.get('Trees', pd.Series(dtype=str)).notna().any()
