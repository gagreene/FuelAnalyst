# -*- coding: utf-8 -*-
"""
Read the tables of an ArcGIS Survey123 form, whatever file format holds them.

A form's data is resolved once into a :class:`FormSource` (``resolve_form_source`` or
``ensure_form_source``), and every table is then read from that source by name (``read_table``). Only
the Survey123 form tables go through this module. Reference tables, weather files, and FOFEM outputs
keep using ``helper.get_df()``, which must not receive Survey123 normalization or schema checks.

Each form lives in its own folder (``3_Trees``). Two kinds of format are supported:

* One file per table, named like the CSV file (``survey_0``): ``'csv_folder'`` (``.csv``),
  ``'parquet_folder'`` (``.parquet``), ``'feather_folder'`` (``.feather`` or ``.arrow``), and
  ``'geojson_folder'`` (``.geojson``: the parent table as points, repeat tables as features without geometry).
* One container per form, holding every table: ``'workbook'`` (Excel ``.xlsx`` or ``.xlsm``, one sheet per
  table, the layout of an ArcGIS Survey123 Excel download), ``'gpkg'`` (a GeoPackage, one layer per table),
  ``'sqlite'`` (a plain SQLite database, one table per table), and ``'gdb'`` (an unzipped ArcGIS file
  geodatabase, a ``*.gdb`` folder in the form folder or one folder below it, one layer per table).

A container matches a table by its full name (``survey_0``) first, then by the name without the table number
(``survey``, as ArcGIS geodatabases name their layers), ignoring case. Zipped downloads must be unzipped.

When a form folder holds several formats, one is chosen in this order: CSV, Parquet, Feather, GeoJSON,
Excel, GeoPackage, SQLite, geodatabase. A SQLite file that holds GeoPackage tables is read as a GeoPackage.

The source kinds are registered in ``_READERS``, so supporting another format means adding one reader and
one existence check.
"""
__author__ = ['Gregory A. Greene']

import contextlib
import io
import os
import re
import sqlite3
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

import numpy as np
import pandas as pd

from . import helper


@dataclass(frozen=True)
class FormSource:
    """
    Where one Survey123 form's tables live.

    :param kind: Source kind: 'csv_folder', 'parquet_folder', 'feather_folder', 'geojson_folder', 'workbook', 'gpkg',
        'sqlite', or 'gdb'.
    :param path: Path to the form folder.
    :param tables: Names of the tables found in the source when it was resolved (file names without extension,
        sheet names, or layer and table names).
    :param files: Paths of the workbooks, GeoPackages, SQLite files, or geodatabases that hold the tables (empty for
        the one-file-per-table kinds).
    """
    kind: str
    path: str
    tables: tuple = ()
    files: tuple = ()


_CSV_FOLDER = 'csv_folder'
_DATABASE_FILE = 'database_file'
_DATABASE_EXTENSIONS = ('.gpkg', '.sqlite', '.sqlite3', '.db')
_DATE_COLUMNS = ('_date', 'CreationDate', 'EditDate')
_FEATHER_FOLDER = 'feather_folder'
_GDB = 'gdb'
_GEOJSON_FOLDER = 'geojson_folder'
_GDB_EXTENSION = '.gdb'
_GPKG = 'gpkg'
_GUID_COLUMNS = {'globalid': 'GlobalID', 'parentglobalid': 'ParentGlobalID'}
_PARQUET_FOLDER = 'parquet_folder'
_SQLITE = 'sqlite'
_WORKBOOK = 'workbook'
_WORKBOOK_EXTENSIONS = ('.xlsx', '.xlsm')
# Table files, one per table: kind -> file extensions.
_FILE_KINDS = {
    _CSV_FOLDER: ('.csv',),
    _PARQUET_FOLDER: ('.parquet',),
    _FEATHER_FOLDER: ('.feather', '.arrow'),
    _GEOJSON_FOLDER: ('.geojson',),
}
# Display names, used in the note printed when a folder holds several formats.
_LABELS = {
    _CSV_FOLDER: 'CSV', _PARQUET_FOLDER: 'Parquet', _FEATHER_FOLDER: 'Feather', _GEOJSON_FOLDER: 'GeoJSON', _WORKBOOK: 'Excel',
    _DATABASE_FILE: 'GeoPackage or SQLite', _GPKG: 'GeoPackage', _SQLITE: 'SQLite', _GDB: 'geodatabase',
}
# Coordinates this close to zero are floating-point noise from a geodatabase or GeoPackage (a point stored at
# 0, 0 can read back as about 5.7e-14), so they are snapped to exactly zero.
_COORDINATE_NOISE = 1e-9


def _as_csv_would(frame: pd.DataFrame, literal_text_columns: tuple = ()) -> pd.DataFrame:
    """
    Give non-date columns the dtypes and missing-value handling that ``pd.read_csv`` would.

    The non-date columns are written to text and read back with the CSV reader, so the result is the same
    as reading the equivalent CSV file (for example text cells that hold only numbers become numbers, and
    32-bit floats come back with their short decimal form). Datetime columns are kept as datetimes, and a
    time-zone-aware one becomes a naive UTC datetime. Explicit literal-text columns
    retain their source strings, including leading zeros and tokens such as NA.

    :param frame: DataFrame read from a spreadsheet, database, or table file.
    :param literal_text_columns: Columns preserved as text without numeric or missing-token inference.
    :return: DataFrame with the same columns and column order.
    """
    frame = frame.copy()
    literal = {column: frame[column].astype('string')
               for column in literal_text_columns if column in frame.columns}
    for column in frame.columns:
        if isinstance(frame[column].dtype, pd.DatetimeTZDtype):
            frame[column] = frame[column].dt.tz_convert('UTC').dt.tz_localize(None)
    date_columns = [c for c in frame.columns if pd.api.types.is_datetime64_any_dtype(frame[c])]
    buffer = io.StringIO()
    frame.drop(columns=date_columns).to_csv(buffer, index=False)
    buffer.seek(0)
    result = pd.read_csv(buffer, header=0, index_col=False, low_memory=False)
    for column in date_columns:
        result[column] = frame[column].to_numpy()
    for column, values in literal.items():
        result[column] = pd.Series(values.array, index=result.index)
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


def _detect_source(folder: str) -> FormSource:
    """
    Work out which format a form folder holds and build its source.

    The first format found is used, in this order: CSV, Parquet, Feather, GeoJSON, Excel, GeoPackage, SQLite, geodatabase.
    Only file names are scanned here; a workbook or database is opened only when it is the chosen format. A folder
    with none of these is treated as an empty CSV folder, so a missing table fails later with the usual
    FileNotFoundError, unless it holds a zipped download, which raises an error that says to unzip it.

    :param folder: Path to the form folder.
    :return: FormSource for the folder.
    """
    found = {}
    for kind, extensions in _FILE_KINDS.items():
        stems = _file_stems(folder, extensions)
        if stems:
            found[kind] = stems
    workbooks = _files_with_extension(folder, _WORKBOOK_EXTENSIONS)
    if workbooks:
        found[_WORKBOOK] = workbooks
    databases = _files_with_extension(folder, _DATABASE_EXTENSIONS)
    if databases:
        found[_DATABASE_FILE] = databases
    gdbs = _gdb_folders(folder)
    if gdbs:
        found[_GDB] = gdbs

    if not found:
        archives = _files_with_extension(folder, ('.zip',))
        if archives:
            raise ValueError(
                f"Form folder {folder} holds a zipped download ({', '.join(os.path.basename(a) for a in archives)}) "
                f"but no CSV, Parquet, Feather, GeoJSON, Excel, GeoPackage, SQLite, or geodatabase tables. Unzip it first."
            )
        return FormSource(kind=_CSV_FOLDER, path=folder, tables=())

    chosen = next(kind for kind in (*_FILE_KINDS, _WORKBOOK, _DATABASE_FILE, _GDB) if kind in found)
    kind, files = chosen, found[chosen]
    if chosen == _DATABASE_FILE:
        geopackages = [f for f in files if f.lower().endswith('.gpkg') or _is_geopackage(f)]
        kind, files = (_GPKG, tuple(geopackages)) if geopackages else (_SQLITE, files)
    others = [_LABELS[k] for k in found if k != chosen]
    if others:
        print(f'\tForm folder {folder} holds {_LABELS[kind]} and {" and ".join(others)} files; using the {_LABELS[kind]} tables')

    if kind in _FILE_KINDS:
        return FormSource(kind=kind, path=folder, tables=files)
    tables = []
    for path in files:
        names = {
            _WORKBOOK: _sheet_names, _GPKG: _ogr_layer_names, _GDB: _ogr_layer_names, _SQLITE: _sqlite_table_names,
        }[kind](path)
        tables.extend(name for name in names if name not in tables)
    return FormSource(kind=kind, path=folder, tables=tuple(tables), files=tuple(files))


def _file_stems(folder: str, extensions: tuple) -> tuple:
    """
    List the table names (file names without extension) of the files with the given extensions in a folder.

    :param folder: Path to the folder to inspect.
    :param extensions: File extensions to match, such as ('.csv',).
    :return: Sorted tuple of table names, or an empty tuple if the folder cannot be listed.
    """
    try:
        names = os.listdir(folder)
    except OSError:
        return ()
    return tuple(sorted({
        os.path.splitext(name)[0] for name in names
        if name.lower().endswith(extensions) and os.path.isfile(os.path.join(folder, name))
    }))


def _file_table_exists(source: FormSource, stem: str) -> bool:
    """
    Check whether a one-file-per-table source has a table.

    :param source: Resolved CSV, Parquet, or Feather source.
    :param stem: Table name without extension.
    :return: True if '<stem>' plus one of the kind's extensions (in any letter case) exists in the source folder.
    """
    return bool(_table_files(source, stem))


def _files_with_extension(folder: str, extensions: tuple) -> tuple:
    """
    List the files in a folder that have one of the given extensions, skipping Excel's '~$' lock files.

    :param folder: Path to the folder to inspect.
    :param extensions: File extensions to match, such as ('.xlsx', '.xlsm').
    :return: Sorted tuple of file paths, or an empty tuple if the folder cannot be listed.
    """
    try:
        names = os.listdir(folder)
    except OSError:
        return ()
    return tuple(sorted(
        os.path.join(folder, name) for name in names
        if name.lower().endswith(extensions) and not name.startswith('~$') and os.path.isfile(os.path.join(folder, name))
    ))


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


def _is_geopackage(path: str) -> bool:
    """
    Check whether a SQLite file is a GeoPackage (it has the 'gpkg_contents' table).

    :param path: Path to the SQLite file.
    :return: True for a GeoPackage; False for any other file, including one that cannot be opened.
    """
    try:
        with contextlib.closing(sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)) as connection:
            row = connection.execute("select 1 from sqlite_master where name = 'gpkg_contents'").fetchone()
        return row is not None
    except sqlite3.Error:
        return False


def _layer_name(stem: str) -> str:
    """
    Convert a CSV table name to its geodatabase layer name by dropping the table index.

    :param stem: Table name without extension (for example 't1_woody_2').
    :return: Layer name (for example 't1_woody').
    """
    return re.sub(r'_\d+$', '', stem)


def _match_name(names: tuple, stem: str) -> Optional[str]:
    """
    Find the name in a container (sheet, layer, or table) that holds a table.

    The full name ('survey_0') is tried first, then the name without the table number ('survey'), ignoring case.

    :param names: Names found in the container.
    :param stem: Table name without extension.
    :return: The matching name as the container spells it, or None.
    """
    lower = {name.lower(): name for name in names}
    return lower.get(stem.lower()) or lower.get(_layer_name(stem).lower())


def _normalize_ogr_frame(
        layer_df: pd.DataFrame,
        parse_dates: bool = False,
        literal_text_columns: tuple = ()
) -> pd.DataFrame:
    """
    Turn a geodatabase or GeoPackage layer into the table the CSV download of the same form holds.

    The object ID becomes the ``ObjectID`` column: an ``ObjectID`` field wins when the layer has one (editing in
    QGIS or ArcGIS Pro renumbers the row IDs but keeps the field), otherwise the layer's FID, which is the index
    here, is used. ``globalid`` and ``parentglobalid`` become ``GlobalID`` and ``ParentGlobalID`` with lower-case
    GUIDs and no braces; point geometry becomes ``x`` and ``y`` columns in WGS84 degrees, reprojected if the layer uses
    another coordinate system (unless the layer has them as fields); and the remaining columns get the dtypes
    ``pd.read_csv`` would give.

    :param layer_df: Layer read with ``pyogrio.read_dataframe(..., fid_as_index=True)``.
    :param parse_dates: Also parse text in the date columns into datetimes (for formats that store dates as text).
    :param literal_text_columns: Columns preserved as text without numeric or missing-token inference.
    :return: DataFrame with an ``ObjectID`` first column and no geometry column. ``x`` and ``y`` are added only when the
        layer has point geometry (a table whose features have no geometry gets none).
    """
    import geopandas as gpd
    spatial = isinstance(layer_df, gpd.GeoDataFrame)
    frame = pd.DataFrame(layer_df.drop(columns=layer_df.geometry.name)) if spatial else pd.DataFrame(layer_df)
    frame = frame.reset_index(drop=True)
    object_id = next((c for c in frame.columns if c.lower() == 'objectid'), None)
    if object_id is None:
        frame.insert(0, 'ObjectID', layer_df.index.to_numpy(dtype='int64'))
    else:
        frame.insert(0, 'ObjectID', frame.pop(object_id))
    frame = frame.rename(columns={c: _GUID_COLUMNS[c.lower()] for c in frame.columns if c.lower() in _GUID_COLUMNS})
    for name in _GUID_COLUMNS.values():
        if name in frame.columns:
            frame[name] = frame[name].map(_clean_guid)
    if spatial and layer_df.geometry.notna().any():
        other_types = sorted(set(layer_df.geometry.geom_type.dropna()) - {'Point'})
        if other_types:
            raise ValueError(f"point geometry is needed, but the layer holds {', '.join(other_types)}")
        if not {'x', 'y'} & {c.lower() for c in frame.columns}:
            geometry = _to_wgs84(layer_df.geometry.reset_index(drop=True))
            for axis in ('x', 'y'):
                values = getattr(geometry, axis).to_numpy(dtype=float)
                frame[axis] = np.where(np.abs(values) < _COORDINATE_NOISE, 0.0, values)
    if parse_dates:
        frame = _parse_date_text(frame, literal_text_columns)
    return _as_csv_would(frame, literal_text_columns)


def _ogr_layer_names(path: str) -> tuple:
    """
    List the layer and table names of a file geodatabase or GeoPackage.

    :param path: Path to the geodatabase folder or GeoPackage file.
    :return: Tuple of layer names, in file order.
    """
    import pyogrio
    try:
        return tuple(str(name) for name, _geometry in pyogrio.list_layers(path))
    except Exception as exc:
        raise ValueError(f'Cannot open {os.path.basename(path)} ({path}): {exc}') from exc


def _ogr_table_exists(source: FormSource, stem: str) -> bool:
    """
    Check whether a geodatabase or GeoPackage source has a layer for a table.

    :param source: Resolved geodatabase or GeoPackage source.
    :param stem: Table name without extension (for example 'survey_0').
    :return: True if a layer with the table's name, or its name without the table number, exists.
    """
    return _match_name(source.tables, stem) is not None


def _parse_date_text(frame: pd.DataFrame, literal_text_columns: tuple = ()) -> pd.DataFrame:
    """
    Parse text in the date columns (``_date``, ``CreationDate``, ``EditDate``) into datetimes.

    Parsing is done as UTC, so timestamps with different offsets (for example daylight-saving and standard time)
    normalize to UTC clock time and text without an offset is read as it is. Columns that are already datetimes are kept.

    :param frame: DataFrame read from a format that stores dates as text (SQLite or GeoJSON).
    :param literal_text_columns: Columns preserved as text without numeric or missing-token inference.
    :return: DataFrame with those columns as datetimes.
    """
    frame = frame.copy()
    for column in _DATE_COLUMNS:
        if (column in frame.columns and column not in literal_text_columns
                and not pd.api.types.is_datetime64_any_dtype(frame[column])):
            frame[column] = pd.to_datetime(frame[column], format='mixed', errors='coerce', utc=True)
    return frame


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


def _read_file_table(
        source: FormSource,
        stem: str,
        literal_text_columns: tuple = ()
) -> pd.DataFrame:
    """
    Read one table from a one-file-per-table source (CSV, Parquet, Feather, or GeoJSON).

    CSV is read with the standard CSV reader (``helper.get_df``). Parquet and Feather need the optional ``pyarrow``
    package; their tables are given the dtypes ``pd.read_csv`` would infer, and time-zone-aware dates become naive UTC.

    :param source: Resolved source.
    :param stem: Table name without extension.
    :param literal_text_columns: Columns preserved as text without numeric or missing-token inference.
    :return: DataFrame with the table data.
    """
    paths = _table_files(source, stem)
    if not paths:
        raise FileNotFoundError(f"No '{stem}' table ({', '.join(_FILE_KINDS[source.kind])}) in {source.path}")
    if len(paths) > 1:
        raise ValueError(
            f"More than one {_LABELS[source.kind]} file holds the table '{stem}' in {source.path}: "
            f"{', '.join(os.path.basename(path) for path in paths)}. Keep one file per table."
        )
    path = paths[0]
    if source.kind == _CSV_FOLDER:
        frame = helper.get_df(path)
        if literal_text_columns:
            # Read protected cells from the source; casting the inferred frame loses 001/NA.
            literal = pd.read_csv(
                path, usecols=lambda name: name in literal_text_columns,
                dtype=str, keep_default_na=False, na_filter=False,
            )
            for column in literal:
                frame[column] = literal[column]
        return frame
    if source.kind == _GEOJSON_FOLDER:
        return _read_geojson_file(path, literal_text_columns)
    try:
        import pyarrow  # noqa: F401
    except ImportError as exc:
        raise ImportError(
            f'Reading {_LABELS[source.kind]} tables needs the pyarrow package: pip install pyarrow '
            f'(or pip install "fuel-analyst[parquet]")'
        ) from exc
    print(f'\tGetting DataFrame from {_LABELS[source.kind]} file at: {path}')
    try:
        frame = pd.read_parquet(path) if source.kind == _PARQUET_FOLDER else pd.read_feather(path)
    except Exception as exc:
        raise ValueError(f'Cannot read {path}: {exc}') from exc
    return _as_csv_would(frame, literal_text_columns)


def _read_geojson_file(path: str, literal_text_columns: tuple = ()) -> pd.DataFrame:
    """
    Read one GeoJSON table file.

    The parent table holds point features (GeoJSON coordinates are WGS84 degrees); a repeat table holds features without
    geometry. ``ObjectID`` is the property of that name or else the feature's id, ``x`` and ``y`` come from the points,
    and date text is parsed (as UTC).

    :param path: Path to the ``.geojson`` file.
    :param literal_text_columns: Columns preserved as text without numeric or missing-token inference.
    :return: DataFrame normalized like the CSV table (see ``_normalize_ogr_frame``).
    """
    import pyogrio
    print(f'\tGetting DataFrame from GeoJSON file at: {path}')
    try:
        layer_df = pyogrio.read_dataframe(path, fid_as_index=True)
    except Exception as exc:
        raise ValueError(f'Cannot read {path}: {exc}') from exc
    try:
        return _normalize_ogr_frame(layer_df, parse_dates=True, literal_text_columns=literal_text_columns)
    except ValueError as exc:
        raise ValueError(f'{path}: {exc}') from exc


def _read_ogr_table(
        source: FormSource,
        stem: str,
        literal_text_columns: tuple = ()
) -> pd.DataFrame:
    """
    Read one table (layer) from a geodatabase or GeoPackage source.

    :param source: Resolved geodatabase or GeoPackage source.
    :param stem: Table name without extension (for example 'survey_0').
    :param literal_text_columns: Columns preserved as text without numeric or missing-token inference.
    :return: DataFrame normalized like the CSV table (see ``_normalize_ogr_frame``).
    """
    import pyogrio
    label = _LABELS[source.kind]
    holders = []
    for path in source.files:
        name = _match_name(_ogr_layer_names(path), stem)
        if name is not None:
            holders.append((path, name))
    if not holders:
        raise FileNotFoundError(f"No layer for '{stem}' in the {label} files of {source.path}")
    if len(holders) > 1:
        raise ValueError(
            f"A layer for '{stem}' is in more than one {label} in {source.path}: "
            f"{', '.join(os.path.relpath(path, source.path) for path, _name in holders)}. Keep one {label} per form."
        )
    path, name = holders[0]
    print(f"\tGetting DataFrame from {label} layer '{name}' at: {path}")
    try:
        layer_df = pyogrio.read_dataframe(path, layer=name, fid_as_index=True)
    except Exception as exc:
        raise ValueError(f"Cannot read layer '{name}' from {path}: {exc}") from exc
    try:
        return _normalize_ogr_frame(layer_df, literal_text_columns=literal_text_columns)
    except ValueError as exc:
        raise ValueError(f"Layer '{name}' in {path}: {exc}") from exc


def _read_sqlite_table(
        source: FormSource,
        stem: str,
        literal_text_columns: tuple = ()
) -> pd.DataFrame:
    """
    Read one table from a plain SQLite source.

    SQLite stores dates as text, so the ``_date``, ``CreationDate``, and ``EditDate`` columns are parsed into datetimes
    (ISO text and the CSV date formats both work). Parsing is done as UTC, so timestamps with different offsets (for example
    daylight-saving and standard time) normalize to UTC clock time and text without an offset is read as it is. The other
    columns get the dtypes ``pd.read_csv`` would infer.

    :param source: Resolved SQLite source.
    :param stem: Table name without extension (for example 'survey_0').
    :param literal_text_columns: Columns preserved as text without numeric or missing-token inference.
    :return: DataFrame with the table data.
    """
    holders = []
    for path in source.files:
        name = _match_name(_sqlite_table_names(path), stem)
        if name is not None:
            holders.append((path, name))
    if not holders:
        raise FileNotFoundError(f"No table for '{stem}' in the SQLite files of {source.path}")
    if len(holders) > 1:
        raise ValueError(
            f"A table for '{stem}' is in more than one SQLite file in {source.path}: "
            f"{', '.join(os.path.basename(path) for path, _name in holders)}. Keep one SQLite file per form."
        )
    path, name = holders[0]
    print(f"\tGetting DataFrame from SQLite table '{name}' at: {path}")
    try:
        with contextlib.closing(sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)) as connection:
            frame = pd.read_sql_query('select * from "' + name.replace('"', '""') + '"', connection)
    except Exception as exc:
        raise ValueError(f"Cannot read table '{name}' from {path}: {exc}") from exc
    return _as_csv_would(_parse_date_text(frame, literal_text_columns), literal_text_columns)


def _read_workbook_table(
        source: FormSource,
        stem: str,
        literal_text_columns: tuple = ()
) -> pd.DataFrame:
    """
    Read one table (sheet) from a workbook source.

    The result matches what the CSV reader would give for the same data: columns that hold numbers or
    numbers stored as text get the same dtypes ``pd.read_csv`` infers, and ``'NA'`` text is missing
    unless the caller explicitly protects that column as literal text.
    Date columns stay datetimes, which ``helper.get_unique_id`` accepts.

    :param source: Resolved workbook source.
    :param stem: Table name without extension; the sheet is the table name, or the name without its number.
    :param literal_text_columns: Columns preserved as text without numeric or missing-token inference.
    :return: DataFrame with the sheet data.
    """
    holders = []
    for path in source.files:
        name = _match_name(_sheet_names(path), stem)
        if name is not None:
            holders.append((path, name))
    if not holders:
        raise FileNotFoundError(f"No sheet for '{stem}' in the Excel workbooks of {source.path}")
    if len(holders) > 1:
        raise ValueError(
            f"A sheet for '{stem}' is in more than one workbook in {source.path}: "
            f"{', '.join(os.path.basename(path) for path, _name in holders)}. Keep one workbook per form."
        )
    path, name = holders[0]
    print(f"\tGetting DataFrame from Excel sheet '{name}' at: {path}")
    try:
        with _quiet_openpyxl():
            frame = pd.read_excel(path, sheet_name=name, header=0, engine='openpyxl')
            if literal_text_columns:
                literal = pd.read_excel(
                    path, sheet_name=name, header=0, engine='openpyxl',
                    usecols=lambda column: column in literal_text_columns,
                    dtype=str, keep_default_na=False, na_filter=False,
                )
                for column in literal:
                    frame[column] = literal[column]
    except Exception as exc:
        raise ValueError(f"Cannot read sheet '{name}' from {path}: {exc}") from exc
    return _as_csv_would(frame, literal_text_columns)


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


def _sqlite_table_exists(source: FormSource, stem: str) -> bool:
    """
    Check whether a SQLite source has a table for a table name.

    :param source: Resolved SQLite source.
    :param stem: Table name without extension (for example 'survey_0').
    :return: True if a table with that name, or its name without the table number, exists.
    """
    return _match_name(source.tables, stem) is not None


def _sqlite_table_names(path: str) -> tuple:
    """
    List the tables of a plain SQLite database (without SQLite's own 'sqlite_' tables).

    :param path: Path to the SQLite file.
    :return: Tuple of table names.
    """
    try:
        with contextlib.closing(sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)) as connection:
            rows = connection.execute(
                "select name from sqlite_master where type = 'table' and name not like 'sqlite_%' order by rowid"
            ).fetchall()
    except sqlite3.Error as exc:
        raise ValueError(f'Cannot open SQLite file {path}: {exc}') from exc
    return tuple(row[0] for row in rows)


def _table_files(source: FormSource, stem: str) -> list:
    """
    Find the files of a table in a one-file-per-table source, as they are spelled on disk.

    The table name must match exactly; the extension is matched ignoring letter case, so 'survey_0.PARQUET' counts.

    :param source: Resolved CSV, Parquet, or Feather source.
    :param stem: Table name without extension.
    :return: Sorted list of matching file paths (more than one means an ambiguous table).
    """
    try:
        names = os.listdir(source.path)
    except OSError:
        return []
    extensions = _FILE_KINDS[source.kind]
    return sorted(
        os.path.join(source.path, name) for name in names
        if os.path.splitext(name)[0] == stem and os.path.splitext(name)[1].lower() in extensions
        and os.path.isfile(os.path.join(source.path, name))
    )


def _to_wgs84(geometry):
    """
    Return point geometry in geographic WGS84 degrees (EPSG:4326), so x and y can be used as longitude and latitude.

    A layer in another coordinate system (for example a projected one such as BC Albers, as QGIS and ArcGIS Pro often save)
    is reprojected. A layer with no coordinate system (or an undefined one) is accepted only when every coordinate is a valid
    longitude and latitude; anything else cannot be interpreted and raises an error.

    :param geometry: GeoSeries of points.
    :return: GeoSeries in EPSG:4326 (or unchanged if it has no valid points).
    """
    # Older GDAL versions read a layer saved without a coordinate system as 'Undefined geographic SRS', not as None.
    if geometry.crs is not None and 'undefined' not in str(geometry.crs.name).lower():
        return geometry if geometry.crs.to_epsg() == 4326 else geometry.to_crs(4326)
    min_x, min_y, max_x, max_y = geometry.total_bounds
    if np.isnan([min_x, min_y, max_x, max_y]).all():
        return geometry
    if min_x < -180 or max_x > 180 or min_y < -90 or max_y > 90:
        raise ValueError(
            'the layer has no coordinate system and its coordinates are not longitude and latitude in degrees; '
            'define its coordinate system (for example EPSG:4326) in the file'
        )
    print('\tThe layer has no coordinate system; its coordinates are read as WGS84 longitude and latitude')
    return geometry


def _workbook_table_exists(source: FormSource, stem: str) -> bool:
    """
    Check whether a workbook source has a sheet for a table.

    :param source: Resolved workbook source.
    :param stem: Table name without extension (for example 'survey_0').
    :return: True if a sheet has the table's name, or its name without the table number.
    """
    return _match_name(source.tables, stem) is not None


# Registry of source kinds: (table-exists check, table reader). Add a format by adding one entry.
_READERS = {
    _CSV_FOLDER: (_file_table_exists, _read_file_table),
    _FEATHER_FOLDER: (_file_table_exists, _read_file_table),
    _GDB: (_ogr_table_exists, _read_ogr_table),
    _GEOJSON_FOLDER: (_file_table_exists, _read_file_table),
    _GPKG: (_ogr_table_exists, _read_ogr_table),
    _PARQUET_FOLDER: (_file_table_exists, _read_file_table),
    _SQLITE: (_sqlite_table_exists, _read_sqlite_table),
    _WORKBOOK: (_workbook_table_exists, _read_workbook_table),
}


def ensure_form_source(location: Union[str, FormSource]) -> FormSource:
    """
    Return a form source, resolving a folder path if necessary.

    A path string is resolved from the files in that folder (CSV, Parquet, Feather, GeoJSON, Excel, GeoPackage, SQLite,
    then file geodatabase tables, whichever is found first). A folder that does not exist, or holds none of these, is
    treated as an empty CSV folder, so a missing table still fails later with the same error as before. An existing
    FormSource is returned as is.

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


def read_table(
        source: Union[str, FormSource],
        stem: str,
        required: bool = True,
        literal_text_columns: tuple = ()
) -> Optional[pd.DataFrame]:
    """
    Read one table of a Survey123 form.

    :param source: A resolved FormSource, or the path to a form folder.
    :param stem: Table name without extension (for example 'survey_0').
    :param required: If True, a missing table raises FileNotFoundError; if False, None is returned.
    :param literal_text_columns: Columns preserved as text without numeric or missing-token inference.
    :return: DataFrame with the table data, or None when the table is absent and not required.
    """
    source = ensure_form_source(source)
    if not required and not has_table(source, stem):
        return None
    _, reader = _READERS[source.kind]
    return reader(source, stem, literal_text_columns=literal_text_columns)


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
