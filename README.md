# near‑sky

A sleek CLI tool that fetches live flight data from the OpenSky Network and visualises it on a radar‑style map.

## ✈️ Features
- **Live aircraft positions** within a configurable radius.
- **Static radar image** generation (`--map-image`) with optional destination labels (`--show-destinations`).
- **Dynamic origin**: edit `src/near_sky/origin.py` or provide a custom point via CLI.
- **Rich terminal output** using `rich` for colourised information.
- **Extensible** – add new helpers or data sources without touching the core driver.

## 📦 Installation
```bash
# Using pip (recommended)
python -m pip install .
# Or with uv (fast installer)
uv pip install .
```
> The package ships a wrapper script `run_near_sky.sh` that creates a temporary virtual environment on‑the‑fly.

## 🚀 Quick start
```bash
# Default radius (25 km) around the bundled origin (Basilica del Pilar, Zaragoza)
near‑sky

# Custom radius
near‑sky --radius 120

# Generate a radar PNG
near‑sky --map-image --output my_radar.png

# Show destination labels on the radar image
near‑sky --map-image --show-destinations
```

## 🎯 Configuring the origin
- **Edit the constants** in `src/near_sky/origin.py`:
  ```python
  ORIGIN_LAT = 41.6562
  ORIGIN_LON = -0.8805
  ```
- **Or set a custom origin at runtime** (future feature placeholder).

## 🛠️ Advanced flags
| Flag | Description |
|------|-------------|
| `--radius <km>` | Search radius in kilometres (default **25**). |
| `--map` | Print an OpenStreetMap link for each aircraft. |
| `--map-image` | Generate a static PNG radar image. |
| `--show-destinations` | Include destination labels on the radar image. |
| `--output <file>` | Filename for the generated PNG (default **sky_map.png**). |
| `--opensky` | Use OpenSky API instead of airplanes.live (default). |

## 🤝 Contributing
1. Fork the repository.
2. Create a feature branch.
3. Keep the code style consistent (`black`, `ruff`).
4. Write tests for new functionality.
5. Submit a pull request.

## 📜 License
This project is licensed under the **MIT License** – see the `LICENSE` file for details.
