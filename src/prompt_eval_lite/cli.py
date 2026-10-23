"""Command line interface: ``prompt-eval run suite.json``."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .baseline import BaselineError, compare, format_comparison, load_report
from .loader import LoadError, load_suite
from .providers import ProviderError, make_provider
from .report import build_report, format_table, to_json, to_junit
from .runner import run_suite

EXIT_OK, EXIT_FAIL, EXIT_USAGE = 0, 1, 2


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="prompt-eval", description="Regression tests for LLM prompts.")
    p.add_argument("--version", action="version", version=f"prompt-eval {__version__}")
    sub = p.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run", help="run a test suite (JSON or YAML)")
    r.add_argument("suite", help="path to the suite file")
    r.add_argument("--provider", choices=["mock", "openai", "ollama"], help="override provider")
    r.add_argument("--model", help="override model name")
    r.add_argument("--base-url", help="override provider base URL")
    r.add_argument("--repeat", type=int, default=1, metavar="N", help="runs per test (flakiness)")
    r.add_argument("--baseline", metavar="FILE", help="JSON report from an earlier run")
    r.add_argument(
        "--fail-on",
        choices=["any", "regression"],
        default="any",
        help="exit 1 on any failing test (default) or only on regressions vs --baseline",
    )
    r.add_argument("--junit", metavar="FILE", help="write JUnit XML")
    r.add_argument("--json", metavar="FILE", dest="json_out", help="write JSON report")
    r.add_argument("--no-color", action="store_true", help="disable ANSI colors")
    return p


def _provider_config(args: argparse.Namespace, suite_cfg: dict[str, Any]) -> dict[str, Any]:
    cfg = dict(suite_cfg)
    if args.provider and args.provider != cfg.get("type"):
        cfg = {"type": args.provider}
    if args.model:
        cfg["model"] = args.model
    if args.base_url:
        cfg["base_url"] = args.base_url
    cfg.setdefault("type", "mock")
    return cfg


def _write(path: str, text: str) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8", newline="\n")


def cmd_run(args: argparse.Namespace) -> int:
    if args.repeat < 1:
        print("error: --repeat must be >= 1", file=sys.stderr)
        return EXIT_USAGE
    if args.fail_on == "regression" and not args.baseline:
        print("error: --fail-on regression needs --baseline", file=sys.stderr)
        return EXIT_USAGE
    try:
        suite = load_suite(args.suite)
        provider = make_provider(_provider_config(args, suite.provider))
        baseline = load_report(args.baseline) if args.baseline else None
    except (LoadError, ProviderError, BaselineError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE

    results = run_suite(suite, provider, repeat=args.repeat)
    comparison = compare(results, baseline) if baseline is not None else None

    color = not args.no_color and sys.stdout.isatty() and "NO_COLOR" not in os.environ
    print(f"{suite.name} - {provider.label} - repeat {args.repeat}\n")
    print(format_table(results, color=color))
    if comparison is not None:
        print("\n" + format_comparison(comparison))

    if args.json_out:
        _write(
            args.json_out,
            to_json(build_report(suite.name, provider.label, args.repeat, results, comparison)),
        )
    if args.junit:
        _write(args.junit, to_junit(suite.name, results))

    if args.fail_on == "regression":
        failed = bool(comparison and comparison.has_regressions)
    else:
        failed = any(r.status != "pass" for r in results) or bool(
            comparison and comparison.has_regressions
        )
    return EXIT_FAIL if failed else EXIT_OK


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "run":
        return cmd_run(args)
    return EXIT_USAGE  # pragma: no cover
