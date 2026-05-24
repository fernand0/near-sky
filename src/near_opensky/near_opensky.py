#!/usr/bin/env python3

import argparse
from . import origin
import sys
import os
from pathlib import Path

# Original OpenSky imports
from rich import print
from opensky_api import OpenSkyApi
from geopy import distance
from bs4 import BeautifulSoup
import requests
import time
import math
from . import opensky_auth as tokens

# Optional airports data for helper
try:
    import airportsdata
    airports = airportsdata.load()
except ImportError:
    airports = None


def get_airport_name(icao):
    name = "Unknown"
    if icao:
        name = icao
        if airports and icao in airports:
            name = f"{airports[icao]['name']} ({icao})"
    return name


def calculate_bbox(lat, lon, radius_km):
    lat_offset = radius_km / 111.1
    lon_offset = radius_km / (111.1 * math.cos(math.radians(lat)))
    return (lat - lat_offset, lat + lat_offset, lon - lon_offset, lon + lon_offset)





def run_opensky(radius: float):
    """Core OpenSky logic (original script).

    The function prints rich information about aircraft within the computed
    bounding box around a fixed origin point.
    """
    origin = (origin.ORIGIN_LAT, origin.ORIGIN_LON)  # Default coordinates from origin module
    bounding_box = calculate_bbox(origin[0], origin[1], radius)

    api = OpenSkyApi()
    states = api.get_states(bbox=bounding_box)

    if not (states and states.states):
        print("[bold red]No aircraft states returned.[/bold red]")
        return 0

    sorted_states = sorted(
        states.states,
        key=lambda s: distance.distance((s.latitude, s.longitude), origin).km,
        reverse=True,
    )

    for s in sorted_states:
        print(f"[bold]Callsign:[/bold] {s.callsign}")
        print(f"[bold]Origin:[/bold] {s.origin_country}")
        print(f"[bold]Altitude:[/bold] {s.geo_altitude}")
        print(
            f"[bold]Distance:[/bold] {distance.distance((s.latitude, s.longitude), origin).km}\n"
            f"[bold]Status:[/bold] {'✅ Grounded' if getattr(s, 'on_ground', getattr(s, '__getitem__', lambda idx: None)(8) if hasattr(s, '__getitem__') else False) else '✈️ In‑flight'}"
        )

        end_time = int(time.time())
        start_time = end_time - 60 * 60 * 24
        url = (
            f"https://opensky-network.org/api/flights/aircraft?icao24={s.icao24}&"
            f"begin={start_time}&end={end_time}"
        )
        req = requests.get(url, headers=tokens.headers())
        opensky_route = None
        flightaware_route = None
        dep = "Unknown"
        arr = "Unknown"

        try:
            flights_history = req.json()
            if isinstance(flights_history, list) and flights_history:
                current_callsign = s.callsign.strip() if s.callsign else ""
                latest_flight = None
                if current_callsign:
                    for f in flights_history:
                        if f.get("callsign", "").strip() == current_callsign:
                            latest_flight = f
                            break
                if not latest_flight:
                    latest_flight = flights_history[0]
                dep = get_airport_name(latest_flight.get("estDepartureAirport"))
                arr = get_airport_name(latest_flight.get("estArrivalAirport"))
                if dep != "Unknown" and arr != "Unknown":
                    opensky_route = f"{dep} ➡️ {arr}"
        except Exception:
            pass

        if s.callsign:
            url_fa = f"https://es.flightaware.com/live/flight/{s.callsign.strip()}"
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
                    meta = soup.find("meta", property="og:description")
                    if meta and meta.get("content"):
                        flightaware_route = meta["content"].strip()
            except Exception:
                pass

        if opensky_route:
            print(f"[bold]Route:[/bold] {opensky_route}")
        elif flightaware_route:
            print(f"[bold]Route:[/bold] {flightaware_route}")
        else:
            print(f"[bold]Route:[/bold] {dep} ➡️ {arr}")

        print(f"[bold]Flightradar:[/bold] https://www.flightradar24.com/{s.callsign}")
        print(f"[bold]Opensky:[/bold] https://map.opensky-network.org/?icao={s.icao24}")
        print(f"[bold dim cyan]{'─' * 55}[/bold dim cyan]")

    return 0


def main() -> int:
    """CLI entry point supporting two modes.


    * **OpenSky mode** – otherwise it runs the original OpenSky flight fetcher.
    """
    parser = argparse.ArgumentParser(description="Hybrid CLI: OpenSky flight fetcher.")
    parser.add_argument('--radius', type=float, default=25,
                        help='Radius in km for the OpenSky bounding box (default 50)')
    args = parser.parse_args()
    # Run OpenSky functionality with the provided or default radius
    return run_opensky(args.radius)

if __name__ == '__main__':
    sys.exit(main())
