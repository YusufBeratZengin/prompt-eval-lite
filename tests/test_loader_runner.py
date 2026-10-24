from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from prompt_eval_lite import (
    LoadError,
    MockProvider,
    ProviderError,
    RunResult,
    TestResult,
    load_suite,
    run_suite,
)
from prompt_eval_lite.loader import parse_suite
from prompt_eval_lite.providers import Provider
from prompt_eval_lite.runner import summarize

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


@pytest.mark.parametrize(
    "schema",
    [
        {"minimum": "zero"},
        {"maximum": True},
        {"minimum": float("nan")},
        {"type": "unknown"},
        {"type": ["string", 1]},
        {"type": []},
        {"type": {}},
        {"enum": 1},
        {"enum": []},
        {"required": "x"},
        {"required": [1]},
        {"properties": []},
        {"properties": {"x": {"minLength": "2"}}},
        {"properties": {"x": 3}},
        {"items": []},
        {"items": {"maxItems": -1}},
        {"minLength": True},
        {"maxLength": 1.5},
        {"minItems": -1},
        {"maxItems": "2"},
    ],
)
def test_invalid_schema_rejected_at_load_time(schema: Any) -> None:
    with pytest.raises(LoadError, match="json_schema"):
        parse_suite({"tests": [{"prompt": "x", "expect": [{"json_schema": schema}]}]})


def write(tmp_path: Path, name: str, data: Any) -> Path:
    p = tmp_path / name
    p.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
    return p


def test_load_example_json() -> None:
    suite = load_suite(EXAMPLES / "suite.json")
    assert suite.name == "support-bot"
    assert [t.name for t in suite.tests][:2] == ["capital", "summary-no-email"]
    assert suite.tests[0].expect[0].kind == "contains"
    assert suite.provider["type"] == "mock"


def test_load_yaml() -> None:
    pytest.importorskip("yaml")
    suite = load_suite(EXAMPLES / "suite.yaml")
    assert suite.name == "translator"
    assert suite.tests[0].vars == {"greeting": "Bonjour"}
    assert suite.tests[0].expect[0].ignore_case is True


def test_yaml_without_pyyaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import sys

    monkeypatch.setitem(sys.modules, "yaml", None)  # makes `import yaml` raise ImportError
    p = write(tmp_path, "s.yaml", "tests: []")
    with pytest.raises(LoadError, match="PyYAML"):
        load_suite(p)


def test_invalid_yaml(tmp_path: Path) -> None:
    pytest.importorskip("yaml")
    with pytest.raises(LoadError, match="invalid YAML"):
        load_suite(write(tmp_path, "s.yml", "tests: [unclosed"))


def test_missing_and_invalid_json(tmp_path: Path) -> None:
    with pytest.raises(LoadError, match="cannot read"):
        load_suite(tmp_path / "nope.json")
    with pytest.raises(LoadError, match="invalid JSON"):
        load_suite(write(tmp_path, "bad.json", "{"))


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ([], "mapping"),
        ({}, "tests"),
        ({"tests": [1]}, "mapping"),
        ({"tests": [{"name": "a"}]}, "prompt"),
        ({"tests": [{"prompt": "x"}, {"name": "test-1", "prompt": "y"}]}, "duplicate"),
        ({"tests": [{"prompt": "x", "expect": "contains"}]}, "list"),
        ({"tests": [{"prompt": "x", "vars": 3}]}, "vars"),
        ({"tests": [{"prompt": "x", "expect": [3]}]}, "mapping"),
        ({"tests": [{"prompt": "x", "expect": [{"foo": 1}]}]}, "exactly one"),
        ({"tests": [{"prompt": "x", "expect": [{"type": "foo"}]}]}, "unknown expectation"),
        ({"tests": [{"prompt": "x", "expect": [{"max_length": "a"}]}]}, "integer"),
        ({"tests": [{"prompt": "x", "expect": [{"json_schema": 3}]}]}, "mapping"),
        ({"tests": [{"prompt": "x", "expect": [{"type": "contains"}]}]}, "needs a value"),
        ({"tests": [{"prompt": "x", "expect": [{"regex": "("}]}]}, "invalid regex"),
        ({"tests": [{"prompt": "x"}], "provider": 3}, "provider"),
    ],
)
def test_validation_errors(data: Any, message: str) -> None:
    with pytest.raises(LoadError, match=message):
        parse_suite(data)


def test_expectation_forms_and_shared_vars() -> None:
    suite = parse_suite(
        {
            "vars": {"a": 1, "b": 2},
            "system": "sys",
            "tests": [
                {
                    "prompt": "{{a}}{{b}}",
                    "vars": {"b": 3},
                    "expect": {"type": "contains", "value": "13"},
                },
                {"prompt": "x", "system": "own", "expect": [{"type": "json_schema", "schema": {}}]},
            ],
        }
    )
    first, second = suite.tests
    assert first.vars == {"a": 1, "b": 3}
    assert first.system == "sys"
    assert first.expect[0].value == "13"
    assert second.system == "own"
    assert second.expect[0].kind == "json_schema"


def test_run_suite_statuses() -> None:
    suite = load_suite(EXAMPLES / "suite.json")
    provider = MockProvider(**{k: v for k, v in suite.provider.items() if k != "type"})
    results = run_suite(suite, provider, repeat=3)
    by_name = {r.name: r for r in results}
    assert by_name["capital"].status == "pass"
    assert by_name["summary-no-email"].status == "fail"
    assert by_name["greeting"].status == "flaky"
    assert by_name["greeting"].pass_rate == pytest.approx(2 / 3)
    assert summarize(results) == {"total": 4, "pass": 2, "fail": 1, "flaky": 1, "error": 0}
    assert by_name["summary-no-email"].messages() == ["expected output not to contain '@'"]


def test_run_suite_is_deterministic() -> None:
    suite = load_suite(EXAMPLES / "suite.json")

    def go() -> list[str]:
        p = MockProvider(**{k: v for k, v in suite.provider.items() if k != "type"})
        return [r.status for r in run_suite(suite, p, repeat=3)]

    assert go() == go()


def test_repeat_validation_and_callback() -> None:
    suite = parse_suite({"tests": [{"prompt": "x"}]})
    with pytest.raises(ValueError, match="repeat"):
        run_suite(suite, MockProvider(), repeat=0)
    seen: list[str] = []
    run_suite(suite, MockProvider(), on_result=lambda r: seen.append(r.name))
    assert seen == ["test-1"]


class Boom(Provider):
    def complete(self, prompt: str, system: str | None = None) -> str:
        raise ProviderError("down")


def test_errors_are_captured() -> None:
    suite = parse_suite({"tests": [{"prompt": "x"}, {"prompt": "{{nope}}"}]})
    results = run_suite(suite, Boom())
    assert [r.status for r in results] == ["error", "error"]
    assert results[0].messages() == ["down"]
    assert "nope" in results[1].messages()[0]


def test_result_helpers() -> None:
    assert TestResult("x", []).pass_rate == 0.0
    mixed = TestResult("x", [RunResult(True), RunResult(False, error="e")])
    assert mixed.status == "flaky"
    assert mixed.to_dict()["pass_rate"] == 0.5
