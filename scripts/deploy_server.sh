#!/usr/bin/env bash
set -euo pipefail

if [[ ! -f ".env" ]]; then
  echo ".env not found. Please run: cp .env.example .env and fill required values."
  exit 1
fi

echo "Starting Auto Ledger (server mode)..."
docker compose -f docker-compose.server.yml up -d --build

echo "Service status:"
docker compose -f docker-compose.server.yml ps

echo "Done. Check health endpoint:"
echo "  curl https://<YOUR_DOMAIN>/health"

