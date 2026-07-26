# Security Model

## Safety invariant

Milestone one contains no live broker client and no live-order method.
`LIVE_DISABLED` is the application mode, and the Risk Governor rejects both
missing human approval and any target other than a verified demo account.

## Agent permissions

Agents receive allowlisted tool names. Shell access is denied by default.
Only Deployment Controller may eventually call MT5 demo-order tools. Risk
Governor rules are immutable frozen values and have no override API.

## Input and model safety

- LLM/provider output is untrusted and must parse into Pydantic v2 schemas.
- Strategies use a constrained condition tree; generated Python is prohibited.
- Provider credentials come only from environment variables.
- Correlation and idempotency identifiers are validated at boundaries.
- Logs are JSON and redact values whose names match secret/token/key/password.

## MT5 bridge controls

The future bridge requires TLS at the ingress, token authentication, timestamped
HMAC requests with nonces, IP allowlisting, rate limiting, idempotency keys,
account-mode validation, and append-only audit logs. Demo and Real gateways may
provide read-only account data; live order methods remain absent and blocked
before adapter dispatch.

## Operational controls

Kill switch, emergency stop, strategy disable, deployment rollback, and
account-level loss lock are independent deterministic controls. Production
secrets must be injected by a secret manager; `.env` files are ignored.

## Threats explicitly addressed

- Prompt injection cannot alter risk rules or execute arbitrary strategy code.
- Replay attacks are bounded by nonce, timestamp, and idempotency checks.
- Look-ahead and same-bar fill bias are blocked in the simulator.
- Event spoofing is prevented by server-generated sequence numbers.
- A mock integration cannot be mistaken for a verified real integration:
  status responses include `adapter_kind` and `verified`.
