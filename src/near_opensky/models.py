from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class AircraftPosition:
    latitude: float
    longitude: float
    grounded: bool
    alt_km: Optional[float] = None
    dest: str = ""
    ident: str = ""
    mag_heading: Optional[float] = None
    icao24: str = ""
