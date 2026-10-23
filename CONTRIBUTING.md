# Contributing

Thanks for helping improve prompt-eval-lite.

## Principles

- Zero required runtime dependencies: the core must use only the standard library. PyYAML stays an optional extra.
- Fully typed (`mypy --strict`), cross-platform (Linux and Windows are tested in CI).
- Tests never touch the real network. Use the `mock` provider or the loopback `fake_llm` fixture in `tests/conftest.py`.

## Setup

```bash
git clone https://github.com/YusufBeratZengin/prompt-eval-lite.git
cd prompt-eval-lite
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## Checks

```bash
ruff check .
ruff format --check .
mypy
pytest            # coverage must stay at or above 85%
```

If you change CLI output or the example suite, regenerate the demo image with `python scripts/make-demo.py` and update the README snippets.

## Commit style

[Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `docs:`, `test:`, `ci:`, `chore:`. Keep commits small. Add a line to the `[Unreleased]` section of `CHANGELOG.md` for user-visible changes. Do not include secrets or personal data in code, tests or examples.

## Releasing

1. Update `CHANGELOG.md` (move `[Unreleased]` entries under the new version).
2. Bump `version` in `pyproject.toml` and `__version__` in `src/prompt_eval_lite/__init__.py`.
3. Check locally: `python -m build && twine check dist/*`.
4. Commit `chore(release): vX.Y.Z`, then `git tag vX.Y.Z` and push the tag.

The `Publish` workflow builds the package and uploads it to PyPI using trusted publishing (OIDC); configure a PyPI pending publisher for this repository, the `publish.yml` workflow and the `pypi` environment. No API token is stored.
