from __future__ import annotations

from typing import Protocol

from qforge.optimizer import exhaustive_binary_selection
from qforge.schemas import SolverBenchmark, SolverResult, StatisticalResult


class QuantumBackend(Protocol):
    name: str
    verified: bool

    def solve(self, statistics: list[StatisticalResult], *, seed: int) -> SolverResult: ...


class MockQuantumBackend:
    name = "mock-qubo-exhaustive"
    verified = False

    def solve(self, statistics: list[StatisticalResult], *, seed: int) -> SolverResult:
        return exhaustive_binary_selection(statistics, seed=seed)


class ClassicalControlBackend:
    """Production fallback when no real quantum backend is configured."""

    name = "classical-exhaustive-control"
    verified = True

    def solve(self, statistics: list[StatisticalResult], *, seed: int) -> SolverResult:
        result = exhaustive_binary_selection(statistics, seed=seed)
        return result.model_copy(
            update={
                "solver": self.name,
                "verified": True,
            }
        )


def benchmark(
    classical: SolverResult,
    quantum: SolverResult,
) -> SolverBenchmark:
    solvers = {classical.solver: classical, quantum.solver: quantum}
    winner = max(solvers, key=lambda name: solvers[name].objective_score)
    return SolverBenchmark(
        problem="strategy_portfolio_selection",
        solvers=solvers,
        winner=winner,
        validation_required=not all(result.verified for result in solvers.values()),
    )
