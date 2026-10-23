"""Terminal table, JSON and JUnit XML reporters."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from typing import Any

from .baseline import Comparison
from .models import TestResult
from .runner import summarize

_COLORS = {"pass": "32", "fail": "31", "error": "31", "flaky": "33"}


def _clip(text: str, width: int) -> str:
    text = text.replace("\n", " ")
    return text if len(text) <= width else text[: width - 3] + "..."


def format_table(results: list[TestResult], color: bool = False, width: int = 48) -> str:
    rows = []
    for r in results:
        detail = "; ".join(r.messages())
        rows.append((r.name, r.status, f"{r.pass_rate:.0%}", f"{r.duration:.2f}s", detail))
    head = ("TEST", "STATUS", "PASS", "TIME")
    w_name = max([len(head[0])] + [len(x[0]) for x in rows])
    w_stat = max(len(head[1]), 6)
    lines = [f"{head[0]:<{w_name}}  {head[1]:<{w_stat}}  {head[2]:>5}  {head[3]:>7}  DETAIL"]
    for name, status, rate, dur, detail in rows:
        shown = f"{status:<{w_stat}}"
        if color:
            shown = f"\x1b[{_COLORS[status]}m{shown}\x1b[0m"
        lines.append(f"{name:<{w_name}}  {shown}  {rate:>5}  {dur:>7}  {_clip(detail, width)}")
    s = summarize(results)
    lines.append("")
    lines.append(
        f"{s['total']} tests: {s['pass']} passed, {s['fail']} failed, "
        f"{s['flaky']} flaky, {s['error']} errored"
    )
    return "\n".join(lines)


def build_report(
    suite_name: str,
    provider_label: str,
    repeat: int,
    results: list[TestResult],
    comparison: Comparison | None = None,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "suite": suite_name,
        "provider": provider_label,
        "repeat": repeat,
        "summary": summarize(results),
        "tests": [r.to_dict() for r in results],
    }
    if comparison is not None:
        report["comparison"] = comparison.to_dict()
    return report


def to_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, ensure_ascii=False) + "\n"


def to_junit(suite_name: str, results: list[TestResult]) -> str:
    """JUnit XML. Failed, flaky and errored tests all count as failing for CI."""
    s = summarize(results)
    root = ET.Element(
        "testsuite",
        name=suite_name,
        tests=str(s["total"]),
        failures=str(s["fail"] + s["flaky"]),
        errors=str(s["error"]),
        skipped="0",
        time=f"{sum(r.duration for r in results):.3f}",
    )
    for r in results:
        case = ET.SubElement(
            root, "testcase", classname=suite_name, name=r.name, time=f"{r.duration:.3f}"
        )
        message = "; ".join(r.messages()) or r.status
        if r.status == "error":
            ET.SubElement(case, "error", message=message, type="ProviderError").text = message
        elif r.status in ("fail", "flaky"):
            label = r.status if r.status == "fail" else f"flaky ({r.pass_rate:.0%} pass rate)"
            text = f"{label}: {message}"
            ET.SubElement(case, "failure", message=text, type="AssertionError").text = text
        if r.runs:
            ET.SubElement(case, "system-out").text = r.runs[-1].output
    ET.indent(root)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n"
