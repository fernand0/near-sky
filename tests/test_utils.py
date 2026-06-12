import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import requests

from near_sky import utils


class DummyResponse:
    def __init__(self, data, status_code=200):
        self._data = data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError()

    def json(self):
        return self._data


def test_get_nearby_cities_caches_results(monkeypatch):
    utils._NEARBY_CITIES_CACHE.clear()
    call_count = {"count": 0}

    def fake_post(url, data, headers, timeout):
        call_count["count"] += 1
        return DummyResponse(
            {
                "elements": [
                    {
                        "tags": {"name": "Sample City", "place": "city"},
                        "lat": 10.0,
                        "lon": 20.0,
                    }
                ]
            }
        )

    monkeypatch.setattr(utils.requests, "post", fake_post)

    first = utils.get_nearby_cities(10.0, 20.0, 50.0)
    second = utils.get_nearby_cities(10.0, 20.0, 50.0)

    assert call_count["count"] == 1
    assert first == second
    assert first[0][0] == "Sample City"
    assert first is not second


def test_get_nearby_cities_does_not_cache_failures(monkeypatch):
    utils._NEARBY_CITIES_CACHE.clear()
    call_count = {"count": 0}

    def fake_post(url, data, headers, timeout):
        call_count["count"] += 1
        raise requests.RequestException("API unreachable")

    monkeypatch.setattr(utils.requests, "post", fake_post)

    first = utils.get_nearby_cities(10.0, 20.0, 50.0)
    second = utils.get_nearby_cities(10.0, 20.0, 50.0)

    assert call_count["count"] == 2
    assert first == []
    assert second == []


def test_get_nearby_cities_loads_from_disk(monkeypatch, tmp_path):
    cache_file = tmp_path / "nearby_cache.json"
    cache_key = "10.0|20.0|50.0"
    cache_file.write_text(
        json.dumps({cache_key: [["Cached City", 10.0, 20.0, 0.0, "city"]]}),
        encoding="utf-8",
    )

    monkeypatch.setattr(utils, "_NEARBY_CITIES_CACHE_PATH", str(cache_file))
    utils._NEARBY_CITIES_CACHE.clear()
    utils._NEARBY_CITIES_CACHE.update(utils._load_nearby_cities_cache())

    def fake_post(url, data, headers, timeout):
        raise AssertionError("API should not be called when cache is loaded from disk")

    monkeypatch.setattr(utils.requests, "post", fake_post)

    cities = utils.get_nearby_cities(10.0, 20.0, 50.0)
    assert cities == [("Cached City", 10.0, 20.0, 0.0, "city")]


def test_get_nearby_cities_persists_cache_to_disk(monkeypatch, tmp_path):
    cache_file = tmp_path / "nearby_cache.json"
    monkeypatch.setattr(utils, "_NEARBY_CITIES_CACHE_PATH", str(cache_file))
    utils._NEARBY_CITIES_CACHE.clear()

    call_count = {"count": 0}

    def fake_post(url, data, headers, timeout):
        call_count["count"] += 1
        return DummyResponse(
            {
                "elements": [
                    {
                        "tags": {"name": "Persisted City", "place": "town"},
                        "lat": 30.0,
                        "lon": 40.0,
                    }
                ]
            }
        )

    monkeypatch.setattr(utils.requests, "post", fake_post)

    cities = utils.get_nearby_cities(30.0, 40.0, 100.0)
    assert call_count["count"] == 1
    assert cities == [("Persisted City", 30.0, 40.0, 0.0, "town")]
    assert cache_file.exists()

    stored = json.loads(cache_file.read_text(encoding="utf-8"))
    assert "30.0|40.0|100.0" in stored
