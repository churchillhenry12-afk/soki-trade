# Quantum Integration

## Status

Milestone one uses an explicitly labeled deterministic mock backend. QPanda3
and Origin Pilot were not detected or tested. The application remains healthy
when quantum dependencies are absent.

## Contract

The quantum layer accepts a QUBO matrix plus constraints and returns a decoded
solution, objective score, runtime, iterations/shots, seed, violations, backend
name, and verification flag. A benchmark must contain at least one classical
baseline over the same problem.

## First use case

Strategy portfolio selection maps one binary variable to each candidate.
Diagonal terms reward robust expected return. Pair terms penalize correlation,
and a cardinality penalty bounds the portfolio size. The mock backend searches
the small binary space deterministically; it does not emulate quantum physics
and cannot demonstrate quantum advantage.

## Optional QPanda setup

Create an isolated Python 3.12 environment and install the current QPanda
package only after checking its official platform compatibility:

```bash
uv venv --python 3.12
uv pip install pyqpanda
```

Because package names and macOS ARM support can change, this command is
documentation rather than a verified claim. The future adapter must run a
capability probe and a benchmark before reporting `verified=true`.

## Measurement policy

Runtime, objective score, constraint violations, seed, and solver configuration
are stored for every run. The UI reports the winner of that benchmark only.
It never labels a result “quantum advantage” without repeated, statistically
sound measurements against tuned classical methods.

