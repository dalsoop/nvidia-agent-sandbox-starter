import os
import sys
import yaml
from pathlib import Path

def load_config(config_path: str = "config/sandbox.yaml") -> dict:
    path = Path(config_path)
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def run():
    print("=== NVIDIA Agent Sandbox Runner ===")
    config = load_config()
    sandbox_name = config.get("sandbox", {}).get("name", "unknown")
    print(f"Loaded sandbox profile: {sandbox_name}")
    print(f"Current UID/GID: {os.getuid()}/{os.getgid()}")
    print(f"Working Directory: {os.getcwd()}")
    print("Agent ready for hackathon task execution.")

if __name__ == "__main__":
    run()
