# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog 1.1](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Fixed
- Reject HTTP redirects and omit raw HTTP error bodies to protect credentials.
- Reject non-finite JSON numbers and distinguish booleans from numbers in schema equality.
- Validate supported JSON Schema fields and nested schemas while loading suites.
- Replace characters forbidden by XML 1.0 in JUnit text and attributes.

## [0.1.0] - 2026-10-23

### Added
- JSON and YAML (optional PyYAML extra) test suites with `{{ variable }}` templates.
- Expectations: `contains`, `not_contains`, `regex`, `equals`, `max_length`, `min_length`,
  `is_json`, `json_schema` (small JSON Schema subset), with `ignore_case`.
- Providers: OpenAI-compatible chat completions, Ollama, and a deterministic `mock`.
- Terminal table, JSON report and JUnit XML output.
- `--baseline` comparison with regression report, `--fail-on regression`.
- `--repeat N` flakiness measurement.
- `prompt-eval` CLI and a typed Python library API.

[Unreleased]: https://github.com/YusufBeratZengin/prompt-eval-lite/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/YusufBeratZengin/prompt-eval-lite/releases/tag/v0.1.0
