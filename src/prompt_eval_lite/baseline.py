"""Compare a run against a previously saved JSON report."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .models import TestResult


class BaselineError(ValueError):
    pass


@dataclass
class Change:
    name: str
    before: float
    after: float


@dataclass
class Comparison:
    regressions: list[Change] = field(default_factory=list)
    improvements: list[Change] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    new: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)

    @property
    def has_regressions(self) -> bool:
        return bool(self.regressions)

    def to_dict(self) -> dict[str, Any]:
        def conv(items: list[Change]) -> list[dict[str, Any]]:
            return [{"name": c.name, "before": c.before, "after": c.after} for c in items]

        return {
            "regressions": conv(self.regressions),
            "improvements": conv(self.improvements),
            "unchanged": self.unchanged,
            "new": self.new,
            "removed": self.removed,
        }


def load_report(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    try:
        data = json.loads(p.read_text(encoding="utf-8-sig"))
    except OSError as exc:
        raise BaselineError(f"cannot read baseline {p}: {exc}") from exc
    except ValueError as exc:
        raise BaselineError(f"baseline {p} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("tests"), list):
        raise BaselineError(f"baseline {p} is not a prompt-eval report")
    return data


def compare(results: list[TestResult], baseline: dict[str, Any]) -> Comparison:
    """A regression is any test whose pass rate dropped versus the baseline."""
    before: dict[str, float] = {}
    for item in baseline["tests"]:
        try:
            before[str(item["name"])] = float(item["pass_rate"])
        except (KeyError, TypeError, ValueError) as exc:
            raise BaselineError("baseline test entries need 'name' and 'pass_rate'") from exc
    out = Comparison()
    seen: set[str] = set()
    for r in results:
        seen.add(r.name)
        if r.name not in before:
            out.new.append(r.name)
            continue
        old, now = before[r.name], round(r.pass_rate, 4)
        if now < old:
            out.regressions.append(Change(r.name, old, now))
        elif now > old:
            out.improvements.append(Change(r.name, old, now))
        else:
            out.unchanged.append(r.name)
    out.removed = [n for n in before if n not in seen]
    return out


def format_comparison(cmp: Comparison) -> str:
    lines = ["Baseline comparison"]
    if cmp.regressions:
        lines.append(f"  Regressions ({len(cmp.regressions)}):")
        lines += [f"    - {c.name}: {c.before:.0%} -> {c.after:.0%}" for c in cmp.regressions]
    else:
        lines.append("  Regressions: none")
    if cmp.improvements:
        lines.append(f"  Improvements ({len(cmp.improvements)}):")
        lines += [f"    + {c.name}: {c.before:.0%} -> {c.after:.0%}" for c in cmp.improvements]
    lines.append(f"  Unchanged: {len(cmp.unchanged)}")
    if cmp.new:
        lines.append(f"  New: {', '.join(cmp.new)}")
    if cmp.removed:
        lines.append(f"  Removed: {', '.join(cmp.removed)}")
    return "\n".join(lines)
