"""
Helpers for the multi-format Survey123 integration tests.

They build ArcGIS-style Excel workbooks and file geodatabases from the example CSV tables, run the whole pipeline on any
input folder, and compare the written outputs.
"""
import contextlib
import io
import sqlite3
import uuid
from pathlib import Path

import geopandas as gpd
import openpyxl
import pandas as pd
import pyogrio

from fuel_analyst.fuel_analyst import fuel_analyst

DATE_COLUMNS = ('_date', 'CreationDate', 'EditDate')
COMPARED_OUTPUTS = [
    'master_fuel_df.csv', 'master_tree_df.csv', 'conpyro_df.csv', 'fbp_prep_df.csv',
    'fofem_consume_si_df.csv', 'fofem_gui_app_tree_mortality_df.csv', 'fuelanalyst_errors.csv',
]


def csv_files(out_dir):
    """Sorted relative paths of every CSV a run wrote (results and the processed copies of the input tables)."""
    return sorted(str(p.relative_to(out_dir)) for p in Path(out_dir).rglob('*.csv'))


def csv_form_to_workbook(form_dir, out_form_dir):
    """Write one form's CSV tables as an ArcGIS-style workbook (one sheet per table, real date cells)."""
    out_form_dir.mkdir(parents=True)
    book = openpyxl.Workbook()
    book.remove(book.active)
    for stem in table_stems(form_dir):
        df = pd.read_csv(form_dir / f'{stem}.csv', low_memory=False)
        for column in DATE_COLUMNS:
            if column in df.columns:
                df[column] = pd.to_datetime(df[column], format='mixed', errors='coerce')
        sheet = book.create_sheet(stem)
        sheet.append(list(df.columns))
        for row in df.itertuples(index=False):
            sheet.append([
                None if pd.isna(v) else (v.to_pydatetime() if isinstance(v, pd.Timestamp) else
                                         (v.item() if hasattr(v, 'item') else v))
                for v in row
            ])
    book.save(out_form_dir / f'S123_{form_dir.name}_EXCEL.xlsx')


def example_dir():
    """The checked-in example Survey123 dataset."""
    return Path(__file__).resolve().parents[2] / 'examples' / 'data' / 'Survey123_Data'


def form_dirs(root):
    """Sorted form folders of a Survey123 input folder."""
    return sorted(p for p in Path(root).iterdir() if p.is_dir())


def guid(value):
    """A real GlobalID is a GUID; the example data uses descriptive parent IDs, so derive stable GUIDs."""
    if pd.isna(value):
        return None
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f'fuelanalyst-example:{value}'))


def plot_coordinates(source_dir):
    """Each plot's coordinates from the parent tables that have x and y (a form without them reuses these)."""
    found = {}
    for form_dir in form_dirs(source_dir):
        raw = raw_table(form_dir / 'survey_0.csv')
        if 'x' in raw.columns and 'y' in raw.columns:
            for key, x, y in zip(plot_key(raw), pd.to_numeric(raw['x']), pd.to_numeric(raw['y'])):
                found.setdefault(key, (x, y))
    return found


def plot_key(raw):
    return raw[['treatment_area', 'treatment_unit', 'treatment_type', 'plot_id']].fillna('').agg('|'.join, axis=1)


def raw_table(csv_path):
    """Read a CSV table as text with GlobalIDs mapped to GUIDs."""
    raw = pd.read_csv(csv_path, dtype=str, encoding='utf-8-sig')
    for column in ('GlobalID', 'ParentGlobalID'):
        if column in raw.columns:
            raw[column] = raw[column].map(guid)
    return raw


def read_output(path):
    """Read an output CSV, parsing date columns so text formats do not matter."""
    df = pd.read_csv(path, low_memory=False)
    for column in df.columns:
        if column in DATE_COLUMNS or column.endswith('_date'):
            df[column] = pd.to_datetime(df[column], format='mixed', errors='coerce')
    return df


def run_pipeline(in_dir, out_dir):
    """Run fuel_analyst() with every optional table on, and return the output folder."""
    fuel_analyst(
        in_dir=str(in_dir),
        out_dir=str(out_dir),
        surface_fire_intensity_model='Byram',
        gen_conpyro_df=True,
        gen_fofem_gui_app_tree_df=True,
        gen_fofem_consume_df=True,
    )
    return Path(out_dir)


def table_stems(form_dir):
    """CSV table names of a form, ordered by table index."""
    return sorted((p.stem for p in Path(form_dir).glob('*.csv')), key=lambda s: int(s.rsplit('_', 1)[1]))


def write_forms(source_dir, csv_out, gdb_out):
    """Write GUID-mapped CSV copies and ArcGIS-style geodatabases (one per form) from the example CSV tables."""
    write_formats(source_dir, {'csv': csv_out, 'gdb': gdb_out})


def write_formats(source_dir, roots):
    """
    Write the example tables in several formats, one folder per form under each format's root folder.

    The data are GUID-mapped copies of the example tables. ``roots`` maps a format to its output root:
    'csv', 'parquet', 'feather', 'geojson' (one file per table; GeoJSON holds the parent table as points and the repeat
    tables as features without geometry), 'gdb' (one ``<guid>.gdb`` per form, layers without the table
    number), 'gpkg' (one GeoPackage per form, same layers), and 'sqlite' (one plain database per form, with x and y
    columns and dates as ISO text).
    """
    coordinates = plot_coordinates(source_dir)
    for form_dir in form_dirs(source_dir):
        outs = {fmt: root / form_dir.name for fmt, root in roots.items()}
        for out in outs.values():
            out.mkdir(parents=True)
        connection = sqlite3.connect(outs['sqlite'] / f'{form_dir.name}.sqlite') if 'sqlite' in outs else None
        with contextlib.ExitStack() as stack:
            if connection is not None:
                stack.enter_context(contextlib.closing(connection))
            for stem in table_stems(form_dir):
                raw = raw_table(form_dir / f'{stem}.csv')
                typed = _typed_table(raw)
                if 'csv' in outs:
                    raw.to_csv(outs['csv'] / f'{stem}.csv', index=False)
                if 'parquet' in outs:
                    typed.to_parquet(outs['parquet'] / f'{stem}.parquet', index=False)
                if 'feather' in outs:
                    typed.to_feather(outs['feather'] / f'{stem}.feather')
                if 'geojson' in outs:
                    geometry_only = list(raw.columns[-2:]) == ['x', 'y']
                    props = typed.drop(columns=['x', 'y']) if geometry_only else typed
                    if int(stem.rsplit('_', 1)[1]) == 0:
                        x, y = _parent_xy(raw, coordinates)
                        geometry = gpd.points_from_xy(x, y)
                    else:
                        geometry = [None] * len(props)
                    gpd.GeoDataFrame(props, geometry=geometry, crs='EPSG:4326').to_file(
                        outs['geojson'] / f'{stem}.geojson', driver='GeoJSON')
                if connection is not None:
                    iso = typed.copy()
                    for column in DATE_COLUMNS:
                        if column in iso.columns:
                            iso[column] = iso[column].dt.strftime('%Y-%m-%d %H:%M:%S')
                    iso.to_sql(stem, connection, index=False)
                layer, index = stem.rsplit('_', 1)
                for fmt, driver, fid, target in (
                        ('gdb', 'OpenFileGDB', 'objectid', outs.get('gdb') and outs['gdb'] / f'{uuid.uuid5(uuid.NAMESPACE_URL, form_dir.name)}.gdb'),
                        ('gpkg', 'GPKG', 'fid', outs.get('gpkg') and outs['gpkg'] / f'{form_dir.name}.gpkg')):
                    if fmt not in outs:
                        continue
                    table = _gdb_table(raw).rename(columns={'objectid': fid})
                    if int(index) == 0:
                        x, y = _parent_xy(raw, coordinates)
                        frame = gpd.GeoDataFrame(table, geometry=gpd.points_from_xy(x, y), crs='EPSG:4326')
                        frame.geometry.name = 'SHAPE'
                        pyogrio.write_dataframe(frame, str(target), layer=layer, driver=driver, geometry_type='Point',
                                                layer_options={'FID': fid, 'GEOMETRY_NAME': 'SHAPE'})
                    else:
                        pyogrio.write_dataframe(table, str(target), layer=layer, driver=driver, layer_options={'FID': fid})


def _parent_xy(raw, coordinates):
    """x and y of a parent table: its own columns, or (for a form without them) the plot form's coordinates."""
    if 'x' in raw.columns:
        return pd.to_numeric(raw['x']), pd.to_numeric(raw['y'])
    pairs = plot_key(raw).map(coordinates)
    return pairs.map(lambda p: p[0]), pairs.map(lambda p: p[1])


def _typed_table(raw):
    """A raw text table with the dtypes pd.read_csv infers and real datetimes in the date columns."""
    typed = pd.read_csv(io.StringIO(raw.to_csv(index=False)), low_memory=False)
    for column in DATE_COLUMNS:
        if column in typed.columns:
            typed[column] = pd.to_datetime(typed[column], format='mixed', errors='coerce')
    return typed


def _gdb_table(raw):
    """
    Convert one raw CSV table to an ArcGIS-style layer table (FID column, braced GUIDs, UTC dates).

    ``x`` and ``y`` are the point geometry when they are the last two CSV columns (ArcGIS appends them); when they sit
    mid-table (the plot form) they are real fields, so they stay as attributes as well.
    """
    table = pd.DataFrame({'objectid': raw['ObjectID'].astype('int32')})
    geometry_only = list(raw.columns[-2:]) == ['x', 'y']
    for column in raw.columns:
        if column == 'ObjectID' or (geometry_only and column in ('x', 'y')):
            continue
        name = {'GlobalID': 'globalid', 'ParentGlobalID': 'parentglobalid'}.get(column, column)
        if column in DATE_COLUMNS:
            table[name] = pd.to_datetime(raw[column], format='mixed', errors='coerce').dt.tz_localize('UTC')
        elif column in ('GlobalID', 'ParentGlobalID'):
            table[name] = raw[column].map(lambda v: None if pd.isna(v) else '{' + v.upper() + '}')
        else:
            numeric = pd.to_numeric(raw[column].dropna(), errors='coerce')
            if len(numeric) and numeric.notna().all():
                whole = (numeric == numeric.round()).all() and not raw[column].dropna().str.contains(r'[.eE]').any()
                table[name] = pd.to_numeric(raw[column], errors='coerce').astype('Int32' if whole else 'float64')
            else:
                table[name] = raw[column].astype(object).where(raw[column].notna(), None)
    return table
