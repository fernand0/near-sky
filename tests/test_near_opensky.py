import os
import subprocess
import sys
from pathlib import Path


def run_cli(args):
    """Run the near-opensky CLI with the given args list and return (stdout, stderr, returncode)."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    result = subprocess.run(
        [sys.executable, "-m", "near_opensky.near_opensky"] + args,
        capture_output=True,
        text=True,
        env=env,
    )
    return result.stdout, result.stderr, result.returncode


def test_help_shows_usage():
    stdout, stderr, rc = run_cli(["--help"])
    assert rc == 0
    assert "usage:" in stdout.lower()
    assert stderr == ""


def test_unknown_argument_fails():
    stdout, stderr, rc = run_cli(["--unknown-flag"])
    assert rc != 0
    assert "unrecognized arguments" in stderr.lower()
