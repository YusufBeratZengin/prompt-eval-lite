from __future__ import annotations

import pytest

from prompt_eval_lite import Expectation, check
from prompt_eval_lite.expectations import parse_json_output, validate_schema
from prompt_eval_lite.template import TemplateError, render


@pytest.mark.parametrize("output", ["NaN", "Infinity", "-Infinity", "1e999", '[{"x": NaN}]'])
def test_nonfinite_json_is_rejected(output: str) -> None:
    assert not ok("is_json", True, output)
    assert not ok("json_schema", {"type": "number", "minimum": 0, "maximum": 1}, output)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_schema_rejects_nonfinite_numbers(value: float) -> None:
    assert validate_schema(value, {"minimum": 0, "maximum": 1})
    assert validate_schema({"x": [value]}, {})


@pytest.mark.parametrize("keyword", ["enum", "const"])
@pytest.mark.parametrize("value,output", [(1, "true"), (False, "0"), ({"x": [1]}, '{"x":[true]}')])
def test_json_equality_distinguishes_booleans(keyword: str, value: object, output: str) -> None:
    schema = {keyword: [value] if keyword == "enum" else value}
    assert not ok("json_schema", schema, output)
    assert ok("json_schema", {keyword: [1] if keyword == "enum" else 1}, "1.0")


def ok(kind: str, value: object, output: str, ignore_case: bool = False) -> bool:
    return check(Expectation(kind, value, ignore_case), output) is None


def test_contains_and_not_contains() -> None:
    assert ok("contains", "Paris", "I love Paris")
    assert not ok("contains", "paris", "I love Paris")
    assert ok("contains", "paris", "I love Paris", ignore_case=True)
    assert ok("not_contains", "Rome", "I love Paris")
    assert not ok("not_contains", "Paris", "I love Paris")
    assert not ok("not_contains", "PARIS", "I love Paris", ignore_case=True)


def test_regex() -> None:
    assert ok("regex", r"^\d{3}$", "123")
    assert not ok("regex", r"^\d{3}$", "12a")
    assert ok("regex", "hello", "HELLO", ignore_case=True)


def test_equals_strips_whitespace() -> None:
    assert ok("equals", "yes", "  yes\n")
    assert not ok("equals", "yes", "yes!")
    assert ok("equals", "YES", "yes", ignore_case=True)


def test_length_bounds() -> None:
    assert ok("max_length", 5, "12345")
    assert not ok("max_length", 4, "12345")
    assert ok("min_length", 5, "12345")
    assert not ok("min_length", 6, "12345")


def test_is_json_accepts_fences() -> None:
    assert ok("is_json", None, '{"a": 1}')
    assert ok("is_json", None, '```json\n{"a": 1}\n```')
    assert not ok("is_json", None, "nope")
    assert parse_json_output("[1, 2]") == [1, 2]


def test_json_schema() -> None:
    schema = {
        "type": "object",
        "required": ["name"],
        "properties": {
            "name": {"type": "string", "minLength": 2, "maxLength": 5},
            "age": {"type": "integer", "minimum": 0, "maximum": 150},
            "tags": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 2},
            "kind": {"enum": ["a", "b"]},
            "v": {"const": 1},
        },
    }
    assert ok("json_schema", schema, '{"name": "Ada", "age": 36, "tags": ["x"], "kind": "a"}')
    assert not ok("json_schema", schema, '{"age": 1}')
    assert not ok("json_schema", schema, '{"name": "A"}')
    assert not ok("json_schema", schema, '{"name": "Abcdefg"}')
    assert not ok("json_schema", schema, '{"name": "Ada", "age": 1.5}')
    assert not ok("json_schema", schema, '{"name": "Ada", "age": true}')
    assert not ok("json_schema", schema, '{"name": "Ada", "age": -1}')
    assert not ok("json_schema", schema, '{"name": "Ada", "age": 200}')
    assert not ok("json_schema", schema, '{"name": "Ada", "tags": []}')
    assert not ok("json_schema", schema, '{"name": "Ada", "tags": ["a", "b", "c"]}')
    assert not ok("json_schema", schema, '{"name": "Ada", "tags": [1]}')
    assert not ok("json_schema", schema, '{"name": "Ada", "kind": "z"}')
    assert not ok("json_schema", schema, '{"name": "Ada", "v": 2}')
    assert not ok("json_schema", schema, "[]")
    assert not ok("json_schema", schema, "garbage")


def test_validate_schema_type_union() -> None:
    assert validate_schema(None, {"type": ["string", "null"]}) == []
    assert validate_schema(3, {"type": ["string", "null"]})


def test_unknown_kind_reports() -> None:
    assert "unknown" in (check(Expectation("bogus", 1), "x") or "")


def test_template() -> None:
    assert render("Hi {{ name }}, {{n}}!", {"name": "Ada", "n": 3}) == "Hi Ada, 3!"
    with pytest.raises(TemplateError):
        render("{{missing}}", {})
