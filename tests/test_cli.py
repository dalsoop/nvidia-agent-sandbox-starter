"""Run the real entry point as a subprocess against the scripted server."""

import json
import os
import subprocess
import sys
from pathlib import Path

from tests.conftest import final, tool_call

REPO = Path(__file__).resolve().parent.parent


def _agent(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    base_env = {k: v for k, v in os.environ.items() if k not in {"NVIDIA_API_KEY", "LLM_BASE_URL", "LLM_MODEL"}}
    return subprocess.run(
        [sys.executable, "-m", "agent", *args],
        cwd=REPO,
        env={**base_env, "PYTHONPATH": str(REPO), **(env or {})},
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_successful_run_prints_json_and_exits_zero(fake_llm, tmp_path: Path):
    fake_llm.reply(tool_call("write_file", {"path": "hello.txt", "content": "hi"}))
    fake_llm.reply(final("done"))
    proc = _agent("write hello", "--workspace", str(tmp_path), "--base-url", fake_llm.base_url)
    payload = json.loads(proc.stdout)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert payload["status"] == "success" and payload["endpoint"] == "custom"
    # Report the model that answered, not only the one requested.
    assert payload["served_model"] == "served-model" and payload["requested_model"] != "served-model"
    assert (tmp_path / "hello.txt").read_text() == "hi"


def test_model_failure_exits_three_and_never_fakes_success(fake_llm, tmp_path: Path):
    fake_llm.error(400, "bad request")
    proc = _agent("anything", "--workspace", str(tmp_path), "--base-url", fake_llm.base_url)
    assert proc.returncode == 3
    payload = json.loads(proc.stdout)
    assert payload["status"] == "llm_error" and "bad request" in payload["error"]


def test_nim_without_key_is_a_config_error(tmp_path: Path):
    proc = _agent("anything", "--workspace", str(tmp_path), "--base-url", "https://integrate.api.nvidia.com/v1")
    assert proc.returncode == 2
    assert json.loads(proc.stdout)["status"] == "config_error"


def test_selfcheck_on_a_normal_host_reports_not_sandboxed(tmp_path: Path):
    proc = _agent("--selfcheck", "--workspace", str(tmp_path), "--egress-url", "http://127.0.0.1:9/")
    report = json.loads(proc.stdout)
    assert report["sandboxed"] is False and proc.returncode == 1
