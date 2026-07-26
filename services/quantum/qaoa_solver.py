from qforge.schemas import SolverResult, StatisticalResult


def solve_qaoa(statistics: list[StatisticalResult], *, seed: int) -> SolverResult:
    del statistics, seed
    raise RuntimeError("QAOA is unavailable: install and verify a supported QPanda backend")
