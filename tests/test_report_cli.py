from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from conftest import FakeLLM
from prompt_eval_lite import MockProvider, RunResult, TestResult, compare, load_report, load_suite
from prompt_eval_lite import run_suite as run
from prompt_eval_lite.baseline import BaselineError, format_comparison
from prompt_eval_lite.cli import main
from prompt_eval_lite.report import build_report, format_table, to_json, to_junit

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
SUITE = str(EXAMPLES / "suite.json")


@pytest.mark.parametrize("bad", ["\x00", "\x1b", "\x0b", "\ud800", "\ufffe", "\uffff"])
def test_junit_sanitizes_xml_text_and_attributes(bad: str) -> None:
    text = f"before{bad}after"
    rs = [
        TestResult(text, [RunResult(False, output=text, error=text)]),
        TestResult("failure", [RunResult(False, output=text, failures=[text])]),
    ]
    root = ET.fromstring(to_junit(text, rs))
    assert root.get("name") == "before\ufffdafter"
    assert root.find("testcase").get("name") == "before\ufffdafter"
    assert root.find("testcase/system-out").text == "before\ufffdafter"
    assert root.find("testcase/error").get("message") == "before\ufffdafter"
    assert "before\ufffdafter" in root.find("testcase/failure").text


def results() -> list[TestResult]:
    suite = load_suite(SUITE)
    provider = MockProvider(**{k: v for k, v in suite.provider.items() if k != "type"})
    return run(suite, provider, repeat=3)


def test_table_and_color() -> None:
    plain = format_table(results())
    assert "summary-no-email" in plain
    assert "4 tests: 2 passed, 1 failed, 1 flaky, 0 errored" in plain
    assert "\x1b[" not in plain
    assert "\x1b[31m" in format_table(results(), color=True)


def test_junit_structure() -> None:
    root = ET.fromstring(to_junit("support-bot", results()))
    assert root.tag == "testsuite"
    assert root.get("tests") == "4"
    assert root.get("failures") == "2"  # one failed + one flaky
    assert root.get("errors") == "0"
    cases = {c.get("name"): c for c in root.findall("testcase")}
    assert cases["capital"].find("failure") is None
    assert cases["summary-no-email"].find("failure") is not None
    flaky = cases["greeting"].find("failure")
    assert flaky is not None and "flaky" in (flaky.get("message") or "")


def test_junit_error_element() -> None:
    err = TestResult("t", [RunResult(False, error="down")])
    root = ET.fromstring(to_junit("s", [err]))
    assert root.get("errors") == "1"
    assert root.find("testcase/error") is not None


def test_json_report_roundtrip(tmp_path: Path) -> None:
    rs = results()
    report = json.loads(to_json(build_report("s", "mock", 3, rs)))
    assert report["summary"]["flaky"] == 1
    assert report["repeat"] == 3
    assert report["tests"][0]["runs"][0]["output"]
    p = tmp_path / "r.json"
    p.write_text(json.dumps(report), encoding="utf-8")
    assert load_report(p)["suite"] == "s"


def test_compare_detects_regressions_and_improvements() -> None:
    rs = results()
    baseline = {
        "tests": [
            {"name": "capital", "pass_rate": 1.0},
            {"name": "summary-no-email", "pass_rate": 1.0},  # now 0 -> regression
            {"name": "greeting", "pass_rate": 0.0},  # now 0.67 -> improvement
            {"name": "gone", "pass_rate": 1.0},
        ]
    }
    cmp = compare(rs, baseline)
    assert [c.name for c in cmp.regressions] == ["summary-no-email"]
    assert [c.name for c in cmp.improvements] == ["greeting"]
    assert cmp.unchanged == ["capital"]
    assert cmp.new == ["extract-json"]
    assert cmp.removed == ["gone"]
    assert cmp.has_regressions
    text = format_comparison(cmp)
    assert "summary-no-email: 100% -> 0%" in text
    assert "Removed: gone" in text
    assert cmp.to_dict()["regressions"][0]["after"] == 0.0


def test_compare_clean() -> None:
    cmp = compare(results(), {"tests": []})
    assert not cmp.has_regressions
    assert "Regressions: none" in format_comparison(cmp)


def test_baseline_errors(tmp_path: Path) -> None:
    with pytest.raises(BaselineError, match="cannot read"):
        load_report(tmp_path / "x.json")
    bad = tmp_path / "b.json"
    bad.write_text("{", encoding="utf-8")
    with pytest.raises(BaselineError, match="not valid JSON"):
        load_report(bad)
    bad.write_text("[]", encoding="utf-8")
    with pytest.raises(BaselineError, match="not a prompt-eval report"):
        load_report(bad)
    with pytest.raises(BaselineError, match="pass_rate"):
        compare(results(), {"tests": [{"name": "a"}]})


# ---- CLI ----


def test_cli_exit_code_and_outputs(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    junit, js = tmp_path / "out" / "j.xml", tmp_path / "out" / "r.json"
    code = main(["run", SUITE, "--repeat", "3", "--junit", str(junit), "--json", str(js)])
    out = capsys.readouterr().out
    assert code == 1
    assert "support-bot - mock - repeat 3" in out
    assert ET.parse(junit).getroot().get("tests") == "4"
    assert json.loads(js.read_text(encoding="utf-8"))["summary"]["fail"] == 1


def test_cli_baseline_flow(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    suite = tmp_path / "s.json"
    good = {
        "provider": {"type": "mock", "default": "ok"},
        "tests": [{"name": "a", "prompt": "p", "expect": [{"contains": "ok"}]}],
    }
    suite.write_text(json.dumps(good), encoding="utf-8")
    base = tmp_path / "base.json"
    assert main(["run", str(suite), "--json", str(base)]) == 0

    # same suite, regressed model
    bad = {**good, "provider": {"type": "mock", "default": "nope"}}
    suite.write_text(json.dumps(bad), encoding="utf-8")
    capsys.readouterr()
    assert main(["run", str(suite), "--baseline", str(base), "--fail-on", "regression"]) == 1
    assert "a: 100% -> 0%" in capsys.readouterr().out

    # a test that was already failing in the baseline is not a regression
    base2 = tmp_path / "base2.json"
    assert main(["run", str(suite), "--json", str(base2)]) == 1
    assert main(["run", str(suite), "--baseline", str(base2), "--fail-on", "regression"]) == 0
    assert main(["run", str(suite), "--baseline", str(base2)]) == 1


def test_cli_usage_errors(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["run", SUITE, "--repeat", "0"]) == 2
    assert main(["run", SUITE, "--fail-on", "regression"]) == 2
    assert main(["run", str(tmp_path / "missing.json")]) == 2
    assert main(["run", SUITE, "--baseline", str(tmp_path / "missing.json")]) == 2
    err = capsys.readouterr().err
    assert "--repeat" in err and "--baseline" in err and "missing.json" in err


def test_cli_provider_override_http(
    tmp_path: Path, fake_llm: FakeLLM, capsys: pytest.CaptureFixture[str]
) -> None:
    suite = tmp_path / "s.json"
    suite.write_text(
        json.dumps(
            {"tests": [{"name": "t", "prompt": "hello", "expect": [{"contains": "hello"}]}]}
        ),
        encoding="utf-8",
    )
    args = ["run", str(suite), "--model", "m", "--base-url", fake_llm.url, "--no-color"]
    assert main([*args, "--provider", "openai"]) == 0
    assert main([*args, "--provider", "ollama"]) == 0
    assert [r["path"] for r in fake_llm.requests] == ["/chat/completions", "/api/generate"]
    assert "ollama:m" in capsys.readouterr().out


def test_cli_provider_failure_is_reported_not_raised(
    tmp_path: Path, fake_llm: FakeLLM, capsys: pytest.CaptureFixture[str]
) -> None:
    fake_llm.mode = "http500"
    suite = tmp_path / "s.json"
    suite.write_text(json.dumps({"tests": [{"name": "t", "prompt": "x"}]}), encoding="utf-8")
    code = main(
        ["run", str(suite), "--provider", "ollama", "--model", "m", "--base-url", fake_llm.url]
    )
    assert code == 1
    assert "error" in capsys.readouterr().out


def test_cli_bad_provider_config(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    suite = tmp_path / "s.json"
    suite.write_text(json.dumps({"tests": [{"prompt": "x"}]}), encoding="utf-8")
    assert main(["run", str(suite), "--provider", "openai"]) == 2  # no model
    assert "needs 'model'" in capsys.readouterr().err


def test_python_dash_m_entry() -> None:
    import runpy

    with pytest.raises(SystemExit) as exc:
        runpy.run_module("prompt_eval_lite", run_name="__main__", alter_sys=True)
    assert exc.value.code == 2  # argparse: missing subcommand
