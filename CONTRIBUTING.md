# Contributing

Contributions are welcome. This guide summarises the process and project
requirements.

## Development environment

1. Create a virtual environment for Python 3.10 or later.
2. Install dependencies with:

   ```bash
   python -m pip install -e .[all,dev]
   ```

3. Run the quality checks before opening a pull request:

   ```bash
   python -m pytest
   python -m ruff check .
   python -m black --check .
   python -m mypy --strict .
   python -m bandit -r src
   ```

## Coding standards

- Formatting: Black (line length 88).
- Linting: Ruff (configuration in `pyproject.toml`).
- Typing: `mypy --strict`.
- Documentation: Google-style docstrings, factual tone.
- Imports: standard library, third-party, and local packages grouped and sorted.

## Commit expectations

- Keep commits focused and include tests when behaviour changes.
- Reference related issues when applicable.
- Follow the project's hash-chain ledger semantics when modifying ledger code
   (each ledger entry stores the hash of the previous entry; see the README
   section “Ledger output” for details).

## Communication

Use the GitHub issue tracker for bugs and feature requests. General questions
can be posted in Discussions or sent to s@scrrlt.dev.

Thank you for helping improve carbon-ops.
