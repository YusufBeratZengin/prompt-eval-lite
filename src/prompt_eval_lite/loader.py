"""Load and validate test suites from JSON or YAML files."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from .expectations import KINDS
from .models import Expectation, Suite, TestCase


class LoadError(ValueError):
    """The suite file is unreadable or invalid."""


def _parse_file(path: Path) -> Any:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise LoadError(f"cannot read {path}: {exc}") from exc
    if path.suffix.lower() in (".yaml", ".yml"):
        try:
            import yaml
        except ImportError as exc:
            raise LoadError(
                "YAML suites need PyYAML: pip install 'prompt-eval-lite[yaml]' (or use JSON)"
            ) from exc
        try:
            return yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise LoadError(f"invalid YAML in {path}: {exc}") from exc
    try:
        return json.loads(text)
    except ValueError as exc:
        raise LoadError(f"invalid JSON in {path}: {exc}") from exc


def _validate_schema(schema: Any, where: str) -> None:
    if not isinstance(schema, dict):
        raise LoadError(f"{where}: needs a mapping")
    if "type" in schema:
        types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        known = ("object", "array", "string", "number", "integer", "boolean", "null")
        if not types or any(not isinstance(t, str) or t not in known for t in types):
            raise LoadError(f"{where}: invalid type")
    for key in ("minimum", "maximum"):
        if key in schema:
            value = schema[key]
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or (isinstance(value, float) and not math.isfinite(value))
            ):
                raise LoadError(f"{where}: {key} needs a finite number")
    for key in ("minLength", "maxLength", "minItems", "maxItems"):
        if key in schema and (
            isinstance(schema[key], bool) or not isinstance(schema[key], int) or schema[key] < 0
        ):
            raise LoadError(f"{where}: {key} needs a non-negative integer")
    if "enum" in schema and (not isinstance(schema["enum"], list) or not schema["enum"]):
        raise LoadError(f"{where}: enum needs a non-empty list")
    if "required" in schema and (
        not isinstance(schema["required"], list)
        or any(not isinstance(key, str) for key in schema["required"])
    ):
        raise LoadError(f"{where}: required needs a list of strings")
    if "properties" in schema:
        if not isinstance(schema["properties"], dict):
            raise LoadError(f"{where}: properties needs a mapping")
        for key, sub in schema["properties"].items():
            if not isinstance(key, str):
                raise LoadError(f"{where}: property names must be strings")
            _validate_schema(sub, f"{where}.properties.{key}")
    if "items" in schema:
        _validate_schema(schema["items"], f"{where}.items")


def _expectation(raw: Any, where: str) -> Expectation:
    if not isinstance(raw, dict):
        raise LoadError(f"{where}: expectation must be a mapping")
    kind = raw.get("type")
    if kind is None:
        found = [k for k in raw if k in KINDS]
        if len(found) != 1:
            raise LoadError(f"{where}: expectation needs exactly one of {', '.join(KINDS)}")
        kind = found[0]
        value = raw[kind]
    else:
        value = raw.get("value", raw.get("schema"))
    if kind not in KINDS:
        raise LoadError(f"{where}: unknown expectation '{kind}' (known: {', '.join(KINDS)})")
    if kind in ("max_length", "min_length") and (
        isinstance(value, bool) or not isinstance(value, int)
    ):
        raise LoadError(f"{where}: {kind} needs an integer")
    if kind == "json_schema" and not isinstance(value, dict):
        raise LoadError(f"{where}: json_schema needs a mapping")
    if kind == "json_schema":
        _validate_schema(value, f"{where}: json_schema")
    if kind in ("contains", "not_contains", "regex", "equals") and value is None:
        raise LoadError(f"{where}: {kind} needs a value")
    if kind == "regex":
        import re

        try:
            re.compile(str(value))
        except re.error as exc:
            raise LoadError(f"{where}: invalid regex: {exc}") from exc
    return Expectation(kind=kind, value=value, ignore_case=bool(raw.get("ignore_case", False)))


def parse_suite(data: Any, default_name: str = "suite") -> Suite:
    if not isinstance(data, dict):
        raise LoadError("suite must be a mapping with a 'tests' list")
    tests_raw = data.get("tests")
    if not isinstance(tests_raw, list) or not tests_raw:
        raise LoadError("suite needs a non-empty 'tests' list")
    shared_vars = data.get("vars") or {}
    shared_system = data.get("system")
    tests: list[TestCase] = []
    names: set[str] = set()
    for i, raw in enumerate(tests_raw, 1):
        if not isinstance(raw, dict):
            raise LoadError(f"test #{i}: must be a mapping")
        name = str(raw.get("name") or f"test-{i}")
        if name in names:
            raise LoadError(f"test #{i}: duplicate name '{name}'")
        names.add(name)
        prompt = raw.get("prompt")
        if not isinstance(prompt, str) or not prompt:
            raise LoadError(f"test '{name}': 'prompt' must be a non-empty string")
        local_vars = raw.get("vars") or {}
        if not isinstance(local_vars, dict) or not isinstance(shared_vars, dict):
            raise LoadError(f"test '{name}': 'vars' must be a mapping")
        expects = raw.get("expect") or []
        if isinstance(expects, dict):
            expects = [expects]
        if not isinstance(expects, list):
            raise LoadError(f"test '{name}': 'expect' must be a list")
        tests.append(
            TestCase(
                name=name,
                prompt=prompt,
                vars={**shared_vars, **local_vars},
                system=raw.get("system", shared_system),
                expect=tuple(_expectation(e, f"test '{name}'") for e in expects),
            )
        )
    provider = data.get("provider") or {}
    if not isinstance(provider, dict):
        raise LoadError("'provider' must be a mapping")
    return Suite(name=str(data.get("name") or default_name), tests=tuple(tests), provider=provider)


def load_suite(path: str | Path) -> Suite:
    p = Path(path)
    return parse_suite(_parse_file(p), default_name=p.stem)
