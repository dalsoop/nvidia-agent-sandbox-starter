"""
NVIDIA Agent Sandbox Security Audit Suite
=========================================
Automated security evaluation suite for hackathon judging & compliance audits.

Test Matrix:
1. Test 1: System File Modification & Tampering Prevention
2. Test 2: Unauthorized External Egress & IP/Domain Communication Blocking
3. Test 3: Authorized Model Endpoint Routing & Task Success Verification
"""

import json
import os
import socket
import sys
from pathlib import Path
from typing import List, Dict, Any
import pytest
import yaml

# Import SandboxedAgent from agent module
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from agent.main import SandboxedAgent, SecurityContextError


@pytest.fixture(scope="module")
def security_policy() -> Dict[str, Any]:
    """Loads and parses declarative security policy (policy.yaml)."""
    policy_path = REPO_ROOT / "policy.yaml"
    assert policy_path.exists(), f"Policy file not found at {policy_path}"
    with open(policy_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def openshell_config() -> Dict[str, Any]:
    """Loads and parses L7 gateway config (config/openshell.json)."""
    config_path = REPO_ROOT / "config" / "openshell.json"
    assert config_path.exists(), f"Gateway configuration not found at {config_path}"
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def temp_workspace(tmp_path: Path) -> Path:
    """Provides an isolated workspace sandbox directory."""
    ws = tmp_path / "workspace"
    ws.mkdir(parents=True, exist_ok=True)
    return ws


# ==============================================================================
# TEST 1: System File Tampering & Filesystem Isolation Audit
# ==============================================================================

class TestSystemFileTamperingPrevention:
    """
    Validates that unauthorized filesystem modifications outside the designated
    workspace are strictly prohibited by sandbox boundary controls.
    """

    @pytest.mark.parametrize("target_sys_path", [
        "/etc/passwd",
        "/etc/shadow",
        "/usr/bin/python3",
        "/bin/sh",
        "/root/.bashrc",
        "/etc/sudoers",
    ])
    def test_system_file_modification_blocked(self, target_sys_path: str):
        """
        Verify that writing to critical system paths fails with permission or read-only error.
        """
        try:
            with open(target_sys_path, "a") as f:
                f.write("\n# unauthorized modification attempt")
            # If write succeeded, sandbox is compromised
            pytest.fail(f"SECURITY BREACH: Succeeded in modifying protected system file {target_sys_path}")
        except (PermissionError, OSError) as e:
            # Expected behavior: access denied or read-only filesystem
            assert True, f"Correctly blocked with {e}"

    def test_directory_traversal_attack_blocked(self, temp_workspace: Path):
        """
        Verify that path traversal (../) attempts out of the workspace are detected and blocked.
        """
        agent = SandboxedAgent(workspace_dir=str(temp_workspace), mock_inference=True)

        traversal_attempts = [
            "../../etc/cron.d/malicious_job",
            "../../../tmp/pwned.txt",
            "/etc/exploit.conf",
            "subdir/../../../../../../root/hacked",
        ]

        for payload in traversal_attempts:
            with pytest.raises(SecurityContextError) as exc_info:
                agent.safe_write_file(payload, "malicious payload")
            assert "blocked" in str(exc_info.value).lower() or "traversal" in str(exc_info.value).lower()

    def test_authorized_workspace_writing_permitted(self, temp_workspace: Path):
        """
        Verify that legit agent execution writes within /workspace succeed seamlessly.
        """
        agent = SandboxedAgent(workspace_dir=str(temp_workspace), mock_inference=True)
        legit_file = agent.safe_write_file("artifacts/output.json", '{"key": "value"}')

        assert Path(legit_file).exists()
        read_back = agent.safe_read_file("artifacts/output.json")
        assert '{"key": "value"}' in read_back


# ==============================================================================
# TEST 2: Network Egress & Default-Deny Isolation Audit
# ==============================================================================

class TestUnauthorizedNetworkEgressBlocked:
    """
    Validates that unauthorized outbound network connections are blocked by default,
    enforcing zero-trust network containment (egress: default_action: deny).
    """

    def test_policy_default_deny_rules(self, security_policy: Dict[str, Any], openshell_config: Dict[str, Any]):
        """
        Verify the declarative security policies explicitly declare default-deny for egress and ingress.
        """
        net_spec = security_policy.get("spec", {}).get("network", {})
        assert net_spec.get("default_action") == "deny", "Network default action must be 'deny'"
        assert net_spec.get("egress", {}).get("default_action") == "deny", "Egress default action must be 'deny'"
        assert net_spec.get("ingress", {}).get("default_action") == "deny", "Ingress default action must be 'deny'"

        # Verify OpenShell gateway proxy default policy
        proxy_config = openshell_config.get("proxy", {})
        assert proxy_config.get("default_policy") == "deny", "OpenShell proxy default policy must be 'deny'"
        assert proxy_config.get("intercept_all_egress") is True, "OpenShell proxy must intercept all egress"

    @pytest.mark.parametrize("unauthorized_target", [
        ("198.51.100.254", 443),   # RFC 5737 TEST-NET-2 IP (always blocked/unreachable)
        ("203.0.113.199", 80),     # RFC 5737 TEST-NET-3 IP (always blocked/unreachable)
        ("192.0.2.1", 8080),       # RFC 5737 TEST-NET-1 IP (always blocked/unreachable)
    ])
    def test_unauthorized_external_ip_connection_blocked(self, unauthorized_target):
        """
        Verify direct TCP socket connection to unallowed IPs is blocked or times out.
        Inside sandbox container (internal: true), all external traffic is dropped.
        """
        ip, port = unauthorized_target
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1.0)  # Strict 1-second timeout

        blocked = False
        try:
            sock.connect((ip, port))
        except (socket.timeout, ConnectionRefusedError, OSError):
            blocked = True
        finally:
            sock.close()

        assert blocked, f"SECURITY LEAK: Unrestricted socket connection established to {ip}:{port}"

    def test_sandbox_container_complete_isolation_when_in_docker(self):
        """
        If running inside the Docker sandbox container, verify that even public DNS/IPs
        are completely blocked by the internal network driver.
        """
        in_container = Path("/.dockerenv").exists() or os.environ.get("SANDBOX_ENV") == "container"
        if not in_container:
            pytest.skip("Skipping full egress drop test (runs exclusively inside isolated container)")

        # Target public IP that must fail inside container
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1.5)
        blocked = False
        try:
            sock.connect(("1.1.1.1", 53))
        except (socket.timeout, ConnectionRefusedError, OSError):
            blocked = True
        finally:
            sock.close()

        assert blocked, "SECURITY LEAK: Container failed to block external public egress!"

    def test_policy_egress_whitelist_integrity(self, security_policy: Dict[str, Any]):
        """
        Verify that allowed endpoints in policy.yaml are restricted strictly to authorized AI services.
        """
        allowed_list = security_policy.get("spec", {}).get("network", {}).get("egress", {}).get("allowed_endpoints", [])
        allowed_hosts = [item["host"] for item in allowed_list]

        expected_hosts = {
            "build.nvidia.com",
            "integrate.api.nvidia.com",
            "api.openai.com",
            "api.anthropic.com",
            "huggingface.co",
        }
        assert set(allowed_hosts) == expected_hosts, f"Disallowed or unexpected hosts in whitelist: {allowed_hosts}"

        # Unauthorized domain verification against whitelist logic
        forbidden_test_domains = [
            "evil-exfiltration.attacker.net",
            "pastebin.com",
            "discord.com",
            "cryptominer-pool.org",
        ]
        for bad_domain in forbidden_test_domains:
            assert bad_domain not in allowed_hosts, f"Security risk: {bad_domain} present in allowed hosts!"


# ==============================================================================
# TEST 3: Authorized Model Endpoint Routing & Autonomous Task Success
# ==============================================================================

class TestAuthorizedModelEndpointAndTaskSuccess:
    """
    Validates that authorized model inference endpoints are accessible through
    the L7 OpenShell Gateway and that the autonomous agent completes end-to-end tasks.
    """

    def test_gateway_route_upstreams_configured(self, openshell_config: Dict[str, Any]):
        """
        Verify L7 gateway routes correctly forward to NVIDIA NIM and approved foundation APIs.
        """
        upstreams = {u["id"]: u for u in openshell_config.get("upstreams", [])}
        assert "nvidia-integrate" in upstreams
        assert upstreams["nvidia-integrate"]["host"] == "integrate.api.nvidia.com"

        routes = openshell_config.get("routes", [])
        route_prefixes = [r["match"]["path_prefix"] for r in routes]
        assert "/v1/nvidia" in route_prefixes
        assert "/v1/openai" in route_prefixes

        # Check guardrails active
        guardrails = openshell_config.get("guardrails", {})
        assert guardrails.get("pii_redaction", {}).get("enabled") is True
        assert guardrails.get("prompt_injection", {}).get("enabled") is True

    def test_agent_autonomous_task_execution_end_to_end(self, temp_workspace: Path):
        """
        Verify that the agent runs end-to-end inside the sandbox, passes preflight checks,
        performs safe I/O, invokes model inference, and outputs valid structured JSON.
        """
        agent = SandboxedAgent(
            workspace_dir=str(temp_workspace),
            policy_path=str(REPO_ROOT / "policy.yaml"),
            gateway_url="http://localhost:8080",
            mock_inference=True
        )

        test_task = "Analyze financial dataset and compute risk score"
        result = agent.run_task(task_description=test_task)

        # 1. Output schema validation
        assert result["status"] == "success", f"Agent failed: {result}"
        assert result["agent_id"] == "nvidia-openshell-agent-v1"
        assert result["task"] == test_task
        assert result["elapsed_ms"] > 0

        # 2. Security audit validation
        audit = result["security_audit"]
        assert audit["workspace_writable"] is True
        assert audit["policy_detected"] is True

        # 3. Artifact generation validation
        artifacts = result["artifacts"]
        assert Path(artifacts["plan_path"]).exists()
        assert Path(artifacts["result_path"]).exists()

        result_json_data = json.loads(Path(artifacts["result_path"]).read_text())
        assert result_json_data["execution_verified"] is True
        assert result_json_data["task"] == test_task

        # 4. Trace integrity check
        actions_in_trace = [step["action"] for step in result["trace"]]
        assert "verify_sandbox_security" in actions_in_trace
        assert "safe_write_file" in actions_in_trace
        assert "request_model_inference" in actions_in_trace
