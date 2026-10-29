"""The Survey123 forms and the species tables must offer and describe the same tree species."""
import os

import pandas as pd
import pytest

openpyxl = pytest.importorskip('openpyxl')

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_FORMS = os.path.join(_ROOT, 'docs', 'survey123', 'survey123_forms')
_TREE_PARAMS = os.path.join(_ROOT, 'src', 'fuel_analyst', 'supporting_data', 'tree_parameters.csv')
_LIST = 'list_tree_species'


def _form_path(folder):
    """Return the path of the XLSForm in a form folder."""
    return os.path.join(_FORMS, folder, f'{folder}.xlsx')


def _tree_species(folder):
    """Return the species codes of the list_tree_species choices of a form."""
    sheet = openpyxl.load_workbook(_form_path(folder), read_only=True)['choices']
    return [str(row[1]).strip() for row in sheet.values if row[0] == _LIST]


_TREES = 'CWC Fuels 3 - Trees'
_OTHERS = ['CWC Fuels 1 - Plot Attributes', 'CWC Fuels 2 - Plants and Regen', 'CWC Fuels 5 - Woody Debris']


def _shrubs():
    """Return the codes that tree_parameters.csv types as shrubs (JD and JH); a shrub is not a tree, so it needs no tree type.

    A shrub is offered on the Woody Debris form only, because its stems add small-diameter woody fuel.
    """
    params = pd.read_csv(_TREE_PARAMS).set_index('Species')['TreeType']
    return set(params[params == 'shrub'].index)


def _tree_types():
    """Return the Species and Type columns of the Trees form's Tree_Types.csv."""
    return pd.read_csv(os.path.join(_FORMS, _TREES, 'media', 'Tree_Types.csv')).set_index('Species')['Type']


def test_every_tree_species_choice_has_a_tree_type():
    missing = [code for code in _tree_species(_TREES) if code not in _tree_types().index]
    assert missing == []


def test_tree_types_agree_with_tree_parameters():
    params = pd.read_csv(_TREE_PARAMS).set_index('Species')['TreeType']
    types = _tree_types()
    wrong = {code: (kind, params[code]) for code, kind in types.items() if code in params.index and params[code] != kind}
    assert not set(types.index) & _shrubs(), 'a shrub must not have a tree type'
    assert wrong == {}


def test_every_form_species_choice_is_in_tree_parameters():
    params = set(pd.read_csv(_TREE_PARAMS)['Species'])
    for folder in [_TREES] + _OTHERS:
        assert [code for code in _tree_species(folder) if code not in params] == [], folder


@pytest.mark.parametrize('folder', _OTHERS)
def test_every_form_offers_all_the_trees_form_species(folder):
    # FD and PL stay out of every list on purpose: the forms offer the interior and coastal codes (FDC, FDI, PLC, PLI)
    assert sorted(set(_tree_species(_TREES)) - set(_tree_species(folder))) == []


def test_shrubs_are_offered_on_the_woody_debris_form_only():
    shrubs = _shrubs()
    assert shrubs == {'JD', 'JH'}
    for folder in (_TREES, 'CWC Fuels 1 - Plot Attributes', 'CWC Fuels 2 - Plants and Regen'):
        assert shrubs & set(_tree_species(folder)) == set(), folder
    assert shrubs <= set(_tree_species('CWC Fuels 5 - Woody Debris'))
