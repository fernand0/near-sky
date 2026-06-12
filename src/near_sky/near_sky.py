#!/usr/bin/env python3

import argparse
import sys
import time
from typing import List

from geopy import distance
from rich import print

from . import origin
from .api import (
    fetch_airplanes_live_positions,
    fetch_opensky_positions,
    get_flightaware_route,
    get_opensky_route,
    #resolve_flightaware_labels,
)
from .drawing import generate_radar_image
from .models import AircraftPosition
from .utils import calculate_bbox, remove_accents

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


def _get_coords(obj):
    """Return (lat, lon) for objects that may use different attribute names."""
    lat = getattr(obj, "lat", None)
    if lat is None:
        lat = getattr(obj, "latitude", None)
    lon = getattr(obj, "lon", None)
    if lon is None:
        lon = getattr(obj, "longitude", None)
    return lat, lon


def _apply_interval_filter(positions: List[AircraftPosition], center: tuple[float, float], radius: float) -> List[AircraftPosition]:
    """Return the subset of `positions` that fall within the chosen interval bucket.

    Prints a message if the chosen interval differs from the requested `radius`.
    """
    pairs: list[tuple[AircraftPosition, float]] = []
    for pos in positions:
        lat, lon = _get_coords(pos)
        if lat is None or lon is None:
            continue
        d = distance.distance((lat, lon), center).km
        pairs.append((pos, d))
    if not pairs:
        return []
    distances = [d for (_p, d) in pairs]
    selected_radius = choose_nearest_interval(radius, distances)
    if selected_radius is None:
        print(f"[bold yellow]No flights found within the requested {radius} km intervals.[/bold yellow]")
        return []
    if selected_radius != radius:
        print(f"Showing planes within the nearest interval: {selected_radius} km")
    filtered = [p for (p, d) in pairs if d <= selected_radius]
    return filtered


def _print_route_info(dep: str, arr: str, opensky_route: str | None, flightaware_route: str | None, airline_text: str | None, airplanes_live: bool) -> None:
    #if airplanes_live:
    #    return
    if opensky_route:
        print(f"[bold]Route:[/bold] {opensky_route}")
    elif dep != "Unknown" and arr != "Unknown":
        print(f"[bold]Route:[/bold] {dep} ➡️  {arr}")
    elif flightaware_route:
        print(f"[bold]Route:[/bold] {flightaware_route}")
    else:
        print(f"[bold]Route:[/bold] {dep} ➡️  {arr}")
    if airline_text:
        print(f"[bold]Airline:[/bold] {airline_text}")


def display_nearby_aircraft(
    radius: float,
    show_map: bool = False,
    generate_image: bool = False,
    output_file: str = "sky_map.png",
    airplanes_live: bool = False,
) -> int:
    """Fetch and display nearby aircraft from OpenSky or airplanes.live.

    This is the main entrypoint that queries the selected API, applies
    the configured interval-based radius selection, and prints summaries
    or generates an image.
    """
    center = (origin.ORIGIN_LAT, origin.ORIGIN_LON)
    positions: List[AircraftPosition] = []
    bounding_box = calculate_bbox(center[0], center[1], max(radius, 100))

    if airplanes_live:
        positions = fetch_airplanes_live_positions(center[0], center[1], radius)
    else:
        positions = fetch_opensky_positions(bounding_box, center[0], center[1])
    if not positions:
        print("[bold red]No aircraft data returned from API.[/bold red]")
        return 0
    positions = _apply_interval_filter(positions, center, radius)
    if not positions:
        return 0
    print(f"[bold cyan]Fetched {len(positions)} aircraft from API[/bold cyan]")

    radar_positions: List[AircraftPosition] = []
    if positions:
        sorted_positions = sorted(
            positions,
            key=lambda p: (distance.distance(_get_coords(p), center).km if _get_coords(p)[0] is not None else float("inf")),
        )
        print(f"[bold dim cyan]{'─' * 55}[/bold dim cyan]")
        for pos in sorted_positions:
            pos_lat, pos_lon = _get_coords(pos)
            print(f"[bold]Description:[/bold] {pos.desc}")
            print(f"[bold]Callsign:[/bold] {pos.ident}")
            # url = f"https://api.airplanes.live/v2/callsign/{pos.ident}"
            # import requests
            # import urllib.request
            # req = urllib.request.Request(url)
            # resProc = requests.get(url).json()
            # print(f"Info: {resProc}")
            if pos.alt_km is not None:
                print(f"[bold]Altitude:[/bold] {pos.alt_km:.1f} km")
            origin_country = getattr(pos, "origin_country", None)
            if origin_country is not None:
                print(f"[bold]Origin country:[/bold] {origin_country}")
            dist_val = distance.distance((pos_lat, pos_lon), center).km if pos_lat is not None else float("nan")
            print(
                f"[bold]Distance:[/bold] {dist_val:.1f} km\n"
                f"[bold]Status:[/bold] {'✅ Grounded' if pos.grounded else '✈️ In‑flight'}"
            )

            opensky_route = None
            flightaware_route = None
            dep = "Unknown"
            arr = "Unknown"

            # dep, arr, opensky_route = get_opensky_route(pos)
            dep, arr, flightaware_route, airline_text = get_flightaware_route(pos, dep, arr)
            _print_route_info(dep, arr, opensky_route, flightaware_route, airline_text, airplanes_live)

            dest_label = arr
            orig_label = dep
            # if not airplanes_live:
            #     orig_label, dest_label = resolve_flightaware_labels(flightaware_route, orig_label, dest_label)

            if show_map or generate_image:
                if pos_lat is not None and pos_lon is not None:
                    osm_url = f"https://www.openstreetmap.org/?mlat={pos_lat}&mlon={pos_lon}#map=12/{pos_lat}/{pos_lon}"
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
        default="sky_map.png",
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
    return display_nearby_aircraft(
        args.radius,
        args.map,
        args.map_image,
        args.output,
        airplanes_live=args.airplanes_live,
    )


if __name__ == "__main__":
    sys.exit(main())
