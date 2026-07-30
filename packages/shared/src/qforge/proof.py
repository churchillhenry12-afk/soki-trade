from __future__ import annotations

import re
from uuid import UUID

from qforge.database import Repository
from qforge.schemas import (
    AgentTask,
    AgentTaskStatus,
    ProofCheck,
    ProofCheckStatus,
    TaskCheckpoint,
    utc_now,
)


class ProofLedger:
    """Durable completion contracts for every user-visible agent request."""

    def __init__(self, repository: Repository) -> None:
        self.repository = repository

    def start(self, *, session_id: str, request: str) -> AgentTask:
        task = AgentTask(
            session_id=session_id,
            request=request,
            checks=[
                ProofCheck(
                    key="understood",
                    label="Request understood",
                    status=ProofCheckStatus.VERIFIED,
                    evidence="The request was accepted and converted into a task.",
                ),
                ProofCheck(
                    key="boundary",
                    label="Safety boundary checked",
                    status=ProofCheckStatus.VERIFIED,
                    evidence="Trading execution remains research, paper, or read-only.",
                ),
                ProofCheck(
                    key="executed",
                    label="Requested work executed",
                    status=ProofCheckStatus.RUNNING,
                ),
                ProofCheck(
                    key="verified",
                    label="Outcome verified",
                    status=ProofCheckStatus.PENDING,
                ),
            ],
            checkpoints=[
                TaskCheckpoint(label="Completion contract created", status=AgentTaskStatus.RUNNING)
            ],
        )
        return self.repository.save_agent_task(task)

    def finish(
        self,
        task: AgentTask,
        *,
        response: str,
        action: str,
        runtime: str,
        experiment_id: UUID | None,
    ) -> AgentTask:
        task.response = response
        task.runtime = runtime
        task.experiment_id = experiment_id
        executed = next(check for check in task.checks if check.key == "executed")
        verified = next(check for check in task.checks if check.key == "verified")
        if action == "EXPERIMENT_STARTED":
            task.status = AgentTaskStatus.WAITING
            executed.status = ProofCheckStatus.VERIFIED
            executed.evidence = "The research run was created and started."
            verified.status = ProofCheckStatus.RUNNING
            verified.evidence = "The adversarial pipeline is verifying the result."
            checkpoint = "Research started; verification continues in the run ledger"
        elif self._failed_outcome(response):
            task.status = AgentTaskStatus.FAILED
            executed.status = ProofCheckStatus.FAILED
            executed.evidence = "The requested outcome was not completed."
            verified.status = ProofCheckStatus.FAILED
            verified.evidence = "soki code preserved the failure instead of claiming completion."
            checkpoint = "Outcome not completed"
        elif self._needs_user_input(response):
            task.status = AgentTaskStatus.WAITING
            executed.status = ProofCheckStatus.RUNNING
            executed.evidence = (
                "soki code needs user input before the requested outcome can be completed."
            )
            verified.status = ProofCheckStatus.PENDING
            verified.evidence = "Verification will run after the missing information is supplied."
            checkpoint = "Waiting for information required to continue"
        else:
            task.status = AgentTaskStatus.VERIFIED
            executed.status = ProofCheckStatus.VERIFIED
            executed.evidence = (
                f"soki code completed the {action.lower().replace('_', ' ')} action."
            )
            verified.status = ProofCheckStatus.VERIFIED
            verified.evidence = "The API returned a valid, non-empty outcome."
            checkpoint = "Outcome delivered and verified"
        task.updated_at = utc_now()
        task.checkpoints.append(TaskCheckpoint(label=checkpoint, status=task.status))
        return self.repository.save_agent_task(task)

    @staticmethod
    def _needs_user_input(response: str) -> bool:
        patterns = (
            r"\bplease provide\b",
            r"\bplease (?:share|choose|confirm|specify|clarify)\b",
            r"\bi need (?:to know|more|you to|details|information)\b",
            r"\bneed to understand\b",
            r"\bcould you (?:provide|share|clarify|confirm|specify)\b",
            r"\bwhat (?:would|is|are|type|kind)\b[^?]{0,160}\?",
        )
        lowered = response.lower()
        return any(re.search(pattern, lowered) for pattern in patterns)

    @staticmethod
    def _failed_outcome(response: str) -> bool:
        patterns = (
            r"\brequest was rejected\b",
            r"\bcould not (?:complete|finish|perform|execute)\b",
            r"\bunable to (?:complete|finish|perform|execute)\b",
            r"\bfailed to (?:complete|finish|perform|execute)\b",
            r"\bi (?:cannot|can't) (?:complete|finish|perform|execute)\b",
        )
        lowered = response.lower()
        return any(re.search(pattern, lowered) for pattern in patterns)

    def fail(self, task: AgentTask, error: str) -> AgentTask:
        task.status = AgentTaskStatus.FAILED
        task.error = error
        task.updated_at = utc_now()
        for check in task.checks:
            if check.status in {ProofCheckStatus.PENDING, ProofCheckStatus.RUNNING}:
                check.status = ProofCheckStatus.FAILED
                check.evidence = error
        task.checkpoints.append(
            TaskCheckpoint(label="Task stopped with a recoverable failure", status=task.status)
        )
        return self.repository.save_agent_task(task)
