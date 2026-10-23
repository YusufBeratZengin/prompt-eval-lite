"""Plain data classes shared by the loader, runner and reporters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Expectation:
    """One check applied to a model output."""

    kind: str
    value: Any = None
    ignore_case: bool = False


@dataclass(frozen=True)
class TestCase:
    __test__ = False  # not a pytest class

    name: str
    prompt: str
    vars: dict[str, Any] = field(default_factory=dict)
    system: str | None = None
    expect: tuple[Expectation, ...] = ()


@dataclass(frozen=True)
class Suite:
    name: str
    tests: tuple[TestCase, ...]
    provider: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunResult:
    """Outcome of one model call for one test."""

    passed: bool
    output: str = ""
    failures: list[str] = field(default_factory=list)
    error: str | None = None
    duration: float = 0.0


@dataclass
class TestResult:
    __test__ = False

    name: str
    runs: list[RunResult]

    @property
    def pass_rate(self) -> float:
        if not self.runs:
            return 0.0
        return sum(1 for r in self.runs if r.passed) / len(self.runs)

    @property
    def status(self) -> str:
        """pass, fail, flaky (mixed results over repeats) or error (every run errored)."""
        rate = self.pass_rate
        if rate == 1.0:
            return "pass"
        if rate == 0.0:
            return "error" if all(r.error for r in self.runs) else "fail"
        return "flaky"

    @property
    def duration(self) -> float:
        return sum(r.duration for r in self.runs)

    def messages(self) -> list[str]:
        """Distinct failure/error messages across runs, in order."""
        seen: list[str] = []
        for r in self.runs:
            for m in [r.error] if r.error else r.failures:
                if m and m not in seen:
                    seen.append(m)
        return seen

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "pass_rate": round(self.pass_rate, 4),
            "duration": round(self.duration, 4),
            "runs": [
                {
                    "passed": r.passed,
                    "output": r.output,
                    "failures": r.failures,
                    "error": r.error,
                    "duration": round(r.duration, 4),
                }
                for r in self.runs
            ],
        }
