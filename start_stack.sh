#!/usr/bin/env bash
set -euo pipefail

echo "Starting TheSNMC RustDB docker stack..."
docker compose up --build
