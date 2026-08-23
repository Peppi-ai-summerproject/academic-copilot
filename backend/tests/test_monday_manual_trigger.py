from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


def test_manual_monday_trigger_refuses_to_run_without_confirmation():
    backend_dir = Path(__file__).resolve().parents[1]
    environment = dict(os.environ)
    environment["DEBUG"] = "false"

    result = subprocess.run(
        [sys.executable, str(backend_dir / "scripts" / "run_monday_briefing.py")],
        cwd=backend_dir,
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    assert result.returncode == 2
    assert "--confirm-send is required" in result.stderr
    assert "status=" not in result.stdout
