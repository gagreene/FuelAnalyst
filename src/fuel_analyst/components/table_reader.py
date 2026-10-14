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
* ``'gdb'``: one or more file geodatabases (``<name>.gdb`` folders, in the form folder or one folder
  below it, for example after unzipping an ArcGIS download). Layers are named like the CSV tables
  without the table index (``survey``, ``tree_plot``, ``t1_woody``). Zipped downloads must be unzipped.

When a form folder holds several formats, CSV is used first, then Excel, then geodatabase.
"""
__author__ = ['Gregory A. Greene']

import contextlib
import io
import os
import re
import warnings
from dataclasses import dataclass
from typing import Optional, Union

import numpy as np
import pandas as pd

from . import helper


@dataclass(frozen=True)
class FormSource:
    """
    Where one Survey123 form's tables live.

    :param kind: Source kind: 'csv_folder', 'workbook', or 'gdb'.
    :param path: Path to the form folder.
    :param tables: Names of the tables found in the source when it was resolved (CSV names, sheet names, or
        geodatabase layer names).
    :param files: Paths of the workbooks or geodatabases that hold the tables (empty for a CSV folder).
    """
    kind: str
    path: str
    tables: tuple = ()
    files: tuple = ()


_CSV_EXTENSION = '.csv'
_CSV_FOLDER = 'csv_folder'
_GDB = 'gdb'
_GDB_EXTENSION = '.gdb'
_GUID_COLUMNS = {'globalid': 'GlobalID', 'parentglobalid': 'ParentGlobalID'}
_WORKBOOK = 'workbook'
_WORKBOOK_EXTENSIONS = ('.xlsx', '.xlsm')
# Coordinates this close to zero are floating-point noise from the geodatabase (a record without a location
# is stored at 0, 0 and reads back as about 5.7e-14), so they are snapped to exactly zero.
_COORDINATE_NOISE = 1e-9


def _as_csv_would(frame: pd.DataFrame) -> pd.DataFrame:
    """
    Give non-date columns the dtypes and missing-value handling that ``pd.read_csv`` would.

    The non-date columns are written to text and read back with the CSV reader, so the result is the same
    as reading the equivalent CSV file (for example text cells that hold only numbers become numbers, and
    32-bit floats come back with their short decimal form). Datetime columns are kept as datetimes.

    :param frame: DataFrame read from a spreadsheet or geodatabase.
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


def _clean_guid(value):
    """
    Convert a geodatabase GUID ('{ABC...}') to the CSV form (lower case, no braces).

    :param value: GUID text, or a missing value.
    :return: Cleaned text, or the missing value unchanged.
    """
    if pd.isna(value):
        return value
    return str(value).strip().strip('{}').lower()


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
    Work out which format a form folder holds: CSV files first, then Excel workbooks, then geodatabases.

    A folder with none of these is treated as an empty CSV folder, so a missing table fails later with the
    usual FileNotFoundError, unless it holds a zipped download, which raises an error that says to unzip it.

    :param folder: Path to the form folder.
    :return: FormSource for the folder.
    """
    csv_tables = _csv_stems(folder)
    workbooks = _workbook_files(folder)
    gdbs = _gdb_folders(folder)
    if csv_tables:
        others = [label for label, found in (('Excel', workbooks), ('geodatabase', gdbs)) if found]
        if others:
            print(f'\tForm folder {folder} holds CSV and {" and ".join(others)} files; using the CSV tables')
        return FormSource(kind=_CSV_FOLDER, path=folder, tables=csv_tables)
    if workbooks:
        if gdbs:
            print(f'\tForm folder {folder} holds Excel and geodatabase files; using the Excel tables')
        tables = []
        for workbook in workbooks:
            tables.extend(name for name in _sheet_names(workbook) if name not in tables)
        return FormSource(kind=_WORKBOOK, path=folder, tables=tuple(tables), files=workbooks)
    if gdbs:
        tables = []
        for gdb in gdbs:
            tables.extend(name for name in _gdb_layer_names(gdb) if name not in tables)
        return FormSource(kind=_GDB, path=folder, tables=tuple(tables), files=gdbs)
    archives = _zip_files(folder)
    if archives:
        raise ValueError(
            f"Form folder {folder} holds a zipped download ({', '.join(os.path.basename(a) for a in archives)}) "
            f"but no CSV, Excel, or geodatabase tables. Unzip it first."
        )
    return FormSource(kind=_CSV_FOLDER, path=folder, tables=())


def _gdb_folders(folder: str) -> tuple:
    """
    List the file geodatabases (``*.gdb`` folders) in a form folder and one folder below it.

    A zipped ArcGIS download holds a single '<guid>.gdb' folder, so after unzipping it the geodatabase is either
    directly in the form folder or inside a folder named after the zip.

    :param folder: Path to the form folder.
    :return: Sorted tuple of geodatabase paths, or an empty tuple if the folder cannot be listed.
    """
    try:
        entries = sorted(os.listdir(folder))
    except OSError:
        return ()
    found = []
    for name in entries:
        path = os.path.join(folder, name)
        if not os.path.isdir(path):
            continue
        if name.lower().endswith(_GDB_EXTENSION):
            found.append(path)
            continue
        try:
            found.extend(
                os.path.join(path, sub) for sub in sorted(os.listdir(path))
                if sub.lower().endswith(_GDB_EXTENSION) and os.path.isdir(os.path.join(path, sub))
            )
        except OSError:
            continue
    return tuple(sorted(found))


def _gdb_layer_names(gdb: str) -> tuple:
    """
    List the layer and table names of a file geodatabase.

    :param gdb: Path to the geodatabase folder.
    :return: Tuple of layer names, in geodatabase order.
    """
    import pyogrio
    try:
        return tuple(str(name) for name, _geometry in pyogrio.list_layers(gdb))
    except Exception as exc:
        raise ValueError(f'Cannot open file geodatabase {gdb}: {exc}') from exc


def _gdb_table_exists(source: FormSource, stem: str) -> bool:
    """
    Check whether a geodatabase source has a layer for a table.

    :param source: Resolved geodatabase source.
    :param stem: Table name without extension (for example 'survey_0').
    :return: True if a layer with the name of the table (without its index) exists.
    """
    return _layer_name(stem).lower() in {name.lower() for name in source.tables}


def _layer_name(stem: str) -> str:
    """
    Convert a CSV table name to its geodatabase layer name by dropping the table index.

    :param stem: Table name without extension (for example 't1_woody_2').
    :return: Layer name (for example 't1_woody').
    """
    return re.sub(r'_\d+$', '', stem)


def _normalize_gdb_frame(layer_df: pd.DataFrame) -> pd.DataFrame:
    """
    Turn a geodatabase layer into the table the CSV download of the same form holds.

    The object ID (the layer's FID, which is the index here) becomes the ``ObjectID`` column; ``globalid`` and
    ``parentglobalid`` become ``GlobalID`` and ``ParentGlobalID`` with lower-case GUIDs and no braces; point
    geometry becomes ``x`` and ``y`` columns (unless the layer has them as fields); time-zone-aware dates
    become naive UTC datetimes; and the remaining columns get the dtypes ``pd.read_csv`` would give.

    :param layer_df: Layer read with ``pyogrio.read_dataframe(..., fid_as_index=True)``.
    :return: DataFrame with an ``ObjectID`` first column and no geometry column.
    """
    import geopandas as gpd
    spatial = isinstance(layer_df, gpd.GeoDataFrame)
    frame = pd.DataFrame(layer_df.drop(columns=layer_df.geometry.name)) if spatial else pd.DataFrame(layer_df)
    frame.insert(0, 'ObjectID', layer_df.index.to_numpy(dtype='int64'))
    frame = frame.reset_index(drop=True)
    frame = frame.rename(columns={c: _GUID_COLUMNS[c.lower()] for c in frame.columns if c.lower() in _GUID_COLUMNS})
    for name in _GUID_COLUMNS.values():
        if name in frame.columns:
            frame[name] = frame[name].map(_clean_guid)
    if spatial and not {'x', 'y'} & {c.lower() for c in frame.columns}:
        geometry = layer_df.geometry.reset_index(drop=True)
        for axis in ('x', 'y'):
            values = getattr(geometry, axis).to_numpy(dtype=float)
            frame[axis] = np.where(np.abs(values) < _COORDINATE_NOISE, 0.0, values)
    for column in frame.columns:
        if isinstance(frame[column].dtype, pd.DatetimeTZDtype):
            frame[column] = frame[column].dt.tz_convert('UTC').dt.tz_localize(None)
    return _as_csv_would(frame)


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


def _read_gdb_table(source: FormSource, stem: str) -> pd.DataFrame:
    """
    Read one table (layer) from a geodatabase source.

    :param source: Resolved geodatabase source.
    :param stem: Table name without extension (for example 'survey_0'); the layer is the name without the index.
    :return: DataFrame normalized like the CSV table (see ``_normalize_gdb_frame``).
    """
    import pyogrio
    layer = _layer_name(stem).lower()
    holders = []
    for gdb in source.files:
        names = {name.lower(): name for name in _gdb_layer_names(gdb)}
        if layer in names:
            holders.append((gdb, names[layer]))
    if not holders:
        raise FileNotFoundError(f"No layer named '{_layer_name(stem)}' in the geodatabases of {source.path}")
    if len(holders) > 1:
        raise ValueError(
            f"Layer '{_layer_name(stem)}' is in more than one geodatabase in {source.path}: "
            f"{', '.join(os.path.relpath(gdb, source.path) for gdb, _name in holders)}. Keep one geodatabase per form."
        )
    gdb, name = holders[0]
    print(f"\tGetting DataFrame from geodatabase layer '{name}' at: {gdb}")
    try:
        layer_df = pyogrio.read_dataframe(gdb, layer=name, fid_as_index=True)
    except Exception as exc:
        raise ValueError(f"Cannot read layer '{name}' from {gdb}: {exc}") from exc
    return _normalize_gdb_frame(layer_df)


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


def _zip_files(folder: str) -> tuple:
    """
    List the zip archives in a folder.

    :param folder: Path to the folder to inspect.
    :return: Sorted tuple of zip file paths, or an empty tuple if the folder cannot be listed.
    """
    try:
        names = os.listdir(folder)
    except OSError:
        return ()
    return tuple(sorted(os.path.join(folder, name) for name in names if name.lower().endswith('.zip')))


# Registry of source kinds: (table-exists check, table reader). Add a format by adding one entry.
_READERS = {
    _CSV_FOLDER: (_csv_table_exists, _read_csv_table),
    _GDB: (_gdb_table_exists, _read_gdb_table),
    _WORKBOOK: (_workbook_table_exists, _read_workbook_table),
}


def ensure_form_source(location: Union[str, FormSource]) -> FormSource:
    """
    Return a form source, resolving a folder path if necessary.

    A path string is resolved from the files in that folder (CSV tables first, then Excel workbooks, then file
    geodatabases). A folder that does not exist, or holds none of these, is treated as an empty CSV folder, so a
    missing table still fails later with the same error as before. An existing FormSource is returned as is.

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
