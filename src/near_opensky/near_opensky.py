#!/usr/bin/env python3

import argparse
import sys
import time
from typing import List

import requests
from bs4 import BeautifulSoup
from geopy import distance
from opensky_api import OpenSkyApi
from rich import print

from . import origin
from .api import build_positions_from_opensky, fetch_airplanes_live_positions
from .drawing import generate_radar_image
from .models import AircraftPosition
from .opensky_auth import headers as opensky_headers
from .utils import calculate_bbox, get_airport_name, remove_accents

INTERVALS = (5, 10, 15, 25, 50, 75, 100)


def choose_nearest_interval(radius: float, distances: list[float]) -> float | None:
    """Choose the nearest defined interval that contains at least one plane."""
    if radius <= 0:
        return None
    intervals = [n for n in INTERVALS if n <= radius]
    if not intervals:
        intervals = [radius]
    for interval in intervals:
        if any(d <= interval for d in distances):
            return interval
    return None


def run_opensky(
    radius: float,
    show_map: bool = False,
    generate_image: bool = False,
    output_file: str = "opensky_map.png",
    airplanes_live: bool = False,
) -> int:
    """Run the main OpenSky/airplanes.live query and print flight summaries."""
    center = (origin.ORIGIN_LAT, origin.ORIGIN_LON)
    positions: List[AircraftPosition] = []
    bounding_box = calculate_bbox(center[0], center[1], max(radius, 100))
    states = None

    if airplanes_live:
        positions = fetch_airplanes_live_positions(center[0], center[1], radius)
        print(f"Pos: {positions}")
        if not positions:
            print("[bold red]No aircraft data returned from airplanes.live.[/bold red]")
            return 0
        distances = [distance.distance((pos.latitude, pos.longitude), center).km for pos in positions]
        selected_radius = choose_nearest_interval(radius, distances)
        if selected_radius is not None:
            if selected_radius != radius:
                print(f"Showing planes within the nearest interval: {selected_radius} km")
            positions = [pos for pos, dist in zip(positions, distances) if dist <= selected_radius]
        else:
            print(f"[bold yellow]No flights found within the requested {radius} km intervals.[/bold yellow]")
            return 0
        print(f"[bold cyan]Fetched {len(positions)} aircraft from airplanes.live[/bold cyan]")
    else:
        api = OpenSkyApi()
        states = api.get_states(bbox=bounding_box)
        if not (states and states.states):
            print("[bold red]No aircraft states returned.[/bold red]")
            return 0

        in_flight_states = [s for s in states.states if not getattr(s, "on_ground", False)]
        if in_flight_states:
            distances = [distance.distance((s.latitude, s.longitude), center).km for s in in_flight_states]
            selected_radius = choose_nearest_interval(radius, distances)
            if selected_radius is not None:
                if selected_radius != radius:
                    print(f"Showing planes within the nearest interval: {selected_radius} km")
                radius = selected_radius
            else:
                print(f"[bold yellow]No flights found within the requested {radius} km intervals.[/bold yellow]")

        positions = build_positions_from_opensky(states.states, center, radius)

    radar_positions: List[AircraftPosition] = []
    if positions:
        sorted_positions = sorted(
            positions,
            key=lambda p: distance.distance((p.latitude, p.longitude), center).km,
        )
        print(f"[bold dim cyan]{'─' * 55}[/bold dim cyan]")
        for pos in sorted_positions:
            state_obj = None
            if not airplanes_live and states and getattr(states, "states", None):
                state_obj = next(
                    (
                        s
                        for s in states.states
                        if getattr(s, "icao24", None) == pos.icao24
                        or (
                            getattr(s, "latitude", None) == pos.latitude
                            and getattr(s, "longitude", None) == pos.longitude
                        )
                    ),
                    None,
                )

            print(f"[bold]Callsign:[/bold] {pos.ident}")
            if pos.alt_km is not None:
                print(f"[bold]Altitude:[/bold] {pos.alt_km:.1f} km")
            if state_obj and not airplanes_live:
                print(f"[bold]Origin:[/bold] {state_obj.origin_country}")
            print(
                f"[bold]Distance:[/bold] {distance.distance((pos.latitude, pos.longitude), center).km:.1f} km\n"
                f"[bold]Status:[/bold] {'✅ Grounded' if pos.grounded else '✈️ In‑flight'}"
            )

            opensky_route = None
            flightaware_route = None
            dep = "Unknown"
            arr = "Unknown"
            end_time = int(time.time())
            start_time = end_time - 60 * 60 * 24
            flights_url = (
                f"https://opensky-network.org/api/flights/aircraft?icao24={pos.icao24}&"
                f"begin={start_time}&end={end_time}"
            )
            req = requests.get(flights_url, headers=opensky_headers())

            try:
                flights_history = req.json()
                if isinstance(flights_history, list) and flights_history:
                    current_callsign = (
                        state_obj.callsign.strip()
                        if state_obj and getattr(state_obj, "callsign", None)
                        else (pos.ident.strip() if pos.ident else "")
                    )
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

            callsign_for_fa = pos.ident
            if callsign_for_fa:
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
                        meta = soup.find("meta", property="og:description")
                        if meta and meta.get("content"):
                            flightaware_route = meta["content"].strip()
                        origin_meta = soup.find("meta", attrs={"name": "origin"})
                        from airports import airport_data
                        cnt = origin_meta["content"]
                        dep = f"{airport_data.get_airport_by_icao(cnt)[0]['airport']} [{cnt}]"
                        print(f"[bold]Origin:[/bold] {dep}")
                        destination = soup.find("meta", attrs={"name": "destination"})
                        if destination:
                            cnt = destination["content"]
                            arr = f"{airport_data.get_airport_by_icao(cnt)[0]['airport']} [{cnt}]"
                            print(f"[bold]Destination:[/bold] {arr}")
                        airline = soup.find("meta", attrs={"name": "airline"})
                        print(f"[bold]Airline:[/bold] {airline['content']}")
                except Exception:
                    pass

            if not airplanes_live:
                if opensky_route:
                    print(f"[bold]Route:[/bold] {opensky_route}")
                elif dep and arr:
                    print(f"[bold]Route:[/bold] {dep} ➡️  {arr}")
                elif flightaware_route:
                    print(f"[bold]Route:[/bold] {flightaware_route}")
                else:
                    print(f"[bold]Route:[/bold] {dep} ➡️  {arr}")

            dest_label = arr
            orig_label = dep
            if not airplanes_live and dest_label == "Unknown" and flightaware_route and "to" in flightaware_route:
                import re
                match_orig = re.search(r"from\s+([^\n]+)", flightaware_route, re.IGNORECASE)
                if match_orig:
                    candidate = match_orig.group(1).strip()
                    candidate = re.split(r"[:,]\s*", candidate)[0]
                    orig_label = candidate.replace("Int'l de", "").replace("Int'l", "")
                    match_dest = re.search(r"to\s+([^\n]+)", flightaware_route, re.IGNORECASE)
                    if match_dest:
                        candidate = match_dest.group(1).strip()
                        candidate = re.split(r"[:,]\s*", candidate)[0]
                        dest_label = candidate.replace("Int'l de", "")
                        orig_label = orig_label.replace(dest_label, "")[:-3]
                        print(
                            f"[bold]Origin:[/bold] {orig_label} {airport_data.search_by_name(remove_accents(orig_label))}"
                        )
                        print(
                            f"[bold]Destination:[/bold] {dest_label} {airport_data.search_by_name(remove_accents(dest_label))}"
                        )
                    else:
                        print(
                            f"[bold]Origin:[/bold] {orig_label} {airport_data.search_by_name(remove_accents(orig_label))}"
                        )

            if show_map or generate_image:
                osm_url = f"https://www.openstreetmap.org/?mlat={pos.latitude}&mlon={pos.longitude}#map=12/{pos.latitude}/{pos.longitude}"
                print(f"[bold]Map:[/bold] {osm_url}")

            print(f"[bold dim cyan]{'─' * 55}[/bold dim cyan]")
            if generate_image:
                pos.dest = dest_label if dest_label != "Unknown" else ""
                radar_positions.append(pos)

    if generate_image and not radar_positions:
        print("[WARN] No aircraft positions found – map image will not be generated.")
    if generate_image and radar_positions:
        generate_radar_image(radar_positions, center[0], center[1], radius, output_file)

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Hybrid CLI: OpenSky flight fetcher.")
    parser.add_argument(
        "--map",
        action="store_true",
        help="Print OpenStreetMap link for each aircraft position",
    )
    parser.add_argument(
        "--map-image",
        action="store_true",
        help="Generate a static OpenStreetMap image with aircraft markers",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="opensky_map.png",
        help="Filename for the generated map image",
    )
    parser.add_argument(
        "--radius",
        type=float,
        default=100,
        help="Radius in km for the OpenStreetMap bounding box (default 100)",
    )
    parser.add_argument(
        "--airplanes-live",
        action="store_true",
        help="Use airplanes.live API for aircraft position data instead of OpenSky data",
    )
    args = parser.parse_args()
    return run_opensky(
        args.radius,
        args.map,
        args.map_image,
        args.output,
        airplanes_live=args.airplanes_live,
    )


if __name__ == "__main__":
    sys.exit(main())
