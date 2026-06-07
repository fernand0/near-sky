import sys
from pathlib import Path
# Add src directory to PYTHONPATH for package imports in tests
sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

import math
import pytest

from near_opensky import origin
from near_opensky.utils import calculate_bbox

def test_default_origin():
    assert origin.ORIGIN_LAT == 41.6562
    assert origin.ORIGIN_LON == -0.8778

def test_calculate_bbox_center():
    # radius 0 should give the same point
    radius = 0
    lat_min, lat_max, lon_min, lon_max = calculate_bbox(origin.ORIGIN_LAT, origin.ORIGIN_LON, radius)
    assert math.isclose(lat_min, origin.ORIGIN_LAT)
    assert math.isclose(lat_max, origin.ORIGIN_LAT)
    assert math.isclose(lon_min, origin.ORIGIN_LON)
    assert math.isclose(lon_max, origin.ORIGIN_LON)
