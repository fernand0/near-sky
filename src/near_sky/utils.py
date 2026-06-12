from __future__ import annotations

import json
import math
import os
import unicodedata
from typing import Optional, Tuple

import requests
from geopy import distance

try:
    from geographiclib.geodesic import Geodesic
except ImportError:
    Geodesic = None

_NEARBY_CITIES_CACHE_PATH = os.path.join(os.path.dirname(__file__), ".nearby_cities_cache.json")
_NEARBY_CITIES_CACHE: dict[tuple[float, float, float], list[tuple[str, float, float, float, str]]] = {}


def _serialize_cache_key(cache_key: tuple[float, float, float]) -> str:
    return f"{cache_key[0]}|{cache_key[1]}|{cache_key[2]}"


def _deserialize_cache_key(key: str) -> tuple[float, float, float] | None:
    parts = key.split("|")
    if len(parts) != 3:
        return None
    try:
        return float(parts[0]), float(parts[1]), float(parts[2])
    except ValueError:
        return None


def _load_nearby_cities_cache() -> dict[tuple[float, float, float], list[tuple[str, float, float, float, str]]]:
    try:
        with open(_NEARBY_CITIES_CACHE_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
        cache: dict[tuple[float, float, float], list[tuple[str, float, float, float, str]]] = {}
        for key, value in raw.items():
            parsed_key = _deserialize_cache_key(key)
            if parsed_key is None or not isinstance(value, list):
                continue
            cache[parsed_key] = [tuple(item) for item in value if isinstance(item, list) and len(item) == 5]
        return cache
    except Exception:
        return {}


def _save_nearby_cities_cache() -> None:
    try:
        raw_cache = {
            _serialize_cache_key(key): [list(item) for item in value]
            for key, value in _NEARBY_CITIES_CACHE.items()
        }
        temp_path = f"{_NEARBY_CITIES_CACHE_PATH}.tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(raw_cache, f)
        os.replace(temp_path, _NEARBY_CITIES_CACHE_PATH)
    except Exception:
        pass


_NEARBY_CITIES_CACHE = _load_nearby_cities_cache()


def calculate_bbox(lat: float, lon: float, radius_km: float) -> Tuple[float, float, float, float]:
    """Return a latitude/longitude bounding box around a center point."""
    lat_offset = radius_km / 111.1
    lon_offset = radius_km / (111.1 * math.cos(math.radians(lat)))
    return lat - lat_offset, lat + lat_offset, lon - lon_offset, lon + lon_offset


def get_airport_name(icao: Optional[str]) -> str:
    name = "Unknown"
    if icao:
        name = icao
        try:
            import airportsdata

            airports = airportsdata.load()
            if icao in airports:
                name = f"{airports[icao]['name']} ({icao})"
        except ImportError:
            pass
    return name


def remove_accents(input_str: str) -> str:
    nfkd_form = unicodedata.normalize("NFD", input_str)
    return nfkd_form.encode("ASCII", "ignore").decode("UTF-8")


def bearing_spherical(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, lambda1 = math.radians(lat1), math.radians(lon1)
    phi2, lambda2 = math.radians(lat2), math.radians(lon2)
    y = math.sin(lambda2 - lambda1) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(lambda2 - lambda1)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def bearing_ellipsoidal(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    if Geodesic:
        g = Geodesic.WGS84.Inverse(lat1, lon1, lat2, lon2)
        return (g["azi1"] + 360) % 360
    return bearing_spherical(lat1, lon1, lat2, lon2)


def get_nearby_cities(lat: float, lon: float, radius_km: float) -> list[tuple[str, float, float, float, str]]:
    cache_key = (round(lat, 6), round(lon, 6), round(radius_km, 3))
    if cache_key in _NEARBY_CITIES_CACHE:
        return list(_NEARBY_CITIES_CACHE[cache_key])

    url = "https://overpass-api.de/api/interpreter"
    query = f"""
    [out:json];
    (
      node["place"="city"](around:{radius_km * 1000},{lat},{lon});
      node["place"="town"](around:{radius_km * 1000},{lat},{lon});
    );
    out body;
    """
    headers = {"User-Agent": "near-opensky-cli/1.0"}
    try:
        response = requests.post(url, data={"data": query}, headers=headers, timeout=5)
        response.raise_for_status()
        elements = response.json().get("elements", [])
        cities: list[tuple[str, float, float, float, str]] = []
        for e in elements:
            name = e.get("tags", {}).get("name")
            clat = e.get("lat")
            clon = e.get("lon")
            place_type = e.get("tags", {}).get("place", "")
            if name and clat is not None and clon is not None:
                dist = distance.distance((lat, lon), (clat, clon)).km
                if dist <= radius_km:
                    cities.append((name, clat, clon, dist, place_type))
        cities.sort(key=lambda item: item[3])
        _NEARBY_CITIES_CACHE[cache_key] = cities
        _save_nearby_cities_cache()
        return list(cities)
    except Exception:
        return []
