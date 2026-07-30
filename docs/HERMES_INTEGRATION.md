# Hermes Agent integration

soki code uses Hermes through its authenticated OpenAI-compatible API server.
The process boundary keeps Hermes upgradeable and prevents its general tools
from entering soki code’s deterministic risk engine.

## Start Hermes

Install Hermes Agent from its official repository, select a model, and add the
following to the Hermes profile `.env`:

```bash
API_SERVER_ENABLED=true
API_SERVER_KEY=replace-with-a-long-random-secret
```

Then start its gateway:

```bash
hermes gateway
```

Hermes listens on `http://127.0.0.1:8642` by default.

## Connect soki code

Add matching values to `qforge/.env`:

```bash
QFORGE_HERMES_URL=http://127.0.0.1:8642
QFORGE_HERMES_API_KEY=replace-with-the-same-long-random-secret
QFORGE_HERMES_MODEL=hermes-agent
```

Start soki code with:

```bash
./soki
```

`GET /setup/status` reports `hermes.verified=true` only after the live health
probe succeeds. General tasks then use Hermes. Deterministic connection,
research, backtest, and risk actions remain owned by soki code.

## Failure behavior

If Hermes becomes unavailable, soki code records the failure and uses the configured
model router for general conversation. It does not bypass trading controls.
The Proof Ledger records which runtime produced each outcome.
