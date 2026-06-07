from __future__ import annotations

import asyncio
import os
import time
from typing import List, Optional

import httpx
import requests
from geopy import distance
from opensky_api import OpenSkyApi

from .models import AircraftPosition
from .opensky_auth import headers as opensky_headers

_AIRPLANES_LIVE_TS_PATH = os.path.join(os.path.dirname(__file__), ".airplanes_live_ts")


def _respect_airplanes_live_rate_limit() -> None:
    try:
        with open(_AIRPLANES_LIVE_TS_PATH, "r") as f:
            last_ts = float(f.read().strip())
    except Exception:
        last_ts = 0.0
    now = time.time()
    elapsed = now - last_ts
    if elapsed < 1.0:
        time.sleep(1.0 - elapsed)
    with open(_AIRPLANES_LIVE_TS_PATH, "w") as f:
        f.write(str(time.time()))


async def fetch_position(url: str) -> tuple[float, float]:
    async with httpx.AsyncClient() as client:
        response = await client.get(url, timeout=10.0)
        response.raise_for_status()
        data = response.json()
        return float(data["lat"]), float(data["lon"])


async def fetch_airplanes_live_position(icao24: str) -> tuple[float, float]:
    url = f"https://api.airplanes.live/api/v1/flight?icao24={icao24}"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, dict) or "lat" not in data or "lon" not in data:
            raise ValueError(f"Invalid response from airplanes.live for {icao24}: {data}")
        return float(data["lat"]), float(data["lon"])


async def _fetch_airplanes_live_positions_async(center_lat: float, center_lon: float, radius_km: float) -> List[AircraftPosition]:
    _respect_airplanes_live_rate_limit()
    radius_nm = radius_km / 1.852
    url = f"https://api.airplanes.live/v2/point/{center_lat}/{center_lon}/{radius_nm}"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers={"User-Agent": "near-opensky/1.0"}, timeout=10.0)
            resp.raise_for_status()
            live_data = resp.json()
    except httpx.HTTPError:
        return []
    if not live_data or "ac" not in live_data:
        return []
    return _build_positions_from_airplanes_live(live_data.get("ac", []))


def fetch_airplanes_live_positions(center_lat: float, center_lon: float, radius_km: float) -> List[AircraftPosition]:
    return asyncio.run(_fetch_airplanes_live_positions_async(center_lat, center_lon, radius_km))


def _build_positions_from_airplanes_live(ac_items: List[dict]) -> List[AircraftPosition]:
    positions: List[AircraftPosition] = []
    for item in ac_items:
        if not isinstance(item, dict) or "lat" not in item or "lon" not in item:
            continue
        try:
            alt_km = float(item.get("alt_geom")) * 0.3048 / 1000 if item.get("alt_geom") is not None else None
        except (TypeError, ValueError):
            alt_km = None
        positions.append(
            AircraftPosition(
                latitude=float(item["lat"]),
                longitude=float(item["lon"]),
                grounded=(item.get("alt_baro") == "ground"),
                alt_km=alt_km,
                dest="",
                ident=item.get("flight") or item.get("icao24", ""),
                mag_heading=float(item["mag_heading"]) if item.get("mag_heading") is not None else None,
                icao24=item.get("hex", ""),
            )
        )
    return positions


def build_positions_from_opensky(states_list: List, center: tuple[float, float], radius: float) -> List[AircraftPosition]:
    positions: List[AircraftPosition] = []
    for state in states_list:
        if distance.distance((state.latitude, state.longitude), center).km <= radius:
            alt_km = (state.geo_altitude / 1000) if getattr(state, "geo_altitude", None) is not None else None
            positions.append(
                AircraftPosition(
                    lat=state.latitude,
                    lon=state.longitude,
                    grounded=getattr(state, "on_ground", False),
                    alt_km=alt_km,
                    dest="",
                    ident=state.callsign or state.icao24,
                    mag_heading=None,
                    icao24=state.icao24,
                )
            )
    return positions
