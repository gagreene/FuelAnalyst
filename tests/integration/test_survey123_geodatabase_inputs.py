import uuid
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyogrio
import pytest

from fuel_analyst.fuel_analyst import fuel_analyst

DATE_COLUMNS = ('_date', 'CreationDate', 'EditDate')
COMPARED_OUTPUTS = [
    'master_fuel_df.csv', 'master_tree_df.csv', 'conpyro_df.csv', 'fbp_prep_df.csv',
    'fofem_consume_si_df.csv', 'fofem_gui_app_tree_mortality_df.csv', 'fuelanalyst_errors.csv',
]


def _guid(value):
    """A real GlobalID is a GUID; the example data uses descriptive parent IDs, so derive stable GUIDs."""
    if pd.isna(value):
        return None
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f'fuelanalyst-example:{value}'))


def _stems(form_dir):
    return sorted((p.stem for p in form_dir.glob('*.csv')), key=lambda s: int(s.rsplit('_', 1)[1]))


def _raw_table(csv_path):
    raw = pd.read_csv(csv_path, dtype=str, encoding='utf-8-sig')
    for column in ('GlobalID', 'ParentGlobalID'):
        if column in raw.columns:
            raw[column] = raw[column].map(_guid)
    return raw


def _gdb_table(raw, is_parent):
    """
    Convert one raw CSV table to an ArcGIS-style layer table (FID column, braced GUIDs, UTC dates).

    ``x`` and ``y`` are the point geometry when they are the last two CSV columns (ArcGIS appends them); when they sit
    mid-table (the plot form) they are real fields and stay as attributes as well.
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


def _plot_key(raw):
    return raw[['treatment_area', 'treatment_unit', 'treatment_type', 'plot_id']].fillna('').agg('|'.join, axis=1)


def _plot_coordinates(source_dir):
    """Each plot's coordinates from the parent tables that have x and y (a form without them reuses these)."""
    found = {}
    for form_dir in sorted(p for p in source_dir.iterdir() if p.is_dir()):
        raw = _raw_table(form_dir / 'survey_0.csv')
        if 'x' in raw.columns and 'y' in raw.columns:
            for key, x, y in zip(_plot_key(raw), pd.to_numeric(raw['x']), pd.to_numeric(raw['y'])):
                found.setdefault(key, (x, y))
    return found


def _write_forms(source_dir, csv_out, gdb_out):
    """Write GUID-mapped CSV copies and ArcGIS-style geodatabases (one per form) from the example CSV tables."""
    coordinates = _plot_coordinates(source_dir)
    for form_dir in sorted(p for p in source_dir.iterdir() if p.is_dir()):
        (csv_out / form_dir.name).mkdir(parents=True)
        (gdb_out / form_dir.name).mkdir(parents=True)
        gdb = gdb_out / form_dir.name / f'{uuid.uuid5(uuid.NAMESPACE_URL, form_dir.name)}.gdb'
        for stem in _stems(form_dir):
            raw = _raw_table(form_dir / f'{stem}.csv')
            raw.to_csv(csv_out / form_dir.name / f'{stem}.csv', index=False)
            layer, index = stem.rsplit('_', 1)
            table = _gdb_table(raw, int(index) == 0)
            if int(index) == 0:
                if 'x' in raw.columns:
                    x, y = pd.to_numeric(raw['x']), pd.to_numeric(raw['y'])
                else:
                    pairs = _plot_key(raw).map(coordinates)
                    x, y = pairs.map(lambda p: p[0]), pairs.map(lambda p: p[1])
                frame = gpd.GeoDataFrame(table, geometry=gpd.points_from_xy(x, y), crs='EPSG:4326')
                frame.geometry.name = 'SHAPE'
                pyogrio.write_dataframe(frame, str(gdb), layer=layer, driver='OpenFileGDB', geometry_type='Point',
                                        layer_options={'FID': 'objectid', 'GEOMETRY_NAME': 'SHAPE'})
            else:
                pyogrio.write_dataframe(table, str(gdb), layer=layer, driver='OpenFileGDB', layer_options={'FID': 'objectid'})


def _read_output(path):
    df = pd.read_csv(path, low_memory=False)
    for column in df.columns:
        if column in DATE_COLUMNS or column.endswith('_date'):
            df[column] = pd.to_datetime(df[column], format='mixed', errors='coerce')
    return df


@pytest.mark.integration
@pytest.mark.slow
def test_geodatabase_inputs_give_the_same_pipeline_outputs_as_csv_inputs(tmp_path):
    project_root = Path(__file__).resolve().parents[2]
    csv_dir, gdb_dir = tmp_path / 'csv_in', tmp_path / 'gdb_in'
    _write_forms(project_root / 'examples' / 'data' / 'Survey123_Data', csv_dir, gdb_dir)
    assert not list(gdb_dir.rglob('*.csv'))

    outputs = {}
    for label, source in (('csv', csv_dir), ('gdb', gdb_dir)):
        out_dir = tmp_path / f'out_{label}'
        fuel_analyst(
            in_dir=str(source),
            out_dir=str(out_dir),
            surface_fire_intensity_model='Byram',
            gen_conpyro_df=True,
            gen_fofem_gui_app_tree_df=True,
            gen_fofem_consume_df=True,
        )
        outputs[label] = out_dir

    for name in COMPARED_OUTPUTS:
        expected = _read_output(outputs['csv'] / name)
        actual = _read_output(outputs['gdb'] / name)
        pd.testing.assert_frame_equal(actual, expected, obj=name)
