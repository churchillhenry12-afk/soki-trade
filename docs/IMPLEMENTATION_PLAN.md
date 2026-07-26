# Implementation Plan

## Milestone 1 — complete research slice

- Typed strategy DSL and specialist permissions
- Mock Hermes research director and strategy builder
- Deterministic synthetic OHLCV adapter
- Event-driven, next-bar-fill backtester
- Critic and spread/slippage adversarial tests
- Deterministic robustness statistics
- Classical subset selection and mock QUBO benchmark
- Immutable risk review and mandatory human approval boundary
- FastAPI REST/OpenAPI and WebSocket events
- React fire-terminal with objective input and final report inspection
- Unit, integration, frontend, lint, type, and startup checks

## Milestone 2 — durable orchestration

- PostgreSQL repository and full Alembic mappings
- Redis/Celery worker with task leases and idempotent retries
- Authentication and project tenancy
- Walk-forward, bootstrap, Monte Carlo, and multiple-testing modules
- Branching experiments and replay from persisted events

## Milestone 3 — external integrations

- Connect the real Hermes repository through `HermesAdapter`
- Deploy the signed MT5 bridge to a Windows demo terminal
- Validate QPanda locally and add Origin adapters behind feature flags
- Add paper-trading reconciliation and deployment rollback

## Definition of done for milestone 1

One command starts the mock stack. A browser user can submit an objective and
watch real backend events reach a terminal UI. The pipeline returns validated
strategies, backtest evidence, attacks, robustness scores, a classical/quantum
benchmark, a deterministic risk decision, and a readable report. No code path
can place an order.

