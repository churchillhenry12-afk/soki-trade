# Soki Trade Architecture

## Scope

The first milestone is a deployable modular monolith that proves one complete,
observable research path. Service boundaries are Python modules with typed
contracts. They may be extracted into separate processes without changing those
contracts. Live execution is not present.

## Runtime topology

```text
React terminal UI
  | REST + WebSocket
FastAPI API
  | Experiment state machine
HermesAdapter (MockHermesAdapter in milestone one)
  | typed requests only
Deterministic research services
  |- strategy DSL validation
  |- market-data adapter
  |- event-driven backtester
  |- critic/adversarial/statistics engines
  |- classical + mock-quantum benchmark
  `- immutable risk governor
```

The local profile persists metadata to SQLite and runs work in an in-process
async worker so it works on macOS without Docker. The production profile is
designed for PostgreSQL, Redis, and Celery. `docker-compose.yml` defines those
dependencies, but Docker is not installed on the detected development machine.

## Trust boundaries

- Hermes proposes research operations; it never computes trading metrics.
- Every LLM-originated strategy passes through the Pydantic strategy DSL.
- Market data is only exposed as the current and past bar to the simulator.
- Orders fill on the next bar. If stop and target are both touched in a bar,
  the stop is applied first.
- Risk approval is a pure deterministic function over validated evidence.
- Human approval is separate from risk approval and cannot turn a rejection
  into an approval.
- Deployment can export only PAPER or MT5_DEMO artifacts.
- `LIVE_DISABLED` is a compile-time application default and an immutable risk
  rejection rule.

## State machine

```text
CREATED -> PLANNING -> GENERATING -> BACKTESTING -> CRITICIZING
 -> ADVERSARIAL_TESTING -> STATISTICAL_VALIDATION -> OPTIMIZING
 -> QUANTUM_OPTIMIZING -> RISK_REVIEW
 -> AWAITING_HUMAN_APPROVAL | REJECTED | FAILED
 -> APPROVED_FOR_PAPER | APPROVED_FOR_DEMO -> COMPLETED
```

Any active state can be paused, resumed, cancelled, or failed. Retrying creates
an auditable new run. Branch experiments record a parent experiment identifier.

## Persistence model

The production schema is versioned with Alembic and includes:

`users`, `projects`, `research_objectives`, `experiments`,
`experiment_events`, `agent_runs`, `agent_messages`, `strategies`,
`strategy_versions`, `backtests`, `trades`, `metrics`, `adversarial_tests`,
`statistical_tests`, `optimization_runs`, `quantum_jobs`,
`solver_benchmarks`, `risk_reviews`, `approvals`, `deployments`,
`mt5_accounts`, `audit_logs`, and `system_settings`.

Each important record carries UTC timestamps, actor, agent, correlation ID,
experiment ID, status, and a JSON payload where applicable.

## Hermes extension point

Hermes source was not found in the workspace. `HermesAdapter` is therefore the
only integration seam in milestone one. A real integration must implement the
same typed methods and may call Hermes skills, tools, MCP servers, memory, and
agent definitions. No assumption is made about Hermes internals.

The specialist registry defines Research Director, Strategy Builder,
Backtester, Critic, Adversary, Statistician, Optimizer, Quantum Optimizer, Risk
Governor, Deployment Controller, Reporter, and Memory. Their permissions and
retry limits are data, not prompt text.

## Event contract

Every workflow transition emits an `ExperimentEvent` containing a monotonic
sequence, UTC timestamp, experiment and correlation identifiers, agent, event
type, state, status, and structured payload. The same persisted events feed the
REST history and WebSocket stream, so production mode never invents UI activity.
