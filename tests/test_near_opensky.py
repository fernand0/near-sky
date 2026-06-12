import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import near_sky.near_sky as near_sky


def run_cli(args):
    """Run the near-opensky CLI with the given args list and return (stdout, stderr, returncode)."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    result = subprocess.run(
        [sys.executable, "-m", "near_sky.near_sky"] + args,
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


def test_airplanes_live_uses_nearest_interval(monkeypatch, capsys):
    fake_positions = [
        type(
            "P",
            (),
            {
                "lat": 0.0,
                "lon": 0.0,
                "grounded": False,
                "alt_km": 10.0,
                "dest": "",
                "ident": "ABC123",
                "mag_heading": None,
                "icao24": "abc",
            },
        ),
        type(
            "P",
            (),
            {
                "lat": 0.5,
                "lon": 0.0,
                "grounded": False,
                "alt_km": 10.0,
                "dest": "",
                "ident": "DEF456",
                "mag_heading": None,
                "icao24": "def",
            },
        ),
    ]

    def fake_fetch(center_lat, center_lon, radius_km):
        return fake_positions

    monkeypatch.setattr(near_sky, "fetch_airplanes_live_positions", fake_fetch)
    monkeypatch.setattr(near_sky.origin, "ORIGIN_LAT", 0.0)
    monkeypatch.setattr(near_sky.origin, "ORIGIN_LON", 0.0)

    near_sky.display_nearby_aircraft(100, airplanes_live=True)
    captured = capsys.readouterr()

    assert "Showing planes within the nearest interval" in captured.out
    assert "Fetched 1 aircraft" in captured.out
