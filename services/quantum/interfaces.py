from typing import Protocol

from qforge.schemas import SolverResult, StatisticalResult


class QuantumSolver(Protocol):
    name: str
    verified: bool

    def solve(self, statistics: list[StatisticalResult], *, seed: int) -> SolverResult: ...
