# soki code

soki code is an evidence-first general-purpose operations agent with specialist trading
research tools. You connect the agent's intelligence, Telegram gateway, and
optional MT5 bridge, then use one chat to manage those connections, handle
normal AI tasks, start strategy tests, and receive reports. Production research
turns trading requests into validated strategy DSL, downloads and caches real
historical market candles, runs deterministic backtests and hostile execution
tests, scores robustness, selects a portfolio, and applies immutable risk rules.

This is research software, not financial advice. Live trading is disabled.

Every agent request creates a durable completion contract and proof-ledger
entry. General agent work runs on the authenticated Hermes Agent runtime that
is installed and managed as part of Soki Code; deterministic research and
immutable risk remain inside soki code.

The product clients share one API and attachment pipeline:

- `apps/soki-code-web` — responsive chat-first laptop interface
- `apps/soki-code-android` — native Android chat client
- `apps/terminal-tui` — native Textual terminal interface

## Current integration status

| Integration | Production research implementation | Status |
|---|---|---:|
| Research engine | deterministic local planner and typed strategy generator | Ready |
| Agent intelligence/chat | bundled Hermes Agent HTTP runtime with server-side tools, session continuity, and controlled model fallback | Ready after model setup |
| Proof Loop | durable tasks, checks, checkpoints, runtime evidence | Ready |
| Market data | real Yahoo Finance candles with validated local CSV/Parquet override and cache | Ready |
| Telegram | authenticated bot gateway with restricted-chat inbound polling | User-configured |
| MT5 | local terminal detection plus authenticated REST/MCP demo-bridge verification | Terminal detected; bridge user-configured |
| Quantum | no QPU claim; verified classical exhaustive control | Disabled |
| Execution | PAPER artifact approval only; zero orders | Disabled |
| Persistence | SQLite locally; PostgreSQL schema available | Yes/local |
| Worker | in-process local orchestrator; Celery boundary available | Yes/local |

## One-product installation

The official installer installs Soki Code, the pinned Hermes automation
runtime, Python, Node.js, browser tooling, and the desktop-control driver in one
operation. Users do not install or launch Hermes separately.

### Windows

Open PowerShell and run:

```powershell
irm https://raw.githubusercontent.com/churchillhenry12-afk/soki-trade/main/packaging/install.ps1 | iex
```

Then open a new PowerShell window and start the product:

```powershell
soki-code
```

### macOS

Open Terminal and run:

```bash
curl -fsSL https://raw.githubusercontent.com/churchillhenry12-afk/soki-trade/main/packaging/install.sh | bash
```

Then start the product:

```bash
soki-code
```

`soki-code` opens the web interface. Use `soki-code terminal` for the terminal
interface. Re-running the installer updates Soki and its pinned runtime while
preserving user data. The uninstallers in `packaging/` remove both application
components together and preserve data unless `SOKI_PURGE_DATA=1` is set.

On macOS, Screen Recording and Accessibility consent must be approved in
System Settings when prompted. Apple does not allow any installer to grant
those permissions silently.

Windows and macOS run the same API, bundled Hermes runtime, proof ledger,
research engine, attachment pipeline, and user interfaces.

## Source-development requirements

- Windows, macOS, or Linux
- Git and [`uv`](https://docs.astral.sh/uv/)
- Browser interface: Node.js 22+
- Android development: Android Studio with SDK 36 and JDK 17 or newer
- Docker is optional

## Start the browser interface

Production mode is the default. The first command installs dependencies; the
second starts the API and the fresh laptop interface, then opens it in your
browser:

```bash
make setup
./soki
```

The bundled Hermes runtime is enabled automatically. Choose and test an AI
model in Soki settings; Soki securely synchronizes that verified model to its
internal automation runtime.
If the browser does not open automatically, use:

- soki code: <http://127.0.0.1:5173>
- API: <http://127.0.0.1:8000>
- OpenAPI: <http://127.0.0.1:8000/docs>

Use the settings control to verify Hermes. Use **Pair phone** to generate a
five-minute, one-use QR code for the Android app. Web and Android can attach
images, videos, audio, documents, and archives from the composer. The Proof
view preserves the evidence for every request.

Starting `./soki` again is safe. If the web app and API are already running,
the launcher reuses them instead of failing with a port collision. If another
application owns a default port, Soki chooses the next available local port
and prints the address it selected.

## Build and test Android

Build the signed debug APK and run its unit tests:

```bash
make android-test
make android-build
```

The APK is created at
`apps/soki-code-android/app/build/outputs/apk/debug/app-debug.apk`.

For a physical phone with USB debugging enabled:

```bash
make android-install
```

`android-install` builds the app, forwards the phone's port 8000 to the laptop,
and upgrades the APK. Version `0.2.0` deliberately replaces the original test
build that blocked local-network HTTP. Keep `./soki` running. In the laptop interface, choose
**Pair phone**, keep `http://127.0.0.1:8000`, generate the QR, then scan it in
the Android app. For a Wi-Fi connection, keep the phone and laptop on the same
trusted network and scan the generated LAN QR. Soki exposes only its pairing
claim and authenticated mobile routes on that network listener.

For a symbol/timeframe without a local file, Soki Code downloads real candles
from Yahoo Finance, validates them, and maintains a 15-minute cache under
`data/market/.cache/`. A matching user-supplied
`data/market/SYMBOL_TIMEFRAME.csv` or Parquet file takes precedence. CSV files require
`timestamp,open,high,low,close,volume` columns with ordered, unique
UTC-compatible timestamps and valid OHLC relationships.

Check readiness at <http://127.0.0.1:8000/ready>. Network access is required
only for the first download of a symbol/timeframe.

## Terminal interface

The native terminal interface is available with `soki-code terminal`. Its compact
Soki mark remains visible while you work.

- `/setup` — connection center
- `/hermes` — inspect and verify the bundled automation runtime
- `/connect telegram` / `/disconnect telegram` — manage Telegram in chat
- `/connect mt5` / `/disconnect mt5` — manage the MT5 gateway in chat
- `/model` — configure and test the fallback model
- `/phone` — create a one-use Android pairing QR
- `/telegram` — connect and test the Telegram bot
- `/mt5` — verify an MT5 MCP or REST gateway
- `/backtest EURUSD M15` — start a real-data study
- `/report` — explain the current report
- `/attach /path/to/file` — attach an image, video, audio file, or document
- `/status`, `/help`, `/clear`, `/quit`

The installer prepares all dependencies. The terminal command starts the
production API on the laptop and stops the process it owns when the terminal
agent exits.

Fallback model setup supports:

- OpenAI-compatible APIs
- Anthropic APIs
- Local OpenAI-compatible endpoints

Choose the provider, enter its API key and base URL, then use **Scan available
models**. Soki Code requests the provider's live model catalog and lets you
select a returned model before running the response test. Provider settings,
Telegram tokens, and gateway tokens can all be entered without leaving the
terminal. Persisted credentials are Git-ignored, restricted to the current user
with user-only permissions, and never returned by the API.

Hermes Agent is distributed under the MIT License. See
[`packaging/THIRD_PARTY_NOTICES.md`](packaging/THIRD_PARTY_NOTICES.md).

Ask the agent to connect MT5 and it will guide you to the verified REST or MCP
gateway form. Broker account creation, terms, KYC, passkeys, and terminal login
remain inside the official MetaTrader application. Automated trading is forced
off. Connection setup asks you to select Demo or Real; both account types
remain read-only.

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
- MT5 Demo and Real gateways remain read-only.
- Connecting an MT5 bridge verifies its health/protocol; it does not enable
  order placement.
- There is no live-order implementation in this milestone.

## Repository map

```text
apps/api/             FastAPI entry point
apps/worker/          Celery production boundary
apps/soki-code-web/   Responsive React/Vite laptop client
apps/soki-code-android/ Native Android chat and pairing client
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

Deploy a signed Windows-side MT5 bridge behind the verified REST/MCP connector,
then add read-only account reconciliation and signed production releases.
