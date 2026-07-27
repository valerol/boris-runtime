from pathlib import Path
import shutil
import subprocess

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SURFACE_PATH = (
    PROJECT_ROOT
    / "mcp_server"
    / "ui"
    / "developer_surface_v2.html"
)
HARNESS_PATH = (
    PROJECT_ROOT
    / "tests"
    / "developer_surface_bridge_harness.js"
)
NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="Node.js is not available.")
def test_operator_resume_wakes_host_through_standard_bridge_with_retry():
    result = subprocess.run(
        [NODE, str(HARNESS_PATH), str(SURFACE_PATH)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        check=False,
        text=True,
        timeout=20,
    )

    assert result.returncode == 0, result.stderr
