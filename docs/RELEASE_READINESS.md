# Release Readiness

Verified locally on 2026-07-26.

## Product surfaces

| Surface | Verification |
|---|---|
| Overview | Real objective/run totals and latest persisted result render |
| Agent | Normal chat, connection tools, progress messages, and complete responses work |
| Research | A study can be launched and reaches a terminal persisted state |
| Runs | Run selection, events, report evidence, and valid controls render |
| Strategies | Typed definitions and a direct deterministic backtest render |
| Labs | Solver benchmark renders and quantum capability is truthfully disabled |
| Risk | Deterministic gates and the deployment block render |
| Connections | Provider scan/test, Telegram form, local MT5 detection, and bridge form work |
| Terminal | `./soki`, `/help`, `/status`, normal chat, and clean exit work |

## Automated release gates

- Python and frontend lint
- Python unit/integration suite
- React component suite across every section
- TypeScript production build
- full npm dependency audit
- terminal connectivity check
- live HTTP route smoke test
- live experiment WebSocket event test

## Verified local connection state

- Model provider: configured, model catalog scan succeeded, response test passed
- Market data: ready with validated cache support
- MetaTrader 5 application: installed and detected
- MT5 account gateway: not connected; requires a compatible REST/MCP bridge,
  endpoint, token, and bridge-reported DEMO account
- Telegram: not configured; requires a bot token and allowed chat ID
- Live orders: disabled

The core research product can be used now without Telegram or MT5. Those two
external gateways are never presented as connected until their real
authentication and health checks succeed.
