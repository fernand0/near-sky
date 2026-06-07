#!/usr/bin/env python3

try:
    from near_opensky import origin as orig
except ImportError:
    import origin as orig

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
import asyncio
import httpx
from typing import Optional, Tuple

# Optional: use GeographicLib for ellipsoidal precision
try:
    from geographiclib.geodesic import Geodesic
except ImportError:
    Geodesic = None  # fallback to spherical formula if not installed

import requests
import os
import time

# Path to a tiny file that stores the timestamp of the last airplanes.live request.
# This persists across separate script runs, ensuring the 1‑request‑per‑second limit is respected globally.
_AIRPLANES_LIVE_TS_PATH = os.path.join(os.path.dirname(__file__), ".airplanes_live_ts")

def _respect_airplanes_live_rate_limit() -> None:
    """Block until at least one second has passed since the previous request.

    The timestamp is stored in a tiny file next to this module. If the file does not
    exist we treat it as never having made a request.
    """
    try:
        with open(_AIRPLANES_LIVE_TS_PATH, "r") as f:
            last_ts = float(f.read().strip())
    except Exception:
        last_ts = 0.0
    now = time.time()
    elapsed = now - last_ts
    if elapsed < 1.0:
        time.sleep(1.0 - elapsed)
    # Update the timestamp file with the current time
    with open(_AIRPLANES_LIVE_TS_PATH, "w") as f:
        f.write(str(time.time()))


_airplanes_live_last_ts: Optional[float] = None  # timestamp of last airplanes.live request
try:
    from near_opensky import opensky_auth as tokens
except ImportError:
    import opensky_auth as tokens


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
    # Compute pixel position
    px = cx + r_pixels * math.sin(angle_rad)
    py = cy - r_pixels * math.cos(angle_rad)
    # Clamp to keep within the image bounds (5‑pixel margin)
    margin = 5
    px = max(margin, min(size - margin, px))
    py = max(margin, min(size - margin, py))
    # Draw small green indicator and label
    draw.ellipse([px - 2, py - 2, px + 2, py + 2], fill=(0, 100, 0))
    draw.text((px + 5, py - 5), name, fill=(0, 100, 0), font=font)


def _draw_aircraft(draw: ImageDraw.Draw, cx: int, cy: int, size: int, radius_km: float, center_lat: float, center_lon: float, lat: float, lon: float, grounded: bool, dest: Optional[str], bearing: float, font: ImageFont.ImageFont, ident: Optional[str] = None) -> None:
    """
    Draw an aircraft symbol on the radar image.

    Parameters
    ----------
    draw : ImageDraw.Draw
        Pillow drawing context.
    cx, cy : int
        Pixel coordinates of the radar centre.
    size : int
        Image size (square, in pixels).
    radius_km : float
        Real‑world radius represented by the image.
    center_lat, center_lon : float
        Geographic centre of the radar.
    lat, lon : float
        Aircraft position.
    grounded : bool
        If True, draw a square instead of an arrow.
    dest : Optional[str]
        Destination ICAO code label.
    bearing : float
        Pre‑computed bearing from the centre to the aircraft (degrees).
    font : ImageFont.ImageFont
        Font used for the destination label.
    ident : Optional[str]
        Aircraft identifier (e.g., callsign) to be shown on the map.
    """

    """
    Draw an aircraft symbol on the radar image.

    Parameters
    ----------
    draw : ImageDraw.Draw
        Pillow drawing context.
    cx, cy : int
        Pixel coordinates of the radar centre.
    size : int
        Image size (square, in pixels).
    radius_km : float
        Real‑world radius represented by the image.
    center_lat, center_lon : float
        Geographic centre of the radar.
    lat, lon : float
        Aircraft position.
    grounded : bool
        If True, draw a square instead of an arrow.
    dest : Optional[str]
        Destination ICAO code label.
    bearing : float
        Pre‑computed bearing from the centre to the aircraft (degrees).
    font : ImageFont.ImageFont
        Font used for the destination label.
    """
    # Distance and pixel radius (clamp distance to radius_km to avoid off‑canvas points)
    dist_km = distance.distance((center_lat, center_lon), (lat, lon)).km
    if dist_km > radius_km:
        dist_km = radius_km
    r_pixels = (dist_km / radius_km) * (size / 2)

    # Convert bearing to radians
    angle_rad = math.radians(bearing)

    # Aircraft pixel position
    px = cx + r_pixels * math.sin(angle_rad)
    py = cy - r_pixels * math.cos(angle_rad)
    # Clamp to keep within image bounds (4‑pixel margin)
    margin = 4
    px = max(margin, min(size - margin, px))
    py = max(margin, min(size - margin, py))

    if grounded:
        sq = 6
        draw.rectangle([px - sq / 2, py - sq / 2, px + sq / 2, py + sq / 2], 
                       fill="blue")
    else:
        arrow_len = 12
        arrow_w = 5
        tip_x = px + arrow_len * math.sin(angle_rad)
        tip_y = py - arrow_len * math.cos(angle_rad)
        left_x = px - arrow_w * math.sin(angle_rad)
        left_y = py - arrow_w * math.cos(angle_rad)
        right_x = px + arrow_w * math.sin(angle_rad)
        right_y = py + arrow_w * math.cos(angle_rad)
        draw.polygon([(tip_x, tip_y), (left_x, left_y), (right_x, right_y)], fill="yellow")

    # Aircraft centre point
    draw.ellipse([px - 4, py - 4, px + 4, py + 4], fill="red")

    # Destination label
    if dest:
        draw.text((px + 6, py - 6), dest, fill="yellow", font=font)
    # Identifier (callsign) label – placed a little below the aircraft marker
    if ident:
        # Use a slightly smaller offset so it doesn’t overlap the marker
        draw.text((px + 6, py + 6), ident, fill="white", font=font)

async def fetch_position(url: str) -> Tuple[float, float]:
    """Fetch a (lat, lon) pair from a JSON endpoint.

    The endpoint must return a JSON object containing numeric ``lat`` and ``lon`` fields.
    Example response::

        {"lat": 48.3538, "lon": 11.7861}
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(url, timeout=10.0)
        response.raise_for_status()
        data = response.json()
        return float(data["lat"]), float(data["lon"])

# New: fetch position from airplanes.live API
async def fetch_airplanes_live_position(icao24: str) -> Tuple[float, float]:
    """Retrieve latitude and longitude for an aircraft using the airplanes.live API.

    The API endpoint is ``https://api.airplanes.live/api/v1/flight?icao24={icao24}``.
    It returns JSON containing ``lat`` and ``lon`` among other fields.
    If the request fails or the fields are missing, a ``ValueError`` is raised.
    """
    url = f"https://api.airplanes.live/api/v1/flight?icao24={icao24}"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, dict) or "lat" not in data or "lon" not in data:
            raise ValueError(f"Invalid response from airplanes.live for {icao24}: {data}")
        return float(data["lat"]), float(data["lon"])


def bearing_spherical(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great‑circle bearing using the spherical Earth formula.
    Returns degrees clockwise from true north (0‑360)."""
    φ1, λ1 = math.radians(lat1), math.radians(lon1)
    φ2, λ2 = math.radians(lat2), math.radians(lon2)
    y = math.sin(λ2 - λ1) * math.cos(φ2)
    x = math.cos(φ1) * math.sin(φ2) - math.sin(φ1) * math.cos(φ2) * math.cos(λ2 - λ1)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def bearing_ellipsoidal(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """WGS‑84 ellipsoidal bearing using GeographicLib if available.
    Falls back to the spherical formula when GeographicLib is not installed."""
    if Geodesic:
        g = Geodesic.WGS84.Inverse(lat1, lon1, lat2, lon2)
        return (g["azi1"] + 360) % 360
    else:
        return bearing_spherical(lat1, lon1, lat2, lon2)


async def compute_bearing_from_two_apis(origin_url: str, dest_url: str, use_ellipsoidal: bool = False) -> float:
    """Fetch two positions from separate URLs and return the bearing from the first to the second.

    Parameters
    ----------
    origin_url, dest_url : str
        URLs that each return JSON with ``lat`` and ``lon``.
    use_ellipsoidal : bool
        If ``True`` compute the bearing with the ellipsoidal formula (requires GeographicLib).
    """
    # Run the two HTTP calls concurrently
    origin_task = asyncio.create_task(fetch_position(origin_url))
    dest_task   = asyncio.create_task(fetch_position(dest_url))
    lat1, lon1 = await origin_task
    lat2, lon2 = await dest_task
    return bearing_ellipsoidal(lat1, lon1, lat2, lon2) if use_ellipsoidal else bearing_spherical(lat1, lon1, lat2, lon2)

def draw_aircraft_using_api(draw: ImageDraw.Draw, cx: int, cy: int, size: int, radius_km: float, center_lat: float, center_lon: float, lat: float, lon: float, grounded: bool, dest: Optional[str], origin_url: str, aircraft_url: str, font: ImageFont.ImageFont, use_ellipsoidal: bool = False) -> None:
    """Fetch bearing from two API endpoints and draw the aircraft.

    Parameters
    ----------
    origin_url, aircraft_url : str
        URLs returning JSON objects with ``lat`` and ``lon`` fields.
    use_ellipsoidal : bool
        If ``True`` compute the bearing with the ellipsoidal formula.
    """
    # Compute bearing asynchronously
    bearing = asyncio.run(compute_bearing_from_two_apis(origin_url, aircraft_url, use_ellipsoidal))
    # Call the existing drawing routine with the pre‑computed bearing
    _draw_aircraft(draw, cx, cy, size, radius_km, center_lat, center_lon, lat, lon, grounded, dest, bearing, font)


    """Draw an aircraft marker, optional grounded square, arrow, and destination label.
    """
    # Compute bearing and distance
    if precomputed_bearing is None:
        lat1 = math.radians(center_lat)
        lon1 = math.radians(center_lon)
        lat2 = math.radians(lat)
        lon2 = math.radians(lon)
        y = math.sin(lon2 - lon1) * math.cos(lat2)
        x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(lon2 - lon1)
        bearing = (math.degrees(math.atan2(y, x)) + 360) % 360
    else:
        bearing = precomputed_bearing
    dist_km = distance.distance((center_lat, center_lon), (lat, lon)).km
    r_pixels = (dist_km / radius_km) * (size / 2)
    angle_rad = math.radians((bearing + 180) % 360)
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

    # Use the original centre as the reference for bearing calculations
    ref_lat, ref_lon = center_lat, center_lon

    for entry in positions:
        # Support tuples with optional altitude and heading:
        # Expected formats:
        # (lat, lon, grounded, alt_km?, dest, ident, mag_heading?)
        # Determine length and unpack accordingly
        if len(entry) == 7:
            lat, lon, grounded, alt_km, dest, ident, mag_heading = entry
        elif len(entry) == 6:
            lat, lon, grounded, alt_km, dest, ident = entry
            mag_heading = None
        else:
            # fallback to older 5‑tuple format
            lat, lon, grounded, dest, ident = entry
            alt_km = None
            mag_heading = None
        bearing = mag_heading if mag_heading is not None else (bearing_ellipsoidal(ref_lat, ref_lon, lat, lon) if Geodesic else bearing_spherical(ref_lat, ref_lon, lat, lon))
        # Include altitude in the log if available
        alt_msg = f", alt={alt_km:.1f} km" if alt_km is not None else ""
        print(f"[bold cyan]Plane {ident}: lat={lat:.4f}, lon={lon:.4f}{alt_msg}, bearing={bearing:.2f}°, grounded={grounded}, dest={dest}[/bold cyan]")
        _draw_aircraft(draw, cx, cy, size, radius_km, ref_lat, ref_lon, lat, lon, grounded, dest, bearing, font)

    img.save(output_file)
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


def _build_positions_from_airplanes_live(ac_items: List[dict]) -> List[Tuple]:
    """Convert airplanes.live API items into the unified position tuple list.

    Each tuple is (lat, lon, grounded, alt_km, destination, ident, mag_heading).
    """
    res = [
        (
            float(item.get("lat")),
            float(item.get("lon")),
            (item.get("alt_baro") == "ground"),  # grounded flag based on alt_baro
            (float(item.get("alt_geom")) * 0.3048 / 1000) if item.get("alt_geom") is not None else None,
            "",                          # destination unknown
            item.get("flight") or item.get("icao24", ""),
            float(item.get("mag_heading")) if item.get("mag_heading") is not None else None,
            item.get("hex"),
        )
        for item in ac_items
        if isinstance(item, dict) and "lat" in item and "lon" in item
    ]
    return res


def _build_positions_from_opensky(states_list: List, center: Tuple[float, float], radius: float) -> List[Tuple]:
    """Convert OpenSky state objects into the unified position tuple list.

    Each tuple is (lat, lon, grounded, alt_km, destination, ident, mag_heading).
    """
    res = []
    for s in states_list:
        if distance.distance((s.latitude, s.longitude), center).km <= radius:
            alt_km = (s.geo_altitude / 1000) if getattr(s, "geo_altitude", None) is not None else None
            res.append(
                (
                    s.latitude,
                    s.longitude,
                    getattr(s, "on_ground", False),
                    alt_km,
                    "",  # destination unknown for OpenSky
                    s.callsign or s.icao24,
                    None,  # OpenSky does not provide mag_heading
                    s.icao24,
                )
            )
    return res


def run_opensky(radius: float, show_map: bool = False, generate_image: bool = False, output_file: str = "opensky_map.png", airplanes_live: bool = False):
    """Core OpenSky logic (original script).

    The function prints rich information about aircraft within the computed
    bounding box around a fixed origin point. If *show_map* is True, an OpenStreetMap
    link for each aircraft's current position is also printed. If *generate_image*
    is True, a static map image is generated and saved to *output_file*.
    """
    center = (orig.ORIGIN_LAT, orig.ORIGIN_LON)  # Default coordinates from origin module
    positions = []  # Collect aircraft positions for static map generation
    bounding_box = calculate_bbox(center[0], center[1], 100)

    if airplanes_live:
        # Use the airplanes.live service to retrieve aircraft within the radius
        radius_nm = radius / 1.852  # convert km to nautical miles as required by the API
        async def fetch_airplanes_live_area():
            _respect_airplanes_live_rate_limit()
            url = f"https://api.airplanes.live/v2/point/{center[0]}/{center[1]}/{radius_nm}"
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(url, headers={"User-Agent": "near-opensky/1.0"}, timeout=10.0)
                    resp.raise_for_status()
                    return resp.json()
            except httpx.HTTPError as exc:
                print(f"[WARN] Airplanes.live request failed: {exc}")
                return []

        live_data = asyncio.run(fetch_airplanes_live_area())
        # print(f"Data: {live_data}")
        if live_data and 'ac' in live_data:
            positions = _build_positions_from_airplanes_live(live_data.get('ac', []))
            print(f"[bold cyan]Fetched {len(positions)} aircraft from airplanes.live[/bold cyan]")
        else:
            print("[bold red]No aircraft data returned from airplanes.live.[/bold red]")
            return None
    else:
        api = OpenSkyApi()
        states = api.get_states(bbox=bounding_box)
        # print(f"States: {states}")

        if not (states and states.states):
            print("[bold red]No aircraft states returned.[/bold red]")
            return None

        # Filter and possibly expand radius using only in‑flight aircraft
        in_flight_states = [s for s in states.states if not getattr(s, "on_ground", False)]
        if in_flight_states:
            sorted_flight_states = sorted(
                in_flight_states,
                key=lambda s: distance.distance((s.latitude, s.longitude), center).km,
                reverse=True,
            )
            last = sorted_flight_states[-1]
            last_distance = distance.distance((last.latitude, last.longitude), center).km
            if last_distance > radius:
                numbers = (5, 10, 15, 25, 50, 75, 100)
                radius = min(x for x in numbers if x > last_distance)
                print(f"Changing radius {radius} → new radius {radius}")

        positions = _build_positions_from_opensky(states.states, center, radius)

    # -----------------------------------------------------------------
    # Print aircraft information and prepare radar map positions
    # -----------------------------------------------------------------
    radar_positions = []
    if positions:
        sorted_positions = sorted(
            positions,
            key=lambda p: distance.distance((p[0], p[1]), center).km,
            reverse=False,
        )
        print(f"[bold dim cyan]{'─' * 55}[/bold dim cyan]")
        for pos in sorted_positions:
            # print(f"Pos: {pos}")
            lat, lon, grounded, alt_km, dest, ident, mag_heading, icao24 = pos
            print(f"[bold]Callsign:[/bold] {ident}")
            if alt_km is not None:
                print(f"[bold]Altitude:[/bold] {alt_km:.1f} km")
            #if not airplanes_live:
            #    # OpenSky specific additional info
            #    state_obj = next((s for s in states.states if (s.latitude == lat and s.longitude == lon)), None)
            #    if state_obj:
            #        print(f"[bold]Origin:[/bold] {state_obj.origin_country}")
            print(
                f"[bold]Distance:[/bold] {distance.distance((lat, lon), center).km:.1f} km\n"
                f"[bold]Status:[/bold] {'✅ Grounded' if grounded else '✈️ In‑flight'}"
            )
            
            # Initialize route/airport variables to prevent UnboundLocalError
            opensky_route = None
            flightaware_route = None
            dep = "Unknown"
            arr = "Unknown"
            end_time = int(time.time())
            start_time = end_time - 60 * 60 * 24
            url = (
                f"https://opensky-network.org/api/flights/aircraft?icao24={icao24}&"
                f"begin={start_time}&end={end_time}"
            )
            req = requests.get(url, headers=tokens.headers())

            # # Optionally fetch route information for OpenSky (same as before)
            # if not airplanes_live:
            #     # Use the icao24 if available from the state object
            #     icao24 = state_obj.icao24 if (state_obj and getattr(state_obj, 'icao24', None)) else ident
                
            try:
                flights_history = req.json()
                if isinstance(flights_history, list) and flights_history:
                    current_callsign = state_obj.callsign.strip() if (state_obj and getattr(state_obj, 'callsign', None)) else (ident.strip() if ident else "")
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

            # callsign_for_fa = state_obj.callsign if (state_obj and getattr(state_obj, 'callsign', None)) else (ident if ident else None)
            callsign_for_fa = ident
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

            if not airplanes_live:
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
            if not airplanes_live and dest_label == "Unknown" and flightaware_route and 'to' in flightaware_route:
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
                osm_url = f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=12/{lat}/{lon}"
                print(f"[bold]Map:[/bold] {osm_url}")

            # Append position with destination label (empty if still unknown)
            print(f"[bold dim cyan]{'─' * 55}[/bold dim cyan]")
            if generate_image:
                # Append position with destination label and aircraft identifier (callsign)
                ident_label = ident.strip() if ident else ""
                radar_positions.append((lat, lon, grounded, alt_km, dest_label if dest_label != "Unknown" else "", ident_label, mag_heading))

    # Duplicate airplanes.live fetching removed – positions already collected earlier.
    # No further action needed here.
    # If the user requested an image but we have no aircraft, warn them
    if generate_image and not radar_positions:
        print("[WARN] No aircraft positions found – map image will not be generated.")
    if generate_image and radar_positions:
        generate_radar_image(radar_positions, center[0], center[1], radius, output_file)

    return 0


def main() -> int:
    """CLI entry point supporting two modes.


    * **OpenSky mode** – otherwise it runs the original OpenSky flight fetcher.
    """
    parser = argparse.ArgumentParser(description="Hybrid CLI: OpenSky flight fetcher.")
    parser.add_argument('--map', action='store_true', help='Print OpenStreetMap link for each aircraft position')
    parser.add_argument('--map-image', action='store_true', help='Generate a static OpenStreetMap image with aircraft markers')
    parser.add_argument('--output', type=str, default='opensky_map.png', help='Filename for the generated map image')
    parser.add_argument('--radius', type=float, default=100,
                        help='Radius in km for the OpenStreetMap bounding box (default 50)')
    parser.add_argument('--airplanes-live', action='store_true', help='Use airplanes.live API for aircraft position data instead of OpenSky data')
    args = parser.parse_args()
    # Run OpenSky functionality with the provided or default radius
    return run_opensky(args.radius, args.map, args.map_image, args.output, airplanes_live=args.airplanes_live)

if __name__ == '__main__':
    sys.exit(main())
