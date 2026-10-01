"""Behavior of stand-summary selection across permutation modes."""

import pandas as pd
import pytest

from fuel_analyst.components.trees import _calc_stand_attributes
from fuel_analyst.fuel_analyst import fuel_analyst


def _calculate_summaries(summary: list[str], mode: str) -> tuple[pd.DataFrame, list[str]]:
    plot_df = pd.DataFrame({'GlobalID': ['plot-1']})
    tree_df = pd.DataFrame({
        'ParentGlobalID': ['plot-1'] * 4,
        'tree_status': ['L', 'L', 'D', 'D'],
        'tree_type': ['conifer', 'broadleaf', 'conifer', 'broadleaf'],
        'tree_dens_ha': [1, 1, 1, 1],
    })
    params = {'dens': {
        'att_source': 'dens',
        'summary': summary,
        'summary_permutation': mode,
        'metrics': ['sum'],
        'units': 'tpha',
    }}
    return _calc_stand_attributes(plot_df, tree_df, params)


@pytest.mark.parametrize(
    ('summary', 'suffix', 'expected'),
    [
        (['live'], 'live', 2),
        (['dead'], 'dead', 2),
        (['conifer'], 'conifer', 2),
        (['broadleaf'], 'broadleaf', 2),
        (['live', 'conifer'], 'live_conifer', 1),
        (['live', 'broadleaf'], 'live_broadleaf', 1),
        (['dead', 'conifer'], 'dead_conifer', 1),
        (['dead', 'broadleaf'], 'dead_broadleaf', 1),
        (['live', 'dead'], 'total', 4),
        (['conifer', 'broadleaf'], 'total', 4),
        (['live', 'dead', 'conifer'], 'conifer', 2),
        (['live', 'dead', 'broadleaf'], 'broadleaf', 2),
        (['live', 'conifer', 'broadleaf'], 'live', 2),
        (['dead', 'conifer', 'broadleaf'], 'dead', 2),
        (['live', 'dead', 'conifer', 'broadleaf'], 'total', 4),
    ],
)
def test_combined_permutation_covers_every_non_total_subset(
        summary: list[str], suffix: str, expected: int
) -> None:
    result, columns = _calculate_summaries(summary, 'combined')
    column = f'stand_dens_tpha_{suffix}_sum'.replace('_total', '')

    assert columns == [column]
    assert result.loc[0, column] == expected


def test_combined_permutation_drops_total_without_mutating_input() -> None:
    summary = ['total', 'live', 'conifer']

    result, columns = _calculate_summaries(summary, 'combined')

    assert summary == ['total', 'live', 'conifer']
    assert columns == ['stand_dens_tpha_live_conifer_sum']
    assert result.loc[0, columns[0]] == 1


def test_combined_permutation_rejects_total_only(caplog) -> None:
    with pytest.raises(ValueError, match="requires at least one summary other than 'total'"):
        _calculate_summaries(['total'], 'combined')

    assert any(
        record.issue_code == 'combined_summary_total_only'
        for record in caplog.records
    )


def test_combined_permutation_with_both_broadleaf_statuses_selects_broadleaf() -> None:
    result, columns = _calculate_summaries(
        ['live', 'broadleaf', 'dead', 'broadleaf'], 'combined'
    )

    assert columns == ['stand_dens_tpha_broadleaf_sum']
    assert result.loc[0, columns[0]] == 2


def test_combined_permutation_with_both_conifer_statuses_selects_conifer() -> None:
    result, columns = _calculate_summaries(
        ['live', 'conifer', 'dead', 'conifer'], 'combined'
    )

    assert columns == ['stand_dens_tpha_conifer_sum']
    assert result.loc[0, columns[0]] == 2


def test_fuel_analyst_reports_total_only_combined_before_processing(tmp_path) -> None:
    out_dir = tmp_path / 'results'
    params = {'dens': {
        'summary': ['total'],
        'summary_permutation': 'combined',
    }}

    with pytest.raises(ValueError, match="requires at least one summary other than 'total'"):
        fuel_analyst(str(tmp_path / 'missing-input'), str(out_dir), 'Byram',
                     stand_summary_params=params)

    report = pd.read_csv(out_dir / 'fuelanalyst_errors.csv')
    assert report['unique_id'].tolist() == ['General Error']
    assert "for: dens" in report.loc[0, 'Trees']


@pytest.mark.parametrize('mode', ['all', 'exact'])
def test_noncombined_permutations_keep_total(mode: str) -> None:
    result, columns = _calculate_summaries(['total', 'live'], mode)

    assert columns == ['stand_dens_tpha_sum', 'stand_dens_tpha_live_sum']
    assert result.loc[0, 'stand_dens_tpha_sum'] == 4
    assert result.loc[0, 'stand_dens_tpha_live_sum'] == 2
