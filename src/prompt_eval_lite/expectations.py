"""Output checks. Each returns an error message or None when it holds."""

from __future__ import annotations

import json
import re
from typing import Any

from .models import Expectation

KINDS = (
    "contains",
    "not_contains",
    "regex",
    "equals",
    "max_length",
    "min_length",
    "is_json",
    "json_schema",
)

_JSON_TYPES: dict[str, tuple[type, ...]] = {
    "object": (dict,),
    "array": (list,),
    "string": (str,),
    "number": (int, float),
    "integer": (int,),
    "boolean": (bool,),
    "null": (type(None),),
}

_FENCE = re.compile(r"^\s*```[A-Za-z0-9_-]*\s*\n(.*?)\n\s*```\s*$", re.DOTALL)


def parse_json_output(text: str) -> Any:
    """Parse JSON, tolerating a surrounding Markdown code fence."""
    stripped = text.strip()
    fenced = _FENCE.match(stripped)
    if fenced:
        stripped = fenced.group(1)
    return json.loads(stripped)


def _type_ok(value: Any, expected: str) -> bool:
    if expected in ("number", "integer") and isinstance(value, bool):
        return False
    return isinstance(value, _JSON_TYPES.get(expected, ()))


def validate_schema(value: Any, schema: dict[str, Any], path: str = "$") -> list[str]:
    """Validate against a small JSON-Schema subset.

    Supported: type, enum, const, required, properties, items, minimum, maximum,
    minLength, maxLength, minItems, maxItems.
    """
    errors: list[str] = []
    expected = schema.get("type")
    if expected is not None:
        types = expected if isinstance(expected, list) else [expected]
        if not any(_type_ok(value, t) for t in types):
            return [f"{path}: expected {'|'.join(types)}, got {type(value).__name__}"]
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: {value!r} not in enum {schema['enum']!r}")
    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: expected constant {schema['const']!r}")
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}: missing required field '{key}'")
        for key, sub in schema.get("properties", {}).items():
            if key in value:
                errors.extend(validate_schema(value[key], sub, f"{path}.{key}"))
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append(f"{path}: fewer than {schema['minItems']} items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append(f"{path}: more than {schema['maxItems']} items")
        if "items" in schema:
            for i, item in enumerate(value):
                errors.extend(validate_schema(item, schema["items"], f"{path}[{i}]"))
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append(f"{path}: shorter than {schema['minLength']} characters")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append(f"{path}: longer than {schema['maxLength']} characters")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: {value} < minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: {value} > maximum {schema['maximum']}")
    return errors


def _short(text: str, limit: int = 60) -> str:
    text = text.replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 3] + "..."


def check(exp: Expectation, output: str) -> str | None:
    """Return a failure message, or None if the expectation holds."""
    kind, value = exp.kind, exp.value
    hay = output.lower() if exp.ignore_case else output
    needle = str(value).lower() if exp.ignore_case else str(value)

    if kind == "contains":
        return None if needle in hay else f"expected output to contain {_short(str(value))!r}"
    if kind == "not_contains":
        return f"expected output not to contain {_short(str(value))!r}" if needle in hay else None
    if kind == "regex":
        flags = re.IGNORECASE if exp.ignore_case else 0
        return None if re.search(str(value), output, flags) else f"no match for regex /{value}/"
    if kind == "equals":
        a, b = output.strip(), str(value).strip()
        if exp.ignore_case:
            a, b = a.lower(), b.lower()
        return None if a == b else f"expected {_short(str(value))!r}, got {_short(output)!r}"
    if kind == "max_length":
        n = len(output)
        return None if n <= int(value) else f"length {n} exceeds max_length {value}"
    if kind == "min_length":
        n = len(output)
        return None if n >= int(value) else f"length {n} below min_length {value}"
    if kind in ("is_json", "json_schema"):
        try:
            parsed = parse_json_output(output)
        except ValueError:
            return "output is not valid JSON"
        if kind == "json_schema":
            errors = validate_schema(parsed, value)
            if errors:
                return "; ".join(errors[:3])
        return None
    return f"unknown expectation kind: {kind}"
