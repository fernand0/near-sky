#!/usr/bin/env python3

from . import origin as orig

import sys
import argparse
from typing import List, Tuple, Optional
from dataclasses import dataclass

# Original OpenSky imports
from rich import print
from opensky_api import OpenSkyApi
from geopy import distance
from bs4 import BeautifulSoup
import math
import requests
import time
from . import opensky_auth as tokens

# Pillow for image generation
from PIL import Image, ImageDraw, ImageFont

def _draw_city(draw: ImageDraw.Draw, cx: int, cy: int, size: int, radius_km: float, center_lat: float, center_lon: float, name: str, clat: float, clon: float, font: ImageFont.ImageFont) -> None:
    """Draw a city/town marker and label on the radar.

    Parameters
    ----------
    draw: ImageDraw.Draw
        Drawing context.
    cx, cy: int
        Center pixel coordinates of the radar.
    size: int
        Image size in pixels (square).
    radius_km: float
        Radar radius in kilometres.
    center_lat, center_lon: float
        Geographic centre of the radar.
    name: str
        City or town name.
    clat, clon: float
        Latitude and longitude of the city.
    font: ImageFont.ImageFont
        Font for text labels.
    """
    # Compute bearing from centre to city
    lat1 = math.radians(center_lat)
    lon1 = math.radians(center_lon)
    lat2 = math.radians(clat)
    lon2 = math.radians(clon)
    y = math.sin(lon2 - lon1) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(lon2 - lon1)
    bearing = (math.degrees(math.atan2(y, x)) + 360) % 360
    # Convert distance to pixel radius
    dist_km = distance.distance((center_lat, center_lon), (clat, clon)).km
    r_pixels = (dist_km / radius_km) * (size / 2)
    angle_rad = math.radians(bearing)
    px = cx + r_pixels * math.sin(angle_rad)
    py = cy - r_pixels * math.cos(angle_rad)
    # Draw small green indicator and label
    draw.ellipse([px - 2, py - 2, px + 2, py + 2], fill=(0, 100, 0))
    draw.text((px + 5, py - 5), name, fill=(0, 100, 0), font=font)

def _draw_aircraft(draw: ImageDraw.Draw, cx: int, cy: int, size: int, radius_km: float, center_lat: float, center_lon: float, lat: float, lon: float, grounded: bool, dest: Optional[str], font: ImageFont.ImageFont) -> None:
    """Draw an aircraft marker, optional grounded square, arrow, and destination label.
    """
    # Compute bearing and distance
    lat1 = math.radians(center_lat)
    lon1 = math.radians(center_lon)
    lat2 = math.radians(lat)
    lon2 = math.radians(lon)
    y = math.sin(lon2 - lon1) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(lon2 - lon1)
    bearing = (math.degrees(math.atan2(y, x)) + 360) % 360
    dist_km = distance.distance((center_lat, center_lon), (lat, lon)).km
    r_pixels = (dist_km / radius_km) * (size / 2)
    angle_rad = math.radians(bearing)
    px = cx + r_pixels * math.sin(angle_rad)
    py = cy - r_pixels * math.cos(angle_rad)
    if grounded:
        sq_size = 6
        draw.rectangle([px - sq_size/2, py - sq_size/2, px + sq_size/2, py + sq_size/2], fill="blue")
    else:
        arrow_len = 12
        arrow_width = 5
        tip_x = px + arrow_len * math.sin(angle_rad)
        tip_y = py - arrow_len * math.cos(angle_rad)
        left_x = px - arrow_width * math.sin(angle_rad)
        left_y = py - arrow_width * math.cos(angle_rad)
        right_x = px + arrow_width * math.sin(angle_rad)
        right_y = py + arrow_width * math.cos(angle_rad)
        draw.polygon([(tip_x, tip_y), (left_x, left_y), (right_x, right_y)], fill="yellow")
    # Aircraft point
    draw.ellipse([px - 4, py - 4, px + 4, py + 4], fill="red")
    if dest:
        draw.text((px + 6, py - 6), dest, fill="yellow", font=font)

# Optional airports data for helper

@dataclass
class AircraftPos:
    """Simple container for aircraft position data used in radar image generation."""
    lat: float
    lon: float
    grounded: bool
    dest: Optional[str] = None
def get_nearby_cities(lat, lon, radius_km):
    """Retrieve cities and towns within a specified radius using the Overpass API."""
    url = "https://overpass-api.de/api/interpreter"
    
    # Query for cities and towns within the radius
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
        if response.status_code == 200:
            elements = response.json().get("elements", [])
            cities = []
            for e in elements:
                name = e.get("tags", {}).get("name")
                clat = e.get("lat")
                clon = e.get("lon")
                place_type = e.get("tags", {}).get("place")
                if name and clat is not None and clon is not None:
                    # Calculate distance to sort/filter
                    dist = distance.distance((lat, lon), (clat, clon)).km
                    if dist <= radius_km:
                        cities.append((name, clat, clon, dist, place_type))
            
            # Sort by distance so we can prioritize closer ones
            cities.sort(key=lambda x: x[3])
            return cities
    except Exception:
        pass
    return []


def generate_radar_image(positions, center_lat, center_lon, radius_km, output_file):
    """Generate a radar‑style PNG showing aircraft positions.

    * positions – list of (lat, lon, grounded) tuples where `grounded` is a boolean indicating if the aircraft is on the ground
    * center_lat/center_lon – geographic centre (origin)
    * radius_km – radius of the search area (used to scale the image)
    * output_file – filename to save the PNG image
    """
    size = 800  # pixels, square image
    img = Image.new("RGB", (size, size), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()

    cx, cy = size // 2, size // 2
    # Outer radar circle (full radius)
    draw.ellipse([cx - size // 2, cy - size // 2, cx + size // 2, cy + size // 2], outline="green")
    # Center point
    draw.ellipse([cx - 3, cy - 3, cx + 3, cy + 3], fill="green")
    # Concentric distance circles (5, 10, 25, 50 km) if within radius_km
    for dist in (5, 10, 25, 50):
        if dist < radius_km:
            r = (dist / radius_km) * (size / 2)
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline="green")

    cities = get_nearby_cities(center_lat, center_lon, radius_km)
    sorted_cities = sorted(cities, key=lambda x: (0 if x[4] == "city" else 1, x[3]))
    
    for name, clat, clon, dist_km, place_type in sorted_cities[:12]:
         _draw_city(draw, cx, cy, size, radius_km, center_lat, center_lon, name, clat, clon, font)
        
    for lat, lon, grounded, dest in positions:
         _draw_aircraft(draw, cx, cy, size, radius_km, center_lat, center_lon, lat, lon, grounded, dest, font)

    img.save(output_file)
    print(f"[bold green]✅ Radar image saved to:[/bold green] {output_file}")
    return None


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


import unicodedata

def remove_accents(input_str):
    # Normalize to NFD (decomposed form)
    nfkd_form = unicodedata.normalize('NFD', input_str)
    # Encode to ASCII, ignoring non-ASCII characters (the accents)
    return nfkd_form.encode('ASCII', 'ignore').decode('UTF-8')



def run_opensky(radius: float, show_map: bool = False, generate_image: bool = False, output_file: str = "opensky_map.png"):
    """Core OpenSky logic (original script).

    The function prints rich information about aircraft within the computed
    bounding box around a fixed origin point. If *show_map* is True, an OpenStreetMap
    link for each aircraft's current position is also printed. If *generate_image*
    is True, a static map image is generated and saved to *output_file*.
    """
    center = (orig.ORIGIN_LAT, orig.ORIGIN_LON)  # Default coordinates from origin module
    positions = []  # Collect aircraft positions for static map generation
    bounding_box = calculate_bbox(center[0], center[1], 100)
    api = OpenSkyApi()
    states = api.get_states(bbox=bounding_box)

    if not (states and states.states):
        print("[bold red]No aircraft states returned.[/bold red]")
        # No aircraft; continue to end for single return
        result = 0
        return result

    sorted_states = sorted(
        states.states,
        key=lambda s: distance.distance((s.latitude, s.longitude), center).km,
        reverse=True,
    )


    last = sorted_states[-1]
    last_distance = distance.distance((last.latitude, last.longitude), center).km
    if  last_distance> radius:
        numbers = (5, 10, 15, 25, 50, 75, 100)
        result = min(x for x in numbers if x > last_distance)
        print(f"Changing radius {radius}, nearest plane at {last_distance}"
              f" new radius -> {result}")
        radius = result

    print(f"[bold dim cyan]{'─' * 55}[/bold dim cyan]")
    for s in sorted_states:
        if distance.distance((s.latitude, s.longitude), center).km <=radius:
            print(f"[bold]Callsign:[/bold] {s.callsign}")
            print(f"[bold]Origin:[/bold] {s.origin_country}")
            print(f"[bold]Altitude:[/bold] {s.geo_altitude}")
            print(
                f"[bold]Distance:[/bold] {distance.distance((s.latitude, s.longitude), center).km}\n"
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
                        meta = soup.find_all("meta")
                        #print(meta)
                        meta = soup.find("meta", property="og:description")
                        if meta and meta.get("content"):
                            flightaware_route = meta["content"].strip()
                        origin = soup.find("meta", attrs={"name": "origin"})
                        from airports import airport_data
                        cnt = origin['content']
                        dep = f"{airport_data.get_airport_by_icao(cnt)[0]['airport']} [{cnt}]"
                        print(f"[bold]Origin:[/bold] {dep}")
                        destination = soup.find("meta", attrs={"name": "destination"})
                        if destination:
                            cnt = destination['content']
                            arr = f"{airport_data.get_airport_by_icao(cnt)[0]['airport']} [{cnt}]"
                            print(f"[bold]Destination:[/bold] {arr}")
                        airline = soup.find("meta", attrs={"name": "airline"})
                        print(f"[bold]Airline:[/bold] {airline['content']}")

                except Exception:
                    pass

            if opensky_route:
                print(f"[bold]Route:[/bold] {opensky_route}")
            elif dep and arr:
                print(f"[bold]Route:[/bold] {dep} ➡️  {arr}")
            elif flightaware_route:
                print(f"[bold]Route:[/bold] {flightaware_route}")
            else:
                print(f"[bold]Route:[/bold] {dep} ➡️  {arr}")


            # Determine destination label
            dest_label = arr
            orig_label = dep
            if dest_label == "Unknown" and flightaware_route and 'to' in flightaware_route:
                # Try to extract destination from flightaware_route string
                # Common patterns: "... to XYZ", "... → XYZ", possibly with lowercase or spaces
                import re
                # Look for 'to' followed by any characters up to a line break or end
                match_orig = re.search(r"from\s+([^\n]+)", flightaware_route, re.IGNORECASE)
                # if not match_dest:
                #     # Arrow symbol variant
                #     match_dest = re.search(r"→\s*([^\n]+)", flightaware_route)
                if match_orig:
                    # Take the first word of the matched segment as airport code/name
                    candidate = match_orig.group(1).strip()
                    # Remove any trailing descriptors (e.g., "airport", commas)
                    candidate = re.split(r"[,:]\s*", candidate)[0]
                    # Keep only alphanumeric characters and hyphens
                    #candidate = re.sub(r"[^A-Za-z0-9-]", "", candidate)
                    orig_label = candidate
                    orig_label = orig_label.replace("Int'l de", "")
                    orig_label = orig_label.replace("Int'l", "")
                    match_dest = re.search(r"to\s+([^\n]+)", flightaware_route, re.IGNORECASE)
                    if match_dest:
                        # Take the first word of the matched segment as airport code/name
                        candidate = match_dest.group(1).strip()
                        # Remove any trailing descriptors (e.g., "airport", commas)
                        candidate = re.split(r"[,:]\s*", candidate)[0]
                        # Keep only alphanumeric characters and hyphens
                        #candidate = re.sub(r"[^A-Za-z0-9-]", "", candidate)
                        dest_label = candidate
                        dest_label = dest_label.replace("Int'l de", "")
                        match_dest = re.search(r"to\s+([^\n]+)", orig_label, re.IGNORECASE)
                        orig_label = orig_label.replace(dest_label, "")[:-3] 


                        print(f"[bold]Origin:[/bold] {orig_label} {airport_data.search_by_name(remove_accents(orig_label))}")
                        print(f"[bold]Destination:[/bold] {dest_label} {airport_data.search_by_name(remove_accents(dest_label))}")
                    else:
                        print(f"[bold]Origin:[/bold] {orig_label} {airport_data.search_by_name(remove_accents(orig_label))}")

            # Map link per aircraft
            if show_map or generate_image:
                osm_url = f"https://www.openstreetmap.org/?mlat={s.latitude}&mlon={s.longitude}#map=12/{s.latitude}/{s.longitude}"
                print(f"[bold]Map:[/bold] {osm_url}")

            # Append position with destination label (empty if still unknown)
            print(f"[bold dim cyan]{'─' * 55}[/bold dim cyan]")
            if generate_image:
                positions.append((s.latitude, s.longitude, s.on_ground, dest_label if dest_label != "Unknown" else ""))

    # After processing all aircraft, generate static map if requested
    if generate_image and positions:
        generate_radar_image(positions, center[0], center[1], radius, output_file)

    return 0


def main() -> int:
    """CLI entry point supporting two modes.


    * **OpenSky mode** – otherwise it runs the original OpenSky flight fetcher.
    """
    parser = argparse.ArgumentParser(description="Hybrid CLI: OpenSky flight fetcher.")
    parser.add_argument('--map', action='store_true', help='Print OpenStreetMap link for each aircraft position')
    parser.add_argument('--map-image', action='store_true', help='Generate a static OpenStreetMap image with aircraft markers')
    parser.add_argument('--output', type=str, default='opensky_map.png', help='Filename for the generated map image')
    parser.add_argument('--radius', type=float, default=25,
                        help='Radius in km for the OpenStreetMap bounding box (default 50)')
    args = parser.parse_args()
    # Run OpenSky functionality with the provided or default radius
    return run_opensky(args.radius, args.map, args.map_image, args.output)

if __name__ == '__main__':
    sys.exit(main())
