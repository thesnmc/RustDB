# Contributing to TheSNMC RustDB

## Local setup

- Python 3.11+
- Optional: Docker Desktop for full stack

## Quick checks before PR

1. Run tests:
   - `python -m unittest discover -s tests -v`
2. Run local demo:
   - `python main.py`
3. If touching API/worker behavior, run smoke test:
   - start API, then `python scripts/smoke_test.py`

## Pull requests

- Keep changes scoped and small when possible.
- Update `README.md` if commands, env vars, or endpoints change.
- Include testing notes in PR description.
