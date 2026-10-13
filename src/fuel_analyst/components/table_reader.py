# -*- coding: utf-8 -*-
"""
Read the tables of an ArcGIS Survey123 form, whatever file format holds them.

A form's data is resolved once into a :class:`FormSource` (``resolve_form_source`` or
``ensure_form_source``), and every table is then read from that source by name (``read_table``). Only
the Survey123 form tables go through this module. Reference tables, weather files, and FOFEM outputs
keep using ``helper.get_df()``, which must not receive Survey123 normalization or schema checks.

The source kinds are registered in ``_READERS``, so supporting another file format means adding one
reader and one existence check. Currently supported: a folder of CSV files (``'csv_folder'``).
"""
__author__ = ['Gregory A. Greene']

import os
from dataclasses import dataclass
from typing import Optional, Union

import pandas as pd

from . import helper


@dataclass(frozen=True)
class FormSource:
    """
    Where one Survey123 form's tables live.

    :param kind: Source kind, such as 'csv_folder'.
    :param path: Path to the folder, workbook, or geodatabase that holds the tables.
    :param tables: Names of the tables found in the source when it was resolved.
    """
    kind: str
    path: str
    tables: tuple = ()


_CSV_EXTENSION = '.csv'
_CSV_FOLDER = 'csv_folder'


def _csv_stems(folder: str) -> tuple:
    """
    List the CSV table names (file names without extension) in a folder.

    :param folder: Path to the folder to inspect.
    :return: Sorted tuple of CSV table names, or an empty tuple if the folder cannot be listed.
    """
    try:
        names = os.listdir(folder)
    except OSError:
        return ()
    return tuple(sorted(
        os.path.splitext(name)[0] for name in names if name.lower().endswith(_CSV_EXTENSION)
    ))


def _csv_table_exists(source: FormSource, stem: str) -> bool:
    """
    Check whether a CSV table exists in a CSV-folder source.

    :param source: Resolved CSV-folder source.
    :param stem: Table name without extension.
    :return: True if '<stem>.csv' exists in the source folder.
    """
    return os.path.exists(os.path.join(source.path, f'{stem}{_CSV_EXTENSION}'))


def _read_csv_table(source: FormSource, stem: str) -> pd.DataFrame:
    """
    Read one CSV table from a CSV-folder source.

    :param source: Resolved CSV-folder source.
    :param stem: Table name without extension.
    :return: DataFrame read with the standard CSV reader (``helper.get_df``).
    """
    return helper.get_df(os.path.join(source.path, f'{stem}{_CSV_EXTENSION}'))


# Registry of source kinds: (table-exists check, table reader). Add a format by adding one entry.
_READERS = {
    _CSV_FOLDER: (_csv_table_exists, _read_csv_table),
}


def ensure_form_source(location: Union[str, FormSource]) -> FormSource:
    """
    Return a form source, converting a folder path if necessary.

    A path string is treated as a folder of CSV files and is not required to exist, so a missing
    table still fails later with the same error as before. An existing FormSource is returned as is.

    :param location: A FormSource, or the path to a form folder of CSV files.
    :return: The corresponding FormSource.
    """
    if isinstance(location, FormSource):
        return location
    path = os.fspath(location)
    return FormSource(kind=_CSV_FOLDER, path=path, tables=_csv_stems(path))


def form_exists(in_dir: str, form_dir_name: str) -> bool:
    """
    Check whether a Survey123 form is present in the input directory.

    :param in_dir: Path to the Survey123 data directory.
    :param form_dir_name: Name of the form folder (for example '3_Trees').
    :return: True if the form can be resolved to a source.
    """
    return resolve_form_source(in_dir, form_dir_name) is not None


def has_table(source: FormSource, stem: str) -> bool:
    """
    Check whether a form source provides a table.

    :param source: Resolved form source.
    :param stem: Table name without extension (for example 'survey_0').
    :return: True if the table exists in the source.
    """
    table_exists, _ = _READERS[source.kind]
    return table_exists(source, stem)


def read_table(source: Union[str, FormSource], stem: str, required: bool = True) -> Optional[pd.DataFrame]:
    """
    Read one table of a Survey123 form.

    :param source: A resolved FormSource, or the path to a form folder of CSV files.
    :param stem: Table name without extension (for example 'survey_0').
    :param required: If True, a missing table raises FileNotFoundError; if False, None is returned.
    :return: DataFrame with the table data, or None when the table is absent and not required.
    """
    source = ensure_form_source(source)
    if not required and not has_table(source, stem):
        return None
    _, reader = _READERS[source.kind]
    return reader(source, stem)


def resolve_form_source(in_dir: str, form_dir_name: str) -> Optional[FormSource]:
    """
    Resolve where a Survey123 form's tables live.

    :param in_dir: Path to the Survey123 data directory.
    :param form_dir_name: Name of the form folder (for example '3_Trees').
    :return: FormSource for the form, or None when the form is absent.
    """
    folder = os.path.join(in_dir, form_dir_name)
    if not os.path.isdir(folder):
        return None
    return FormSource(kind=_CSV_FOLDER, path=folder, tables=_csv_stems(folder))
