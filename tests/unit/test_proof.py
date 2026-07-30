from qforge.database import Repository
from qforge.proof import ProofLedger
from qforge.schemas import AgentTaskStatus, ProofCheckStatus


def test_proof_ledger_does_not_claim_completion_while_waiting_for_input(tmp_path) -> None:
    ledger = ProofLedger(Repository(f"sqlite:///{tmp_path / 'proof.db'}"))
    task = ledger.start(session_id="session-1", request="Build a launch checklist")

    result = ledger.finish(
        task,
        response="I need more information. Please provide the product and launch date.",
        action="MESSAGE",
        runtime="hermes-agent",
        experiment_id=None,
    )

    assert result.status == AgentTaskStatus.WAITING
    executed = next(check for check in result.checks if check.key == "executed")
    verified = next(check for check in result.checks if check.key == "verified")
    assert executed.status == ProofCheckStatus.RUNNING
    assert verified.status == ProofCheckStatus.PENDING


def test_proof_ledger_preserves_a_failed_outcome(tmp_path) -> None:
    ledger = ProofLedger(Repository(f"sqlite:///{tmp_path / 'failed-proof.db'}"))
    task = ledger.start(session_id="session-2", request="Complete this task")

    result = ledger.finish(
        task,
        response="The request was rejected because it was considered high risk.",
        action="MESSAGE",
        runtime="hermes-agent",
        experiment_id=None,
    )

    assert result.status == AgentTaskStatus.FAILED
    assert all(
        check.status == ProofCheckStatus.FAILED
        for check in result.checks
        if check.key in {"executed", "verified"}
    )
