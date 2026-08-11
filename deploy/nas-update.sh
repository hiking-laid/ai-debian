#!/bin/bash
# Update the Toddler Dinner Planner on the NAS: pull the latest image and restart.
# Put this next to docker-compose.prod.yml on the NAS and run it (Task Scheduler or SSH).
set -euo pipefail

# Work from the folder this script lives in, so it finds docker-compose.prod.yml
cd "$(dirname "$0")"

COMPOSE_FILE="docker-compose.prod.yml"

# The Docker daemon needs root. Task Scheduler already runs as root; over SSH you usually don't,
# so prefix with sudo only when we're not root (avoids requiring sudo to exist for root).
if [ "$(id -u)" -ne 0 ]; then
  SUDO="sudo"
else
  SUDO=""
fi

# Support both Docker Compose v2 ("docker compose") and the legacy "docker-compose".
if $SUDO docker compose version >/dev/null 2>&1; then
  COMPOSE="$SUDO docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE="$SUDO docker-compose"
else
  echo "ERROR: neither 'docker compose' nor 'docker-compose' is available." >&2
  exit 1
fi

echo "==> Pulling latest image..."
$COMPOSE -f "$COMPOSE_FILE" pull

echo "==> Recreating container (DB migrations run on startup)..."
$COMPOSE -f "$COMPOSE_FILE" up -d

echo "==> Cleaning up old images..."
$SUDO docker image prune -f >/dev/null 2>&1 || true

echo "==> Current status:"
$COMPOSE -f "$COMPOSE_FILE" ps
echo "Done."
