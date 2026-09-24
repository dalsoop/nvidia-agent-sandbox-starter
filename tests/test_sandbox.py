import os
import yaml
from pathlib import Path

def test_config_file_exists():
    config_file = Path("config/sandbox.yaml")
    assert config_file.exists(), "config/sandbox.yaml should exist"
    with open(config_file, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    assert "sandbox" in data
    assert data["sandbox"]["security"]["read_only_rootfs"] is True
    assert data["sandbox"]["security"]["network_isolation"] is True

def test_compose_file_validity():
    compose_file = Path("docker-compose.yml")
    assert compose_file.exists(), "docker-compose.yml should exist"
    with open(compose_file, "r", encoding="utf-8") as f:
        compose_data = yaml.safe_load(f)
    assert "services" in compose_data
    assert "agent-sandbox" in compose_data["services"]
    svc = compose_data["services"]["agent-sandbox"]
    assert svc.get("read_only") is True
    assert "sandbox-internal" in svc.get("networks", [])
    assert compose_data.get("networks", {}).get("sandbox-internal", {}).get("internal") is True

def test_agent_package():
    from agent import __version__
    from agent.runner import load_config
    assert __version__ == "0.1.0"
    cfg = load_config()
    assert isinstance(cfg, dict)
