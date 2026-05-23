# Contributing to fatture-cli

Thanks for considering a contribution.

## Quick setup

```bash
git clone https://github.com/mayai-it/fatture-cli
cd fatture-cli
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/
```

## Before opening a PR

- `ruff check fatture_cli/ tests/` must be clean.
- `mypy fatture_cli/` must report 0 errors.
- `pytest tests/` must be green.
- Add tests for new behavior. Coverage must not drop.

## Commit messages

Conventional commits preferred: `feat:`, `fix:`, `docs:`, `test:`,
`refactor:`, `ci:`, `chore:`. Imperative mood ("add X", not "added X").

## Reporting issues

For bugs, please include:

- Python version, OS, fatture-cli version (`fatture --version`)
- Command that triggered the issue
- Expected vs actual behavior
- Stderr output if relevant

There's an issue template that prompts for each of these — please use it.

## Architecture notes

A few places that aren't obvious from the file tree:

- **`fatture_cli/transforms/`** holds pure helpers shared between the CLI
  and the MCP server. If you add a new resource shape, add the transform
  here so both surfaces stay aligned.
- **`fatture_cli/models/`** holds Pydantic 2 models. Monetary fields are
  `Decimal`, never `float` — please don't change this even if the underlying
  SDK uses `float`. See [README.md#engineering-notes](README.md#engineering-notes).
- **`fatture_cli/api/client.py`** exposes typed methods `get_resource`,
  `get_paginated`, `post_resource`, `put_resource` returning `dict[str, Any]`.
  Prefer these over the raw `get` / `post` / `put` in new call sites.
