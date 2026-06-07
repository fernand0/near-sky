import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from near_opensky.near_opensky import choose_nearest_interval


def test_choose_nearest_interval_prefers_smallest_non_empty_bucket():
    assert choose_nearest_interval(100, [2.0, 6.0, 30.0, 85.0]) == 5


def test_choose_nearest_interval_skips_empty_small_buckets():
    assert choose_nearest_interval(100, [12.0, 34.0, 60.0]) == 15


def test_choose_nearest_interval_returns_none_when_no_planes_within_radius():
    assert choose_nearest_interval(50, [55.0, 80.0]) is None


def test_choose_nearest_interval_allows_small_radius_below_min_interval():
    assert choose_nearest_interval(3, [2.5]) == 3
