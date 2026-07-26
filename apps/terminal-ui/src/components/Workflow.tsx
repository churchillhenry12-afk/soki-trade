import type { ExperimentEvent } from "../types";

const STAGES = [
  ["DIRECTOR", "PLANNING"],
  ["BUILDER", "GENERATING"],
  ["BACKTEST", "BACKTESTING"],
  ["CRITIC", "CRITICIZING"],
  ["ADVERSARY", "ADVERSARIAL_TESTING"],
  ["STATS", "STATISTICAL_VALIDATION"],
  ["CLASSICAL", "OPTIMIZING"],
  ["QUBO", "QUANTUM_OPTIMIZING"],
  ["RISK", "RISK_REVIEW"],
  ["APPROVAL", "AWAITING_HUMAN_APPROVAL"],
] as const;

export function Workflow({
  state,
  events,
}: {
  state: string;
  events: ExperimentEvent[];
}) {
  const currentIndex = STAGES.findIndex(([, stage]) => stage === state);
  const latest = events.at(-1);
  return (
    <div className="workflow" aria-label="Agent workflow">
      {STAGES.map(([label, stage], index) => {
        const isActive = state === stage;
        const isPast = currentIndex > index || ["REJECTED", "COMPLETED"].includes(state);
        return (
          <div className="workflow__stage" key={stage}>
            <div className={`workflow__node ${isActive ? "is-active" : ""} ${isPast ? "is-past" : ""}`}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <strong>{label}</strong>
              <small>{isActive ? "EXEC" : isPast ? "DONE" : "IDLE"}</small>
            </div>
            {index < STAGES.length - 1 ? <div className="workflow__link">···›</div> : null}
          </div>
        );
      })}
      <div className="workflow__readout">
        <span>STATE::{state}</span>
        <span>{latest ? latest.event_type : "NO_ACTIVE_SIGNAL"}</span>
      </div>
    </div>
  );
}

