"""
Recreate ArcGIS Survey123 Excel and file geodatabase downloads from the CSV example dataset.

Decoded structure of real ArcGIS Online downloads (2026-10-13 sample, five forms):

Excel (``S123_<32 hex>_EXCEL.xlsx``, one workbook per form, in the form folder)
  - One sheet per table, named exactly like the CSV stem (``survey_0``, ``regeneration_1``, ...), ordered by table index.
    Empty repeat tables are present as a header-only sheet.
  - Row 1 is the header; the columns, their names, and their order are identical to the CSV.
  - Dates (``_date``, ``CreationDate``, ``EditDate``) are real datetime cells with the same wall-clock time as the
    CSV text. Number formats: ``_date`` 'M/d/yyyy h:mm'; ``CreationDate`` and ``EditDate`` 'MM/dd/yyyy hh:mm:ss.000'.
  - Text choice codes stay text cells (for example '1'); numbers are numeric cells; blanks are empty cells.

File geodatabase (``S123_<32 hex>_FGDB.zip`` holding one ``<guid>.gdb`` folder; this script writes the unzipped folder)
  - Layer names drop the CSV table index: ``survey``, ``regeneration``, ``sapling``, ``tree_plot``, ``t1_woody``, ...
  - ``survey`` is a Point layer (geometry column ``SHAPE``, EPSG:4326); repeat tables have no geometry.
  - The object ID is the layer FID, named ``objectid`` (not a column); field names are lower case for
    ``globalid`` and ``parentglobalid`` and keep their case otherwise (``CreationDate``).
  - GlobalIDs are '{UPPER-CASE-GUID}' (braces); the CSV has lower-case GUIDs without braces.
  - ``x`` and ``y`` are the point geometry when ArcGIS appends them (the last two CSV columns); they are real fields too
    when they sit mid-table (the plot form). Every point here carries the plot's real coordinates from the example
    data (a form without x and y columns takes them from the plot form's record for the same plot). Uncleaned
    downloads can hold 0, 0 or empty coordinates because tablets without GPS fill in defaults; that is a data-cleaning
    matter, not part of the format, so it is not reproduced.
  - Dates are UTC datetimes with the same wall-clock value as the CSV text (milliseconds).
  - Numeric fields keep their ESRI types (int32, float32, float64); the types come from the reference JSON.

Other formats written from the same data (the organization FuelAnalyst reads; see the README "Supported file formats"):

  - Parquet and Feather: one ``<table>.parquet`` or ``<table>.feather`` per table, named like the CSV (``survey_0``), with typed
    columns and real datetimes. They need pyarrow.
  - GeoPackage: one ``<form>.gpkg`` per form with the same layers as the geodatabase (``survey``, ``tree_plot``, ...), the object ID
    as the ``fid`` column, and point geometry for ``survey``.
  - SQLite: one ``<form>.sqlite`` per form with one plain table per CSV table (``survey_0``), x and y as columns, and dates as
    ISO text.

Output layout: ``<out>/<format>/<form>/...`` for each selected format (every one a
complete input folder to pass as ``in_dir``), plus ``<out>/all_formats/<form>/...`` where every form folder holds all the selected
formats at once, like a download bundle (FuelAnalyst then reads the CSV tables).

Usage (every option is optional):
    python examples/generate_multiformat_example_datasets.py [--src DIR] [--out DIR] [--formats FORMAT ...] [--no-bundle]

    --src DIR          Folder of CSV example form folders (default: examples/data/Survey123_Data, the committed input data)
    --out DIR          Output folder (default: examples/results/survey123_formats, a generated, git-ignored folder)
    --formats F ...    Formats to write, any of: csv excel gdb gpkg sqlite parquet feather (default: all; parquet and feather
                       are skipped with a message when pyarrow is missing, and are an error when asked for explicitly)
    --no-bundle        Skip the all_formats folder (written when at least two formats are selected)
    --reference FILE   Column types of a real ArcGIS download (default: examples/data/esri_reference_types.json, schema only)

For example, ``--formats gpkg sqlite`` writes only ``<out>/gpkg/`` and ``<out>/sqlite/`` (and the bundle holding both). The script
needs pandas, geopandas, pyogrio, and openpyxl (installed with FuelAnalyst) and pyarrow for Parquet and Feather
(``pip install "fuel-analyst[parquet]"``).

When to run it: on demand, to produce a human-inspectable sample of every input format (for example when the example CSV
tables, the supported formats, or the docs change). The automated tests do not use this script; they build their inputs from
the example CSV tables in a temporary folder (tests/integration/survey123_formats.py). The output folder is not committed.
"""
import argparse
import contextlib
import hashlib
import io
import json
import os
import re
import shutil
import sqlite3
import sys
import uuid
import warnings

import geopandas as gpd
import numpy as np
import openpyxl
import pandas as pd
import pyogrio

warnings.filterwarnings('ignore')

DATE_COLUMNS = ('_date', 'CreationDate', 'EditDate')
EXCEL_DATE_FORMATS = {'_date': 'M/d/yyyy h:mm', 'CreationDate': 'MM/dd/yyyy hh:mm:ss.000', 'EditDate': 'MM/dd/yyyy hh:mm:ss.000'}
STEM = re.compile(r'^(?P<name>.+)_(?P<idx>\d+)$')
GUID = re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')


def _infer_type(values: pd.Series) -> str:
    """
    Infer a column type from raw CSV text.

    :param values: Raw text values of one column.
    :return: 'int64', 'float64', or 'str'.
    """
    present = values.dropna()
    if present.empty:
        return 'str'
    as_number = pd.to_numeric(present, errors='coerce')
    if as_number.notna().all():
        return 'int64' if (as_number == as_number.round()).all() and not present.str.contains(r'[.eE]').any() else 'float64'
    return 'str'


def _parse_dates(values: pd.Series) -> pd.Series:
    """
    Parse CSV date text (either 24-hour or 12-hour, with or without seconds) into datetimes.

    :param values: Raw date text values.
    :return: Datetime series (NaT where blank).
    """
    return pd.to_datetime(values, format='mixed', errors='coerce')


def _read_raw(csv_path: str) -> pd.DataFrame:
    """
    Read a CSV table as raw text so values such as '1' keep their text form.

    :param csv_path: Path to the CSV table.
    :return: DataFrame of strings, with blanks as missing values.
    """
    # Default NA handling matches what pd.read_csv does in the pipeline (for example the text 'NA' is missing).
    raw = pd.read_csv(csv_path, dtype=str, encoding='utf-8-sig')
    # Real GlobalIDs are GUIDs; the example data uses descriptive parent IDs, so map those to stable GUIDs.
    for column in ('GlobalID', 'ParentGlobalID'):
        if column in raw.columns:
            raw[column] = raw[column].map(_to_guid)
    return raw


def _to_guid(value):
    """
    Return a lower-case GUID string for an ID, deriving a stable one (uuid5) when the ID is not already a GUID.

    :param value: ID text, or a missing value.
    :return: GUID text (lower case, no braces), or None for a missing value.
    """
    if pd.isna(value):
        return None
    text = str(value).strip('{}')
    if GUID.match(text):
        return text.lower()
    return str(uuid.uuid5(uuid.NAMESPACE_URL, 'fuelanalyst-example:' + str(value)))


def _esri_csv_date(value) -> str:
    """
    Format a datetime like an ArcGIS CSV export ('9/21/2026 7:00:00 PM').

    :param value: Datetime or NaT.
    :return: Text, or an empty string for NaT.
    """
    if pd.isna(value):
        return ''
    hour12 = value.hour % 12 or 12
    return f'{value.month}/{value.day}/{value.year} {hour12}:{value.minute:02d}:{value.second:02d} {"AM" if value.hour < 12 else "PM"}'


def write_csv(form_dir: str, out_form_dir: str) -> None:
    """
    Write one form's CSV tables in the style of an ArcGIS CSV export.

    UTF-8 with a byte order mark, no quoting, blanks for missing values, and dates as 'M/d/yyyy h:mm:ss AM/PM'.

    :param form_dir: Source form folder with CSV tables.
    :param out_form_dir: Output form folder.
    :return: None. Writes the CSV files.
    """
    for stem in _tables(form_dir):
        raw = _read_raw(os.path.join(form_dir, stem + '.csv'))
        for column in DATE_COLUMNS:
            if column in raw.columns:
                raw[column] = _parse_dates(raw[column]).map(_esri_csv_date)
        raw.to_csv(os.path.join(out_form_dir, stem + '.csv'), index=False, encoding='utf-8-sig', lineterminator='\n')


def _stable_id(text: str) -> str:
    """
    Make a stable 32-character hex id (like the S123_<id> parts of real file names).

    :param text: Seed text.
    :return: 32 hex characters.
    """
    return hashlib.md5(text.encode('utf-8')).hexdigest()


def _tables(form_dir: str) -> list:
    """
    List the CSV table stems of a form, ordered by their numeric table index.

    :param form_dir: Path to the form folder.
    :return: Sorted list of table stems.
    """
    stems = [os.path.splitext(f)[0] for f in os.listdir(form_dir) if f.lower().endswith('.csv')]
    return sorted(stems, key=lambda s: int(STEM.match(s).group('idx')))


def _typed_column(raw: pd.Series, kind: str):
    """
    Convert raw text values to Python values of one type.

    :param raw: Raw text values.
    :param kind: 'int64', 'float64', 'str', or 'datetime'.
    :return: List of values with None for blanks.
    """
    out = []
    for value in raw:
        if pd.isna(value):
            out.append(None)
        elif kind == 'int64':
            out.append(int(float(value)))
        elif kind == 'float64':
            out.append(float(value))
        else:
            out.append(str(value))
    return out


def write_excel(form_dir: str, out_form_dir: str, reference: dict) -> str:
    """
    Write one form's ESRI-style Excel workbook.

    :param form_dir: Source form folder with CSV tables.
    :param out_form_dir: Output form folder.
    :param reference: Type reference (``reference['excel'][sheet][column]``).
    :return: Path of the written workbook.
    """
    book = openpyxl.Workbook()
    book.remove(book.active)
    for stem in _tables(form_dir):
        raw = _read_raw(os.path.join(form_dir, stem + '.csv'))
        sheet = book.create_sheet(stem)
        sheet.append(list(raw.columns))
        ref = reference['excel'].get(stem, {})
        columns = {}
        for column in raw.columns:
            if column in DATE_COLUMNS:
                columns[column] = ('datetime', _parse_dates(raw[column]))
            else:
                kind = ref.get(column) or _infer_type(raw[column])
                columns[column] = (kind, _typed_column(raw[column], kind))
        for i in range(len(raw)):
            row = []
            for column in raw.columns:
                kind, values = columns[column]
                value = values.iloc[i] if kind == 'datetime' else values[i]
                if kind == 'datetime':
                    value = None if pd.isna(value) else value.to_pydatetime()
                row.append(value)
            sheet.append(row)
        for j, column in enumerate(raw.columns, start=1):
            if column in DATE_COLUMNS:
                for i in range(2, len(raw) + 2):
                    sheet.cell(row=i, column=j).number_format = EXCEL_DATE_FORMATS[column]
    path = os.path.join(out_form_dir, f'S123_{_stable_id(os.path.basename(form_dir))}_EXCEL.xlsx')
    book.save(path)
    return path


def _gdb_frame(raw: pd.DataFrame, layer: str, ref: dict):
    """
    Build the geodatabase table for one CSV table.

    :param raw: Raw text CSV table.
    :param layer: Geodatabase layer name.
    :param ref: Field-type reference for the layer (``reference['gdb'][layer]``).
    :return: (DataFrame, is_point_layer). Geometry is attached later by the caller.
    """
    out = pd.DataFrame(index=range(len(raw)))
    out['objectid'] = raw['ObjectID'].astype('int64').to_numpy()
    # x and y are the point geometry when ArcGIS appends them (the last two CSV columns); when they sit mid-table (the plot
    # form) they are real form fields, so they stay as attributes too.
    geometry_only = list(raw.columns[-2:]) == ['x', 'y']
    for column in raw.columns:
        if column == 'ObjectID' or (geometry_only and column in ('x', 'y')):
            continue
        name = {'GlobalID': 'globalid', 'ParentGlobalID': 'parentglobalid'}.get(column, column)
        if column in DATE_COLUMNS:
            parsed = _parse_dates(raw[column])
            out[name] = parsed.dt.tz_localize('UTC').astype('datetime64[ms, UTC]')
            continue
        if column in ('GlobalID', 'ParentGlobalID'):
            out[name] = raw[column].map(lambda v: None if pd.isna(v) else '{' + str(v).upper() + '}')
            continue
        dtype = ref.get(name)
        kind = _infer_type(raw[column])
        if dtype is None:
            dtype = {'int64': 'int32', 'float64': 'float64', 'str': 'object'}[kind]
        if dtype == 'object':
            out[name] = raw[column].where(raw[column].notna(), None).astype(object)
        elif dtype == 'int32':
            out[name] = pd.to_numeric(raw[column], errors='coerce').round().astype('Int32')
        else:
            out[name] = pd.to_numeric(raw[column], errors='coerce').astype(dtype)
    return out, 'x' in raw.columns and 'y' in raw.columns


def _plot_key(raw: pd.DataFrame) -> pd.Series:
    """
    Build a plot identity key from the parent-table columns that identify a plot.

    :param raw: Raw text parent table (survey_0).
    :return: Series of 'area|unit|type|plot' keys.
    """
    columns = ['treatment_area', 'treatment_unit', 'treatment_type', 'plot_id']
    return raw[columns].fillna('').agg('|'.join, axis=1)


def plot_coordinates(src: str) -> dict:
    """
    Collect each plot's coordinates from the parent tables that have x and y columns.

    :param src: Folder holding the CSV example form folders.
    :return: Dict {plot key: (x, y)} with the first non-missing pair per plot.
    """
    found = {}
    for form in sorted(os.listdir(src)):
        path = os.path.join(src, form, 'survey_0.csv')
        if not os.path.exists(path):
            continue
        raw = _read_raw(path)
        if 'x' not in raw.columns or 'y' not in raw.columns:
            continue
        x, y = pd.to_numeric(raw['x'], errors='coerce'), pd.to_numeric(raw['y'], errors='coerce')
        for key, xv, yv in zip(_plot_key(raw), x, y):
            if pd.notna(xv) and pd.notna(yv) and key not in found:
                found[key] = (float(xv), float(yv))
    return found


def _typed_frame(raw: pd.DataFrame) -> pd.DataFrame:
    """
    Give a raw text table the dtypes ``pd.read_csv`` infers and real datetimes in the date columns.

    :param raw: Raw text CSV table.
    :return: Typed DataFrame.
    """
    typed = pd.read_csv(io.StringIO(raw.to_csv(index=False)), low_memory=False)
    for column in DATE_COLUMNS:
        if column in typed.columns:
            typed[column] = _parse_dates(typed[column])
    return typed


def write_gdb(form_dir: str, out_form_dir: str, reference: dict, coordinates: dict = None) -> str:
    """
    Write one form's ESRI-style file geodatabase (unzipped folder).

    :param form_dir: Source form folder with CSV tables.
    :param out_form_dir: Output form folder.
    :param reference: Type reference (``reference['gdb'][layer][field]``).
    :param coordinates: Plot coordinates from :func:`plot_coordinates`, used for a parent table without x and y.
    :return: Path of the written geodatabase folder.
    """
    path = os.path.join(out_form_dir, str(uuid.uuid5(uuid.NAMESPACE_URL, os.path.basename(form_dir))) + '.gdb')
    return _write_ogr(form_dir, path, reference, coordinates, 'OpenFileGDB', 'objectid')


def write_gpkg(form_dir: str, out_form_dir: str, reference: dict, coordinates: dict = None) -> str:
    """
    Write one form's GeoPackage (one file, the same layers as the geodatabase, the object ID as the ``fid`` column).

    :param form_dir: Source form folder with CSV tables.
    :param out_form_dir: Output form folder.
    :param reference: Type reference (``reference['gdb'][layer][field]``).
    :param coordinates: Plot coordinates from :func:`plot_coordinates`, used for a parent table without x and y.
    :return: Path of the written GeoPackage.
    """
    path = os.path.join(out_form_dir, os.path.basename(form_dir) + '.gpkg')
    return _write_ogr(form_dir, path, reference, coordinates, 'GPKG', 'fid')


def write_sqlite(form_dir: str, out_form_dir: str) -> str:
    """
    Write one form's plain SQLite database: one table per CSV table, x and y as columns, dates as ISO text.

    :param form_dir: Source form folder with CSV tables.
    :param out_form_dir: Output form folder.
    :return: Path of the written database.
    """
    path = os.path.join(out_form_dir, os.path.basename(form_dir) + '.sqlite')
    if os.path.exists(path):
        os.remove(path)
    with contextlib.closing(sqlite3.connect(path)) as connection:
        for stem in _tables(form_dir):
            typed = _typed_frame(_read_raw(os.path.join(form_dir, stem + '.csv')))
            for column in DATE_COLUMNS:
                if column in typed.columns:
                    typed[column] = typed[column].dt.strftime('%Y-%m-%d %H:%M:%S')
            typed.to_sql(stem, connection, index=False)
    return path


def write_table_files(form_dir: str, out_form_dir: str, kind: str) -> list:
    """
    Write one form's tables as one Parquet or Feather file per table (named like the CSV; needs pyarrow).

    :param form_dir: Source form folder with CSV tables.
    :param out_form_dir: Output form folder.
    :param kind: 'parquet' or 'feather'.
    :return: Paths of the written files.
    """
    paths = []
    for stem in _tables(form_dir):
        typed = _typed_frame(_read_raw(os.path.join(form_dir, stem + '.csv')))
        path = os.path.join(out_form_dir, f'{stem}.{kind}')
        typed.to_parquet(path, index=False) if kind == 'parquet' else typed.to_feather(path)
        paths.append(path)
    return paths


def _write_ogr(form_dir: str, path: str, reference: dict, coordinates: dict, driver: str, fid: str) -> str:
    """
    Write one form as a file geodatabase or GeoPackage (one layer per table, point geometry for the parent table).

    :param form_dir: Source form folder with CSV tables.
    :param path: Path of the geodatabase folder or GeoPackage file to write.
    :param reference: Type reference (``reference['gdb'][layer][field]``).
    :param coordinates: Plot coordinates from :func:`plot_coordinates`, used for a parent table without x and y.
    :param driver: 'OpenFileGDB' or 'GPKG'.
    :param fid: Name of the object ID column ('objectid' or 'fid').
    :return: The path written.
    """
    coordinates = coordinates or {}
    if os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)
    elif os.path.exists(path):
        os.remove(path)
    for stem in _tables(form_dir):
        match = STEM.match(stem)
        layer, is_parent = match.group('name'), int(match.group('idx')) == 0
        raw = _read_raw(os.path.join(form_dir, stem + '.csv'))
        frame, has_xy = _gdb_frame(raw, layer, reference['gdb'].get(layer, {}))
        frame = frame.rename(columns={'objectid': fid})
        if is_parent:
            if has_xy:
                x, y = pd.to_numeric(raw['x'], errors='coerce'), pd.to_numeric(raw['y'], errors='coerce')
            else:
                pairs = _plot_key(raw).map(lambda key: coordinates.get(key, (np.nan, np.nan)))
                x, y = pairs.map(lambda p: p[0]), pairs.map(lambda p: p[1])
            gdf = gpd.GeoDataFrame(frame, geometry=gpd.points_from_xy(x, y), crs='EPSG:4326')
            gdf.geometry.name = 'SHAPE'
            pyogrio.write_dataframe(gdf, path, layer=layer, driver=driver, geometry_type='Point',
                                    layer_options={'FID': fid, 'GEOMETRY_NAME': 'SHAPE'})
        else:
            pyogrio.write_dataframe(frame, path, layer=layer, driver=driver, layer_options={'FID': fid})
    return path


FORMATS = ('csv', 'excel', 'gdb', 'gpkg', 'sqlite', 'parquet', 'feather')


def _selected_formats(requested: list = None) -> list:
    """
    Work out which formats to write.

    :param requested: Format names asked for, or None for every format.
    :return: List of format names, in the standard order.
    :raises ValueError: For a name that is not a format.
    :raises ImportError: If Parquet or Feather is asked for explicitly and pyarrow is not installed.
    """
    try:
        import pyarrow  # noqa: F401
        arrow = True
    except ImportError:
        arrow = False
    if requested is None:
        if not arrow:
            print('pyarrow is not installed: skipping the Parquet and Feather files')
        return [f for f in FORMATS if arrow or f not in ('parquet', 'feather')]
    unknown = [f for f in requested if f not in FORMATS]
    if unknown:
        raise ValueError(f"Unknown format(s) {', '.join(unknown)}. Choose from: {', '.join(FORMATS)}")
    if not arrow and {'parquet', 'feather'} & set(requested):
        raise ImportError('Parquet and Feather need pyarrow: pip install "fuel-analyst[parquet]"')
    return [f for f in FORMATS if f in requested]


def main(src: str, out: str, reference_path: str, formats: list = None, bundle: bool = True) -> None:
    """
    Build the example dataset in the selected input formats.

    :param src: Folder holding the CSV example form folders.
    :param out: Output folder; ``<format>/<form>/`` for each format and ``all_formats/<form>/`` with the formats together.
    :param reference_path: Path to the type reference JSON.
    :param formats: Formats to write (any of ``FORMATS``), or None for all of them.
    :param bundle: Also write the ``all_formats`` folder (only when at least two formats are selected).
    :return: None. Writes the files.
    """
    selected = _selected_formats(formats)
    with open(reference_path, encoding='utf-8') as fh:
        reference = json.load(fh)
    coordinates = plot_coordinates(src)
    writers = {
        'csv': lambda form_dir, out_form: write_csv(form_dir, out_form),
        'excel': lambda form_dir, out_form: write_excel(form_dir, out_form, reference),
        'gdb': lambda form_dir, out_form: write_gdb(form_dir, out_form, reference, coordinates),
        'gpkg': lambda form_dir, out_form: write_gpkg(form_dir, out_form, reference, coordinates),
        'sqlite': lambda form_dir, out_form: write_sqlite(form_dir, out_form),
        'parquet': lambda form_dir, out_form: write_table_files(form_dir, out_form, 'parquet'),
        'feather': lambda form_dir, out_form: write_table_files(form_dir, out_form, 'feather'),
    }
    writers = {fmt: writers[fmt] for fmt in selected}
    for form in sorted(os.listdir(src)):
        form_dir = os.path.join(src, form)
        if not os.path.isdir(form_dir):
            continue
        for fmt, write in writers.items():
            out_form = os.path.join(out, fmt, form)
            os.makedirs(out_form, exist_ok=True)
            write(form_dir, out_form)
        if bundle and len(writers) > 1:
            bundle_form = os.path.join(out, 'all_formats', form)
            os.makedirs(bundle_form, exist_ok=True)
            for write in writers.values():
                write(form_dir, bundle_form)
        print(f'{form}: {", ".join(writers)}')


if __name__ == '__main__':
    here = os.path.dirname(os.path.abspath(__file__))
    parser = argparse.ArgumentParser(description='Write the example Survey123 dataset in the supported input formats.')
    parser.add_argument('--src', default=os.path.join(here, 'data', 'Survey123_Data'),
                        help='folder of CSV example form folders (default: examples/data/Survey123_Data)')
    parser.add_argument('--out', default=os.path.join(here, 'results', 'survey123_formats'),
                        help='output folder (default: examples/results/survey123_formats)')
    parser.add_argument('--formats', nargs='+', choices=FORMATS, metavar='FORMAT',
                        help=f"formats to write, any of: {', '.join(FORMATS)} (default: all)")
    parser.add_argument('--no-bundle', action='store_true', help='skip the all_formats folder')
    parser.add_argument('--reference', default=os.path.join(here, 'data', 'esri_reference_types.json'),
                        help='column types of a real ArcGIS download (default: examples/data/esri_reference_types.json)')
    cli = parser.parse_args()
    main(cli.src, cli.out, cli.reference, cli.formats, bundle=not cli.no_bundle)
