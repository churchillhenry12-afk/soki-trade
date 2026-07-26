# Soki Trade

Soki Trade is a general-purpose operations agent with specialist trading
research tools. You connect the agent's intelligence, Telegram gateway, and
optional MT5 bridge, then use one chat to manage those connections, handle
normal AI tasks, start strategy tests, and receive reports. Production research
turns trading requests into validated strategy DSL, downloads and caches real
historical market candles, runs deterministic backtests and hostile execution
tests, scores robustness, selects a portfolio, and applies immutable risk rules.

This is research software, not financial advice. Live trading is disabled.

## Current integration status

| Integration | Production research implementation | Status |
|---|---|---:|
| Research engine | deterministic local planner and typed strategy generator | Ready |
| Agent intelligence/chat | tested OpenAI-compatible, Anthropic, or local model connection | User-configured |
| Market data | real Yahoo Finance candles with validated local CSV/Parquet override and cache | Ready |
| Telegram | authenticated bot gateway with restricted-chat inbound polling | User-configured |
| MT5 | local terminal detection plus authenticated REST/MCP demo-bridge verification | Terminal detected; bridge user-configured |
| Quantum | no QPU claim; verified classical exhaustive control | Disabled |
| Execution | PAPER artifact approval only; zero orders | Disabled |
| Persistence | SQLite locally; PostgreSQL schema available | Yes/local |
| Worker | in-process local orchestrator; Celery boundary available | Yes/local |

## Requirements

- Windows, macOS, or Linux
- Python 3.12+
- Node.js 22+
- [`uv`](https://docs.astral.sh/uv/)
- Docker is optional

The local production research runtime does not require Docker, PostgreSQL, or
Redis.

## Start the agent

Production mode is the default. Demo adapters are not loaded by this command:

```bash
make setup
make run
```

Then open:

- Agent UI: <http://127.0.0.1:5173>
- API: <http://127.0.0.1:8000>
- OpenAPI: <http://127.0.0.1:8000/docs>

The agent opens as the main workspace. Use F1–F8 or the navigation bar for
Overview, Agent, Research, Runs, Strategies, Labs, Risk, and Connections.
Connections includes the provider/model setup, Telegram, and MT5 gateway
configuration. Ask `Backtest EURUSD M15` in chat or launch a structured study
from Research. Telegram and MT5 are optional, and remain visibly disconnected
until their real remote checks pass.

For a symbol/timeframe without a local file, Soki Trade downloads real candles
from Yahoo Finance, validates them, and maintains a 15-minute cache under
`data/market/.cache/`. A matching user-supplied
`data/market/SYMBOL_TIMEFRAME.csv` or Parquet file takes precedence. CSV files require
`timestamp,open,high,low,close,volume` columns with ordered, unique
UTC-compatible timestamps and valid OHLC relationships.

Check readiness at <http://127.0.0.1:8000/ready>. Network access is required
only for the first download of a symbol/timeframe.

## Start in one terminal

The primary terminal experience starts the API and centered agent chat together:

```bash
./soki
```

For Windows, the standalone executable is the simplest option. It includes its
own Python runtime and does not need the PowerShell installer, Python, `uv`, or
Node.js:

<https://github.com/churchillhenry12-afk/soki-trade/releases/latest/download/SokiTrade.exe>

Download `SokiTrade.exe` and open it, or run it from PowerShell:

```powershell
.\SokiTrade.exe
```

Agent settings, gateway credentials, market data, and the local database are
kept under `%LOCALAPPDATA%\SokiTrade`. The executable selects a free private
localhost port automatically, so an existing application on port 8000 cannot
prevent it from starting.

For a fresh Windows machine, run this in PowerShell:

```powershell
irm https://github.com/churchillhenry12-afk/soki-trade/releases/latest/download/install.ps1 | iex
```

On macOS or Linux, install the verified release with:

```bash
curl -fsSL https://github.com/churchillhenry12-afk/soki-trade/releases/latest/download/install.sh | bash
```

The hosted interface is available at
<https://soki-trade-agent.vercel.app>. The terminal agent must be running on
the same computer. Credentials, MT5 access, research data, and model
configuration remain local and are never uploaded to Vercel.

No second terminal is required. Type normally to chat, or use:

- `/setup` — connection center
- `/connect telegram` / `/disconnect telegram` — manage Telegram in chat
- `/connect mt5` / `/disconnect mt5` — manage the MT5 gateway in chat
- `/model` — configure and test the model
- `/telegram` — connect and test the Telegram bot
- `/mt5` — verify an MT5 MCP or REST gateway
- `/install-mt5` — download and open the official installer
- `/mt5-login` — launch MT5 with a demo/investor account
- `/backtest EURUSD M15` — start a real-data study
- `/report` — explain the current report
- `/status`, `/help`, `/clear`, `/quit`

On first launch, `./soki` installs Python dependencies when necessary. It starts
the production API privately in the background and stops it when the terminal
agent exits. The same command works on later launches.

Model setup supports:

- OpenAI-compatible APIs
- Anthropic APIs
- Local OpenAI-compatible endpoints

Choose the provider, enter its API key and base URL, then use **Scan available
models**. Soki Trade requests the provider's live model catalog and lets you
select a returned model before running the response test. Provider settings,
Telegram tokens, and gateway tokens can all be entered without leaving the
terminal. Persisted credentials are Git-ignored, restricted to the current user
with `0600` permissions, and never returned by the API.

The MT5 installer is downloaded from MetaQuotes' official distribution. On
macOS and Windows, Soki Trade opens the signed installer. Broker account
creation, terms, KYC, and passkey confirmation cannot be bypassed and remain in
the official terminal. `/mt5-login` can launch an installed terminal with a
demo or investor account; its temporary password file is owner-only and deleted
after launch. Automated trading is forced off. An installed terminal is
detected separately from an MT5 bridge: account data requires a compatible
REST/MCP endpoint and optional token. Connection setup asks you to select Demo
or Real. If the bridge reports its account type, it must match that selection;
bridges without an account-mode field use the explicit selection and are marked
accordingly. Both account types remain read-only.

## Optional explicit demo

Synthetic data and mock agents are available only through explicit demo
commands:

```bash
make demo
make terminal-demo
```

Check terminal connectivity without opening the interactive view:

```bash
make terminal-check
```

## Quality commands

```bash
make test
make lint
make backend
make frontend
make worker   # requires Redis
make clean
```

Docker users can run:

```bash
docker compose up --build
```

## Submit a research objective by API

```bash
objective_id=$(curl -s http://127.0.0.1:8000/research/objectives \
  -H 'Content-Type: application/json' \
  -d '{
    "title": "EURUSD resilience",
    "thesis": "Test whether volatility-gated transitions survive cost stress.",
    "symbols": ["EURUSD"],
    "timeframe": "M15"
  }' | python3 -c 'import json,sys; print(json.load(sys.stdin)["objective_id"])')

curl -s http://127.0.0.1:8000/experiments \
  -H 'Content-Type: application/json' \
  -d "{\"objective_id\":\"$objective_id\",\"seed\":42}"
```

The browser handles experiment creation, startup, WebSocket subscription, and
paper approval automatically.

## Safety properties

- Strategies are JSON/Pydantic DSL, never generated Python.
- Fills occur on the next bar and use conservative stop/target ordering.
- Critical metrics are deterministic Python calculations.
- Human approval cannot override failed risk checks.
- Only MT5 demo accounts are accepted by the gateway configuration.
- Connecting an MT5 bridge verifies its health/protocol; it does not enable
  order placement.
- There is no live-order implementation in this milestone.

## Repository map

```text
apps/api/             FastAPI entry point
apps/worker/          Celery production boundary
apps/terminal-ui/     React/Vite agent setup and chat
apps/terminal-tui/    Native interactive terminal application
hermes/               adapter connection notes and specialist policies
packages/shared/      schemas, state machine, deterministic services
services/             extraction boundaries and integration adapters
infrastructure/       Docker, Alembic, and scripts
tests/                unit and API integration tests
docs/                 architecture and security decisions
```

Read [Architecture](docs/ARCHITECTURE.md),
[Implementation plan](docs/IMPLEMENTATION_PLAN.md), and
[Security model](docs/SECURITY_MODEL.md), [MT5 integration](docs/MT5_BRIDGE.md),
and [Release readiness](docs/RELEASE_READINESS.md) before connecting an
external agent or broker.

## Next milestone

Deploy the Windows-side MT5 bridge behind the verified REST/MCP connector,
then add read-only account reconciliation. Connect the actual Hermes repository
through `HermesAdapter` and move the orchestrator to durable Celery tasks backed
by PostgreSQL/Redis.
