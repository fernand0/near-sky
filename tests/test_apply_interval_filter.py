import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from near_sky.near_sky import _apply_interval_filter


def test_apply_interval_filter_mixed_coords():
    center = (0.0, 0.0)
    # pos1 uses latitude/longitude, pos2 uses lat/lon, pos3 far away
    pos1 = SimpleNamespace(latitude=0.0, longitude=0.0, grounded=False, alt_km=None, dest="", ident="P1", mag_heading=None, icao24="p1")
    pos2 = SimpleNamespace(lat=0.04, lon=0.0, grounded=False, alt_km=None, dest="", ident="P2", mag_heading=None, icao24="p2")
    pos3 = SimpleNamespace(lat=0.5, lon=0.0, grounded=False, alt_km=None, dest="", ident="P3", mag_heading=None, icao24="p3")

    filtered = _apply_interval_filter([pos1, pos2, pos3], center, 100)
    # pos1 and pos2 should be within the 5 km interval
    idents = sorted([p.ident for p in filtered])
    assert idents == ["P1", "P2"]


def test_apply_interval_filter_no_matches():
    center = (0.0, 0.0)
    pos_far1 = SimpleNamespace(lat=0.6, lon=0.0, grounded=False, alt_km=None, dest="", ident="F1", mag_heading=None, icao24="f1")
    pos_far2 = SimpleNamespace(lat=0.8, lon=0.0, grounded=False, alt_km=None, dest="", ident="F2", mag_heading=None, icao24="f2")

    filtered = _apply_interval_filter([pos_far1, pos_far2], center, 50)
    assert filtered == []
