from qforge.schemas import ExperimentState

ACTIVE_SEQUENCE = (
    ExperimentState.PLANNING,
    ExperimentState.GENERATING,
    ExperimentState.BACKTESTING,
    ExperimentState.CRITICIZING,
    ExperimentState.ADVERSARIAL_TESTING,
    ExperimentState.STATISTICAL_VALIDATION,
    ExperimentState.OPTIMIZING,
    ExperimentState.QUANTUM_OPTIMIZING,
    ExperimentState.RISK_REVIEW,
)

TERMINAL_STATES = {
    ExperimentState.REJECTED,
    ExperimentState.FAILED,
    ExperimentState.CANCELLED,
    ExperimentState.COMPLETED,
}

TRANSITIONS: dict[ExperimentState, set[ExperimentState]] = {
    ExperimentState.CREATED: {ExperimentState.PLANNING, ExperimentState.CANCELLED},
    ExperimentState.PLANNING: {ExperimentState.GENERATING},
    ExperimentState.GENERATING: {ExperimentState.BACKTESTING},
    ExperimentState.BACKTESTING: {ExperimentState.CRITICIZING},
    ExperimentState.CRITICIZING: {ExperimentState.ADVERSARIAL_TESTING},
    ExperimentState.ADVERSARIAL_TESTING: {ExperimentState.STATISTICAL_VALIDATION},
    ExperimentState.STATISTICAL_VALIDATION: {ExperimentState.OPTIMIZING},
    ExperimentState.OPTIMIZING: {ExperimentState.QUANTUM_OPTIMIZING},
    ExperimentState.QUANTUM_OPTIMIZING: {ExperimentState.RISK_REVIEW},
    ExperimentState.RISK_REVIEW: {
        ExperimentState.AWAITING_HUMAN_APPROVAL,
        ExperimentState.REJECTED,
    },
    ExperimentState.AWAITING_HUMAN_APPROVAL: {
        ExperimentState.APPROVED_FOR_PAPER,
        ExperimentState.APPROVED_FOR_DEMO,
        ExperimentState.CANCELLED,
    },
    ExperimentState.APPROVED_FOR_PAPER: {ExperimentState.COMPLETED},
    ExperimentState.APPROVED_FOR_DEMO: {ExperimentState.COMPLETED},
    ExperimentState.PAUSED: set(ACTIVE_SEQUENCE),
}


class InvalidTransitionError(ValueError):
    pass


def ensure_transition(current: ExperimentState, target: ExperimentState) -> None:
    if (
        target in {ExperimentState.FAILED, ExperimentState.CANCELLED}
        and current not in TERMINAL_STATES
    ):
        return
    if target == ExperimentState.PAUSED and current in ACTIVE_SEQUENCE:
        return
    if target not in TRANSITIONS.get(current, set()):
        raise InvalidTransitionError(f"invalid experiment transition: {current} -> {target}")
