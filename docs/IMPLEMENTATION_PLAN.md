# soki code implementation plan

soki code is an evidence-first operating agent built on Hermes Agent. Hermes
owns the general agent loop, tools, memory, skills, and session continuity.
soki code owns completion contracts, verification, trading research, immutable risk,
product surfaces, and the Proof Ledger.

## Phase 1 — working vertical slice (implemented)

- Authenticated Hermes HTTP runtime integration with stable session IDs
- Graceful, visible fallback to the configured model router
- Durable agent tasks, success checks, checkpoints, and evidence records
- Proof Ledger APIs and browser/terminal presentation
- Deterministic backtesting, adversarial stress, statistics, and risk review
- Telegram and read-only MT5 connection boundaries
- Compact soki code terminal identity and persistent ASCII mark
- Shared attachment pipeline for images, video, audio, and documents
- Responsive chat-first web interface
- Python tests, strict typing, lint, React tests, and production frontend build

## Phase 2 — completion and recovery engine

- Hermes Runs API streaming for tool-level live progress
- Idempotent task leases and automatic retry policy
- Resume from the last verified checkpoint after process or network failure
- Operator/verifier separation with independent evidence judgments
- Explicit approval inbox for irreversible or externally visible actions
- Artifact registry with hashes, provenance, and rollback metadata

## Phase 3 — Market Laboratory

- Walk-forward and fully held-out evaluation
- Bootstrap, Monte Carlo, parameter-stability, and multiple-testing controls
- Strategy DNA profiles and regime-specific failure maps
- Dataset provenance, freshness, gap, and leakage reports
- Paper-trading reconciliation against backtest assumptions
- Portfolio correlation and concentration challenges

## Phase 4 — general agent platform

- User/project tenancy and encrypted credential vault
- Soky skill forge with reviewable skill versions
- Structured memory graph separating facts, preferences, and hypotheses
- Browser, files, code, messaging, scheduling, and MCP connections
- Cost/time budgets and per-tool permissions
- Shareable, redacted proof reports

## Phase 5 — Android application (implemented foundation)

- Native Kotlin and Jetpack Compose client
- Chat, Proof Ledger, file library, device controls, and QR pairing
- Native file picker for images, video, audio, and documents
- Authenticated REST commands and durable task results
- Encrypted Android Keystore tokens; no broker credentials stored in the app
- Debug APK, unit tests, Android lint, and native build validation

Remaining mobile hardening:

- WebSocket/SSE live agent and experiment events
- Push notifications for completion, failure, and approval requests
- Offline outbox with idempotency keys and safe reconnect
- Biometric confirmation for sensitive approvals
- Mobile API versioning before public release

The Android app is intentionally a client of the same soki code API. It does not
embed the Hermes runtime or trading engine, so mobile development does not
fork agent behavior.

## Phase 6 — release hardening

- Threat model and external security review
- Load, interruption, migration, and disaster-recovery tests
- Signed desktop/Windows builds and reproducible release pipeline
- Observability, privacy controls, retention, export, and deletion
- Paper-only public beta before any separately reviewed execution milestone

## Product definition of done

soki code may say “verified” only when every completion check has evidence. A
research result must survive deterministic risk and adversarial review. A task
interrupted after a durable checkpoint must resume without repeating completed
side effects. No Hermes tool or client may bypass soki code’s risk governor.
