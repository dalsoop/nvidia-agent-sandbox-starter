"""Measure whether this process is actually contained. Makes no model call.

Each probe tries the forbidden action for real and reports what happened.
The run counts as sandboxed only if every forbidden action failed and the
workspace is still writable. Outside a sandbox the report says so.
"""

from __future__ import annotations

import errno
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

PROBE_NAME = ".agent-selfcheck"


def _try_write(directory: str | Path) -> dict[str, Any]:
    probe = Path(directory) / PROBE_NAME
    try:
        probe.write_text("probe", encoding="utf-8")
        probe.unlink()
        return {"path": str(directory), "writable": True}
    except OSError as error:
        return {"path": str(directory), "writable": False, "error": errno.errorcode.get(error.errno or 0, str(error))}


def _try_egress(url: str, timeout: float) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return {"url": url, "reachable": True, "status": response.status}
    except urllib.error.HTTPError as error:
        return {"url": url, "reachable": True, "status": error.code}
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        reason = getattr(error, "reason", error)
        return {"url": url, "reachable": False, "error": str(reason)[:160]}


def selfcheck(
    workspace: str | Path,
    *,
    egress_url: str = "https://example.com/",
    system_dir: str = "/usr",
    undeclared_dir: str = "/var/tmp",
    timeout: float = 5.0,
) -> dict[str, Any]:
    uid = os.getuid()
    report: dict[str, Any] = {
        "uid": uid,
        "is_root": uid == 0,
        "real_nvidia_key_in_env": sorted(k for k, v in os.environ.items() if v.startswith("nvapi-")),
    }
    if uid == 0:
        # Write probes as root would modify system directories; refuse instead.
        report["probes"] = "skipped: running as root"
        report["sandboxed"] = False
        return report

    report["workspace"] = _try_write(workspace)
    report["system_dir"] = _try_write(system_dir)
    report["undeclared_dir"] = _try_write(undeclared_dir)
    report["egress"] = _try_egress(egress_url, timeout)
    report["sandboxed"] = (
        report["workspace"]["writable"]
        and not report["system_dir"]["writable"]
        and not report["undeclared_dir"]["writable"]
        and not report["egress"]["reachable"]
        and not report["real_nvidia_key_in_env"]
    )
    return report
