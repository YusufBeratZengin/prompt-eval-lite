"""Tiny ``{{ variable }}`` template renderer."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

_VAR = re.compile(r"\{\{\s*([A-Za-z_][\w.-]*)\s*\}\}")


class TemplateError(ValueError):
    pass


def render(template: str, variables: Mapping[str, Any]) -> str:
    """Replace ``{{ name }}`` with ``variables[name]``; unknown names raise TemplateError."""

    def sub(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in variables:
            raise TemplateError(f"undefined template variable: {key}")
        value = variables[key]
        return value if isinstance(value, str) else str(value)

    return _VAR.sub(sub, template)
