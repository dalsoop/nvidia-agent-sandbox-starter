"""End-to-end: build this repo into a real OpenShell sandbox and measure containment.

Opt-in because it needs the `openshell` CLI and a running gateway:

    OPENSHELL_E2E=1 uv run pytest -m e2e -v

The permissive-policy test is the control: if the selfcheck still reported
"sandboxed" under a weakened policy, it would not be measuring anything.
"""

import json
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
POLICY = REPO / "policy" / "openshell-policy.yaml"
PERMISSIVE = REPO / "tests" / "fixtures" / "permissive-policy.yaml"

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        os.environ.get("OPENSHELL_E2E") != "1" or shutil.which("openshell") is None,
        reason="set OPENSHELL_E2E=1 and install the openshell CLI with a running gateway",
    ),
]


def _openshell(*args: str, timeout: int = 900) -> subprocess.CompletedProcess:
    return subprocess.run(["openshell", *args], capture_output=True, text=True, timeout=timeout)


def _selfcheck_in_sandbox(policy: Path) -> tuple[dict, subprocess.CompletedProcess]:
    """Create a sandbox, run the selfcheck in it with `exec`, then delete it.

    `sandbox create -- <cmd>` can race the supervisor session on OpenShell
    0.0.116, so the sandbox is started detached and the check runs once exec
    reaches the container.
    """
    name = f"e2e-{uuid.uuid4().hex[:8]}"  # OpenShell caps names at 19 characters
    created = _openshell(
        "sandbox", "create", "--name", name, "--from", str(REPO), "--policy", str(policy),
        "--detach", "--no-tty", "--no-auto-providers", "--", "sleep", "600",
    )
    assert created.returncode == 0, created.stdout + created.stderr
    try:
        for _ in range(10):
            proc = _openshell("sandbox", "exec", "-n", name, "--no-tty", "--", "python3", "-m", "agent", "--selfcheck", timeout=120)
            if '"sandboxed"' in proc.stdout:
                break
            time.sleep(3)
        return _last_json_block(proc.stdout, proc.stderr), proc
    finally:
        _openshell("sandbox", "delete", name, timeout=120)


def _last_json_block(stdout: str, stderr: str) -> dict:
    """The selfcheck prints an indented object; image build output can precede it."""
    lines = [line.rstrip() for line in stdout.splitlines()]
    starts = [i for i, line in enumerate(lines) if line == "{"]
    for start in reversed(starts):
        end = next((j for j in range(start + 1, len(lines)) if lines[j] == "}"), None)
        if end is not None:
            return json.loads("\n".join(lines[start : end + 1]))
    pytest.fail(f"no JSON report in output:\n{stdout}\n{stderr}")


def test_default_policy_contains_the_agent():
    report, proc = _selfcheck_in_sandbox(POLICY)
    assert report["sandboxed"] is True, json.dumps(report, indent=2) + proc.stdout[-2000:] + proc.stderr
    assert report["uid"] == 10001


def test_permissive_policy_is_detected():
    report, _ = _selfcheck_in_sandbox(PERMISSIVE)
    assert report["sandboxed"] is False
    assert report["egress"]["reachable"] or report["undeclared_dir"]["writable"]
