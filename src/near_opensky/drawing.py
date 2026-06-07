from __future__ import annotations

import math
from typing import List

from PIL import Image, ImageDraw, ImageFont
from geopy import distance

from .models import AircraftPosition
from .utils import bearing_ellipsoidal, bearing_spherical, get_nearby_cities


def _draw_city(
    draw: ImageDraw.Draw,
    cx: int,
    cy: int,
    size: int,
    radius_km: float,
    center_lat: float,
    center_lon: float,
    name: str,
    clat: float,
    clon: float,
    font: ImageFont.ImageFont,
) -> None:
    lat1 = math.radians(center_lat)
    lon1 = math.radians(center_lon)
    lat2 = math.radians(clat)
    lon2 = math.radians(clon)
    y = math.sin(lon2 - lon1) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(lon2 - lon1)
    bearing = (math.degrees(math.atan2(y, x)) + 360) % 360
    dist_km = distance.distance((center_lat, center_lon), (clat, clon)).km
    r_pixels = (dist_km / radius_km) * (size / 2)
    angle_rad = math.radians(bearing)
    px = cx + r_pixels * math.sin(angle_rad)
    py = cy - r_pixels * math.cos(angle_rad)
    margin = 5
    px = max(margin, min(size - margin, px))
    py = max(margin, min(size - margin, py))
    draw.ellipse([px - 2, py - 2, px + 2, py + 2], fill=(0, 100, 0))
    draw.text((px + 5, py - 5), name, fill=(0, 100, 0), font=font)


def _draw_aircraft(
    draw: ImageDraw.Draw,
    cx: int,
    cy: int,
    size: int,
    radius_km: float,
    center_lat: float,
    center_lon: float,
    lat: float,
    lon: float,
    grounded: bool,
    dest: str,
    bearing: float,
    font: ImageFont.ImageFont,
    ident: str = "",
) -> None:
    dist_km = distance.distance((center_lat, center_lon), (lat, lon)).km
    if dist_km > radius_km:
        dist_km = radius_km
    r_pixels = (dist_km / radius_km) * (size / 2)
    angle_rad = math.radians(bearing)
    px = cx + r_pixels * math.sin(angle_rad)
    py = cy - r_pixels * math.cos(angle_rad)
    margin = 4
    px = max(margin, min(size - margin, px))
    py = max(margin, min(size - margin, py))
    if grounded:
        sq = 6
        draw.rectangle([px - sq / 2, py - sq / 2, px + sq / 2, py + sq / 2], fill="blue")
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
    draw.ellipse([px - 4, py - 4, px + 4, py + 4], fill="red")
    if dest:
        draw.text((px + 6, py - 6), dest, fill="yellow", font=font)
    if ident:
        draw.text((px + 6, py + 6), ident, fill="white", font=font)


def generate_radar_image(
    positions: List[AircraftPosition],
    center_lat: float,
    center_lon: float,
    radius_km: float,
    output_file: str,
) -> None:
    size = 800
    img = Image.new("RGB", (size, size), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    cx, cy = size // 2, size // 2
    draw.ellipse([cx - size // 2, cy - size // 2, cx + size // 2, cy + size // 2], outline="green")
    draw.ellipse([cx - 3, cy - 3, cx + 3, cy + 3], fill="green")
    for dist in (5, 10, 25, 50):
        if dist < radius_km:
            r = (dist / radius_km) * (size / 2)
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline="green")
    cities = get_nearby_cities(center_lat, center_lon, radius_km)
    sorted_cities = sorted(cities, key=lambda x: (0 if x[4] == "city" else 1, x[3]))
    for name, clat, clon, dist_km, place_type in sorted_cities[:12]:
        _draw_city(draw, cx, cy, size, radius_km, center_lat, center_lon, name, clat, clon, font)
    for pos in positions:
        bearing = pos.mag_heading
        if bearing is None:
            bearing = bearing_ellipsoidal(center_lat, center_lon, pos.lat, pos.lon)
        _draw_aircraft(
            draw,
            cx,
            cy,
            size,
            radius_km,
            center_lat,
            center_lon,
            pos.lat,
            pos.lon,
            pos.grounded,
            pos.dest,
            bearing,
            font,
            pos.ident,
        )
    img.save(output_file)
