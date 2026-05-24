import subprocess
import sys
import tempfile
from pathlib import Path


def run_cli(args):
    """Run the near-opensky CLI with the given args list and return (stdout, stderr, returncode)."""
    script_path = Path(__file__).resolve().parents[2] / "near-opensky.py"
    result = subprocess.run([sys.executable, str(script_path)] + args, capture_output=True, text=True)
    return result.stdout, result.stderr, result.returncode


def test_happy_path():
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as tmp:
        tmp.write('Hello, world!')
        tmp_path = tmp.name
    stdout, stderr, rc = run_cli([tmp_path])
    assert rc == 0
    assert stdout.strip() == 'Hello, world!'
    assert stderr == ''


def test_file_not_found():
    non_existent = 'nonexistent_file_12345.txt'
    stdout, stderr, rc = run_cli([non_existent])
    assert rc == 1
    assert 'Error: File not found' in stdout
    assert stderr == ''
