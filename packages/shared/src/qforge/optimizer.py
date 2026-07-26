from __future__ import annotations

from itertools import combinations
from time import perf_counter

from qforge.schemas import SolverResult, StatisticalResult


def select_portfolio(
    statistics: list[StatisticalResult], *, seed: int, maximum_size: int = 2
) -> SolverResult:
    started = perf_counter()
    ordered = sorted(statistics, key=lambda item: item.robustness_score, reverse=True)
    selected = [
        result.strategy_id
        for result in ordered[:maximum_size]
        if result.deployment_recommendation != "REJECT"
    ]
    objective = sum(
        result.robustness_score for result in statistics if result.strategy_id in selected
    )
    return SolverResult(
        solver="deterministic_ranked_subset",
        solution=selected,
        objective_score=objective,
        runtime_ms=(perf_counter() - started) * 1_000,
        iterations=len(statistics),
        constraint_violations=[],
        seed=seed,
        verified=True,
    )


def exhaustive_binary_selection(
    statistics: list[StatisticalResult], *, seed: int, maximum_size: int = 2
) -> SolverResult:
    started = perf_counter()
    best: tuple[str, ...] = ()
    best_score = 0.0
    iterations = 0
    for size in range(1, min(maximum_size, len(statistics)) + 1):
        for candidate in combinations(statistics, size):
            iterations += 1
            score = sum(result.robustness_score for result in candidate)
            if size > 1:
                score -= 0.04 * (size - 1)
            if score > best_score:
                best_score = score
                best = tuple(result.strategy_id for result in candidate)
    return SolverResult(
        solver="mock_qubo_exhaustive",
        solution=list(best),
        objective_score=best_score,
        runtime_ms=(perf_counter() - started) * 1_000,
        iterations=iterations,
        constraint_violations=[],
        seed=seed,
        verified=False,
    )
