"""Validate the policy with NVIDIA's own parser (openshell-prover), when installed.

The prover rejects unknown fields and requires `version: 1`, so passing here
means the file is a real OpenShell policy, not just valid YAML.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
POLICY = REPO / "policy" / "openshell-policy.yaml"
PERMISSIVE = REPO / "tests" / "fixtures" / "permissive-policy.yaml"
PROVER = shutil.which("openshell-prover")

pytestmark = pytest.mark.skipif(PROVER is None, reason="openshell-prover is not on PATH")


def _check(candidate: Path, boundary: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [PROVER, "check", str(candidate), "--boundary", str(boundary)],
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_policy_is_accepted_by_the_openshell_parser():
    proc = _check(POLICY, POLICY)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_permissive_fixture_is_strictly_weaker_than_the_policy():
    proc = _check(PERMISSIVE, POLICY)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "example.com" in proc.stdout
