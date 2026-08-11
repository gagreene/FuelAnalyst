import pandas as pd

from fuel_analyst import fbp_fuel_type


def test_process_fbp_fuel_type_merges_fuel_type_into_conpyro_output(tmp_path, monkeypatch):
    master_path, prep_path, conpyro_path = (
        tmp_path / 'master.csv', tmp_path / 'prep.csv', tmp_path / 'conpyro.csv'
    )
    pd.DataFrame({'unique_id': ['p1'], '_date': ['2025-01-01'], 'cc': [50]}).to_csv(master_path, index=False)
    pd.DataFrame({
        'unique_id': ['p1'], '_date': ['2025-01-01'], 'treatment_area': ['A'],
        'treatment_unit': ['U'], 'treatment_type': ['treated'], 'plot_id': ['1'],
        'SPECIES_CD_1': ['FDI'], 'BEC_Zone': ['IDF'],
    }).to_csv(prep_path, index=False)
    pd.DataFrame({'unique_id': ['p1'], 'fbp_fuel_type': [None]}).to_csv(conpyro_path, index=False)

    def fake_calc(df, season):
        assert season == 'Growing'
        df['fbp_fuel_type'] = 'C2'
        return df

    monkeypatch.setattr(fbp_fuel_type, '_calc_fbp_fuel_type', fake_calc)
    fbp_fuel_type.process_fbp_fuel_type(
        str(master_path), str(prep_path), str(conpyro_path), str(tmp_path), 'Growing'
    )

    result = pd.read_csv(tmp_path / 'conpyro_fbp.csv')
    assert result.loc[0, 'fbp_fuel_type'] == 'C2'


def test_process_fbp_fuel_type_preserves_existing_assignment(tmp_path, monkeypatch):
    master_path, prep_path, conpyro_path = tmp_path / 'master.csv', tmp_path / 'prep.csv', tmp_path / 'conpyro.csv'
    pd.DataFrame({'unique_id': ['p1'], '_date': ['2025-01-01']}).to_csv(master_path, index=False)
    pd.DataFrame({
        'unique_id': ['p1'], '_date': ['2025-01-01'], 'treatment_area': ['A'],
        'treatment_unit': ['U'], 'treatment_type': ['treated'], 'plot_id': ['1'],
        'SPECIES_CD_1': ['FDI'],
    }).to_csv(prep_path, index=False)
    pd.DataFrame({'unique_id': ['p1'], 'fbp_fuel_type': ['M1']}).to_csv(conpyro_path, index=False)
    monkeypatch.setattr(
        fbp_fuel_type, '_calc_fbp_fuel_type',
        lambda df, season: df.assign(fbp_fuel_type='C2'),
    )
    fbp_fuel_type.process_fbp_fuel_type(
        str(master_path), str(prep_path), str(conpyro_path), str(tmp_path), 'Growing'
    )
    assert pd.read_csv(tmp_path / 'conpyro_fbp.csv').loc[0, 'fbp_fuel_type'] == 'M1'
