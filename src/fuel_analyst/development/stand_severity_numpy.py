import numpy as np

def _calc_stand_ba_killed(unique_ids: np.ndarray,
                          tree_unique_ids: np.ndarray,
                          ba_live_ha: np.ndarray,
                          tree_dead_ba_crnsch: np.ndarray) -> (np.ndarray, np.ndarray, np.ndarray):
    """
    Calculate live stand basal area killed based on mortality probability.
    :param unique_ids: 1D array of stand unique IDs.
    :param tree_unique_ids: 1D array of tree unique IDs (same length as ba_live_ha).
    :param ba_live_ha: 1D array of tree live basal area.
    :param tree_dead_ba_crnsch: 1D array of tree dead basal area (CRNSCH).
    :return: Tuple of arrays (total_live_ba, dead_ba_crnsch, prop_dead_ba_crnsch) for each stand in unique_ids.
    """
    total_live_ba = np.array([ba_live_ha[tree_unique_ids == uid].sum() for uid in unique_ids])
    dead_ba_crnsch = np.array([tree_dead_ba_crnsch[tree_unique_ids == uid].sum() for uid in unique_ids])
    prop_dead_ba_crnsch = dead_ba_crnsch / total_live_ba
    return total_live_ba, dead_ba_crnsch, prop_dead_ba_crnsch


def _calc_severity_class(prop_dead_ba_crnsch: np.ndarray) -> np.ndarray:
    """
    Calculate stand-level fire severity based on proportion of basal area killed.
    0-20% = low, 20-70% = moderate, 70-100% = high (Agee, 1994).
    :param prop_dead_ba_crnsch: 1D array of proportion of dead basal area.
    :return: 1D array of fire severity class ('low', 'mod', 'high').
    """
    severity = np.full(prop_dead_ba_crnsch.shape, None, dtype=object)
    severity[(0 <= prop_dead_ba_crnsch) & (prop_dead_ba_crnsch <= 0.2)] = 'low'
    severity[(prop_dead_ba_crnsch > 0.2) & (prop_dead_ba_crnsch < 0.7)] = 'mod'
    severity[prop_dead_ba_crnsch >= 0.7] = 'high'
    return severity


def _calc_tree_mortality(prob_mortality_crnsch: np.ndarray,
                         ba_live_ha: np.ndarray) -> (np.ndarray, np.ndarray):
    """
    Calculate tree-level mortality using the CRNSCH model.
    :param prob_mortality_crnsch: 1D array of tree mortality probabilities.
    :param ba_live_ha: 1D array of tree live basal area.
    :return: Tuple of arrays (tree_dead_crnsch, tree_dead_ba_crnsch).
    """
    tree_dead_crnsch = (prob_mortality_crnsch > 0.5).astype(int)
    tree_dead_ba_crnsch = np.where(tree_dead_crnsch == 1, ba_live_ha, 0)
    return tree_dead_crnsch, tree_dead_ba_crnsch

