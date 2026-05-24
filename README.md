# near-opensky

A CLI tool that fetches live flight data from the OpenSky Network (using the opensky‑api library).

## Usage

```bash
# OpenSky mode (default radius 50 km)
near-opensky

# Custom radius
near-opensky --radius 120
```

The project is installable via `uv` and provides an automatic wrapper script `run_near_opensky.sh` that creates a virtual environment on the fly.
