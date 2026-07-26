from __future__ import annotations

import numpy as np
from qforge.schemas import StatisticalResult


def build_portfolio_qubo(
    statistics: list[StatisticalResult], *, cardinality_penalty: float = 0.04
) -> np.ndarray:
    size = len(statistics)
    matrix = np.zeros((size, size), dtype=float)
    for index, result in enumerate(statistics):
        matrix[index, index] = -result.robustness_score
    for left in range(size):
        for right in range(left + 1, size):
            matrix[left, right] = cardinality_penalty
            matrix[right, left] = cardinality_penalty
    return matrix
