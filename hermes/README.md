# Hermes integration

Hermes source was not present during environment inspection. Soki Trade therefore
depends only on the `HermesAdapter` protocol in
`packages/shared/src/qforge/agents.py`.

To connect Hermes:

1. Add its repository or package outside this directory.
2. Implement `plan` and `build_strategies` using Hermes-supported skills,
   tools, MCP, memory, and agent definitions.
3. Return only Pydantic-valid Soki Trade schemas.
4. Register the implementation through dependency injection in the API.
5. Run the adversarial and risk integration suite before enabling it by default.

Hermes must never calculate portfolio metrics, access unrestricted shell tools,
call MT5 order methods, or override Risk Governor output.
