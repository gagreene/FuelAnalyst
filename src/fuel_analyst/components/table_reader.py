# -*- coding: utf-8 -*-
"""
Read the tables of an ArcGIS Survey123 form, whatever file format holds them.

A form's data is resolved once into a :class:`FormSource` (``resolve_form_source`` or
``ensure_form_source``), and every table is then read from that source by name (``read_table``). Only
the Survey123 form tables go through this module. Reference tables, weather files, and FOFEM outputs
keep using ``helper.get_df()``, which must not receive Survey123 normalization or schema checks.

The source kinds are registered in ``_READERS``, so supporting another file format means adding one
reader and one existence check. Currently supported:

* ``'csv_folder'``: a folder of CSV files, one per table (``survey_0.csv``).
* ``'workbook'``: one or more Excel workbooks (``.xlsx``, ``.xlsm``) in the form folder, with one
  sheet per table, named like the CSV file (``survey_0``). This is the layout of an ArcGIS Survey123
  Excel download.

When a form folder holds several formats, CSV is used first, then Excel.
"""
__author__ = ['Gregory A. Greene']

import contextlib
import io
import os
import warnings
from dataclasses import dataclass
from typing import Optional, Union

import pandas as pd

from . import helper


@dataclass(frozen=True)
class FormSource:
    """
    Where one Survey123 form's tables live.

    :param kind: Source kind, such as 'csv_folder' or 'workbook'.
    :param path: Path to the form folder.
    :param tables: Names of the tables found in the source when it was resolved.
    :param files: Paths of the workbook files that hold the tables (empty for a CSV folder).
    """
    kind: str
    path: str
    tables: tuple = ()
    files: tuple = ()


_CSV_EXTENSION = '.csv'
_CSV_FOLDER = 'csv_folder'
_WORKBOOK = 'workbook'
_WORKBOOK_EXTENSIONS = ('.xlsx', '.xlsm')


def _as_csv_would(frame: pd.DataFrame) -> pd.DataFrame:
    """
    Give non-date columns the dtypes and missing-value handling that ``pd.read_csv`` would.

    The non-date columns are written to text and read back with the CSV reader, so the result is the same
    as reading the equivalent CSV file (for example text cells that hold only numbers become numbers).
    Datetime columns are kept as datetimes.

    :param frame: DataFrame read from a spreadsheet.
    :return: DataFrame with the same columns and column order.
    """
    date_columns = [c for c in frame.columns if pd.api.types.is_datetime64_any_dtype(frame[c])]
    buffer = io.StringIO()
    frame.drop(columns=date_columns).to_csv(buffer, index=False)
    buffer.seek(0)
    result = pd.read_csv(buffer, header=0, index_col=False, low_memory=False)
    for column in date_columns:
        result[column] = frame[column].to_numpy()
    return result[list(frame.columns)]


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


def _detect_source(folder: str) -> FormSource:
    """
    Work out which format a form folder holds: CSV files first, then Excel workbooks.

    A folder with neither is treated as an empty CSV folder, so a missing table fails later with the
    usual FileNotFoundError.

    :param folder: Path to the form folder.
    :return: FormSource for the folder.
    """
    csv_tables = _csv_stems(folder)
    workbooks = _workbook_files(folder)
    if csv_tables:
        if workbooks:
            print(f'\tForm folder {folder} holds CSV and Excel files; using the CSV tables')
        return FormSource(kind=_CSV_FOLDER, path=folder, tables=csv_tables)
    if workbooks:
        tables = []
        for workbook in workbooks:
            tables.extend(name for name in _sheet_names(workbook) if name not in tables)
        return FormSource(kind=_WORKBOOK, path=folder, tables=tuple(tables), files=workbooks)
    return FormSource(kind=_CSV_FOLDER, path=folder, tables=())


@contextlib.contextmanager
def _quiet_openpyxl():
    """
    Silence openpyxl's "Workbook contains no default style" warning.

    ArcGIS writes workbooks without a default style, which is harmless but would print a warning for every read.

    :return: Context manager that ignores that one warning.
    """
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore', message='Workbook contains no default style', category=UserWarning)
        yield


def _read_csv_table(source: FormSource, stem: str) -> pd.DataFrame:
    """
    Read one CSV table from a CSV-folder source.

    :param source: Resolved CSV-folder source.
    :param stem: Table name without extension.
    :return: DataFrame read with the standard CSV reader (``helper.get_df``).
    """
    return helper.get_df(os.path.join(source.path, f'{stem}{_CSV_EXTENSION}'))


def _read_workbook_table(source: FormSource, stem: str) -> pd.DataFrame:
    """
    Read one table (sheet) from a workbook source.

    The result matches what the CSV reader would give for the same data: columns that hold numbers or
    numbers stored as text get the same dtypes ``pd.read_csv`` infers, and ``'NA'`` text is missing.
    Date columns stay datetimes, which ``helper.get_unique_id`` accepts.

    :param source: Resolved workbook source.
    :param stem: Sheet name (the table name without extension).
    :return: DataFrame with the sheet data.
    """
    holders = [path for path in source.files if stem in _sheet_names(path)]
    if not holders:
        raise FileNotFoundError(f"No sheet named '{stem}' in the Excel workbooks of {source.path}")
    if len(holders) > 1:
        raise ValueError(
            f"Sheet '{stem}' is in more than one workbook in {source.path}: "
            f"{', '.join(os.path.basename(path) for path in holders)}. Keep one workbook per form."
        )
    print(f"\tGetting DataFrame from Excel sheet '{stem}' at: {holders[0]}")
    try:
        with _quiet_openpyxl():
            frame = pd.read_excel(holders[0], sheet_name=stem, header=0, engine='openpyxl')
    except Exception as exc:
        raise ValueError(f"Cannot read sheet '{stem}' from {holders[0]}: {exc}") from exc
    return _as_csv_would(frame)


def _sheet_names(workbook: str) -> tuple:
    """
    List the sheet names of an Excel workbook without loading its data.

    :param workbook: Path to the workbook.
    :return: Tuple of sheet names, in workbook order.
    """
    from openpyxl import load_workbook
    try:
        with _quiet_openpyxl():
            book = load_workbook(workbook, read_only=True)
    except Exception as exc:
        raise ValueError(f'Cannot open Excel workbook {workbook}: {exc}') from exc
    try:
        return tuple(book.sheetnames)
    finally:
        book.close()


def _workbook_files(folder: str) -> tuple:
    """
    List the Excel workbooks in a folder, skipping Excel's temporary lock files ('~$name.xlsx').

    :param folder: Path to the folder to inspect.
    :return: Sorted tuple of workbook paths, or an empty tuple if the folder cannot be listed.
    """
    try:
        names = os.listdir(folder)
    except OSError:
        return ()
    return tuple(sorted(
        os.path.join(folder, name) for name in names
        if name.lower().endswith(_WORKBOOK_EXTENSIONS) and not name.startswith('~$')
    ))


def _workbook_table_exists(source: FormSource, stem: str) -> bool:
    """
    Check whether a workbook source has a sheet for a table.

    :param source: Resolved workbook source.
    :param stem: Sheet name (the table name without extension).
    :return: True if any workbook of the source has a sheet with that name.
    """
    return stem in source.tables


# Registry of source kinds: (table-exists check, table reader). Add a format by adding one entry.
_READERS = {
    _CSV_FOLDER: (_csv_table_exists, _read_csv_table),
    _WORKBOOK: (_workbook_table_exists, _read_workbook_table),
}


def ensure_form_source(location: Union[str, FormSource]) -> FormSource:
    """
    Return a form source, resolving a folder path if necessary.

    A path string is resolved from the files in that folder (CSV tables first, then Excel workbooks). A
    folder that does not exist, or holds neither, is treated as an empty CSV folder, so a missing table still
    fails later with the same error as before. An existing FormSource is returned as is.

    :param location: A FormSource, or the path to a form folder.
    :return: The corresponding FormSource.
    """
    if isinstance(location, FormSource):
        return location
    path = os.fspath(location)
    if os.path.isdir(path):
        return _detect_source(path)
    return FormSource(kind=_CSV_FOLDER, path=path, tables=())


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

    :param source: A resolved FormSource, or the path to a form folder.
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
    return _detect_source(folder)
