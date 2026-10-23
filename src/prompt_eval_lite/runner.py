"""Execute a suite against a provider."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from .expectations import check
from .models import RunResult, Suite, TestCase, TestResult
from .providers import Provider, ProviderError
from .template import TemplateError, render


def run_case(case: TestCase, provider: Provider) -> RunResult:
    start = time.perf_counter()
    try:
        prompt = render(case.prompt, case.vars)
        system = render(case.system, case.vars) if case.system else None
        output = provider.complete(prompt, system)
    except (TemplateError, ProviderError) as exc:
        return RunResult(passed=False, error=str(exc), duration=time.perf_counter() - start)
    duration = time.perf_counter() - start
    failures = [m for exp in case.expect if (m := check(exp, output)) is not None]
    return RunResult(passed=not failures, output=output, failures=failures, duration=duration)


def run_suite(
    suite: Suite,
    provider: Provider,
    repeat: int = 1,
    on_result: Callable[[TestResult], None] | None = None,
) -> list[TestResult]:
    """Run every test ``repeat`` times; tests that pass only sometimes are reported as flaky."""
    if repeat < 1:
        raise ValueError("repeat must be >= 1")
    results: list[TestResult] = []
    for case in suite.tests:
        result = TestResult(name=case.name, runs=[run_case(case, provider) for _ in range(repeat)])
        results.append(result)
        if on_result:
            on_result(result)
    return results


def summarize(results: list[TestResult]) -> dict[str, Any]:
    counts = {"pass": 0, "fail": 0, "flaky": 0, "error": 0}
    for r in results:
        counts[r.status] += 1
    return {"total": len(results), **counts}
