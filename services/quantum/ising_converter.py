from __future__ import annotations

import numpy as np


def qubo_to_ising(qubo: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
    if qubo.ndim != 2 or qubo.shape[0] != qubo.shape[1]:
        raise ValueError("QUBO must be a square matrix")
    symmetric = (qubo + qubo.T) / 2
    coupling = symmetric / 4
    field = symmetric.sum(axis=1) / 2
    offset = float(symmetric.sum() / 4)
    return coupling, field, offset
