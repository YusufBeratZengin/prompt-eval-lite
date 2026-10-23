"""Render docs/demo.svg from the real CLI output of examples/suite.json.

Usage: python scripts/make-demo.py
"""

from __future__ import annotations

import contextlib
import io
import re
import sys
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from prompt_eval_lite.cli import main  # noqa: E402

COMMAND = "prompt-eval run examples/suite.json --repeat 3"
COLORS = {"pass": "#3fb950", "fail": "#f85149", "error": "#f85149", "flaky": "#d29922"}


def capture() -> tuple[str, int]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = main(["run", "examples/suite.json", "--repeat", "3", "--no-color"])
    return buf.getvalue().rstrip("\n"), code


def line_color(line: str) -> str:
    match = re.search(r"\s(pass|fail|flaky|error)\s", line)
    if match and not line.startswith("TEST"):
        return COLORS[match.group(1)]
    return "#d1d5db"


def render(output: str) -> str:
    lines = [("$ " + COMMAND, "#a5b4fc"), *[(ln, line_color(ln)) for ln in output.split("\n")]]
    width = int(max(760, max(len(t) for t, _ in lines) * 8.4 + 64))
    height = 90 + 22 * len(lines)
    rows = "\n".join(
        f'    <text x="32" y="{84 + 22 * i}" fill="{color}">{escape(text)}</text>'
        for i, (text, color) in enumerate(lines)
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" \
viewBox="0 0 {width} {height}" role="img" aria-labelledby="t d">
  <title id="t">prompt-eval-lite terminal output</title>
  <desc id="d">Real output of {escape(COMMAND)}: two tests pass, one fails, one is flaky.</desc>
  <rect x="1" y="1" width="{width - 2}" height="{height - 2}" rx="12" fill="#0d1117" \
stroke="#30363d"/>
  <circle cx="24" cy="24" r="6" fill="#ff5f57"/>
  <circle cx="44" cy="24" r="6" fill="#febc2e"/>
  <circle cx="64" cy="24" r="6" fill="#28c840"/>
  <g font-family="ui-monospace, SFMono-Regular, Consolas, monospace" font-size="14" \
xml:space="preserve">
{rows}
  </g>
</svg>
"""


def run() -> None:
    import os

    os.chdir(ROOT)
    output, code = capture()
    assert code == 1, "demo suite is expected to contain a failing test"
    out = ROOT / "docs" / "demo.svg"
    out.parent.mkdir(exist_ok=True)
    out.write_text(render(output), encoding="utf-8", newline="\n")
    print(f"wrote {out.relative_to(ROOT)}")
    print(output)


if __name__ == "__main__":
    run()
