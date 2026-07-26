# MT5 Integration

## Current verified behavior

Soki Trade treats the locally installed MetaTrader terminal and the machine-
readable MT5 gateway as two separate things.

- `GET /mt5/local-status` detects an installed terminal and reports its path.
- The connection center accepts an authenticated REST or MCP bridge endpoint.
- The bridge must pass its protocol/health check before its configuration is
  saved.
- The connection center requires the user to select `DEMO` or `REAL`.
- If the bridge reports an account type, it must match the selected type. The
  bridge may report `account_mode`, `mode`, or MetaTrader's numeric
  `trade_mode` (`0` for Demo and `2` for Real).
- A bridge that does not expose account mode can still connect using the
  explicit user selection; status identifies that selection as
  `USER_SELECTED` instead of `BRIDGE_VERIFIED`.
- Both Demo and Real connections are read-only.
- Connecting a bridge does not enable order placement. Live orders are not
  implemented.

On the verified macOS installation, the terminal is available at
`/Applications/MetaTrader 5.app`. The application bundle runs the Windows
terminal through Wine and does not itself expose a safe local account API to
Soki Trade.

## What is required for an account connection

1. Log into the intended Demo or Real account in the MetaTrader 5 terminal.
2. Run a compatible REST or MCP bridge on the terminal host.
3. Open **Connections** or type `/connect mt5`.
4. Select the matching account type and enter the bridge transport, endpoint,
   and bearer token.
5. Let Soki Trade verify the protocol. If the bridge reports its account type,
   Soki also verifies that it matches the selection.

The app deliberately does not infer account state from a running process and
does not save an unverified endpoint. An installed terminal can therefore be
shown as **installed** while its gateway remains **disconnected**.

## Bridge security contract

A production companion bridge should expose authenticated health,
terminal/account/symbol information, historical bars and ticks, positions,
pending orders, and reconciliation reports. Any future demo mutation must
require:

- bearer-token authentication and a timestamped HMAC signature
- a unique nonce and idempotency key
- source IP on an allowlist
- verified `trade_mode=DEMO`
- local risk and loss-lock checks
- a structured audit record

The Soki Trade API treats a mutation timeout as an unknown execution state until
reconciliation. It must never blindly retry an order mutation.

## Adapter boundary

`MT5Adapter` separates transport from orchestration:

- `FileMarketDataAdapter` supplies validated CSV or Parquet historical bars.
- The configured REST/MCP gateway supplies verified remote terminal status.
- A deployable MetaTrader-side companion bridge is a separate deployment unit
  and is not included in this repository.

Until that companion service is connected, MT5 account data remains
unavailable and the UI keeps the gateway visibly disconnected. A connected
Real account is restricted to read-only status and reconciliation data.
