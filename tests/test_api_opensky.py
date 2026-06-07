import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import types
import pytest

from near_opensky import api


class FakeStates:
    def __init__(self, states):
        self.states = states


class FakeState:
    def __init__(self, lat, lon, callsign=None, icao24="abc", geo_altitude=None, on_ground=False):
        self.latitude = lat
        self.longitude = lon
        self.callsign = callsign
        self.icao24 = icao24
        self.geo_altitude = geo_altitude
        self.on_ground = on_ground


def test_fetch_opensky_positions_no_states(monkeypatch):
    class DummyApi:
        def get_states(self, bbox=None):
            return None

    monkeypatch.setattr(api, "OpenSkyApi", lambda: DummyApi())
    positions, states = api.fetch_opensky_positions((0, 0, 0, 0), 0.0, 0.0)
    assert positions == []
    assert states is None


def test_fetch_opensky_positions_returns_positions_and_states(monkeypatch):
    fake_state = FakeState(0.0, 0.0, callsign="CALL1", icao24="id1", geo_altitude=10000)
    fake_states = FakeStates([fake_state])

    class DummyApi:
        def get_states(self, bbox=None):
            return fake_states

    monkeypatch.setattr(api, "OpenSkyApi", lambda: DummyApi())
    positions, states = api.fetch_opensky_positions((0, 0, 0, 0), 0.0, 0.0)
    assert len(positions) == 1
    p = positions[0]
    assert p.latitude == fake_state.latitude
    assert p.longitude == fake_state.longitude
    assert states is fake_states
