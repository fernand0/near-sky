#!/usr/bin/env bash
# ------------------------------------------------------------
# Auto‑create a persistent .venv (if missing) and run the near‑opensky CLI.
# Place this script in the project root (near‑opensky directory).
# ------------------------------------------------------------

set -euo pipefail   # safer Bash execution

# Determine project root and venv location
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${PROJECT_ROOT}/.venv"

# Create the virtual environment on first run
if [ ! -d "${VENV_DIR}" ]; then
    echo "⏳ Creating virtual environment in ${VENV_DIR}..."
    uv venv "${VENV_DIR}" || { echo "❌ uv venv failed"; exit 1; }
    echo "✅ Virtual environment created."
else
    echo "[uv‑wrapper] Reusing existing .venv"
fi

# Activate the environment
# shellcheck source=/dev/null
source "${VENV_DIR}/bin/activate"

# Ensure dependencies are installed (editable install)
# This is safe to run repeatedly; uv will skip already‑satisfied packages.
uv pip install -e "${PROJECT_ROOT}"

# Execute the CLI script with any arguments passed to this wrapper
exec python -m near_opensky.near_opensky "$@"
