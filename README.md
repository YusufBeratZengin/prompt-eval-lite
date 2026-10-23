# prompt-eval-lite

[![CI](https://github.com/YusufBeratZengin/prompt-eval-lite/actions/workflows/ci.yml/badge.svg)](https://github.com/YusufBeratZengin/prompt-eval-lite/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/prompt-eval-lite)](https://pypi.org/project/prompt-eval-lite/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)
[![Dependencies](https://img.shields.io/badge/dependencies-0-brightgreen.svg)](pyproject.toml)

English | [Türkçe](README.tr.md)

Regression tests for LLM prompts: describe prompts and expectations in a JSON or YAML file, run them against OpenAI-compatible endpoints, Ollama or a deterministic mock, and get a terminal table, JUnit XML for CI, JSON reports, baseline comparison and flakiness measurement.

It has zero required dependencies (standard library only, HTTP through `urllib`), works offline with the built-in mock provider, and never reads API keys from files.

```bash
pip install prompt-eval-lite          # add "[yaml]" for YAML suites
prompt-eval run examples/suite.json --repeat 3
```

![Terminal output of prompt-eval](docs/demo.svg)

## Demo

The image above is generated from the real tool output by `python scripts/make-demo.py`. Two tests pass, `summary-no-email` fails on a `not_contains` check, and `greeting` is flaky: the mock provider cycles its replies, so one of three runs answers "Hi there" instead of "Hello, Ada!".

## Install

```bash
pip install prompt-eval-lite
pip install "prompt-eval-lite[yaml]"   # optional PyYAML for .yaml/.yml suites
```

Python 3.10 or newer. Until the first PyPI release, install from a clone: `pip install -e .`.

## Usage

### A suite file

```json
{
  "name": "support-bot",
  "provider": {"type": "openai", "model": "gpt-4o-mini"},
  "tests": [
    {
      "name": "capital",
      "prompt": "What is the capital of {{country}}?",
      "vars": {"country": "France"},
      "expect": [{"contains": "Paris"}, {"not_contains": "Lyon"}, {"max_length": 80}]
    }
  ]
}
```

The same suite in YAML:

```yaml
name: support-bot
provider: {type: openai, model: gpt-4o-mini}
tests:
  - name: capital
    prompt: "What is the capital of {{country}}?"
    vars: {country: France}
    expect:
      - contains: Paris
      - max_length: 80
```

Suite-level `vars` and `system` are defaults that each test can override. `{{ name }}` placeholders are replaced from `vars`; an undefined variable is reported as an error for that test.

### Expectations

| Expectation | Passes when |
|---|---|
| `contains: text` | the output contains `text` |
| `not_contains: text` | the output does not contain `text` |
| `regex: pattern` | `re.search(pattern, output)` matches |
| `equals: text` | the trimmed output equals the trimmed `text` |
| `max_length: n` / `min_length: n` | the output has at most / at least `n` characters |
| `is_json: true` | the output parses as JSON (a Markdown code fence is tolerated) |
| `json_schema: {...}` | the parsed JSON matches a schema subset: `type`, `enum`, `const`, `required`, `properties`, `items`, `minimum`, `maximum`, `minLength`, `maxLength`, `minItems`, `maxItems` |

Add `ignore_case: true` next to `contains`, `not_contains`, `regex` or `equals`. The long form `{type: contains, value: Paris}` also works.

### Providers

| `type` | Options | Notes |
|---|---|---|
| `openai` | `model` (required), `base_url` (default `https://api.openai.com/v1`), `api_key_env` (default `OPENAI_API_KEY`), `timeout`, `temperature` | Calls `POST {base_url}/chat/completions`; works with vLLM, LM Studio, llama.cpp server and similar. |
| `ollama` | `model` (required), `base_url` (default `http://localhost:11434`), `timeout`, `temperature` | Calls `POST /api/generate`. |
| `mock` | `rules`, `default` | Deterministic, offline. A rule has `match` (substring) or `regex`, and `reply` or `replies` (cycled per call). Without a matching rule the reply is `default`, or `mock: <prompt>`. |

API keys are read only from the environment variable named by `api_key_env`; they are never read from suite files.

### CLI

```bash
prompt-eval run SUITE [--provider mock|openai|ollama] [--model M] [--base-url URL]
                      [--repeat N] [--baseline report.json] [--fail-on any|regression]
                      [--junit out.xml] [--json out.json] [--no-color]
```

Exit codes: `0` all good, `1` a test failed (or regressed, see `--fail-on`), `2` bad usage or an unreadable suite.

### Baselines and regressions

```bash
prompt-eval run examples/suite.json --json baseline.json     # save a known-good run
prompt-eval run examples/suite.json --repeat 3 --baseline baseline.json
```

Real output of the second command (after a one-run baseline):

```text
Baseline comparison
  Regressions (1):
    - greeting: 100% -> 67%
  Unchanged: 3
```

A regression is a test whose pass rate dropped compared with the baseline. Use `--fail-on regression` to fail CI only on regressions, so tests that were already failing do not block you.

### Flakiness

`--repeat N` runs each test `N` times. A test that passes every time is `pass`, one that never passes is `fail` (or `error` if every run raised a provider error), and sometimes is `flaky` with its pass rate shown. In JUnit output, `flaky` counts as a failure.

### Library

```python
from prompt_eval_lite import load_suite, make_provider, run_suite

suite = load_suite("examples/suite.json")
results = run_suite(suite, make_provider(suite.provider), repeat=3)
print([(r.name, r.status, r.pass_rate) for r in results])
```

## Examples

See [`examples/`](examples/): `suite.json` (the demo above, mock provider) and `suite.yaml`.

## How it works

The loader validates the suite and turns every expectation into a small object. For each test the runner renders the prompt, asks the provider `repeat` times, and applies each expectation to each answer. Reporters then format the results as a table, JSON or JUnit XML, and `--baseline` compares pass rates by test name.

## Limitations and privacy

- Checks are deterministic string and JSON checks. There is no LLM-as-judge and no semantic similarity.
- The JSON Schema support is a small subset, not a full validator.
- Requests are sequential and non-streaming. Prompts and outputs are sent to whichever endpoint you configure and are written, in full, to JSON reports; do not put secrets or personal data in prompts you send to third-party services.
- The tests of this project use the mock provider and a loopback fake server. They make no real network calls.

## Development

```bash
git clone https://github.com/YusufBeratZengin/prompt-eval-lite.git
cd prompt-eval-lite
pip install -e ".[dev]"
ruff check . && ruff format --check . && mypy && pytest
python scripts/make-demo.py     # regenerate docs/demo.svg
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md). Security issues: see [SECURITY.md](SECURITY.md).

## License

[MIT](LICENSE)
