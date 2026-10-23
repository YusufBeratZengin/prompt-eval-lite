"""Shared fixtures: a loopback fake LLM server, so no real network is ever used."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest


class FakeLLM:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.mode = "ok"  # ok | http500 | badjson | badshape
        self.server: ThreadingHTTPServer | None = None

    @property
    def url(self) -> str:
        assert self.server is not None
        return f"http://127.0.0.1:{self.server.server_address[1]}"


@pytest.fixture
def fake_llm() -> Iterator[FakeLLM]:
    state = FakeLLM()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:
            pass

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            state.requests.append(
                {"path": self.path, "body": body, "auth": self.headers.get("Authorization")}
            )
            if state.mode == "http500":
                self._send(500, b'{"error": "boom"}')
                return
            if state.mode == "badjson":
                self._send(200, b"not json")
                return
            if state.mode == "badshape":
                self._send(200, b'{"unexpected": true}')
                return
            if self.path == "/chat/completions":
                prompt = body["messages"][-1]["content"]
                payload = {"choices": [{"message": {"content": f"echo: {prompt}"}}]}
            elif self.path == "/api/generate":
                payload = {"response": f"ollama: {body['prompt']}", "done": True}
            else:
                self._send(404, b"{}")
                return
            self._send(200, json.dumps(payload).encode())

        def _send(self, code: int, data: bytes) -> None:
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    state.server = server
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
