from __future__ import annotations

import asyncio
import os
import time
from typing import List, Optional

import httpx
import requests
from bs4 import BeautifulSoup
from geopy import distance
from opensky_api import OpenSkyApi

from .models import AircraftPosition
from .opensky_auth import headers as opensky_headers
from .utils import get_airport_name, remove_accents

__all__ = [
    "fetch_airplanes_live_positions",
    "fetch_opensky_positions",
    "get_opensky_route",
    "get_flightaware_route",
    #"resolve_flightaware_labels",
]

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


# async def fetch_airplanes_live_position(icao24: str) -> tuple[float, float]:
#     url = f"https://api.airplanes.live/api/v1/flight?icao24={icao24}"
#     async with httpx.AsyncClient() as client:
#         resp = await client.get(url, timeout=10.0)
#         resp.raise_for_status()
#         data = resp.json()
#         if not isinstance(data, dict) or "lat" not in data or "lon" not in data:
#             raise ValueError(f"Invalid response from airplanes.live for {icao24}: {data}")
#         return float(data["lat"]), float(data["lon"])


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
        # print(f"Item: {item}")
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
                origin_country="",
                desc=item.get("desc", ""),
                # 'desc': 'AIRBUS A-321neo'
            )
        )
    return positions


def _build_positions_from_opensky(states_list: List, center: tuple[float, float], radius: Optional[float] = None) -> List[AircraftPosition]:
    """Convert OpenSky state objects to AircraftPosition.

    If `radius` is provided, only include states within that distance (km).
    If `radius` is None, include all provided states.
    """
    positions: List[AircraftPosition] = []
    for state in states_list:
        # print(f"Item: {state}")
        try:
            d = distance.distance((state.latitude, state.longitude), center).km
        except Exception:
            continue
        if radius is None or d <= radius:
            alt_km = (state.geo_altitude / 1000) if getattr(state, "geo_altitude", None) is not None else None
            positions.append(
                AircraftPosition(
                    latitude=state.latitude,
                    longitude=state.longitude,
                    grounded=getattr(state, "on_ground", False),
                    alt_km=alt_km,
                    dest="",
                    ident=state.callsign or state.icao24,
                    mag_heading=None,
                    icao24=state.icao24,
                    origin_country=getattr(state, "origin_country", None),
                    desc="",
                )
            )
    return positions


def fetch_opensky_positions(bbox: tuple[float, float, float, float], center_lat: float, center_lon: float) -> List[AircraftPosition]:
    """Query OpenSky for states inside `bbox` and return converted positions."""
    api = OpenSkyApi()
    states = api.get_states(bbox=bbox)
    if not (states and states.states):
        return []
    return _build_positions_from_opensky(states.states, (center_lat, center_lon), None)


def get_opensky_route(pos: AircraftPosition) -> tuple[str, str, str | None]:
    opensky_route = None
    dep = "Unknown"
    arr = "Unknown"
    end_time = int(time.time())
    start_time = end_time - 60 * 60 * 24
    flights_url = (
        f"https://opensky-network.org/api/flights/aircraft?icao24={pos.icao24}&"
        f"begin={start_time}&end={end_time}"
    )
    try:
        req = requests.get(flights_url, headers=opensky_headers())
        flights_history = req.json()
        if isinstance(flights_history, list) and flights_history:
            current_callsign = pos.ident.strip() if pos.ident else ""
            latest_flight = None
            if current_callsign:
                for flight in flights_history:
                    if flight.get("callsign", "").strip() == current_callsign:
                        latest_flight = flight
                        break
            if not latest_flight:
                latest_flight = flights_history[0]
            dep = get_airport_name(latest_flight.get("estDepartureAirport"))
            arr = get_airport_name(latest_flight.get("estArrivalAirport"))
            if dep != "Unknown" and arr != "Unknown":
                opensky_route = f"{dep} ➡️ {arr}"
    except Exception:
        pass
    return dep, arr, opensky_route


def get_flightaware_route(pos: AircraftPosition, dep: str, arr: str) -> tuple[str, str, str | None, str | None]:
    flightaware_route = None
    airline_text = None
    callsign_for_fa = pos.ident
    if not callsign_for_fa:
        return dep, arr, flightaware_route, airline_text

    url_fa = f"https://es.flightaware.com/live/flight/{callsign_for_fa.strip()}"
    try:
        req_fa = requests.get(
            url_fa,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            },
        )
        if req_fa.status_code == 200:
            soup = BeautifulSoup(req_fa.text, "lxml")
            # print(f"Soup: {soup}")
            meta = soup.find("meta", property="og:description")
            # <meta content="B38M" name="aircrafttype"/>
            # https://www.flightaware.com/live/aircrafttype/
            # <meta content="RYR" name="airline"/>
            # <meta content="https://es.flightaware.com/ajax/flight/map/RYR5ND/20260609/1955Z/LEVT/LEAL/?width=1200&amp;height=630&amp;dpi=2" property="og:image"/>
            if meta and meta.get("content"):
                flightaware_route = meta["content"].strip()
            origin_meta = soup.find("meta", attrs={"name": "origin"})
            if origin_meta and origin_meta.get("content"):
                from airports import airport_data

                cnt = origin_meta["content"]
                dep = f"{airport_data.get_airport_by_icao(cnt)[0]['airport']} [{cnt}]"
                destination = soup.find("meta", attrs={"name": "destination"})
                if destination and destination.get("content"):
                    cnt = destination["content"]
                    arr = f"{airport_data.get_airport_by_icao(cnt)[0]['airport']} [{cnt}]"
                airline = soup.find("meta", attrs={"name": "airline"})
                if airline and airline.get("content"):
                    airline_text = airline["content"]
    except Exception:
        pass
    return dep, arr, flightaware_route, airline_text


# def resolve_flightaware_labels(flightaware_route: str | None, orig_label: str, dest_label: str) -> tuple[str, str]:
#     if not flightaware_route or dest_label != "Unknown" or "to" not in flightaware_route:
#         return orig_label, dest_label
#     import re
#     from airports import airport_data
# 
#     match_orig = re.search(r"from\s+([^\n]+)", flightaware_route, re.IGNORECASE)
#     if not match_orig:
#         return orig_label, dest_label
# 
#     candidate = match_orig.group(1).strip()
#     candidate = re.split(r"[:,]\s*", candidate)[0]
#     orig_label = candidate.replace("Int'l de", "").replace("Int'l", "")
#     match_dest = re.search(r"to\s+([^\n]+)", flightaware_route, re.IGNORECASE)
#     if match_dest:
#         candidate = match_dest.group(1).strip()
#         candidate = re.split(r"[:,]\s*", candidate)[0]
#         dest_label = candidate.replace("Int'l de", "")
#         orig_label = orig_label.replace(dest_label, "")[:-3]
#         print(
#             f"[bold]Origin:[/bold] {orig_label} {airport_data.search_by_name(remove_accents(orig_label))}"
#         )
#         print(
#             f"[bold]Destination:[/bold] {dest_label} {airport_data.search_by_name(remove_accents(dest_label))}"
#         )
#     else:
#         print(
#             f"[bold]Origin:[/bold] {orig_label} {airport_data.search_by_name(remove_accents(orig_label))}"
#         )
#     return orig_label, dest_label
