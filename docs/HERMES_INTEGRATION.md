# Hermes Agent integration

soki code uses a pinned Hermes Agent runtime through its authenticated local
OpenAI-compatible API server. The process boundary keeps the runtime
upgradeable and prevents general computer tools from entering soki code’s
deterministic risk engine.

## Product ownership

The Soki installer downloads a checksum-verified Hermes installer, pins the
runtime to the tested upstream commit, and places it below the Soki product
root:

- macOS/Linux: `~/.local/share/soki-code/runtime/hermes`
- Windows: `%LOCALAPPDATA%\SokiCode\runtime\hermes`

It generates the runtime API key, limits the server to loopback, enables the
computer-use toolset, installs the desktop driver, and manages the gateway.
The user performs one Soki installation and launches only `soki-code`.

Hermes Agent remains an MIT-licensed internal dependency. Its copyright and
license are preserved in `packaging/THIRD_PARTY_NOTICES.md`.

## Model setup

Choose a model provider in Soki settings and run its connection test. After the
provider test succeeds, Soki applies the verified model to the bundled runtime,
restarts the local gateway, and verifies a live agent response. Model secrets
are never returned by the API.

`GET /setup/status` reports `hermes.verified=true` only after the live health
probe succeeds. General tasks then use Hermes. Deterministic connection,
research, backtest, and risk actions remain owned by soki code.

On macOS, the user must approve Accessibility and Screen Recording in System
Settings. This is an operating-system security boundary and cannot be bundled
or bypassed.

## Failure behavior

If the runtime becomes unavailable, soki code records the failure and uses the
configured model router only for conversation. Requests requiring computer
tools fail clearly instead of pretending to have acted. It never bypasses
trading controls. The Proof Ledger records which runtime produced each outcome.
