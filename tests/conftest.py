"""A scripted OpenAI-compatible server on 127.0.0.1 for offline tests."""

from __future__ import annotations

import json
import threading
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest


class FakeLLM:
    def __init__(self) -> None:
        self.replies: deque[tuple[int, dict[str, Any], dict[str, str]]] = deque()
        self.requests: list[dict[str, Any]] = []
        self.base_url = ""

    def reply(self, message: dict[str, Any], status: int = 200, headers: dict[str, str] | None = None, model: str = "served-model") -> None:
        self.replies.append((status, {"model": model, "choices": [{"index": 0, "message": message}]}, headers or {}))

    def error(self, status: int, detail: str = "error", headers: dict[str, str] | None = None) -> None:
        self.replies.append((status, {"detail": detail}, headers or {}))


def tool_call(name: str, arguments: dict[str, Any], call_id: str = "call_1") -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [{"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}],
    }


def final(text: str) -> dict[str, Any]:
    return {"role": "assistant", "content": text}


@pytest.fixture
def fake_llm():
    fake = FakeLLM()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length) or b"{}")
            fake.requests.append({"path": self.path, "headers": dict(self.headers), "body": body})
            status, payload, headers = fake.replies.popleft() if fake.replies else (500, {"detail": "no scripted reply"}, {})
            data = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            for key, value in headers.items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args: Any) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    fake.base_url = f"http://127.0.0.1:{server.server_port}/v1"
    yield fake
    server.shutdown()
    server.server_close()
