from pathlib import Path

import openpyxl
import pandas as pd
import pytest

from fuel_analyst.fuel_analyst import fuel_analyst

DATE_COLUMNS = ('_date', 'CreationDate', 'EditDate')
COMPARED_OUTPUTS = [
    'master_fuel_df.csv', 'master_tree_df.csv', 'conpyro_df.csv', 'fbp_prep_df.csv',
    'fofem_consume_si_df.csv', 'fofem_gui_app_tree_mortality_df.csv', 'fuelanalyst_errors.csv',
]


def _csv_form_to_workbook(form_dir, out_form_dir):
    """Write one form's CSV tables as an ArcGIS-style workbook (one sheet per table, real date cells)."""
    out_form_dir.mkdir(parents=True)
    book = openpyxl.Workbook()
    book.remove(book.active)
    stems = sorted((p.stem for p in form_dir.glob('*.csv')), key=lambda s: int(s.rsplit('_', 1)[1]))
    for stem in stems:
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


def _read_output(path):
    df = pd.read_csv(path, low_memory=False)
    for column in df.columns:
        if column in DATE_COLUMNS or column.endswith('_date'):
            df[column] = pd.to_datetime(df[column], format='mixed', errors='coerce')
    return df


@pytest.mark.integration
@pytest.mark.slow
def test_excel_inputs_give_the_same_pipeline_outputs_as_csv_inputs(tmp_path):
    project_root = Path(__file__).resolve().parents[2]
    csv_dir = project_root / 'examples' / 'data' / 'Survey123_Data'
    excel_dir = tmp_path / 'excel_in'
    for form_dir in sorted(p for p in csv_dir.iterdir() if p.is_dir()):
        _csv_form_to_workbook(form_dir, excel_dir / form_dir.name)
    assert not list(excel_dir.rglob('*.csv'))

    outputs = {}
    for label, source in (('csv', csv_dir), ('excel', excel_dir)):
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
        actual = _read_output(outputs['excel'] / name)
        pd.testing.assert_frame_equal(actual, expected, obj=name)
