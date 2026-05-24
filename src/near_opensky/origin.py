# origin.py – default geographic origin for OpenSky queries

# Latitude and longitude of the default point (Basilica del Pilar, Zaragoza, Spain)
ORIGIN_LAT = 41.6562
ORIGIN_LON = -0.8778

# Users can modify these constants to change the reference location for the
# near‑opensky CLI without altering the main script.
# Utility to set origin coordinates via location name
from geopy.geocoders import Nominatim
from typing import Tuple

def get_coordinates(location: str) -> Tuple[float, float]:
    """
    Retrieve latitude and longitude for a given location name using Nominatim.
    Returns a (lat, lon) tuple. Raises ValueError if location not found.
    """
    geocoder = Nominatim(user_agent="near_opensky_cli")
    geocode = geocoder.geocode(location)
    if not geocode:
        raise ValueError(f"Location '{location}' not found.")
    return float(geocode.latitude), float(geocode.longitude)

def set_origin_by_name(location: str) -> None:
    """
    Update ORIGIN_LAT and ORIGIN_LON constants based on location name.
    """
    global ORIGIN_LAT, ORIGIN_LON
    lat, lon = get_coordinates(location)
    ORIGIN_LAT = lat
    ORIGIN_LON = lon

# Example CLI usage:
if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Usage: python origin.py \"Location Name\"")
        sys.exit(1)
    try:
        set_origin_by_name(sys.argv[1])
        print(f"Origin set to ({ORIGIN_LAT}, {ORIGIN_LON})")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
