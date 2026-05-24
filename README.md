# near-opensky

A CLI tool that fetches live flight data from the OpenSky Network (using the opensky‑api library).

## What it does

The tool queries the OpenSky API for aircraft within a **radius (km) around a default geographic point**. By default the point is set to the coordinates of the Basilica del Pilar in Zaragoza, Spain. These coordinates are defined in `src/near_opensky/origin.py` so you can easily adjust the reference location without touching the main script.

## Usage

```bash
# OpenSky mode (default radius 25 km around the default origin)
near-opensky

# Custom radius
near-opensky --radius 120
```

### Configuring the default origin

Edit `src/near_opensky/origin.py` and change the `ORIGIN_LAT` and `ORIGIN_LON` constants to the latitude and longitude you want the CLI to use as the centre of the search area.

## Custom origin via CLI

You can set a custom origin without editing the source code by using the new command‑line interface provided in `src/near_opensky/origin.py`.

```bash
python src/near_opensky/origin.py "City, Country"
```

Running this command updates the internal origin coordinates and prints the new values, e.g., `Origin set to (48.8566, 2.3522)` for Paris. The CLI will then use this location for subsequent `near-opensky` queries.


## Token handling

If you set the environment variable `OPENSKY_TOKEN` the CLI will include it in API requests that require authentication. Without the token the tool still works for public data calls.

The project is installable via `uv` and provides an automatic wrapper script `run_near_opensky.sh` that creates a virtual environment on the fly.
