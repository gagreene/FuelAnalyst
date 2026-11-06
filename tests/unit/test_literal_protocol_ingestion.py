import json
import sqlite3

import pandas as pd
import pytest

from fuel_analyst.components import table_reader


FORMATS = ['csv', 'excel', 'parquet', 'feather', 'sqlite', 'geojson', 'gpkg', 'gdb']


def _write(folder, frame, kind):
    folder.mkdir()
    if kind in ('parquet', 'feather'):
        pytest.importorskip('pyarrow')
    if kind == 'csv':
        frame.to_csv(folder / 'survey_0.csv', index=False)
    elif kind == 'excel':
        frame.to_excel(folder / 'form.xlsx', sheet_name='survey_0', index=False)
    elif kind == 'parquet':
        frame.to_parquet(folder / 'survey_0.parquet', index=False)
    elif kind == 'feather':
        frame.to_feather(folder / 'survey_0.feather')
    elif kind == 'sqlite':
        with sqlite3.connect(folder / 'form.sqlite') as connection:
            frame.to_sql('survey_0', connection, index=False)
    elif kind == 'geojson':
        records = frame.where(frame.notna(), None).to_dict('records')
        features = [{'type': 'Feature', 'geometry': None, 'properties': row} for row in records]
        (folder / 'survey_0.geojson').write_text(json.dumps({'type': 'FeatureCollection', 'features': features}))
    else:
        import pyogrio
        driver = 'GPKG' if kind == 'gpkg' else 'OpenFileGDB'
        pyogrio.write_dataframe(frame, folder / f'form.{kind}', layer='survey', driver=driver)


@pytest.mark.parametrize('missing', [None, pd.NA, float('nan')])
def test_literal_normalization_preserves_nulls_dates_and_row_positions(missing):
    frame = pd.DataFrame({'protocol': ['001', missing], 'measurement': ['001', 'NA'],
                          '_date': pd.to_datetime(['2025-01-01', None])}, index=[4, 7])
    before = frame.copy(deep=True)
    result = table_reader._as_csv_would(frame, literal_text_columns=('protocol',))
    assert result.protocol.iloc[0] == '001' and pd.isna(result.protocol.iloc[1])
    assert result.measurement.iloc[0] == 1 and pd.isna(result.measurement.iloc[1])
    assert result['_date'].iloc[0] == pd.Timestamp('2025-01-01')
    assert pd.isna(result['_date'].iloc[1])
    assert pd.api.types.is_datetime64_any_dtype(result['_date'])
    pd.testing.assert_frame_equal(frame, before)


def test_literal_text_does_not_invent_an_absent_column(tmp_path):
    _write(tmp_path / 'csv', pd.DataFrame({'value': [1]}), 'csv')
    result = table_reader.read_table(str(tmp_path / 'csv'), 'survey_0', literal_text_columns=('absent',))
    assert result.to_dict('records') == [{'value': 1}]


@pytest.mark.parametrize('kind', FORMATS)
@pytest.mark.parametrize('labels', [['001', '002'], ['NA', 'NULL', 'NaN', 'N/A'], [' NFI', 'NFI ', 'nfi', '']])
def test_literal_text_survives_all_reader_normalization(tmp_path, kind, labels):
    frame = pd.DataFrame({'GlobalID': [f'p{i}' for i in range(len(labels))], 'protocol': labels,
                          'measurement': ['001'] + ['NA'] * (len(labels) - 1)})
    folder = tmp_path / kind
    _write(folder, frame, kind)
    ordinary = table_reader.read_table(str(folder), 'survey_0')
    literal = table_reader.read_table(str(folder), 'survey_0', literal_text_columns=('protocol',))
    assert literal.protocol.fillna('').tolist() == labels
    pd.testing.assert_frame_equal(literal.drop(columns='protocol'), ordinary.drop(columns='protocol'))
    assert literal.measurement.iloc[0] == 1
    assert literal.measurement.iloc[1:].isna().all()
